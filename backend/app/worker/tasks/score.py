import logging
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy import select

from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.models.clip import Clip, ClipStatus
from app.models.exclude_zone import ExcludeZone
from app.models.job import Job, JobStatus
from app.models.transcript import TranscriptSegment
from app.models.video import ClipProfile, Video, VideoImportState, VideoSourceType, VideoStatus
from app.services.ffmpeg import extract_audio, extract_thumbnail, get_video_resolution
from app.services.ai_copy import AICopyUnavailableError, generate_clip_copy, provider_configured
from app.services.object_storage import object_storage_client
from app.services.workspace import finalize_workspace, heartbeat_workspace, start_workspace
from app.services.youtube import transition_import_state
from app.services.scoring import (
    ClipSelectionProfile,
    CandidateWindow,
    apply_exclude_zones,
    build_chunks,
    build_energy_profile,
    build_word_tokens,
    calculate_energy_score,
    calculate_hook_score,
    extract_window_text,
    generate_candidate_ranges,
    get_clip_selection_profile,
    select_top_candidates,
)
from app.services.storage import clip_thumbnail_key

logger = logging.getLogger(__name__)


ENERGY_BUCKET_SEC = 0.5
LONG_FORM_CLIP_PROFILE_ALIASES = {"long_form_speaking"}
THUMBNAIL_CAPTION_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
)


def _resolve_clip_profile(video: Video) -> ClipProfile:
    metadata = video.external_metadata_json or {}
    if isinstance(metadata, dict):
        raw = metadata.get("clip_profile")
        if isinstance(raw, str):
            normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
            if normalized == ClipProfile.sermon.value or normalized in LONG_FORM_CLIP_PROFILE_ALIASES:
                return ClipProfile.sermon
    return ClipProfile.viral


def _latest_score_job(db, video_uuid: uuid.UUID) -> Job | None:
    return (
        db.execute(
            select(Job)
            .where(Job.video_id == video_uuid, Job.type == "score")
            .order_by(Job.created_at.desc())
        )
        .scalars()
        .first()
    )


def _build_clip_title(text: str, clip_number: int) -> str:
    trimmed = " ".join(text.split())
    if not trimmed:
        return f"Clip {clip_number}"
    if len(trimmed) <= 72:
        return trimmed
    return f"{trimmed[:69].rstrip()}..."


def _thumbnail_timestamps(start_time: float, end_time: float) -> list[float]:
    safe_start = max(float(start_time), 0.0)
    safe_end = max(float(end_time), safe_start)
    duration = max(safe_end - safe_start, 0.0)
    midpoint = safe_start + (duration / 2.0)
    end_probe = max(safe_start, safe_end - 0.15)
    start_probe = safe_start + 0.15 if duration >= 0.3 else safe_start

    candidates = [midpoint, start_probe, end_probe, safe_start, 0.0]
    deduped: list[float] = []
    for ts in candidates:
        normalized = round(max(ts, 0.0), 3)
        if normalized in deduped:
            continue
        deduped.append(normalized)
    return deduped


def get_thumbnail_caption_words(clip: Clip) -> tuple[str, str]:
    text = " ".join((clip.transcript_text or "").split())
    if not text:
        return ("", "")

    text = re.sub(r"[^\w\s'\-]", "", text).strip()
    words = text.split()[:12]
    if not words:
        return ("", "")
    if len(words) <= 5:
        return (" ".join(words).upper(), "")

    midpoint = len(words) // 2
    return (" ".join(words[:midpoint]).upper(), " ".join(words[midpoint:]).upper())


def _resolve_thumbnail_caption_font() -> str | None:
    for font_path in THUMBNAIL_CAPTION_FONT_CANDIDATES:
        if Path(font_path).exists():
            return font_path
    return None


def _thumbnail_caption_font_size(source_path: str) -> int:
    resolution = get_video_resolution(source_path)
    try:
        height = int((resolution or "0x0").split("x", 1)[1])
    except (IndexError, ValueError):
        height = 720
    if height >= 1080:
        return 54
    if height >= 720:
        return 42
    return 28


def _escape_drawtext_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace(",", "\\,")
        .replace("%", "\\%")
    )


def generate_thumbnail_with_caption(
    source_path: str,
    thumbnail_path: str,
    timestamp: float,
    line1: str,
    line2: str,
    font_path: str | None = None,
) -> bool:
    Path(thumbnail_path).parent.mkdir(parents=True, exist_ok=True)
    resolved_font = font_path or _resolve_thumbnail_caption_font()
    font_size = _thumbnail_caption_font_size(source_path)
    box_border = max(8, round(font_size * 0.28))

    def fallback_plain_thumbnail() -> bool:
        try:
            extract_thumbnail(source_path, thumbnail_path, timestamp)
            return Path(thumbnail_path).exists()
        except Exception as exc:
            logger.warning("[score] plain thumbnail fallback failed path=%s error=%s", thumbnail_path, exc)
            return False

    if not resolved_font or not (line1 or line2):
        return fallback_plain_thumbnail()

    line1_escaped = _escape_drawtext_text(line1)
    line2_escaped = _escape_drawtext_text(line2)

    if line1 and line2:
        y1 = "h*0.68"
        y2 = f"h*0.68+{font_size + box_border + 8}"
        video_filter = (
            f"drawtext=fontfile='{resolved_font}':text='{line1_escaped}':fontsize={font_size}"
            f":fontcolor=white:x=(w-text_w)/2:y={y1}:box=1:boxcolor=black@0.65:boxborderw={box_border},"
            f"drawtext=fontfile='{resolved_font}':text='{line2_escaped}':fontsize={font_size}"
            f":fontcolor=white:x=(w-text_w)/2:y={y2}:box=1:boxcolor=black@0.65:boxborderw={box_border}"
        )
    else:
        video_filter = (
            f"drawtext=fontfile='{resolved_font}':text='{line1_escaped}':fontsize={font_size}"
            f":fontcolor=white:x=(w-text_w)/2:y=h*0.72:box=1:boxcolor=black@0.65:boxborderw={box_border}"
        )

    command = [
        "ffmpeg",
        "-ss",
        f"{max(float(timestamp), 0.0):.3f}",
        "-i",
        source_path,
        "-frames:v",
        "1",
        "-update",
        "1",
        "-vf",
        video_filter,
        "-q:v",
        "2",
        "-y",
        thumbnail_path,
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.warning("[score] caption thumbnail failed stderr=%s", result.stderr[-800:])
            return fallback_plain_thumbnail()
        return Path(thumbnail_path).exists()
    except Exception as exc:
        logger.warning("[score] caption thumbnail exception error=%s", exc)
        return fallback_plain_thumbnail()


def _build_scored_candidates(
    transcript_words: list[TranscriptSegment],
    exclude_zones: list[ExcludeZone],
    audio_path: str,
    selection_profile: ClipSelectionProfile,
) -> tuple[list[CandidateWindow], dict[str, int | float | str]]:
    tokens = build_word_tokens(transcript_words)
    if not tokens:
        return [], {
            "word_count": 0,
            "raw_candidate_count": 0,
            "filtered_candidate_count": 0,
            "selected_candidate_count": 0,
        }

    chunks = build_chunks(tokens, pause_gap_sec=selection_profile.pause_gap_sec)
    candidate_ranges = generate_candidate_ranges(
        chunks=chunks,
        tokens=tokens,
        min_duration_sec=selection_profile.min_duration_sec,
        max_duration_sec=selection_profile.max_duration_sec,
        min_words=selection_profile.min_words,
        chunk_merge_gap_sec=selection_profile.chunk_merge_gap_sec,
    )

    energy_profile = build_energy_profile(audio_path, bucket_size_sec=ENERGY_BUCKET_SEC)

    raw_count = len(candidate_ranges)
    filtered_candidates: list[CandidateWindow] = []
    for start, end in candidate_ranges:
        adjusted = apply_exclude_zones(
            start=start,
            end=end,
            zones=exclude_zones,
            min_duration_sec=selection_profile.min_duration_sec,
        )
        if not adjusted:
            continue

        adjusted_start, adjusted_end = adjusted
        transcript_text = extract_window_text(tokens, adjusted_start, adjusted_end)
        if len(transcript_text.split()) < selection_profile.min_words:
            continue

        hook_score = calculate_hook_score(
            transcript_text,
            adjusted_start,
            hook_word_bonus_min=selection_profile.hook_word_bonus_min,
            hook_word_bonus_max=selection_profile.hook_word_bonus_max,
        )
        energy_score = calculate_energy_score(adjusted_start, adjusted_end, energy_profile)
        combined_score = round(
            (selection_profile.hook_weight * hook_score)
            + (selection_profile.energy_weight * energy_score),
            4,
        )

        filtered_candidates.append(
            CandidateWindow(
                start=adjusted_start,
                end=adjusted_end,
                transcript_text=transcript_text,
                hook_score=hook_score,
                energy_score=energy_score,
                combined_score=combined_score,
            )
        )

    selected = select_top_candidates(
        candidates=filtered_candidates,
        top_n=selection_profile.top_n,
        max_overlap_ratio=selection_profile.max_overlap_ratio,
        clip_profile=selection_profile.clip_profile,
    )
    stats = {
        "clip_profile": selection_profile.clip_profile.value,
        "word_count": len(tokens),
        "raw_candidate_count": raw_count,
        "filtered_candidate_count": len(filtered_candidates),
        "selected_candidate_count": len(selected),
    }
    return selected, stats


@celery_app.task(name="app.worker.tasks.score.score_job", queue="score", bind=True)
def score_job(self, video_id: str):
    tmp_dir = Path(f"/tmp/clipbandit-score/{video_id}")
    logger.info("[score] score_job received for video_id=%s", video_id)
    video_uuid: uuid.UUID | None = None
    storage_key: str | None = None
    clip_profile = ClipProfile.viral
    selection_profile = get_clip_selection_profile(clip_profile)
    workspace = None

    try:
        try:
            video_uuid = uuid.UUID(video_id)
        except ValueError:
            raise ValueError(f"score_job got invalid video id: {video_id}")

        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if not video:
                raise ValueError(f"Video not found: {video_id}")
            clip_profile = _resolve_clip_profile(video)
            selection_profile = get_clip_selection_profile(clip_profile)
            workspace = start_workspace(
                job_type="score",
                workspace_key=f"{video_id}-score-{self.request.id or uuid.uuid4().hex[:8]}",
                video_id=str(video.id),
                user_id=str(video.user_id),
                expected_paths=["source_video", "audio_analysis", "clip_thumbnails"],
                refs={"video_id": str(video.id)},
            )
            if not video.storage_key:
                raise FileNotFoundError(f"Video storage key missing for {video_id}")
            storage_key = video.storage_key
            if video.source_type in {
                VideoSourceType.youtube,
                VideoSourceType.youtube_single,
                VideoSourceType.youtube_playlist,
                VideoSourceType.instagram,
                VideoSourceType.facebook,
                VideoSourceType.tiktok,
                VideoSourceType.x,
                VideoSourceType.twitch,
            }:
                transition_import_state(
                    db,
                    video,
                    to_state=VideoImportState.processing,
                    reason_code="score_started",
                    actor="worker_score",
                    allow_noop=True,
                    strict=False,
                )

            score_row = _latest_score_job(db, video_uuid)
            if not score_row:
                score_row = Job(
                    video_id=video_uuid,
                    type="score",
                    payload={},
                    status=JobStatus.queued,
                )
                db.add(score_row)
                db.flush()

            score_row.status = JobStatus.running
            score_row.started_at = datetime.now(timezone.utc)
            score_row.attempts = (score_row.attempts or 0) + 1
            db.commit()

        tmp_dir.mkdir(parents=True, exist_ok=True)
        local_video_path = tmp_dir / "original.mp4"
        local_audio_path = tmp_dir / "audio.wav"

        if storage_key is None:
            raise FileNotFoundError(f"Video storage key missing for {video_id}")

        logger.info("[score] loading media source for video_id=%s", video_id)
        object_storage_client.download_file(storage_key, str(local_video_path))
        if workspace:
            heartbeat_workspace(workspace)
        logger.info("[score] media source ready at %s", local_video_path)

        logger.info("[score] audio analysis start for video_id=%s", video_id)
        extract_audio(str(local_video_path), str(local_audio_path))
        if workspace:
            heartbeat_workspace(workspace)
        logger.info("[score] audio analysis end for video_id=%s", video_id)

        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if not video:
                raise ValueError(f"Video not found during scoring: {video_id}")

            transcript_words = (
                db.execute(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.video_id == video_uuid)
                    .order_by(TranscriptSegment.start_time.asc())
                )
                .scalars()
                .all()
            )
            exclude_zones = (
                db.execute(
                    select(ExcludeZone)
                    .where(ExcludeZone.video_id == video_uuid)
                    .order_by(ExcludeZone.start_time.asc())
                )
                .scalars()
                .all()
            )

            logger.info(
                "[score] transcript loaded for video_id=%s word_rows=%s exclude_zones=%s clip_profile=%s",
                video_id,
                len(transcript_words),
                len(exclude_zones),
                selection_profile.clip_profile.value,
            )

        selected_candidates, stats = _build_scored_candidates(
            transcript_words=transcript_words,
            exclude_zones=exclude_zones,
            audio_path=str(local_audio_path),
            selection_profile=selection_profile,
        )
        logger.info(
            "[score] candidate counts video_id=%s profile=%s raw=%s filtered=%s selected=%s",
            video_id,
            selection_profile.clip_profile.value,
            stats["raw_candidate_count"],
            stats["filtered_candidate_count"],
            stats["selected_candidate_count"],
        )

        with SyncSessionLocal() as db:
            video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
            if not video:
                raise ValueError(f"Video not found while persisting clips: {video_id}")

            db.execute(delete(Clip).where(Clip.video_id == video_uuid))
            db.commit()

            created_clips: list[Clip] = []
            for idx, candidate in enumerate(selected_candidates, start=1):
                clip = Clip(
                    video_id=video_uuid,
                    start_time=round(candidate.start, 3),
                    end_time=round(candidate.end, 3),
                    duration_sec=round(candidate.duration, 3),
                    score=candidate.combined_score,
                    hook_score=candidate.hook_score,
                    energy_score=candidate.energy_score,
                    transcript_text=candidate.transcript_text,
                    status=ClipStatus.ready,
                    title=_build_clip_title(candidate.transcript_text, idx),
                )
                db.add(clip)
                created_clips.append(clip)

            db.flush()
            logger.info("[score] db write prepared video_id=%s clip_rows=%s", video_id, len(created_clips))

            thumbnail_success = 0
            thumbnail_failed = 0
            for clip in created_clips:
                thumb_local_path = tmp_dir / f"thumb-{clip.id}.jpg"
                thumb_storage_key = clip_thumbnail_key(str(video.user_id), str(video.id), str(clip.id))
                timestamps = _thumbnail_timestamps(clip.start_time, clip.end_time)
                thumb_error: Exception | None = None

                for timestamp in timestamps:
                    try:
                        line1, line2 = get_thumbnail_caption_words(clip)
                        thumbnail_ok = generate_thumbnail_with_caption(
                            source_path=str(local_video_path),
                            thumbnail_path=str(thumb_local_path),
                            timestamp=timestamp,
                            line1=line1,
                            line2=line2,
                        )
                        if not thumbnail_ok:
                            raise RuntimeError("Caption thumbnail generation failed")
                        object_storage_client.save_thumbnail_locally(str(thumb_local_path), thumb_storage_key)
                        clip.thumbnail_key = thumb_storage_key
                        thumbnail_success += 1
                        thumb_error = None
                        break
                    except Exception as thumb_exc:
                        thumb_error = thumb_exc
                        logger.warning(
                            "[score] thumbnail attempt failed video_id=%s clip_id=%s ts=%s error=%s",
                            video_id,
                            clip.id,
                            timestamp,
                            thumb_exc,
                        )

                if thumb_error is not None:
                    clip.thumbnail_key = None
                    thumbnail_failed += 1
                    logger.warning(
                        "[score] thumbnail generation failed video_id=%s clip_id=%s attempts=%s final_error=%s",
                        video_id,
                        clip.id,
                        len(timestamps),
                        thumb_error,
                    )

            video.clip_count = len(created_clips)
            video.status = VideoStatus.ready
            video.error_message = None
            if video.source_type in {
                VideoSourceType.youtube,
                VideoSourceType.youtube_single,
                VideoSourceType.youtube_playlist,
                VideoSourceType.instagram,
                VideoSourceType.facebook,
                VideoSourceType.tiktok,
                VideoSourceType.x,
                VideoSourceType.twitch,
            }:
                transition_import_state(
                    db,
                    video,
                    to_state=VideoImportState.ready,
                    reason_code="score_complete",
                    actor="worker_score",
                    metadata={"clip_count": len(created_clips)},
                    allow_noop=True,
                    strict=False,
                )

            score_row = _latest_score_job(db, video_uuid)
            if score_row:
                score_row.status = JobStatus.done
                score_row.error = None
                score_row.completed_at = datetime.now(timezone.utc)

            db.commit()
            logger.info(
                "[score] final db write complete video_id=%s clip_count=%s thumbnails_ok=%s thumbnails_failed=%s",
                video_id,
                len(created_clips),
                thumbnail_success,
                thumbnail_failed,
            )

            clip_ids = [clip.id for clip in created_clips]

        if clip_ids:
            logger.info("[score] ai copy generation start video_id=%s clip_count=%s", video_id, len(clip_ids))
            copy_ready_count = 0
            copy_unavailable_count = 0

            with SyncSessionLocal() as copy_db:
                copy_video = copy_db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
                copy_video_title = copy_video.title if copy_video else None

                if not provider_configured():
                    for clip_id in clip_ids:
                        clip_row = copy_db.execute(select(Clip).where(Clip.id == clip_id)).scalars().first()
                        if not clip_row:
                            continue
                        clip_row.title_options = None
                        clip_row.hashtag_options = None
                        clip_row.copy_generation_status = "unavailable"
                        clip_row.copy_generation_error = "DEEPSEEK_API_KEY is not configured"
                        copy_unavailable_count += 1
                    copy_db.commit()
                    logger.warning("[score] ai copy unavailable video_id=%s reason=missing_api_key", video_id)
                else:
                    for clip_id in clip_ids:
                        clip_row = copy_db.execute(select(Clip).where(Clip.id == clip_id)).scalars().first()
                        if not clip_row:
                            continue
                        try:
                            copy_result = generate_clip_copy(
                                transcript_text=clip_row.transcript_text or "",
                                video_title=copy_video_title,
                                clip_start=clip_row.start_time,
                                clip_end=clip_row.end_time,
                            )
                            clip_row.title_options = copy_result.title_options
                            clip_row.hashtag_options = copy_result.hashtag_options
                            clip_row.copy_generation_status = "ready"
                            clip_row.copy_generation_error = None
                            clip_row.title = copy_result.title_options[0]
                            clip_row.hashtags = copy_result.hashtag_options[0]
                            copy_ready_count += 1
                        except AICopyUnavailableError as exc:
                            clip_row.title_options = None
                            clip_row.hashtag_options = None
                            clip_row.copy_generation_status = "unavailable"
                            clip_row.copy_generation_error = str(exc)[:500]
                            copy_unavailable_count += 1
                            logger.warning(
                                "[score] ai copy unavailable video_id=%s clip_id=%s error=%s",
                                video_id,
                                clip_id,
                                exc,
                            )
                        except Exception as exc:
                            clip_row.title_options = None
                            clip_row.hashtag_options = None
                            clip_row.copy_generation_status = "unavailable"
                            clip_row.copy_generation_error = str(exc)[:500]
                            copy_unavailable_count += 1
                            logger.warning(
                                "[score] ai copy generation failed video_id=%s clip_id=%s error=%s",
                                video_id,
                                clip_id,
                                exc,
                            )
                    copy_db.commit()

            logger.info(
                "[score] ai copy generation end video_id=%s ready=%s unavailable=%s",
                video_id,
                copy_ready_count,
                copy_unavailable_count,
            )

        if not selected_candidates:
            logger.info("[score] no strong clips found video_id=%s status=ready clip_count=0", video_id)
        logger.info("[score] final status update video_id=%s status=ready", video_id)
        if workspace:
            finalize_workspace(workspace, state="terminal_success", metadata={"result": "ready"})
        return {
            "video_id": video_id,
            "status": "ready",
            "clip_count": len(selected_candidates),
            "stats": stats,
        }
    except Exception as exc:
        logger.exception("[score] score_job failed for video_id=%s: %s", video_id, exc)
        user_error_message = str(exc)[:500]
        if video_uuid is not None:
            try:
                with SyncSessionLocal() as db:
                    video = db.execute(select(Video).where(Video.id == video_uuid)).scalars().first()
                    if video:
                        video.status = VideoStatus.error
                        video.error_message = user_error_message
                        if video.source_type in {
                            VideoSourceType.youtube,
                            VideoSourceType.youtube_single,
                            VideoSourceType.youtube_playlist,
                            VideoSourceType.instagram,
                            VideoSourceType.facebook,
                            VideoSourceType.tiktok,
                            VideoSourceType.x,
                            VideoSourceType.twitch,
                        }:
                            transition_import_state(
                                db,
                                video,
                                to_state=VideoImportState.failed_retryable,
                                reason_code="score_error",
                                actor="worker_score",
                                metadata={"error_type": type(exc).__name__},
                                allow_noop=True,
                                strict=False,
                            )

                    score_row = _latest_score_job(db, video_uuid)
                    if score_row:
                        score_row.status = JobStatus.failed
                        score_row.error = user_error_message
                        score_row.completed_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception as inner_exc:
                logger.exception("[score] failed to write error state for video_id=%s: %s", video_id, inner_exc)
        if workspace:
            finalize_workspace(
                workspace,
                state="terminal_failed",
                metadata={"error_type": type(exc).__name__},
            )
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# Legacy filename compatibility.
score_clips = score_job
