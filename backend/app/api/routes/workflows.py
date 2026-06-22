from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.connected_account import ConnectedAccount, SocialPlatform
from app.models.export import Export, ExportStatus
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
)

router = APIRouter(prefix="/social/workflows", tags=["social-workflows"])


def _destination_type(account: ConnectedAccount) -> str:
    metadata = account.metadata_json or {}
    return str(metadata.get("destination_type") or metadata.get("provider_destination_type") or account.platform.value)


async def _validate_source_account(db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID) -> ConnectedAccount:
    account = await db.scalar(select(ConnectedAccount).where(ConnectedAccount.id == account_id, ConnectedAccount.user_id == user_id))
    if not account:
        raise HTTPException(status_code=404, detail="Instagram source account not found")
    if account.platform != SocialPlatform.instagram or _destination_type(account) != "instagram_professional":
        raise HTTPException(status_code=400, detail="Workflow source must be a connected Instagram professional account")
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


@router.get("", response_model=list[SocialWorkflowResponse])
async def list_workflows(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(SocialWorkflow)
        .options(selectinload(SocialWorkflow.source_posts).selectinload(SocialWorkflowSourcePost.workflow_run))
        .where(SocialWorkflow.user_id == current_user.id)
        .order_by(SocialWorkflow.created_at.desc())
    )
    return result.scalars().unique().all()


@router.post("", response_model=SocialWorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: SocialWorkflowCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.source_platform != SocialPlatform.instagram:
        raise HTTPException(status_code=400, detail="Instagram is the only official source platform enabled in v1")
    await _validate_source_account(db, current_user.id, body.source_account_id)
    destinations = await _validate_destinations(db, current_user.id, body.destinations)
    workflow = SocialWorkflow(
        user_id=current_user.id,
        name=body.name.strip(),
        source_platform=SocialPlatform.instagram,
        source_account_id=body.source_account_id,
        status=SocialWorkflowStatus.active,
        copy_mode=body.copy_mode,
        auto_publish=body.auto_publish,
        destination_targets_json=destinations,
        poll_cursor_json={},
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return await _workflow_or_404(db, current_user.id, workflow.id)


@router.get("/{workflow_id}", response_model=SocialWorkflowResponse)
async def get_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _workflow_or_404(db, current_user.id, workflow_id)


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
    await db.commit()
    return await _workflow_or_404(db, current_user.id, workflow.id)


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
    if export.status != ExportStatus.ready or not export.storage_key:
        raise HTTPException(status_code=400, detail="Attached export must be ready")
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
