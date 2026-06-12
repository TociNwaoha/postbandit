import pytest

from app.services import ai_copy
from app.services.ai_copy import AICopyError, generate_platform_copy


def test_platform_copy_accepts_partial_results(monkeypatch):
    monkeypatch.setattr(
        ai_copy,
        "_post_deepseek_json",
        lambda *_args, **_kwargs: {
            "results": {
                "instagram": {
                    "caption": "A platform-specific caption",
                    "hashtags": ["PostBandit", "#Clips"],
                },
                "x": {"unexpected": "value"},
            }
        },
    )

    result = generate_platform_copy(
        "A transcript with enough context.",
        ["instagram", "x"],
    )

    assert result.results["instagram"]["caption"] == "A platform-specific caption"
    assert result.results["instagram"]["hashtags"] == ["#postbandit", "#clips"]
    assert "x" in result.errors


def test_platform_copy_enforces_x_limit(monkeypatch):
    monkeypatch.setattr(
        ai_copy,
        "_post_deepseek_json",
        lambda *_args, **_kwargs: {
            "results": {"x": {"caption": "x" * 400, "hashtags": ["#one", "#two", "#three", "#four"]}}
        },
    )

    result = generate_platform_copy("Transcript", ["x"])
    assert len(result.results["x"]["caption"]) == 280
    assert len(result.results["x"]["hashtags"]) == 3


def test_platform_copy_rejects_when_nothing_parses(monkeypatch):
    monkeypatch.setattr(
        ai_copy,
        "_post_deepseek_json",
        lambda *_args, **_kwargs: {"results": {"youtube": {}}},
    )
    with pytest.raises(AICopyError, match="No platform copy result"):
        generate_platform_copy("Transcript", ["youtube"])
