from __future__ import annotations

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yt_dlp
from sqlalchemy import select

from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.models.job import Job, JobStatus
from app.models.twitch_channel import TwitchChannel, TwitchChannelStatus
from app.models.video import Video, VideoImportMode, VideoImportState, VideoSourceType, VideoStatus
from app.services.object_storage import object_storage_client
from app.services.twitch import TwitchAPIError, create_clip_for_broadcaster, wait_for_clip
from app.worker.tasks.transcribe import transcribe_job

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.twitch_live.create_live_clip", bind=True, queue="twitch_live_clips", max_retries=2)
def create_live_clip(self, channel_id: str, triggered_by_user_id: str):
    """Create and download a Twitch clip without consuming existing ingest capacity."""
    work_dir = Path(f"/tmp/clipbandit/twitch-live/{self.request.id or uuid.uuid4().hex}")
    work_dir.mkdir(parents=True, exist_ok=True)
    video_id: uuid.UUID | None = None
    try:
        channel_uuid = uuid.UUID(channel_id)
        user_uuid = uuid.UUID(triggered_by_user_id)
        with SyncSessionLocal() as db:
            channel = db.execute(select(TwitchChannel).where(TwitchChannel.id == channel_uuid)).scalars().first()
            if not channel or channel.owner_user_id != user_uuid or channel.status != TwitchChannelStatus.active:
                raise ValueError("Twitch channel is unavailable")
            if not channel.is_live:
                raise ValueError("Twitch channel is not live")
            requested = create_clip_for_broadcaster(db, channel.twitch_broadcaster_id)

        clip = wait_for_clip(str(requested["id"]))
        clip_url = str(clip.get("url") or "")
        if not clip_url:
            raise TwitchAPIError("Twitch clip response did not include a playable URL")
        with yt_dlp.YoutubeDL({"outtmpl": str(work_dir / "clip.%(ext)s"), "format": "best[height<=1080]/best", "noplaylist": True}) as ydl:
            ydl.extract_info(clip_url, download=True)
        files = [path for path in work_dir.iterdir() if path.is_file()]
        if not files:
            raise FileNotFoundError("Twitch clip download produced no media file")
        source_file = next((path for path in files if path.suffix.lower() == ".mp4"), files[0])

        with SyncSessionLocal() as db:
            channel = db.execute(select(TwitchChannel).where(TwitchChannel.id == channel_uuid)).scalars().one()
            video = Video(
                user_id=user_uuid,
                title=str(clip.get("title") or f"Twitch clip from {channel.display_name}"),
                source_type=VideoSourceType.twitch_live,
                source_url=clip_url,
                source_video_id=str(clip.get("id") or requested["id"]),
                thumbnail_url=clip.get("thumbnail_url"),
                duration_sec=int(clip.get("duration") or 0) or None,
                import_mode=VideoImportMode.server_download,
                import_state=VideoImportState.processing,
                status=VideoStatus.transcribing,
                twitch_clip_id=str(clip.get("id") or requested["id"]),
                twitch_clip_slug=str(clip.get("id") or requested["id"]),
                triggering_channel_id=channel.id,
                triggered_by_user_id=user_uuid,
                external_metadata_json={"twitch_live": {"broadcaster_id": channel.twitch_broadcaster_id, "clip_url": clip_url}},
            )
            db.add(video)
            db.flush()
            video_id = video.id
            storage_key = f"uploads/{video.id}/original.mp4"
            object_storage_client.upload_file(str(source_file), storage_key)
            video.storage_key = storage_key
            transcribe_row = Job(video_id=video.id, type="transcribe", payload={}, status=JobStatus.queued)
            db.add(transcribe_row)
            db.commit()
            task = transcribe_job.apply_async(args=[str(video.id)], countdown=1, queue="transcribe")
            transcribe_row.celery_task_id = task.id
            db.commit()
        return {"video_id": str(video_id), "status": "transcribing"}
    except TwitchAPIError as exc:
        logger.warning("[twitch_live] clip creation failed channel_id=%s status=%s", channel_id, exc.status_code)
        raise self.retry(exc=exc, countdown=15) if exc.status_code in {429, 503} and self.request.retries < self.max_retries else exc
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
