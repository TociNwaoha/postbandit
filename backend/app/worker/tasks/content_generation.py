import asyncio
import logging
import random

from sqlalchemy import select

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.brand_profile import BrandProfile
from app.services.content_agent import generate_and_queue_carousel

logger = logging.getLogger(__name__)


def pick_topic_for_niche(niche: str) -> str:
    normalized_niche = (niche or "your niche").strip() or "your niche"
    templates = [
        f"3 tools that will change how you work in {normalized_niche}",
        f"The biggest mistake people make in {normalized_niche}",
        f"Why most people fail at {normalized_niche} (and how to fix it)",
        f"The fastest way to get results in {normalized_niche}",
        f"What nobody tells you about {normalized_niche}",
    ]
    return random.choice(templates)


async def _run_generation() -> None:
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(BrandProfile).where(
                    BrandProfile.ai_cmo_enabled.is_(True),
                    BrandProfile.post_frequency > 0,
                )
            )
        ).scalars().all()

        for brand in rows:
            frequency = max(0, min(int(brand.post_frequency or 0), 5))
            for _ in range(frequency):
                topic = pick_topic_for_niche(brand.niche)
                try:
                    await generate_and_queue_carousel(
                        user_id=brand.user_id,
                        topic=topic,
                        template_id="viral-dark",
                        platforms=list(brand.preferred_platforms or []),
                        db=db,
                    )
                except Exception as exc:
                    logger.warning(
                        "[content_generation] generation failed user_id=%s topic=%s error=%s",
                        brand.user_id,
                        topic,
                        exc,
                    )


@celery_app.task(name="generate_daily_content")
def generate_daily_content() -> None:
    asyncio.run(_run_generation())
