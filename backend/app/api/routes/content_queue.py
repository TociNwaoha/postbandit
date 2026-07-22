import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.config import settings
from app.models.brand_profile import BrandProfile
from app.models.content_queue_item import ContentQueueItem
from app.models.user import User
from app.schemas.content_queue import (
    BrandProfileResponse,
    BrandProfileUpsertRequest,
    ContentQueueGenerateRequest,
    ContentQueueItemResponse,
    ContentQueueUpdateRequest,
    validate_status_filter,
)
from app.services.content_agent import generate_and_queue_carousel

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/brand-profile", response_model=BrandProfileResponse)
async def get_brand_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.scalar(select(BrandProfile).where(BrandProfile.user_id == current_user.id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand profile not found")
    return row


@router.post("/brand-profile", response_model=BrandProfileResponse)
async def upsert_brand_profile(
    body: BrandProfileUpsertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.scalar(select(BrandProfile).where(BrandProfile.user_id == current_user.id))
    if not row:
        row = BrandProfile(user_id=current_user.id)
        db.add(row)

    row.display_name = body.display_name
    row.handle = body.handle
    row.niche = body.niche
    row.target_audience = body.target_audience
    row.tone = body.tone
    row.use_phrases = body.use_phrases
    row.avoid_phrases = body.avoid_phrases
    row.ai_cmo_enabled = body.ai_cmo_enabled
    row.post_frequency = body.post_frequency
    row.preferred_platforms = body.preferred_platforms

    await db.commit()
    await db.refresh(row)
    return row


@router.get("/content-queue", response_model=list[ContentQueueItemResponse])
async def list_content_queue(
    status_filter: str | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        normalized_status = validate_status_filter(status_filter)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    query = select(ContentQueueItem).where(ContentQueueItem.user_id == current_user.id)
    if normalized_status:
        query = query.where(ContentQueueItem.status == normalized_status)
    query = query.order_by(ContentQueueItem.created_at.desc())

    rows = (await db.execute(query)).scalars().all()
    return list(rows)


@router.get("/content-queue/{item_id}", response_model=ContentQueueItemResponse)
async def get_content_queue_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.scalar(
        select(ContentQueueItem).where(ContentQueueItem.id == item_id, ContentQueueItem.user_id == current_user.id)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found")
    return row


@router.post("/content-queue/generate", response_model=ContentQueueItemResponse)
async def generate_content_queue_item(
    body: ContentQueueGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        item = await generate_and_queue_carousel(
            user_id=current_user.id,
            topic=body.topic,
            template_id=body.template_id,
            platforms=body.platforms,
            db=db,
        )
        return item
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[content_queue] generate failed user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Bandit LM generation failed. Please try again.",
        ) from exc


@router.patch("/content-queue/{item_id}", response_model=ContentQueueItemResponse)
async def update_content_queue_item(
    item_id: uuid.UUID,
    body: ContentQueueUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.scalar(
        select(ContentQueueItem).where(ContentQueueItem.id == item_id, ContentQueueItem.user_id == current_user.id)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found")

    if body.config is not None:
        row.config = body.config
    if body.platforms is not None:
        row.platforms = body.platforms
    if "scheduled_at" in body.model_fields_set:
        row.scheduled_at = body.scheduled_at
        if row.scheduled_at is not None:
            row.asset_cleanup_at = None

    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/content-queue/{item_id}/approve", response_model=ContentQueueItemResponse)
async def approve_content_queue_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.scalar(
        select(ContentQueueItem).where(ContentQueueItem.id == item_id, ContentQueueItem.user_id == current_user.id)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found")

    row.status = "approved"
    row.asset_cleanup_at = None
    if row.scheduled_at and row.scheduled_at.tzinfo is None:
        row.scheduled_at = row.scheduled_at.replace(tzinfo=timezone.utc)

    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/content-queue/{item_id}/reject", response_model=ContentQueueItemResponse)
async def reject_content_queue_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.scalar(
        select(ContentQueueItem).where(ContentQueueItem.id == item_id, ContentQueueItem.user_id == current_user.id)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found")

    row.status = "rejected"
    row.asset_cleanup_at = datetime.now(timezone.utc) + timedelta(
        days=max(1, int(settings.content_queue_rejected_asset_retention_days))
    )
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/content-queue/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content_queue_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.scalar(
        select(ContentQueueItem).where(ContentQueueItem.id == item_id, ContentQueueItem.user_id == current_user.id)
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found")

    await db.delete(row)
    await db.commit()
    return None
