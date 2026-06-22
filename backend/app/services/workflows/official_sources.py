from __future__ import annotations

import logging
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import httpx
from sqlalchemy import select

from app.config import settings
from app.database import SyncSessionLocal
from app.models.clip import Clip, ClipStatus
from app.models.connected_account import ConnectedAccount, SocialPlatform
from app.models.export import AspectRatio, CaptionCadence, CaptionFormat, CaptionStyle, Export, ExportStatus
from app.models.job import Job, JobStatus
from app.models.publish_job import PublishJob, PublishMode, PublishStatus
from app.models.social_workflow import SocialWorkflow, SocialWorkflowCopyMode, SocialWorkflowStatus
from app.models.social_workflow_run import SocialWorkflowRun, SocialWorkflowRunStatus
from app.models.social_workflow_source_post import (
    SocialWorkflowSourcePost,
    SocialWorkflowSourceStatus,
    source_status_to_run_status,
)
from app.models.transcript import TranscriptSegment
from app.models.video import Video, VideoImportMode, VideoImportState, VideoSourceType, VideoStatus
from app.services.ai_copy import AICopyError, AICopyUnavailableError, generate_platform_copy, provider_configured
from app.services.crypto import decrypt_secret
from app.services.r2 import r2_client
from app.services.social.security import redact_url, sanitize_sensitive_text

logger = logging.getLogger(__name__)

INSTAGRAM_MEDIA_FIELDS = "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp"
INSTAGRAM_MEDIA_URL = "https://graph.instagram.com/me/media"
MAX_SOURCE_POSTS_PER_POLL = 25
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class InstagramSourceMedia:
    id: str
    media_type: str
    caption: str | None
    media_url: str | None
    permalink: str | None
    thumbnail_url: str | None
    timestamp: datetime | None
    raw: dict


def _parse_instagram_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iter_instagram_media(access_token: str) -> list[InstagramSourceMedia]:
    params = {
        "fields": INSTAGRAM_MEDIA_FIELDS,
        "limit": str(MAX_SOURCE_POSTS_PER_POLL),
        "access_token": access_token,
    }
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(INSTAGRAM_MEDIA_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"Instagram media poll failed: {sanitize_sensitive_text(exc)}") from exc

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []

    media: list[InstagramSourceMedia] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        media_id = str(item.get("id") or "").strip()
        if not media_id:
            continue
        media.append(
            InstagramSourceMedia(
                id=media_id,
                media_type=str(item.get("media_type") or "").strip().upper(),
                caption=str(item.get("caption") or "").strip() or None,
                media_url=redact_url(str(item.get("media_url") or "").strip()) if item.get("media_url") else None,
                permalink=str(item.get("permalink") or "").strip() or None,
                thumbnail_url=str(item.get("thumbnail_url") or "").strip() or None,
                timestamp=_parse_instagram_timestamp(item.get("timestamp")),
                raw={key: value for key, value in item.items() if key != "media_url"},
            )
        )
    return media


def _raw_media_url(raw_metadata: dict, access_token: str) -> str | None:
    # Re-fetch just before import so signed/temporary media URLs are not persisted.
    media_id = str(raw_metadata.get("id") or "").strip()
    if not media_id:
        return None
    params = {"fields": "id,media_type,media_url", "access_token": access_token}
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(f"https://graph.instagram.com/{media_id}", params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"Instagram media URL lookup failed: {sanitize_sensitive_text(exc)}") from exc
    if not isinstance(payload, dict):
        return None
    media_type = str(payload.get("media_type") or "").upper()
    if media_type != "VIDEO":
        return None
    media_url = payload.get("media_url")
    return str(media_url).strip() if isinstance(media_url, str) and media_url.strip() else None


def _sync_status(source_post: SocialWorkflowSourcePost, status: SocialWorkflowSourceStatus, error: str | None = None) -> None:
    source_post.status = status
    source_post.error_message = sanitize_sensitive_text(error) if error else None
    if source_post.workflow_run:
        source_post.workflow_run.status = source_status_to_run_status(status)
        source_post.workflow_run.error_message = source_post.error_message


def poll_instagram_workflow(workflow_id: str) -> dict:
    workflow_uuid = uuid.UUID(workflow_id)
    created = 0
    enqueued = 0
    new_source_ids: list[str] = []
    now = datetime.now(timezone.utc)

    with SyncSessionLocal() as db:
        workflow = db.execute(
            select(SocialWorkflow)
            .where(SocialWorkflow.id == workflow_uuid, SocialWorkflow.status == SocialWorkflowStatus.active)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if not workflow:
            return {"workflow_id": workflow_id, "created": 0, "enqueued": 0, "skipped": "inactive_or_locked"}

        account = db.get(ConnectedAccount, workflow.source_account_id) if workflow.source_account_id else None
        if not account or account.platform != SocialPlatform.instagram:
            workflow.last_error = "Reconnect the Instagram source account."
            workflow.last_polled_at = now
            db.commit()
            return {"workflow_id": workflow_id, "created": 0, "enqueued": 0, "error": workflow.last_error}

        try:
            access_token = decrypt_secret(account.access_token_encrypted)
            media_rows = _iter_instagram_media(access_token)
        except Exception as exc:
            workflow.last_error = sanitize_sensitive_text(exc)
            workflow.last_polled_at = now
            db.commit()
            logger.warning("[workflows] instagram poll failed workflow_id=%s error=%s", workflow_id, workflow.last_error)
            return {"workflow_id": workflow_id, "created": 0, "enqueued": 0, "error": workflow.last_error}

        watch_started_at = workflow.created_at
        if watch_started_at and watch_started_at.tzinfo is None:
            watch_started_at = watch_started_at.replace(tzinfo=timezone.utc)
        elif watch_started_at:
            watch_started_at = watch_started_at.astimezone(timezone.utc)
        for media in media_rows:
            if media.media_type != "VIDEO":
                continue
            if media.timestamp and watch_started_at and media.timestamp < watch_started_at:
                continue
            existing_source_id = db.execute(
                select(SocialWorkflowSourcePost.id).where(
                    SocialWorkflowSourcePost.workflow_id == workflow.id,
                    SocialWorkflowSourcePost.source_platform == SocialPlatform.instagram,
                    SocialWorkflowSourcePost.external_post_id == media.id,
                )
            ).scalar_one_or_none()
            if existing_source_id:
                continue
            source_post = SocialWorkflowSourcePost(
                user_id=workflow.user_id,
                workflow_id=workflow.id,
                source_account_id=workflow.source_account_id,
                source_platform=SocialPlatform.instagram,
                external_post_id=media.id,
                permalink=media.permalink,
                caption_snapshot=media.caption,
                thumbnail_url=media.thumbnail_url,
                published_at=media.timestamp,
                status=SocialWorkflowSourceStatus.detected,
                raw_metadata_json=media.raw,
            )
            run = SocialWorkflowRun(
                user_id=workflow.user_id,
                workflow_id=workflow.id,
                status=SocialWorkflowRunStatus.detected,
            )
            db.add(run)
            db.flush()
            source_post.workflow_run_id = run.id
            db.add(source_post)
            db.flush()
            created += 1
            new_source_ids.append(str(source_post.id))

        workflow.last_polled_at = now
        workflow.last_error = None
        db.commit()

    from app.worker.tasks.social_workflows import import_source_post_media

    for source_id in new_source_ids:
        import_source_post_media.apply_async(args=[source_id], queue="ingest")
        enqueued += 1

    return {"workflow_id": workflow_id, "created": created, "enqueued": enqueued}


def poll_active_official_source_workflows() -> dict:
    with SyncSessionLocal() as db:
        workflows = db.execute(
            select(SocialWorkflow.id)
            .where(
                SocialWorkflow.status == SocialWorkflowStatus.active,
                SocialWorkflow.source_platform == SocialPlatform.instagram,
            )
            .order_by(SocialWorkflow.last_polled_at.asc().nullsfirst(), SocialWorkflow.created_at.asc())
            .limit(50)
        ).scalars().all()

    from app.worker.tasks.social_workflows import poll_official_source_workflow

    task_ids: list[str] = []
    for workflow_id in workflows:
        task = poll_official_source_workflow.apply_async(args=[str(workflow_id)], queue="ingest")
        task_ids.append(task.id)
    return {"workflow_count": len(workflows), "task_ids": task_ids}


def _download_source_media(media_url: str, destination: Path) -> tuple[int, str | None]:
    max_bytes = int(settings.max_upload_size_mb) * 1024 * 1024
    bytes_written = 0
    content_type = None
    with httpx.Client(timeout=settings.ytdlp_timeout_seconds, follow_redirects=True) as client:
        with client.stream("GET", media_url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            if content_type and not any(kind in content_type.lower() for kind in ("video/", "octet-stream")):
                raise RuntimeError(f"Instagram media returned unsupported content type: {content_type}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as out:
                for chunk in response.iter_bytes(DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise RuntimeError("Instagram source media exceeded the configured upload size limit")
                    out.write(chunk)
    if bytes_written <= 0:
        raise RuntimeError("Instagram source media download was empty")
    return bytes_written, content_type


def import_instagram_source_post(source_post_id: str) -> dict:
    source_uuid = uuid.UUID(source_post_id)
    with SyncSessionLocal() as db:
        source_post = db.execute(
            select(SocialWorkflowSourcePost)
            .where(
                SocialWorkflowSourcePost.id == source_uuid,
                SocialWorkflowSourcePost.status == SocialWorkflowSourceStatus.detected,
            )
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if not source_post:
            return {"source_post_id": source_post_id, "skipped": "not_detected_or_locked"}
        workflow = db.get(SocialWorkflow, source_post.workflow_id)
        account = db.get(ConnectedAccount, source_post.source_account_id) if source_post.source_account_id else None
        raw_metadata = dict(source_post.raw_metadata_json or {"id": source_post.external_post_id})
        account_token_encrypted = account.access_token_encrypted if account else None
        workflow_present = workflow is not None
        _sync_status(source_post, SocialWorkflowSourceStatus.importing)
        db.commit()

    tmp_dir = Path(tempfile.mkdtemp(prefix="clipbandit-instagram-source-"))
    tmp_media = tmp_dir / "source.mp4"
    try:
        if not workflow_present or not account_token_encrypted:
            raise RuntimeError("Reconnect the Instagram source account before importing this post.")
        access_token = decrypt_secret(account_token_encrypted)
        media_url = _raw_media_url(raw_metadata, access_token)
        if not media_url:
            with SyncSessionLocal() as db:
                source_post = db.get(SocialWorkflowSourcePost, source_uuid)
                if source_post:
                    _sync_status(
                        source_post,
                        SocialWorkflowSourceStatus.original_required,
                        "Official Instagram API did not provide a reusable video file for this post.",
                    )
                    db.commit()
            return {"source_post_id": source_post_id, "status": "original_required"}

        size_bytes, content_type = _download_source_media(media_url, tmp_media)

        with SyncSessionLocal() as db:
            source_post = db.get(SocialWorkflowSourcePost, source_uuid)
            if not source_post:
                return {"source_post_id": source_post_id, "status": "missing"}
            video_id = uuid.uuid4()
            storage_key = f"videos/{source_post.user_id}/{video_id}/source/instagram.mp4"
            r2_client.upload_file(str(tmp_media), storage_key)
            title = (source_post.caption_snapshot or "Instagram source import").replace("\n", " ").strip()[:140]
            video = Video(
                id=video_id,
                user_id=source_post.user_id,
                title=title or "Instagram source import",
                source_type=VideoSourceType.instagram,
                source_url=source_post.permalink,
                thumbnail_url=source_post.thumbnail_url,
                import_state=VideoImportState.processing,
                import_mode=VideoImportMode.server_download,
                external_metadata_json={
                    "source_platform": "instagram",
                    "source_external_post_id": source_post.external_post_id,
                    "source_permalink": source_post.permalink,
                    "source_workflow_id": str(source_post.workflow_id),
                    "source_post_id": str(source_post.id),
                    "imported_from_official_api": True,
                    "content_type": content_type,
                },
                storage_key=storage_key,
                file_size_bytes=size_bytes,
                status=VideoStatus.transcribing,
            )
            db.add(video)
            job = Job(
                video_id=video.id,
                type="transcribe",
                payload={"source": "official_instagram_workflow", "source_post_id": str(source_post.id)},
                status=JobStatus.queued,
            )
            db.add(job)
            source_post.video_id = video.id
            _sync_status(source_post, SocialWorkflowSourceStatus.imported_processing)
            db.flush()
            video_id_str = str(video.id)
            job_id = job.id
            db.commit()

        from app.worker.tasks.transcribe import transcribe_job

        task = transcribe_job.apply_async(args=[video_id_str], queue="transcribe")
        with SyncSessionLocal() as db:
            job = db.get(Job, job_id)
            if job:
                job.celery_task_id = task.id
                db.commit()
        return {"source_post_id": source_post_id, "status": "imported_processing", "video_id": video_id_str}
    except Exception as exc:
        message = sanitize_sensitive_text(exc)
        logger.warning("[workflows] instagram source import failed source_post_id=%s error=%s", source_post_id, message)
        with SyncSessionLocal() as db:
            source_post = db.get(SocialWorkflowSourcePost, source_uuid)
            if source_post:
                _sync_status(source_post, SocialWorkflowSourceStatus.import_failed, message)
                db.commit()
        return {"source_post_id": source_post_id, "status": "import_failed", "error": message}
    finally:
        try:
            tmp_media.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass


def _ensure_full_video_export(db, source_post: SocialWorkflowSourcePost, video: Video) -> tuple[Export, bool]:
    duration = float(video.duration_sec or 0)
    if duration <= 0:
        duration = float(
            db.scalar(select(TranscriptSegment.end_time).where(TranscriptSegment.video_id == video.id).order_by(TranscriptSegment.end_time.desc()).limit(1))
            or 0
        )
    if duration <= 0:
        raise RuntimeError("Imported video duration is unavailable")

    clip = db.execute(
        select(Clip).where(Clip.video_id == video.id, Clip.start_time <= 0.01).order_by(Clip.duration_sec.desc().nullslast())
    ).scalars().first()
    if not clip or abs(float(clip.end_time) - duration) > 0.75:
        words = db.execute(
            select(TranscriptSegment.word)
            .where(TranscriptSegment.video_id == video.id)
            .order_by(TranscriptSegment.start_time.asc())
        ).scalars().all()
        clip = Clip(
            video_id=video.id,
            start_time=0.0,
            end_time=round(duration, 3),
            duration_sec=round(duration, 3),
            score=0.0,
            hook_score=0.0,
            energy_score=0.0,
            title="Workflow Source Video",
            transcript_text=" ".join([word for word in words if word])[:5000],
            status=ClipStatus.ready,
        )
        db.add(clip)
        db.flush()

    existing = db.execute(
        select(Export)
        .where(
            Export.user_id == video.user_id,
            Export.clip_id == clip.id,
            Export.aspect_ratio == AspectRatio.original,
            Export.caption_format == CaptionFormat.burned_in,
            Export.caption_cadence == CaptionCadence.split_line,
            Export.status.in_([ExportStatus.queued, ExportStatus.rendering, ExportStatus.ready]),
        )
        .order_by(Export.created_at.desc())
    ).scalars().first()
    if existing:
        return existing, False

    export = Export(
        user_id=video.user_id,
        clip_id=clip.id,
        aspect_ratio=AspectRatio.original,
        caption_style=CaptionStyle.clean_minimal,
        caption_format=CaptionFormat.burned_in,
        caption_cadence=CaptionCadence.split_line,
        caption_vertical_position=15.0,
        caption_scale=1.0,
        frame_anchor_x=0.5,
        frame_anchor_y=0.5,
        frame_zoom=1.0,
        status=ExportStatus.queued,
    )
    db.add(export)
    db.flush()
    return export, True


def _hashtags_from_caption(caption: str | None) -> list[str] | None:
    tags = []
    for part in (caption or "").split():
        if part.startswith("#") and len(part) > 1:
            tag = part.strip(".,;:!?()[]{}")
            if tag.lower() not in {item.lower() for item in tags}:
                tags.append(tag[:80])
    return tags or None


def _copy_for_destinations(source_post: SocialWorkflowSourcePost, workflow: SocialWorkflow, clip: Clip, platforms: list[str]) -> dict[str, dict]:
    source_caption = source_post.caption_snapshot or ""
    fallback = {
        platform: {
            "caption": source_caption or None,
            "title": (clip.title or "PostBandit repost")[:100],
            "description": source_caption or None,
            "hashtags": _hashtags_from_caption(source_caption),
        }
        for platform in platforms
    }
    if workflow.copy_mode == SocialWorkflowCopyMode.reuse_source:
        return fallback
    if not provider_configured() or not clip.transcript_text:
        return fallback
    try:
        generated = generate_platform_copy(
            clip.transcript_text,
            platforms,
            video_title=clip.title,
            topic_hint="Repurpose this source post for each destination platform.",
        )
    except (AICopyError, AICopyUnavailableError) as exc:
        logger.warning("[workflows] platform copy unavailable source_post_id=%s error=%s", source_post.id, sanitize_sensitive_text(exc))
        return fallback
    merged = dict(fallback)
    for platform, value in generated.results.items():
        if isinstance(value, dict):
            merged[platform] = {
                "title": value.get("title") or fallback.get(platform, {}).get("title"),
                "caption": value.get("caption") or fallback.get(platform, {}).get("caption"),
                "description": value.get("description") or fallback.get(platform, {}).get("description"),
                "hashtags": value.get("hashtags") or fallback.get(platform, {}).get("hashtags"),
            }
    return merged


def _create_publish_jobs(db, source_post: SocialWorkflowSourcePost, workflow: SocialWorkflow, export: Export) -> list[str]:
    clip = db.get(Clip, export.clip_id)
    if not clip:
        raise RuntimeError("Workflow export clip is missing")
    targets = workflow.destination_targets_json or []
    platforms = [str(target.get("platform")) for target in targets if target.get("platform")]
    copy_by_platform = _copy_for_destinations(source_post, workflow, clip, platforms)
    created_job_ids: list[str] = []

    for target in targets:
        account_id_raw = target.get("connected_account_id")
        platform_raw = target.get("platform")
        if not account_id_raw or not platform_raw:
            continue
        try:
            account_id = uuid.UUID(str(account_id_raw))
            platform = SocialPlatform(str(platform_raw))
        except ValueError:
            continue
        account = db.get(ConnectedAccount, account_id)
        if not account or account.user_id != workflow.user_id or account.platform != platform:
            continue
        existing = db.execute(
            select(PublishJob.id).where(
                PublishJob.workflow_source_post_id == source_post.id,
                PublishJob.connected_account_id == account.id,
            )
        ).scalar_one_or_none()
        if existing:
            created_job_ids.append(str(existing))
            continue
        copy = copy_by_platform.get(platform.value, {})
        job = PublishJob(
            user_id=workflow.user_id,
            export_id=export.id,
            clip_id=clip.id,
            platform=platform,
            connected_account_id=account.id,
            workflow_source_post_id=source_post.id,
            status=PublishStatus.queued,
            publish_mode=PublishMode.now,
            caption=copy.get("caption"),
            title=copy.get("title"),
            description=copy.get("description"),
            hashtags=copy.get("hashtags"),
            destination_display_name=account.display_name or account.username_or_channel_name or account.external_account_id,
            content_title_snapshot=copy.get("title") or clip.title or source_post.caption_snapshot or "Workflow repost",
            provider_metadata_json={
                "workflow_id": str(workflow.id),
                "workflow_source_post_id": str(source_post.id),
                "source_platform": source_post.source_platform.value,
                "source_external_post_id": source_post.external_post_id,
            },
        )
        db.add(job)
        db.flush()
        created_job_ids.append(str(job.id))
    return created_job_ids


def continue_ready_official_source_workflows() -> dict:
    progressed = 0
    published = 0
    finalized = 0
    jobs_to_enqueue: list[str] = []
    exports_to_render: list[str] = []
    with SyncSessionLocal() as db:
        processing_posts = db.execute(
            select(SocialWorkflowSourcePost)
            .where(SocialWorkflowSourcePost.status == SocialWorkflowSourceStatus.imported_processing)
            .with_for_update(skip_locked=True)
            .limit(50)
        ).scalars().all()
        for source_post in processing_posts:
            video = db.get(Video, source_post.video_id) if source_post.video_id else None
            if not video:
                continue
            if video.status == VideoStatus.error:
                _sync_status(source_post, SocialWorkflowSourceStatus.import_failed, video.error_message or "Imported video processing failed")
                progressed += 1
                continue
            if video.status != VideoStatus.ready:
                continue
            export, should_render = _ensure_full_video_export(db, source_post, video)
            source_post.export_id = export.id
            if should_render:
                exports_to_render.append(str(export.id))
            _sync_status(source_post, SocialWorkflowSourceStatus.ready_to_publish)
            progressed += 1
        db.commit()

        if exports_to_render:
            from app.worker.tasks.render import render_export

            for export_id in exports_to_render:
                render_export.apply_async(args=[export_id], queue="render")

        ready_posts = db.execute(
            select(SocialWorkflowSourcePost)
            .where(SocialWorkflowSourcePost.status == SocialWorkflowSourceStatus.ready_to_publish)
            .with_for_update(skip_locked=True)
            .limit(50)
        ).scalars().all()
        for source_post in ready_posts:
            workflow = db.get(SocialWorkflow, source_post.workflow_id)
            export = db.get(Export, source_post.export_id) if source_post.export_id else None
            if not workflow or not export:
                continue
            if export.status == ExportStatus.error:
                _sync_status(source_post, SocialWorkflowSourceStatus.import_failed, export.error_message or "Workflow export failed")
                continue
            if export.status != ExportStatus.ready:
                continue
            if not workflow.auto_publish:
                continue
            job_ids = _create_publish_jobs(db, source_post, workflow, export)
            jobs_to_enqueue.extend(job_ids)
            _sync_status(source_post, SocialWorkflowSourceStatus.publishing)
            if source_post.workflow_run:
                source_post.workflow_run.publish_job_ids_json = job_ids
            published += len(job_ids)
        db.commit()

        if jobs_to_enqueue:
            from app.worker.tasks.publish import execute_publish_job

            for job_id in jobs_to_enqueue:
                execute_publish_job.apply_async(args=[job_id], queue="publish")

        publishing_posts = db.execute(
            select(SocialWorkflowSourcePost)
            .where(SocialWorkflowSourcePost.status == SocialWorkflowSourceStatus.publishing)
            .limit(50)
        ).scalars().all()
        for source_post in publishing_posts:
            jobs = db.execute(select(PublishJob).where(PublishJob.workflow_source_post_id == source_post.id)).scalars().all()
            if not jobs:
                continue
            terminal = {PublishStatus.published, PublishStatus.failed, PublishStatus.waiting_user_action, PublishStatus.provider_not_configured, PublishStatus.cancelled}
            if any(job.status not in terminal for job in jobs):
                continue
            all_published = all(job.status == PublishStatus.published for job in jobs)
            _sync_status(source_post, SocialWorkflowSourceStatus.completed if all_published else SocialWorkflowSourceStatus.partial_failed)
            if source_post.workflow_run:
                source_post.workflow_run.destination_results_json = {
                    str(job.id): {
                        "platform": job.platform.value,
                        "status": job.status.value,
                        "external_post_url": job.external_post_url,
                        "error_message": job.error_message,
                    }
                    for job in jobs
                }
            finalized += 1
        db.commit()

    return {"progressed": progressed, "publish_jobs_dispatched": published, "finalized": finalized}
