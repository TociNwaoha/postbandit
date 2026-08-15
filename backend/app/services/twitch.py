from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.twitch_service_credential import TwitchServiceCredential
from app.services.crypto import decrypt_secret, encrypt_secret, encryption_available

logger = logging.getLogger(__name__)

TWITCH_API = "https://api.twitch.tv/helix"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_APP_TOKEN_CACHE_KEY = "twitch:app-access-token"


class TwitchConfigurationError(RuntimeError):
    pass


class TwitchAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _require_config(*values: str) -> None:
    if not encryption_available() or any(not (value or "").strip() for value in values):
        raise TwitchConfigurationError("Twitch integration is not configured")


def verify_eventsub_signature(*, message_id: str, timestamp: str, raw_body: bytes, signature: str) -> bool:
    secret = settings.twitch_webhook_secret.encode("utf-8")
    if not secret or not message_id or not timestamp or not signature:
        return False
    digest = hmac.new(secret, message_id.encode("utf-8") + timestamp.encode("utf-8") + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature)


def claim_event_message(message_id: str, *, ttl_seconds: int = 600) -> bool:
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        return bool(client.set(f"twitch:eventsub:{message_id}", "1", nx=True, ex=ttl_seconds))
    finally:
        client.close()


def _app_access_token() -> str:
    _require_config(settings.twitch_client_id, settings.twitch_client_secret)
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        cached = client.get(_APP_TOKEN_CACHE_KEY)
        if cached:
            return cached
        response = httpx.post(
            TWITCH_TOKEN_URL,
            data={
                "client_id": settings.twitch_client_id,
                "client_secret": settings.twitch_client_secret,
                "grant_type": "client_credentials",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("access_token") or "")
        expires_in = int(payload.get("expires_in") or 0)
        if not token:
            raise TwitchAPIError("Twitch app-token response did not include an access token")
        client.set(_APP_TOKEN_CACHE_KEY, token, ex=max(60, expires_in - 120))
        return token
    finally:
        client.close()


def _twitch_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Client-Id": settings.twitch_client_id}


def get_twitch_user(login: str) -> dict:
    response = httpx.get(
        f"{TWITCH_API}/users",
        params={"login": login},
        headers=_twitch_headers(_app_access_token()),
        timeout=20,
    )
    if response.status_code >= 400:
        raise TwitchAPIError("Twitch channel lookup failed", response.status_code)
    items = response.json().get("data") or []
    if not items:
        raise TwitchAPIError("Twitch channel was not found", 404)
    return items[0]


def get_live_stream(broadcaster_id: str) -> dict | None:
    response = httpx.get(
        f"{TWITCH_API}/streams",
        params={"user_id": broadcaster_id},
        headers=_twitch_headers(_app_access_token()),
        timeout=20,
    )
    if response.status_code >= 400:
        raise TwitchAPIError("Twitch live-status lookup failed", response.status_code)
    streams = response.json().get("data") or []
    return streams[0] if streams else None


def ensure_eventsub_subscription(*, broadcaster_id: str, event_type: str) -> None:
    token = _app_access_token()
    headers = _twitch_headers(token)
    existing = httpx.get(f"{TWITCH_API}/eventsub/subscriptions", headers=headers, timeout=20)
    existing.raise_for_status()
    for item in existing.json().get("data") or []:
        if item.get("type") == event_type and item.get("condition", {}).get("broadcaster_user_id") == broadcaster_id:
            return

    response = httpx.post(
        f"{TWITCH_API}/eventsub/subscriptions",
        headers=headers,
        json={
            "type": event_type,
            "version": "1",
            "condition": {"broadcaster_user_id": broadcaster_id},
            "transport": {
                "method": "webhook",
                "callback": settings.twitch_eventsub_callback_url,
                "secret": settings.twitch_webhook_secret,
            },
        },
        timeout=20,
    )
    if response.status_code == 409:
        return
    if response.status_code >= 400:
        raise TwitchAPIError("Twitch EventSub subscription failed", response.status_code)


def ensure_channel_subscriptions(broadcaster_id: str) -> None:
    _require_config(settings.twitch_client_id, settings.twitch_client_secret, settings.twitch_webhook_secret)
    ensure_eventsub_subscription(broadcaster_id=broadcaster_id, event_type="stream.online")
    ensure_eventsub_subscription(broadcaster_id=broadcaster_id, event_type="stream.offline")


def _bootstrap_service_credential(db: Session) -> TwitchServiceCredential:
    credential = db.get(TwitchServiceCredential, "default")
    if credential:
        return credential
    _require_config(settings.twitch_service_access_token, settings.twitch_service_refresh_token)
    credential = TwitchServiceCredential(
        key="default",
        access_token_encrypted=encrypt_secret(settings.twitch_service_access_token),
        refresh_token_encrypted=encrypt_secret(settings.twitch_service_refresh_token),
    )
    db.add(credential)
    db.commit()
    return credential


def _refresh_service_token(db: Session, credential: TwitchServiceCredential) -> str:
    _require_config(settings.twitch_client_id, settings.twitch_client_secret)
    refresh_token = decrypt_secret(credential.refresh_token_encrypted)
    response = httpx.post(
        TWITCH_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.twitch_client_id,
            "client_secret": settings.twitch_client_secret,
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise TwitchAPIError("Twitch service token refresh failed", response.status_code)
    payload = response.json()
    access_token = str(payload.get("access_token") or "")
    new_refresh_token = str(payload.get("refresh_token") or "")
    if not access_token or not new_refresh_token:
        raise TwitchAPIError("Twitch service token refresh returned incomplete credentials")
    expires_in = int(payload.get("expires_in") or 0)
    credential.access_token_encrypted = encrypt_secret(access_token)
    credential.refresh_token_encrypted = encrypt_secret(new_refresh_token)
    credential.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    credential.last_token_refresh = datetime.now(timezone.utc)
    db.commit()
    return access_token


def get_service_user_token(db: Session, *, force_refresh: bool = False) -> str:
    credential = _bootstrap_service_credential(db)
    expires_at = credential.token_expires_at
    if force_refresh or (expires_at and expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5)):
        return _refresh_service_token(db, credential)
    return decrypt_secret(credential.access_token_encrypted)


def consume_clip_rate_limit() -> bool:
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        window = int(time.time() // 60)
        key = f"twitch:create-clip:{window}"
        used = int(client.incr(key))
        if used == 1:
            client.expire(key, 70)
        return used <= settings.twitch_clip_rate_limit_per_minute
    finally:
        client.close()


def create_clip_for_broadcaster(db: Session, broadcaster_id: str) -> dict:
    if not consume_clip_rate_limit():
        raise TwitchAPIError("Twitch live clipping is temporarily rate limited", 429)
    token = get_service_user_token(db)
    response = httpx.post(
        f"{TWITCH_API}/clips",
        params={"broadcaster_id": broadcaster_id},
        headers=_twitch_headers(token),
        timeout=20,
    )
    if response.status_code == 401:
        token = get_service_user_token(db, force_refresh=True)
        response = httpx.post(
            f"{TWITCH_API}/clips",
            params={"broadcaster_id": broadcaster_id},
            headers=_twitch_headers(token),
            timeout=20,
        )
    if response.status_code >= 400:
        raise TwitchAPIError("Twitch could not create a clip. The channel may have clipping disabled.", response.status_code)
    clips = response.json().get("data") or []
    if not clips or not clips[0].get("id"):
        raise TwitchAPIError("Twitch did not return a clip ID")
    return clips[0]


def wait_for_clip(clip_id: str, *, timeout_seconds: int = 60) -> dict:
    deadline = time.monotonic() + timeout_seconds
    token = _app_access_token()
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{TWITCH_API}/clips",
            params={"id": clip_id},
            headers=_twitch_headers(token),
            timeout=20,
        )
        if response.status_code == 401:
            token = _app_access_token()
            continue
        if response.status_code >= 400:
            raise TwitchAPIError("Twitch clip lookup failed", response.status_code)
        clips = response.json().get("data") or []
        if clips:
            return clips[0]
        time.sleep(2)
    raise TwitchAPIError("Twitch did not finish creating the clip within 60 seconds")
