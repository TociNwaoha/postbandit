import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.clip import Clip
from app.models.clip_overlay_asset import ClipOverlayAsset
from app.models.export import Export
from app.models.job import Job, JobStatus
from app.models.publish_job import PublishJob, PublishStatus
from app.models.transcript import TranscriptSegment
from app.models.user import User
from app.models.video import (
    ClipProfile,
    Video,
    VideoImportMode,
    VideoImportState,
    VideoSourceType,
    VideoStatus,
)
from app.models.youtube_playlist_import import YoutubePlaylistImport
from app.schemas.video import (
    VideoConfirmUploadRequest,
    VideoConfirmUploadResponse,
    VideoGenerateClipsRequest,
    VideoGenerateClipsResponse,
    VideoImportYoutubeRequest,
    VideoImportYoutubeResponse,
    VideoListItem,
    VideoResponse,
    VideoStatusResponse,
    VideoTranscriptResponse,
    VideoUploadUrlRequest,
    VideoUploadUrlResponse,
)
from app.schemas.youtube_import import (
    LocalHelperCompleteRequest,
    LocalHelperCompleteResponse,
    LocalHelperSessionRequest,
    LocalHelperSessionResponse,
    PlaylistImportItemResponse,
    PlaylistImportResponse,
    VideoManualUploadConfirmResponse,
    VideoManualUploadUrlResponse,
)
from app.services.object_storage import object_storage_client
from app.services.editor_preview import (
    mark_editor_preview_failed,
    mark_editor_preview_pending,
    parse_editor_preview_metadata,
    resolve_editor_preview_download_key,
    should_enqueue_editor_preview,
)
from app.services.youtube.local_helper_state import (
    LocalHelperSessionError,
    consume_local_helper_rate_limit,
    consume_local_helper_session,
    create_local_helper_session as create_local_helper_token_session,
)
from app.services.youtube.blocked_source_cache import get_blocked_source_hint
from app.services.youtube import (
    embed_url_for_video_id,
    derive_youtube_ui_state,
    initialize_import_state,
    is_retryable_import_state,
    is_non_retryable_blocked_error_code,
    is_youtube_source,
    normalize_import_url,
    normalize_youtube_input,
    transition_import_state,
    YT_BOT_VERIFICATION,
    YT_NO_FORMATS,
    YT_PO_TOKEN_REQUIRED,
    YT_SIGNIN_REQUIRED,
)
from app.services.youtube.admission import evaluate_youtube_admission

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
}
MAX_UPLOAD_BYTES = 5_368_709_120
CLIP_PROFILE_KEY = "clip_profile"
UPLOAD_CONFIRMED_KEY = "upload_confirmed"
UPLOAD_STARTED_AT_KEY = "upload_started_at"
UPLOAD_CONFIRMED_AT_KEY = "upload_confirmed_at"
LONG_FORM_CLIP_PROFILE_ALIASES = {"long_form_speaking"}


def _file_ext_from_upload(filename: str, content_type: str) -> str:
    existing_ext = Path(filename).suffix.lower()
    if existing_ext:
        return existing_ext

    mime_to_ext = {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-msvideo": ".avi",
        "video/x-matroska": ".mkv",
    }
    return mime_to_ext.get(content_type, ".mp4")


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    return stem or "Untitled"


def _resolve_clip_profile(value: ClipProfile | str | None) -> ClipProfile:
    if isinstance(value, ClipProfile):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized == ClipProfile.sermon.value or normalized in LONG_FORM_CLIP_PROFILE_ALIASES:
            return ClipProfile.sermon
    return ClipProfile.viral


def _clip_profile_for_video(video: Video) -> ClipProfile:
    metadata = video.external_metadata_json or {}
    if isinstance(metadata, dict):
        return _resolve_clip_profile(metadata.get(CLIP_PROFILE_KEY))
    return ClipProfile.viral


def _with_upload_confirmation_metadata(
    existing_metadata: dict | None,
    *,
    confirmed: bool,
) -> dict:
    metadata = dict(existing_metadata or {})
    timestamp = datetime.now(timezone.utc).isoformat()
    metadata[UPLOAD_CONFIRMED_KEY] = bool(confirmed)
    if confirmed:
        metadata[UPLOAD_CONFIRMED_AT_KEY] = timestamp
    else:
        metadata[UPLOAD_STARTED_AT_KEY] = timestamp
        metadata.pop(UPLOAD_CONFIRMED_AT_KEY, None)
    return metadata


def _assert_upload_constraints(body: VideoUploadUrlRequest) -> None:
    if body.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported content type",
        )
    if body.file_size <= 0 or body.file_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size must be between 1 byte and {MAX_UPLOAD_BYTES} bytes",
        )


async def _enqueue_editor_preview_proxy_job(db: AsyncSession, video: Video) -> bool:
    if not video.storage_key:
        return False

    if not should_enqueue_editor_preview(
        storage_key=video.storage_key,
        metadata=video.external_metadata_json,
    ):
        return False

    video.external_metadata_json = mark_editor_preview_pending(
        video.external_metadata_json,
        source_key=video.storage_key,
    )
    await db.commit()

    try:
        from app.worker.tasks.editor_preview import generate_editor_preview_proxy_task

        generate_editor_preview_proxy_task.apply_async(
            args=[str(video.id)],
            countdown=1,
            queue="ingest",
        )
        logger.info("[editor_preview_proxy_enqueued] video_id=%s source_key=%s", video.id, video.storage_key)
        return True
    except Exception as exc:
        video.external_metadata_json = mark_editor_preview_failed(
            video.external_metadata_json,
            source_key=video.storage_key,
            error=f"Failed to enqueue preview proxy: {exc}",
        )
        await db.commit()
        logger.warning("[editor_preview_proxy_failed] video_id=%s error=%s", video.id, exc)
        return False


async def _enqueue_ingest_job(db: AsyncSession, video: Video, normalized_url: str) -> None:
    job = Job(video_id=video.id, type="ingest", status=JobStatus.queued, payload={"url": normalized_url})
    db.add(job)
    await db.flush()
    await db.commit()
    await db.refresh(job)

    try:
        from app.worker.tasks.ingest import ingest_job

        task = ingest_job.apply_async(
            args=[str(video.id)],
            countdown=1,
            queue="ingest",
        )
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        logger.warning("[videos] Unable to enqueue ingest task for video %s: %s", video.id, exc)


async def _enqueue_transcribe_job(db: AsyncSession, video: Video) -> None:
    job = Job(video_id=video.id, type="transcribe", status=JobStatus.queued, payload={})
    db.add(job)
    await db.flush()
    await db.commit()
    await db.refresh(job)

    try:
        from app.worker.tasks.transcribe import transcribe_job

        task = transcribe_job.apply_async(
            args=[str(video.id)],
            countdown=1,
            queue="transcribe",
        )
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        logger.warning("[videos] Unable to enqueue transcribe task for video %s: %s", video.id, exc)


async def _enqueue_score_job(db: AsyncSession, video: Video, clip_profile: ClipProfile) -> None:
    job = Job(
        video_id=video.id,
        type="score",
        status=JobStatus.queued,
        payload={"reason": "manual_clip_regeneration", "clip_profile": clip_profile.value},
    )
    db.add(job)
    await db.flush()
    await db.commit()
    await db.refresh(job)

    try:
        from app.worker.tasks.score import score_job

        task = score_job.apply_async(
            args=[str(video.id)],
            countdown=1,
            queue="score",
        )
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        logger.warning("[videos] Unable to enqueue score task for video %s: %s", video.id, exc)


def _is_youtube_source_type(source_type: VideoSourceType) -> bool:
    return is_youtube_source(source_type)


def _import_state_for_response(video: Video) -> VideoImportState:
    if _is_youtube_source_type(video.source_type):
        return video.import_state or VideoImportState.queued
    return VideoImportState.not_applicable


def _import_state_ui_for_response(video: Video) -> str | None:
    if _is_youtube_source_type(video.source_type):
        return derive_youtube_ui_state(video)
    return None


def _is_youtube_single_source(video: Video) -> bool:
    if video.source_type == VideoSourceType.youtube_single:
        return True
    return video.source_type == VideoSourceType.youtube and not video.source_playlist_id


def _blocked_recovery_user_message(error_code: str | None) -> str:
    if error_code == YT_SIGNIN_REQUIRED:
        return "This video requires sign-in to download from server. Upload replacement file or keep as embed."
    if error_code == YT_BOT_VERIFICATION:
        return "YouTube blocked server download for this item. Upload replacement file or keep as embed."
    if error_code == YT_PO_TOKEN_REQUIRED:
        return "This video currently requires extra YouTube verification on server imports. Upload replacement file or keep as embed."
    if error_code == YT_NO_FORMATS:
        return "No downloadable format was available from server runtime. Upload replacement file or keep as embed."
    return "Server download is currently blocked for this video. Upload replacement file or keep as embed."


async def _finalize_manual_upload_transition(
    *,
    db: AsyncSession,
    video: Video,
    storage_key: str,
    file_size_bytes: int | None = None,
    reason_code: str = "manual_upload_confirmed",
    actor: str = "api",
) -> None:
    if not storage_key or not object_storage_client.file_exists(storage_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file not found in storage")

    video.storage_key = storage_key
    if file_size_bytes and file_size_bytes > 0:
        video.file_size_bytes = file_size_bytes
    video.status = VideoStatus.transcribing
    video.import_mode = VideoImportMode.manual_upload
    video.is_download_blocked = False
    video.error_message = None
    video.error_code = None
    video.debug_error_message = None
    if _is_youtube_source_type(video.source_type):
        transition_import_state(
            db,
            video,
            to_state=VideoImportState.processing,
            reason_code=reason_code,
            actor=actor,
            metadata={"storage_key": storage_key},
            allow_noop=True,
            strict=False,
        )
    await db.commit()
    await db.refresh(video)
    await _enqueue_transcribe_job(db, video)
    await _enqueue_editor_preview_proxy_job(db, video)


def _video_to_list_item(video: Video, thumbnail_url: str | None) -> VideoListItem:
    import_state = _import_state_for_response(video)
    clip_profile = _clip_profile_for_video(video)
    return VideoListItem(
        id=video.id,
        title=video.title,
        status=video.status,
        duration_sec=video.duration_sec,
        clip_count=video.clip_count,
        created_at=video.created_at,
        thumbnail_url=thumbnail_url,
        clip_profile=clip_profile,
        source_type=video.source_type,
        source_url=video.source_url,
        source_video_id=video.source_video_id,
        source_playlist_id=video.source_playlist_id,
        source_playlist_title=video.source_playlist_title,
        playlist_index=video.playlist_index,
        import_parent_id=video.import_parent_id,
        embed_url=video.embed_url,
        import_state=import_state,
        import_state_ui=_import_state_ui_for_response(video),
        import_mode=video.import_mode,
        is_download_blocked=video.is_download_blocked,
        error_code=video.error_code,
        error_message=video.error_message,
    )


def _video_to_response(
    video: Video,
    source_download_url: str | None,
    *,
    editor_preview_download_url: str | None = None,
    editor_preview_status: str | None = None,
) -> VideoResponse:
    import_state = _import_state_for_response(video)
    clip_profile = _clip_profile_for_video(video)
    return VideoResponse(
        id=video.id,
        user_id=video.user_id,
        title=video.title,
        source_type=video.source_type,
        source_url=video.source_url,
        source_video_id=video.source_video_id,
        source_playlist_id=video.source_playlist_id,
        source_playlist_title=video.source_playlist_title,
        playlist_index=video.playlist_index,
        import_parent_id=video.import_parent_id,
        embed_url=video.embed_url,
        thumbnail_url=video.thumbnail_url,
        clip_profile=clip_profile,
        import_state=import_state,
        import_state_ui=_import_state_ui_for_response(video),
        import_mode=video.import_mode,
        is_download_blocked=video.is_download_blocked,
        error_code=video.error_code,
        error_message=video.error_message,
        debug_error_message=video.debug_error_message,
        external_metadata_json=video.external_metadata_json or {},
        storage_key=video.storage_key,
        source_download_url=source_download_url,
        editor_preview_download_url=editor_preview_download_url,
        editor_preview_status=editor_preview_status,
        duration_sec=video.duration_sec,
        resolution=video.resolution,
        file_size_bytes=video.file_size_bytes,
        status=video.status,
        clip_count=video.clip_count,
        created_at=video.created_at,
        updated_at=video.updated_at,
    )


@router.post("/videos/upload-url", response_model=VideoUploadUrlResponse)
async def create_upload_url(
    body: VideoUploadUrlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _assert_upload_constraints(body)
    clip_profile = _resolve_clip_profile(body.clip_profile)

    video = Video(
        user_id=current_user.id,
        status=VideoStatus.queued,
        source_type=VideoSourceType.upload,
        import_state=VideoImportState.not_applicable,
        title=_title_from_filename(body.filename),
        file_size_bytes=body.file_size,
        import_mode=VideoImportMode.manual_upload,
        external_metadata_json=_with_upload_confirmation_metadata(
            {CLIP_PROFILE_KEY: clip_profile.value},
            confirmed=False,
        ),
    )
    db.add(video)
    await db.flush()

    ext = _file_ext_from_upload(body.filename, body.content_type)
    storage_key = f"uploads/{video.id}/original{ext}"
    video.storage_key = storage_key

    signed = object_storage_client.get_presigned_upload_url(storage_key, expiry=900)
    return VideoUploadUrlResponse(
        video_id=video.id,
        upload_url=signed["url"],
        upload_fields=signed.get("fields", {}),
        storage_key=storage_key,
        use_local=signed.get("use_local", False),
    )


@router.post("/videos/confirm-upload", response_model=VideoConfirmUploadResponse)
async def confirm_upload(
    body: VideoConfirmUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video).where(Video.id == body.video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.status != VideoStatus.queued:
        logger.warning(
            "[upload_confirm_failed] video_id=%s reason=invalid_state status=%s",
            video.id,
            video.status.value,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Video is not in queued state")
    if not video.storage_key or not object_storage_client.file_exists(video.storage_key):
        logger.warning(
            "[upload_confirm_failed] video_id=%s reason=uploaded_file_missing storage_key=%s",
            video.id,
            video.storage_key,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file not found in storage")

    video.status = VideoStatus.transcribing
    video.external_metadata_json = _with_upload_confirmation_metadata(
        video.external_metadata_json,
        confirmed=True,
    )
    await db.flush()
    await db.commit()
    await db.refresh(video)

    await _enqueue_transcribe_job(db, video)
    return VideoConfirmUploadResponse(video_id=video.id, status=video.status)


@router.post("/videos/import-youtube", response_model=VideoImportYoutubeResponse)
async def import_youtube(
    body: VideoImportYoutubeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_url = body.url.strip()
    clip_profile = _resolve_clip_profile(body.clip_profile)
    try:
        normalized = normalize_import_url(raw_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if normalized.source_type == "youtube_playlist":
        admission = await evaluate_youtube_admission(db, user_id=current_user.id)
        if admission.reasons:
            logger.warning(
                "[youtube_admission] user_id=%s mode=%s allow=%s reasons=%s snapshot=%s",
                current_user.id,
                admission.mode,
                admission.allow,
                ",".join(admission.reasons),
                admission.snapshot,
            )
        if not admission.allow:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "YouTube import capacity is currently limited. "
                    "Please retry shortly or upload a file directly."
                ),
            )
        parent = YoutubePlaylistImport(
            user_id=current_user.id,
            source_url=normalized.normalized_url,
            playlist_id=normalized.normalized_playlist_id or "unknown",
            title=None,
            status="queued",
            total_items=0,
            completed_items=0,
            failed_items=0,
        )
        db.add(parent)
        await db.flush()
        await db.commit()
        await db.refresh(parent)

        try:
            from app.worker.tasks.ingest_playlist import ingest_playlist_job

            ingest_playlist_job.apply_async(
                args=[str(parent.id), clip_profile.value],
                countdown=1,
                queue="ingest",
            )
        except Exception as exc:
            logger.warning("[videos] Unable to enqueue playlist ingest %s: %s", parent.id, exc)

        return VideoImportYoutubeResponse(
            video_id=None,
            playlist_import_id=parent.id,
            import_kind="playlist",
            status="queued",
            message="Playlist import started",
        )

    is_youtube_single_import = normalized.source_type in {"youtube", "youtube_single"}
    try:
        import_source_type = VideoSourceType.youtube_single if is_youtube_single_import else VideoSourceType(normalized.source_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported import platform",
        ) from exc

    blocked_hint = (
        await get_blocked_source_hint(normalized.normalized_video_id)
        if is_youtube_single_import
        else None
    )
    if blocked_hint and is_non_retryable_blocked_error_code(blocked_hint.error_code):
        logger.info(
            "[youtube_blocked_cache_hit] user_id=%s source_video_id=%s error_code=%s",
            current_user.id,
            blocked_hint.source_video_id,
            blocked_hint.error_code,
        )
        video = Video(
            user_id=current_user.id,
            source_type=VideoSourceType.youtube_single,
            source_url=normalized.normalized_url,
            source_video_id=normalized.normalized_video_id,
            source_playlist_id=normalized.normalized_playlist_id,
            status=VideoStatus.error,
            title="Importing...",
            embed_url=embed_url_for_video_id(normalized.normalized_video_id or blocked_hint.source_video_id),
            import_mode=VideoImportMode.embed_only,
            is_download_blocked=True,
            error_code=blocked_hint.error_code,
            error_message=_blocked_recovery_user_message(blocked_hint.error_code),
            external_metadata_json={CLIP_PROFILE_KEY: clip_profile.value},
        )
        db.add(video)
        await db.flush()
        initialize_import_state(
            db,
            video,
            actor="api",
            reason_code="youtube_import_created",
            metadata={"source_url": normalized.normalized_url},
        )
        transition_import_state(
            db,
            video,
            to_state=VideoImportState.blocked,
            reason_code="blocked_cache_short_circuit",
            actor="api",
            metadata={"error_code": blocked_hint.error_code},
            allow_noop=True,
            strict=False,
        )
        transition_import_state(
            db,
            video,
            to_state=VideoImportState.replacement_upload_required,
            reason_code="blocked_cache_short_circuit",
            actor="api",
            metadata={"error_code": blocked_hint.error_code},
            allow_noop=True,
            strict=False,
        )
        await db.commit()
        await db.refresh(video)
        return VideoImportYoutubeResponse(
            video_id=video.id,
            playlist_import_id=None,
            import_kind="single",
            status=video.status,
            message="Server download is currently blocked for this link. Use Upload replacement file on the new row to continue.",
            recovery_required=True,
            recovery_reason=blocked_hint.error_code,
            recovery_action="upload_replacement_or_embed",
        )

    admission = await evaluate_youtube_admission(db, user_id=current_user.id)
    if admission.reasons:
        logger.warning(
            "[youtube_admission] user_id=%s mode=%s allow=%s reasons=%s snapshot=%s",
            current_user.id,
            admission.mode,
            admission.allow,
            ",".join(admission.reasons),
            admission.snapshot,
        )
    if not admission.allow:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "URL import capacity is currently limited. "
                "Please retry shortly or upload a file directly."
            ),
        )

    video = Video(
        user_id=current_user.id,
        source_type=import_source_type,
        source_url=normalized.normalized_url,
        source_video_id=normalized.normalized_video_id,
        source_playlist_id=normalized.normalized_playlist_id,
        status=VideoStatus.downloading,
        title="Importing...",
        import_mode=VideoImportMode.server_download,
        is_download_blocked=False,
        external_metadata_json={CLIP_PROFILE_KEY: clip_profile.value},
    )
    db.add(video)
    await db.flush()
    initialize_import_state(
        db,
        video,
        actor="api",
        reason_code="url_import_created",
        metadata={"source_url": normalized.normalized_url, "source_type": normalized.source_type},
    )
    await db.commit()
    await db.refresh(video)

    await _enqueue_ingest_job(db, video, normalized.normalized_url)
    return VideoImportYoutubeResponse(
        video_id=video.id,
        playlist_import_id=None,
        import_kind="single",
        status=video.status,
        message="Import started",
    )


@router.get("/videos/import-capacity")
async def get_import_capacity(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    decision = await evaluate_youtube_admission(db, user_id=current_user.id)
    return {
        "mode": decision.mode,
        "allow": decision.allow,
        "reasons": decision.reasons,
        "snapshot": {
            "free_disk_bytes": decision.snapshot.free_disk_bytes,
            "free_disk_gb": decision.snapshot.free_disk_gb,
            "active_user_imports": decision.snapshot.active_user_imports,
            "active_global_imports": decision.snapshot.active_global_imports,
            "ingest_queue_depth": decision.snapshot.ingest_queue_depth,
            "user_window_count": decision.snapshot.user_window_count,
        },
    }


@router.get("/videos/playlist-imports", response_model=list[PlaylistImportResponse])
async def list_playlist_imports(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(YoutubePlaylistImport)
        .where(YoutubePlaylistImport.user_id == current_user.id)
        .order_by(YoutubePlaylistImport.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    parents = result.scalars().all()
    if not parents:
        return []

    parent_ids = [row.id for row in parents]
    child_rows = await db.execute(
        select(Video)
        .where(Video.import_parent_id.in_(parent_ids))
        .order_by(Video.import_parent_id.asc(), Video.playlist_index.asc().nullslast(), Video.created_at.asc())
    )

    by_parent: dict[uuid.UUID, list[PlaylistImportItemResponse]] = {}
    for item in child_rows.scalars().all():
        by_parent.setdefault(item.import_parent_id, []).append(
            PlaylistImportItemResponse(
                id=item.id,
                title=item.title,
                status=item.status,
                import_state=_import_state_for_response(item),
                import_state_ui=_import_state_ui_for_response(item),
                playlist_index=item.playlist_index,
                source_video_id=item.source_video_id,
                embed_url=item.embed_url,
                thumbnail_url=item.thumbnail_url,
                import_mode=item.import_mode,
                is_download_blocked=item.is_download_blocked,
                error_code=item.error_code,
                error_message=item.error_message,
            )
        )

    return [
        PlaylistImportResponse(
            id=row.id,
            source_url=row.source_url,
            playlist_id=row.playlist_id,
            title=row.title,
            status=row.status,
            total_items=row.total_items,
            completed_items=row.completed_items,
            failed_items=row.failed_items,
            created_at=row.created_at,
            updated_at=row.updated_at,
            items=by_parent.get(row.id, []),
        )
        for row in parents
    ]


@router.get("/videos", response_model=list[VideoListItem])
async def list_videos(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video)
        .where(Video.user_id == current_user.id)
        .order_by(Video.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    videos = result.scalars().all()
    if not videos:
        return []

    video_ids = [video.id for video in videos]
    thumbnail_keys_by_video_id: dict[uuid.UUID, str] = {}
    thumbnail_urls_by_video_id: dict[uuid.UUID, str] = {}

    thumbnail_result = await db.execute(
        select(Clip.video_id, Clip.thumbnail_key)
        .where(
            Clip.video_id.in_(video_ids),
            Clip.thumbnail_key.is_not(None),
        )
        .order_by(
            Clip.video_id.asc(),
            Clip.score.desc().nullslast(),
            Clip.created_at.asc(),
        )
    )

    for video_id, thumbnail_key in thumbnail_result.all():
        if video_id in thumbnail_keys_by_video_id or not thumbnail_key:
            continue
        thumbnail_keys_by_video_id[video_id] = thumbnail_key

    for video_id, thumbnail_key in thumbnail_keys_by_video_id.items():
        try:
            thumbnail_urls_by_video_id[video_id] = object_storage_client.get_presigned_download_url(thumbnail_key)
        except Exception as exc:
            logger.warning(
                "[videos] failed to generate dashboard thumbnail URL for video_id=%s key=%s: %s",
                video_id,
                thumbnail_key,
                exc,
            )

    rows: list[VideoListItem] = []
    for video in videos:
        preview_thumb = thumbnail_urls_by_video_id.get(video.id) or video.thumbnail_url
        rows.append(_video_to_list_item(video, preview_thumb))
    return rows


@router.post("/videos/{video_id}/generate-clips", response_model=VideoGenerateClipsResponse)
async def generate_clips(
    video_id: uuid.UUID,
    body: VideoGenerateClipsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Video).where(Video.id == video_id, Video.user_id == current_user.id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    clip_profile = _resolve_clip_profile(body.clip_profile)

    if video.status in {VideoStatus.queued, VideoStatus.downloading, VideoStatus.transcribing}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clip regeneration is unavailable until ingest/transcription completes",
        )
    if not video.storage_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source media is unavailable for this video",
        )

    transcript_exists_result = await db.execute(
        select(TranscriptSegment.id).where(TranscriptSegment.video_id == video.id).limit(1)
    )
    if transcript_exists_result.first() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript is not available yet for this video",
        )

    active_score_job_result = await db.execute(
        select(Job.id).where(
            Job.video_id == video.id,
            Job.type == "score",
            Job.status.in_([JobStatus.queued, JobStatus.running]),
        )
    )
    active_score_job = active_score_job_result.first()
    if active_score_job:
        return VideoGenerateClipsResponse(
            video_id=video.id,
            status="already_scoring",
            clip_profile=_clip_profile_for_video(video),
            message="A clip generation job is already in progress for this video.",
        )

    metadata = dict(video.external_metadata_json or {})
    metadata[CLIP_PROFILE_KEY] = clip_profile.value
    video.external_metadata_json = metadata
    video.status = VideoStatus.scoring
    video.error_message = None
    video.error_code = None
    video.debug_error_message = None
    video.clip_count = 0

    if _is_youtube_source_type(video.source_type):
        transition_import_state(
            db,
            video,
            to_state=VideoImportState.processing,
            reason_code="manual_clip_regeneration_started",
            actor="api",
            metadata={"clip_profile": clip_profile.value},
            allow_noop=True,
            strict=False,
        )
    await db.commit()
    await db.refresh(video)

    await _enqueue_score_job(db, video, clip_profile)

    return VideoGenerateClipsResponse(
        video_id=video.id,
        status="queued",
        clip_profile=clip_profile,
        message="Clip generation started.",
    )


@router.post("/videos/{video_id}/retry-import", response_model=VideoImportYoutubeResponse)
async def retry_import(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Video).where(Video.id == video_id, Video.user_id == current_user.id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.source_type not in {VideoSourceType.youtube, VideoSourceType.youtube_single, VideoSourceType.youtube_playlist}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Retry only supports YouTube imports")
    if not video.source_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source URL missing for retry")
    if is_non_retryable_blocked_error_code(video.error_code):
        logger.info(
            "[youtube_retry_rejected_nonretryable] user_id=%s video_id=%s error_code=%s import_state=%s",
            current_user.id,
            video.id,
            video.error_code,
            video.import_state.value if video.import_state else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Server retry is disabled for this blocked YouTube state. "
                "Upload replacement file or keep as embed."
            ),
        )
    retry_allowed = is_retryable_import_state(video.import_state) or video.status in {
        VideoStatus.error,
        VideoStatus.downloading,
        VideoStatus.queued,
    }
    if not retry_allowed:
        state_label = video.import_state.value if video.import_state else "unknown"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This import is not retryable from state '{state_label}'",
        )

    admission = await evaluate_youtube_admission(db, user_id=current_user.id)
    if not admission.allow:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "YouTube import capacity is currently limited. "
                "Please retry shortly or upload a file directly."
            ),
        )

    previous_error_code = video.error_code
    video.status = VideoStatus.downloading
    video.error_message = None
    video.error_code = None
    video.debug_error_message = None
    video.is_download_blocked = False
    video.import_mode = VideoImportMode.server_download
    transition_import_state(
        db,
        video,
        to_state=VideoImportState.queued,
        reason_code="retry_requested",
        actor="api",
        metadata={"previous_error_code": previous_error_code},
        allow_noop=True,
        strict=False,
    )
    await db.commit()
    await db.refresh(video)

    await _enqueue_ingest_job(db, video, video.source_url)

    return VideoImportYoutubeResponse(
        video_id=video.id,
        playlist_import_id=video.import_parent_id,
        import_kind="single",
        status=video.status,
        message="Retry started",
    )


@router.post("/videos/{video_id}/keep-embed", response_model=VideoStatusResponse)
async def keep_as_embed_only(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Video).where(Video.id == video_id, Video.user_id == current_user.id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.source_type not in {VideoSourceType.youtube, VideoSourceType.youtube_single, VideoSourceType.youtube_playlist}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This action is only for YouTube imports")

    video.import_mode = VideoImportMode.embed_only
    video.is_download_blocked = True
    if not video.error_message:
        video.error_message = "Kept as embed-only reference. Upload manually to process clips."
    transition_import_state(
        db,
        video,
        to_state=VideoImportState.embed_only,
        reason_code="user_keep_embed",
        actor="api",
        allow_noop=True,
        strict=False,
    )
    await db.commit()
    await db.refresh(video)

    return VideoStatusResponse(
        video_id=video.id,
        status=video.status,
        import_state=_import_state_for_response(video),
        import_state_ui=_import_state_ui_for_response(video),
        title=video.title,
        clip_count=video.clip_count,
        error_message=video.error_message,
    )


@router.post("/videos/{video_id}/manual-upload-url", response_model=VideoManualUploadUrlResponse)
async def manual_upload_url(
    video_id: uuid.UUID,
    body: VideoUploadUrlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _assert_upload_constraints(body)

    result = await db.execute(select(Video).where(Video.id == video_id, Video.user_id == current_user.id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.source_type not in {VideoSourceType.youtube, VideoSourceType.youtube_single, VideoSourceType.youtube_playlist}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Manual replacement is only for YouTube imports")

    ext = _file_ext_from_upload(body.filename, body.content_type)
    storage_key = f"uploads/{video.id}/original{ext}"
    video.storage_key = storage_key
    video.file_size_bytes = body.file_size
    if _is_youtube_source_type(video.source_type):
        transition_import_state(
            db,
            video,
            to_state=VideoImportState.replacement_upload_required,
            reason_code="replacement_upload_started",
            actor="api",
            allow_noop=True,
            strict=False,
        )
    await db.commit()

    signed = object_storage_client.get_presigned_upload_url(storage_key, expiry=900)
    return VideoManualUploadUrlResponse(
        video_id=video.id,
        upload_url=signed["url"],
        upload_fields=signed.get("fields", {}),
        storage_key=storage_key,
        use_local=signed.get("use_local", False),
    )


@router.post("/videos/{video_id}/manual-upload-confirm", response_model=VideoManualUploadConfirmResponse)
async def manual_upload_confirm(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Video).where(Video.id == video_id, Video.user_id == current_user.id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.source_type not in {VideoSourceType.youtube, VideoSourceType.youtube_single, VideoSourceType.youtube_playlist}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Manual replacement is only for YouTube imports")
    await _finalize_manual_upload_transition(
        db=db,
        video=video,
        storage_key=video.storage_key or "",
        reason_code="manual_upload_confirmed",
        actor="api",
    )
    return VideoManualUploadConfirmResponse(
        video_id=video.id,
        status=video.status,
        message="Manual upload confirmed and processing started",
    )


@router.post("/videos/local-helper/session", response_model=LocalHelperSessionResponse)
async def create_local_helper_session(
    body: LocalHelperSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Video).where(Video.id == body.video_id, Video.user_id == current_user.id))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if not _is_youtube_single_source(video):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Local helper is only available for blocked single YouTube imports",
        )
    if not video.is_download_blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Local helper is only available after server download is blocked",
        )
    if not video.source_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source URL is missing for this video",
        )
    try:
        allowed, count = await consume_local_helper_rate_limit(
            user_id=str(current_user.id),
            limit_per_hour=int(settings.youtube_helper_session_rate_limit_per_hour),
        )
    except LocalHelperSessionError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many helper sessions requested in the last hour. "
                "Please wait before creating another session."
            ),
        )

    ttl_seconds = max(60, int(settings.youtube_local_helper_ttl_minutes) * 60)
    upload_key = f"uploads/{video.id}/local-helper-{secrets.token_hex(6)}.mp4"
    signed = object_storage_client.get_presigned_upload_url(upload_key, expiry=ttl_seconds)

    try:
        helper_session = await create_local_helper_token_session(
            user_id=str(current_user.id),
            video_id=str(video.id),
            upload_key=upload_key,
            source_url=video.source_url,
            ttl_seconds=ttl_seconds,
        )
    except LocalHelperSessionError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    transition_import_state(
        db,
        video,
        to_state=VideoImportState.helper_required,
        reason_code="helper_session_created",
        actor="api",
        metadata={"helper_requests_in_window": count},
        allow_noop=True,
        strict=False,
    )
    await db.commit()
    await db.refresh(video)

    complete_url = f"{settings.backend_public_url.rstrip('/')}/api/videos/local-helper/complete"
    return LocalHelperSessionResponse(
        video_id=video.id,
        helper_session_token=helper_session.token,
        upload_url=signed["url"],
        upload_fields=signed.get("fields", {}),
        upload_key=upload_key,
        use_local=bool(signed.get("use_local", False)),
        source_url=video.source_url,
        complete_url=complete_url,
        expires_at=helper_session.expires_at,
    )


@router.post("/videos/local-helper/complete", response_model=LocalHelperCompleteResponse)
async def complete_local_helper_import(
    body: LocalHelperCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        session_payload = await consume_local_helper_session(token=body.helper_session_token)
    except LocalHelperSessionError as exc:
        raw = str(exc or "").strip()
        lower = raw.lower()
        if "expired or already used" in lower or "session expired" in lower:
            detail = "Local helper session expired or already used. Create a new helper session and run it again."
        else:
            detail = raw or "Local helper session is invalid. Create a new helper session and retry."
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    if body.upload_key != session_payload.upload_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload key mismatch")

    try:
        video_uuid = uuid.UUID(session_payload.video_id)
        user_uuid = uuid.UUID(session_payload.user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid helper session identity")

    result = await db.execute(select(Video).where(Video.id == video_uuid, Video.user_id == user_uuid))
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if not _is_youtube_single_source(video):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Local helper completion is only supported for single YouTube imports",
        )

    await _finalize_manual_upload_transition(
        db=db,
        video=video,
        storage_key=body.upload_key,
        file_size_bytes=body.size_bytes,
        reason_code="local_helper_completed",
        actor="local_helper",
    )
    return LocalHelperCompleteResponse(
        video_id=video.id,
        status=video.status,
        message="Local helper upload confirmed and processing started",
    )


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    await _enqueue_editor_preview_proxy_job(db, video)

    source_download_url: str | None = None
    if video.storage_key:
        try:
            source_download_url = object_storage_client.get_presigned_download_url(video.storage_key)
        except Exception as exc:
            logger.warning("[videos] failed to generate source download URL for video_id=%s: %s", video.id, exc)

    editor_preview_download_url: str | None = None
    preview_status: str | None = None
    preview_meta = parse_editor_preview_metadata(video.external_metadata_json)
    preview_status = preview_meta.get("status")
    preview_key = resolve_editor_preview_download_key(
        storage_key=video.storage_key,
        metadata=video.external_metadata_json,
    )
    if preview_key:
        try:
            editor_preview_download_url = object_storage_client.get_presigned_download_url(preview_key)
            if preview_status != "ready":
                preview_status = "ready"
        except Exception as exc:
            logger.warning("[videos] failed to generate editor preview URL for video_id=%s: %s", video.id, exc)
    else:
        logger.info(
            "[editor_preview_fallback_to_source] video_id=%s preview_status=%s",
            video.id,
            preview_status or "missing",
        )

    return _video_to_response(
        video,
        source_download_url,
        editor_preview_download_url=editor_preview_download_url,
        editor_preview_status=preview_status,
    )


@router.get("/videos/{video_id}/status", response_model=VideoStatusResponse)
async def get_video_status(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    return VideoStatusResponse(
        video_id=video.id,
        status=video.status,
        import_state=_import_state_for_response(video),
        import_state_ui=_import_state_ui_for_response(video),
        title=video.title,
        clip_count=video.clip_count,
        error_message=video.error_message,
    )


@router.get("/videos/{video_id}/transcript", response_model=VideoTranscriptResponse)
async def get_video_transcript(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    if video.status not in {VideoStatus.scoring, VideoStatus.ready}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not ready yet")

    transcript_key = f"transcripts/{video.id}/transcript.json"
    try:
        transcript_text = object_storage_client.read_text_file(transcript_key)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript file not found")
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript file not found")

    try:
        transcript_data = json.loads(transcript_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Transcript data is invalid")

    segments = transcript_data.get("segments", [])
    full_text = transcript_data.get("full_text")
    if not full_text:
        full_text = " ".join(
            (segment.get("text", "") or "").strip()
            for segment in segments
            if (segment.get("text", "") or "").strip()
        ).strip()

    word_count = transcript_data.get("word_count")
    if word_count is None:
        words = transcript_data.get("words")
        if isinstance(words, list):
            word_count = len([word for word in words if (word or {}).get("word")])
        else:
            word_count = sum(
                len(segment.get("words", []))
                for segment in segments
                if isinstance(segment, dict)
            )

    duration = transcript_data.get("duration")
    if duration is None:
        duration = float(video.duration_sec or 0)

    return VideoTranscriptResponse(
        video_id=video.id,
        word_count=int(word_count or 0),
        duration=float(duration or 0),
        language=transcript_data.get("language"),
        full_text=full_text,
        segments=segments,
    )


@router.delete("/videos/{video_id}")
async def delete_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    storage_keys: set[str] = set()
    if video.storage_key:
        storage_keys.add(video.storage_key)
    storage_keys.add(f"transcripts/{video.id}/transcript.json")

    clip_result = await db.execute(select(Clip).where(Clip.video_id == video.id))
    clips = clip_result.scalars().all()
    clip_ids = [clip.id for clip in clips]
    if clip_ids:
        active_publish_job = await db.scalar(
            select(PublishJob.id)
            .where(
                PublishJob.clip_id.in_(clip_ids),
                PublishJob.status.in_(
                    [PublishStatus.scheduled, PublishStatus.queued, PublishStatus.publishing]
                ),
            )
            .limit(1)
        )
        if active_publish_job:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete a video with an active scheduled or publishing job",
            )
    for clip in clips:
        if clip.thumbnail_key:
            storage_keys.add(clip.thumbnail_key)

    if clip_ids:
        export_result = await db.execute(select(Export).where(Export.clip_id.in_(clip_ids)))
        exports = export_result.scalars().all()
        for export in exports:
            if export.storage_key:
                storage_keys.add(export.storage_key)
            if export.srt_key:
                storage_keys.add(export.srt_key)
        overlay_asset_result = await db.execute(
            select(ClipOverlayAsset).where(ClipOverlayAsset.clip_id.in_(clip_ids))
        )
        for asset in overlay_asset_result.scalars().all():
            storage_keys.add(asset.storage_key)

    for key in storage_keys:
        try:
            object_storage_client.delete_file(key)
        except Exception as exc:
            logger.warning("Best-effort delete failed for %s: %s", key, exc)

    await db.delete(video)
    return {"deleted": True}
