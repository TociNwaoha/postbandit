from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.services.social.security import sanitize_sensitive_text
from app.services.workflows.official_sources import (
    continue_ready_official_source_workflows,
    import_source_post,
    poll_active_official_source_workflows,
    poll_source_workflow,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.social_workflows.poll_official_source_workflows", queue="ingest", max_retries=0)
def poll_official_source_workflows():
    try:
        return poll_active_official_source_workflows()
    except Exception as exc:
        logger.exception("[workflows] poll_official_source_workflows failed: %s", sanitize_sensitive_text(exc))
        return {"status": "failed", "error": sanitize_sensitive_text(exc)}


@celery_app.task(name="app.worker.tasks.social_workflows.poll_official_source_workflow", queue="ingest", max_retries=0)
def poll_official_source_workflow(workflow_id: str):
    try:
        return poll_source_workflow(workflow_id)
    except Exception as exc:
        logger.exception("[workflows] poll_official_source_workflow failed workflow_id=%s: %s", workflow_id, sanitize_sensitive_text(exc))
        return {"workflow_id": workflow_id, "status": "failed", "error": sanitize_sensitive_text(exc)}


@celery_app.task(name="app.worker.tasks.social_workflows.import_source_post_media", queue="ingest", max_retries=0)
def import_source_post_media(source_post_id: str):
    try:
        return import_source_post(source_post_id)
    except Exception as exc:
        logger.exception("[workflows] import_source_post_media failed source_post_id=%s: %s", source_post_id, sanitize_sensitive_text(exc))
        return {"source_post_id": source_post_id, "status": "failed", "error": sanitize_sensitive_text(exc)}


@celery_app.task(name="app.worker.tasks.social_workflows.continue_source_workflow_after_video_ready", queue="ingest", max_retries=0)
def continue_source_workflow_after_video_ready():
    try:
        return continue_ready_official_source_workflows()
    except Exception as exc:
        logger.exception("[workflows] continue_source_workflow_after_video_ready failed: %s", sanitize_sensitive_text(exc))
        return {"status": "failed", "error": sanitize_sensitive_text(exc)}
