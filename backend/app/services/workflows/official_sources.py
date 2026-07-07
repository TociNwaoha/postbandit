from __future__ import annotations

import logging
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
from sqlalchemy import func, select

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
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.ffmpeg import extract_thumbnail
from app.services.object_storage import object_storage_client
from app.services.social.instagram import ensure_instagram_account_token
from app.services.social.meta import GraphRequestError, graph_get
from app.services.social.security import redact_url, sanitize_sensitive_text
from app.services.storage import clip_thumbnail_key

logger = logging.getLogger(__name__)

INSTAGRAM_MEDIA_FIELDS = "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp"
INSTAGRAM_MEDIA_URL = "https://graph.instagram.com/me/media"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
FACEBOOK_VIDEO_FIELDS = "id,title,description,permalink_url,picture,created_time,source"
MAX_SOURCE_POSTS_PER_POLL = 25
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
WORKFLOW_SOURCE_PLACEHOLDER_TITLE = "Workflow Source Video"


@dataclass(frozen=True)
class OfficialSourceMedia:
    platform: SocialPlatform
    id: str
    media_type: str
    caption: str | None
    title: str | None
    media_url: str | None
    permalink: str | None
    thumbnail_url: str | None
    timestamp: datetime | None
    raw: dict


def _parse_iso_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    # Meta timestamps commonly use +0000 offsets, while datetime.fromisoformat
    # expects +00:00. Normalize only the compact timezone suffix.
    if len(text) >= 5 and text[-5] in {"+", "-"} and text[-2] != ":":
        text = f"{text[:-2]}:{text[-2:]}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_instagram_timestamp(value: object) -> datetime | None:
    return _parse_iso_timestamp(value)


def _parse_youtube_timestamp(value: object) -> datetime | None:
    return _parse_iso_timestamp(value)


def _parse_facebook_timestamp(value: object) -> datetime | None:
    return _parse_iso_timestamp(value)


def _iter_instagram_media(access_token: str) -> list[OfficialSourceMedia]:
    params = {
        "fields": INSTAGRAM_MEDIA_FIELDS,
        "limit": str(MAX_SOURCE_POSTS_PER_POLL),
        "access_token": access_token,
    }
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(INSTAGRAM_MEDIA_URL, params=params)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = sanitize_sensitive_text(response.text)
                raise RuntimeError(f"Instagram media poll failed: HTTP {response.status_code}: {body}") from exc
            payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"Instagram media poll failed: {sanitize_sensitive_text(exc)}") from exc

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []

    media: list[OfficialSourceMedia] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        media_id = str(item.get("id") or "").strip()
        if not media_id:
            continue
        media.append(
            OfficialSourceMedia(
                platform=SocialPlatform.instagram,
                id=media_id,
                media_type=str(item.get("media_type") or "").strip().upper(),
                caption=str(item.get("caption") or "").strip() or None,
                title=None,
                media_url=redact_url(str(item.get("media_url") or "").strip()) if item.get("media_url") else None,
                permalink=str(item.get("permalink") or "").strip() or None,
                thumbnail_url=str(item.get("thumbnail_url") or "").strip() or None,
                timestamp=_parse_instagram_timestamp(item.get("timestamp")),
                raw={key: value for key, value in item.items() if key != "media_url"},
            )
        )
    return media


def _youtube_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _refresh_youtube_access_token(account: ConnectedAccount) -> str:
    access_token = decrypt_secret(account.access_token_encrypted)
    expires_at = account.token_expires_at
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)
    if not expires_at or expires_at > datetime.now(timezone.utc) + timedelta(seconds=90):
        return access_token
    if not account.refresh_token_encrypted:
        return access_token

    refresh_token = decrypt_secret(account.refresh_token_encrypted)
    with httpx.Client(timeout=30) as client:
        response = client.post(
            YOUTUBE_TOKEN_URL,
            data={
                "client_id": settings.youtube_client_id,
                "client_secret": settings.youtube_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        payload = response.json()
    token = str(payload.get("access_token") or "").strip()
    if not token:
        return access_token
    account.access_token_encrypted = encrypt_secret(token)
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)):
        account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    return token


def _youtube_uploads_playlist_id(account: ConnectedAccount, access_token: str) -> str | None:
    metadata = account.metadata_json or {}
    channel = metadata.get("channel") if isinstance(metadata, dict) else None
    content_details = channel.get("contentDetails") if isinstance(channel, dict) else None
    related = content_details.get("relatedPlaylists") if isinstance(content_details, dict) else None
    uploads = related.get("uploads") if isinstance(related, dict) else None
    if isinstance(uploads, str) and uploads.strip():
        return uploads.strip()

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(
            YOUTUBE_CHANNELS_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"part": "id,snippet,contentDetails", "mine": "true"},
        )
        response.raise_for_status()
        payload = response.json()
    item = ((payload.get("items") if isinstance(payload, dict) else None) or [None])[0]
    if not isinstance(item, dict):
        return None
    account.metadata_json = {**metadata, "channel": item}
    content_details = item.get("contentDetails") if isinstance(item.get("contentDetails"), dict) else {}
    related = content_details.get("relatedPlaylists") if isinstance(content_details.get("relatedPlaylists"), dict) else {}
    uploads = related.get("uploads")
    return str(uploads).strip() if isinstance(uploads, str) and uploads.strip() else None


def _iter_youtube_uploads(account: ConnectedAccount) -> list[OfficialSourceMedia]:
    try:
        access_token = _refresh_youtube_access_token(account)
        uploads_playlist_id = _youtube_uploads_playlist_id(account, access_token)
        if not uploads_playlist_id:
            return []
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(
                YOUTUBE_PLAYLIST_ITEMS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "part": "snippet,contentDetails",
                    "playlistId": uploads_playlist_id,
                    "maxResults": str(MAX_SOURCE_POSTS_PER_POLL),
                },
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"YouTube uploads poll failed: {sanitize_sensitive_text(exc)}") from exc

    rows = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []

    media: list[OfficialSourceMedia] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        content = item.get("contentDetails") if isinstance(item.get("contentDetails"), dict) else {}
        resource_id = snippet.get("resourceId") if isinstance(snippet.get("resourceId"), dict) else {}
        video_id = str(content.get("videoId") or resource_id.get("videoId") or "").strip()
        if not video_id:
            continue
        thumbnails = snippet.get("thumbnails") if isinstance(snippet.get("thumbnails"), dict) else {}
        thumbnail_url = None
        for key in ("maxres", "standard", "high", "medium", "default"):
            thumb = thumbnails.get(key)
            if isinstance(thumb, dict) and thumb.get("url"):
                thumbnail_url = str(thumb["url"])
                break
        title = str(snippet.get("title") or "").strip() or None
        description = str(snippet.get("description") or "").strip() or None
        media.append(
            OfficialSourceMedia(
                platform=SocialPlatform.youtube,
                id=video_id,
                media_type="VIDEO",
                caption=description,
                title=title,
                media_url=None,
                permalink=_youtube_video_url(video_id),
                thumbnail_url=thumbnail_url,
                timestamp=_parse_youtube_timestamp(content.get("videoPublishedAt") or snippet.get("publishedAt")),
                raw={
                    "id": video_id,
                    "title": title,
                    "description": description,
                    "playlist_item_id": item.get("id"),
                    "publishedAt": content.get("videoPublishedAt") or snippet.get("publishedAt"),
                    "uploads_playlist_id": uploads_playlist_id,
                },
            )
        )
    return media


def _graph_base() -> str:
    return f"https://graph.facebook.com/{settings.meta_graph_api_version}"


def _iter_facebook_page_videos(account: ConnectedAccount) -> list[OfficialSourceMedia]:
    access_token = decrypt_secret(account.access_token_encrypted)
    page_id = str(account.external_account_id or "").strip()
    if not page_id:
        return []
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            payload = graph_get(
                client,
                url=f"{_graph_base()}/{page_id}/videos",
                params={
                    "fields": FACEBOOK_VIDEO_FIELDS,
                    "limit": str(MAX_SOURCE_POSTS_PER_POLL),
                    "access_token": access_token,
                },
            )
    except GraphRequestError as exc:
        raise RuntimeError(f"Facebook Page video poll failed: {sanitize_sensitive_text(exc)}") from exc

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []

    media: list[OfficialSourceMedia] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        video_id = str(item.get("id") or "").strip()
        if not video_id:
            continue
        title = str(item.get("title") or "").strip() or None
        description = str(item.get("description") or "").strip() or None
        media.append(
            OfficialSourceMedia(
                platform=SocialPlatform.facebook,
                id=video_id,
                media_type="VIDEO",
                caption=description,
                title=title,
                media_url=redact_url(str(item.get("source") or "").strip()) if item.get("source") else None,
                permalink=str(item.get("permalink_url") or "").strip() or None,
                thumbnail_url=str(item.get("picture") or "").strip() or None,
                timestamp=_parse_facebook_timestamp(item.get("created_time")),
                raw={key: value for key, value in item.items() if key != "source"},
            )
        )
    return media


def _iter_source_media(workflow: SocialWorkflow, account: ConnectedAccount) -> list[OfficialSourceMedia]:
    if workflow.source_platform == SocialPlatform.instagram:
        access_token = ensure_instagram_account_token(account)
        return _iter_instagram_media(access_token)
    if workflow.source_platform == SocialPlatform.youtube:
        return _iter_youtube_uploads(account)
    if workflow.source_platform == SocialPlatform.facebook:
        return _iter_facebook_page_videos(account)
    raise RuntimeError(f"{workflow.source_platform.value} source workflows are not enabled")


def _source_account_error(platform: SocialPlatform) -> str:
    if platform == SocialPlatform.instagram:
        return "Reconnect the Instagram source account."
    if platform == SocialPlatform.youtube:
        return "Reconnect the YouTube source account with readonly permissions."
    if platform == SocialPlatform.facebook:
        return "Reconnect the Facebook Page source account with video read permissions."
    return f"Reconnect the {platform.value} source account."


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


def _resolve_workflow_source_account(db, workflow: SocialWorkflow) -> ConnectedAccount | None:
    account = db.get(ConnectedAccount, workflow.source_account_id) if workflow.source_account_id else None
    if account and _is_valid_workflow_source_account(account, workflow.source_platform):
        return account

    candidates = [
        candidate
        for candidate in db.execute(
            select(ConnectedAccount)
            .where(
                ConnectedAccount.user_id == workflow.user_id,
                ConnectedAccount.platform == workflow.source_platform,
            )
            .order_by(ConnectedAccount.updated_at.desc())
        ).scalars()
        if _is_valid_workflow_source_account(candidate, workflow.source_platform)
    ]
    if len(candidates) != 1:
        return None

    workflow.source_account_id = candidates[0].id
    if workflow.last_error and is_reconnect_required_source_error(workflow.last_error):
        workflow.last_error = None
    db.flush()
    return candidates[0]


def is_reconnect_required_source_error(error: object) -> bool:
    normalized = str(error or "").lower()
    reconnect_markers = (
        "session has expired",
        "error validating access token",
        "oauth exception",
        "oauthexception",
        "invalid oauth",
        "token has expired",
        "expired token",
        "code 190",
        "reconnect required",
        "reconnect the",
        "refresh token is unavailable",
    )
    if any(marker in normalized for marker in reconnect_markers):
        return True
    return "190" in normalized and ("oauth" in normalized or "access token" in normalized)


def reconnect_required_source_message(platform: SocialPlatform) -> str:
    return _source_account_error(platform)


def source_poll_error_message(platform: SocialPlatform, error: object) -> str:
    sanitized = sanitize_sensitive_text(error)
    if is_reconnect_required_source_error(sanitized):
        return reconnect_required_source_message(platform)
    return sanitized


def _raw_instagram_media_url(raw_metadata: dict, access_token: str) -> str | None:
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


def _raw_facebook_media_url(raw_metadata: dict, access_token: str) -> str | None:
    # Re-fetch just before import so signed/temporary media URLs are not persisted.
    video_id = str(raw_metadata.get("id") or "").strip()
    if not video_id:
        return None
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            payload = graph_get(
                client,
                url=f"{_graph_base()}/{video_id}",
                params={"fields": "id,source", "access_token": access_token},
            )
    except GraphRequestError as exc:
        raise RuntimeError(f"Facebook media URL lookup failed: {sanitize_sensitive_text(exc)}") from exc
    media_url = payload.get("source") if isinstance(payload, dict) else None
    return str(media_url).strip() if isinstance(media_url, str) and media_url.strip() else None


def _sync_status(source_post: SocialWorkflowSourcePost, status: SocialWorkflowSourceStatus, error: str | None = None) -> None:
    source_post.status = status
    source_post.error_message = sanitize_sensitive_text(error) if error else None
    if source_post.workflow_run:
        source_post.workflow_run.status = source_status_to_run_status(status)
        source_post.workflow_run.error_message = source_post.error_message


def _workflow_intake_settings(workflow: SocialWorkflow) -> tuple[str, int | None, bool]:
    cursor = workflow.poll_cursor_json or {}
    mode = str(cursor.get("source_import_mode") or "manual_select")
    if mode not in {"manual_select", "start_now", "last_n"}:
        mode = "manual_select"
    limit = cursor.get("source_backfill_limit")
    try:
        backfill_limit = int(limit) if limit is not None else None
    except (TypeError, ValueError):
        backfill_limit = None
    if backfill_limit is not None:
        backfill_limit = max(1, min(backfill_limit, 10))
    elif mode == "last_n":
        backfill_limit = 3
    return mode, backfill_limit, mode != "manual_select"


def poll_source_workflow(workflow_id: str) -> dict:
    workflow_uuid = uuid.UUID(workflow_id)
    created = 0
    enqueued = 0
    new_source_ids: list[str] = []
    dispatch_source_ids: list[str] = []
    now = datetime.now(timezone.utc)

    with SyncSessionLocal() as db:
        workflow = db.execute(
            select(SocialWorkflow)
            .where(SocialWorkflow.id == workflow_uuid, SocialWorkflow.status == SocialWorkflowStatus.active)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if not workflow:
            return {"workflow_id": workflow_id, "created": 0, "enqueued": 0, "skipped": "inactive_or_locked"}

        account = _resolve_workflow_source_account(db, workflow)
        if not account:
            workflow.last_error = _source_account_error(workflow.source_platform)
            workflow.last_polled_at = now
            db.commit()
            return {"workflow_id": workflow_id, "created": 0, "enqueued": 0, "error": workflow.last_error}

        try:
            media_rows = _iter_source_media(workflow, account)
            db.flush()
        except Exception as exc:
            workflow.last_error = source_poll_error_message(workflow.source_platform, exc)
            workflow.last_polled_at = now
            db.commit()
            logger.warning(
                "[workflows] source poll failed workflow_id=%s platform=%s error=%s",
                workflow_id,
                workflow.source_platform.value,
                workflow.last_error,
            )
            return {"workflow_id": workflow_id, "created": 0, "enqueued": 0, "error": workflow.last_error}

        existing_source_count = db.execute(
            select(func.count(SocialWorkflowSourcePost.id)).where(
                SocialWorkflowSourcePost.workflow_id == workflow.id,
            )
        ).scalar_one()
        intake_mode, backfill_limit, auto_import_detected = _workflow_intake_settings(workflow)
        initial_scan = existing_source_count == 0
        # manual_select: first scan detects existing posts without importing them.
        # start_now: only future posts are detected/imported.
        # last_n: first scan imports the latest N posts; later scans import future posts.
        if intake_mode == "start_now":
            watch_started_at = workflow.created_at
        elif intake_mode == "last_n" and initial_scan:
            watch_started_at = None
        elif intake_mode == "manual_select" and initial_scan:
            watch_started_at = None
        else:
            watch_started_at = workflow.created_at
        if watch_started_at and watch_started_at.tzinfo is None:
            watch_started_at = watch_started_at.replace(tzinfo=timezone.utc)
        elif watch_started_at:
            watch_started_at = watch_started_at.astimezone(timezone.utc)
        for media in media_rows:
            if media.media_type not in {"VIDEO", "REELS"}:
                continue
            if media.timestamp and watch_started_at and media.timestamp < watch_started_at:
                continue
            existing_source_id = db.execute(
                select(SocialWorkflowSourcePost.id).where(
                    SocialWorkflowSourcePost.workflow_id == workflow.id,
                    SocialWorkflowSourcePost.source_platform == workflow.source_platform,
                    SocialWorkflowSourcePost.external_post_id == media.id,
                )
            ).scalar_one_or_none()
            if existing_source_id:
                continue
            source_post = SocialWorkflowSourcePost(
                user_id=workflow.user_id,
                workflow_id=workflow.id,
                source_account_id=workflow.source_account_id,
                source_platform=workflow.source_platform,
                external_post_id=media.id,
                permalink=media.permalink,
                caption_snapshot=media.caption or media.title,
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
            if intake_mode == "last_n" and initial_scan and backfill_limit and created >= backfill_limit:
                break

        if auto_import_detected:
            # Redispatch existing detected posts as well as brand-new detections.
            # This makes Poll Now self-healing if a previous deploy created ledger
            # rows but lost the import task before workers could claim them.
            detected_source_ids = db.execute(
                select(SocialWorkflowSourcePost.id)
                .where(
                    SocialWorkflowSourcePost.workflow_id == workflow.id,
                    SocialWorkflowSourcePost.status == SocialWorkflowSourceStatus.detected,
                )
                .order_by(SocialWorkflowSourcePost.created_at.asc())
                .limit(50)
            ).scalars().all()
            seen_source_ids: set[str] = set()
            for source_id in [*new_source_ids, *[str(source_id) for source_id in detected_source_ids]]:
                if source_id in seen_source_ids:
                    continue
                seen_source_ids.add(source_id)
                dispatch_source_ids.append(source_id)

        workflow.last_polled_at = now
        workflow.last_error = None
        db.commit()

    from app.worker.tasks.social_workflows import import_source_post_media

    for source_id in dispatch_source_ids:
        import_source_post_media.apply_async(args=[source_id], queue="ingest")
        enqueued += 1

    return {"workflow_id": workflow_id, "created": created, "enqueued": enqueued}


def poll_active_official_source_workflows() -> dict:
    with SyncSessionLocal() as db:
        workflows = db.execute(
            select(SocialWorkflow.id)
            .where(
                SocialWorkflow.status == SocialWorkflowStatus.active,
                SocialWorkflow.source_platform.in_(
                    [SocialPlatform.instagram, SocialPlatform.youtube, SocialPlatform.facebook]
                ),
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


def _download_source_media(media_url: str, destination: Path, *, platform_label: str) -> tuple[int, str | None]:
    max_bytes = int(settings.max_upload_size_mb) * 1024 * 1024
    bytes_written = 0
    content_type = None
    with httpx.Client(timeout=settings.ytdlp_timeout_seconds, follow_redirects=True) as client:
        with client.stream("GET", media_url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            if content_type and not any(kind in content_type.lower() for kind in ("video/", "octet-stream")):
                raise RuntimeError(f"{platform_label} media returned unsupported content type: {content_type}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as out:
                for chunk in response.iter_bytes(DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise RuntimeError(f"{platform_label} source media exceeded the configured upload size limit")
                    out.write(chunk)
    if bytes_written <= 0:
        raise RuntimeError(f"{platform_label} source media download was empty")
    return bytes_written, content_type


def _video_source_type_for_platform(platform: SocialPlatform) -> VideoSourceType:
    if platform == SocialPlatform.instagram:
        return VideoSourceType.instagram
    if platform == SocialPlatform.facebook:
        return VideoSourceType.facebook
    if platform == SocialPlatform.youtube:
        return VideoSourceType.youtube
    return VideoSourceType.upload


def _platform_title(platform: SocialPlatform) -> str:
    if platform == SocialPlatform.youtube:
        return "YouTube"
    if platform == SocialPlatform.facebook:
        return "Facebook"
    if platform == SocialPlatform.instagram:
        return "Instagram"
    return platform.value.title()


def _clean_workflow_title_candidate(value: object, max_length: int = 140) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.replace("\n", " ").split())
    if not text or text == WORKFLOW_SOURCE_PLACEHOLDER_TITLE:
        return None
    if len(text) > max_length:
        return text[: max_length - 3].rstrip() + "..."
    return text


def workflow_source_clip_title(source_post: SocialWorkflowSourcePost, video: Video | None = None) -> str:
    raw_metadata = source_post.raw_metadata_json if isinstance(source_post.raw_metadata_json, dict) else {}
    candidates: list[object] = [
        video.title if video else None,
        raw_metadata.get("title"),
        source_post.caption_snapshot,
        raw_metadata.get("caption"),
        raw_metadata.get("description"),
        raw_metadata.get("name"),
    ]
    for candidate in candidates:
        title = _clean_workflow_title_candidate(candidate)
        if title:
            return title
    return f"{_platform_title(source_post.source_platform)} source video"


def _raw_media_url_for_source(platform: SocialPlatform, raw_metadata: dict, access_token: str) -> str | None:
    if platform == SocialPlatform.instagram:
        return _raw_instagram_media_url(raw_metadata, access_token)
    if platform == SocialPlatform.facebook:
        return _raw_facebook_media_url(raw_metadata, access_token)
    return None


def import_source_post(source_post_id: str) -> dict:
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
        platform = source_post.source_platform
        workflow_present = workflow is not None
        _sync_status(source_post, SocialWorkflowSourceStatus.importing)
        db.commit()

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"clipbandit-{platform.value}-source-"))
    tmp_media = tmp_dir / "source.mp4"
    try:
        if not workflow_present or not account_token_encrypted:
            raise RuntimeError(_source_account_error(platform))
        access_token = decrypt_secret(account_token_encrypted)
        media_url = _raw_media_url_for_source(platform, raw_metadata, access_token)
        if not media_url:
            with SyncSessionLocal() as db:
                source_post = db.get(SocialWorkflowSourcePost, source_uuid)
                if source_post:
                    _sync_status(
                        source_post,
                        SocialWorkflowSourceStatus.original_required,
                        f"Official {_platform_title(platform)} API did not provide a reusable video file for this post.",
                    )
                    db.commit()
            return {"source_post_id": source_post_id, "status": "original_required"}

        size_bytes, content_type = _download_source_media(media_url, tmp_media, platform_label=_platform_title(platform))

        with SyncSessionLocal() as db:
            source_post = db.get(SocialWorkflowSourcePost, source_uuid)
            if not source_post:
                return {"source_post_id": source_post_id, "status": "missing"}
            video_id = uuid.uuid4()
            storage_key = f"videos/{source_post.user_id}/{video_id}/source/{platform.value}.mp4"
            object_storage_client.upload_file(str(tmp_media), storage_key)
            title = (source_post.caption_snapshot or f"{_platform_title(platform)} source import").replace("\n", " ").strip()[:140]
            video = Video(
                id=video_id,
                user_id=source_post.user_id,
                title=title or f"{_platform_title(platform)} source import",
                source_type=_video_source_type_for_platform(platform),
                source_url=source_post.permalink,
                source_video_id=source_post.external_post_id if platform == SocialPlatform.youtube else None,
                thumbnail_url=source_post.thumbnail_url,
                import_state=VideoImportState.processing,
                import_mode=VideoImportMode.server_download,
                external_metadata_json={
                    "source_platform": platform.value,
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
                payload={"source": f"official_{platform.value}_workflow", "source_post_id": str(source_post.id)},
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
        logger.warning("[workflows] source import failed source_post_id=%s platform=%s error=%s", source_post_id, platform.value, message)
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
    derived_title = workflow_source_clip_title(source_post, video)
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
            title=derived_title,
            transcript_text=" ".join([word for word in words if word])[:5000],
            status=ClipStatus.ready,
        )
        db.add(clip)
        db.flush()
    elif clip.title == WORKFLOW_SOURCE_PLACEHOLDER_TITLE and derived_title != WORKFLOW_SOURCE_PLACEHOLDER_TITLE:
        clip.title = derived_title
        db.flush()

    if not clip.thumbnail_key:
        _ensure_workflow_clip_thumbnail(source_post, video, clip)

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


def _ensure_workflow_clip_thumbnail(source_post: SocialWorkflowSourcePost, video: Video, clip: Clip) -> None:
    if not video.storage_key:
        return

    thumb_storage_key = clip_thumbnail_key(str(video.user_id), str(video.id), str(clip.id))
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"clipbandit-workflow-thumb-{clip.id}-"))
    source_path = tmp_dir / "source.mp4"
    thumb_path = tmp_dir / "thumbnail.jpg"
    try:
        object_storage_client.download_file(video.storage_key, str(source_path))
        duration = max(float(clip.end_time or 0) - float(clip.start_time or 0), 0.0)
        offsets = [
            min(max(duration * 0.12, 0.25), max(duration - 0.25, 0.25)),
            min(max(duration * 0.5, 0.25), max(duration - 0.25, 0.25)),
            0.0,
        ]
        seen: set[float] = set()
        for offset in offsets:
            timestamp = round(float(clip.start_time or 0) + max(offset, 0.0), 3)
            if timestamp in seen:
                continue
            seen.add(timestamp)
            try:
                extract_thumbnail(str(source_path), str(thumb_path), timestamp)
                object_storage_client.upload_file(str(thumb_path), thumb_storage_key)
                clip.thumbnail_key = thumb_storage_key
                logger.info(
                    "[workflows] generated source clip thumbnail source_post_id=%s video_id=%s clip_id=%s key=%s",
                    source_post.id,
                    video.id,
                    clip.id,
                    thumb_storage_key,
                )
                return
            except Exception as exc:
                logger.warning(
                    "[workflows] source clip thumbnail attempt failed source_post_id=%s video_id=%s clip_id=%s ts=%s error=%s",
                    source_post.id,
                    video.id,
                    clip.id,
                    timestamp,
                    sanitize_sensitive_text(exc),
                )
    except Exception as exc:
        logger.warning(
            "[workflows] source clip thumbnail generation failed source_post_id=%s video_id=%s clip_id=%s error=%s",
            source_post.id,
            video.id,
            clip.id,
            sanitize_sensitive_text(exc),
        )
    finally:
        try:
            for path in (source_path, thumb_path):
                path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass


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


def _source_post_destination_targets(source_post: SocialWorkflowSourcePost, workflow: SocialWorkflow) -> list[dict]:
    metadata = source_post.raw_metadata_json or {}
    override = metadata.get("workflow_destination_targets_override")
    if isinstance(override, list) and override:
        return [target for target in override if isinstance(target, dict)]
    return workflow.destination_targets_json or []


def _resolve_destination_account(
    db,
    workflow: SocialWorkflow,
    target: dict,
) -> tuple[ConnectedAccount | None, dict]:
    account_id_raw = target.get("connected_account_id")
    platform_raw = target.get("platform")
    try:
        account_id = uuid.UUID(str(account_id_raw))
        platform = SocialPlatform(str(platform_raw))
    except (TypeError, ValueError):
        return None, target

    account = db.get(ConnectedAccount, account_id)
    if account and account.user_id == workflow.user_id and account.platform == platform:
        return account, target

    # OAuth reconnects can replace the connected-account row. Relink a stale
    # workflow destination to the user's newest account for the same platform.
    candidates = db.execute(
        select(ConnectedAccount)
        .where(
            ConnectedAccount.user_id == workflow.user_id,
            ConnectedAccount.platform == platform,
        )
        .order_by(ConnectedAccount.updated_at.desc())
    ).scalars().all()
    if len(candidates) != 1:
        return None, target
    account = candidates[0]
    repaired = {
        **target,
        "connected_account_id": str(account.id),
        "display_name": account.display_name or account.username_or_channel_name or account.external_account_id,
    }
    return account, repaired


def _create_publish_jobs(db, source_post: SocialWorkflowSourcePost, workflow: SocialWorkflow, export: Export) -> list[str]:
    clip = db.get(Clip, export.clip_id)
    if not clip:
        raise RuntimeError("Workflow export clip is missing")
    targets = _source_post_destination_targets(source_post, workflow)
    platforms = [str(target.get("platform")) for target in targets if target.get("platform")]
    copy_by_platform = _copy_for_destinations(source_post, workflow, clip, platforms)
    created_job_ids: list[str] = []
    repaired_targets: list[dict] = []
    targets_changed = False

    for target in targets:
        platform_raw = target.get("platform")
        if not platform_raw:
            continue
        try:
            platform = SocialPlatform(str(platform_raw))
        except ValueError:
            continue
        account, repaired_target = _resolve_destination_account(db, workflow, target)
        repaired_targets.append(repaired_target)
        targets_changed = targets_changed or repaired_target != target
        if not account:
            continue
        copy = copy_by_platform.get(platform.value, {})
        existing_job = db.execute(
            select(PublishJob).where(
                PublishJob.workflow_source_post_id == source_post.id,
                PublishJob.connected_account_id == account.id,
            )
        ).scalars().first()
        if existing_job:
            repaired_title = copy.get("title") or clip.title or source_post.caption_snapshot
            if repaired_title:
                if existing_job.title == WORKFLOW_SOURCE_PLACEHOLDER_TITLE:
                    existing_job.title = str(repaired_title)[:500]
                if existing_job.content_title_snapshot == WORKFLOW_SOURCE_PLACEHOLDER_TITLE:
                    existing_job.content_title_snapshot = str(repaired_title)[:500]
            created_job_ids.append(str(existing_job.id))
            continue
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

    if targets_changed:
        metadata = dict(source_post.raw_metadata_json or {})
        if metadata.get("workflow_destination_targets_override"):
            metadata["workflow_destination_targets_override"] = repaired_targets
            source_post.raw_metadata_json = metadata
        else:
            workflow.destination_targets_json = repaired_targets
    return created_job_ids


def start_source_post_workflow(source_post_id: str, destination_targets: list[dict] | None = None) -> dict:
    source_uuid = uuid.UUID(source_post_id)
    import_task_id = None
    publish_task_ids: list[str] = []
    job_ids: list[str] = []

    with SyncSessionLocal() as db:
        source_post = db.execute(
            select(SocialWorkflowSourcePost)
            .where(SocialWorkflowSourcePost.id == source_uuid)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if not source_post:
            return {"source_post_id": source_post_id, "status": "missing"}
        workflow = db.get(SocialWorkflow, source_post.workflow_id)
        if not workflow:
            _sync_status(source_post, SocialWorkflowSourceStatus.import_failed, "Workflow no longer exists")
            db.commit()
            return {"source_post_id": source_post_id, "status": "import_failed", "error": "Workflow no longer exists"}

        if destination_targets is not None:
            metadata = dict(source_post.raw_metadata_json or {})
            metadata["workflow_destination_targets_override"] = destination_targets
            source_post.raw_metadata_json = metadata

        if source_post.status in {SocialWorkflowSourceStatus.detected, SocialWorkflowSourceStatus.import_failed}:
            _sync_status(source_post, SocialWorkflowSourceStatus.detected)
            db.commit()
            from app.worker.tasks.social_workflows import import_source_post_media

            task = import_source_post_media.apply_async(args=[source_post_id], queue="ingest")
            import_task_id = task.id
            return {
                "source_post_id": source_post_id,
                "status": SocialWorkflowSourceStatus.detected.value,
                "import_task_id": import_task_id,
                "publish_job_ids": [],
                "publish_task_ids": [],
            }

        if source_post.status == SocialWorkflowSourceStatus.imported_processing:
            db.commit()
            return {
                "source_post_id": source_post_id,
                "status": source_post.status.value,
                "import_task_id": None,
                "publish_job_ids": [],
                "publish_task_ids": [],
            }

        if source_post.status != SocialWorkflowSourceStatus.ready_to_publish:
            db.commit()
            return {
                "source_post_id": source_post_id,
                "status": source_post.status.value,
                "import_task_id": None,
                "publish_job_ids": [],
                "publish_task_ids": [],
                "skipped": "not_ready_to_start",
            }

        export = db.get(Export, source_post.export_id) if source_post.export_id else None
        if not export:
            _sync_status(source_post, SocialWorkflowSourceStatus.import_failed, "Workflow export is missing")
            db.commit()
            return {"source_post_id": source_post_id, "status": "import_failed", "error": "Workflow export is missing"}
        if export.status != ExportStatus.ready:
            db.commit()
            return {
                "source_post_id": source_post_id,
                "status": source_post.status.value,
                "import_task_id": None,
                "publish_job_ids": [],
                "publish_task_ids": [],
                "skipped": "export_not_ready",
            }

        job_ids = _create_publish_jobs(db, source_post, workflow, export)
        if not job_ids:
            _sync_status(
                source_post,
                SocialWorkflowSourceStatus.ready_to_publish,
                "No valid destination account is connected. Reconnect or select a destination, then publish again.",
            )
            db.commit()
            return {
                "source_post_id": source_post_id,
                "status": SocialWorkflowSourceStatus.ready_to_publish.value,
                "import_task_id": None,
                "publish_job_ids": [],
                "publish_task_ids": [],
                "skipped": "no_valid_destination",
            }
        _sync_status(source_post, SocialWorkflowSourceStatus.publishing)
        if source_post.workflow_run:
            source_post.workflow_run.publish_job_ids_json = job_ids
        db.commit()

    if job_ids:
        from app.worker.tasks.publish import execute_publish_job

        for job_id in job_ids:
            task = execute_publish_job.apply_async(args=[job_id], queue="publish")
            publish_task_ids.append(task.id)

    return {
        "source_post_id": source_post_id,
        "status": SocialWorkflowSourceStatus.publishing.value,
        "import_task_id": import_task_id,
        "publish_job_ids": job_ids,
        "publish_task_ids": publish_task_ids,
    }


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
            if not job_ids:
                _sync_status(
                    source_post,
                    SocialWorkflowSourceStatus.ready_to_publish,
                    "No valid destination account is connected. Reconnect or select a destination, then publish again.",
                )
                continue
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

        # Revisit partial failures because a failed destination job can be retried later.
        # This keeps the source-post summary aligned with the current job outcomes.
        publishing_posts = db.execute(
            select(SocialWorkflowSourcePost)
            .where(
                SocialWorkflowSourcePost.status.in_(
                    [
                        SocialWorkflowSourceStatus.publishing,
                        SocialWorkflowSourceStatus.partial_failed,
                    ]
                )
            )
            .limit(50)
        ).scalars().all()
        for source_post in publishing_posts:
            jobs = db.execute(select(PublishJob).where(PublishJob.workflow_source_post_id == source_post.id)).scalars().all()
            if not jobs:
                _sync_status(
                    source_post,
                    SocialWorkflowSourceStatus.ready_to_publish,
                    "No destination jobs were created. Reconnect or select a destination, then publish again.",
                )
                finalized += 1
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
