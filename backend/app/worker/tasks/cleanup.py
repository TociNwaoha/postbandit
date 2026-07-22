from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

from sqlalchemy import select

from app.celery_app import celery_app
from app.config import settings
from app.database import SyncSessionLocal
from app.models.export import Export, ExportStatus
from app.models.job import Job, JobStatus
from app.models.publish_job import PublishJob, PublishStatus
from app.models.video import Video, VideoSourceType, VideoStatus
from app.models.clip import Clip
from app.models.carousel_export import CarouselExport
from app.models.content_queue_item import ContentQueueItem
from app.models.editor_project import EditorProject, EditorProjectStatus
from app.services.object_storage import object_storage_client
from app.services.storage import video_thumbnail_key
from app.services.workspace import (
    WORKSPACE_ROOTS,
    is_workspace_lease_active,
    read_workspace_manifest,
    release_workspace_lease,
)

logger = logging.getLogger(__name__)
UPLOAD_CONFIRMED_KEY = "upload_confirmed"
UPLOAD_STARTED_AT_KEY = "upload_started_at"
UPLOAD_CONFIRMED_AT_KEY = "upload_confirmed_at"
RAW_SOURCE_EXPIRED_AT_KEY = "raw_source_expired_at"
ACTIVE_PUBLISH_STATUSES = {
    PublishStatus.scheduled,
    PublishStatus.queued,
    PublishStatus.publishing,
}


def _parse_iso(iso_value: str | None) -> datetime | None:
    if not iso_value:
        return None
    try:
        dt = datetime.fromisoformat(iso_value)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _directory_size(path: Path) -> int:
    size = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                size += item.stat().st_size
            except OSError:
                continue
    return size


def _job_terminal_from_manifest(manifest: dict) -> tuple[bool | None, str]:
    refs = manifest.get("refs") or {}
    job_type = str(manifest.get("job_type") or "").strip()

    with SyncSessionLocal() as db:
        if job_type in {"ingest", "transcribe", "score"}:
            video_id = refs.get("video_id") or manifest.get("video_id")
            if not video_id:
                return None, "missing_video_ref"
            job = (
                db.execute(
                    select(Job)
                    .where(Job.video_id == video_id, Job.type == job_type)
                    .order_by(Job.created_at.desc())
                )
                .scalars()
                .first()
            )
            if not job:
                return None, "db_job_missing"
            return job.status in {JobStatus.done, JobStatus.failed}, f"db_job_status={job.status.value}"

        if job_type == "render":
            export_id = refs.get("export_id")
            if not export_id:
                return None, "missing_export_ref"
            export_row = db.execute(select(Export).where(Export.id == export_id)).scalars().first()
            if not export_row:
                return None, "db_export_missing"
            return export_row.status in {ExportStatus.ready, ExportStatus.error}, f"db_export_status={export_row.status.value}"

        if job_type == "publish":
            publish_job_id = refs.get("publish_job_id")
            if not publish_job_id:
                return None, "missing_publish_ref"
            publish_row = db.execute(select(PublishJob).where(PublishJob.id == publish_job_id)).scalars().first()
            if not publish_row:
                return None, "db_publish_missing"
            terminal = publish_row.status in {
                PublishStatus.published,
                PublishStatus.failed,
                PublishStatus.waiting_user_action,
                PublishStatus.provider_not_configured,
            }
            return terminal, f"db_publish_status={publish_row.status.value}"
    return None, "unknown_job_type"


def sweep_workspaces_impl(*, dry_run: bool) -> dict:
    now = datetime.now(timezone.utc)
    retention_seconds = max(3600, int(settings.workspace_cleanup_retention_hours) * 3600)
    orphan_grace_seconds = max(300, int(settings.workspace_cleanup_orphan_grace_minutes) * 60)

    visited = 0
    reclaimed_dirs = 0
    reclaimed_bytes = 0
    skipped = 0
    disagreements = 0
    failures = 0

    unique_roots = {root.resolve() for root in WORKSPACE_ROOTS.values()}
    for root in unique_roots:
        if not root.exists() or not root.is_dir():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            visited += 1
            manifest = read_workspace_manifest(child)
            st = child.stat()
            age_seconds = max(0.0, (now - datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)).total_seconds())

            if "clipbandit-storage" in str(child):
                skipped += 1
                continue

            if manifest is None:
                if age_seconds < orphan_grace_seconds:
                    skipped += 1
                    continue
                bytes_size = _directory_size(child)
                if not dry_run:
                    shutil.rmtree(child, ignore_errors=True)
                reclaimed_dirs += 1
                reclaimed_bytes += bytes_size
                continue

            lease_id = str(manifest.get("lease_id") or "").strip()
            lease_active = bool(lease_id and is_workspace_lease_active(lease_id))
            manifest_state = str(manifest.get("state") or "active").strip()
            manifest_heartbeat = _parse_iso(manifest.get("last_heartbeat_at"))
            if manifest_heartbeat:
                age_seconds = max(0.0, (now - manifest_heartbeat).total_seconds())

            db_terminal, db_reason = _job_terminal_from_manifest(manifest)
            stale_lease_candidate = False

            if lease_active and db_terminal is True:
                disagreements += 1
                if age_seconds < orphan_grace_seconds:
                    skipped += 1
                    logger.warning(
                        "[workspace_cleanup] disagreement=lease_active_db_terminal path=%s reason=%s",
                        child,
                        db_reason,
                    )
                    continue
                stale_lease_candidate = True

            if (not lease_active) and db_terminal is False:
                disagreements += 1
                skipped += 1
                logger.warning(
                    "[workspace_cleanup] disagreement=lease_missing_db_running path=%s reason=%s",
                    child,
                    db_reason,
                )
                continue

            eligible = False
            if manifest_state in {"terminal_success", "terminal_failed"} and age_seconds >= retention_seconds:
                eligible = True
            elif not lease_active and db_terminal is True and age_seconds >= retention_seconds:
                eligible = True
            elif not lease_active and db_terminal is None and age_seconds >= orphan_grace_seconds:
                eligible = True

            if not eligible:
                skipped += 1
                continue

            bytes_size = _directory_size(child)
            try:
                if stale_lease_candidate and lease_id:
                    release_workspace_lease(lease_id)
                if not dry_run:
                    shutil.rmtree(child, ignore_errors=True)
                reclaimed_dirs += 1
                reclaimed_bytes += bytes_size
            except Exception as exc:
                failures += 1
                logger.warning("[workspace_cleanup] failed path=%s error=%s", child, exc)

    payload = {
        "dry_run": dry_run,
        "visited": visited,
        "reclaimed_dirs": reclaimed_dirs,
        "reclaimed_bytes": reclaimed_bytes,
        "skipped": skipped,
        "disagreements": disagreements,
        "failures": failures,
    }
    logger.info("[workspace_cleanup] summary=%s", payload)
    return payload


@celery_app.task(name="app.worker.tasks.cleanup.sweep_workspaces", queue="ingest")
def sweep_workspaces(dry_run: bool = False):
    return sweep_workspaces_impl(dry_run=dry_run)


def _as_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return default


def _upload_confirmed(video: Video) -> bool:
    metadata = video.external_metadata_json
    if not isinstance(metadata, dict):
        return False
    return _as_bool(metadata.get(UPLOAD_CONFIRMED_KEY), default=False)


def _set_upload_confirmed(video: Video, *, confirmed: bool) -> None:
    metadata = dict(video.external_metadata_json or {})
    metadata[UPLOAD_CONFIRMED_KEY] = confirmed
    now_iso = datetime.now(timezone.utc).isoformat()
    if confirmed:
        metadata[UPLOAD_CONFIRMED_AT_KEY] = now_iso
    else:
        metadata[UPLOAD_STARTED_AT_KEY] = now_iso
        metadata.pop(UPLOAD_CONFIRMED_AT_KEY, None)
    video.external_metadata_json = metadata


def _list_stale_queued_upload_video_ids(db, *, cutoff: datetime) -> list[uuid.UUID]:
    rows = (
        db.execute(
            select(Video.id)
            .where(
                Video.source_type == VideoSourceType.upload,
                Video.status == VideoStatus.queued,
                Video.updated_at <= cutoff,
            )
            .order_by(Video.updated_at.asc())
        )
        .scalars()
        .all()
    )
    return list(rows)


def _enqueue_recovery_transcribe_job(db, *, video: Video) -> bool:
    job = Job(
        video_id=video.id,
        type="transcribe",
        payload={"reason": "stale_queued_upload_recovery"},
        status=JobStatus.queued,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        from app.worker.tasks.transcribe import transcribe_job

        task = transcribe_job.apply_async(
            args=[str(video.id)],
            countdown=1,
            queue="transcribe",
        )
        job.celery_task_id = task.id
        db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "[stale_queued_recovery] enqueue_failed video_id=%s job_id=%s error=%s",
            video.id,
            job.id,
            exc,
        )
        job.status = JobStatus.failed
        job.error = f"Failed to enqueue recovered transcribe job: {exc}"[:500]
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return False


def sweep_stale_queued_uploads_impl(*, dry_run: bool) -> dict:
    now = datetime.now(timezone.utc)
    stale_hours = max(1, int(settings.stale_queued_upload_cleanup_retention_hours))
    cutoff = now - timedelta(hours=stale_hours)

    scanned = 0
    eligible = 0
    skipped_active_job = 0
    stale_queued_marked_error = 0
    stale_queued_recovered_enqueued = 0
    enqueue_failures = 0

    with SyncSessionLocal() as db:
        candidate_ids = _list_stale_queued_upload_video_ids(db, cutoff=cutoff)
        scanned = len(candidate_ids)

        for video_id in candidate_ids:
            if _has_active_jobs(db, video_id=video_id):
                skipped_active_job += 1
                continue

            video = _load_video_for_cleanup(db, video_id=video_id)
            if not video:
                continue

            if _upload_confirmed(video):
                continue

            eligible += 1
            storage_exists = bool(video.storage_key and object_storage_client.file_exists(video.storage_key))

            if dry_run:
                continue

            if storage_exists:
                video.status = VideoStatus.transcribing
                video.error_message = None
                _set_upload_confirmed(video, confirmed=True)
                db.commit()

                if _enqueue_recovery_transcribe_job(db, video=video):
                    stale_queued_recovered_enqueued += 1
                    logger.info(
                        "[stale_queued_recovered_enqueued] video_id=%s storage_key=%s",
                        video.id,
                        video.storage_key,
                    )
                else:
                    enqueue_failures += 1
                    video.status = VideoStatus.error
                    video.error_message = "Upload recovered but failed to enqueue transcription. Please retry upload."
                    db.commit()
                continue

            video.status = VideoStatus.error
            video.error_message = "Upload was not completed. Please upload the file again."
            _set_upload_confirmed(video, confirmed=False)
            db.commit()
            stale_queued_marked_error += 1
            logger.info("[stale_queued_marked_error] video_id=%s reason=upload_not_completed", video.id)

    payload = {
        "dry_run": dry_run,
        "stale_hours": stale_hours,
        "cutoff": cutoff.isoformat(),
        "scanned": scanned,
        "eligible": eligible,
        "skipped_active_job": skipped_active_job,
        "stale_queued_marked_error": stale_queued_marked_error,
        "stale_queued_recovered_enqueued": stale_queued_recovered_enqueued,
        "enqueue_failures": enqueue_failures,
    }
    logger.info("[stale_queued_upload_cleanup] summary=%s", payload)
    return payload


@celery_app.task(name="app.worker.tasks.cleanup.sweep_stale_queued_uploads", queue="ingest")
def sweep_stale_queued_uploads(dry_run: bool = False):
    return sweep_stale_queued_uploads_impl(dry_run=dry_run)


def _list_failed_import_video_ids(db, *, cutoff: datetime) -> list[uuid.UUID]:
    rows = (
        db.execute(
            select(Video.id)
            .where(
                Video.status == VideoStatus.error,
                Video.updated_at <= cutoff,
            )
            .order_by(Video.updated_at.asc())
        )
        .scalars()
        .all()
    )
    return list(rows)


def _has_active_jobs(db, *, video_id: uuid.UUID) -> bool:
    active = (
        db.execute(
            select(Job.id)
            .where(
                Job.video_id == video_id,
                Job.status.in_([JobStatus.queued, JobStatus.running]),
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    return active is not None


def _collect_video_storage_keys(db, *, video: Video) -> set[str]:
    storage_keys: set[str] = set()
    if video.storage_key:
        storage_keys.add(video.storage_key)
    storage_keys.add(video_thumbnail_key(str(video.user_id), str(video.id)))
    storage_keys.add(f"transcripts/{video.id}/transcript.json")

    clip_rows = db.execute(select(Clip.id, Clip.thumbnail_key).where(Clip.video_id == video.id)).all()
    clip_ids: list[uuid.UUID] = []
    for clip_id, thumbnail_key in clip_rows:
        clip_ids.append(clip_id)
        if thumbnail_key:
            storage_keys.add(thumbnail_key)

    if clip_ids:
        export_rows = db.execute(select(Export.storage_key, Export.srt_key).where(Export.clip_id.in_(clip_ids))).all()
        for export_storage_key, export_srt_key in export_rows:
            if export_storage_key:
                storage_keys.add(export_storage_key)
            if export_srt_key:
                storage_keys.add(export_srt_key)

    return storage_keys


def _load_video_for_cleanup(db, *, video_id: uuid.UUID) -> Video | None:
    return db.execute(select(Video).where(Video.id == video_id)).scalars().first()


def sweep_failed_imports_impl(*, dry_run: bool) -> dict:
    now = datetime.now(timezone.utc)
    retention_hours = max(1, int(settings.failed_import_cleanup_retention_hours))
    cutoff = now - timedelta(hours=retention_hours)

    scanned = 0
    eligible = 0
    deleted = 0
    skipped_active_job = 0
    storage_delete_failures = 0
    db_delete_failures = 0

    with SyncSessionLocal() as db:
        candidate_ids = _list_failed_import_video_ids(db, cutoff=cutoff)
        scanned = len(candidate_ids)

        for video_id in candidate_ids:
            if _has_active_jobs(db, video_id=video_id):
                skipped_active_job += 1
                continue

            video = _load_video_for_cleanup(db, video_id=video_id)
            if not video:
                continue

            eligible += 1
            if dry_run:
                continue

            try:
                storage_keys = _collect_video_storage_keys(db, video=video)
                for key in storage_keys:
                    try:
                        deleted_ok = object_storage_client.delete_file(key)
                        if not deleted_ok:
                            storage_delete_failures += 1
                    except Exception as exc:
                        storage_delete_failures += 1
                        logger.warning(
                            "[failed_import_cleanup] storage delete failed video_id=%s key=%s error=%s",
                            video.id,
                            key,
                            exc,
                        )

                db.delete(video)
                db.commit()
                deleted += 1
            except Exception as exc:
                db.rollback()
                db_delete_failures += 1
                logger.warning(
                    "[failed_import_cleanup] db delete failed video_id=%s error=%s",
                    video_id,
                    exc,
                )

    payload = {
        "dry_run": dry_run,
        "retention_hours": retention_hours,
        "cutoff": cutoff.isoformat(),
        "scanned": scanned,
        "eligible": eligible,
        "deleted": deleted,
        "skipped_active_job": skipped_active_job,
        "storage_delete_failures": storage_delete_failures,
        "db_delete_failures": db_delete_failures,
    }
    logger.info("[failed_import_cleanup] summary=%s", payload)
    return payload


@celery_app.task(name="app.worker.tasks.cleanup.sweep_failed_imports", queue="ingest")
def sweep_failed_imports(dry_run: bool = False):
    return sweep_failed_imports_impl(dry_run=dry_run)


def _has_pinned_or_active_editor_project(db, *, video_id: uuid.UUID) -> bool:
    row = (
        db.execute(
            select(EditorProject.id)
            .where(
                EditorProject.video_id == video_id,
                (
                    EditorProject.is_pinned.is_(True)
                    | EditorProject.status.in_([EditorProjectStatus.draft, EditorProjectStatus.rendering])
                ),
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    return row is not None


def _has_active_publish_job_for_export(db, *, export_id: uuid.UUID) -> bool:
    row = (
        db.execute(
            select(PublishJob.id)
            .where(
                PublishJob.export_id == export_id,
                PublishJob.status.in_(ACTIVE_PUBLISH_STATUSES),
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    return row is not None


def _collect_export_storage_keys(export: Export) -> set[str]:
    storage_keys: set[str] = set()
    if export.storage_key:
        storage_keys.add(export.storage_key)
    if export.srt_key:
        storage_keys.add(export.srt_key)
    return storage_keys


def _collect_content_queue_storage_keys(item: ContentQueueItem) -> set[str]:
    keys: set[str] = set()
    for key in list(item.slide_keys_json or []):
        if isinstance(key, str) and key.strip():
            keys.add(key.strip())
    if item.zip_key:
        keys.add(item.zip_key)
    if item.preview_key:
        keys.add(item.preview_key)
    return keys


def _carousel_export_references_key(db, *, user_id: uuid.UUID, key: str) -> bool:
    rows = (
        db.execute(
            select(CarouselExport.slide_keys_json, CarouselExport.zip_key, CarouselExport.preview_key)
            .where(CarouselExport.user_id == user_id)
        )
        .all()
    )
    for slide_keys, zip_key, preview_key in rows:
        if key == zip_key or key == preview_key:
            return True
        if key in set(slide_keys or []):
            return True
    return False


def _content_queue_asset_due_at(item: ContentQueueItem, *, now: datetime) -> datetime:
    if item.status == "rejected":
        return item.updated_at + timedelta(days=max(1, int(settings.content_queue_rejected_asset_retention_days)))
    return item.created_at + timedelta(days=max(1, int(settings.content_queue_ready_asset_retention_days)))


def _content_queue_item_asset_cleanup_eligible(item: ContentQueueItem, *, now: datetime) -> bool:
    if item.assets_deleted_at is not None:
        return False
    if item.status in {"approved", "posted"}:
        return False
    if item.scheduled_at is not None:
        return False
    if not _collect_content_queue_storage_keys(item):
        return False

    due_at = item.asset_cleanup_at or _content_queue_asset_due_at(item, now=now)
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    return due_at <= now


def sweep_content_queue_asset_retention_impl(*, dry_run: bool) -> dict:
    if not settings.content_queue_asset_retention_enabled:
        payload = {
            "dry_run": dry_run,
            "enabled": False,
            "scanned": 0,
            "eligible": 0,
            "deleted_items": 0,
            "deleted_keys": 0,
            "protected_keys": 0,
            "storage_delete_failures": 0,
        }
        logger.info("[content_queue_asset_retention] summary=%s", payload)
        return payload

    now = datetime.now(timezone.utc)
    scanned = 0
    eligible = 0
    deleted_items = 0
    deleted_keys = 0
    protected_keys = 0
    storage_delete_failures = 0

    with SyncSessionLocal() as db:
        rows = (
            db.execute(
                select(ContentQueueItem)
                .where(
                    ContentQueueItem.assets_deleted_at.is_(None),
                    ContentQueueItem.status.in_(["draft", "ready", "rejected"]),
                )
                .order_by(ContentQueueItem.updated_at.asc())
            )
            .scalars()
            .all()
        )
        scanned = len(rows)

        for item in rows:
            if not _content_queue_item_asset_cleanup_eligible(item, now=now):
                continue

            keys = _collect_content_queue_storage_keys(item)
            eligible += 1
            if dry_run:
                continue

            item_delete_failed = False
            for key in keys:
                owned_prefix = f"carousels/{item.user_id}/"
                if not key.startswith(owned_prefix):
                    protected_keys += 1
                    logger.warning(
                        "[content_queue_asset_retention] skipped non-owned key item_id=%s key=%s",
                        item.id,
                        key,
                    )
                    continue
                if _carousel_export_references_key(db, user_id=item.user_id, key=key):
                    protected_keys += 1
                    continue

                try:
                    object_storage_client.delete_file(key)
                    deleted_keys += 1
                except Exception as exc:
                    item_delete_failed = True
                    storage_delete_failures += 1
                    logger.warning(
                        "[content_queue_asset_retention] storage delete failed item_id=%s key=%s error=%s",
                        item.id,
                        key,
                        exc,
                    )

            if item_delete_failed:
                continue

            item.slide_urls = []
            item.slide_keys_json = []
            item.zip_key = None
            item.preview_key = None
            item.assets_deleted_at = now
            item.asset_cleanup_at = None
            db.commit()
            deleted_items += 1

    payload = {
        "dry_run": dry_run,
        "enabled": True,
        "ready_retention_days": max(1, int(settings.content_queue_ready_asset_retention_days)),
        "rejected_retention_days": max(1, int(settings.content_queue_rejected_asset_retention_days)),
        "scanned": scanned,
        "eligible": eligible,
        "deleted_items": deleted_items,
        "deleted_keys": deleted_keys,
        "protected_keys": protected_keys,
        "storage_delete_failures": storage_delete_failures,
    }
    logger.info("[content_queue_asset_retention] summary=%s", payload)
    return payload


@celery_app.task(name="app.worker.tasks.cleanup.sweep_content_queue_asset_retention", queue="ingest")
def sweep_content_queue_asset_retention(dry_run: bool = False):
    return sweep_content_queue_asset_retention_impl(dry_run=dry_run)


def sweep_export_retention_impl(*, dry_run: bool) -> dict:
    if not settings.export_retention_enabled:
        payload = {
            "dry_run": dry_run,
            "enabled": False,
            "scanned": 0,
            "eligible": 0,
            "deleted": 0,
            "skipped_active_publish_job": 0,
            "storage_delete_failures": 0,
        }
        logger.info("[export_retention] summary=%s", payload)
        return payload

    now = datetime.now(timezone.utc)
    retention_days = max(1, int(settings.export_retention_days))
    cutoff = now - timedelta(days=retention_days)

    scanned = 0
    eligible = 0
    deleted = 0
    skipped_active_publish_job = 0
    storage_delete_failures = 0

    with SyncSessionLocal() as db:
        rows = (
            db.execute(
                select(Export)
                .where(
                    Export.updated_at <= cutoff,
                    Export.status.in_([ExportStatus.ready, ExportStatus.error]),
                )
                .order_by(Export.updated_at.asc())
            )
            .scalars()
            .all()
        )
        scanned = len(rows)

        for export in rows:
            if _has_active_publish_job_for_export(db, export_id=export.id):
                skipped_active_publish_job += 1
                continue

            eligible += 1
            if dry_run:
                continue

            storage_delete_failed = False
            for key in _collect_export_storage_keys(export):
                try:
                    object_storage_client.delete_file(key)
                except Exception as exc:
                    storage_delete_failed = True
                    storage_delete_failures += 1
                    logger.warning(
                        "[export_retention] storage delete failed export_id=%s key=%s error=%s",
                        export.id,
                        key,
                        exc,
                    )

            if storage_delete_failed:
                continue

            db.delete(export)
            db.commit()
            deleted += 1

    payload = {
        "dry_run": dry_run,
        "enabled": True,
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(),
        "scanned": scanned,
        "eligible": eligible,
        "deleted": deleted,
        "skipped_active_publish_job": skipped_active_publish_job,
        "storage_delete_failures": storage_delete_failures,
    }
    logger.info("[export_retention] summary=%s", payload)
    return payload


@celery_app.task(name="app.worker.tasks.cleanup.sweep_export_retention", queue="ingest")
def sweep_export_retention(dry_run: bool = False):
    return sweep_export_retention_impl(dry_run=dry_run)


def sweep_raw_source_retention_impl(*, dry_run: bool) -> dict:
    if not settings.raw_source_retention_enabled:
        payload = {
            "dry_run": dry_run,
            "enabled": False,
            "scanned": 0,
            "eligible": 0,
            "deleted": 0,
            "skipped_active_job": 0,
            "skipped_pinned_or_active_project": 0,
            "storage_delete_failures": 0,
        }
        logger.info("[raw_source_retention] summary=%s", payload)
        return payload

    now = datetime.now(timezone.utc)
    retention_days = max(1, int(settings.raw_source_retention_days))
    cutoff = now - timedelta(days=retention_days)

    scanned = 0
    eligible = 0
    deleted = 0
    skipped_active_job = 0
    skipped_pinned_or_active_project = 0
    storage_delete_failures = 0

    with SyncSessionLocal() as db:
        rows = (
            db.execute(
                select(Video)
                .where(
                    Video.storage_key.is_not(None),
                    Video.updated_at <= cutoff,
                    Video.status.in_([VideoStatus.ready, VideoStatus.error]),
                )
                .order_by(Video.updated_at.asc())
            )
            .scalars()
            .all()
        )
        scanned = len(rows)

        for video in rows:
            if _has_active_jobs(db, video_id=video.id):
                skipped_active_job += 1
                continue
            if _has_pinned_or_active_editor_project(db, video_id=video.id):
                skipped_pinned_or_active_project += 1
                continue
            if not video.storage_key:
                continue

            eligible += 1
            if dry_run:
                continue

            deleted_ok = False
            try:
                deleted_ok = object_storage_client.delete_file(video.storage_key)
            except Exception as exc:
                storage_delete_failures += 1
                logger.warning(
                    "[raw_source_retention] storage delete failed video_id=%s key=%s error=%s",
                    video.id,
                    video.storage_key,
                    exc,
                )

            if not deleted_ok:
                storage_delete_failures += 1
                continue

            metadata = dict(video.external_metadata_json or {})
            metadata[RAW_SOURCE_EXPIRED_AT_KEY] = now.isoformat()
            video.external_metadata_json = metadata
            video.storage_key = None
            video.file_size_bytes = 0
            db.commit()
            deleted += 1

    payload = {
        "dry_run": dry_run,
        "enabled": True,
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(),
        "scanned": scanned,
        "eligible": eligible,
        "deleted": deleted,
        "skipped_active_job": skipped_active_job,
        "skipped_pinned_or_active_project": skipped_pinned_or_active_project,
        "storage_delete_failures": storage_delete_failures,
    }
    logger.info("[raw_source_retention] summary=%s", payload)
    return payload


@celery_app.task(name="app.worker.tasks.cleanup.sweep_raw_source_retention", queue="ingest")
def sweep_raw_source_retention(dry_run: bool = False):
    return sweep_raw_source_retention_impl(dry_run=dry_run)
