import pytest

from app.services.youtube.urls import detect_url_platform, normalize_import_url, normalize_youtube_input


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


@pytest.mark.parametrize(
    ("expected", "url"),
    [
        ("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("youtube", "https://youtu.be/dQw4w9WgXcQ"),
        ("youtube", "https://www.youtube.com/shorts/dQw4w9WgXcQ"),
        ("instagram", "https://www.instagram.com/reel/ABC123_def/"),
        ("instagram", "https://www.instagram.com/p/DEF456/"),
        ("instagram", "https://www.instagram.com/tv/GHI789/"),
        ("tiktok", "https://www.tiktok.com/@user.name/video/1234567890"),
        ("tiktok", "https://vm.tiktok.com/ABC123/"),
        ("tiktok", "https://www.tiktok.com/t/ZPRabc123/"),
        ("facebook", "https://www.facebook.com/watch?v=123456789"),
        ("facebook", "https://www.facebook.com/page.name/videos/123456789/"),
        ("facebook", "https://fb.watch/abc123/"),
        ("facebook", "https://www.facebook.com/share/v/abc123/"),
        ("x", "https://x.com/user/status/1234567890"),
        ("x", "https://twitter.com/user/status/1234567890"),
        ("twitch", "https://www.twitch.tv/videos/1234567890"),
        ("twitch", "https://clips.twitch.tv/SomeClipName"),
        ("twitch", "https://www.twitch.tv/user/clip/SomeClipName"),
        ("unknown", "https://example.com/random"),
    ],
)
def test_detect_import_platforms(expected, url):
    assert detect_url_platform(url) == expected


@pytest.mark.parametrize(
    ("source_type", "video_id", "url"),
    [
        ("instagram", "ABC123_def", "https://www.instagram.com/reel/ABC123_def/?igsh=ignored"),
        ("tiktok", "1234567890", "https://www.tiktok.com/@user.name/video/1234567890?lang=en"),
        ("tiktok", "ABC123", "https://vm.tiktok.com/ABC123/"),
        ("facebook", "123456789", "https://www.facebook.com/watch?v=123456789&ref=share"),
        ("facebook", "abc123", "https://fb.watch/abc123/"),
        ("x", "1234567890", "https://twitter.com/user/status/1234567890?s=20"),
        ("twitch", "1234567890", "https://www.twitch.tv/videos/1234567890?t=10s"),
        ("twitch", "SomeClipName", "https://clips.twitch.tv/SomeClipName"),
    ],
)
def test_normalize_universal_import_url(source_type, video_id, url):
    payload = normalize_import_url(url)
    assert payload.source_type == source_type
    assert payload.normalized_video_id == video_id
    assert payload.normalized_playlist_id is None
    assert payload.normalized_url.startswith("https://")


def test_normalize_import_url_rejects_unknown_platform():
    with pytest.raises(ValueError):
        normalize_import_url("https://example.com/random")
