import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.connected_account import ConnectedAccount
from app.models.export import Export, ExportStatus
from app.models.social_workflow import SocialWorkflow, SocialWorkflowRun, WorkflowRunStatus
from app.models.user import User
from app.schemas.workflow import (
    WorkflowAttachExportRequest,
    WorkflowCreateRequest,
    WorkflowPatchRequest,
    WorkflowResponse,
    WorkflowRunListResponse,
    WorkflowRunResponse,
    WorkflowSourceCapabilityResponse,
)
from app.services.workflow_detection import source_capability

router = APIRouter(prefix="/social/workflows", tags=["social-workflows"])


async def _owned_accounts(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_ids: set[uuid.UUID],
) -> dict[uuid.UUID, ConnectedAccount]:
    if not account_ids:
        return {}
    rows = await db.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.user_id == user_id,
            ConnectedAccount.id.in_(account_ids),
        )
    )
    return {account.id: account for account in rows.scalars()}


async def _validated_config(
    db: AsyncSession,
    current_user: User,
    source_account_id: uuid.UUID,
    destinations,
) -> tuple[ConnectedAccount, list[dict]]:
    destination_ids = {item.connected_account_id for item in destinations}
    accounts = await _owned_accounts(db, current_user.id, {source_account_id, *destination_ids})
    source = accounts.get(source_account_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source connected account not found")
    configs: list[dict] = []
    for item in destinations:
        account = accounts.get(item.connected_account_id)
        if not account:
            raise HTTPException(status_code=404, detail=f"Destination account not found: {item.connected_account_id}")
        if account.platform != item.platform:
            raise HTTPException(status_code=400, detail="Destination platform does not match connected account")
        if account.id == source.id:
            raise HTTPException(status_code=400, detail="Source account cannot also be a destination")
        configs.append(
            {
                "connected_account_id": str(account.id),
                "platform": account.platform.value,
                "display_name": account.display_name or account.username_or_channel_name,
                "privacy": item.privacy,
            }
        )
    return source, configs


@router.get("/capabilities", response_model=list[WorkflowSourceCapabilityResponse])
async def list_source_capabilities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    accounts = (
        await db.execute(
            select(ConnectedAccount)
            .where(ConnectedAccount.user_id == current_user.id)
            .order_by(ConnectedAccount.platform, ConnectedAccount.created_at)
        )
    ).scalars()
    result = []
    for account in accounts:
        capability_status, message, missing = source_capability(account)
        result.append(
            WorkflowSourceCapabilityResponse(
                connected_account_id=account.id,
                platform=account.platform,
                status=capability_status,
                message=message,
                missing_scopes=missing,
            )
        )
    return result


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        await db.execute(
            select(SocialWorkflow)
            .where(SocialWorkflow.user_id == current_user.id)
            .order_by(SocialWorkflow.created_at.desc())
        )
    ).scalars().all()


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: WorkflowCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source, configs = await _validated_config(db, current_user, body.source_account_id, body.destinations)
    capability_status, message, missing = source_capability(source)
    workflow = SocialWorkflow(
        user_id=current_user.id,
        name=body.name.strip(),
        source_account_id=source.id,
        source_platform=source.platform,
        copy_mode=body.copy_mode,
        destination_configs=configs,
        enabled=body.enabled,
        last_error=(
            f"{message} Missing scopes: {', '.join(missing)}" if capability_status != "ready" and message else None
        ),
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    if workflow.enabled:
        from app.worker.tasks.workflow import poll_social_workflows

        poll_social_workflows.apply_async(queue="publish", countdown=1)
    return workflow


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = (
        await db.execute(
            select(SocialWorkflow).where(
                SocialWorkflow.id == workflow_id,
                SocialWorkflow.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    source_account_id = body.source_account_id or workflow.source_account_id
    if not source_account_id:
        raise HTTPException(status_code=400, detail="Select a connected source account")
    if body.destinations is not None:
        destinations = body.destinations
    else:
        from app.schemas.workflow import WorkflowDestinationInput

        destinations = [
            WorkflowDestinationInput(
                connected_account_id=uuid.UUID(str(item["connected_account_id"])),
                platform=item["platform"],
                privacy=item.get("privacy"),
            )
            for item in workflow.destination_configs
        ]
    source, configs = await _validated_config(db, current_user, source_account_id, destinations)
    if body.name is not None:
        workflow.name = body.name.strip()
    workflow.source_account_id = source.id
    workflow.source_platform = source.platform
    workflow.destination_configs = configs
    if body.copy_mode is not None:
        workflow.copy_mode = body.copy_mode
    if body.enabled is not None:
        workflow.enabled = body.enabled
    if body.source_account_id is not None:
        workflow.cursor_json = {}
        workflow.last_checked_at = None
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = (
        await db.execute(
            select(SocialWorkflow).where(
                SocialWorkflow.id == workflow_id,
                SocialWorkflow.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await db.delete(workflow)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{workflow_id}/runs", response_model=WorkflowRunListResponse)
async def list_workflow_runs(
    workflow_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow_exists = await db.scalar(
        select(SocialWorkflow.id).where(
            SocialWorkflow.id == workflow_id,
            SocialWorkflow.user_id == current_user.id,
        )
    )
    if not workflow_exists:
        raise HTTPException(status_code=404, detail="Workflow not found")
    conditions = [
        SocialWorkflowRun.workflow_id == workflow_id,
        SocialWorkflowRun.user_id == current_user.id,
    ]
    total = await db.scalar(select(func.count(SocialWorkflowRun.id)).where(*conditions))
    items = (
        await db.execute(
            select(SocialWorkflowRun)
            .where(*conditions)
            .order_by(SocialWorkflowRun.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return WorkflowRunListResponse(items=items, total=int(total or 0))


@router.post("/runs/{run_id}/attach-export", response_model=WorkflowRunResponse)
async def attach_export_to_run(
    run_id: uuid.UUID,
    body: WorkflowAttachExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = (
        await db.execute(
            select(SocialWorkflowRun).where(
                SocialWorkflowRun.id == run_id,
                SocialWorkflowRun.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    export = (
        await db.execute(
            select(Export).where(
                Export.id == body.export_id,
                Export.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")
    if export.status != ExportStatus.ready or not export.storage_key:
        raise HTTPException(status_code=400, detail="Attach a ready MP4 export")
    run.source_export_id = export.id
    run.status = WorkflowRunStatus.processing
    run.error_message = None
    await db.commit()
    await db.refresh(run)

    from app.worker.tasks.workflow import process_workflow_run

    process_workflow_run.apply_async(args=[str(run.id)], queue="publish", countdown=1)
    return run


@router.post("/{workflow_id}/poll-now", response_model=WorkflowResponse)
async def poll_workflow_now(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workflow = (
        await db.execute(
            select(SocialWorkflow).where(
                SocialWorkflow.id == workflow_id,
                SocialWorkflow.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    from app.worker.tasks.workflow import poll_social_workflows

    poll_social_workflows.apply_async(queue="publish", countdown=1)
    return workflow
