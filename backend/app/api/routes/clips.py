import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.database import get_db
from app.models.user import User
from app.models.clip import Clip
from app.models.video import Video
from app.schemas.clip import ClipResponse, ClipUpdateRequest
from app.api.deps import get_current_user
from app.services.ai_copy import AICopyUnavailableError, generate_clip_copy, provider_configured
from app.services.r2 import r2_client

router = APIRouter()
logger = logging.getLogger(__name__)

MIN_CLIP_DURATION_SEC = 1.0


def _clip_to_response(clip: Clip) -> ClipResponse:
    thumbnail_url: str | None = None
    if clip.thumbnail_key:
        try:
            thumbnail_url = r2_client.get_presigned_download_url(clip.thumbnail_key)
        except Exception:
            thumbnail_url = None

    return ClipResponse(
        id=clip.id,
        video_id=clip.video_id,
        start_time=clip.start_time,
        end_time=clip.end_time,
        duration_sec=clip.duration_sec,
        score=clip.score,
        hook_score=clip.hook_score,
        energy_score=clip.energy_score,
        title=clip.title,
        hashtags=clip.hashtags,
        title_options=clip.title_options,
        hashtag_options=clip.hashtag_options,
        copy_generation_status=clip.copy_generation_status,
        copy_generation_error=clip.copy_generation_error,
        thumbnail_key=clip.thumbnail_key,
        thumbnail_url=thumbnail_url,
        transcript_text=clip.transcript_text,
        status=clip.status,
        created_at=clip.created_at,
        updated_at=clip.updated_at,
    )


@router.get("/clips", response_model=list[ClipResponse])
async def list_clips(
    video_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(Clip)
        .join(Video, Clip.video_id == Video.id)
        .where(Video.user_id == current_user.id)
        .order_by(Clip.score.desc())
    )
    if video_id:
        try:
            video_uuid = uuid.UUID(video_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid video_id")
        query = query.where(Clip.video_id == video_uuid)

    result = await db.execute(query)
    clips = result.scalars().all()
    return [_clip_to_response(clip) for clip in clips]


@router.get("/clips/{clip_id}", response_model=ClipResponse)
async def get_clip(
    clip_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        clip_uuid = UUID(clip_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid clip_id")

    result = await db.execute(
        select(Clip)
        .join(Video, Clip.video_id == Video.id)
        .where(Clip.id == clip_uuid, Video.user_id == current_user.id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    return _clip_to_response(clip)


@router.post("/clips/{clip_id}/generate-copy", response_model=ClipResponse)
async def generate_copy_for_clip(
    clip_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        clip_uuid = UUID(clip_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid clip_id")

    row = await db.execute(
        select(Clip, Video)
        .join(Video, Clip.video_id == Video.id)
        .where(Clip.id == clip_uuid, Video.user_id == current_user.id)
    )
    clip_row = row.first()
    if not clip_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    clip, video = clip_row
    transcript_text = " ".join((clip.transcript_text or "").split())
    if not transcript_text:
        clip.title_options = None
        clip.hashtag_options = None
        clip.copy_generation_status = "unavailable"
        clip.copy_generation_error = "Clip transcript text is unavailable"
        await db.commit()
        await db.refresh(clip)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clip transcript text is unavailable")

    if not provider_configured():
        clip.title_options = None
        clip.hashtag_options = None
        clip.copy_generation_status = "unavailable"
        clip.copy_generation_error = "DEEPSEEK_API_KEY is not configured"
        await db.commit()
        await db.refresh(clip)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI copy unavailable")

    try:
        generated = generate_clip_copy(
            transcript_text=transcript_text,
            video_title=video.title,
            clip_start=clip.start_time,
            clip_end=clip.end_time,
        )
    except AICopyUnavailableError as exc:
        clip.title_options = None
        clip.hashtag_options = None
        clip.copy_generation_status = "unavailable"
        clip.copy_generation_error = str(exc)[:500]
        await db.commit()
        await db.refresh(clip)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI copy unavailable")
    except Exception as exc:
        logger.warning("[clips] generate copy failed clip_id=%s error=%s", clip.id, exc)
        clip.title_options = None
        clip.hashtag_options = None
        clip.copy_generation_status = "unavailable"
        clip.copy_generation_error = str(exc)[:500]
        await db.commit()
        await db.refresh(clip)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate clip copy")

    clip.title_options = generated.title_options
    clip.hashtag_options = generated.hashtag_options
    clip.copy_generation_status = "ready"
    clip.copy_generation_error = None
    clip.title = generated.title_options[0] if generated.title_options else clip.title
    clip.hashtags = generated.hashtag_options[0] if generated.hashtag_options else clip.hashtags
    await db.commit()
    await db.refresh(clip)

    logger.info(
        "[clips] generate copy complete user_id=%s clip_id=%s titles=%s hashtag_sets=%s",
        current_user.id,
        clip.id,
        len(generated.title_options),
        len(generated.hashtag_options),
    )
    return _clip_to_response(clip)


@router.patch("/clips/{clip_id}", response_model=ClipResponse)
async def update_clip(
    clip_id: str,
    body: ClipUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        clip_uuid = UUID(clip_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid clip_id")

    logger.info(
        "[clips] update requested user_id=%s clip_id=%s video_id=%s start=%s end=%s",
        current_user.id,
        clip_id,
        body.video_id,
        body.start_time,
        body.end_time,
    )

    result = await db.execute(
        select(Clip, Video)
        .join(Video, Clip.video_id == Video.id)
        .where(Clip.id == clip_uuid, Video.user_id == current_user.id)
    )
    row = result.first()
    if not row:
        logger.warning("[clips] update denied user_id=%s clip_id=%s reason=not_found_or_forbidden", current_user.id, clip_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    clip, video = row
    if clip.video_id != body.video_id:
        logger.warning(
            "[clips] update denied user_id=%s clip_id=%s reason=video_mismatch clip_video_id=%s request_video_id=%s",
            current_user.id,
            clip_id,
            clip.video_id,
            body.video_id,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Clip does not belong to the provided video")

    start_time = max(float(body.start_time), 0.0)
    end_time = max(float(body.end_time), 0.0)

    if video.duration_sec and video.duration_sec > 0:
        start_time = min(start_time, float(video.duration_sec))
        end_time = min(end_time, float(video.duration_sec))

    if end_time <= start_time:
        logger.warning(
            "[clips] timing validation failed clip_id=%s start=%s end=%s reason=end_not_greater",
            clip_id,
            start_time,
            end_time,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End time must be greater than start time")

    duration_sec = round(end_time - start_time, 3)
    if duration_sec < MIN_CLIP_DURATION_SEC:
        logger.warning(
            "[clips] timing validation failed clip_id=%s start=%s end=%s duration=%s reason=too_short",
            clip_id,
            start_time,
            end_time,
            duration_sec,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Clip duration must be at least {MIN_CLIP_DURATION_SEC:.0f} second",
        )

    clip.start_time = round(start_time, 3)
    clip.end_time = round(end_time, 3)
    clip.duration_sec = duration_sec

    await db.flush()
    await db.refresh(clip)

    logger.info(
        "[clips] update saved user_id=%s clip_id=%s start=%s end=%s duration=%s",
        current_user.id,
        clip.id,
        clip.start_time,
        clip.end_time,
        clip.duration_sec,
    )
    return _clip_to_response(clip)
