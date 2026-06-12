from types import SimpleNamespace

import pytest

from app.services.rendering import build_subtitle_cues


def _segments(words: list[str], start: float = 10.0, step: float = 0.35):
    return [
        SimpleNamespace(
            word=word,
            start_time=start + index * step,
            end_time=start + index * step + 0.28,
        )
        for index, word in enumerate(words)
    ]


def test_phrase_preserves_existing_eight_word_grouping():
    cues = build_subtitle_cues(
        _segments("one two three four five six seven eight nine".split()),
        clip_start=10.0,
        clip_end=20.0,
        cadence="phrase",
    )
    assert [len(cue.text.split()) for cue in cues] == [8, 1]


def test_split_line_uses_short_social_groups():
    cues = build_subtitle_cues(
        _segments("one two three four five six seven".split()),
        clip_start=10.0,
        clip_end=20.0,
        cadence="split_line",
    )
    assert all(1 <= len(cue.text.split()) <= 3 for cue in cues)


def test_word_by_word_creates_one_cue_per_word():
    words = ["one", "two", "three"]
    cues = build_subtitle_cues(
        _segments(words),
        clip_start=10.0,
        clip_end=20.0,
        cadence="word_by_word",
    )
    assert [cue.text for cue in cues] == words


def test_subtitle_block_groups_longer_sentences_and_clamps_bounds():
    cues = build_subtitle_cues(
        _segments("one two three four five six seven eight nine ten eleven twelve".split(), start=8.0),
        clip_start=10.0,
        clip_end=12.0,
        cadence="subtitle_block",
    )
    assert cues
    assert all(0 <= cue.start < cue.end <= 2.0 for cue in cues)


def test_unknown_cadence_is_rejected():
    with pytest.raises(ValueError, match="Unsupported caption cadence"):
        build_subtitle_cues([], 0, 10, cadence="unknown")
