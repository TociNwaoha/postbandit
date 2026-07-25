from app.services.music_transcription import get_music_transcribe_kwargs


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
