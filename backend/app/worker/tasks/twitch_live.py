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
from app.models.video import Video, VideoImportState, VideoStatus
from app.services.object_storage import object_storage_client
from app.services.twitch import TwitchAPIError, create_clip_for_broadcaster, wait_for_clip
from app.worker.tasks.transcribe import transcribe_job

logger = logging.getLogger(__name__)


def _latest_twitch_job(db, video_id: uuid.UUID) -> Job | None:
    return db.execute(
        select(Job).where(Job.video_id == video_id, Job.type == "twitch_live_clip").order_by(Job.created_at.desc())
    ).scalars().first()


@celery_app.task(name="app.worker.tasks.twitch_live.create_live_clip", bind=True, queue="twitch_live_clips", max_retries=2)
def create_live_clip(self, video_id: str):
    """Create and download a Twitch clip without consuming existing ingest capacity."""
    work_dir = Path(f"/tmp/clipbandit/twitch-live/{self.request.id or uuid.uuid4().hex}")
    work_dir.mkdir(parents=True, exist_ok=True)
    video_uuid = uuid.UUID(video_id)
    try:
        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if not video or not video.triggering_channel_id:
                raise ValueError("Twitch clip video is unavailable")
            channel = db.execute(select(TwitchChannel).where(TwitchChannel.id == video.triggering_channel_id)).scalars().first()
            if not channel or channel.owner_user_id != video.user_id or channel.status != TwitchChannelStatus.active:
                raise ValueError("Twitch channel is unavailable")
            if not channel.is_live:
                raise ValueError("Twitch channel is not live")
            job = _latest_twitch_job(db, video_uuid)
            if job:
                job.status = JobStatus.running
                job.started_at = datetime.now(timezone.utc)
                job.attempts = (job.attempts or 0) + 1
            video.status = VideoStatus.downloading
            db.commit()
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
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().one()
            channel = db.execute(select(TwitchChannel).where(TwitchChannel.id == video.triggering_channel_id)).scalars().one()
            video.title = str(clip.get("title") or f"Twitch clip from {channel.display_name}")
            video.source_url = clip_url
            video.source_video_id = str(clip.get("id") or requested["id"])
            video.thumbnail_url = clip.get("thumbnail_url")
            video.duration_sec = int(clip.get("duration") or 0) or None
            video.import_state = VideoImportState.processing
            video.status = VideoStatus.transcribing
            video.twitch_clip_id = str(clip.get("id") or requested["id"])
            video.twitch_clip_slug = str(clip.get("id") or requested["id"])
            video.external_metadata_json = {"twitch_live": {"broadcaster_id": channel.twitch_broadcaster_id, "clip_url": clip_url}}
            storage_key = f"uploads/{video.id}/original.mp4"
            object_storage_client.upload_file(str(source_file), storage_key)
            video.storage_key = storage_key
            transcribe_row = Job(video_id=video.id, type="transcribe", payload={}, status=JobStatus.queued)
            db.add(transcribe_row)
            db.commit()
            task = transcribe_job.apply_async(args=[str(video.id)], countdown=1, queue="transcribe")
            transcribe_row.celery_task_id = task.id
            job = _latest_twitch_job(db, video_uuid)
            if job:
                job.status = JobStatus.done
                job.completed_at = datetime.now(timezone.utc)
            db.commit()
        return {"video_id": str(video_uuid), "status": "transcribing"}
    except TwitchAPIError as exc:
        logger.warning("[twitch_live] clip creation failed video_id=%s status=%s", video_id, exc.status_code)
        if exc.status_code in {429, 503} and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=15)
        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if video:
                video.status = VideoStatus.error
                video.error_message = str(exc)[:500]
                job = _latest_twitch_job(db, video_uuid)
                if job:
                    job.status = JobStatus.failed
                    job.error = str(exc)[:1000]
                    job.completed_at = datetime.now(timezone.utc)
                db.commit()
        raise
    except Exception as exc:
        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if video:
                video.status = VideoStatus.error
                video.error_message = str(exc)[:500]
                job = _latest_twitch_job(db, video_uuid)
                if job:
                    job.status = JobStatus.failed
                    job.error = str(exc)[:1000]
                    job.completed_at = datetime.now(timezone.utc)
                db.commit()
        raise
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
