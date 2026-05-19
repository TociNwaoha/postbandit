import pytest

from app.services.youtube.urls import normalize_youtube_input


def test_normalize_watch_url_single():
    payload = normalize_youtube_input("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert payload.source_type == "youtube_single"
    assert payload.normalized_video_id == "dQw4w9WgXcQ"
    assert payload.normalized_playlist_id is None
    assert payload.normalized_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_normalize_youtu_be_single():
    payload = normalize_youtube_input("https://youtu.be/dQw4w9WgXcQ")
    assert payload.source_type == "youtube_single"
    assert payload.normalized_video_id == "dQw4w9WgXcQ"


def test_normalize_shorts_single():
    payload = normalize_youtube_input("https://www.youtube.com/shorts/dQw4w9WgXcQ")
    assert payload.source_type == "youtube_single"
    assert payload.normalized_video_id == "dQw4w9WgXcQ"


def test_normalize_playlist_url():
    payload = normalize_youtube_input("https://www.youtube.com/playlist?list=PL1234567890")
    assert payload.source_type == "youtube_playlist"
    assert payload.normalized_playlist_id == "PL1234567890"
    assert payload.normalized_video_id is None


def test_normalize_watch_plus_playlist_url_is_playlist():
    payload = normalize_youtube_input(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890"
    )
    assert payload.source_type == "youtube_playlist"
    assert payload.normalized_playlist_id == "PL1234567890"
    assert payload.normalized_video_id == "dQw4w9WgXcQ"


def test_reject_non_youtube():
    with pytest.raises(ValueError):
        normalize_youtube_input("https://example.com/watch?v=dQw4w9WgXcQ")

