from __future__ import annotations

from typing import Iterable

from app.models.clip import Clip
from app.models.export import AspectRatio
from app.models.transcript import TranscriptSegment
from app.models.video import Video
from app.schemas.editor import (
    EditorCanvas,
    EditorCaptionConfig,
    EditorCaptionGroupTransform,
    EditorCaptionOverride,
    EditorClipRef,
    EditorExportSettings,
    EditorProjectMeta,
    EditorProjectSchemaV1,
    EditorReframe,
    EditorTrim,
)
from app.services.editor_aspect import (
    aspect_ratio_dimensions,
    canvas_aspect_value,
    infer_editor_aspect_ratio,
    safe_area_preset_for_aspect,
)


def _caption_overrides_from_segments(segments: Iterable[TranscriptSegment], *, clip_start: float, clip_end: float) -> list[EditorCaptionOverride]:
    overrides: list[EditorCaptionOverride] = []
    for idx, segment in enumerate(segments):
        word = (segment.word or "").strip()
        if not word:
            continue
        start = max(float(segment.start_time), float(clip_start)) - float(clip_start)
        end = min(float(segment.end_time), float(clip_end)) - float(clip_start)
        if end <= start:
            continue
        overrides.append(
            EditorCaptionOverride(
                segment_id=str(segment.id) if segment.id else str(idx),
                start_sec=round(start, 3),
                end_sec=round(end, 3),
                text=word,
            )
        )
    return overrides


def build_default_project_json(
    *,
    video: Video,
    clip: Clip,
    aspect_ratio: AspectRatio,
    segments: Iterable[TranscriptSegment],
) -> EditorProjectSchemaV1:
    resolved_aspect = aspect_ratio if aspect_ratio != AspectRatio.original else infer_editor_aspect_ratio(video)
    width, height = aspect_ratio_dimensions(resolved_aspect)
    clip_start = float(clip.start_time)
    clip_end = float(clip.end_time)

    return EditorProjectSchemaV1(
        version=1,
        clip_ref=EditorClipRef(
            video_id=str(video.id),
            clip_id=str(clip.id),
            source_storage_key=video.storage_key,
            source_duration_sec=float(video.duration_sec) if video.duration_sec else None,
        ),
        meta=EditorProjectMeta(aspect_auto_inferred_v1=True),
        canvas=EditorCanvas(
            aspect_ratio=canvas_aspect_value(resolved_aspect),
            width=width,
            height=height,
            safe_area_preset=safe_area_preset_for_aspect(resolved_aspect),
        ),
        trim=EditorTrim(start_sec=clip_start, end_sec=clip_end),
        reframe=EditorReframe(anchor_x=0.5, anchor_y=0.5, zoom=1.0),
        captions=EditorCaptionConfig(
            enabled=True,
            active_word_highlight=False,
            group=EditorCaptionGroupTransform(anchor_x=0.5, anchor_y=0.85, scale=1.0),
            overrides=_caption_overrides_from_segments(segments, clip_start=clip_start, clip_end=clip_end),
        ),
        overlays=[],
        export=EditorExportSettings(),
    )


def clamp_trim(*, start_sec: float, end_sec: float, source_duration_sec: float | None) -> tuple[float, float]:
    safe_start = max(0.0, float(start_sec))
    safe_end = max(0.0, float(end_sec))
    if source_duration_sec and source_duration_sec > 0:
        safe_start = min(safe_start, float(source_duration_sec))
        safe_end = min(safe_end, float(source_duration_sec))
    if safe_end <= safe_start:
        safe_end = safe_start + 0.25
    return round(safe_start, 3), round(safe_end, 3)
