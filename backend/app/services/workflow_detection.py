from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings
from app.models.connected_account import ConnectedAccount, SocialPlatform
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.social.registry import get_adapter


@dataclass(frozen=True)
class DetectedPost:
    external_id: str
    url: str | None
    title: str | None
    description: str | None
    published_at: datetime | None


SOURCE_SCOPES: dict[SocialPlatform, set[str]] = {
    SocialPlatform.youtube: {"https://www.googleapis.com/auth/youtube.readonly"},
    SocialPlatform.instagram: {"instagram_business_basic"},
    SocialPlatform.threads: {"threads_basic"},
    SocialPlatform.facebook: {"pages_read_engagement"},
    SocialPlatform.tiktok: {"video.list"},
    SocialPlatform.x: {"tweet.read", "users.read"},
}


def source_capability(account: ConnectedAccount) -> tuple[str, str | None, list[str]]:
    if account.platform == SocialPlatform.linkedin:
        return "unsupported", "LinkedIn source monitoring is not available yet.", []
    required = SOURCE_SCOPES.get(account.platform)
    if not required:
        return "unsupported", "This provider does not support source monitoring.", []
    if account.platform == SocialPlatform.facebook:
        destination_type = str((account.metadata_json or {}).get("destination_type") or "")
        if destination_type != "facebook_page":
            return "unsupported", "Facebook monitoring requires a connected Page.", []
    present = {str(scope).strip().lower() for scope in (account.scopes or [])}
    missing = sorted(scope for scope in required if scope.lower() not in present)
    if missing:
        return "reconnect_required", "Reconnect this account to grant post-reading access.", missing
    return "ready", None, []


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _refresh_if_needed(account: ConnectedAccount, db) -> str:
    access_token = decrypt_secret(account.access_token_encrypted)
    expiry = account.token_expires_at
    if not expiry or expiry > datetime.now(timezone.utc) + timedelta(minutes=2):
        return access_token
    refresh_token = decrypt_secret(account.refresh_token_encrypted) if account.refresh_token_encrypted else None
    if account.platform == SocialPlatform.threads:
        from app.services.social.threads import _refresh_long_lived_token

        with httpx.Client(timeout=30) as client:
            new_access, new_expiry = _refresh_long_lived_token(client, access_token=access_token)
        account.access_token_encrypted = encrypt_secret(new_access)
        account.token_expires_at = new_expiry
        db.commit()
        return new_access
    if not refresh_token:
        raise RuntimeError("Access token expired. Reconnect this account.")
    adapter = get_adapter(account.platform)
    if account.platform == SocialPlatform.youtube:
        new_access, new_expiry = adapter._refresh_access_token(refresh_token)
        account.access_token_encrypted = encrypt_secret(new_access)
        account.token_expires_at = new_expiry
        db.commit()
        return new_access
    if account.platform == SocialPlatform.x:
        new_access, new_refresh, new_expiry = adapter._refresh_access_token(refresh_token)
        account.access_token_encrypted = encrypt_secret(new_access)
        account.refresh_token_encrypted = encrypt_secret(new_refresh)
        account.token_expires_at = new_expiry
        db.commit()
        return new_access
    if account.platform == SocialPlatform.tiktok:
        with httpx.Client(timeout=30) as client:
            payload = adapter._refresh_token(client, refresh_token=refresh_token)
        new_access = str(payload.get("access_token") or "").strip()
        if not new_access:
            raise RuntimeError("TikTok token refresh returned no access token.")
        new_refresh = str(payload.get("refresh_token") or "").strip()
        expires_in = payload.get("expires_in")
        account.access_token_encrypted = encrypt_secret(new_access)
        if new_refresh:
            account.refresh_token_encrypted = encrypt_secret(new_refresh)
        if isinstance(expires_in, (int, float)):
            account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        db.commit()
        return new_access
    raise RuntimeError("Access token expired. Reconnect this account.")


def _youtube_posts(client: httpx.Client, account: ConnectedAccount, token: str) -> list[DetectedPost]:
    headers = {"Authorization": f"Bearer {token}"}
    channel = (account.metadata_json or {}).get("channel") or {}
    uploads_id = (((channel.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads"))
    if not uploads_id:
        response = client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            headers=headers,
            params={"part": "contentDetails", "mine": "true"},
        )
        response.raise_for_status()
        channel = ((response.json().get("items") or [{}])[0])
        uploads_id = (((channel.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads"))
        if uploads_id:
            account.metadata_json = {**(account.metadata_json or {}), "channel": channel}
    if not uploads_id:
        raise RuntimeError("YouTube uploads playlist was not available. Reconnect YouTube.")
    response = client.get(
        "https://www.googleapis.com/youtube/v3/playlistItems",
        headers=headers,
        params={"part": "snippet,contentDetails", "playlistId": uploads_id, "maxResults": 10},
    )
    response.raise_for_status()
    posts: list[DetectedPost] = []
    for item in response.json().get("items") or []:
        snippet = item.get("snippet") or {}
        video_id = (item.get("contentDetails") or {}).get("videoId") or (
            (snippet.get("resourceId") or {}).get("videoId")
        )
        if video_id:
            posts.append(
                DetectedPost(
                    external_id=str(video_id),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    title=snippet.get("title"),
                    description=snippet.get("description"),
                    published_at=_parse_datetime(snippet.get("publishedAt")),
                )
            )
    return posts


def _instagram_posts(client: httpx.Client, account: ConnectedAccount, token: str) -> list[DetectedPost]:
    response = client.get(
        "https://graph.instagram.com/me/media",
        params={
            "fields": "id,caption,media_type,permalink,timestamp",
            "limit": 10,
            "access_token": token,
        },
    )
    response.raise_for_status()
    return [
        DetectedPost(
            external_id=str(item["id"]),
            url=item.get("permalink"),
            title=None,
            description=item.get("caption"),
            published_at=_parse_datetime(item.get("timestamp")),
        )
        for item in response.json().get("data") or []
        if item.get("id") and str(item.get("media_type") or "").upper() == "VIDEO"
    ]


def _threads_posts(client: httpx.Client, account: ConnectedAccount, token: str) -> list[DetectedPost]:
    response = client.get(
        f"https://graph.threads.net/{settings.threads_graph_api_version}/me/threads",
        params={
            "fields": "id,text,media_type,permalink,timestamp",
            "limit": 10,
            "access_token": token,
        },
    )
    response.raise_for_status()
    return [
        DetectedPost(
            external_id=str(item["id"]),
            url=item.get("permalink"),
            title=None,
            description=item.get("text"),
            published_at=_parse_datetime(item.get("timestamp")),
        )
        for item in response.json().get("data") or []
        if item.get("id") and str(item.get("media_type") or "").upper() == "VIDEO"
    ]


def _facebook_posts(client: httpx.Client, account: ConnectedAccount, token: str) -> list[DetectedPost]:
    response = client.get(
        f"https://graph.facebook.com/{settings.meta_graph_api_version}/{account.external_account_id}/published_posts",
        params={
            "fields": "id,message,permalink_url,created_time,attachments{media_type}",
            "limit": 10,
            "access_token": token,
        },
    )
    response.raise_for_status()
    posts: list[DetectedPost] = []
    for item in response.json().get("data") or []:
        attachments = ((item.get("attachments") or {}).get("data") or [])
        if not attachments or not any(
            str(value.get("media_type") or "").lower() == "video" for value in attachments
        ):
            continue
        if item.get("id"):
            posts.append(
                DetectedPost(
                    external_id=str(item["id"]),
                    url=item.get("permalink_url"),
                    title=None,
                    description=item.get("message"),
                    published_at=_parse_datetime(item.get("created_time")),
                )
            )
    return posts


def _tiktok_posts(client: httpx.Client, account: ConnectedAccount, token: str) -> list[DetectedPost]:
    response = client.post(
        "https://open.tiktokapis.com/v2/video/list/",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        params={"fields": "id,title,video_description,duration,share_url,create_time"},
        json={"max_count": 10},
    )
    response.raise_for_status()
    videos = ((response.json().get("data") or {}).get("videos") or [])
    return [
        DetectedPost(
            external_id=str(item["id"]),
            url=item.get("share_url"),
            title=item.get("title"),
            description=item.get("video_description"),
            published_at=_parse_datetime(item.get("create_time")),
        )
        for item in videos
        if item.get("id")
    ]


def _x_posts(client: httpx.Client, account: ConnectedAccount, token: str) -> list[DetectedPost]:
    response = client.get(
        f"https://api.x.com/2/users/{account.external_account_id}/tweets",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "max_results": 10,
            "tweet.fields": "created_at,attachments,text",
            "expansions": "attachments.media_keys",
            "media.fields": "type",
            "exclude": "retweets,replies",
        },
    )
    response.raise_for_status()
    payload = response.json()
    media_by_key = {item.get("media_key"): item for item in ((payload.get("includes") or {}).get("media") or [])}
    posts: list[DetectedPost] = []
    username = account.username_or_channel_name or account.external_account_id
    for item in payload.get("data") or []:
        keys = ((item.get("attachments") or {}).get("media_keys") or [])
        if not keys or not any(
            (media_by_key.get(key) or {}).get("type") in {"video", "animated_gif"} for key in keys
        ):
            continue
        post_id = item.get("id")
        if post_id:
            posts.append(
                DetectedPost(
                    external_id=str(post_id),
                    url=f"https://x.com/{username}/status/{post_id}",
                    title=None,
                    description=item.get("text"),
                    published_at=_parse_datetime(item.get("created_at")),
                )
            )
    return posts


def fetch_recent_posts(account: ConnectedAccount, db) -> list[DetectedPost]:
    status, message, _missing = source_capability(account)
    if status != "ready":
        raise RuntimeError(message or "Source monitoring is unavailable.")
    token = _refresh_if_needed(account, db)
    with httpx.Client(timeout=30) as client:
        if account.platform == SocialPlatform.youtube:
            posts = _youtube_posts(client, account, token)
        elif account.platform == SocialPlatform.instagram:
            posts = _instagram_posts(client, account, token)
        elif account.platform == SocialPlatform.threads:
            posts = _threads_posts(client, account, token)
        elif account.platform == SocialPlatform.facebook:
            posts = _facebook_posts(client, account, token)
        elif account.platform == SocialPlatform.tiktok:
            posts = _tiktok_posts(client, account, token)
        elif account.platform == SocialPlatform.x:
            posts = _x_posts(client, account, token)
        else:
            raise RuntimeError("Source monitoring is unavailable for this provider.")
    db.commit()
    return sorted(posts, key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc))
