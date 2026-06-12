import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.clip import Clip
from app.models.clip_overlay_asset import ClipOverlayAsset
from app.models.export import CaptionColorVariant, Export, ExportStatus
from app.models.job import Job, JobStatus
from app.models.publish_job import PublishJob, PublishStatus
from app.models.user import User
from app.models.video import Video
from app.schemas.export import ExportCreate, ExportResponse, PublicExportShareResponse
from app.services.r2 import r2_client

router = APIRouter()
logger = logging.getLogger(__name__)

ACTIVE_EXPORT_STATUSES = (ExportStatus.queued, ExportStatus.rendering)


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _resolve_caption_color_variant(
    value: CaptionColorVariant | None,
) -> CaptionColorVariant:
    if value in (CaptionColorVariant.classic, CaptionColorVariant.warm, CaptionColorVariant.cool):
        return value
    return CaptionColorVariant.classic


def _normalize_caption_vertical_position(value: float | None) -> float | None:
    if value is None:
        return None
    return round(min(90.0, max(5.0, float(value))), 2)


def _normalize_caption_scale(value: float | None) -> float:
    if value is None:
        return 1.0
    return round(min(2.0, max(0.25, float(value))), 3)


def _normalize_frame_anchor(value: float | None) -> float:
    if value is None:
        return 0.5
    return round(min(1.0, max(0.0, float(value))), 4)


def _normalize_frame_zoom(value: float | None) -> float:
    if value is None:
        return 1.0
    return round(min(3.0, max(1.0, float(value))), 4)


def _derived_download_url(storage_key: str | None) -> str | None:
    if not storage_key:
        return None
    try:
        if not r2_client.file_exists(storage_key):
            return None
        return r2_client.get_presigned_download_url(storage_key)
    except Exception as exc:
        logger.warning("[exports] failed to derive download URL for key=%s: %s", storage_key, exc)
        return None


def _clip_thumbnail_url(clip: Clip | None) -> str | None:
    if not clip or not clip.thumbnail_key:
        return None
    try:
        return r2_client.get_presigned_download_url(clip.thumbnail_key)
    except Exception as exc:
        logger.warning("[exports] failed to derive thumbnail URL for clip_id=%s: %s", clip.id, exc)
        return None


def _share_description(clip: Clip | None, video: Video | None) -> str:
    transcript = " ".join((clip.transcript_text or "").split()) if clip else ""
    if transcript:
        limit = 280
        if len(transcript) <= limit:
            return transcript
        cut = transcript[:limit]
        last_space = cut.rfind(" ")
        if last_space > 140:
            cut = cut[:last_space]
        return f"{cut.strip()}..."
    if clip and clip.title:
        return clip.title.strip()
    if video and video.title:
        return video.title.strip()
    return "Shared from PostBandit."


def _to_response(
    export: Export,
    clip: Clip | None = None,
    video: Video | None = None,
    reused: bool = False,
) -> ExportResponse:
    download_url = None
    srt_download_url = None
    if export.status == ExportStatus.ready:
        download_url = _derived_download_url(export.storage_key)
        srt_download_url = _derived_download_url(export.srt_key)

    return ExportResponse(
        id=export.id,
        clip_id=export.clip_id,
        retry_of_export_id=export.retry_of_export_id,
        user_id=export.user_id,
        aspect_ratio=export.aspect_ratio,
        caption_style=export.caption_style,
        caption_color_variant=_resolve_caption_color_variant(export.caption_color_variant),
        caption_format=export.caption_format,
        caption_cadence=export.caption_cadence,
        caption_vertical_position=export.caption_vertical_position,
        caption_scale=export.caption_scale,
        frame_anchor_x=export.frame_anchor_x,
        frame_anchor_y=export.frame_anchor_y,
        frame_zoom=export.frame_zoom,
        overlay_image_asset_id=export.overlay_image_asset_id,
        overlay_image_config=export.overlay_image_config,
        overlay_text_config=export.overlay_text_config,
        storage_key=export.storage_key,
        srt_key=export.srt_key,
        download_url=download_url,
        srt_download_url=srt_download_url,
        url_expires_at=export.url_expires_at,
        status=export.status,
        error_message=export.error_message,
        render_time_sec=export.render_time_sec,
        reused=reused,
        video_id=video.id if video else None,
        video_title=video.title if video else None,
        clip_title=clip.title if clip else None,
        clip_transcript_text=clip.transcript_text if clip else None,
        clip_thumbnail_url=_clip_thumbnail_url(clip),
        clip_title_options=clip.title_options if clip else None,
        clip_hashtag_options=clip.hashtag_options if clip else None,
        clip_copy_generation_status=clip.copy_generation_status if clip else None,
        clip_copy_generation_error=clip.copy_generation_error if clip else None,
        created_at=export.created_at,
        updated_at=export.updated_at,
    )


async def _enqueue_render_job(
    db: AsyncSession,
    export: Export,
    video_id: uuid.UUID,
    payload: dict,
) -> None:
    render_job = Job(
        video_id=video_id,
        type="render",
        status=JobStatus.queued,
        payload=payload,
    )
    db.add(render_job)
    await db.flush()
    await db.commit()
    await db.refresh(export)
    await db.refresh(render_job)

    try:
        from app.worker.tasks.render import render_export

        task = render_export.apply_async(
            args=[str(export.id), str(render_job.id)],
            countdown=1,
            queue="render",
        )
        render_job.celery_task_id = task.id
        await db.commit()
        logger.info(
            "[exports] export enqueued export_id=%s job_id=%s task_id=%s",
            export.id,
            render_job.id,
            task.id,
        )
    except Exception as exc:
        export.status = ExportStatus.error
        export.error_message = f"Failed to enqueue render job: {exc}"
        render_job.status = JobStatus.failed
        render_job.error = str(exc)[:500]
        await db.commit()
        logger.exception("[exports] enqueue failed export_id=%s job_id=%s", export.id, render_job.id)


@router.get("/exports", response_model=list[ExportResponse])
async def list_exports(
    clip_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logger.info("[exports] list requested user_id=%s clip_id=%s", current_user.id, clip_id)
    query = (
        select(Export, Clip, Video)
        .join(Clip, Export.clip_id == Clip.id)
        .join(Video, Clip.video_id == Video.id)
        .where(Export.user_id == current_user.id)
        .order_by(Export.created_at.desc())
    )
    if clip_id:
        query = query.where(Export.clip_id == clip_id)
    result = await db.execute(query)
    rows = result.all()
    return [_to_response(export, clip, video) for export, clip, video in rows]


@router.get("/exports/{export_id}", response_model=ExportResponse)
async def get_export(
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logger.info("[exports] get requested user_id=%s export_id=%s", current_user.id, export_id)
    result = await db.execute(
        select(Export, Clip, Video)
        .join(Clip, Export.clip_id == Clip.id)
        .join(Video, Clip.video_id == Video.id)
        .where(Export.id == export_id, Export.user_id == current_user.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    export, clip, video = row
    return _to_response(export, clip, video)


@router.delete("/exports/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_export(
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logger.info("[exports] delete requested user_id=%s export_id=%s", current_user.id, export_id)
    result = await db.execute(
        select(Export).where(Export.id == export_id, Export.user_id == current_user.id)
    )
    export = result.scalar_one_or_none()
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")

    if export.status in ACTIVE_EXPORT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete an export while it is queued or rendering",
        )
    active_publish_job = await db.scalar(
        select(PublishJob.id)
        .where(
            PublishJob.export_id == export.id,
            PublishJob.status.in_(
                [PublishStatus.scheduled, PublishStatus.queued, PublishStatus.publishing]
            ),
        )
        .limit(1)
    )
    if active_publish_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete an export with an active scheduled or publishing job",
        )

    storage_keys: set[str] = set()
    if export.storage_key:
        storage_keys.add(export.storage_key)
    if export.srt_key:
        storage_keys.add(export.srt_key)

    storage_delete_failures = 0
    for key in storage_keys:
        try:
            deleted = r2_client.delete_file(key)
            if not deleted:
                storage_delete_failures += 1
                logger.warning("[exports] storage key missing during delete export_id=%s key=%s", export.id, key)
        except Exception as exc:
            storage_delete_failures += 1
            logger.warning("[exports] best-effort storage delete failed export_id=%s key=%s error=%s", export.id, key, exc)

    await db.delete(export)
    await db.commit()
    logger.info(
        "[exports] delete completed user_id=%s export_id=%s export_status=%s storage_keys=%s storage_delete_failures=%s",
        current_user.id,
        export_id,
        export.status,
        len(storage_keys),
        storage_delete_failures,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/public/exports/{export_id}/share", response_model=PublicExportShareResponse)
async def get_public_export_share(
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Export, Clip, Video)
        .join(Clip, Export.clip_id == Clip.id)
        .join(Video, Clip.video_id == Video.id)
        .where(Export.id == export_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share export not found")

    export, clip, video = row
    if export.status != ExportStatus.ready or not export.storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share export not found")

    media_url = _derived_download_url(export.storage_key)
    if not media_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share export not found")

    title = (clip.title or video.title or "PostBandit Share").strip()
    share_url = f"{settings.frontend_public_url.rstrip('/')}/share/exports/{export.id}"

    return PublicExportShareResponse(
        export_id=export.id,
        clip_id=clip.id,
        video_id=video.id,
        title=title,
        description=_share_description(clip, video),
        thumbnail_url=_clip_thumbnail_url(clip),
        media_url=media_url,
        share_url=share_url,
    )


@router.post("/exports", response_model=ExportResponse, status_code=status.HTTP_201_CREATED)
async def create_export(
    body: ExportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logger.info(
        "[exports] create requested user_id=%s clip_id=%s aspect_ratio=%s caption_style=%s caption_color_variant=%s caption_format=%s caption_cadence=%s caption_vertical_position=%s caption_scale=%s frame_anchor_x=%s frame_anchor_y=%s frame_zoom=%s overlay_image_asset_id=%s overlay_text=%s",
        current_user.id,
        body.clip_id,
        body.aspect_ratio,
        body.caption_style,
        body.caption_color_variant,
        body.caption_format,
        body.caption_cadence,
        body.caption_vertical_position,
        body.caption_scale,
        body.frame_anchor_x,
        body.frame_anchor_y,
        body.frame_zoom,
        body.overlay_image_asset_id,
        bool(body.overlay_text_config),
    )
    caption_vertical_position = _normalize_caption_vertical_position(body.caption_vertical_position)
    caption_scale = _normalize_caption_scale(body.caption_scale)
    frame_anchor_x = _normalize_frame_anchor(body.frame_anchor_x)
    frame_anchor_y = _normalize_frame_anchor(body.frame_anchor_y)
    frame_zoom = _normalize_frame_zoom(body.frame_zoom)
    caption_color_variant = _resolve_caption_color_variant(body.caption_color_variant)
    overlay_image_config = (
        body.overlay_image_config.model_dump(mode="json") if body.overlay_image_config else None
    )
    overlay_text_config = (
        body.overlay_text_config.model_dump(mode="json") if body.overlay_text_config else None
    )

    clip_video_result = await db.execute(
        select(Clip, Video)
        .join(Video, Clip.video_id == Video.id)
        .where(Clip.id == body.clip_id, Video.user_id == current_user.id)
    )
    clip_video_row = clip_video_result.first()
    if not clip_video_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    clip, video = clip_video_row

    if body.overlay_image_asset_id:
        asset_result = await db.execute(
            select(ClipOverlayAsset).where(
                ClipOverlayAsset.id == body.overlay_image_asset_id,
                ClipOverlayAsset.clip_id == clip.id,
                ClipOverlayAsset.user_id == current_user.id,
            )
        )
        overlay_asset = asset_result.scalar_one_or_none()
        if not overlay_asset or not r2_client.file_exists(overlay_asset.storage_key):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Overlay image is unavailable",
            )

    dedupe_query = (
        select(Export)
        .where(
            Export.user_id == current_user.id,
            Export.clip_id == body.clip_id,
            Export.aspect_ratio == body.aspect_ratio,
            Export.caption_style == body.caption_style,
            Export.caption_format == body.caption_format,
            Export.caption_cadence == body.caption_cadence,
            Export.caption_scale == caption_scale,
            Export.frame_anchor_x == frame_anchor_x,
            Export.frame_anchor_y == frame_anchor_y,
            Export.frame_zoom == frame_zoom,
            Export.overlay_image_asset_id == body.overlay_image_asset_id,
            Export.status.in_(ACTIVE_EXPORT_STATUSES),
        )
        .order_by(Export.created_at.desc())
    )
    if caption_color_variant == CaptionColorVariant.classic:
        dedupe_query = dedupe_query.where(
            or_(
                Export.caption_color_variant == CaptionColorVariant.classic,
                Export.caption_color_variant.is_(None),
            )
        )
    else:
        dedupe_query = dedupe_query.where(Export.caption_color_variant == caption_color_variant)
    if caption_vertical_position is None:
        dedupe_query = dedupe_query.where(Export.caption_vertical_position.is_(None))
    else:
        dedupe_query = dedupe_query.where(Export.caption_vertical_position == caption_vertical_position)
    if overlay_image_config is None:
        dedupe_query = dedupe_query.where(Export.overlay_image_config.is_(None))
    else:
        dedupe_query = dedupe_query.where(Export.overlay_image_config == overlay_image_config)
    if overlay_text_config is None:
        dedupe_query = dedupe_query.where(Export.overlay_text_config.is_(None))
    else:
        dedupe_query = dedupe_query.where(Export.overlay_text_config == overlay_text_config)

    dedupe_result = await db.execute(dedupe_query)
    existing = dedupe_result.scalars().first()
    if existing:
        logger.info(
            "[exports] dedupe reused existing export_id=%s clip_id=%s status=%s",
            existing.id,
            existing.clip_id,
            existing.status,
        )
        payload = _to_response(existing, clip, video, reused=True).model_dump(mode="json")
        return JSONResponse(status_code=status.HTTP_200_OK, content=payload)

    export = Export(
        clip_id=body.clip_id,
        retry_of_export_id=None,
        user_id=current_user.id,
        aspect_ratio=body.aspect_ratio,
        caption_style=body.caption_style,
        caption_color_variant=caption_color_variant,
        caption_format=body.caption_format,
        caption_cadence=body.caption_cadence,
        caption_vertical_position=caption_vertical_position,
        caption_scale=caption_scale,
        frame_anchor_x=frame_anchor_x,
        frame_anchor_y=frame_anchor_y,
        frame_zoom=frame_zoom,
        overlay_image_asset_id=body.overlay_image_asset_id,
        overlay_image_config=overlay_image_config,
        overlay_text_config=overlay_text_config,
    )
    db.add(export)
    await db.flush()

    await _enqueue_render_job(
        db=db,
        export=export,
        video_id=clip.video_id,
        payload={
            "export_id": str(export.id),
            "clip_id": str(body.clip_id),
            "aspect_ratio": _enum_value(body.aspect_ratio),
            "caption_style": _enum_value(body.caption_style) if body.caption_style else None,
            "caption_color_variant": _enum_value(caption_color_variant),
            "caption_format": _enum_value(body.caption_format),
            "caption_cadence": _enum_value(body.caption_cadence),
            "caption_vertical_position": caption_vertical_position,
            "caption_scale": caption_scale,
            "frame_anchor_x": frame_anchor_x,
            "frame_anchor_y": frame_anchor_y,
            "frame_zoom": frame_zoom,
            "overlay_image_asset_id": str(body.overlay_image_asset_id) if body.overlay_image_asset_id else None,
            "overlay_image_config": overlay_image_config,
            "overlay_text_config": overlay_text_config,
        },
    )

    await db.refresh(export)
    return _to_response(export, clip, video, reused=False)


@router.post("/exports/{export_id}/retry", response_model=ExportResponse, status_code=status.HTTP_201_CREATED)
async def retry_export(
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logger.info("[exports] retry requested user_id=%s export_id=%s", current_user.id, export_id)

    result = await db.execute(
        select(Export, Clip, Video)
        .join(Clip, Export.clip_id == Clip.id)
        .join(Video, Clip.video_id == Video.id)
        .where(Export.id == export_id, Export.user_id == current_user.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    original_export, clip, video = row

    if original_export.status != ExportStatus.error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed exports can be retried",
        )

    retry_export_row = Export(
        clip_id=original_export.clip_id,
        retry_of_export_id=original_export.id,
        user_id=current_user.id,
        aspect_ratio=original_export.aspect_ratio,
        caption_style=original_export.caption_style,
        caption_color_variant=_resolve_caption_color_variant(original_export.caption_color_variant),
        caption_format=original_export.caption_format,
        caption_cadence=original_export.caption_cadence,
        caption_vertical_position=original_export.caption_vertical_position,
        caption_scale=original_export.caption_scale,
        frame_anchor_x=original_export.frame_anchor_x,
        frame_anchor_y=original_export.frame_anchor_y,
        frame_zoom=original_export.frame_zoom,
        overlay_image_asset_id=original_export.overlay_image_asset_id,
        overlay_image_config=original_export.overlay_image_config,
        overlay_text_config=original_export.overlay_text_config,
    )
    db.add(retry_export_row)
    await db.flush()

    await _enqueue_render_job(
        db=db,
        export=retry_export_row,
        video_id=clip.video_id,
        payload={
            "export_id": str(retry_export_row.id),
            "clip_id": str(clip.id),
            "aspect_ratio": _enum_value(retry_export_row.aspect_ratio),
            "caption_style": _enum_value(retry_export_row.caption_style) if retry_export_row.caption_style else None,
            "caption_color_variant": _enum_value(
                _resolve_caption_color_variant(retry_export_row.caption_color_variant)
            ),
            "caption_format": _enum_value(retry_export_row.caption_format),
            "caption_cadence": _enum_value(retry_export_row.caption_cadence),
            "caption_vertical_position": retry_export_row.caption_vertical_position,
            "caption_scale": retry_export_row.caption_scale,
            "frame_anchor_x": retry_export_row.frame_anchor_x,
            "frame_anchor_y": retry_export_row.frame_anchor_y,
            "frame_zoom": retry_export_row.frame_zoom,
            "overlay_image_asset_id": (
                str(retry_export_row.overlay_image_asset_id)
                if retry_export_row.overlay_image_asset_id
                else None
            ),
            "overlay_image_config": retry_export_row.overlay_image_config,
            "overlay_text_config": retry_export_row.overlay_text_config,
            "retry_of_export_id": str(original_export.id),
        },
    )

    await db.refresh(retry_export_row)
    logger.info(
        "[exports] retry created original_export_id=%s new_export_id=%s",
        original_export.id,
        retry_export_row.id,
    )
    return _to_response(retry_export_row, clip, video, reused=False)
