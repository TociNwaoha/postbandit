import json
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services import carousel
from app.services.carousel_renderer import render_modern


def _raw_config():
    return {
        "title": "My Carousel",
        "profile": {"display_name": "Creator", "handle": "@creator"},
        "slides": [
            {"type": "hook", "text": "Hook *line*"},
            {"type": "body", "title": "Body 1", "bullets": ["One", "Two", "Three"]},
            {"type": "body", "title": "Body 2", "text": "Body text"},
            {"type": "body", "title": "Body 3", "text": "More text"},
            {"type": "body", "title": "Body 4", "text": "More text"},
            {"type": "cta", "text": "CTA", "cta_action": 'Comment *"GUIDE"* and I\'ll DM you the link'},
        ],
    }


def test_list_templates_includes_expected_defaults():
    templates = carousel.list_templates()
    template_ids = {item["id"] for item in templates}
    assert template_ids == {
        "viral-dark",
        "navy-clean",
        "editorial-sun",
        "paper-notes",
        "signal-brutalist",
        "data-mint",
        "aurora-glass",
        "retro-future",
        "luxe-mono",
        "case-study",
    }
    for template in templates:
        assert template["preview_url"].endswith(".png")
        assert template["default_slides"] == 6


def test_registered_renderer_scripts_exist():
    for template in carousel.list_templates():
        renderer_path = carousel.CAROUSEL_RENDERER_DIR / template["renderer"]
        assert renderer_path.is_file(), f"Missing renderer for {template['id']}: {renderer_path}"


def test_get_template_unknown_raises():
    with pytest.raises(carousel.CarouselError):
        carousel.get_template_or_raise("missing-template")


def test_generate_config_claude_path(monkeypatch):
    user = SimpleNamespace(email="tester@example.com")
    monkeypatch.setattr(carousel, "_generate_with_claude", lambda *args, **kwargs: _raw_config())

    config, provider = carousel.generate_config("viral-dark", "Topic", user)
    assert provider == "claude"
    assert config["renderer"] == "render_viral_with_green.py"
    assert len(config["slides"]) == 6
    assert config["slides"][0]["type"] == "hook"
    assert config["slides"][5]["type"] == "cta"


def test_generate_config_deepseek_fallback(monkeypatch):
    user = SimpleNamespace(email="tester@example.com")

    def fail_claude(*args, **kwargs):
        raise carousel.CarouselError("claude unavailable")

    monkeypatch.setattr(carousel, "_generate_with_claude", fail_claude)
    monkeypatch.setattr(carousel, "_generate_with_deepseek", lambda *args, **kwargs: _raw_config())

    config, provider = carousel.generate_config("navy-clean", "Topic", user)
    assert provider == "deepseek"
    assert config["renderer"] == "render.py"


@pytest.mark.parametrize(
    ("template_id", "renderer"),
    [
        ("editorial-sun", "render_modern.py"),
        ("paper-notes", "render_modern.py"),
        ("signal-brutalist", "render_modern.py"),
        ("data-mint", "render_modern.py"),
        ("aurora-glass", "render_modern.py"),
        ("retro-future", "render_modern.py"),
        ("luxe-mono", "render_modern.py"),
        ("case-study", "render_modern.py"),
    ],
)
def test_generate_config_modern_templates_include_theme(monkeypatch, template_id, renderer):
    user = SimpleNamespace(email="tester@example.com")
    monkeypatch.setattr(carousel, "_generate_with_claude", lambda *args, **kwargs: _raw_config())

    config, provider = carousel.generate_config(template_id, "Topic", user)

    assert provider == "claude"
    assert config["renderer"] == renderer
    assert config["template_id"] == template_id


@pytest.mark.parametrize("template_id", sorted(render_modern.THEMES))
def test_modern_renderer_outputs_six_valid_pngs(tmp_path, template_id):
    config = _raw_config()
    config["template_id"] = template_id
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")

    render_modern.render_carousel(tmp_path)

    slide_paths = sorted(tmp_path.glob("slide_*.png"))
    assert len(slide_paths) == 6
    for slide_path in slide_paths:
        with Image.open(slide_path) as image:
            assert image.size == (render_modern.WIDTH, render_modern.HEIGHT)
            assert image.mode == "RGB"
