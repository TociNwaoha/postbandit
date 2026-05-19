import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.models.job import Job, JobStatus
from app.models.transcript import TranscriptSegment
from app.models.video import Video, VideoImportState, VideoSourceType, VideoStatus
from app.services.ffmpeg import extract_audio, get_video_duration, get_video_resolution
from app.services.r2 import r2_client
from app.services.workspace import finalize_workspace, heartbeat_workspace, start_workspace
from app.services.youtube import transition_import_state
from app.services.transcription import get_model_with_metadata, transcribe_audio

logger = logging.getLogger(__name__)


class PerfTracker:
    def __init__(self, video_id: str):
        self.video_id = video_id
        self.task_started_at = time.perf_counter()
        self.phase_starts: dict[str, float] = {}
        self.phase_durations: dict[str, float] = {}

    def _elapsed(self) -> float:
        return time.perf_counter() - self.task_started_at

    @staticmethod
    def _fmt_fields(fields: dict[str, object]) -> str:
        parts: list[str] = []
        for key, value in fields.items():
            if isinstance(value, float):
                parts.append(f"{key}={value:.3f}")
            else:
                parts.append(f"{key}={value}")
        return " ".join(parts)

    def mark(self, event: str, **fields: object) -> None:
        extra = self._fmt_fields(fields)
        logger.info(
            "TRANSCRIBE_PERF video_id=%s event=%s elapsed_s=%.3f %s",
            self.video_id,
            event,
            self._elapsed(),
            extra,
        )

    def start(self, phase: str, **fields: object) -> None:
        self.phase_starts[phase] = time.perf_counter()
        self.mark(f"{phase}_start", **fields)

    def end(self, phase: str, **fields: object) -> float:
        started_at = self.phase_starts.get(phase)
        if started_at is None:
            self.mark(f"{phase}_end_missing_start", **fields)
            return 0.0
        duration = time.perf_counter() - started_at
        self.phase_durations[phase] = duration
        self.mark(f"{phase}_end", duration_s=duration, **fields)
        return duration

    def summary(self, **fields: object) -> None:
        payload = {
            "total_task_s": round(self._elapsed(), 3),
            "phase_durations_s": {
                key: round(value, 3) for key, value in sorted(self.phase_durations.items())
            },
            **fields,
        }
        logger.info(
            "TRANSCRIBE_PERF_SUMMARY video_id=%s data=%s",
            self.video_id,
            json.dumps(payload, sort_keys=True),
        )


def _latest_transcribe_job(db, video_uuid: uuid.UUID) -> Job | None:
    return (
        db.execute(
            select(Job)
            .where(Job.video_id == video_uuid, Job.type == "transcribe")
            .order_by(Job.created_at.desc())
        )
        .scalars()
        .first()
    )


@celery_app.task(
    name="app.worker.tasks.transcribe.transcribe_job",
    queue="transcribe",
    bind=True,
    max_retries=2,
    soft_time_limit=3600,
    time_limit=3900,
)
def transcribe_job(self, video_id: str):
    """
    Full transcription pipeline:
    1. Download video from storage to /tmp
    2. Extract audio with FFmpeg (16kHz mono WAV)
    3. Run faster-whisper transcription
    4. Save word segments to transcript_segments table
    5. Save full transcript JSON to storage
    6. Update video status to "scoring"
    7. Trigger score_job (stub for now)
    8. Clean up /tmp files
    """
    perf = PerfTracker(video_id)
    perf.mark("task_received")
    tmp_dir = Path(f"/tmp/clipbandit/{video_id}")
    workspace = None
    queue_delay_s: float | None = None

    try:
        video_uuid = uuid.UUID(video_id)
    except ValueError as exc:
        raise ValueError(f"Invalid video ID: {video_id}") from exc

    try:
        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if not video:
                raise ValueError(f"Video not found: {video_id}")
            workspace = start_workspace(
                job_type="transcribe",
                workspace_key=f"{video_id}-transcribe-{self.request.id or uuid.uuid4().hex[:8]}",
                video_id=str(video.id),
                user_id=str(video.user_id),
                expected_paths=["original.mp4", "audio.wav", "transcript.json"],
                refs={"video_id": str(video.id)},
            )

            job = _latest_transcribe_job(db, video_uuid)
            if job:
                if job.created_at:
                    now_utc = datetime.now(timezone.utc)
                    created_at = (
                        job.created_at.replace(tzinfo=timezone.utc)
                        if job.created_at.tzinfo is None
                        else job.created_at
                    )
                    queue_delay_s = max((now_utc - created_at).total_seconds(), 0.0)
                    perf.mark("queue_delay_computed", queue_delay_s=queue_delay_s)
                job.status = JobStatus.running
                job.started_at = datetime.now(timezone.utc)
                job.attempts = (job.attempts or 0) + 1
                db.commit()

            logger.info(f"Starting transcription for video {video_id}")

            tmp_dir.mkdir(parents=True, exist_ok=True)
            video_path = tmp_dir / "original.mp4"

            if not video.storage_key:
                raise FileNotFoundError("Video storage key is missing")
            if video.source_type in {
                VideoSourceType.youtube,
                VideoSourceType.youtube_single,
                VideoSourceType.youtube_playlist,
            }:
                transition_import_state(
                    db,
                    video,
                    to_state=VideoImportState.processing,
                    reason_code="transcribe_started",
                    actor="worker_transcribe",
                    allow_noop=True,
                    strict=False,
                )
            perf.start("file_read_source_locate", storage_key=video.storage_key)
            r2_client.download_file(video.storage_key, str(video_path))
            perf.end("file_read_source_locate")
            logger.info(f"Video downloaded to {video_path}")

            if not video.duration_sec:
                duration = get_video_duration(str(video_path))
                if duration:
                    video.duration_sec = int(duration)
            if not video.resolution:
                resolution = get_video_resolution(str(video_path))
                if resolution:
                    video.resolution = resolution
            video.status = VideoStatus.transcribing
            db.commit()

        audio_path = tmp_dir / "audio.wav"
        perf.start("ffmpeg_audio_extraction", input_path=str(video_path), output_path=str(audio_path))
        if workspace:
            heartbeat_workspace(workspace)
        extract_audio(str(video_path), str(audio_path))
        perf.end("ffmpeg_audio_extraction")
        logger.info(f"Audio extracted: {audio_path}")

        perf.start("whisper_model_load")
        model, loaded_from_cache, model_name = get_model_with_metadata()
        model_load_duration_s = perf.end(
            "whisper_model_load",
            model_name=model_name,
            loaded_from_cache=loaded_from_cache,
        )

        perf.start("transcription_inference", model_name=model_name)
        if workspace:
            heartbeat_workspace(workspace)
        result = transcribe_audio(str(audio_path), language="en", model=model)
        inference_duration_s = perf.end(
            "transcription_inference",
            model_name=model_name,
            word_count=len(result["words"]),
        )

        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if not video:
                raise ValueError(f"Video not found while saving transcript: {video_id}")

            perf.start("db_save", operation="transcript_segments")
            db.query(TranscriptSegment).filter(TranscriptSegment.video_id == video_uuid).delete()
            db.commit()

            segments_to_insert: list[TranscriptSegment] = []
            for word_data in result["words"]:
                if not word_data["word"]:
                    continue
                segments_to_insert.append(
                    TranscriptSegment(
                        video_id=video_uuid,
                        word=word_data["word"],
                        start_time=float(word_data["start"]),
                        end_time=float(word_data["end"]),
                        confidence=float(word_data["confidence"]),
                        segment_index=int(word_data["segment_index"]),
                    )
                )

            if segments_to_insert:
                db.bulk_save_objects(segments_to_insert)
                db.commit()
            perf.end("db_save", inserted_segments=len(segments_to_insert))

            logger.info(f"Saved {len(segments_to_insert)} word segments to DB")

            full_text = " ".join(
                (segment.get("text", "") or "").strip()
                for segment in result["segments"]
                if (segment.get("text", "") or "").strip()
            ).strip()

            transcript_key = f"transcripts/{video_id}/transcript.json"
            transcript_payload = {
                "video_id": video_id,
                "language": result["language"],
                "language_probability": float(result["language_probability"]),
                "duration": float(result["duration"]),
                "word_count": len(result["words"]),
                "full_text": full_text,
                "segments": result["segments"],
            }
            transcript_path = tmp_dir / "transcript.json"
            transcript_path.write_text(json.dumps(transcript_payload, indent=2), encoding="utf-8")
            perf.start("transcript_storage_save", transcript_key=transcript_key)
            r2_client.upload_file(str(transcript_path), transcript_key)
            perf.end("transcript_storage_save", transcript_key=transcript_key)
            logger.info(f"Transcript saved to storage: {transcript_key}")

            perf.start("final_status_update", target_status=VideoStatus.scoring.value)
            video.status = VideoStatus.scoring
            video.error_message = None
            db.commit()

            transcribe_row = _latest_transcribe_job(db, video_uuid)
            if transcribe_row:
                transcribe_row.status = JobStatus.done
                transcribe_row.error = None
                transcribe_row.completed_at = datetime.now(timezone.utc)

            score_row = Job(
                video_id=video_uuid,
                type="score",
                payload={},
                status=JobStatus.queued,
            )
            db.add(score_row)
            db.commit()
            db.refresh(score_row)
            perf.end("final_status_update", target_status=VideoStatus.scoring.value)

            from app.worker.tasks.score import score_job

            perf.start("score_trigger")
            task = score_job.apply_async(
                args=[video_id],
                countdown=1,
                queue="score",
            )
            score_row.celery_task_id = task.id
            db.commit()
            perf.end("score_trigger")

            logger.info(f"Transcription complete for {video_id}. Triggered score_job.")
            perf.summary(
                status="success",
                queue_delay_s=round(queue_delay_s, 3) if queue_delay_s is not None else None,
                model_load_s=round(model_load_duration_s, 3),
                transcription_inference_s=round(inference_duration_s, 3),
            )
            if workspace:
                finalize_workspace(workspace, state="terminal_success", metadata={"result": "scoring"})
            return {"video_id": video_id, "status": "scoring"}

    except Exception as exc:
        logger.exception(f"Transcription failed for video {video_id}: {exc}")
        perf.mark("task_error", error_type=type(exc).__name__)

        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if video:
                video.status = VideoStatus.error
                video.error_message = str(exc)[:500]
                if video.source_type in {
                    VideoSourceType.youtube,
                    VideoSourceType.youtube_single,
                    VideoSourceType.youtube_playlist,
                }:
                    transition_import_state(
                        db,
                        video,
                        to_state=VideoImportState.failed_retryable,
                        reason_code="transcribe_error",
                        actor="worker_transcribe",
                        metadata={"error_type": type(exc).__name__},
                        allow_noop=True,
                        strict=False,
                    )

            job = _latest_transcribe_job(db, video_uuid)
            if job:
                job.status = JobStatus.failed
                job.error = str(exc)[:500]
                job.completed_at = datetime.now(timezone.utc)
            db.commit()

        perf.summary(
            status="failed",
            error_type=type(exc).__name__,
            queue_delay_s=round(queue_delay_s, 3) if queue_delay_s is not None else None,
        )
        if workspace:
            finalize_workspace(
                workspace,
                state="terminal_failed",
                metadata={"error_type": type(exc).__name__},
            )

        if not isinstance(exc, (ValueError, FileNotFoundError)):
            raise self.retry(exc=exc, countdown=60)
        raise

    finally:
        try:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
                logger.info(f"Cleaned up {tmp_dir}")
        except Exception as cleanup_err:
            logger.warning(f"Cleanup failed: {cleanup_err}")


# Prompt 2 naming compatibility.
transcribe_video = transcribe_job
