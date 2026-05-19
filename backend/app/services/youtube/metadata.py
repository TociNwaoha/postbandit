from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any

import requests
import yt_dlp

from app.services.youtube.urls import embed_url_for_video_id, watch_url_for_video_id

logger = logging.getLogger(__name__)

YTDLP_EXTRACTOR_ARGS = {
    "youtube": {
        # Try multiple official extractor clients in priority order.
        # This improves best-effort reliability without bypass behavior.
        "player_client": ["android", "mweb", "web", "tv_embedded"],
        "player_skip": ["webpage", "configs"],
    }
}


@dataclass(frozen=True)
class YouTubeVideoMetadata:
    video_id: str
    title: str | None
    channel: str | None
    duration_sec: int | None
    thumbnail_url: str | None
    watch_url: str
    embed_url: str
    raw: dict[str, Any]


def ytdlp_common_options(timeout_seconds: int, noplaylist: bool) -> dict[str, Any]:
    return {
        "quiet": False,
        "no_warnings": False,
        "extract_flat": False,
        "ignoreerrors": False,
        "noplaylist": noplaylist,
        "socket_timeout": timeout_seconds,
        "retries": 8,
        "extractor_retries": 3,
        "file_access_retries": 3,
        "fragment_retries": 8,
        "skip_unavailable_fragments": True,
        "concurrent_fragment_downloads": 1,
        "extractor_args": YTDLP_EXTRACTOR_ARGS,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    }


def _select_thumbnail(info: dict[str, Any]) -> str | None:
    thumbnails = info.get("thumbnails")
    if isinstance(thumbnails, list):
        best_url = None
        best_area = -1
        for item in thumbnails:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
            area = width * height
            if area >= best_area:
                best_area = area
                best_url = url
        if best_url:
            return best_url
    if isinstance(info.get("thumbnail"), str):
        return info.get("thumbnail")
    return None


def metadata_from_yt_info(info: dict[str, Any], fallback_video_id: str | None = None) -> YouTubeVideoMetadata | None:
    video_id = info.get("id") or fallback_video_id
    if not isinstance(video_id, str) or not video_id:
        return None

    duration = info.get("duration")
    duration_sec = int(duration) if isinstance(duration, (int, float)) else None
    title = info.get("title") if isinstance(info.get("title"), str) else None
    channel = info.get("channel") if isinstance(info.get("channel"), str) else None
    thumbnail_url = _select_thumbnail(info)
    watch_url = watch_url_for_video_id(video_id)
    embed_url = embed_url_for_video_id(video_id)

    return YouTubeVideoMetadata(
        video_id=video_id,
        title=title,
        channel=channel,
        duration_sec=duration_sec,
        thumbnail_url=thumbnail_url,
        watch_url=watch_url,
        embed_url=embed_url,
        raw=info,
    )


def extract_single_video_metadata(url: str, timeout_seconds: int) -> YouTubeVideoMetadata:
    opts = ytdlp_common_options(timeout_seconds=timeout_seconds, noplaylist=True)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    meta = metadata_from_yt_info(info)
    if not meta:
        raise ValueError("Could not parse YouTube metadata from extractor response.")
    return meta


def extract_playlist_entries(url: str, timeout_seconds: int, max_items: int) -> tuple[str | None, str | None, list[YouTubeVideoMetadata]]:
    opts = {
        **ytdlp_common_options(timeout_seconds=timeout_seconds, noplaylist=False),
        "extract_flat": "in_playlist",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    playlist_id = info.get("id") if isinstance(info.get("id"), str) else None
    playlist_title = info.get("title") if isinstance(info.get("title"), str) else None

    entries_raw = info.get("entries") if isinstance(info.get("entries"), list) else []
    items: list[YouTubeVideoMetadata] = []
    for raw in entries_raw[:max_items]:
        if not isinstance(raw, dict):
            continue
        item = metadata_from_yt_info(raw)
        if item:
            items.append(item)

    return playlist_id, playlist_title, items


_ISO8601_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def _parse_iso8601_duration(value: str | None) -> int | None:
    if not value:
        return None
    match = _ISO8601_DURATION.match(value)
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def enrich_playlist_items_with_youtube_api(
    items: list[YouTubeVideoMetadata],
    api_key: str,
    enabled: bool,
) -> list[YouTubeVideoMetadata]:
    if not enabled or not api_key or not items:
        return items

    ids = [item.video_id for item in items if item.video_id]
    if not ids:
        return items

    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "snippet,contentDetails",
                "id": ",".join(ids),
                "key": api_key,
            },
            timeout=10,
        )
        if response.status_code >= 400:
            logger.warning("[youtube] metadata API enrichment skipped status=%s", response.status_code)
            return items
        payload = response.json()
    except Exception as exc:
        logger.warning("[youtube] metadata API enrichment failed: %s", exc)
        return items

    by_id: dict[str, dict[str, Any]] = {}
    for row in payload.get("items", []):
        if not isinstance(row, dict):
            continue
        video_id = row.get("id")
        if isinstance(video_id, str):
            by_id[video_id] = row

    enriched: list[YouTubeVideoMetadata] = []
    for item in items:
        src = by_id.get(item.video_id)
        if not src:
            enriched.append(item)
            continue

        snippet = src.get("snippet") or {}
        content_details = src.get("contentDetails") or {}
        title = snippet.get("title") if isinstance(snippet.get("title"), str) else item.title
        channel = snippet.get("channelTitle") if isinstance(snippet.get("channelTitle"), str) else item.channel
        duration_sec = _parse_iso8601_duration(content_details.get("duration")) or item.duration_sec
        thumb = item.thumbnail_url
        thumbs = snippet.get("thumbnails")
        if isinstance(thumbs, dict):
            for key in ("maxres", "standard", "high", "medium", "default"):
                candidate = thumbs.get(key)
                if isinstance(candidate, dict) and isinstance(candidate.get("url"), str):
                    thumb = candidate["url"]
                    break

        enriched.append(
            YouTubeVideoMetadata(
                video_id=item.video_id,
                title=title,
                channel=channel,
                duration_sec=duration_sec,
                thumbnail_url=thumb,
                watch_url=item.watch_url,
                embed_url=item.embed_url,
                raw=item.raw,
            )
        )

    return enriched
