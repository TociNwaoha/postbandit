"""Caption preset implementations for FFmpeg ASS rendering."""

from __future__ import annotations

import random
from typing import Any


def generate_scattered_positions(
    word_count: int,
    width: int = 1080,
    height: int = 1920,
    seed: str | None = None,
) -> list[tuple[int, int]]:
    """Generate reproducible, jittered positions in a three-column grid."""
    rng = random.Random(seed)
    columns = 3
    rows = 4
    margin_x = max(24, round(width * (90 / 1080)))
    margin_y = max(36, round(height * (180 / 1920)))
    usable_width = width - (2 * margin_x)
    usable_height = height - (2 * margin_y)
    cell_width = usable_width / columns
    cell_height = usable_height / rows

    positions: list[tuple[int, int]] = []
    for index in range(word_count):
        column = index % columns
        row = (index // columns) % rows
        center_x = margin_x + (column * cell_width) + (cell_width / 2)
        center_y = margin_y + (row * cell_height) + (cell_height / 2)
        x = round(center_x + rng.uniform(-cell_width * 0.05, cell_width * 0.05))
        y = round(center_y + rng.uniform(-cell_height * 0.05, cell_height * 0.05))
        positions.append((x, y))
    return positions


def generate_music_video_ass(
    words: list[dict[str, Any]],
    video_width: int,
    video_height: int,
    font_name: str = "DejaVu Sans",
    font_size: int = 82,
    hold_seconds: float = 1.0,
    clip_id: str | None = None,
    clip_duration: float | None = None,
) -> str:
    """Build an ASS script whose words accumulate at scattered screen positions."""
    clean_words = [word for word in words if str(word.get("word") or "").strip()]
    if not clean_words:
        return ""

    def format_time(seconds: float) -> str:
        total_centiseconds = max(0, round(seconds * 100))
        hours, remainder = divmod(total_centiseconds, 360000)
        minutes, remainder = divmod(remainder, 6000)
        seconds_part, centiseconds = divmod(remainder, 100)
        return f"{hours}:{minutes:02d}:{seconds_part:02d}.{centiseconds:02d}"

    def escape_text(value: str) -> str:
        return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", " ")

    positions = generate_scattered_positions(len(clean_words), video_width, video_height, clip_id)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {video_width}",
        f"PlayResY: {video_height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Music,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,3,0,1,0,0,5,10,10,10,1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]

    for word_data, (x, y) in zip(clean_words, positions):
        start = max(0.0, float(word_data.get("start", 0.0)))
        end = start + max(0.1, hold_seconds)
        if clip_duration is not None:
            end = min(end, clip_duration)
        if end <= start:
            continue
        text = escape_text(str(word_data["word"]).strip().upper())
        lines.append(
            f"Dialogue: 0,{format_time(start)},{format_time(end)},Music,,0,0,0,,{{\\an5\\pos({x},{y})}}{text}"
        )

    return "\n".join(lines) + "\n"
