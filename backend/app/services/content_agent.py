from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_profile import BrandProfile
from app.models.content_queue_item import ContentQueueItem
from app.services.bandit_lm import generate_carousel_config
from app.config import settings
from app.services.carousel import render_config


async def generate_and_queue_carousel(
    user_id: uuid.UUID,
    topic: str,
    template_id: str = "viral-dark",
    platforms: list[str] | None = None,
    db: AsyncSession | None = None,
) -> ContentQueueItem:
    if db is None:
        raise ValueError("Database session is required")

    brand = await db.scalar(select(BrandProfile).where(BrandProfile.user_id == user_id))
    if not brand:
        raise ValueError("Brand profile not set up. Complete onboarding first.")

    config = await generate_carousel_config(topic, brand, template_id)
    render_result = render_config(template_id=template_id, config=config, user_id=user_id)
    slide_urls = [slide.get("url") for slide in render_result.get("slides", []) if isinstance(slide, dict) and slide.get("url")]
    slide_keys = [str(key) for key in render_result.get("slide_keys", []) if key]
    zip_payload = render_result.get("zip") if isinstance(render_result.get("zip"), dict) else {}
    zip_key = str(zip_payload.get("key")) if zip_payload.get("key") else None
    preview_key = str(render_result.get("preview_key")) if render_result.get("preview_key") else None
    cleanup_at = datetime.now(timezone.utc) + timedelta(days=max(1, int(settings.content_queue_ready_asset_retention_days)))

    item = ContentQueueItem(
        user_id=user_id,
        content_type="carousel",
        config=config,
        slide_urls=slide_urls,
        slide_keys_json=slide_keys,
        zip_key=zip_key,
        preview_key=preview_key,
        asset_cleanup_at=cleanup_at,
        status="ready",
        platforms=platforms or list(brand.preferred_platforms or []),
        generation_topic=topic,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item
