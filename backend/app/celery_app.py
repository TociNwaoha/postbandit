from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "clipbandit",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.worker.tasks.ingest",
        "app.worker.tasks.ingest_playlist",
        "app.worker.tasks.cleanup",
        "app.worker.tasks.editor_preview",
        "app.worker.tasks.transcribe",
        "app.worker.tasks.score",
        "app.worker.tasks.render",
        "app.worker.tasks.editor_render",
        "app.worker.tasks.publish",
        "app.worker.tasks.content_generation",
    ],
)

beat_schedule: dict[str, dict] = {}
if settings.workspace_cleanup_enabled:
    beat_schedule["workspace-cleanup-hourly"] = {
        "task": "app.worker.tasks.cleanup.sweep_workspaces",
        "schedule": 3600.0,
        "args": (bool(settings.workspace_cleanup_dry_run),),
    }
if settings.failed_import_cleanup_enabled:
    beat_schedule["failed-import-cleanup-hourly"] = {
        "task": "app.worker.tasks.cleanup.sweep_failed_imports",
        "schedule": 3600.0,
        "args": (bool(settings.failed_import_cleanup_dry_run),),
    }
if settings.stale_queued_upload_cleanup_enabled:
    beat_schedule["stale-queued-upload-cleanup-hourly"] = {
        "task": "app.worker.tasks.cleanup.sweep_stale_queued_uploads",
        "schedule": 3600.0,
        "args": (bool(settings.stale_queued_upload_cleanup_dry_run),),
    }
if settings.raw_source_retention_enabled:
    beat_schedule["raw-source-retention-hourly"] = {
        "task": "app.worker.tasks.cleanup.sweep_raw_source_retention",
        "schedule": 3600.0,
        "args": (False,),
    }
beat_schedule["generate-daily-content"] = {
    "task": "generate_daily_content",
    "schedule": crontab(hour=8, minute=0),
}

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_expires=3600,
    task_routes={
        "app.worker.tasks.ingest.*": {"queue": "ingest"},
        "app.worker.tasks.ingest_playlist.*": {"queue": "ingest"},
        "app.worker.tasks.cleanup.*": {"queue": "ingest"},
        "app.worker.tasks.editor_preview.*": {"queue": "ingest"},
        "app.worker.tasks.transcribe.*": {"queue": "transcribe"},
        "app.worker.tasks.score.*": {"queue": "score"},
        "app.worker.tasks.render.*": {"queue": "render"},
        "app.worker.tasks.editor_render.*": {"queue": "render"},
        "app.worker.tasks.publish.*": {"queue": "publish"},
        "app.worker.tasks.content_generation.*": {"queue": "ingest"},
        "generate_daily_content": {"queue": "ingest"},
    },
    task_queues={
        "ingest": {},
        "transcribe": {},
        "score": {},
        "render": {},
        "publish": {},
    },
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule=beat_schedule,
)
