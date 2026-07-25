import json
import logging
import time
from threading import Lock
from typing import Any

from faster_whisper import WhisperModel

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level model instance — loaded once, reused across jobs.
_model: WhisperModel | None = None
_model_name: str | None = None
_model_lock = Lock()


def get_model() -> WhisperModel:
    """
    Load the Whisper model once and cache it.
    Uses medium model with int8 quantization for CPU efficiency.
    Downloads model on first call (~1.5GB, one-time).
    """
    model, _, _ = get_model_with_metadata()
    return model


def get_model_with_metadata() -> tuple[WhisperModel, bool, str]:
    """
    Return the singleton model and metadata about cache usage.

    Returns:
      model: WhisperModel instance
      loaded_from_cache: True when reusing an in-process model
      model_name: active model name
    """
    global _model
    global _model_name

    requested_model = settings.whisper_model_size
    loaded_from_cache = False

    with _model_lock:
        if _model is not None and _model_name == requested_model:
            loaded_from_cache = True
            return _model, loaded_from_cache, requested_model

        load_started = time.perf_counter()
        logger.info(
            "TRANSCRIBE_PERF event=whisper_model_load_internal_start model=%s",
            requested_model,
        )
        _model = WhisperModel(
            requested_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            download_root=settings.whisper_download_root,
            num_workers=settings.whisper_num_workers,
        )
        _model_name = requested_model
        load_elapsed = time.perf_counter() - load_started
        logger.info(
            "TRANSCRIBE_PERF event=whisper_model_load_internal_end model=%s duration_s=%.3f",
            requested_model,
            load_elapsed,
        )
        return _model, loaded_from_cache, requested_model


def transcribe_audio(
    audio_path: str,
    language: str = "en",
    model: WhisperModel | None = None,
    transcribe_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Transcribe audio file and return word-level timestamps.

    Returns dict with:
      segments: list of segment dicts
      words: list of word dicts with start/end/confidence
      language: detected language
      duration: total audio duration in seconds
    """
    model = model or get_model()
    logger.info(f"Starting transcription of {audio_path}")

    default_kwargs: dict[str, Any] = {
        "language": language,
        "word_timestamps": True,
        "beam_size": settings.whisper_beam_size,
        "best_of": settings.whisper_best_of,
        "temperature": 0.0,
        "condition_on_previous_text": settings.whisper_condition_on_previous_text,
        "vad_filter": True,
        "vad_parameters": dict(min_silence_duration_ms=500),
    }
    effective_kwargs = {**default_kwargs, **(transcribe_kwargs or {})}
    segments_raw, info = model.transcribe(audio_path, **effective_kwargs)

    segments: list[dict[str, Any]] = []
    all_words: list[dict[str, Any]] = []
    segment_index = 0

    for segment in segments_raw:
        seg_dict = {
            "id": segment_index,
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text.strip(),
            "words": [],
        }

        if segment.words:
            for word in segment.words:
                word_dict = {
                    "word": word.word.strip(),
                    "start": float(word.start),
                    "end": float(word.end),
                    "confidence": float(round(float(word.probability), 4)),
                    "segment_index": segment_index,
                }
                seg_dict["words"].append(word_dict)
                all_words.append(word_dict)

        segments.append(seg_dict)
        segment_index += 1

    logger.info(
        f"Transcription complete: {len(all_words)} words, {len(segments)} segments, "
        f"detected language: {info.language}"
    )

    logger.debug(
        "TRANSCRIBE_PERF event=transcribe_audio_result summary=%s",
        json.dumps(
            {
                "word_count": len(all_words),
                "segment_count": len(segments),
                "language": info.language,
            },
            sort_keys=True,
        ),
    )

    return {
        "segments": segments,
        "words": all_words,
        "language": info.language,
        "language_probability": float(round(float(info.language_probability), 4)),
        "duration": float(info.duration or 0.0),
    }
