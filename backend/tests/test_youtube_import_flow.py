from types import SimpleNamespace

from app.services.youtube.metadata import (
    extract_playlist_entries,
    metadata_from_yt_info,
)


def test_metadata_from_yt_info_builds_embed_and_watch_urls():
    row = {
        "id": "dQw4w9WgXcQ",
        "title": "Sample",
        "channel": "Uploader",
        "duration": 123,
        "thumbnail": "https://img.example/thumb.jpg",
    }
    metadata = metadata_from_yt_info(row)
    assert metadata is not None
    assert metadata.video_id == "dQw4w9WgXcQ"
    assert metadata.watch_url.endswith("v=dQw4w9WgXcQ")
    assert metadata.embed_url.endswith("/dQw4w9WgXcQ")


def test_extract_playlist_entries_respects_max_items(monkeypatch):
    fake_payload = {
        "id": "PL1234567890",
        "title": "Demo Playlist",
        "entries": [
            {"id": "AAAAAAAAAAA", "title": "One", "duration": 10},
            {"id": "BBBBBBBBBBB", "title": "Two", "duration": 20},
            {"id": "CCCCCCCCCCC", "title": "Three", "duration": 30},
        ],
    }

    class FakeYDL:
        def __init__(self, _opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=False):
            assert download is False
            return fake_payload

    monkeypatch.setattr(
        "app.services.youtube.metadata.yt_dlp.YoutubeDL",
        lambda opts: FakeYDL(opts),
    )

    playlist_id, title, items = extract_playlist_entries(
        url="https://www.youtube.com/playlist?list=PL1234567890",
        timeout_seconds=30,
        max_items=2,
    )
    assert playlist_id == "PL1234567890"
    assert title == "Demo Playlist"
    assert len(items) == 2
    assert [item.video_id for item in items] == ["AAAAAAAAAAA", "BBBBBBBBBBB"]

