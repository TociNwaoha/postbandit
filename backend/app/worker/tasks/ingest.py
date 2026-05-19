import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yt_dlp
from sqlalchemy import func, select
from yt_dlp.utils import DownloadError

from app.celery_app import celery_app
from app.config import settings
from app.database import SyncSessionLocal
from app.models.job import Job, JobStatus
from app.models.video import Video, VideoImportMode, VideoImportState, VideoSourceType, VideoStatus
from app.models.youtube_playlist_import import YoutubePlaylistImport
from app.services.r2 import r2_client
from app.services.youtube import (
    classify_yt_dlp_error,
    embed_url_for_video_id,
    extract_single_video_metadata,
    is_non_retryable_blocked_error_code,
    normalize_youtube_input,
    ytdlp_common_options,
    transition_import_state,
)
from app.services.youtube.blocked_source_cache import set_blocked_source_hint_sync
from app.services.workspace import finalize_workspace, heartbeat_workspace, start_workspace
from app.worker.tasks.transcribe import transcribe_job

logger = logging.getLogger(__name__)


def _latest_ingest_job(db, video_uuid: uuid.UUID) -> Job | None:
    return (
        db.execute(
            select(Job)
            .where(Job.video_id == video_uuid, Job.type == "ingest")
            .order_by(Job.created_at.desc())
        )
        .scalars()
        .first()
    )


def _resolution_from_info(info: dict) -> str | None:
    width = info.get("width")
    height = info.get("height")
    if width and height:
        return f"{width}x{height}"
    return None


def _refresh_playlist_progress(parent_id: uuid.UUID | None) -> None:
    if not parent_id:
        return

    with SyncSessionLocal() as db:
        parent = db.execute(
            select(YoutubePlaylistImport).where(YoutubePlaylistImport.id == parent_id)
        ).scalars().first()
        if not parent:
            return

        total = db.execute(
            select(func.count(Video.id)).where(Video.import_parent_id == parent_id)
        ).scalar_one()
        completed = db.execute(
            select(func.count(Video.id)).where(
                Video.import_parent_id == parent_id,
                Video.status.in_([VideoStatus.transcribing, VideoStatus.scoring, VideoStatus.ready, VideoStatus.error]),
            )
        ).scalar_one()
        failed = db.execute(
            select(func.count(Video.id)).where(
                Video.import_parent_id == parent_id,
                Video.status == VideoStatus.error,
            )
        ).scalar_one()

        parent.total_items = int(total or 0)
        parent.completed_items = int(completed or 0)
        parent.failed_items = int(failed or 0)

        if parent.total_items <= 0:
            parent.status = "queued"
        elif parent.completed_items < parent.total_items:
            parent.status = "importing"
        elif parent.failed_items == 0:
            parent.status = "completed"
        elif parent.failed_items == parent.total_items:
            parent.status = "failed"
        else:
            parent.status = "partial"

        db.commit()


def _mark_video_and_job_failed(video_uuid: uuid.UUID, message: str, code: str | None = None, debug: str | None = None):
    parent_id: uuid.UUID | None = None
    with SyncSessionLocal() as db:
        video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
        if video:
            parent_id = video.import_parent_id
            video.status = VideoStatus.error
            video.error_message = message[:500]
            video.error_code = code
            video.debug_error_message = (debug or message)[:2000]
            if video.source_type in {
                VideoSourceType.youtube,
                VideoSourceType.youtube_single,
                VideoSourceType.youtube_playlist,
            }:
                target_state = VideoImportState.failed_retryable if code in {"YT_RATE_LIMITED", "YT_UNKNOWN_FAILURE"} else VideoImportState.failed_terminal
                transition_import_state(
                    db,
                    video,
                    to_state=target_state,
                    reason_code="ingest_unhandled_error",
                    actor="worker_ingest",
                    metadata={"error_code": code, "error": message[:200]},
                    allow_noop=True,
                    strict=False,
                )

        ingest_row = _latest_ingest_job(db, video_uuid)
        if ingest_row:
            ingest_row.status = JobStatus.failed
            ingest_row.error = message[:500]
            ingest_row.completed_at = datetime.now(timezone.utc)

        db.commit()

    _refresh_playlist_progress(parent_id)


@celery_app.task(name="app.worker.tasks.ingest.ingest_job", bind=True, queue="ingest", max_retries=2)
def ingest_job(self, video_id: str):
    tmp_dir = Path(f"/tmp/{video_id}")
    workspace = None

    try:
        video_uuid = uuid.UUID(video_id)
    except ValueError as exc:
        raise ValueError(f"Invalid video ID: {video_id}") from exc

    parent_id: uuid.UUID | None = None

    try:
        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if not video:
                raise ValueError(f"Video not found: {video_id}")
            if video.source_type not in {
                VideoSourceType.youtube,
                VideoSourceType.youtube_single,
                VideoSourceType.youtube_playlist,
            }:
                raise ValueError("Ingest task only supports YouTube source videos")
            if not video.source_url:
                raise ValueError("Video source URL is missing")

            parent_id = video.import_parent_id

            workspace = start_workspace(
                job_type="ingest",
                workspace_key=f"{video_id}-ingest-{self.request.id or uuid.uuid4().hex[:8]}",
                video_id=str(video.id),
                user_id=str(video.user_id),
                expected_paths=["source_download", "normalized_media"],
                refs={"video_id": str(video.id)},
            )

            ingest_row = _latest_ingest_job(db, video_uuid)
            if ingest_row:
                ingest_row.status = JobStatus.running
                ingest_row.started_at = datetime.now(timezone.utc)
                ingest_row.attempts = (ingest_row.attempts or 0) + 1
            transition_import_state(
                db,
                video,
                to_state=VideoImportState.metadata_extracting,
                reason_code="ingest_started",
                actor="worker_ingest",
                allow_noop=True,
                strict=False,
            )
            db.commit()

            source_url = video.source_url

        metadata = extract_single_video_metadata(source_url, timeout_seconds=settings.ytdlp_timeout_seconds)

        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if not video:
                raise ValueError(f"Video not found after metadata extraction: {video_id}")

            video.source_video_id = video.source_video_id or metadata.video_id
            video.title = metadata.title or video.title
            video.duration_sec = metadata.duration_sec or video.duration_sec
            video.embed_url = metadata.embed_url
            video.thumbnail_url = metadata.thumbnail_url or video.thumbnail_url
            video.external_metadata_json = {
                **(video.external_metadata_json or {}),
                "youtube": {
                    "video_id": metadata.video_id,
                    "title": metadata.title,
                    "channel": metadata.channel,
                    "duration_sec": metadata.duration_sec,
                    "watch_url": metadata.watch_url,
                    "embed_url": metadata.embed_url,
                    "thumbnail_url": metadata.thumbnail_url,
                },
            }
            transition_import_state(
                db,
                video,
                to_state=VideoImportState.downloadable,
                reason_code="metadata_extract_ok",
                actor="worker_ingest",
                metadata={"source_video_id": metadata.video_id},
                allow_noop=True,
                strict=False,
            )
            db.commit()

        logger.info(
            "[ingest] decision=downloadable video_id=%s source_video_id=%s",
            video_id,
            metadata.video_id,
        )
        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if video:
                transition_import_state(
                    db,
                    video,
                    to_state=VideoImportState.downloading,
                    reason_code="download_started",
                    actor="worker_ingest",
                    allow_noop=True,
                    strict=False,
                )
                db.commit()
        if workspace:
            heartbeat_workspace(workspace)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        ydl_opts = {
            **ytdlp_common_options(timeout_seconds=settings.ytdlp_timeout_seconds, noplaylist=True),
            "outtmpl": f"/tmp/{video_id}/%(ext)s",
            "format": (
                "bestvideo[height<=1080]+bestaudio/"
                "best[height<=1080]/"
                "bestvideo+bestaudio/"
                "best"
            ),
            "merge_output_format": "mp4",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source_url, download=True)

        download_candidates = sorted(path for path in tmp_dir.iterdir() if path.is_file())
        if not download_candidates:
            raise FileNotFoundError(f"No downloaded file was found in {tmp_dir}")

        preferred = [path for path in download_candidates if path.suffix.lower() == ".mp4"]
        local_video = preferred[0] if preferred else download_candidates[0]

        storage_key = f"uploads/{video_id}/original.mp4"
        r2_client.upload_file(str(local_video), storage_key)

        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if not video:
                raise ValueError(f"Video not found before finishing ingest: {video_id}")

            video.storage_key = storage_key
            video.status = VideoStatus.transcribing
            video.import_mode = VideoImportMode.server_download
            video.is_download_blocked = False
            video.error_code = None
            video.error_message = None
            video.debug_error_message = None
            video.resolution = _resolution_from_info(info) or video.resolution
            transition_import_state(
                db,
                video,
                to_state=VideoImportState.processing,
                reason_code="ingest_download_complete",
                actor="worker_ingest",
                metadata={"storage_key": storage_key},
                allow_noop=True,
                strict=False,
            )

            transcribe_row = Job(
                video_id=video.id,
                type="transcribe",
                payload={},
                status=JobStatus.queued,
            )
            db.add(transcribe_row)

            ingest_row = _latest_ingest_job(db, video_uuid)
            if ingest_row:
                ingest_row.status = JobStatus.done
                ingest_row.error = None
                ingest_row.completed_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(transcribe_row)

            try:
                task = transcribe_job.apply_async(
                    args=[str(video.id)],
                    countdown=1,
                    queue="transcribe",
                )
                transcribe_row.celery_task_id = task.id
                db.commit()
            except Exception as enqueue_exc:
                logger.warning("[ingest] Unable to enqueue transcribe job for %s: %s", video.id, enqueue_exc)
                db.commit()

        _refresh_playlist_progress(parent_id)
        if workspace:
            finalize_workspace(workspace, state="terminal_success", metadata={"result": "processing"})
        logger.info("[ingest] Completed ingest for video %s mode=server_download", video_id)
        return {"video_id": video_id, "status": "transcribing"}

    except DownloadError as exc:
        classification = classify_yt_dlp_error(exc)
        logger.info(
            "[youtube_blocked_code_distribution] video_id=%s code=%s fallback=%s",
            video_id,
            classification.code,
            classification.fallback_action,
        )

        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if video:
                is_blocked = classification.fallback_action in {"embed_only", "upload_manual"}
                if classification.fallback_action == "embed_only":
                    import_mode = VideoImportMode.embed_only
                elif classification.fallback_action == "upload_manual":
                    import_mode = VideoImportMode.manual_upload
                else:
                    import_mode = VideoImportMode.server_download

                video.status = VideoStatus.error
                video.error_message = classification.user_facing_error_message[:500]
                video.error_code = classification.code
                video.debug_error_message = classification.developer_debug_message[:2000]
                video.is_download_blocked = is_blocked
                video.import_mode = import_mode
                if is_blocked:
                    transition_import_state(
                        db,
                        video,
                        to_state=VideoImportState.blocked,
                        reason_code="download_blocked_classified",
                        actor="worker_ingest",
                        metadata={
                            "error_code": classification.code,
                            "fallback_action": classification.fallback_action,
                        },
                        allow_noop=True,
                        strict=False,
                    )
                    transition_import_state(
                        db,
                        video,
                        to_state=VideoImportState.replacement_upload_required,
                        reason_code="download_blocked",
                        actor="worker_ingest",
                        metadata={
                            "error_code": classification.code,
                            "fallback_action": classification.fallback_action,
                        },
                        allow_noop=True,
                        strict=False,
                    )
                else:
                    transition_import_state(
                        db,
                        video,
                        to_state=VideoImportState.failed_retryable,
                        reason_code="download_retryable_failure",
                        actor="worker_ingest",
                        metadata={
                            "error_code": classification.code,
                            "fallback_action": classification.fallback_action,
                        },
                        allow_noop=True,
                        strict=False,
                    )
                if not video.embed_url and video.source_video_id:
                    video.embed_url = embed_url_for_video_id(video.source_video_id)
                if not video.source_video_id and video.source_url:
                    try:
                        normalized = normalize_youtube_input(video.source_url)
                        video.source_video_id = normalized.normalized_video_id
                        if normalized.normalized_video_id:
                            video.embed_url = embed_url_for_video_id(normalized.normalized_video_id)
                    except Exception:
                        pass
                if is_non_retryable_blocked_error_code(classification.code) and video.source_video_id:
                    set_blocked_source_hint_sync(
                        source_video_id=video.source_video_id,
                        error_code=classification.code,
                    )

            ingest_row = _latest_ingest_job(db, video_uuid)
            if ingest_row:
                ingest_row.status = JobStatus.failed
                ingest_row.error = classification.user_facing_error_message[:500]
                ingest_row.completed_at = datetime.now(timezone.utc)

            db.commit()

        _refresh_playlist_progress(parent_id)
        if workspace:
            finalize_workspace(
                workspace,
                state="terminal_failed",
                metadata={"error_code": classification.code, "fallback_action": classification.fallback_action},
            )
        logger.error(
            "[ingest] yt-dlp download failed video_id=%s code=%s fallback=%s",
            video_id,
            classification.code,
            classification.fallback_action,
            exc_info=True,
        )
        return {
            "video_id": video_id,
            "status": "error",
            "error_code": classification.code,
            "error": classification.user_facing_error_message,
        }

    except Exception as exc:
        logger.exception("[ingest] Failed ingest for video %s: %s", video_id, exc)
        _mark_video_and_job_failed(video_uuid, str(exc), code="YT_UNKNOWN_FAILURE", debug=str(exc))
        if workspace:
            finalize_workspace(
                workspace,
                state="terminal_failed",
                metadata={"error_code": "YT_UNKNOWN_FAILURE", "error": str(exc)[:200]},
            )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)
        raise

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# Prompt 1 naming compatibility.
download_video = ingest_job
