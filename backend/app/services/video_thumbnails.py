from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.models.video import Video
from app.services.ffmpeg import extract_thumbnail
from app.services.object_storage import object_storage_client
from app.services.storage import video_thumbnail_key

logger = logging.getLogger(__name__)


def _thumbnail_timestamp(duration_sec: int | float | None) -> float:
    if not duration_sec or duration_sec <= 1:
        return 0.1
    return min(max(float(duration_sec) * 0.08, 1.0), max(float(duration_sec) - 0.5, 0.1))


def generate_video_thumbnail_from_local_source(
    *,
    source_path: str | Path,
    user_id: uuid.UUID,
    video_id: uuid.UUID,
    duration_sec: int | float | None = None,
    log_context: str = "video_thumbnail",
) -> str | None:
    """Generate a stable PostBandit-served thumbnail from an available local video file.

    Thumbnail generation is intentionally best-effort. A bad/corrupt source frame should not
    block ingest, transcription, or workflow import.
    """
    source = Path(source_path)
    if not source.exists() or not source.is_file():
        logger.warning(
            "[video_thumbnail] skipped missing_source context=%s video_id=%s source_path=%s",
            log_context,
            video_id,
            source,
        )
        return None

    thumbnail_key = video_thumbnail_key(str(user_id), str(video_id))
    existing_url = object_storage_client.get_thumbnail_url(thumbnail_key)
    if existing_url:
        return existing_url

    thumbnail_path = source.parent / f"{source.stem}-postbandit-thumbnail.jpg"
    try:
        extract_thumbnail(str(source), str(thumbnail_path), _thumbnail_timestamp(duration_sec))
        object_storage_client.save_thumbnail_locally(str(thumbnail_path), thumbnail_key)
        return object_storage_client.get_thumbnail_url(thumbnail_key)
    except Exception as exc:
        logger.warning(
            "[video_thumbnail] generation_failed context=%s video_id=%s source_path=%s error=%s",
            log_context,
            video_id,
            source,
            exc,
        )
        return None


def ensure_video_thumbnail_from_local_source(
    video: Video,
    source_path: str | Path,
    *,
    log_context: str = "video_thumbnail",
) -> str | None:
    thumbnail_key = video_thumbnail_key(str(video.user_id), str(video.id))
    existing_url = object_storage_client.get_thumbnail_url(thumbnail_key)
    if existing_url:
        return existing_url

    return generate_video_thumbnail_from_local_source(
        source_path=source_path,
        user_id=video.user_id,
        video_id=video.id,
        duration_sec=video.duration_sec,
        log_context=log_context,
    )
