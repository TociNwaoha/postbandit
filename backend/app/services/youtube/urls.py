from dataclasses import dataclass
import re
from urllib.parse import parse_qs, urlencode, urlparse


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


@dataclass(frozen=True)
class YouTubeNormalizedInput:
    source_type: str
    original_url: str
    normalized_url: str
    normalized_video_id: str | None
    normalized_playlist_id: str | None


def watch_url_for_video_id(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def embed_url_for_video_id(video_id: str) -> str:
    return f"https://www.youtube.com/embed/{video_id}"


def _validate_video_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if VIDEO_ID_RE.fullmatch(value):
        return value
    return None


def _validate_playlist_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if PLAYLIST_ID_RE.fullmatch(value):
        return value
    return None


def normalize_youtube_input(value: str) -> YouTubeNormalizedInput:
    original = (value or "").strip()
    if not original:
        raise ValueError("Please enter a valid YouTube URL.")

    try:
        parsed = urlparse(original)
    except Exception as exc:
        raise ValueError("Please enter a valid YouTube URL.") from exc

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Please enter a valid YouTube URL.")
    if not parsed.netloc:
        raise ValueError("Please enter a valid YouTube URL.")

    host = parsed.netloc.lower().split(":", 1)[0]
    if host not in YOUTUBE_HOSTS:
        raise ValueError("Only youtube.com, m.youtube.com, or youtu.be links are supported.")

    query = parse_qs(parsed.query)
    playlist_id = _validate_playlist_id((query.get("list") or [None])[0])
    video_id: str | None = None

    path_parts = [p for p in parsed.path.split("/") if p]
    if host.endswith("youtu.be"):
        video_id = _validate_video_id(path_parts[0] if path_parts else None)
    elif parsed.path == "/watch":
        video_id = _validate_video_id((query.get("v") or [None])[0])
    elif len(path_parts) >= 2 and path_parts[0] == "shorts":
        video_id = _validate_video_id(path_parts[1])
    elif len(path_parts) >= 2 and path_parts[0] == "embed":
        video_id = _validate_video_id(path_parts[1])
    elif parsed.path == "/playlist":
        # playlist-only form
        pass

    if playlist_id:
        normalized_query = {"list": playlist_id}
        if video_id:
            normalized_query["v"] = video_id
        normalized_url = f"https://www.youtube.com/playlist?{urlencode(normalized_query)}"
        return YouTubeNormalizedInput(
            source_type="youtube_playlist",
            original_url=original,
            normalized_url=normalized_url,
            normalized_video_id=video_id,
            normalized_playlist_id=playlist_id,
        )

    if not video_id:
        raise ValueError("Please paste a direct YouTube video or playlist link.")

    return YouTubeNormalizedInput(
        source_type="youtube_single",
        original_url=original,
        normalized_url=watch_url_for_video_id(video_id),
        normalized_video_id=video_id,
        normalized_playlist_id=None,
    )

