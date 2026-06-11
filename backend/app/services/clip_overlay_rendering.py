from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT_PATH, size=size)
    except OSError:
        return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    box = draw.textbbox((0, 0), text, font=font, stroke_width=1)
    return float(box[2] - box[0])


def render_highlighted_text_layer(
    config: dict,
    *,
    target_width: int,
    target_height: int,
    output_path: str,
) -> str:
    text = " ".join(str(config.get("text") or "").split())
    if not text:
        raise ValueError("Overlay text is empty")

    font_size = max(16, min(160, int(config.get("font_size") or 52)))
    font = _load_font(font_size)
    canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    words = text.split()
    space_width = _text_width(draw, " ", font)
    max_line_width = target_width * 0.82

    lines: list[list[tuple[int, str, float]]] = []
    current: list[tuple[int, str, float]] = []
    current_width = 0.0
    for index, word in enumerate(words):
        word_width = _text_width(draw, word, font)
        next_width = word_width if not current else current_width + space_width + word_width
        if current and next_width > max_line_width:
            lines.append(current)
            current = []
            current_width = 0.0
        if current:
            current_width += space_width
        current.append((index, word, word_width))
        current_width += word_width
    if current:
        lines.append(current)

    highlight_map = {
        int(item["word_index"]): str(item["color"])
        for item in config.get("highlights") or []
        if isinstance(item, dict) and "word_index" in item and "color" in item
    }
    text_color = str(config.get("text_color") or "#FFFFFF")
    line_height = int(round(font_size * 1.25))
    total_height = max(line_height, len(lines) * line_height)
    center_x = max(0.0, min(1.0, float(config.get("x", 0.5)))) * target_width
    center_y = max(0.0, min(1.0, float(config.get("y", 0.2)))) * target_height
    start_y = max(0.0, min(target_height - total_height, center_y - total_height / 2))
    highlight_pad_x = max(4, int(round(font_size * 0.12)))
    highlight_pad_y = max(2, int(round(font_size * 0.06)))

    for line_index, line in enumerate(lines):
        line_width = sum(item[2] for item in line) + space_width * max(0, len(line) - 1)
        cursor_x = max(0.0, min(target_width - line_width, center_x - line_width / 2))
        y = start_y + line_index * line_height
        for item_index, (word_index, word, word_width) in enumerate(line):
            highlight_color = highlight_map.get(word_index)
            if highlight_color:
                draw.rounded_rectangle(
                    (
                        cursor_x - highlight_pad_x,
                        y - highlight_pad_y,
                        cursor_x + word_width + highlight_pad_x,
                        y + font_size + highlight_pad_y,
                    ),
                    radius=max(4, highlight_pad_y * 2),
                    fill=highlight_color,
                )
            draw.text(
                (cursor_x, y),
                word,
                font=font,
                fill=text_color,
                stroke_width=max(1, int(round(font_size * 0.025))),
                stroke_fill="#000000",
            )
            cursor_x += word_width
            if item_index < len(line) - 1:
                cursor_x += space_width

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, "PNG")
    return str(path)
