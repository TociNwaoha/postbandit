from app.services.caption_presets import generate_music_video_ass, generate_scattered_positions


def test_scattered_positions_are_reproducible_and_stay_in_frame():
    positions = generate_scattered_positions(12, width=720, height=1280, seed="clip-123")

    assert positions == generate_scattered_positions(12, width=720, height=1280, seed="clip-123")
    assert len(positions) == 12
    assert all(0 < x < 720 and 0 < y < 1280 for x, y in positions)


def test_music_video_ass_accumulates_words_and_clamps_to_clip_duration():
    ass = generate_music_video_ass(
        [
            {"word": "walk", "start": 0.5, "end": 0.7},
            {"word": "with", "start": 0.8, "end": 1.0},
            {"word": "god", "start": 1.1, "end": 1.3},
        ],
        video_width=720,
        video_height=1280,
        clip_id="clip-123",
        hold_seconds=2.5,
        clip_duration=2.0,
    )

    dialogue_lines = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len(dialogue_lines) == 3
    assert "Style: Music,DejaVu Sans" in ass
    assert "{\\an5\\pos(" in ass
    assert "WALK" in ass and "WITH" in ass and "GOD" in ass
    assert any(",0:00:02.00,Music," in line for line in dialogue_lines)


def test_music_video_ass_returns_empty_for_empty_words():
    assert generate_music_video_ass([], video_width=720, video_height=1280) == ""
