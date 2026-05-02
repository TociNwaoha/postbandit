import json
import logging
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.video import Video
from app.models.clip import Clip
from app.models.export import Export
from app.models.job import Job, JobStatus
from app.models.video import VideoSourceType, VideoStatus
from app.schemas.video import (
    VideoConfirmUploadRequest,
    VideoConfirmUploadResponse,
    VideoImportYoutubeRequest,
    VideoImportYoutubeResponse,
    VideoListItem,
    VideoResponse,
    VideoStatusResponse,
    VideoTranscriptResponse,
    VideoUploadUrlRequest,
    VideoUploadUrlResponse,
)
from app.api.deps import get_current_user
from app.services.r2 import r2_client

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
}
MAX_UPLOAD_BYTES = 5_368_709_120
ALLOWED_YOUTUBE_DOMAINS = {"youtube.com", "youtu.be"}


def _file_ext_from_upload(filename: str, content_type: str) -> str:
    existing_ext = Path(filename).suffix.lower()
    if existing_ext:
        return existing_ext

    mime_to_ext = {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/x-msvideo": ".avi",
        "video/x-matroska": ".mkv",
    }
    return mime_to_ext.get(content_type, ".mp4")


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    return stem or "Untitled"


def _is_valid_youtube_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host in ALLOWED_YOUTUBE_DOMAINS:
        return True
    return host.endswith(".youtube.com") or host.endswith(".youtu.be")


@router.post("/videos/upload-url", response_model=VideoUploadUrlResponse)
async def create_upload_url(
    body: VideoUploadUrlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported content type",
        )
    if body.file_size <= 0 or body.file_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size must be between 1 byte and {MAX_UPLOAD_BYTES} bytes",
        )

    video = Video(
        user_id=current_user.id,
        status=VideoStatus.queued,
        source_type=VideoSourceType.upload,
        title=_title_from_filename(body.filename),
        file_size_bytes=body.file_size,
    )
    db.add(video)
    await db.flush()

    ext = _file_ext_from_upload(body.filename, body.content_type)
    storage_key = f"uploads/{video.id}/original{ext}"
    video.storage_key = storage_key

    signed = r2_client.get_presigned_upload_url(storage_key, expiry=900)
    return VideoUploadUrlResponse(
        video_id=video.id,
        upload_url=signed["url"],
        upload_fields=signed.get("fields", {}),
        storage_key=storage_key,
        use_local=signed.get("use_local", False),
    )


@router.post("/videos/confirm-upload", response_model=VideoConfirmUploadResponse)
async def confirm_upload(
    body: VideoConfirmUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video).where(Video.id == body.video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    if video.status != VideoStatus.queued:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Video is not in queued state")
    if not video.storage_key or not r2_client.file_exists(video.storage_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file not found in storage")

    video.status = VideoStatus.transcribing
    job = Job(video_id=video.id, type="transcribe", status=JobStatus.queued, payload={})
    db.add(job)
    await db.flush()
    await db.commit()
    await db.refresh(video)
    await db.refresh(job)

    try:
        from app.worker.tasks.transcribe import transcribe_job

        task = transcribe_job.apply_async(
            args=[str(video.id)],
            countdown=1,
            queue="transcribe",
        )
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        logger.warning(f"Unable to enqueue transcribe task for video {video.id}: {exc}")

    return VideoConfirmUploadResponse(video_id=video.id, status=video.status)


@router.post("/videos/import-youtube", response_model=VideoImportYoutubeResponse)
async def import_youtube(
    body: VideoImportYoutubeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    url = body.url.strip()
    if not _is_valid_youtube_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only valid youtube.com or youtu.be URLs are allowed",
        )

    video = Video(
        user_id=current_user.id,
        source_type=VideoSourceType.youtube_single,
        source_url=url,
        status=VideoStatus.downloading,
        title="Importing...",
    )
    db.add(video)
    await db.flush()

    job = Job(video_id=video.id, type="ingest", status=JobStatus.queued, payload={"url": url})
    db.add(job)
    await db.flush()
    await db.commit()
    await db.refresh(video)
    await db.refresh(job)

    try:
        from app.worker.tasks.ingest import ingest_job

        task = ingest_job.apply_async(
            args=[str(video.id)],
            countdown=1,
            queue="ingest",
        )
        job.celery_task_id = task.id
        await db.commit()
    except Exception as exc:
        logger.warning(f"Unable to enqueue ingest task for video {video.id}: {exc}")

    return VideoImportYoutubeResponse(
        video_id=video.id,
        status=video.status,
        message="Import started",
    )


@router.get("/videos", response_model=list[VideoListItem])
async def list_videos(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video)
        .where(Video.user_id == current_user.id)
        .order_by(Video.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    videos = result.scalars().all()
    return [
        VideoListItem(
            id=video.id,
            title=video.title,
            status=video.status,
            duration_sec=video.duration_sec,
            clip_count=video.clip_count,
            created_at=video.created_at,
            thumbnail_url=None,
        )
        for video in videos
    ]


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    source_download_url: str | None = None
    if video.storage_key:
        try:
            source_download_url = r2_client.get_presigned_download_url(video.storage_key)
        except Exception as exc:
            logger.warning("[videos] failed to generate source download URL for video_id=%s: %s", video.id, exc)

    return VideoResponse(
        id=video.id,
        user_id=video.user_id,
        title=video.title,
        source_type=video.source_type,
        source_url=video.source_url,
        storage_key=video.storage_key,
        source_download_url=source_download_url,
        duration_sec=video.duration_sec,
        resolution=video.resolution,
        file_size_bytes=video.file_size_bytes,
        status=video.status,
        error_message=video.error_message,
        clip_count=video.clip_count,
        created_at=video.created_at,
        updated_at=video.updated_at,
    )


@router.get("/videos/{video_id}/status", response_model=VideoStatusResponse)
async def get_video_status(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    return VideoStatusResponse(
        video_id=video.id,
        status=video.status,
        title=video.title,
        clip_count=video.clip_count,
        error_message=video.error_message,
    )


@router.get("/videos/{video_id}/transcript", response_model=VideoTranscriptResponse)
async def get_video_transcript(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    if video.status not in {VideoStatus.scoring, VideoStatus.ready}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not ready yet")

    transcript_key = f"transcripts/{video.id}/transcript.json"
    try:
        transcript_text = r2_client.read_text_file(transcript_key)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript file not found")
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript file not found")

    try:
        transcript_data = json.loads(transcript_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Transcript data is invalid")

    segments = transcript_data.get("segments", [])
    full_text = transcript_data.get("full_text")
    if not full_text:
        full_text = " ".join(
            (segment.get("text", "") or "").strip()
            for segment in segments
            if (segment.get("text", "") or "").strip()
        ).strip()

    word_count = transcript_data.get("word_count")
    if word_count is None:
        words = transcript_data.get("words")
        if isinstance(words, list):
            word_count = len([word for word in words if (word or {}).get("word")])
        else:
            word_count = sum(
                len(segment.get("words", []))
                for segment in segments
                if isinstance(segment, dict)
            )

    duration = transcript_data.get("duration")
    if duration is None:
        duration = float(video.duration_sec or 0)

    return VideoTranscriptResponse(
        video_id=video.id,
        word_count=int(word_count or 0),
        duration=float(duration or 0),
        language=transcript_data.get("language"),
        full_text=full_text,
        segments=segments,
    )


@router.delete("/videos/{video_id}")
async def delete_video(
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Video).where(Video.id == video_id, Video.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    storage_keys: set[str] = set()
    if video.storage_key:
        storage_keys.add(video.storage_key)
    storage_keys.add(f"transcripts/{video.id}/transcript.json")

    clip_result = await db.execute(select(Clip).where(Clip.video_id == video.id))
    clips = clip_result.scalars().all()
    clip_ids = [clip.id for clip in clips]
    for clip in clips:
        if clip.thumbnail_key:
            storage_keys.add(clip.thumbnail_key)

    if clip_ids:
        export_result = await db.execute(select(Export).where(Export.clip_id.in_(clip_ids)))
        exports = export_result.scalars().all()
        for export in exports:
            if export.storage_key:
                storage_keys.add(export.storage_key)
            if export.srt_key:
                storage_keys.add(export.srt_key)

    for key in storage_keys:
        try:
            r2_client.delete_file(key)
        except Exception as exc:
            logger.warning(f"Best-effort delete failed for {key}: {exc}")

    await db.delete(video)
    return {"deleted": True}
