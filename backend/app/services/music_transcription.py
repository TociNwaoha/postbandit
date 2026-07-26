"""Music-optimized faster-whisper settings for the music video caption preset."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_music_transcribe_kwargs(base_kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return faster-whisper options tuned for lyric-heavy music audio."""
    music_kwargs: dict[str, Any] = {
        "word_timestamps": True,
        "beam_size": 10,
        "best_of": 5,
        "condition_on_previous_text": False,
        "initial_prompt": (
            "Rap music video lyrics. Hip hop. Urban music. "
            "Every word matters. Song lyrics:"
        ),
        "temperature": [0.0, 0.2, 0.4, 0.6],
        "language": "en",
        "task": "transcribe",
        "log_prob_threshold": -1.2,
        "no_speech_threshold": 0.7,
        "vad_filter": True,
        "vad_parameters": {
            "threshold": 0.25,
            "min_speech_duration_ms": 50,
            "max_speech_duration_s": 30,
            "min_silence_duration_ms": 200,
            "speech_pad_ms": 300,
        },
    }
    return {**(base_kwargs or {}), **music_kwargs}


def assess_coverage(segments_or_words: list[Any], video_duration: float) -> tuple[float, int]:
    """Return recognized timestamp coverage and word count for an audio duration."""
    words: list[Any] = []
    for item in segments_or_words:
        if hasattr(item, "words") and item.words:
            words.extend(item.words)
        elif isinstance(item, dict) and "word" in item:
            words.append(item)
        elif hasattr(item, "word"):
            words.append(item)

    if not words or video_duration <= 0:
        return 0.0, len(words)

    try:
        starts = [float(word["start"] if isinstance(word, dict) else word.start) for word in words]
        ends = [float(word["end"] if isinstance(word, dict) else word.end) for word in words]
    except (KeyError, AttributeError, TypeError, ValueError):
        return 0.0, len(words)

    first_start = min(starts)
    last_end = max(ends)
    coverage_ratio = max(0.0, last_end - first_start) / video_duration
    start_gap = max(0.0, first_start) / video_duration
    logger.info(
        "[transcribe] transcript coverage=%.1f%% words=%s start_gap=%.1f%% range=%.1fs-%.1fs duration=%.1fs",
        coverage_ratio * 100,
        len(words),
        start_gap * 100,
        first_start,
        last_end,
        video_duration,
    )
    return coverage_ratio, len(words)


def is_poor_coverage(coverage_ratio: float, word_count: int, video_duration: float) -> bool:
    """Identify results likely truncated by voice activity detection."""
    return coverage_ratio < 0.50 or (video_duration > 30 and word_count < 20)


def get_music_transcribe_kwargs_no_vad() -> dict[str, Any]:
    """Return music transcription options with voice activity detection disabled."""
    kwargs = get_music_transcribe_kwargs()
    kwargs["vad_filter"] = False
    kwargs.pop("vad_parameters", None)
    kwargs["log_prob_threshold"] = -1.5
    kwargs["no_speech_threshold"] = 0.8
    return kwargs
