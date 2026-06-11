from __future__ import annotations

from typing import Literal

from app.models.export import AspectRatio
from app.models.video import Video

ASPECT_INFERENCE_TOLERANCE = 0.14

_STANDARD_RATIOS: tuple[tuple[AspectRatio, float], ...] = (
    (AspectRatio.vertical, 9 / 16),
    (AspectRatio.square, 1.0),
    (AspectRatio.landscape, 16 / 9),
)


def aspect_ratio_dimensions(aspect_ratio: AspectRatio) -> tuple[int, int]:
    if aspect_ratio == AspectRatio.square:
        return 720, 720
    if aspect_ratio == AspectRatio.landscape:
        return 1280, 720
    return 720, 1280


def safe_area_preset_for_aspect(
    aspect_ratio: AspectRatio,
) -> Literal["tiktok", "square", "landscape"]:
    if aspect_ratio == AspectRatio.square:
        return "square"
    if aspect_ratio == AspectRatio.landscape:
        return "landscape"
    return "tiktok"


def canvas_aspect_value(aspect_ratio: AspectRatio) -> Literal["9:16", "1:1", "16:9"]:
    if aspect_ratio == AspectRatio.square:
        return "1:1"
    if aspect_ratio == AspectRatio.landscape:
        return "16:9"
    return "9:16"


def parse_resolution(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    raw = value.strip().lower().replace(" ", "")
    if "x" not in raw:
        return None
    left, right = raw.split("x", 1)
    try:
        width = int(left)
        height = int(right)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _metadata_dimension(metadata: dict, *keys: str) -> int | None:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def extract_video_dimensions(video: Video) -> tuple[int, int] | None:
    parsed = parse_resolution(video.resolution)
    if parsed:
        return parsed

    metadata = video.external_metadata_json or {}
    width = _metadata_dimension(metadata, "width", "video_width", "source_width")
    height = _metadata_dimension(metadata, "height", "video_height", "source_height")
    if width and height:
        return width, height

    preview_info = metadata.get("editor_preview_probe")
    if isinstance(preview_info, dict):
        width = _metadata_dimension(preview_info, "width")
        height = _metadata_dimension(preview_info, "height")
        if width and height:
            return width, height

    return None


def infer_aspect_ratio_from_dimensions(width: int, height: int) -> AspectRatio:
    if width <= 0 or height <= 0:
        return AspectRatio.square

    ratio = float(width) / float(height)
    nearest = min(_STANDARD_RATIOS, key=lambda candidate: abs(ratio - candidate[1]))
    _, standard_ratio = nearest
    relative_delta = abs(ratio - standard_ratio) / standard_ratio
    if relative_delta > ASPECT_INFERENCE_TOLERANCE:
        return AspectRatio.square
    return nearest[0]


def infer_editor_aspect_ratio(video: Video) -> AspectRatio:
    dims = extract_video_dimensions(video)
    if not dims:
        return AspectRatio.square
    width, height = dims
    return infer_aspect_ratio_from_dimensions(width, height)
