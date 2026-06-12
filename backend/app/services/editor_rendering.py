from __future__ import annotations

import math
import shlex
import subprocess
from pathlib import Path

from app.schemas.editor import EditorOverlay, EditorProjectSchemaV1


def _normalize_multiline_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _escape_filter_value(value: str) -> str:
    escaped: list[str] = []
    for char in value:
        if char in {"\\", "'", ":", ",", ";", "[", "]"}:
            escaped.append(f"\\{char}")
            continue
        escaped.append(char)
    return "".join(escaped)


def _write_drawtext_text_file(drawtext_dir: Path, *, prefix: str, index: int, text: str) -> str:
    file_path = drawtext_dir / f"{prefix}_{index:04d}.txt"
    file_path.write_text(_normalize_multiline_text(text), encoding="utf-8")
    return _escape_filter_value(str(file_path))


def _normalize_hex_color(value: str, fallback: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return fallback
    if not raw.startswith("#"):
        raw = f"#{raw}"
    if len(raw) not in (7, 9):
        return fallback
    try:
        int(raw[1:], 16)
    except ValueError:
        return fallback
    return raw


def _hex_to_ffmpeg_font_color(value: str, fallback: str = "#FFFFFF") -> str:
    color = _normalize_hex_color(value, fallback)
    if len(color) == 9:
        rgb = color[1:7]
        alpha = int(color[7:9], 16) / 255.0
        return f"#{rgb}@{alpha:.3f}"
    return f"#{color[1:7]}"


def _hex_to_ffmpeg_box_color(value: str, fallback: str = "#000000CC") -> str:
    color = _normalize_hex_color(value, fallback)
    if len(color) == 9:
        rgb = color[1:7]
        alpha = int(color[7:9], 16) / 255.0
        return f"#{rgb}@{alpha:.3f}"
    return f"#{color[1:7]}@0.65"


def _overlay_enable_expr(start_sec: float, end_sec: float) -> str:
    start = max(0.0, float(start_sec))
    end = max(start + 0.01, float(end_sec))
    return f"between(t\\,{start:.3f}\\,{end:.3f})"


def _build_text_filter(
    overlay: EditorOverlay,
    target_width: int,
    target_height: int,
    *,
    textfile_path: str,
) -> str:
    style = overlay.style
    font_size = max(14, int(round((style.font_size if style and style.font_size else 42))))
    color = _hex_to_ffmpeg_font_color(style.color if style and style.color else "#FFFFFF")
    box_color = _hex_to_ffmpeg_box_color(style.bg_color if style and style.bg_color else "#000000CC")

    center_x = max(0.0, min(1.0, float(overlay.x))) * target_width
    center_y = max(0.0, min(1.0, float(overlay.y))) * target_height
    x_expr = f"{center_x:.2f}-text_w/2"
    y_expr = f"{center_y:.2f}-text_h/2"

    return (
        "drawtext="
        "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"textfile={textfile_path}:"
        "expansion=none:"
        f"x={x_expr}:"
        f"y={y_expr}:"
        f"fontsize={font_size}:"
        f"fontcolor={color}:"
        "line_spacing=6:"
        "borderw=0:"
        "box=1:"
        f"boxcolor={box_color}:"
        "boxborderw=12:"
        f"enable={_overlay_enable_expr(overlay.start_sec, overlay.end_sec)}"
    )


def _build_base_filter(
    *,
    target_width: int,
    target_height: int,
    anchor_x: float,
    anchor_y: float,
    zoom: float,
    fit_mode: str | None,
) -> list[str]:
    safe_zoom = min(3.0, max(1.0, float(zoom)))
    safe_anchor_x = min(1.0, max(0.0, float(anchor_x)))
    safe_anchor_y = min(1.0, max(0.0, float(anchor_y)))
    safe_fit_mode = "fit" if fit_mode == "fit" else "fill"
    target_ratio = float(target_width) / float(target_height)

    if safe_fit_mode == "fit":
        filters: list[str] = [
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease:flags=lanczos",
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black",
        ]
        if safe_zoom > 1.0:
            crop_expr_w = f"{target_width}/{safe_zoom:.4f}"
            crop_expr_h = f"{target_height}/{safe_zoom:.4f}"
            crop_x = f"max(0\\,min({target_width}-{crop_expr_w}\\,{safe_anchor_x:.6f}*{target_width}-{crop_expr_w}/2))"
            crop_y = f"max(0\\,min({target_height}-{crop_expr_h}\\,{safe_anchor_y:.6f}*{target_height}-{crop_expr_h}/2))"
            filters.extend(
                [
                    f"crop={crop_expr_w}:{crop_expr_h}:{crop_x}:{crop_y}",
                    f"scale={target_width}:{target_height}:flags=lanczos",
                ]
            )
        filters.extend(["setsar=1", "format=yuv420p"])
        return filters

    # Fill mode crops source into target ratio, then applies zoom and anchor-based framing.
    base_crop_w = f"if(gte(iw/ih\\,{target_ratio:.8f})\\,ih*{target_ratio:.8f}\\,iw)"
    base_crop_h = f"if(gte(iw/ih\\,{target_ratio:.8f})\\,ih\\,iw/{target_ratio:.8f})"
    crop_expr_w = f"{base_crop_w}/{safe_zoom:.4f}"
    crop_expr_h = f"{base_crop_h}/{safe_zoom:.4f}"
    crop_x = f"max(0\\,min(iw-{crop_expr_w}\\,{safe_anchor_x:.6f}*iw-{crop_expr_w}/2))"
    crop_y = f"max(0\\,min(ih-{crop_expr_h}\\,{safe_anchor_y:.6f}*ih-{crop_expr_h}/2))"

    return [
        f"crop={crop_expr_w}:{crop_expr_h}:{crop_x}:{crop_y}",
        f"scale={target_width}:{target_height}:flags=lanczos",
        "setsar=1",
        "format=yuv420p",
    ]


def _build_caption_drawtext_filters(
    project: EditorProjectSchemaV1,
    target_width: int,
    target_height: int,
    *,
    drawtext_dir: Path,
) -> list[str]:
    captions = project.captions
    if not captions.enabled:
        return []

    style = captions.style
    group = captions.group
    group_scale = min(3.0, max(0.35, float(group.scale) if group.scale is not None else 1.0))
    font_size = max(14, int(round(style.font_size * group_scale)))
    color = _hex_to_ffmpeg_font_color(style.text_color)
    box_color = _hex_to_ffmpeg_box_color(style.bg_color)
    anchor_x = min(1.0, max(0.0, float(group.anchor_x) if group.anchor_x is not None else 0.5))

    if group.anchor_y is None:
        if style.position == "top":
            anchor_y = 0.12
        elif style.position == "middle":
            anchor_y = 0.5
        else:
            anchor_y = 0.85
    else:
        anchor_y = min(1.0, max(0.0, float(group.anchor_y)))

    x_expr = f"{anchor_x * target_width:.2f}-text_w/2"
    y_expr = f"{anchor_y * target_height:.2f}-text_h/2"

    items = list(captions.overrides)
    if len(items) > 120:
        compacted: list = []
        current = None
        for item in items:
            text = (item.text or "").strip()
            if not text:
                continue
            if current is None:
                current = {
                    "start_sec": float(item.start_sec),
                    "end_sec": float(item.end_sec),
                    "text": text,
                }
                continue

            gap = float(item.start_sec) - float(current["end_sec"])
            next_text = f"{current['text']} {text}".strip()
            next_duration = float(item.end_sec) - float(current["start_sec"])
            if gap <= 0.32 and len(next_text) <= 52 and next_duration <= 2.8:
                current["text"] = next_text
                current["end_sec"] = float(item.end_sec)
                continue

            compacted.append(current)
            current = {
                "start_sec": float(item.start_sec),
                "end_sec": float(item.end_sec),
                "text": text,
            }

        if current is not None:
            compacted.append(current)

        class _Segment:
            def __init__(self, start_sec: float, end_sec: float, text: str):
                self.start_sec = start_sec
                self.end_sec = end_sec
                self.text = text

        items = [_Segment(seg["start_sec"], seg["end_sec"], seg["text"]) for seg in compacted]

    filters: list[str] = []
    for index, item in enumerate(items, start=1):
        text = (item.text or "").strip()
        if not text:
            continue
        if style.uppercase:
            text = text.upper()
        textfile_path = _write_drawtext_text_file(drawtext_dir, prefix="caption", index=index, text=text)
        filters.append(
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"textfile={textfile_path}:"
            "expansion=none:"
            f"x={x_expr}:"
            f"y={y_expr}:"
            f"fontsize={font_size}:"
            f"fontcolor={color}:"
            "line_spacing=6:"
            "box=1:"
            f"boxcolor={box_color}:"
            "boxborderw=10:"
            f"enable={_overlay_enable_expr(item.start_sec, item.end_sec)}"
        )
    return filters


def _rotation_enabled(value: float) -> bool:
    return abs(float(value)) > 0.001


def build_editor_ffmpeg_command(
    *,
    source_path: str,
    output_path: str,
    project: EditorProjectSchemaV1,
    trim_start_sec: float,
    trim_end_sec: float,
    target_width: int,
    target_height: int,
    image_inputs: list[tuple[EditorOverlay, str, int]],
) -> list[str]:
    cmd: list[str] = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{trim_start_sec:.3f}",
        "-to",
        f"{trim_end_sec:.3f}",
        "-i",
        source_path,
    ]

    for _, image_path, _ in image_inputs:
        cmd.extend(["-i", image_path])

    filter_nodes: list[str] = []
    chain_label = "v0"
    drawtext_dir = Path(output_path).parent / "drawtext"
    drawtext_dir.mkdir(parents=True, exist_ok=True)

    base_filters = _build_base_filter(
        target_width=target_width,
        target_height=target_height,
        anchor_x=project.reframe.anchor_x,
        anchor_y=project.reframe.anchor_y,
        zoom=project.reframe.zoom,
        fit_mode=project.reframe.fit_mode,
    )
    filter_nodes.append(f"[0:v]{','.join(base_filters)}[{chain_label}]")

    text_overlays = [overlay for overlay in project.overlays if overlay.type == "text" and (overlay.content or "").strip()]
    text_overlays.sort(key=lambda item: item.z_index)

    for index, overlay in enumerate(text_overlays, start=1):
        next_label = f"vt{index}"
        textfile_path = _write_drawtext_text_file(
            drawtext_dir,
            prefix="overlay_text",
            index=index,
            text=(overlay.content or "").strip(),
        )
        draw_filter = _build_text_filter(
            overlay,
            target_width,
            target_height,
            textfile_path=textfile_path,
        )
        filter_nodes.append(f"[{chain_label}]{draw_filter}[{next_label}]")
        chain_label = next_label

    caption_filters = _build_caption_drawtext_filters(
        project,
        target_width,
        target_height,
        drawtext_dir=drawtext_dir,
    )
    for index, draw_filter in enumerate(caption_filters, start=1):
        next_label = f"vc{index}"
        filter_nodes.append(f"[{chain_label}]{draw_filter}[{next_label}]")
        chain_label = next_label

    image_overlays = sorted(image_inputs, key=lambda pair: pair[0].z_index)
    for index, (overlay, _, input_index) in enumerate(image_overlays, start=1):

        scaled_w = max(8, int(round(max(0.02, min(1.0, overlay.width)) * target_width)))
        scaled_h = max(8, int(round(max(0.02, min(1.0, overlay.height)) * target_height)))
        scaled_w = scaled_w + (scaled_w % 2)
        scaled_h = scaled_h + (scaled_h % 2)
        img_label = f"img{index}"
        img_filter = f"[{input_index}:v]scale={scaled_w}:{scaled_h},format=rgba"
        if _rotation_enabled(overlay.rotation_deg):
            radians = float(overlay.rotation_deg) * math.pi / 180.0
            img_filter += f",rotate={radians:.6f}:fillcolor=none"
        img_filter += f"[{img_label}]"
        filter_nodes.append(img_filter)

        center_x = max(0.0, min(1.0, float(overlay.x))) * target_width
        center_y = max(0.0, min(1.0, float(overlay.y))) * target_height
        x_expr = f"{center_x:.2f}-overlay_w/2"
        y_expr = f"{center_y:.2f}-overlay_h/2"

        next_label = f"vi{index}"
        filter_nodes.append(
            f"[{chain_label}][{img_label}]overlay={x_expr}:{y_expr}:"
            f"enable={_overlay_enable_expr(overlay.start_sec, overlay.end_sec)}:eof_action=pass[{next_label}]"
        )
        chain_label = next_label

    filter_complex = ";".join(filter_nodes)
    filter_script_path = Path(output_path).parent / "filtergraph.txt"
    filter_script_path.write_text(filter_complex, encoding="utf-8")

    cmd.extend(
        [
            "-filter_complex_script",
            str(filter_script_path),
            "-map",
            f"[{chain_label}]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            output_path,
        ]
    )

    return cmd


def run_editor_render(cmd: list[str], *, timeout_seconds: int) -> tuple[str, int]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stderr_tail = stderr[-4000:] if stderr else "Unknown ffmpeg error"
        raise RuntimeError(f"FFmpeg render failed: {stderr_tail}")

    output_path = cmd[-1]
    output = Path(output_path)
    if not output.exists() or output.stat().st_size <= 0:
        raise RuntimeError("FFmpeg render produced no output file")

    return " ".join(shlex.quote(part) for part in cmd), int(output.stat().st_size)
