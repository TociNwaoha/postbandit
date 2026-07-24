import logging
import io
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile, status
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.database import get_db
from app.models.clip_overlay_asset import ClipOverlayAsset
from app.models.export import Export
from app.models.transcript import TranscriptSegment
from app.models.user import User
from app.models.clip import Clip
from app.models.video import Video
from app.schemas.clip import (
    ClipCopyGenerateRequest,
    ClipCopyOptionsResponse,
    ClipGenerateCarouselResponse,
    ClipOverlayAssetResponse,
    ClipResponse,
    ClipUpdateRequest,
    PlatformCopyFields,
    PlatformCopyGenerateRequest,
    PlatformCopyGenerateResponse,
)
from app.api.deps import get_current_user
from app.services.ai_copy import (
    AICopyError,
    AICopyUnavailableError,
    generate_content_brief,
    generate_copy_options,
    generate_platform_copy,
    provider_configured,
)
from app.services.editor_quota import enforce_storage_hard_stop
from app.services.object_storage import object_storage_client
from app.services.video_carousel import (
    VideoCarouselGenerationError,
    create_video_carousel_queue_item,
)

router = APIRouter()
logger = logging.getLogger(__name__)

MIN_CLIP_DURATION_SEC = 1.0
MAX_CLIP_OVERLAY_ASSET_BYTES = 25 * 1024 * 1024
ALLOWED_OVERLAY_IMAGE_FORMATS = {
    "PNG": ("image/png", ".png"),
    "JPEG": ("image/jpeg", ".jpg"),
    "WEBP": ("image/webp", ".webp"),
}


async def _clip_transcript_for_generation(db: AsyncSession, clip: Clip) -> str:
    transcript_text = " ".join((clip.transcript_text or "").split())
    if transcript_text:
        return transcript_text

    result = await db.execute(
        select(TranscriptSegment.word)
        .where(
            TranscriptSegment.video_id == clip.video_id,
            TranscriptSegment.start_time < clip.end_time,
            TranscriptSegment.end_time > clip.start_time,
        )
        .order_by(TranscriptSegment.start_time.asc())
    )
    return " ".join(str(word).strip() for word in result.scalars().all() if word and str(word).strip())


def _clip_to_response(clip: Clip) -> ClipResponse:
    thumbnail_url: str | None = None
    if clip.thumbnail_key:
        try:
            thumbnail_url = object_storage_client.get_thumbnail_url(clip.thumbnail_key)
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
        content_brief=clip.content_brief,
        status=clip.status,
        created_at=clip.created_at,
        updated_at=clip.updated_at,
    )


def _overlay_asset_to_response(asset: ClipOverlayAsset) -> ClipOverlayAssetResponse:
    return ClipOverlayAssetResponse(
        id=asset.id,
        clip_id=asset.clip_id,
        user_id=asset.user_id,
        original_filename=asset.original_filename,
        mime_type=asset.mime_type,
        size_bytes=int(asset.size_bytes or 0),
        width=asset.width,
        height=asset.height,
        download_url=object_storage_client.get_presigned_download_url(asset.storage_key),
        created_at=asset.created_at,
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


@router.post("/clips/{clip_id}/overlay-assets", response_model=ClipOverlayAssetResponse)
async def upload_clip_overlay_asset(
    clip_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        clip_uuid = UUID(clip_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid clip_id")

    clip_result = await db.execute(
        select(Clip)
        .join(Video, Clip.video_id == Video.id)
        .where(Clip.id == clip_uuid, Video.user_id == current_user.id)
    )
    clip = clip_result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    raw = await file.read()
    size_bytes = len(raw)
    if size_bytes <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded image is empty")
    if size_bytes > MAX_CLIP_OVERLAY_ASSET_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image exceeds the 25 MB limit",
        )

    try:
        with Image.open(io.BytesIO(raw)) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
            image.verify()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload must be a valid PNG, JPG, or WebP image",
        ) from exc

    format_meta = ALLOWED_OVERLAY_IMAGE_FORMATS.get(image_format)
    if not format_meta or width <= 0 or height <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload must be a valid PNG, JPG, or WebP image",
        )

    await enforce_storage_hard_stop(
        db,
        current_user.id,
        incoming_bytes=size_bytes,
        operation_label="clip overlay upload",
    )

    mime_type, extension = format_meta
    asset_id = uuid.uuid4()
    key = f"clip-overlays/{current_user.id}/{clip.id}/{asset_id}{extension}"
    object_storage_client.upload_fileobj(io.BytesIO(raw), key, content_type=mime_type)

    asset = ClipOverlayAsset(
        id=asset_id,
        clip_id=clip.id,
        user_id=current_user.id,
        storage_key=key,
        original_filename=Path(file.filename or f"overlay{extension}").name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        width=width,
        height=height,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    logger.info(
        "[clips] overlay asset uploaded user_id=%s clip_id=%s asset_id=%s size_bytes=%s",
        current_user.id,
        clip.id,
        asset.id,
        size_bytes,
    )
    return _overlay_asset_to_response(asset)


@router.delete("/clips/{clip_id}/overlay-assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_clip_overlay_asset(
    clip_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        clip_uuid = UUID(clip_id)
        asset_uuid = UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid clip or asset id")

    result = await db.execute(
        select(ClipOverlayAsset)
        .join(Clip, ClipOverlayAsset.clip_id == Clip.id)
        .join(Video, Clip.video_id == Video.id)
        .where(
            ClipOverlayAsset.id == asset_uuid,
            ClipOverlayAsset.clip_id == clip_uuid,
            ClipOverlayAsset.user_id == current_user.id,
            Video.user_id == current_user.id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overlay asset not found")

    referenced = await db.scalar(
        select(Export.id).where(Export.overlay_image_asset_id == asset.id).limit(1)
    )
    if referenced:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This image is used by an export and cannot be deleted",
        )

    try:
        object_storage_client.delete_file(asset.storage_key)
    except Exception as exc:
        logger.warning(
            "[clips] overlay storage delete failed user_id=%s asset_id=%s key=%s error=%s",
            current_user.id,
            asset.id,
            asset.storage_key,
            exc,
        )
    await db.delete(asset)
    await db.commit()
    logger.info("[clips] overlay asset deleted user_id=%s asset_id=%s", current_user.id, asset.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/clips/{clip_id}/generate-copy", response_model=ClipCopyOptionsResponse)
async def generate_copy_for_clip(
    clip_id: str,
    platform: str | None = None,
    body: ClipCopyGenerateRequest | None = Body(default=None),
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
        requested_platform = (body.platform if body and body.platform is not None else platform)
        instructions = body.instructions if body else None
        content_brief = " ".join((clip.content_brief or "").split())
        if not content_brief:
            content_brief = generate_content_brief(
                transcript_text=transcript_text,
                video_title=video.title,
            )
            clip.content_brief = content_brief
            await db.commit()
            await db.refresh(clip)

        generated = generate_copy_options(
            content_brief=content_brief,
            video_title=video.title,
            platform=requested_platform,
            instructions=instructions,
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

    clip.title_options = generated.titles
    clip.hashtag_options = generated.hashtag_sets
    clip.copy_generation_status = "ready"
    clip.copy_generation_error = None
    clip.title = generated.titles[0] if generated.titles else clip.title
    clip.hashtags = generated.hashtag_sets[0] if generated.hashtag_sets else clip.hashtags
    await db.commit()
    await db.refresh(clip)

    logger.info(
        "[clips] generate copy complete user_id=%s clip_id=%s platform=%s titles=%s captions=%s descriptions=%s hashtag_sets=%s",
        current_user.id,
        clip.id,
        generated.platform or "universal",
        len(generated.titles),
        len(generated.captions),
        len(generated.descriptions),
        len(generated.hashtag_sets),
    )
    return ClipCopyOptionsResponse(
        provider_used="deepseek",
        titles=generated.titles,
        captions=generated.captions,
        descriptions=generated.descriptions,
        hashtag_sets=generated.hashtag_sets,
        platform=generated.platform,
    )


@router.post("/clips/{clip_id}/generate-carousel", response_model=ClipGenerateCarouselResponse)
async def generate_carousel_for_clip(
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

    transcript_text = await _clip_transcript_for_generation(db, clip)
    if not transcript_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip transcript text is unavailable",
        )

    content_brief = " ".join((clip.content_brief or "").split())
    if not content_brief and provider_configured():
        try:
            content_brief = generate_content_brief(
                transcript_text=transcript_text,
                video_title=video.title,
            )
            clip.content_brief = content_brief
            await db.commit()
            await db.refresh(clip)
        except Exception as exc:
            logger.warning("[clips] content brief fallback failed clip_id=%s error=%s", clip.id, exc)
            content_brief = ""

    try:
        item, provider_used = await create_video_carousel_queue_item(
            user_id=current_user.id,
            clip_id=clip.id,
            transcript=transcript_text,
            content_brief=content_brief,
            db=db,
        )
    except VideoCarouselGenerationError as exc:
        logger.warning("[clips] generate carousel failed clip_id=%s error=%s", clip.id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc) or "Carousel generation is temporarily unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("[clips] generate carousel save failed clip_id=%s", clip.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate carousel",
        ) from exc

    slide_count = len(item.config.get("slides") or [])
    redirect_url = f"/carousels/new?queueItem={item.id}"
    logger.info(
        "[clips] generate carousel complete user_id=%s clip_id=%s queue_item_id=%s slides=%s provider=%s",
        current_user.id,
        clip.id,
        item.id,
        slide_count,
        provider_used,
    )
    return ClipGenerateCarouselResponse(
        carousel_id=item.id,
        queue_item_id=item.id,
        slide_count=slide_count,
        provider_used=provider_used,
        redirect_url=redirect_url,
    )


@router.post(
    "/clips/{clip_id}/generate-platform-copy",
    response_model=PlatformCopyGenerateResponse,
)
async def generate_platform_copy_for_clip(
    clip_id: str,
    body: PlatformCopyGenerateRequest,
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip transcript text is unavailable",
        )
    if not provider_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DeepSeek platform copy is unavailable",
        )

    try:
        generated = generate_platform_copy(
            transcript_text,
            [platform.value for platform in body.platforms],
            video_title=video.title,
            topic_hint=body.topic_hint,
        )
    except AICopyUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except AICopyError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    return PlatformCopyGenerateResponse(
        provider_used="deepseek",
        results={
            platform: PlatformCopyFields.model_validate(value)
            for platform, value in generated.results.items()
        },
        errors=generated.errors,
    )


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
