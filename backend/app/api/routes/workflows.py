from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.connected_account import ConnectedAccount, SocialPlatform
from app.models.export import Export, ExportStatus
from app.models.publish_job import PublishJob
from app.models.social_workflow import SocialWorkflow, SocialWorkflowStatus
from app.models.social_workflow_source_post import (
    SocialWorkflowSourcePost,
    SocialWorkflowSourceStatus,
    source_status_to_run_status,
)
from app.models.user import User
from app.schemas.social_workflow import (
    SocialWorkflowAttachExportRequest,
    SocialWorkflowAttachExportResponse,
    SocialWorkflowCreateRequest,
    SocialWorkflowPatchRequest,
    SocialWorkflowPollResponse,
    SocialWorkflowResponse,
    SocialWorkflowStartSourcePostRequest,
    SocialWorkflowStartSourcePostResponse,
)
from app.schemas.social import PublishJobResponse
from app.services.workflows.official_sources import (
    is_reconnect_required_source_error,
    reconnect_required_source_message,
    start_source_post_workflow,
)

router = APIRouter(prefix="/social/workflows", tags=["social-workflows"])


ENABLED_SOURCE_PLATFORMS = {SocialPlatform.instagram, SocialPlatform.youtube, SocialPlatform.facebook}
POSTING_CADENCES = {"immediate", "once_daily", "twice_daily"}


def _normalize_posting_schedule(schedule) -> dict:
    if schedule is None:
        return {"cadence": "immediate", "times": [], "timezone": "UTC"}
    cadence = schedule.cadence if schedule.cadence in POSTING_CADENCES else "immediate"
    timezone_name = (schedule.timezone or "UTC").strip() or "UTC"
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=400, detail="Posting schedule timezone is invalid") from None

    normalized_times: list[str] = []
    for value in schedule.times or []:
        text = str(value).strip()
        try:
            hour_text, minute_text = text.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Posting schedule times must use HH:MM format") from None
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise HTTPException(status_code=400, detail="Posting schedule times must use HH:MM format")
        normalized_times.append(f"{hour:02d}:{minute:02d}")

    if cadence == "immediate":
        return {"cadence": "immediate", "times": [], "timezone": timezone_name}
    required = 2 if cadence == "twice_daily" else 1
    if len(normalized_times) < required:
        raise HTTPException(status_code=400, detail="Posting schedule is missing a posting time")
    return {"cadence": cadence, "times": sorted(normalized_times[:required]), "timezone": timezone_name}


def _destination_type(account: ConnectedAccount) -> str:
    metadata = account.metadata_json or {}
    return str(metadata.get("destination_type") or metadata.get("provider_destination_type") or account.platform.value)


def _is_valid_workflow_source_account(account: ConnectedAccount, platform: SocialPlatform) -> bool:
    if account.platform != platform:
        return False
    if platform == SocialPlatform.instagram:
        return _destination_type(account) == "instagram_professional"
    if platform == SocialPlatform.facebook:
        return _destination_type(account) == "facebook_page"
    if platform == SocialPlatform.youtube:
        return account.platform == SocialPlatform.youtube
    return False


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _auto_repair_workflow_sources(db: AsyncSession, workflows: list[SocialWorkflow]) -> None:
    changed = False
    for workflow in workflows:
        if workflow.source_account_id:
            account = await db.scalar(
                select(ConnectedAccount).where(
                    ConnectedAccount.id == workflow.source_account_id,
                    ConnectedAccount.user_id == workflow.user_id,
                )
            )
            if (
                account
                and _is_valid_workflow_source_account(account, workflow.source_platform)
                and workflow.last_error
                and is_reconnect_required_source_error(workflow.last_error)
            ):
                account_updated_at = _utc(account.updated_at)
                last_polled_at = _utc(workflow.last_polled_at)
                if account_updated_at and (last_polled_at is None or account_updated_at > last_polled_at):
                    workflow.last_error = None
                    changed = True
            continue

        result = await db.execute(
            select(ConnectedAccount)
            .where(
                ConnectedAccount.user_id == workflow.user_id,
                ConnectedAccount.platform == workflow.source_platform,
            )
            .order_by(ConnectedAccount.updated_at.desc())
        )
        candidates = [
            account
            for account in result.scalars().all()
            if _is_valid_workflow_source_account(account, workflow.source_platform)
        ]
        if len(candidates) == 1:
            workflow.source_account_id = candidates[0].id
            if workflow.last_error and is_reconnect_required_source_error(workflow.last_error):
                workflow.last_error = None
            changed = True

    if changed:
        await db.commit()


async def _validate_source_account(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    platform: SocialPlatform,
) -> ConnectedAccount:
    account = await db.scalar(select(ConnectedAccount).where(ConnectedAccount.id == account_id, ConnectedAccount.user_id == user_id))
    if not account:
        raise HTTPException(status_code=404, detail=f"{platform.value.title()} source account not found")
    if account.platform != platform:
        raise HTTPException(status_code=400, detail="Workflow source account platform mismatch")
    destination_type = _destination_type(account)
    if platform == SocialPlatform.instagram and destination_type != "instagram_professional":
        raise HTTPException(status_code=400, detail="Workflow source must be a connected Instagram professional account")
    if platform == SocialPlatform.facebook and destination_type != "facebook_page":
        raise HTTPException(status_code=400, detail="Workflow source must be a connected Facebook Page")
    if platform == SocialPlatform.youtube and account.platform != SocialPlatform.youtube:
        raise HTTPException(status_code=400, detail="Workflow source must be a connected YouTube channel")
    return account


async def _validate_destinations(db: AsyncSession, user_id: uuid.UUID, destinations) -> list[dict]:
    normalized: list[dict] = []
    seen: set[uuid.UUID] = set()
    for destination in destinations:
        if destination.connected_account_id in seen:
            continue
        account = await db.scalar(
            select(ConnectedAccount).where(
                ConnectedAccount.id == destination.connected_account_id,
                ConnectedAccount.user_id == user_id,
            )
        )
        if not account:
            raise HTTPException(status_code=404, detail=f"Destination account not found: {destination.connected_account_id}")
        if account.platform != destination.platform:
            raise HTTPException(status_code=400, detail="Destination account platform mismatch")
        if account.platform == SocialPlatform.instagram and _destination_type(account) != "instagram_professional":
            raise HTTPException(status_code=400, detail="Instagram destination must be a professional account")
        if account.platform == SocialPlatform.facebook and _destination_type(account) != "facebook_page":
            raise HTTPException(status_code=400, detail="Facebook destination must be a Page")
        if account.platform == SocialPlatform.linkedin:
            raise HTTPException(status_code=400, detail="LinkedIn automated workflow publishing is not enabled yet")
        normalized.append(
            {
                "platform": destination.platform.value,
                "connected_account_id": str(destination.connected_account_id),
                "display_name": account.display_name or account.username_or_channel_name or account.external_account_id,
            }
        )
        seen.add(destination.connected_account_id)
    if not normalized:
        raise HTTPException(status_code=400, detail="At least one destination account is required")
    return normalized


async def _workflow_or_404(db: AsyncSession, user_id: uuid.UUID, workflow_id: uuid.UUID) -> SocialWorkflow:
    workflow = await db.scalar(
        select(SocialWorkflow)
        .options(selectinload(SocialWorkflow.source_posts).selectinload(SocialWorkflowSourcePost.workflow_run))
        .where(SocialWorkflow.id == workflow_id, SocialWorkflow.user_id == user_id)
    )
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


async def _workflow_publish_jobs_by_source(
    db: AsyncSession,
    user_id: uuid.UUID,
    workflows: list[SocialWorkflow],
) -> dict[uuid.UUID, list[PublishJobResponse]]:
    source_post_ids = [
        source_post.id
        for workflow in workflows
        for source_post in workflow.source_posts
    ]
    if not source_post_ids:
        return {}

    result = await db.execute(
        select(PublishJob)
        .where(
            PublishJob.user_id == user_id,
            PublishJob.workflow_source_post_id.in_(source_post_ids),
        )
        .order_by(
            PublishJob.scheduled_for.asc().nullslast(),
            PublishJob.created_at.asc(),
        )
    )
    grouped: dict[uuid.UUID, list[PublishJobResponse]] = defaultdict(list)
    for job in result.scalars().all():
        if job.workflow_source_post_id:
            grouped[job.workflow_source_post_id].append(PublishJobResponse.model_validate(job))
    return grouped


def _workflow_response_payload(
    workflow: SocialWorkflow,
    jobs_by_source: dict[uuid.UUID, list[PublishJobResponse]],
) -> dict:
    source_posts = sorted(
        workflow.source_posts,
        key=lambda post: post.published_at or post.created_at,
        reverse=True,
    )
    source_account_status = "connected"
    source_account_action = None
    source_account_message = None
    if workflow.last_error and is_reconnect_required_source_error(workflow.last_error):
        source_account_status = "needs_reconnection"
        source_account_action = f"reconnect_{workflow.source_platform.value}"
        source_account_message = reconnect_required_source_message(workflow.source_platform)
    elif workflow.last_error:
        source_account_status = "poll_error"
        source_account_message = workflow.last_error
    return {
        "id": workflow.id,
        "user_id": workflow.user_id,
        "name": workflow.name,
        "source_platform": workflow.source_platform,
        "source_account_id": workflow.source_account_id,
        "status": workflow.status,
        "copy_mode": workflow.copy_mode,
        "auto_publish": workflow.auto_publish,
        "destination_targets_json": workflow.destination_targets_json,
        "poll_cursor_json": workflow.poll_cursor_json,
        "last_polled_at": workflow.last_polled_at,
        "last_error": workflow.last_error,
        "source_account_status": source_account_status,
        "source_account_action": source_account_action,
        "source_account_message": source_account_message,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
        "source_posts": [
            {
                "id": source_post.id,
                "user_id": source_post.user_id,
                "workflow_id": source_post.workflow_id,
                "source_account_id": source_post.source_account_id,
                "source_platform": source_post.source_platform,
                "external_post_id": source_post.external_post_id,
                "permalink": source_post.permalink,
                "caption_snapshot": source_post.caption_snapshot,
                "thumbnail_url": source_post.thumbnail_url,
                "published_at": source_post.published_at,
                "status": source_post.status,
                "video_id": source_post.video_id,
                "export_id": source_post.export_id,
                "workflow_run_id": source_post.workflow_run_id,
                "error_message": source_post.error_message,
                "raw_metadata_json": source_post.raw_metadata_json,
                "created_at": source_post.created_at,
                "updated_at": source_post.updated_at,
                "workflow_run": source_post.workflow_run,
                "publish_jobs": jobs_by_source.get(source_post.id, []),
            }
            for source_post in source_posts
        ],
    }


async def _workflow_responses(
    db: AsyncSession,
    user_id: uuid.UUID,
    workflows: list[SocialWorkflow],
) -> list[SocialWorkflowResponse]:
    await _auto_repair_workflow_sources(db, workflows)
    jobs_by_source = await _workflow_publish_jobs_by_source(db, user_id, workflows)
    return [
        SocialWorkflowResponse.model_validate(_workflow_response_payload(workflow, jobs_by_source))
        for workflow in workflows
    ]


@router.get("", response_model=list[SocialWorkflowResponse])
async def list_workflows(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(SocialWorkflow)
        .options(selectinload(SocialWorkflow.source_posts).selectinload(SocialWorkflowSourcePost.workflow_run))
        .where(SocialWorkflow.user_id == current_user.id)
        .order_by(SocialWorkflow.created_at.desc())
    )
    workflows = result.scalars().unique().all()
    return await _workflow_responses(db, current_user.id, workflows)


@router.post("", response_model=SocialWorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: SocialWorkflowCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.source_platform not in ENABLED_SOURCE_PLATFORMS:
        raise HTTPException(status_code=400, detail="Enabled workflow sources are Instagram, YouTube, and Facebook Pages")
    await _validate_source_account(db, current_user.id, body.source_account_id, body.source_platform)
    destinations = await _validate_destinations(db, current_user.id, body.destinations)
    workflow = SocialWorkflow(
        user_id=current_user.id,
        name=body.name.strip(),
        source_platform=body.source_platform,
        source_account_id=body.source_account_id,
        status=SocialWorkflowStatus.active,
        copy_mode=body.copy_mode,
        auto_publish=body.auto_publish,
        destination_targets_json=destinations,
        poll_cursor_json={
            "source_import_mode": body.source_import_mode,
            "source_backfill_limit": body.source_backfill_limit if body.source_import_mode == "last_n" else None,
            "posting_schedule": _normalize_posting_schedule(body.posting_schedule),
        },
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    workflow = await _workflow_or_404(db, current_user.id, workflow.id)
    return (await _workflow_responses(db, current_user.id, [workflow]))[0]


@router.get("/{workflow_id}", response_model=SocialWorkflowResponse)
async def get_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = await _workflow_or_404(db, current_user.id, workflow_id)
    return (await _workflow_responses(db, current_user.id, [workflow]))[0]


@router.patch("/{workflow_id}", response_model=SocialWorkflowResponse)
async def update_workflow(
    workflow_id: uuid.UUID,
    body: SocialWorkflowPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = await _workflow_or_404(db, current_user.id, workflow_id)
    if body.name is not None:
        workflow.name = body.name.strip()
    if body.status is not None:
        workflow.status = body.status
    if body.copy_mode is not None:
        workflow.copy_mode = body.copy_mode
    if body.auto_publish is not None:
        workflow.auto_publish = body.auto_publish
    if body.destinations is not None:
        workflow.destination_targets_json = await _validate_destinations(db, current_user.id, body.destinations)
    if body.posting_schedule is not None:
        cursor = dict(workflow.poll_cursor_json or {})
        cursor["posting_schedule"] = _normalize_posting_schedule(body.posting_schedule)
        workflow.poll_cursor_json = cursor
    await db.commit()
    workflow = await _workflow_or_404(db, current_user.id, workflow.id)
    return (await _workflow_responses(db, current_user.id, [workflow]))[0]


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = await _workflow_or_404(db, current_user.id, workflow_id)
    await db.delete(workflow)
    await db.commit()


@router.post("/{workflow_id}/poll-now", response_model=SocialWorkflowPollResponse)
async def poll_workflow_now(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = await _workflow_or_404(db, current_user.id, workflow_id)
    from app.worker.tasks.social_workflows import poll_official_source_workflow

    task = poll_official_source_workflow.apply_async(args=[str(workflow.id)], queue="ingest")
    return SocialWorkflowPollResponse(workflow_id=workflow.id, enqueued=True, task_id=task.id)


@router.post("/source-posts/{source_post_id}/attach-export", response_model=SocialWorkflowAttachExportResponse)
async def attach_export_to_source_post(
    source_post_id: uuid.UUID,
    body: SocialWorkflowAttachExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source_post = await db.scalar(
        select(SocialWorkflowSourcePost)
        .options(selectinload(SocialWorkflowSourcePost.workflow_run))
        .where(
            SocialWorkflowSourcePost.id == source_post_id,
            SocialWorkflowSourcePost.user_id == current_user.id,
        )
    )
    if not source_post:
        raise HTTPException(status_code=404, detail="Workflow source post not found")
    if source_post.status != SocialWorkflowSourceStatus.original_required:
        raise HTTPException(status_code=409, detail="An export can only be attached when the original file is required")
    export = await db.scalar(select(Export).where(Export.id == body.export_id, Export.user_id == current_user.id))
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")
    if export.status == ExportStatus.ready and not export.storage_key:
        raise HTTPException(status_code=400, detail="Attached export is missing its media file")
    if export.status not in {ExportStatus.ready, ExportStatus.queued, ExportStatus.rendering}:
        raise HTTPException(status_code=400, detail="Attached export must be ready, queued, or rendering")
    source_post.export_id = export.id
    source_post.status = SocialWorkflowSourceStatus.ready_to_publish
    source_post.error_message = None
    if source_post.workflow_run:
        source_post.workflow_run.status = source_status_to_run_status(source_post.status)
        source_post.workflow_run.error_message = None
    await db.commit()
    return SocialWorkflowAttachExportResponse(
        source_post_id=source_post.id,
        export_id=export.id,
        status=source_post.status,
    )


@router.post("/source-posts/{source_post_id}/start", response_model=SocialWorkflowStartSourcePostResponse)
async def start_source_post(
    source_post_id: uuid.UUID,
    body: SocialWorkflowStartSourcePostRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source_post = await db.scalar(
        select(SocialWorkflowSourcePost).where(
            SocialWorkflowSourcePost.id == source_post_id,
            SocialWorkflowSourcePost.user_id == current_user.id,
        )
    )
    if not source_post:
        raise HTTPException(status_code=404, detail="Workflow source post not found")

    destinations = None
    if body.destinations is not None:
        destinations = await _validate_destinations(db, current_user.id, body.destinations)

    result = start_source_post_workflow(str(source_post.id), destinations)
    status_value = result.get("status")
    if status_value == "missing":
        raise HTTPException(status_code=404, detail="Workflow source post not found")
    return SocialWorkflowStartSourcePostResponse(
        source_post_id=source_post.id,
        status=SocialWorkflowSourceStatus(str(status_value)),
        import_task_id=result.get("import_task_id"),
        publish_job_ids=result.get("publish_job_ids") or [],
        publish_task_ids=result.get("publish_task_ids") or [],
        skipped=result.get("skipped"),
    )
