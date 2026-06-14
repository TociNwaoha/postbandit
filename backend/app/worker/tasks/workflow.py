import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.models.connected_account import ConnectedAccount
from app.models.publish_job import PublishJob, PublishStatus
from app.models.social_workflow import SocialWorkflow, SocialWorkflowRun, WorkflowRunStatus
from app.services.workflow_detection import fetch_recent_posts
from app.services.workflow_engine import (
    create_external_run,
    create_run_from_publish_job,
    fan_out_workflow_run,
    reconcile_workflow_run,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.workflow.process_publish_workflow_source", queue="publish")
def process_publish_workflow_source(publish_job_id: str):
    with SyncSessionLocal() as db:
        try:
            job_id = uuid.UUID(publish_job_id)
        except ValueError:
            return {"created": 0, "error": "invalid id"}
        source_job = db.scalar(select(PublishJob).where(PublishJob.id == job_id))
        if (
            not source_job
            or source_job.status != PublishStatus.published
            or not source_job.connected_account_id
            or not source_job.external_post_id
            or (source_job.provider_metadata_json or {}).get("workflow_origin")
        ):
            return {"created": 0}
        workflows = list(
            db.execute(
                select(SocialWorkflow).where(
                    SocialWorkflow.enabled.is_(True),
                    SocialWorkflow.source_account_id == source_job.connected_account_id,
                )
            ).scalars()
        )
        created = 0
        for workflow in workflows:
            run = create_run_from_publish_job(db, workflow, source_job)
            if run and run.status == WorkflowRunStatus.processing:
                fan_out_workflow_run(db, run)
                created += 1
        return {"created": created}


@celery_app.task(name="app.worker.tasks.workflow.process_workflow_run", queue="publish")
def process_workflow_run(run_id: str):
    with SyncSessionLocal() as db:
        try:
            run_uuid = uuid.UUID(run_id)
        except ValueError:
            return {"created": 0, "error": "invalid id"}
        run = db.scalar(select(SocialWorkflowRun).where(SocialWorkflowRun.id == run_uuid))
        if not run:
            return {"created": 0, "error": "not found"}
        run.status = WorkflowRunStatus.processing
        run.error_message = None
        db.commit()
        return fan_out_workflow_run(db, run)


@celery_app.task(name="app.worker.tasks.workflow.poll_social_workflows", queue="publish")
def poll_social_workflows():
    initialized = 0
    detected = 0
    errors = 0
    with SyncSessionLocal() as db:
        workflows = list(
            db.execute(
                select(SocialWorkflow)
                .where(SocialWorkflow.enabled.is_(True))
                .order_by(SocialWorkflow.last_checked_at.asc().nullsfirst())
            ).scalars()
        )
        for workflow in workflows:
            account = db.scalar(
                select(ConnectedAccount).where(
                    ConnectedAccount.id == workflow.source_account_id,
                    ConnectedAccount.user_id == workflow.user_id,
                )
            )
            if not account:
                workflow.last_error = "Source account disconnected. Reconnect and update this workflow."
                workflow.last_checked_at = datetime.now(timezone.utc)
                errors += 1
                db.commit()
                continue
            try:
                posts = fetch_recent_posts(account, db)
                seen = set((workflow.cursor_json or {}).get("seen_ids") or [])
                current_ids = [post.external_id for post in posts]
                if not (workflow.cursor_json or {}).get("initialized"):
                    created_at = workflow.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    else:
                        created_at = created_at.astimezone(timezone.utc)
                    for post in posts:
                        if post.published_at and post.published_at >= created_at:
                            create_external_run(db, workflow, post)
                            detected += 1
                    workflow.cursor_json = {"initialized": True, "seen_ids": current_ids[-100:]}
                    initialized += 1
                else:
                    for post in posts:
                        if post.external_id in seen:
                            continue
                        create_external_run(db, workflow, post)
                        detected += 1
                    workflow.cursor_json = {
                        "initialized": True,
                        "seen_ids": list(dict.fromkeys([*current_ids, *seen]))[:100],
                    }
                workflow.last_error = None
            except Exception as exc:
                logger.warning("[workflow] poll failed workflow_id=%s error=%s", workflow.id, exc)
                workflow.last_error = str(exc)[:500]
                errors += 1
            workflow.last_checked_at = datetime.now(timezone.utc)
            db.commit()
    return {"initialized": initialized, "detected": detected, "errors": errors}


@celery_app.task(name="app.worker.tasks.workflow.reconcile_social_workflow_runs", queue="publish")
def reconcile_social_workflow_runs():
    updated = 0
    with SyncSessionLocal() as db:
        runs = list(
            db.execute(
                select(SocialWorkflowRun).where(
                    SocialWorkflowRun.status.in_(
                        [WorkflowRunStatus.processing, WorkflowRunStatus.queued]
                    )
                )
            ).scalars()
        )
        for run in runs:
            before = run.status
            reconcile_workflow_run(db, run)
            if run.status != before:
                updated += 1
        db.commit()
    return {"updated": updated}
