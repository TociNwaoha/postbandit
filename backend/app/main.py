import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from sqlalchemy import select

from app.api.routes import auth, clips, exports, health, social, storage, videos
from app.config import settings
from app.database import SessionLocal, engine

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def run_migrations():
    import os

    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_sync_url)

    import asyncio

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: command.upgrade(alembic_cfg, "head"))


async def seed_admin_user():
    from app.models.user import User

    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email == settings.admin_email))
        existing = result.scalar_one_or_none()
        if not existing:
            admin = User(
                email=settings.admin_email,
                password_hash=pwd_context.hash(settings.admin_password),
            )
            db.add(admin)
            await db.commit()
            logger.info("Admin user created: %s", settings.admin_email)
        else:
            logger.info("Admin user already exists")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Running database migrations...")
    try:
        await run_migrations()
        logger.info("Migrations complete")
    except Exception as exc:
        logger.error("Migration failed: %s", exc)
        raise

    await seed_admin_user()
    yield

    await engine.dispose()


app = FastAPI(
    title="PostBandit API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.nextauth_url,
        settings.frontend_public_url,
        "http://localhost:3001",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(videos.router, prefix="/api")
app.include_router(clips.router, prefix="/api")
app.include_router(exports.router, prefix="/api")
app.include_router(storage.router, prefix="/api")
app.include_router(social.router, prefix="/api")
