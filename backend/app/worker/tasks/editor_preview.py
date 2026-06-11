from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.models.clip import Clip
from app.models.editor_project import EditorProject
from app.models.video import Video
from app.services.editor_project_preview import (
    build_project_preview_key,
    generate_project_preview_proxy,
    mark_project_preview_failed,
    mark_project_preview_pending,
    mark_project_preview_ready,
    resolve_project_preview_window,
)
from app.services.editor_preview import (
    mark_editor_preview_failed,
    mark_editor_preview_pending,
    mark_editor_preview_ready,
    generate_editor_preview_proxy,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.worker.tasks.editor_preview.generate_editor_preview_proxy_task",
    bind=True,
    queue="ingest",
    max_retries=0,
)
def generate_editor_preview_proxy_task(self, video_id: str):
    try:
        video_uuid = uuid.UUID(video_id)
    except ValueError:
        logger.error("[editor_preview_proxy_failed] invalid_video_id=%s", video_id)
        return {"status": "failed", "reason": "invalid_video_id"}

    with SyncSessionLocal() as db:
        video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
        if not video:
            logger.warning("[editor_preview_proxy_failed] video_not_found video_id=%s", video_id)
            return {"status": "failed", "reason": "video_not_found"}
        if not video.storage_key:
            logger.warning("[editor_preview_proxy_failed] source_missing video_id=%s", video_id)
            video.external_metadata_json = mark_editor_preview_failed(
                video.external_metadata_json,
                source_key="",
                error="Source storage key is missing",
            )
            db.commit()
            return {"status": "failed", "reason": "source_missing"}

        source_key = video.storage_key
        video.external_metadata_json = mark_editor_preview_pending(
            video.external_metadata_json,
            source_key=source_key,
        )
        db.commit()

    try:
        result = generate_editor_preview_proxy(video_id=video_id, source_key=source_key)
    except Exception as exc:
        message = str(exc)[:1000]
        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if video:
                video.external_metadata_json = mark_editor_preview_failed(
                    video.external_metadata_json,
                    source_key=video.storage_key or source_key,
                    error=message,
                )
                db.commit()
        logger.exception("[editor_preview_proxy_failed] video_id=%s error=%s", video_id, exc)
        return {"status": "failed", "reason": message}

    with SyncSessionLocal() as db:
        video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
        if not video:
            return {"status": "failed", "reason": "video_deleted_during_render"}
        video.external_metadata_json = mark_editor_preview_ready(
            video.external_metadata_json,
            source_key=video.storage_key or source_key,
            preview_key=result.preview_key,
        )
        video.updated_at = datetime.now(timezone.utc)
        db.commit()

    logger.info(
        "[editor_preview_proxy_succeeded] video_id=%s used_proxy=%s preview_key=%s source_profile=%s",
        video_id,
        result.used_proxy,
        result.preview_key,
        result.source_profile,
    )
    return {
        "status": "completed",
        "video_id": video_id,
        "used_proxy": result.used_proxy,
        "preview_key": result.preview_key,
    }


@celery_app.task(
    name="app.worker.tasks.editor_preview.generate_editor_project_preview_proxy_task",
    bind=True,
    queue="ingest",
    max_retries=0,
)
def generate_editor_project_preview_proxy_task(self, project_id: str):
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        logger.error("[editor_project_preview_proxy_failed] invalid_project_id=%s", project_id)
        return {"status": "failed", "reason": "invalid_project_id"}

    with SyncSessionLocal() as db:
        row = (
            db.execute(
                select(EditorProject, Clip, Video)
                .join(Clip, EditorProject.clip_id == Clip.id)
                .join(Video, EditorProject.video_id == Video.id)
                .where(EditorProject.id == project_uuid)
            )
            .first()
        )
        if not row:
            logger.warning("[editor_project_preview_proxy_failed] project_not_found project_id=%s", project_id)
            return {"status": "failed", "reason": "project_not_found"}

        project, clip, video = row
        if not video.storage_key:
            window = resolve_project_preview_window(project=project, clip=clip, video=video)
            project.project_json = mark_project_preview_failed(
                project.project_json,
                source_key=None,
                preview_key=None,
                window=window,
                error="Source storage key is missing",
            )
            db.commit()
            return {"status": "failed", "reason": "source_missing"}

        source_key = video.storage_key
        window = resolve_project_preview_window(project=project, clip=clip, video=video)
        user_id_str = str(project.user_id)
        preview_key = build_project_preview_key(user_id=user_id_str, project_id=str(project.id))
        project.project_json = mark_project_preview_pending(
            project.project_json,
            source_key=source_key,
            preview_key=preview_key,
            window=window,
        )
        project.updated_at = datetime.now(timezone.utc)
        db.commit()

    try:
        result = generate_project_preview_proxy(
            project_id=project_id,
            user_id=user_id_str,
            source_key=source_key,
            window=window,
        )
    except Exception as exc:
        message = str(exc)[:1000]
        with SyncSessionLocal() as db:
            project = db.execute(select(EditorProject).where(EditorProject.id == project_uuid)).scalars().first()
            if project:
                project.project_json = mark_project_preview_failed(
                    project.project_json,
                    source_key=source_key,
                    preview_key=preview_key,
                    window=window,
                    error=message,
                )
                project.updated_at = datetime.now(timezone.utc)
                db.commit()
        logger.exception("[editor_project_preview_proxy_failed] project_id=%s error=%s", project_id, exc)
        return {"status": "failed", "reason": message}

    with SyncSessionLocal() as db:
        project = db.execute(select(EditorProject).where(EditorProject.id == project_uuid)).scalars().first()
        if not project:
            return {"status": "failed", "reason": "project_deleted_during_render"}
        project.project_json = mark_project_preview_ready(
            project.project_json,
            source_key=source_key,
            preview_key=result.preview_key,
            window=window,
        )
        project.updated_at = datetime.now(timezone.utc)
        db.commit()

    logger.info(
        "[editor_project_preview_proxy_succeeded] project_id=%s preview_key=%s source_profile=%s offset=%s duration=%s",
        project_id,
        result.preview_key,
        result.source_profile,
        result.offset_sec,
        result.duration_sec,
    )
    return {
        "status": "completed",
        "project_id": project_id,
        "preview_key": result.preview_key,
        "offset_sec": result.offset_sec,
        "duration_sec": result.duration_sec,
    }
