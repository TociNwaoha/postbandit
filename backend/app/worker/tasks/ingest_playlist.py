import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.celery_app import celery_app
from app.config import settings
from app.database import SyncSessionLocal
from app.models.job import Job, JobStatus
from app.models.video import (
    ClipProfile,
    Video,
    VideoImportMode,
    VideoImportState,
    VideoSourceType,
    VideoStatus,
)
from app.models.youtube_playlist_import import YoutubePlaylistImport
from app.services.youtube import (
    enrich_playlist_items_with_youtube_api,
    extract_playlist_entries,
    watch_url_for_video_id,
    transition_import_state,
)
from app.worker.tasks.ingest import ingest_job

logger = logging.getLogger(__name__)

LONG_FORM_CLIP_PROFILE_ALIASES = {"long_form_speaking"}


def _resolve_clip_profile(value: str | None) -> ClipProfile:
    if value:
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized == ClipProfile.sermon.value or normalized in LONG_FORM_CLIP_PROFILE_ALIASES:
            return ClipProfile.sermon
    return ClipProfile.viral


@celery_app.task(
    name="app.worker.tasks.ingest_playlist.ingest_playlist_job",
    bind=True,
    queue="ingest",
    max_retries=1,
)
def ingest_playlist_job(self, playlist_import_id: str, clip_profile: str = ClipProfile.viral.value):
    resolved_clip_profile = _resolve_clip_profile(clip_profile)
    try:
        import_uuid = uuid.UUID(playlist_import_id)
    except ValueError as exc:
        raise ValueError(f"Invalid playlist import id: {playlist_import_id}") from exc

    with SyncSessionLocal() as db:
        parent = db.execute(
            select(YoutubePlaylistImport).where(YoutubePlaylistImport.id == import_uuid)
        ).scalars().first()
        if not parent:
            raise ValueError(f"Playlist import not found: {playlist_import_id}")

        parent.status = "expanding"
        parent.updated_at = datetime.now(timezone.utc)
        db.commit()

    try:
        playlist_id, playlist_title, items = extract_playlist_entries(
            url=parent.source_url,
            timeout_seconds=settings.ytdlp_timeout_seconds,
            max_items=settings.youtube_import_max_playlist_items,
        )

        items = enrich_playlist_items_with_youtube_api(
            items=items,
            api_key=settings.youtube_api_key,
            enabled=settings.enable_youtube_api_metadata,
        )

        created_rows: list[tuple[uuid.UUID, uuid.UUID]] = []
        with SyncSessionLocal() as db:
            parent = db.execute(
                select(YoutubePlaylistImport).where(YoutubePlaylistImport.id == import_uuid)
            ).scalars().first()
            if not parent:
                raise ValueError(f"Playlist import not found: {playlist_import_id}")

            parent.title = playlist_title or parent.title
            parent.playlist_id = playlist_id or parent.playlist_id
            parent.total_items = len(items)
            parent.completed_items = 0
            parent.failed_items = 0
            parent.status = "importing"

            for index, item in enumerate(items):
                video = Video(
                    user_id=parent.user_id,
                    source_type=VideoSourceType.youtube_playlist,
                    source_url=watch_url_for_video_id(item.video_id),
                    source_video_id=item.video_id,
                    source_playlist_id=parent.playlist_id,
                    source_playlist_title=parent.title,
                    playlist_index=index,
                    import_parent_id=parent.id,
                    embed_url=item.embed_url,
                    thumbnail_url=item.thumbnail_url,
                    import_mode=VideoImportMode.server_download,
                    import_state=VideoImportState.queued,
                    is_download_blocked=False,
                    external_metadata_json={
                        "clip_profile": resolved_clip_profile.value,
                        "youtube": {
                            "video_id": item.video_id,
                            "title": item.title,
                            "channel": item.channel,
                            "duration_sec": item.duration_sec,
                            "watch_url": item.watch_url,
                            "embed_url": item.embed_url,
                            "thumbnail_url": item.thumbnail_url,
                        }
                    },
                    status=VideoStatus.downloading,
                    title=item.title or "Importing...",
                    duration_sec=item.duration_sec,
                )
                db.add(video)
                db.flush()
                transition_import_state(
                    db,
                    video,
                    to_state=VideoImportState.queued,
                    reason_code="playlist_item_created",
                    actor="worker_playlist_ingest",
                    metadata={"playlist_id": parent.playlist_id, "playlist_index": index},
                    allow_noop=True,
                    strict=False,
                )

                job = Job(
                    video_id=video.id,
                    type="ingest",
                    status=JobStatus.queued,
                    payload={"url": video.source_url},
                )
                db.add(job)
                db.flush()
                created_rows.append((video.id, job.id))

            db.commit()

        concurrency = max(1, settings.youtube_import_concurrency)
        with SyncSessionLocal() as db:
            for index, (video_id, job_id) in enumerate(created_rows):
                task = ingest_job.apply_async(
                    args=[str(video_id)],
                    countdown=index // concurrency,
                    queue="ingest",
                )
                job = db.execute(select(Job).where(Job.id == job_id)).scalars().first()
                if job:
                    job.celery_task_id = task.id
            db.commit()

        logger.info(
            "[playlist_ingest] expanded playlist_import_id=%s playlist_id=%s items=%s",
            playlist_import_id,
            playlist_id,
            len(created_rows),
        )
        return {
            "playlist_import_id": playlist_import_id,
            "playlist_id": playlist_id,
            "count": len(created_rows),
        }
    except Exception as exc:
        logger.exception("[playlist_ingest] failed playlist_import_id=%s: %s", playlist_import_id, exc)
        with SyncSessionLocal() as db:
            parent = db.execute(
                select(YoutubePlaylistImport).where(YoutubePlaylistImport.id == import_uuid)
            ).scalars().first()
            if parent:
                parent.status = "failed"
                parent.failed_items = parent.total_items or parent.failed_items
                parent.updated_at = datetime.now(timezone.utc)
                db.commit()
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30)
        raise
