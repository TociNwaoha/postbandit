from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.clip import Clip
from app.models.connected_account import ConnectedAccount, SocialPlatform
from app.models.export import Export, ExportStatus
from app.models.publish_job import PublishJob, PublishMode, PublishStatus
from app.models.social_workflow import (
    SocialWorkflow,
    SocialWorkflowRun,
    WorkflowCopyMode,
    WorkflowRunStatus,
)
from app.services.ai_copy import AICopyError, generate_platform_copy
from app.services.social.registry import get_adapter


HASHTAG_RE = re.compile(r"(?<!\w)#[A-Za-z0-9_]+")
DEFAULT_MAX_DURATION_SECONDS: dict[SocialPlatform, int] = {
    SocialPlatform.instagram: 15 * 60,
    SocialPlatform.threads: 5 * 60,
    SocialPlatform.tiktok: 10 * 60,
    SocialPlatform.x: 140,
}


def _source_copy(run: SocialWorkflowRun, platform: SocialPlatform) -> dict:
    title = (run.source_title or "").strip() or None
    description = (run.source_description or "").strip() or None
    hashtags = HASHTAG_RE.findall(description or "")
    caption = description or title
    if platform == SocialPlatform.youtube:
        return {"title": title, "description": description, "caption": None, "hashtags": hashtags[:15]}
    return {"title": title, "description": description, "caption": caption, "hashtags": hashtags}


def _duration_limit(account: ConnectedAccount) -> int | None:
    metadata = account.metadata_json or {}
    creator_info = metadata.get("creator_info") if isinstance(metadata.get("creator_info"), dict) else {}
    raw = (
        metadata.get("max_video_post_duration_sec")
        or creator_info.get("max_video_post_duration_sec")
        or creator_info.get("max_video_duration")
    )
    if isinstance(raw, (int, float)) and raw > 0:
        return int(raw)
    return DEFAULT_MAX_DURATION_SECONDS.get(account.platform)


def _validate_destination_media(account: ConnectedAccount, clip: Clip) -> str | None:
    adapter = get_adapter(account.platform)
    capabilities = adapter.capabilities()
    if not capabilities.supports_video_upload:
        return "This destination does not support automatic video upload."
    duration = max(0.0, float(clip.end_time) - float(clip.start_time))
    max_duration = _duration_limit(account)
    if max_duration and duration > max_duration:
        return f"Skipped: {duration:.0f}s video exceeds the {max_duration}s destination limit."
    return None


def create_run_from_publish_job(db, workflow: SocialWorkflow, source_job: PublishJob) -> SocialWorkflowRun | None:
    if not source_job.external_post_id:
        return None
    existing = db.scalar(
        select(SocialWorkflowRun).where(
            SocialWorkflowRun.workflow_id == workflow.id,
            SocialWorkflowRun.source_external_post_id == source_job.external_post_id,
        )
    )
    if existing:
        if source_job.export_id and not existing.source_export_id:
            existing.source_publish_job_id = source_job.id
            existing.source_export_id = source_job.export_id
            existing.source_external_url = source_job.external_post_url or existing.source_external_url
            existing.source_title = source_job.title or source_job.content_title_snapshot or existing.source_title
            existing.source_description = source_job.description or source_job.caption or existing.source_description
            existing.status = WorkflowRunStatus.processing
            existing.error_message = None
            db.commit()
        return existing
    run = SocialWorkflowRun(
        workflow_id=workflow.id,
        user_id=workflow.user_id,
        source_publish_job_id=source_job.id,
        source_export_id=source_job.export_id,
        source_platform=source_job.platform,
        source_external_post_id=source_job.external_post_id,
        source_external_url=source_job.external_post_url,
        source_title=source_job.title or source_job.content_title_snapshot,
        source_description=source_job.description or source_job.caption,
        source_published_at=source_job.updated_at,
        status=WorkflowRunStatus.processing if source_job.export_id else WorkflowRunStatus.waiting_asset,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(
            select(SocialWorkflowRun).where(
                SocialWorkflowRun.workflow_id == workflow.id,
                SocialWorkflowRun.source_external_post_id == source_job.external_post_id,
            )
        )
    db.refresh(run)
    return run


def create_external_run(db, workflow: SocialWorkflow, post) -> SocialWorkflowRun | None:
    existing = db.scalar(
        select(SocialWorkflowRun).where(
            SocialWorkflowRun.workflow_id == workflow.id,
            SocialWorkflowRun.source_external_post_id == post.external_id,
        )
    )
    if existing:
        return existing
    run = SocialWorkflowRun(
        workflow_id=workflow.id,
        user_id=workflow.user_id,
        source_platform=workflow.source_platform,
        source_external_post_id=post.external_id,
        source_external_url=post.url,
        source_title=post.title,
        source_description=post.description,
        source_published_at=post.published_at,
        status=WorkflowRunStatus.waiting_asset,
        error_message="Original file required. Attach a ready PostBandit export to continue.",
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(run)
    return run


def fan_out_workflow_run(db, run: SocialWorkflowRun) -> dict:
    workflow = db.scalar(select(SocialWorkflow).where(SocialWorkflow.id == run.workflow_id))
    if not workflow or not workflow.enabled:
        run.status = WorkflowRunStatus.skipped
        run.error_message = "Workflow is disabled."
        db.commit()
        return {"created": 0, "skipped": 0}
    export_row = db.execute(
        select(Export, Clip).join(Clip, Export.clip_id == Clip.id).where(
            Export.id == run.source_export_id,
            Export.user_id == run.user_id,
        )
    ).first()
    if not export_row:
        run.status = WorkflowRunStatus.waiting_asset
        run.error_message = "Original file required. Attach a ready PostBandit export to continue."
        db.commit()
        return {"created": 0, "skipped": 0}
    export, clip = export_row
    if export.status != ExportStatus.ready or not export.storage_key:
        run.status = WorkflowRunStatus.waiting_asset
        run.error_message = "The attached export is not ready."
        db.commit()
        return {"created": 0, "skipped": 0}

    destination_configs = workflow.destination_configs or []
    account_ids = []
    for config in destination_configs:
        try:
            account_ids.append(uuid.UUID(str(config.get("connected_account_id"))))
        except (TypeError, ValueError):
            continue
    accounts = {
        account.id: account
        for account in db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.user_id == run.user_id,
                ConnectedAccount.id.in_(account_ids),
            )
        ).scalars()
    }

    platforms = sorted({account.platform.value for account in accounts.values()})
    copy_results: dict[str, dict] = {}
    copy_errors: dict[str, str] = {}
    if workflow.copy_mode == WorkflowCopyMode.ai_platform and platforms:
        transcript = " ".join((clip.transcript_text or "").split())
        if transcript:
            try:
                generated = generate_platform_copy(
                    transcript,
                    platforms,
                    video_title=run.source_title,
                    topic_hint=run.source_description,
                )
                copy_results = generated.results
                copy_errors = generated.errors
            except AICopyError as exc:
                copy_errors = {platform: str(exc) for platform in platforms}
        else:
            copy_errors = {platform: "Transcript unavailable; source copy used." for platform in platforms}

    created_jobs: list[PublishJob] = []
    destination_errors: dict[str, str] = {}
    for config in destination_configs:
        account_id_text = str(config.get("connected_account_id") or "")
        try:
            account_id = uuid.UUID(account_id_text)
        except ValueError:
            destination_errors[account_id_text or "unknown"] = "Invalid destination account."
            continue
        account = accounts.get(account_id)
        if not account:
            destination_errors[account_id_text] = "Destination disconnected. Reconnect and update the workflow."
            continue
        if account.id == workflow.source_account_id:
            destination_errors[account_id_text] = "Source account cannot be a destination."
            continue
        media_error = _validate_destination_media(account, clip)
        if media_error:
            destination_errors[account_id_text] = media_error
            continue
        setup_status, setup_message = get_adapter(account.platform).setup_status()
        if setup_status != "ready":
            destination_errors[account_id_text] = setup_message or "Provider is not configured."
            continue

        content = copy_results.get(account.platform.value) or _source_copy(run, account.platform)
        privacy = str(config.get("privacy") or "").strip() or None
        if account.platform == SocialPlatform.youtube and not privacy:
            privacy = "private"
        if account.platform == SocialPlatform.tiktok and not privacy:
            privacy = "SELF_ONLY"
        job = PublishJob(
            user_id=run.user_id,
            export_id=export.id,
            clip_id=clip.id,
            workflow_run_id=run.id,
            platform=account.platform,
            connected_account_id=account.id,
            status=PublishStatus.queued,
            publish_mode=PublishMode.now,
            caption=content.get("caption"),
            title=content.get("title"),
            description=content.get("description"),
            hashtags=content.get("hashtags") or [],
            privacy=privacy,
            destination_display_name=account.display_name or account.username_or_channel_name,
            content_title_snapshot=content.get("title") or run.source_title or "Automated cross-post",
            provider_metadata_json={
                "workflow_origin": True,
                "workflow_id": str(workflow.id),
                "workflow_run_id": str(run.id),
                "source_platform": run.source_platform.value,
                "source_external_post_id": run.source_external_post_id,
            },
        )
        db.add(job)
        created_jobs.append(job)

    run.generated_copy_json = {
        "mode": workflow.copy_mode.value,
        "results": copy_results,
        "copy_errors": copy_errors,
        "destination_errors": destination_errors,
    }
    run.error_message = None if created_jobs else "No compatible connected destinations were available."
    run.status = WorkflowRunStatus.queued if created_jobs else WorkflowRunStatus.skipped
    db.commit()

    from app.worker.tasks.publish import execute_publish_job

    for job in created_jobs:
        execute_publish_job.apply_async(args=[str(job.id)], queue="publish", countdown=1)
    return {"created": len(created_jobs), "skipped": len(destination_errors)}


def reconcile_workflow_run(db, run: SocialWorkflowRun) -> None:
    jobs = list(
        db.execute(select(PublishJob).where(PublishJob.workflow_run_id == run.id)).scalars()
    )
    if not jobs:
        return
    active = {PublishStatus.queued, PublishStatus.publishing, PublishStatus.scheduled}
    if any(job.status in active for job in jobs):
        run.status = WorkflowRunStatus.queued
        return
    published = sum(job.status == PublishStatus.published for job in jobs)
    destination_errors = (run.generated_copy_json or {}).get("destination_errors") or {}
    if published == len(jobs) and not destination_errors:
        run.status = WorkflowRunStatus.completed
        run.error_message = None
    elif published:
        run.status = WorkflowRunStatus.partial_failed
        skipped = len(destination_errors)
        run.error_message = (
            f"{published} destination(s) published"
            + (f"; {skipped} skipped." if skipped else f" of {len(jobs)}.")
        )
    else:
        run.status = WorkflowRunStatus.failed
        run.error_message = "All destination publishes failed."


def workflow_run_counts(db, workflow_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(SocialWorkflowRun.status, func.count(SocialWorkflowRun.id))
        .where(SocialWorkflowRun.workflow_id == workflow_id)
        .group_by(SocialWorkflowRun.status)
    ).all()
    return {status.value: count for status, count in rows}
