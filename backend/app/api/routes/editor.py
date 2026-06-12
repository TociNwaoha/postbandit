from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.clip import Clip
from app.models.editor_asset import EditorAsset, EditorAssetType
from app.models.editor_project import EditorProject, EditorProjectStatus
from app.models.editor_render import EditorRender, EditorRenderPreset, EditorRenderStatus
from app.models.export import AspectRatio, CaptionFormat, Export, ExportStatus
from app.models.transcript import TranscriptSegment
from app.models.user import User
from app.models.video import Video
from app.schemas.editor import (
    EditorAssetResponse,
    EditorProjectCreateFromClipRequest,
    EditorProjectDuplicateResponse,
    EditorProjectFromClipResponse,
    EditorProjectPatchRequest,
    EditorProjectResponse,
    EditorRenderRequest,
    EditorRenderResponse,
    EditorProjectSchemaV1,
)
from app.services.editor_aspect import (
    aspect_ratio_dimensions,
    canvas_aspect_value,
    infer_editor_aspect_ratio,
    safe_area_preset_for_aspect,
)
from app.services.editor_projects import build_default_project_json, clamp_trim
from app.services.editor_project_preview import (
    build_project_preview_key,
    mark_project_preview_failed,
    mark_project_preview_pending,
    parse_project_preview_metadata,
    preserve_project_preview_metadata,
    resolve_project_preview_window,
    should_enqueue_project_preview,
)
from app.services.editor_quota import enforce_storage_hard_stop, refresh_user_storage_usage, to_usage_response
from app.services.r2 import r2_client

router = APIRouter()
logger = logging.getLogger(__name__)


MAX_EDITOR_ASSET_BYTES = 25 * 1024 * 1024


def _asset_download_url(storage_key: str | None) -> str | None:
    if not storage_key:
        return None
    try:
        if not r2_client.file_exists(storage_key):
            return None
        return r2_client.get_presigned_download_url(storage_key)
    except Exception:
        return None


def _asset_to_response(asset: EditorAsset) -> EditorAssetResponse:
    return EditorAssetResponse(
        id=asset.id,
        project_id=asset.project_id,
        user_id=asset.user_id,
        asset_type=asset.asset_type,
        storage_key=asset.storage_key,
        original_filename=asset.original_filename,
        mime_type=asset.mime_type,
        size_bytes=int(asset.size_bytes or 0),
        width=asset.width,
        height=asset.height,
        download_url=_asset_download_url(asset.storage_key),
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _render_to_response(render: EditorRender | None) -> EditorRenderResponse | None:
    if not render:
        return None
    return EditorRenderResponse(
        id=render.id,
        project_id=render.project_id,
        user_id=render.user_id,
        export_id=render.export_id,
        status=render.status,
        preset=render.preset,
        output_storage_key=render.output_storage_key,
        output_size_bytes=render.output_size_bytes,
        error_message=render.error_message,
        download_url=_asset_download_url(render.output_storage_key),
        started_at=render.started_at,
        completed_at=render.completed_at,
        created_at=render.created_at,
        updated_at=render.updated_at,
    )


async def _project_or_404(db: AsyncSession, *, project_id: uuid.UUID, user_id: uuid.UUID) -> EditorProject:
    row = await db.execute(
        select(EditorProject)
        .options(selectinload(EditorProject.assets), selectinload(EditorProject.renders))
        .where(EditorProject.id == project_id, EditorProject.user_id == user_id)
    )
    project = row.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Editor project not found")
    return project


async def _project_response(db: AsyncSession, project: EditorProject) -> EditorProjectResponse:
    usage = await refresh_user_storage_usage(db, project.user_id)
    latest_render = None
    if project.last_render_id:
        latest_render = await db.get(EditorRender, project.last_render_id)
    if latest_render is None and project.renders:
        latest_render = sorted(project.renders, key=lambda item: item.created_at, reverse=True)[0]

    preview_meta = parse_project_preview_metadata(project.project_json)
    preview_download_url = None
    if preview_meta.status == "ready" and preview_meta.key:
        try:
            if r2_client.file_exists(preview_meta.key):
                preview_download_url = r2_client.get_presigned_download_url(preview_meta.key)
        except Exception:
            preview_download_url = None

    return EditorProjectResponse(
        id=project.id,
        user_id=project.user_id,
        video_id=project.video_id,
        clip_id=project.clip_id,
        name=project.name,
        status=project.status,
        aspect_ratio=project.aspect_ratio,
        trim_start_sec=float(project.trim_start_sec),
        trim_end_sec=float(project.trim_end_sec),
        is_pinned=bool(project.is_pinned),
        revision=int(project.revision),
        project_json=project.project_json,
        last_render_id=project.last_render_id,
        assets=[_asset_to_response(asset) for asset in sorted(project.assets, key=lambda item: item.created_at)],
        latest_render=_render_to_response(latest_render),
        storage_usage=to_usage_response(usage),
        preview_status=preview_meta.status,
        preview_download_url=preview_download_url,
        preview_offset_sec=preview_meta.offset_sec,
        preview_duration_sec=preview_meta.duration_sec,
        preview_error=preview_meta.error,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def _ensure_project_preview_proxy(db: AsyncSession, project: EditorProject, *, force: bool = False) -> EditorProject:
    row = await db.execute(
        select(Clip, Video)
        .join(Video, Clip.video_id == Video.id)
        .where(Clip.id == project.clip_id, Video.id == project.video_id)
    )
    result = row.first()
    if not result:
        return project

    clip, video = result
    window = resolve_project_preview_window(project=project, clip=clip, video=video)
    source_key = video.storage_key
    preview_key = build_project_preview_key(user_id=str(project.user_id), project_id=str(project.id))

    if not source_key:
        project.project_json = mark_project_preview_failed(
            project.project_json,
            source_key=None,
            preview_key=preview_key,
            window=window,
            error="Source media is unavailable for editor preview",
        )
        await db.commit()
        await db.refresh(project)
        return project

    if not should_enqueue_project_preview(
        project_json=project.project_json,
        source_key=source_key,
        preview_key=preview_key,
        window=window,
        force=force,
    ):
        return project

    project.project_json = mark_project_preview_pending(
        project.project_json,
        source_key=source_key,
        preview_key=preview_key,
        window=window,
    )
    await db.commit()
    await db.refresh(project)

    try:
        from app.worker.tasks.editor_preview import generate_editor_project_preview_proxy_task

        generate_editor_project_preview_proxy_task.apply_async(
            args=[str(project.id)],
            countdown=1,
            queue="ingest",
        )
        logger.info(
            "[editor_project_preview_proxy_enqueued] project_id=%s video_id=%s source_key=%s offset=%s duration=%s",
            project.id,
            video.id,
            source_key,
            window.offset_sec,
            window.duration_sec,
        )
    except Exception as exc:
        project.project_json = mark_project_preview_failed(
            project.project_json,
            source_key=source_key,
            preview_key=preview_key,
            window=window,
            error=f"Failed to enqueue editor preview: {exc}",
        )
        await db.commit()
        await db.refresh(project)
        logger.warning("[editor_project_preview_proxy_failed] project_id=%s error=%s", project.id, exc)

    return project


async def _maybe_autocorrect_aspect_once(db: AsyncSession, project: EditorProject) -> EditorProject:
    payload = EditorProjectSchemaV1.model_validate(project.project_json)
    if payload.meta.aspect_auto_inferred_v1:
        return project

    video = await db.get(Video, project.video_id)
    inferred = infer_editor_aspect_ratio(video) if video else AspectRatio.square
    target_width, target_height = aspect_ratio_dimensions(inferred)

    payload.canvas.aspect_ratio = canvas_aspect_value(inferred)
    payload.canvas.width = target_width
    payload.canvas.height = target_height
    payload.canvas.safe_area_preset = safe_area_preset_for_aspect(inferred)
    payload.meta.aspect_auto_inferred_v1 = True

    project.aspect_ratio = inferred
    project.project_json = payload.model_dump(mode="json")
    project.revision = int(project.revision) + 1
    await db.commit()
    await db.refresh(project)
    return project


@router.post("/editor/projects/from-clip", response_model=EditorProjectFromClipResponse)
async def create_project_from_clip(
    body: EditorProjectCreateFromClipRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing_row = await db.execute(
        select(EditorProject.id)
        .where(
            EditorProject.user_id == current_user.id,
            EditorProject.clip_id == body.clip_id,
            EditorProject.status != EditorProjectStatus.archived,
        )
        .order_by(EditorProject.updated_at.desc())
        .limit(1)
    )
    existing_id = existing_row.scalars().first()
    if existing_id:
        return EditorProjectFromClipResponse(project_id=existing_id)

    row = await db.execute(
        select(Clip, Video)
        .join(Video, Clip.video_id == Video.id)
        .where(Clip.id == body.clip_id, Video.user_id == current_user.id)
    )
    result = row.first()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")

    clip, video = result
    if not video.storage_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source media is unavailable for this clip")

    transcript_rows = (
        (
            await db.execute(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.video_id == video.id,
                    TranscriptSegment.start_time < clip.end_time,
                    TranscriptSegment.end_time > clip.start_time,
                )
                .order_by(TranscriptSegment.start_time.asc())
            )
        )
        .scalars()
        .all()
    )

    aspect_ratio = body.aspect_ratio
    if aspect_ratio in (None, AspectRatio.original):
        aspect_ratio = infer_editor_aspect_ratio(video)

    payload = build_default_project_json(
        video=video,
        clip=clip,
        aspect_ratio=aspect_ratio,
        segments=transcript_rows,
    )

    project = EditorProject(
        user_id=current_user.id,
        video_id=video.id,
        clip_id=clip.id,
        name=(clip.title or video.title or "Clip Project")[:500],
        status=EditorProjectStatus.draft,
        aspect_ratio=aspect_ratio,
        trim_start_sec=float(clip.start_time),
        trim_end_sec=float(clip.end_time),
        project_json=payload.model_dump(mode="json"),
        revision=1,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    project = await _ensure_project_preview_proxy(db, project)
    return EditorProjectFromClipResponse(project_id=project.id)


@router.get("/editor/projects/{project_id}", response_model=EditorProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _project_or_404(db, project_id=project_id, user_id=current_user.id)
    project = await _maybe_autocorrect_aspect_once(db, project)
    project = await _ensure_project_preview_proxy(db, project)
    project = await _project_or_404(db, project_id=project.id, user_id=current_user.id)
    return await _project_response(db, project)


@router.post("/editor/projects/{project_id}/preview/regenerate", response_model=EditorProjectResponse)
async def regenerate_project_preview(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _project_or_404(db, project_id=project_id, user_id=current_user.id)
    project = await _ensure_project_preview_proxy(db, project, force=True)
    project = await _project_or_404(db, project_id=project.id, user_id=current_user.id)
    return await _project_response(db, project)


@router.patch("/editor/projects/{project_id}", response_model=EditorProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: EditorProjectPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _project_or_404(db, project_id=project_id, user_id=current_user.id)

    if body.revision is not None and int(body.revision) != int(project.revision):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project revision mismatch. Refresh and retry.",
        )

    if body.name is not None:
        project.name = (body.name or "").strip()[:500] or None
    if body.is_pinned is not None:
        project.is_pinned = bool(body.is_pinned)
    if body.aspect_ratio is not None and body.aspect_ratio != AspectRatio.original:
        project.aspect_ratio = body.aspect_ratio

    trim_start = body.trim_start_sec if body.trim_start_sec is not None else project.trim_start_sec
    trim_end = body.trim_end_sec if body.trim_end_sec is not None else project.trim_end_sec

    video = await db.get(Video, project.video_id)
    safe_start, safe_end = clamp_trim(
        start_sec=float(trim_start),
        end_sec=float(trim_end),
        source_duration_sec=float(video.duration_sec) if video and video.duration_sec else None,
    )
    project.trim_start_sec = safe_start
    project.trim_end_sec = safe_end

    if body.project_json is not None:
        project.project_json = preserve_project_preview_metadata(
            current_json=project.project_json,
            incoming_json=body.project_json.model_dump(mode="json"),
        )
    project.revision = int(project.revision) + 1

    await db.commit()
    await db.refresh(project)
    project = await _ensure_project_preview_proxy(db, project)
    project = await _project_or_404(db, project_id=project.id, user_id=current_user.id)
    return await _project_response(db, project)


@router.post("/editor/projects/{project_id}/assets", response_model=EditorAssetResponse)
async def upload_project_asset(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    asset_type: EditorAssetType = Form(default=EditorAssetType.image),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _project_or_404(db, project_id=project_id, user_id=current_user.id)

    raw = await file.read()
    size_bytes = len(raw)
    if size_bytes <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if size_bytes > MAX_EDITOR_ASSET_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Asset exceeds {MAX_EDITOR_ASSET_BYTES} bytes limit",
        )

    await enforce_storage_hard_stop(
        db,
        current_user.id,
        incoming_bytes=size_bytes,
        operation_label="asset upload",
    )

    width = None
    height = None
    if (file.content_type or "").lower().startswith("image/"):
        try:
            with Image.open(io.BytesIO(raw)) as image:
                width, height = image.size
        except Exception:
            width = None
            height = None

    asset_id = uuid.uuid4()
    ext = Path(file.filename or "asset.png").suffix or ".png"
    key = f"editor/{current_user.id}/{project.id}/assets/{asset_id}{ext}"
    r2_client.upload_fileobj(io.BytesIO(raw), key, content_type=file.content_type)

    asset = EditorAsset(
        id=asset_id,
        project_id=project.id,
        user_id=current_user.id,
        asset_type=asset_type,
        storage_key=key,
        original_filename=file.filename,
        mime_type=file.content_type,
        size_bytes=size_bytes,
        width=width,
        height=height,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return _asset_to_response(asset)


@router.delete("/editor/projects/{project_id}/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_asset(
    project_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = await _project_or_404(db, project_id=project_id, user_id=current_user.id)
    row = await db.execute(
        select(EditorAsset).where(
            EditorAsset.id == asset_id,
            EditorAsset.project_id == project_id,
            EditorAsset.user_id == current_user.id,
        )
    )
    asset = row.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Editor asset not found")

    try:
        r2_client.delete_file(asset.storage_key)
    except Exception as exc:
        logger.warning("[editor] failed to delete asset key=%s error=%s", asset.storage_key, exc)

    await db.delete(asset)
    await db.commit()


@router.post("/editor/projects/{project_id}/render", response_model=EditorRenderResponse)
async def create_project_render(
    project_id: uuid.UUID,
    body: EditorRenderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _project_or_404(db, project_id=project_id, user_id=current_user.id)
    await enforce_storage_hard_stop(
        db,
        current_user.id,
        incoming_bytes=0,
        operation_label="render",
    )

    export = Export(
        clip_id=project.clip_id,
        user_id=project.user_id,
        aspect_ratio=project.aspect_ratio,
        caption_style=None,
        caption_color_variant=None,
        caption_format=CaptionFormat.burned_in,
        status=ExportStatus.queued,
        error_message=None,
    )
    db.add(export)
    await db.flush()

    editor_render = EditorRender(
        project_id=project.id,
        user_id=current_user.id,
        export_id=export.id,
        preset=body.preset,
        status=EditorRenderStatus.queued,
    )
    project.status = EditorProjectStatus.rendering
    db.add(editor_render)
    await db.commit()
    await db.refresh(editor_render)

    try:
        from app.worker.tasks.editor_render import render_editor_project

        render_editor_project.apply_async(
            args=[str(editor_render.id)],
            countdown=1,
            queue="render",
        )
    except Exception as exc:
        editor_render.status = EditorRenderStatus.failed
        editor_render.error_message = f"Failed to enqueue render: {exc}"[:500]
        project.status = EditorProjectStatus.error
        await db.commit()

    return _render_to_response(editor_render)


@router.get("/editor/renders/{render_id}", response_model=EditorRenderResponse)
async def get_render(
    render_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await db.execute(
        select(EditorRender).where(
            EditorRender.id == render_id,
            EditorRender.user_id == current_user.id,
        )
    )
    render = row.scalar_one_or_none()
    if not render:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Editor render not found")
    return _render_to_response(render)


@router.post("/editor/projects/{project_id}/duplicate", response_model=EditorProjectDuplicateResponse)
async def duplicate_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _project_or_404(db, project_id=project_id, user_id=current_user.id)

    duplicate = EditorProject(
        user_id=project.user_id,
        video_id=project.video_id,
        clip_id=project.clip_id,
        name=(f"{project.name or 'Project'} (Copy)")[:500],
        status=EditorProjectStatus.draft,
        aspect_ratio=project.aspect_ratio,
        trim_start_sec=project.trim_start_sec,
        trim_end_sec=project.trim_end_sec,
        is_pinned=project.is_pinned,
        project_json=project.project_json,
        revision=1,
    )
    db.add(duplicate)
    await db.commit()
    await db.refresh(duplicate)
    return EditorProjectDuplicateResponse(project_id=duplicate.id)
