from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.plans import get_storage_limits, storage_hard_stop_from_quota_bytes
from app.models.editor_asset import EditorAsset
from app.models.editor_render import EditorRender, EditorRenderStatus
from app.models.clip_overlay_asset import ClipOverlayAsset
from app.models.user import User
from app.models.user_storage_usage import UserStorageUsage
from app.models.video import Video
from app.schemas.editor import UserStorageUsageResponse


async def get_user_storage_limits(db: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    user = await db.get(User, user_id)
    if user is None:
        return get_storage_limits("trial", "trialing")
    return get_storage_limits(user.billing_plan, user.subscription_status)


async def refresh_user_storage_usage(db: AsyncSession, user_id: uuid.UUID) -> UserStorageUsage:
    quota_bytes, _hard_stop_bytes = await get_user_storage_limits(db, user_id)
    raw_video_bytes = (
        await db.scalar(
            select(func.coalesce(func.sum(Video.file_size_bytes), 0)).where(
                Video.user_id == user_id,
                Video.storage_key.is_not(None),
            )
        )
        or 0
    )

    editor_project_asset_bytes = (
        await db.scalar(
            select(func.coalesce(func.sum(EditorAsset.size_bytes), 0)).where(EditorAsset.user_id == user_id)
        )
        or 0
    )
    clip_overlay_asset_bytes = (
        await db.scalar(
            select(func.coalesce(func.sum(ClipOverlayAsset.size_bytes), 0)).where(
                ClipOverlayAsset.user_id == user_id
            )
        )
        or 0
    )
    editor_asset_bytes = int(editor_project_asset_bytes) + int(clip_overlay_asset_bytes)

    render_output_bytes = (
        await db.scalar(
            select(func.coalesce(func.sum(EditorRender.output_size_bytes), 0)).where(
                EditorRender.user_id == user_id,
                EditorRender.status == EditorRenderStatus.completed,
                EditorRender.output_storage_key.is_not(None),
            )
        )
        or 0
    )

    used_bytes = int(raw_video_bytes) + int(editor_asset_bytes) + int(render_output_bytes)

    usage = await db.get(UserStorageUsage, user_id)
    if usage is None:
        usage = UserStorageUsage(
            user_id=user_id,
            quota_bytes=quota_bytes,
            used_bytes=used_bytes,
            raw_video_bytes=int(raw_video_bytes),
            editor_asset_bytes=int(editor_asset_bytes),
            render_output_bytes=int(render_output_bytes),
        )
        db.add(usage)
    else:
        usage.quota_bytes = quota_bytes
        usage.used_bytes = used_bytes
        usage.raw_video_bytes = int(raw_video_bytes)
        usage.editor_asset_bytes = int(editor_asset_bytes)
        usage.render_output_bytes = int(render_output_bytes)

    await db.flush()
    return usage


def to_usage_response(usage: UserStorageUsage) -> UserStorageUsageResponse:
    quota_bytes = int(usage.quota_bytes or 0)
    hard_stop_bytes = storage_hard_stop_from_quota_bytes(quota_bytes)
    warning = int(usage.used_bytes or 0) >= int(usage.quota_bytes or 0)
    blocked = int(usage.used_bytes or 0) >= hard_stop_bytes
    return UserStorageUsageResponse(
        quota_bytes=quota_bytes,
        hard_stop_bytes=hard_stop_bytes,
        used_bytes=int(usage.used_bytes or 0),
        raw_video_bytes=int(usage.raw_video_bytes or 0),
        editor_asset_bytes=int(usage.editor_asset_bytes or 0),
        render_output_bytes=int(usage.render_output_bytes or 0),
        warning=warning,
        blocked=blocked,
    )


async def enforce_storage_hard_stop(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    incoming_bytes: int = 0,
    operation_label: str,
) -> UserStorageUsage:
    usage = await refresh_user_storage_usage(db, user_id)
    projected = int(usage.used_bytes or 0) + max(0, int(incoming_bytes))
    hard_stop = storage_hard_stop_from_quota_bytes(int(usage.quota_bytes or 0))
    if projected >= hard_stop:
        over_by = projected - hard_stop
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Storage hard limit reached for {operation_label}. "
                f"Free at least {max(over_by, 0)} bytes and retry."
            ),
        )
    return usage
