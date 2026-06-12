from types import SimpleNamespace
import shutil
import subprocess
import uuid

from PIL import Image
import pytest

from app.models.export import AspectRatio, CaptionFormat
from app.schemas.export import ExportCreate
from app.services.clip_overlay_rendering import render_highlighted_text_layer
from app.services import rendering


def test_export_overlay_schema_normalizes_highlights():
    payload = ExportCreate(
        clip_id=uuid.uuid4(),
        aspect_ratio=AspectRatio.vertical,
        caption_format=CaptionFormat.burned_in,
        overlay_text_config={
            "text": "Make   this stand out",
            "highlights": [
                {"word_index": 1, "color": "#FACC15"},
                {"word_index": 99, "color": "#22D3EE"},
                {"word_index": 1, "color": "#4ADE80"},
            ],
        },
    )

    assert payload.overlay_text_config is not None
    assert payload.overlay_text_config.text == "Make this stand out"
    assert [item.model_dump() for item in payload.overlay_text_config.highlights] == [
        {"word_index": 1, "color": "#4ADE80"}
    ]


def test_export_overlay_image_requires_asset_and_config_pair():
    with pytest.raises(ValueError):
        ExportCreate(
            clip_id=uuid.uuid4(),
            aspect_ratio=AspectRatio.square,
            caption_format=CaptionFormat.srt,
            overlay_image_config={"x": 0.5, "y": 0.5, "width": 0.25, "opacity": 1},
        )


def test_highlighted_text_layer_creates_transparent_png(tmp_path):
    output = tmp_path / "text.png"
    render_highlighted_text_layer(
        {
            "text": "Make this stand out",
            "x": 0.5,
            "y": 0.2,
            "font_size": 52,
            "text_color": "#FFFFFF",
            "highlights": [{"word_index": 1, "color": "#FACC15"}],
        },
        target_width=720,
        target_height=1280,
        output_path=str(output),
    )

    with Image.open(output) as image:
        assert image.size == (720, 1280)
        assert image.mode == "RGBA"
        alpha = image.getchannel("A")
        assert alpha.getbbox() is not None


def test_overlay_render_uses_filter_complex_and_preserves_layer_order(monkeypatch, tmp_path):
    output = tmp_path / "output.mp4"
    source = tmp_path / "source.mp4"
    image = tmp_path / "logo.png"
    text = tmp_path / "text.png"
    ass = tmp_path / "captions.ass"
    for path in (source, image, text, ass):
        path.write_bytes(b"fixture")

    monkeypatch.setattr(
        rendering,
        "resolve_crop_window",
        lambda **_kwargs: rendering.CropWindow(
            x=0,
            y=0,
            width=1280,
            height=720,
            source_width=1280,
            source_height=720,
        ),
    )

    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        output.write_bytes(b"rendered")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(rendering.subprocess, "run", fake_run)

    rendering.render_video_clip(
        source_path=str(source),
        output_path=str(output),
        clip_start=5,
        clip_end=10,
        aspect_ratio="9:16",
        target_width=720,
        target_height=1280,
        burned_ass_path=str(ass),
        overlay_image_path=str(image),
        overlay_image_config={"x": 0.8, "y": 0.2, "width": 0.2, "opacity": 0.8},
        overlay_text_layer_path=str(text),
    )

    command = captured["cmd"]
    assert "-filter_complex_script" in command
    filter_path = command[command.index("-filter_complex_script") + 1]
    filter_graph = (tmp_path / "filtergraph.txt").read_text()
    assert filter_path == str(tmp_path / "filtergraph.txt")
    assert filter_graph.index("[overlay_image]overlay") < filter_graph.index("subtitles=")
    assert filter_graph.index("subtitles=") < filter_graph.index("[overlay_text]overlay")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_overlay_render_real_ffmpeg_smoke(tmp_path):
    source = tmp_path / "source.mp4"
    logo = tmp_path / "logo.png"
    text = tmp_path / "text.png"
    captions = tmp_path / "captions.ass"
    output = tmp_path / "output.mp4"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=#223355:s=640x360:r=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "1.5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    Image.new("RGBA", (180, 90), "#22D3EE").save(logo)
    render_highlighted_text_layer(
        {
            "text": "Clip overlay smoke",
            "x": 0.5,
            "y": 0.2,
            "font_size": 48,
            "text_color": "#FFFFFF",
            "highlights": [{"word_index": 1, "color": "#FACC15"}],
        },
        target_width=720,
        target_height=1280,
        output_path=str(text),
    )
    rendering.write_ass(
        [rendering.SubtitleCue(start=0, end=1.2, text="Caption layer")],
        str(captions),
        "clean_minimal",
        "classic",
        "9:16",
        720,
        1280,
    )

    rendering.render_video_clip(
        source_path=str(source),
        output_path=str(output),
        clip_start=0,
        clip_end=1.4,
        aspect_ratio="9:16",
        target_width=720,
        target_height=1280,
        burned_ass_path=str(captions),
        overlay_image_path=str(logo),
        overlay_image_config={"x": 0.8, "y": 0.2, "width": 0.2, "opacity": 0.8},
        overlay_text_layer_path=str(text),
    )

    assert output.exists()
    assert output.stat().st_size > 0
