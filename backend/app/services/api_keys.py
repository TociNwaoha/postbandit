import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey

MAX_ACTIVE_API_KEYS = 5
KEY_PREFIX = "pb_live_"


def generate_api_key() -> tuple[str, str, str]:
    raw = secrets.token_urlsafe(30)
    full_key = f"{KEY_PREFIX}{raw}"
    key_hash = hash_api_key(full_key)
    key_prefix = f"{full_key[:12]}...{full_key[-4:]}"
    return full_key, key_hash, key_prefix


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


def looks_like_api_key(value: str | None) -> bool:
    return bool(value and value.startswith(KEY_PREFIX) and len(value) >= len(KEY_PREFIX) + 20)


async def create_api_key(db: AsyncSession, *, user_id: uuid.UUID, name: str) -> tuple[ApiKey, str]:
    clean_name = " ".join((name or "").strip().split())
    if not clean_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key name is required")

    active_count = int(
        await db.scalar(
            select(func.count(ApiKey.id)).where(ApiKey.user_id == user_id, ApiKey.is_active.is_(True))
        )
        or 0
    )
    if active_count >= MAX_ACTIVE_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You can have at most {MAX_ACTIVE_API_KEYS} active API keys.",
        )

    for _ in range(5):
        full_key, key_hash, key_prefix = generate_api_key()
        existing = await db.scalar(select(ApiKey.id).where(ApiKey.key_hash == key_hash).limit(1))
        if existing:
            continue
        row = ApiKey(user_id=user_id, name=clean_name, key_hash=key_hash, key_prefix=key_prefix)
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row, full_key

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create API key")


async def list_api_keys(db: AsyncSession, *, user_id: uuid.UUID) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user_id)
        .order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_api_key(db: AsyncSession, *, user_id: uuid.UUID, key_id: uuid.UUID) -> None:
    row = await db.scalar(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    row.is_active = False
    await db.flush()


async def find_active_api_key(db: AsyncSession, *, full_key: str) -> ApiKey | None:
    key_hash = hash_api_key(full_key)
    return await db.scalar(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    )


def mark_api_key_used(row: ApiKey) -> None:
    row.last_used_at = datetime.now(timezone.utc)
