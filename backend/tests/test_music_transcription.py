from app.services.music_transcription import (
    assess_coverage,
    get_music_transcribe_kwargs,
    get_music_transcribe_kwargs_no_vad,
    is_poor_coverage,
)


def test_music_transcription_parameters_are_tuned_for_lyrics():
    kwargs = get_music_transcribe_kwargs()

    assert kwargs["word_timestamps"] is True
    assert kwargs["beam_size"] == 10
    assert kwargs["best_of"] == 5
    assert kwargs["condition_on_previous_text"] is False
    assert kwargs["temperature"] == [0.0, 0.2, 0.4, 0.6]
    assert kwargs["vad_parameters"]["threshold"] == 0.25
    assert kwargs["initial_prompt"].startswith("Rap music video lyrics")


def test_music_transcription_parameters_override_base_defaults():
    kwargs = get_music_transcribe_kwargs({"beam_size": 1, "custom_option": "keep"})

    assert kwargs["beam_size"] == 10
    assert kwargs["custom_option"] == "keep"


def test_poor_music_coverage_triggers_vad_off_fallback():
    words = [
        {"word": f"word{index}", "start": 64.8 + (index * 0.7), "end": 65.3 + (index * 0.7)}
        for index in range(33)
    ]
    coverage, count = assess_coverage(words, 97.36)

    assert count == 33
    assert coverage < 0.50
    assert is_poor_coverage(coverage, count, 97.36) is True


def test_good_music_coverage_keeps_vad_enabled_result():
    words = [
        {"word": f"word{index}", "start": index * 1.0, "end": (index * 1.0) + 0.8}
        for index in range(80)
    ]
    coverage, count = assess_coverage(words, 97.36)

    assert count == 80
    assert coverage >= 0.50
    assert is_poor_coverage(coverage, count, 97.36) is False


def test_vad_off_fallback_disables_vad_and_relaxes_thresholds():
    kwargs = get_music_transcribe_kwargs_no_vad()

    assert kwargs["vad_filter"] is False
    assert "vad_parameters" not in kwargs
    assert kwargs["log_prob_threshold"] == -1.5
    assert kwargs["no_speech_threshold"] == 0.8
