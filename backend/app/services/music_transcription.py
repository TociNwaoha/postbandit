"""Music-optimized faster-whisper settings for the music video caption preset."""

from __future__ import annotations

from typing import Any


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
