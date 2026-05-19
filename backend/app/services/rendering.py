import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.models.transcript import TranscriptSegment

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubtitleCue:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class CaptionLayout:
    play_res_x: int
    play_res_y: int
    font_size: int
    margin_l: int
    margin_r: int
    margin_v: int
    max_chars_per_line: int
    max_lines: int = 3


@dataclass(frozen=True)
class CropWindow:
    x: int
    y: int
    width: int
    height: int
    source_width: int
    source_height: int


def has_video_stream(media_path: str) -> bool:
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        media_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed while reading media streams: {result.stderr}")

    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    return any(stream.get("codec_type") == "video" for stream in streams)


def build_subtitle_cues(
    segments: Iterable[TranscriptSegment],
    clip_start: float,
    clip_end: float,
) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    words: list[str] = []
    cue_start: float | None = None
    prev_end: float | None = None

    def flush() -> None:
        nonlocal words, cue_start, prev_end
        if cue_start is None or prev_end is None or not words:
            words = []
            cue_start = None
            prev_end = None
            return

        start = max(cue_start, 0.0)
        end = max(prev_end, start + 0.2)
        text = _normalize_text(" ".join(words))
        if text:
            cues.append(SubtitleCue(start=round(start, 3), end=round(end, 3), text=text))

        words = []
        cue_start = None
        prev_end = None

    for segment in segments:
        word = (segment.word or "").strip()
        if not word:
            continue

        abs_start = max(float(segment.start_time), float(clip_start))
        abs_end = min(float(segment.end_time), float(clip_end))
        if abs_end <= abs_start:
            continue

        rel_start = abs_start - float(clip_start)
        rel_end = abs_end - float(clip_start)

        if cue_start is None:
            cue_start = rel_start
        else:
            gap = rel_start - (prev_end or rel_start)
            should_break = (
                gap > 0.6
                or len(words) >= 8
                or (rel_end - cue_start) >= 2.8
                or _ends_sentence(words[-1] if words else "")
            )
            if should_break:
                flush()
                cue_start = rel_start

        words.append(word)
        prev_end = rel_end

    flush()
    return cues


def write_srt(cues: list[SubtitleCue], output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for idx, cue in enumerate(cues, start=1):
        lines.append(str(idx))
        lines.append(f"{_format_srt_timestamp(cue.start)} --> {_format_srt_timestamp(cue.end)}")
        lines.append(cue.text)
        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    logger.info("Wrote SRT subtitles: %s", output_path)
    return output_path


def write_ass(
    cues: list[SubtitleCue],
    output_path: str,
    caption_style: str | None,
    caption_color_variant: str | None,
    aspect_ratio: str,
    target_width: int,
    target_height: int,
    caption_vertical_position: float | None = None,
    caption_scale: float | None = None,
) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    layout = _caption_layout(
        aspect_ratio=aspect_ratio,
        caption_style=caption_style,
        target_width=target_width,
        target_height=target_height,
        caption_vertical_position=caption_vertical_position,
        caption_scale=caption_scale,
    )
    style_line = _ass_style_line(caption_style, caption_color_variant, layout)

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        f"PlayResX: {layout.play_res_x}",
        f"PlayResY: {layout.play_res_y}",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding",
        style_line,
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]

    events = []
    for cue in cues:
        wrapped = _wrap_caption_text(
            cue.text,
            max_chars_per_line=layout.max_chars_per_line,
            max_lines=layout.max_lines,
        )
        events.append(
            f"Dialogue: 0,{_format_ass_timestamp(cue.start)},{_format_ass_timestamp(cue.end)},"
            f"Default,,0,0,0,,{_escape_ass_text(wrapped)}"
        )

    path.write_text("\n".join(header + events) + "\n", encoding="utf-8")
    logger.info("Wrote ASS subtitles: %s", output_path)
    return output_path


def render_video_clip(
    source_path: str,
    output_path: str,
    clip_start: float,
    clip_end: float,
    aspect_ratio: str,
    target_width: int,
    target_height: int,
    burned_ass_path: str | None = None,
    frame_anchor_x: float | None = None,
    frame_anchor_y: float | None = None,
    frame_zoom: float | None = None,
) -> str:
    if clip_end <= clip_start:
        raise ValueError("Clip end time must be greater than start time")

    crop_window = resolve_crop_window(
        aspect_ratio=aspect_ratio,
        source_path=source_path,
        frame_anchor_x=frame_anchor_x,
        frame_anchor_y=frame_anchor_y,
        frame_zoom=frame_zoom,
    )
    logger.info(
        "Resolved crop window aspect=%s zoom=%.3f anchor=(%.3f, %.3f) source=%sx%s crop=x%s:y%s:w%s:h%s",
        aspect_ratio,
        _normalize_frame_zoom(frame_zoom),
        _normalize_anchor(frame_anchor_x),
        _normalize_anchor(frame_anchor_y),
        crop_window.source_width,
        crop_window.source_height,
        crop_window.x,
        crop_window.y,
        crop_window.width,
        crop_window.height,
    )

    filter_chain = [
        f"crop={crop_window.width}:{crop_window.height}:{crop_window.x}:{crop_window.y}",
        f"scale={target_width}:{target_height}:flags=lanczos",
        "setsar=1",
        "format=yuv420p",
    ]

    if burned_ass_path:
        ass_filter_path = _escape_filter_path(burned_ass_path)
        filter_chain.append(f"subtitles='{ass_filter_path}'")

    vf_arg = ",".join(filter_chain)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{clip_start:.3f}",
        "-to", f"{clip_end:.3f}",
        "-i", source_path,
        "-vf", vf_arg,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg render failed: {result.stderr}")

    out = Path(output_path)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("Render completed but output file is missing or empty")

    logger.info("Rendered output video: %s", output_path)
    return output_path


def resolve_output_dimensions(aspect_ratio: str, source_path: str) -> tuple[int, int]:
    normalized = (aspect_ratio or "").strip()
    if normalized == "1:1":
        return 720, 720
    if normalized == "9:16":
        return 720, 1280
    if normalized == "16:9":
        return 1280, 720
    if normalized == "original":
        source_width, source_height = _probe_video_dimensions(source_path)
        if source_width <= 0 or source_height <= 0:
            raise ValueError("Unable to resolve source dimensions for original aspect export")
        max_dim = 1280
        scale = min(1.0, max_dim / float(max(source_width, source_height)))
        target_width = _ensure_even(int(round(source_width * scale)))
        target_height = _ensure_even(int(round(source_height * scale)))
        return max(2, target_width), max(2, target_height)
    raise ValueError(f"Unsupported aspect ratio: {aspect_ratio}")


def resolve_crop_window(
    aspect_ratio: str,
    source_path: str,
    frame_anchor_x: float | None = None,
    frame_anchor_y: float | None = None,
    frame_zoom: float | None = None,
) -> CropWindow:
    source_width, source_height = _probe_video_dimensions(source_path)
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Unable to resolve source dimensions for export reframing")

    source_aspect = source_width / float(source_height)
    target_aspect = _target_aspect_ratio(aspect_ratio, source_aspect)
    zoom = _normalize_frame_zoom(frame_zoom)
    anchor_x = _normalize_anchor(frame_anchor_x)
    anchor_y = _normalize_anchor(frame_anchor_y)

    if source_aspect >= target_aspect:
        base_height = float(source_height)
        base_width = base_height * target_aspect
    else:
        base_width = float(source_width)
        base_height = base_width / target_aspect

    crop_width = min(float(source_width), base_width / zoom)
    crop_height = min(float(source_height), base_height / zoom)

    # Keep the crop ratio stable after float math and before integer conversion.
    if crop_width / crop_height > target_aspect:
        crop_width = crop_height * target_aspect
    else:
        crop_height = crop_width / target_aspect

    crop_width_int = _clamp_even_dimension(int(round(crop_width)), source_width)
    crop_height_int = _clamp_even_dimension(int(round(crop_height)), source_height)

    max_x = max(0, source_width - crop_width_int)
    max_y = max(0, source_height - crop_height_int)

    center_x = anchor_x * source_width
    center_y = anchor_y * source_height
    raw_x = int(round(center_x - (crop_width_int / 2.0)))
    raw_y = int(round(center_y - (crop_height_int / 2.0)))

    crop_x = _clamp_even_offset(raw_x, max_x)
    crop_y = _clamp_even_offset(raw_y, max_y)

    return CropWindow(
        x=crop_x,
        y=crop_y,
        width=crop_width_int,
        height=crop_height_int,
        source_width=source_width,
        source_height=source_height,
    )


def _target_aspect_ratio(aspect_ratio: str, source_aspect: float) -> float:
    normalized = (aspect_ratio or "").strip()
    if normalized == "original":
        return source_aspect
    if normalized == "9:16":
        return 9.0 / 16.0
    if normalized == "16:9":
        return 16.0 / 9.0
    if normalized == "1:1":
        return 1.0
    raise ValueError(f"Unsupported aspect ratio: {aspect_ratio}")


def _normalize_anchor(value: float | None) -> float:
    if value is None:
        return 0.5
    return min(1.0, max(0.0, float(value)))


def _normalize_frame_zoom(value: float | None) -> float:
    if value is None:
        return 1.0
    return min(3.0, max(1.0, float(value)))


def _clamp_even_dimension(value: int, source_max: int) -> int:
    bounded = min(max(2, value), max(2, source_max))
    if bounded % 2 == 1:
        bounded -= 1
    if bounded < 2:
        bounded = 2
    if bounded > source_max:
        bounded = source_max if source_max % 2 == 0 else max(2, source_max - 1)
    return bounded


def _clamp_even_offset(value: int, max_offset: int) -> int:
    bounded = min(max(0, value), max_offset)
    if bounded % 2 == 1:
        bounded -= 1
    if bounded < 0:
        bounded = 0
    if bounded > max_offset:
        bounded = max_offset
    return bounded


def _normalize_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    compact = re.sub(r"\s+([,.;:!?])", r"\1", compact)
    return compact


def _ends_sentence(word: str) -> bool:
    stripped = word.strip()
    return stripped.endswith(".") or stripped.endswith("?") or stripped.endswith("!")


def _format_srt_timestamp(seconds: float) -> str:
    total_ms = int(round(max(seconds, 0.0) * 1000))
    hours = total_ms // 3_600_000
    minutes = (total_ms % 3_600_000) // 60_000
    secs = (total_ms % 60_000) // 1000
    millis = total_ms % 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _format_ass_timestamp(seconds: float) -> str:
    total_cs = int(round(max(seconds, 0.0) * 100))
    hours = total_cs // 360_000
    minutes = (total_cs % 360_000) // 6000
    secs = (total_cs % 6000) // 100
    centis = total_cs % 100
    return f"{hours}:{minutes:02}:{secs:02}.{centis:02}"


def _ass_style_line(
    caption_style: str | None,
    caption_color_variant: str | None,
    layout: CaptionLayout,
) -> str:
    style = caption_style or "clean_minimal"
    variant = caption_color_variant or "classic"
    typography_presets: dict[str, dict[str, int | float]] = {
        "bold_boxed": {"bold": -1, "italic": 0, "border_style": 3, "outline": 1.0, "shadow": 0},
        "sermon_quote": {"bold": 0, "italic": 1, "border_style": 1, "outline": 2.2, "shadow": 0},
        "clean_minimal": {"bold": 0, "italic": 0, "border_style": 1, "outline": 1.8, "shadow": 0},
        "kinetic_bold": {"bold": -1, "italic": 0, "border_style": 3, "outline": 0.8, "shadow": 0},
        "cinema_outline": {"bold": -1, "italic": 0, "border_style": 1, "outline": 3.0, "shadow": 1},
        "clean_highlight": {"bold": 0, "italic": 0, "border_style": 3, "outline": 0.6, "shadow": 0},
    }
    variant_palettes: dict[str, dict[str, dict[str, str]]] = {
        "bold_boxed": {
            "classic": {"primary": "&H00FFFFFF", "outline_colour": "&H00141414", "back_colour": "&H96000000"},
            "warm": {"primary": "&H00C5F8FF", "outline_colour": "&H0014232E", "back_colour": "&H96411A00"},
            "cool": {"primary": "&H00FFF2D9", "outline_colour": "&H002B1B12", "back_colour": "&H96803B00"},
        },
        "sermon_quote": {
            "classic": {"primary": "&H00F5F5F5", "outline_colour": "&H00202020", "back_colour": "&H5A000000"},
            "warm": {"primary": "&H00D9F0FF", "outline_colour": "&H001E2B38", "back_colour": "&H5A2A1200"},
            "cool": {"primary": "&H00FFF0DB", "outline_colour": "&H00331E15", "back_colour": "&H5A4D2300"},
        },
        "clean_minimal": {
            "classic": {"primary": "&H00FFFFFF", "outline_colour": "&H00141414", "back_colour": "&H46000000"},
            "warm": {"primary": "&H00D5F4FF", "outline_colour": "&H001A2B38", "back_colour": "&H46321900"},
            "cool": {"primary": "&H00FFF4E3", "outline_colour": "&H00362618", "back_colour": "&H46513100"},
        },
        "kinetic_bold": {
            "classic": {"primary": "&H00FFFFFF", "outline_colour": "&H000E0E0E", "back_colour": "&HAA000000"},
            "warm": {"primary": "&H00BFF3FF", "outline_colour": "&H001D2E3A", "back_colour": "&HAA3D1800"},
            "cool": {"primary": "&H00FFEBD1", "outline_colour": "&H003E2815", "back_colour": "&HAA6D3400"},
        },
        "cinema_outline": {
            "classic": {"primary": "&H00FFFFFF", "outline_colour": "&H000A0A0A", "back_colour": "&H22000000"},
            "warm": {"primary": "&H00CBEFFF", "outline_colour": "&H001D2E40", "back_colour": "&H22301A00"},
            "cool": {"primary": "&H00FFF0DE", "outline_colour": "&H003D2516", "back_colour": "&H22482700"},
        },
        "clean_highlight": {
            "classic": {"primary": "&H00FFFFFF", "outline_colour": "&H00141414", "back_colour": "&H76000000"},
            "warm": {"primary": "&H00D2F2FF", "outline_colour": "&H001A2B38", "back_colour": "&H76331A00"},
            "cool": {"primary": "&H00FFF1DD", "outline_colour": "&H00382618", "back_colour": "&H76573400"},
        },
    }
    preset = typography_presets.get(style, typography_presets["clean_minimal"])
    palette_by_variant = variant_palettes.get(style, variant_palettes["clean_minimal"])
    palette = palette_by_variant.get(variant, palette_by_variant["classic"])

    return (
        "Style: Default,Arial,"
        f"{layout.font_size},"
        f"{palette['primary']},&H000000FF,{palette['outline_colour']},{palette['back_colour']},"
        f"{preset['bold']},{preset['italic']},0,0,100,100,0,0,{preset['border_style']},{float(preset['outline']):.1f},{preset['shadow']},"
        f"2,{layout.margin_l},{layout.margin_r},{layout.margin_v},1"
    )


def _caption_layout(
    aspect_ratio: str,
    caption_style: str | None,
    target_width: int,
    target_height: int,
    caption_vertical_position: float | None,
    caption_scale: float | None,
) -> CaptionLayout:
    if aspect_ratio == "9:16" or target_width < target_height:
        profile = "vertical"
    elif aspect_ratio == "1:1" or abs(target_width - target_height) <= 16:
        profile = "square"
    else:
        profile = "landscape"

    safe_width = min(target_width, target_height)

    if profile == "vertical":
        base_font = max(26, int(round(safe_width * 0.048)))
        margin_l = margin_r = max(62, int(round(target_width * 0.12)))
        default_margin_v = max(120, int(round(target_height * 0.14)))
        max_chars = 20
    elif profile == "square":
        base_font = max(30, int(round(safe_width * 0.056)))
        margin_l = margin_r = max(56, int(round(target_width * 0.10)))
        default_margin_v = max(84, int(round(target_height * 0.11)))
        max_chars = 28
    else:
        base_font = max(34, int(round(safe_width * 0.063)))
        margin_l = margin_r = max(72, int(round(target_width * 0.08)))
        default_margin_v = max(72, int(round(target_height * 0.11)))
        max_chars = 34

    style = caption_style or "clean_minimal"
    style_font_scale = {
        "bold_boxed": 1.02,
        "sermon_quote": 0.96,
        "clean_minimal": 0.92,
        "kinetic_bold": 1.08,
        "cinema_outline": 1.00,
        "clean_highlight": 0.96,
    }
    font_size = int(round(base_font * style_font_scale.get(style, 0.92)))

    if caption_scale is None:
        scale = 1.0
    else:
        scale = min(2.0, max(0.25, float(caption_scale)))
    font_size = int(round(font_size * scale))

    if caption_vertical_position is not None:
        position_pct = min(90.0, max(5.0, float(caption_vertical_position)))
        margin_v = int(round(target_height * (position_pct / 100.0)))
    else:
        margin_v = default_margin_v

    return CaptionLayout(
        play_res_x=target_width,
        play_res_y=target_height,
        font_size=max(22, font_size),
        margin_l=margin_l,
        margin_r=margin_r,
        margin_v=margin_v,
        max_chars_per_line=max_chars,
        max_lines=3,
    )


def _escape_ass_text(text: str) -> str:
    # Preserve ASS hard/soft line-break tokens while escaping other backslashes.
    hard_break_token = "__ASS_HARD_BREAK__"
    soft_break_token = "__ASS_SOFT_BREAK__"
    escaped = (
        text.replace(r"\N", hard_break_token)
        .replace(r"\n", soft_break_token)
        .replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
    )
    return escaped.replace(hard_break_token, r"\N").replace(soft_break_token, r"\n")


def _wrap_caption_text(text: str, max_chars_per_line: int, max_lines: int) -> str:
    words = [part for part in re.split(r"\s+", text.strip()) if part]
    if not words:
        return ""

    lines: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        projected_len = len(word) if not current else current_len + 1 + len(word)
        if current and projected_len > max_chars_per_line:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
            if len(lines) >= max_lines:
                break
        else:
            current.append(word)
            current_len = projected_len

    if len(lines) < max_lines and current:
        lines.append(" ".join(current))

    if not lines:
        return ""

    if len(lines) > max_lines:
        lines = lines[:max_lines]

    consumed_words = sum(len(line.split()) for line in lines)
    if consumed_words < len(words):
        lines[-1] = lines[-1].rstrip(" .,:;!?") + "..."

    return r"\N".join(lines)


def _escape_filter_path(path: str) -> str:
    return (
        path.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
    )


def _probe_video_dimensions(media_path: str) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-select_streams",
        "v:0",
        media_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed while probing dimensions: {result.stderr}")
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    if not streams:
        return 0, 0
    width = int(streams[0].get("width") or 0)
    height = int(streams[0].get("height") or 0)
    return width, height


def _ensure_even(value: int) -> int:
    if value % 2 == 0:
        return value
    return value - 1 if value > 1 else 2
