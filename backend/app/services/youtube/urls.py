from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
INSTAGRAM_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
}
TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
}
FACEBOOK_HOSTS = {
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "fb.watch",
    "www.fb.watch",
}
X_HOSTS = {
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
}
TWITCH_HOSTS = {
    "twitch.tv",
    "www.twitch.tv",
    "m.twitch.tv",
    "clips.twitch.tv",
    "www.clips.twitch.tv",
}

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
INSTAGRAM_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{4,}$")
SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{3,}$")
NUMERIC_ID_RE = re.compile(r"^\d{5,}$")
SUPPORTED_IMPORT_PLATFORMS = {"youtube", "instagram", "tiktok", "facebook", "x", "twitch"}
PLATFORM_DISPLAY_NAMES = {
    "youtube": "YouTube",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "x": "X",
    "twitch": "Twitch",
}


@dataclass(frozen=True)
class YouTubeNormalizedInput:
    source_type: str
    original_url: str
    normalized_url: str
    normalized_video_id: str | None
    normalized_playlist_id: str | None


@dataclass(frozen=True)
class ImportUrlNormalizedInput:
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


def _parse_http_url(value: str, platform_name: str):
    original = (value or "").strip()
    if not original:
        raise ValueError(f"Please enter a valid {platform_name} URL.")
    try:
        parsed = urlparse(original)
    except Exception as exc:
        raise ValueError(f"Please enter a valid {platform_name} URL.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Please enter a valid {platform_name} URL.")
    return original, parsed, parsed.netloc.lower().split(":", 1)[0]


def _path_parts(parsed) -> list[str]:
    return [part for part in parsed.path.split("/") if part]


def normalize_youtube_input(value: str) -> YouTubeNormalizedInput:
    original, parsed, host = _parse_http_url(value, "YouTube")

    if host not in YOUTUBE_HOSTS:
        raise ValueError("Only youtube.com, m.youtube.com, or youtu.be links are supported.")

    query = parse_qs(parsed.query)
    playlist_id = _validate_playlist_id((query.get("list") or [None])[0])
    video_id: str | None = None

    path_parts = _path_parts(parsed)
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


def detect_url_platform(value: str) -> str:
    original = (value or "").strip()
    if not original:
        return "unknown"
    try:
        parsed = urlparse(original)
    except Exception:
        return "unknown"
    if parsed.scheme not in {"http", "https"}:
        return "unknown"
    host = parsed.netloc.lower().split(":", 1)[0]
    path_parts = _path_parts(parsed)

    if host in YOUTUBE_HOSTS:
        return "youtube"
    if host in INSTAGRAM_HOSTS and len(path_parts) >= 2 and path_parts[0] in {"reel", "p", "tv"}:
        return "instagram"
    if host in TIKTOK_HOSTS:
        if host == "vm.tiktok.com" and path_parts:
            return "tiktok"
        if len(path_parts) >= 3 and path_parts[0].startswith("@") and path_parts[1] == "video":
            return "tiktok"
        if len(path_parts) >= 2 and path_parts[0] == "t":
            return "tiktok"
    if host in FACEBOOK_HOSTS:
        query = parse_qs(parsed.query)
        if host.endswith("fb.watch") and path_parts:
            return "facebook"
        if parsed.path.rstrip("/") == "/watch" and (query.get("v") or [None])[0]:
            return "facebook"
        if len(path_parts) >= 3 and "videos" in path_parts:
            return "facebook"
        if len(path_parts) >= 3 and path_parts[0] == "share" and path_parts[1] == "v":
            return "facebook"
    if host in X_HOSTS and len(path_parts) >= 3 and path_parts[1] == "status" and path_parts[2].isdigit():
        return "x"
    if host in TWITCH_HOSTS:
        if host.endswith("clips.twitch.tv") and path_parts:
            return "twitch"
        if len(path_parts) >= 2 and path_parts[0] == "videos" and path_parts[1].isdigit():
            return "twitch"
        if len(path_parts) >= 3 and path_parts[1] == "clip" and SLUG_RE.fullmatch(path_parts[2]):
            return "twitch"
    return "unknown"


def normalize_instagram_input(value: str) -> ImportUrlNormalizedInput:
    original, parsed, host = _parse_http_url(value, "Instagram")
    if host not in INSTAGRAM_HOSTS:
        raise ValueError("Only instagram.com links are supported.")

    path_parts = _path_parts(parsed)
    if len(path_parts) < 2 or path_parts[0] not in {"reel", "p", "tv"}:
        raise ValueError("Please paste a public Instagram Reel, post, or video URL.")

    shortcode = path_parts[1].strip()
    if not INSTAGRAM_SHORTCODE_RE.fullmatch(shortcode):
        raise ValueError("Please paste a valid Instagram Reel, post, or video URL.")

    normalized_url = f"https://www.instagram.com/{path_parts[0]}/{shortcode}/"
    return ImportUrlNormalizedInput(
        source_type="instagram",
        original_url=original,
        normalized_url=normalized_url,
        normalized_video_id=shortcode,
        normalized_playlist_id=None,
    )


def _clean_url(parsed, *, host: str | None = None, path: str | None = None, query: str = "") -> str:
    return urlunparse((
        "https",
        host or parsed.netloc.lower().split(":", 1)[0],
        path if path is not None else parsed.path,
        "",
        query,
        "",
    ))


def normalize_tiktok_input(value: str) -> ImportUrlNormalizedInput:
    original, parsed, host = _parse_http_url(value, "TikTok")
    if detect_url_platform(original) != "tiktok":
        raise ValueError("Please paste a public TikTok video URL.")
    path_parts = _path_parts(parsed)
    video_id = None
    if len(path_parts) >= 3 and path_parts[0].startswith("@") and path_parts[1] == "video":
        video_id = path_parts[2]
    elif path_parts:
        video_id = path_parts[-1]
    if not video_id or not SLUG_RE.fullmatch(video_id):
        raise ValueError("Please paste a valid TikTok video URL.")
    return ImportUrlNormalizedInput(
        source_type="tiktok",
        original_url=original,
        normalized_url=_clean_url(parsed),
        normalized_video_id=video_id,
        normalized_playlist_id=None,
    )


def normalize_facebook_input(value: str) -> ImportUrlNormalizedInput:
    original, parsed, host = _parse_http_url(value, "Facebook")
    if detect_url_platform(original) != "facebook":
        raise ValueError("Please paste a public Facebook video URL.")
    path_parts = _path_parts(parsed)
    query = parse_qs(parsed.query)
    video_id = (query.get("v") or [None])[0]
    normalized_query = ""
    normalized_path = parsed.path
    if parsed.path.rstrip("/") == "/watch" and video_id:
        if not NUMERIC_ID_RE.fullmatch(video_id):
            raise ValueError("Please paste a valid Facebook watch URL.")
        normalized_path = "/watch"
        normalized_query = urlencode({"v": video_id})
    elif host.endswith("fb.watch") and path_parts:
        video_id = path_parts[0]
    elif len(path_parts) >= 3 and "videos" in path_parts:
        video_id = path_parts[-1]
    elif len(path_parts) >= 3 and path_parts[0] == "share" and path_parts[1] == "v":
        video_id = path_parts[2]
    if not video_id or not SLUG_RE.fullmatch(video_id):
        raise ValueError("Please paste a valid Facebook video URL.")
    return ImportUrlNormalizedInput(
        source_type="facebook",
        original_url=original,
        normalized_url=_clean_url(parsed, path=normalized_path, query=normalized_query),
        normalized_video_id=video_id,
        normalized_playlist_id=None,
    )


def normalize_x_input(value: str) -> ImportUrlNormalizedInput:
    original, parsed, host = _parse_http_url(value, "X")
    if host not in X_HOSTS:
        raise ValueError("Please paste a public X post URL.")
    path_parts = _path_parts(parsed)
    if len(path_parts) < 3 or path_parts[1] != "status" or not path_parts[2].isdigit():
        raise ValueError("Please paste a public X post URL.")
    post_id = path_parts[2]
    normalized_url = f"https://x.com/{path_parts[0]}/status/{post_id}"
    return ImportUrlNormalizedInput(
        source_type="x",
        original_url=original,
        normalized_url=normalized_url,
        normalized_video_id=post_id,
        normalized_playlist_id=None,
    )


def normalize_twitch_input(value: str) -> ImportUrlNormalizedInput:
    original, parsed, host = _parse_http_url(value, "Twitch")
    if detect_url_platform(original) != "twitch":
        raise ValueError("Please paste a public Twitch VOD or clip URL.")
    path_parts = _path_parts(parsed)
    video_id = None
    if host.endswith("clips.twitch.tv") and path_parts:
        video_id = path_parts[0]
    elif len(path_parts) >= 2 and path_parts[0] == "videos":
        video_id = path_parts[1]
    elif len(path_parts) >= 3 and path_parts[1] == "clip":
        video_id = path_parts[2]
    if not video_id or not SLUG_RE.fullmatch(video_id):
        raise ValueError("Please paste a valid Twitch VOD or clip URL.")
    return ImportUrlNormalizedInput(
        source_type="twitch",
        original_url=original,
        normalized_url=_clean_url(parsed),
        normalized_video_id=video_id,
        normalized_playlist_id=None,
    )


def normalize_import_url(value: str) -> ImportUrlNormalizedInput:
    platform = detect_url_platform(value)
    if platform == "youtube":
        normalized = normalize_youtube_input(value)
        return ImportUrlNormalizedInput(
            source_type=normalized.source_type,
            original_url=normalized.original_url,
            normalized_url=normalized.normalized_url,
            normalized_video_id=normalized.normalized_video_id,
            normalized_playlist_id=normalized.normalized_playlist_id,
        )
    if platform == "instagram":
        return normalize_instagram_input(value)
    if platform == "tiktok":
        return normalize_tiktok_input(value)
    if platform == "facebook":
        return normalize_facebook_input(value)
    if platform == "x":
        return normalize_x_input(value)
    if platform == "twitch":
        return normalize_twitch_input(value)
    raise ValueError(
        "Please paste a public video URL from YouTube, Instagram, TikTok, Facebook, X, or Twitch."
    )
