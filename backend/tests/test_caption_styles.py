from app.models.export import CaptionColorVariant, CaptionStyle
from app.services.rendering import _ass_style_line, _caption_layout, _escape_ass_text, _wrap_caption_text


def test_caption_style_enum_includes_new_values():
    values = {item.value for item in CaptionStyle}
    assert "kinetic_bold" in values
    assert "cinema_outline" in values
    assert "clean_highlight" in values


def test_ass_style_line_supported_for_all_caption_styles():
    layout = _caption_layout("9:16", "clean_minimal", 1080, 1920, None, None)
    lines = {
        style.value: _ass_style_line(style.value, CaptionColorVariant.classic.value, layout)
        for style in CaptionStyle
    }

    for value, line in lines.items():
        assert line.startswith("Style: Default,Arial,")
        assert "100,100,0,0" in line
        assert len(line) > 40, f"style line too short for {value}"

    # Ensure new styles are not silently falling back to identical clean_minimal settings.
    assert lines["kinetic_bold"] != lines["clean_minimal"]
    assert lines["cinema_outline"] != lines["clean_minimal"]
    assert lines["clean_highlight"] != lines["clean_minimal"]


def test_ass_style_line_supported_for_all_color_variants():
    layout = _caption_layout("9:16", "clean_minimal", 1080, 1920, None, None)
    for style in CaptionStyle:
        lines = {
            variant.value: _ass_style_line(style.value, variant.value, layout)
            for variant in CaptionColorVariant
        }
        assert lines["classic"] != lines["warm"]
        assert lines["classic"] != lines["cool"]
        assert lines["warm"] != lines["cool"]


def test_ass_style_line_unknown_variant_falls_back_to_classic():
    layout = _caption_layout("9:16", "clean_minimal", 1080, 1920, None, None)
    classic = _ass_style_line("clean_minimal", "classic", layout)
    unknown = _ass_style_line("clean_minimal", "unknown_variant", layout)
    assert classic == unknown


def test_caption_layout_varies_for_new_styles():
    kinetic = _caption_layout("9:16", "kinetic_bold", 1080, 1920, None, None)
    clean = _caption_layout("9:16", "clean_minimal", 1080, 1920, None, None)
    cinema = _caption_layout("9:16", "cinema_outline", 1080, 1920, None, None)

    assert kinetic.font_size > clean.font_size
    assert cinema.font_size > clean.font_size


def test_ass_escape_preserves_linebreak_tokens():
    wrapped = _wrap_caption_text(
        "One two three four five six seven eight nine ten eleven twelve",
        max_chars_per_line=20,
        max_lines=3,
    )
    assert r"\N" in wrapped

    escaped = _escape_ass_text(wrapped)
    assert r"\N" in escaped
    assert r"\\N" not in escaped


def test_ass_escape_still_escapes_braces_and_backslashes():
    escaped = _escape_ass_text(r"Use {tag} and C:\tmp\file")
    assert r"\{tag\}" in escaped
    assert r"C:\\tmp\\file" in escaped
