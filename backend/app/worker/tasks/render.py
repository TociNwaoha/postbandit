import logging
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.celery_app import celery_app
from app.database import SyncSessionLocal
from app.models.clip import Clip, ClipStatus
from app.models.clip_overlay_asset import ClipOverlayAsset
from app.models.export import CaptionColorVariant, CaptionFormat, Export, ExportStatus
from app.models.job import Job, JobStatus
from app.models.transcript import TranscriptSegment
from app.models.video import Video
from app.services.object_storage import object_storage_client
from app.services.clip_overlay_rendering import render_highlighted_text_layer
from app.services.rendering import (
    build_subtitle_cues,
    has_video_stream,
    render_video_clip,
    resolve_output_dimensions,
    write_ass,
    write_srt,
)
from app.services.storage import export_srt_key, export_video_key

logger = logging.getLogger(__name__)


class RenderPipelineError(Exception):
    pass


def _find_render_job(db, video_id: uuid.UUID, explicit_job_id: uuid.UUID | None) -> Job | None:
    if explicit_job_id:
        return db.execute(select(Job).where(Job.id == explicit_job_id)).scalars().first()
    return (
        db.execute(
            select(Job)
            .where(Job.video_id == video_id, Job.type == "render")
            .order_by(Job.created_at.desc())
        )
        .scalars()
        .first()
    )


@celery_app.task(name="app.worker.tasks.render.render_export", bind=True, queue="render", max_retries=0)
def render_export(self, export_id: str, job_id: str | None = None):
    logger.info("[render] render job start export_id=%s job_id=%s", export_id, job_id)

    try:
        export_uuid = uuid.UUID(export_id)
    except ValueError:
        logger.error("[render] invalid export id: %s", export_id)
        return {"export_id": export_id, "status": "error", "message": "invalid export id"}

    job_uuid: uuid.UUID | None = None
    if job_id:
        try:
            job_uuid = uuid.UUID(job_id)
        except ValueError:
            logger.warning("[render] invalid job id: %s", job_id)

    started = time.perf_counter()
    tmp_dir = Path(f"/tmp/clipbandit-render/{export_id}")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        with SyncSessionLocal() as db:
            load_result = db.execute(
                select(Export, Clip, Video)
                .join(Clip, Export.clip_id == Clip.id)
                .join(Video, Clip.video_id == Video.id)
                .where(Export.id == export_uuid)
            ).first()
            if not load_result:
                raise RenderPipelineError(f"Export not found: {export_id}")

            export, clip, video = load_result
            logger.info(
                "[render] export loaded export_id=%s clip_id=%s video_id=%s status=%s",
                export.id,
                clip.id,
                video.id,
                export.status,
            )

            render_job = _find_render_job(db, video.id, job_uuid)
            if render_job:
                render_job.status = JobStatus.running
                render_job.started_at = datetime.now(timezone.utc)
                render_job.attempts = (render_job.attempts or 0) + 1

            export.status = ExportStatus.rendering
            export.error_message = None
            export.render_time_sec = None
            db.commit()

            if not video.storage_key:
                raise RenderPipelineError("Source media key is missing for this clip/video")

            source_path = tmp_dir / "source.mp4"
            logger.info("[render] source media resolution start export_id=%s key=%s", export.id, video.storage_key)
            object_storage_client.download_file(video.storage_key, str(source_path))
            logger.info("[render] source media resolved export_id=%s path=%s", export.id, source_path)

            if not has_video_stream(str(source_path)):
                raise RenderPipelineError("Source media is audio-only and cannot be exported as video")
            aspect_ratio_value = _enum_value(export.aspect_ratio)
            target_width, target_height = resolve_output_dimensions(aspect_ratio_value, str(source_path))

            srt_local_path: Path | None = None
            ass_local_path: Path | None = None
            if export.caption_format != CaptionFormat.none:
                transcript_rows = (
                    db.execute(
                        select(TranscriptSegment)
                        .where(
                            TranscriptSegment.video_id == video.id,
                            TranscriptSegment.start_time < clip.end_time,
                            TranscriptSegment.end_time > clip.start_time,
                        )
                        .order_by(TranscriptSegment.start_time.asc())
                    )
                    .scalars()
                    .all()
                )
                logger.info(
                    "[render] caption generation start export_id=%s transcript_words=%s cadence=%s",
                    export.id,
                    len(transcript_rows),
                    _enum_value(export.caption_cadence),
                )
                cues = build_subtitle_cues(
                    transcript_rows,
                    clip_start=float(clip.start_time),
                    clip_end=float(clip.end_time),
                    cadence=_enum_value(export.caption_cadence),
                )
                if not cues:
                    raise RenderPipelineError(
                        "Caption timing is unavailable for this clip. Choose caption output None or regenerate the transcript."
                    )

                srt_local_path = tmp_dir / "captions.srt"
                write_srt(cues, str(srt_local_path))
                if export.caption_format == CaptionFormat.burned_in:
                    ass_local_path = tmp_dir / "captions.ass"
                    write_ass(
                        cues,
                        str(ass_local_path),
                        _enum_value(export.caption_style),
                        _enum_value(export.caption_color_variant or CaptionColorVariant.classic),
                        aspect_ratio_value,
                        target_width,
                        target_height,
                        export.caption_vertical_position,
                        export.caption_scale,
                    )
                logger.info("[render] caption generation end export_id=%s cues=%s", export.id, len(cues))
            else:
                logger.info("[render] captions disabled export_id=%s", export.id)

            output_path = tmp_dir / "output.mp4"
            overlay_image_path: Path | None = None
            if export.overlay_image_asset_id and export.overlay_image_config:
                overlay_asset = db.execute(
                    select(ClipOverlayAsset).where(
                        ClipOverlayAsset.id == export.overlay_image_asset_id,
                        ClipOverlayAsset.clip_id == clip.id,
                        ClipOverlayAsset.user_id == export.user_id,
                    )
                ).scalars().first()
                if not overlay_asset:
                    raise RenderPipelineError("Overlay image asset is unavailable")
                extension = {
                    "image/png": ".png",
                    "image/jpeg": ".jpg",
                    "image/webp": ".webp",
                }.get(overlay_asset.mime_type, ".png")
                overlay_image_path = tmp_dir / f"overlay-image{extension}"
                object_storage_client.download_file(overlay_asset.storage_key, str(overlay_image_path))

            overlay_text_layer_path: Path | None = None
            if export.overlay_text_config:
                overlay_text_layer_path = tmp_dir / "overlay-text.png"
                render_highlighted_text_layer(
                    export.overlay_text_config,
                    target_width=target_width,
                    target_height=target_height,
                    output_path=str(overlay_text_layer_path),
                )
            logger.info(
                "[render] ffmpeg render start export_id=%s aspect_ratio=%s caption_format=%s caption_vertical_position=%s caption_scale=%s frame_anchor_x=%s frame_anchor_y=%s frame_zoom=%s image_overlay=%s text_overlay=%s",
                export.id,
                _enum_value(export.aspect_ratio),
                _enum_value(export.caption_format),
                export.caption_vertical_position,
                export.caption_scale,
                export.frame_anchor_x,
                export.frame_anchor_y,
                export.frame_zoom,
                bool(overlay_image_path),
                bool(overlay_text_layer_path),
            )
            render_video_clip(
                source_path=str(source_path),
                output_path=str(output_path),
                clip_start=float(clip.start_time),
                clip_end=float(clip.end_time),
                aspect_ratio=aspect_ratio_value,
                target_width=target_width,
                target_height=target_height,
                burned_ass_path=str(ass_local_path) if ass_local_path else None,
                frame_anchor_x=export.frame_anchor_x,
                frame_anchor_y=export.frame_anchor_y,
                frame_zoom=export.frame_zoom,
                overlay_image_path=str(overlay_image_path) if overlay_image_path else None,
                overlay_image_config=export.overlay_image_config,
                overlay_text_layer_path=(
                    str(overlay_text_layer_path) if overlay_text_layer_path else None
                ),
            )
            logger.info("[render] ffmpeg render end export_id=%s output=%s", export.id, output_path)

            output_key = export_video_key(
                str(export.user_id),
                str(clip.id),
                str(export.id),
                _enum_value(export.aspect_ratio),
            )
            object_storage_client.upload_file(str(output_path), output_key)
            logger.info("[render] output upload complete export_id=%s storage_key=%s", export.id, output_key)

            export.storage_key = output_key
            export.download_url = None
            export.url_expires_at = None
            export.srt_key = None

            if export.caption_format == CaptionFormat.srt and srt_local_path:
                srt_key = export_srt_key(str(export.user_id), str(clip.id), str(export.id))
                object_storage_client.upload_file(str(srt_local_path), srt_key)
                export.srt_key = srt_key
                logger.info("[render] srt sidecar upload complete export_id=%s srt_key=%s", export.id, srt_key)

            export.status = ExportStatus.ready
            export.error_message = None
            export.render_time_sec = int(round(time.perf_counter() - started))
            clip.status = ClipStatus.exported

            if render_job:
                render_job.status = JobStatus.done
                render_job.error = None
                render_job.completed_at = datetime.now(timezone.utc)

            db.commit()
            logger.info(
                "[render] final export status update export_id=%s status=%s render_time_sec=%s",
                export.id,
                export.status,
                export.render_time_sec,
            )

            return {"export_id": str(export.id), "status": export.status.value}
    except Exception as exc:
        user_message = str(exc)
        logger.exception("[render] render failed export_id=%s error=%s", export_id, user_message)

        with SyncSessionLocal() as db:
            load_result = db.execute(
                select(Export, Clip, Video)
                .join(Clip, Export.clip_id == Clip.id)
                .join(Video, Clip.video_id == Video.id)
                .where(Export.id == export_uuid)
            ).first()
            if load_result:
                export, _, video = load_result
                render_job = _find_render_job(db, video.id, job_uuid)

                export.status = ExportStatus.error
                export.error_message = user_message[:500]
                export.download_url = None
                export.url_expires_at = None

                if render_job:
                    render_job.status = JobStatus.failed
                    render_job.error = user_message[:500]
                    render_job.completed_at = datetime.now(timezone.utc)

                db.commit()
                logger.info("[render] final export status update export_id=%s status=error", export.id)

        return {"export_id": export_id, "status": "error", "message": user_message[:500]}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _enum_value(value):
    return value.value if hasattr(value, "value") else value
