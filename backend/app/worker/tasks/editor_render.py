from __future__ import annotations

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.celery_app import celery_app
from app.config import settings
from app.database import SyncSessionLocal
from app.models.editor_asset import EditorAsset
from app.models.editor_project import EditorProject, EditorProjectStatus
from app.models.editor_render import EditorRender, EditorRenderStatus
from app.models.export import (
    AspectRatio,
    CaptionColorVariant,
    CaptionFormat,
    CaptionStyle,
    Export,
    ExportStatus,
)
from app.models.video import Video
from app.schemas.editor import EditorProjectSchemaV1
from app.services.editor_rendering import build_editor_ffmpeg_command, run_editor_render
from app.services.r2 import r2_client
from app.services.storage import export_video_key
from app.services.workspace import finalize_workspace, heartbeat_workspace, start_workspace

logger = logging.getLogger(__name__)


class EditorRenderError(Exception):
    pass


def _target_dimensions(aspect_ratio: AspectRatio) -> tuple[int, int]:
    if aspect_ratio == AspectRatio.square:
        return 720, 720
    if aspect_ratio == AspectRatio.landscape:
        return 1280, 720
    return 720, 1280


@celery_app.task(name="app.worker.tasks.editor_render.render_editor_project", bind=True, queue="render", max_retries=0)
def render_editor_project(self, editor_render_id: str):
    try:
        render_uuid = uuid.UUID(editor_render_id)
    except ValueError:
        logger.error("[editor_render] invalid editor_render_id=%s", editor_render_id)
        return {"status": "error", "message": "invalid editor render id"}

    workspace = start_workspace(
        job_type="render",
        workspace_key=f"editor-{editor_render_id}",
        refs={"editor_render_id": editor_render_id},
    )

    source_path = workspace.path / "source.mp4"
    output_path = workspace.path / "output.mp4"
    asset_dir = workspace.path / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)

    try:
        with SyncSessionLocal() as db:
            row = db.execute(
                select(EditorRender, EditorProject, Video)
                .join(EditorProject, EditorRender.project_id == EditorProject.id)
                .join(Video, EditorProject.video_id == Video.id)
                .where(EditorRender.id == render_uuid)
            ).first()
            if not row:
                raise EditorRenderError("Editor render not found")

            editor_render, project, video = row
            export: Export | None = None
            if editor_render.export_id:
                export = db.execute(select(Export).where(Export.id == editor_render.export_id)).scalars().first()

            editor_render.status = EditorRenderStatus.processing
            editor_render.started_at = datetime.now(timezone.utc)
            editor_render.error_message = None
            project.status = EditorProjectStatus.rendering
            if export:
                export.status = ExportStatus.rendering
                export.error_message = None
            db.commit()

            if not video.storage_key:
                raise EditorRenderError("Source media is unavailable for this project")

            r2_client.download_file(video.storage_key, str(source_path))
            heartbeat_workspace(workspace)

            project_payload = EditorProjectSchemaV1.model_validate(project.project_json)

            trim_start = float(project_payload.trim.start_sec)
            trim_end = float(project_payload.trim.end_sec)
            if trim_end <= trim_start:
                raise EditorRenderError("Invalid trim range in project")

            target_width, target_height = _target_dimensions(project.aspect_ratio)

            image_inputs: list[tuple] = []
            image_overlays = [overlay for overlay in project_payload.overlays if overlay.type == "image" and overlay.asset_id]
            for input_offset, overlay in enumerate(image_overlays, start=1):
                try:
                    asset_uuid = uuid.UUID(str(overlay.asset_id))
                except ValueError:
                    continue
                asset = db.execute(
                    select(EditorAsset).where(
                        EditorAsset.id == asset_uuid,
                        EditorAsset.project_id == project.id,
                        EditorAsset.user_id == project.user_id,
                    )
                ).scalars().first()
                if not asset:
                    continue
                if not r2_client.file_exists(asset.storage_key):
                    continue
                ext = Path(asset.original_filename or "asset.png").suffix or ".png"
                local_path = asset_dir / f"{asset.id}{ext}"
                r2_client.download_file(asset.storage_key, str(local_path))
                image_inputs.append((overlay, str(local_path), input_offset))

            cmd = build_editor_ffmpeg_command(
                source_path=str(source_path),
                output_path=str(output_path),
                project=project_payload,
                trim_start_sec=trim_start,
                trim_end_sec=trim_end,
                target_width=target_width,
                target_height=target_height,
                image_inputs=image_inputs,
            )

            command_debug, output_size = run_editor_render(
                cmd,
                timeout_seconds=max(60, int(settings.carousel_render_timeout_seconds) * 2),
            )

            if export is None:
                export = Export(
                    clip_id=project.clip_id,
                    user_id=project.user_id,
                    aspect_ratio=project.aspect_ratio,
                    caption_style=CaptionStyle.clean_minimal,
                    caption_color_variant=CaptionColorVariant.classic,
                    caption_format=CaptionFormat.burned_in,
                    status=ExportStatus.queued,
                )
                db.add(export)
                db.flush()
                editor_render.export_id = export.id

            output_key = export_video_key(
                str(project.user_id),
                str(project.clip_id),
                str(export.id),
                project.aspect_ratio.value,
            )
            r2_client.upload_file(str(output_path), output_key)

            editor_render.output_storage_key = output_key
            editor_render.output_size_bytes = int(output_size)
            editor_render.ffmpeg_command_debug = command_debug[:2000]
            editor_render.status = EditorRenderStatus.completed
            editor_render.completed_at = datetime.now(timezone.utc)
            editor_render.error_message = None

            project.status = EditorProjectStatus.ready
            project.last_render_id = editor_render.id

            export.storage_key = output_key
            export.srt_key = None
            export.download_url = None
            export.url_expires_at = None
            export.status = ExportStatus.ready
            export.error_message = None
            export.render_time_sec = max(1, int((editor_render.completed_at - editor_render.started_at).total_seconds()))

            db.commit()
            finalize_workspace(workspace, state="terminal_success")
            return {"status": "completed", "editor_render_id": str(editor_render.id), "export_id": str(export.id)}

    except Exception as exc:
        logger.exception("[editor_render] failed editor_render_id=%s error=%s", editor_render_id, exc)
        with SyncSessionLocal() as db:
            row = db.execute(
                select(EditorRender, EditorProject, Export)
                .join(EditorProject, EditorRender.project_id == EditorProject.id)
                .outerjoin(Export, EditorRender.export_id == Export.id)
                .where(EditorRender.id == render_uuid)
            ).first()
            if row:
                editor_render, project, export = row
                editor_render.status = EditorRenderStatus.failed
                editor_render.error_message = str(exc)[:2000]
                editor_render.completed_at = datetime.now(timezone.utc)
                project.status = EditorProjectStatus.error
                if export:
                    export.status = ExportStatus.error
                    export.error_message = str(exc)[:2000]
                db.commit()
        finalize_workspace(workspace, state="terminal_failed", metadata={"error": str(exc)[:2000]})
        return {"status": "failed", "message": str(exc)[:2000]}
    finally:
        shutil.rmtree(workspace.path, ignore_errors=True)
