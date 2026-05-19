from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis_async

from app.config import settings

logger = logging.getLogger(__name__)

_LOCAL_HELPER_PREFIX = "youtube:local-helper"
_LOCAL_HELPER_RATE_PREFIX = "youtube:local-helper:rate"


class LocalHelperSessionError(Exception):
    pass


@dataclass
class LocalHelperSessionPayload:
    token: str
    user_id: str
    video_id: str
    upload_key: str
    source_url: str
    expires_at: datetime


def _build_key(token: str) -> str:
    return f"{_LOCAL_HELPER_PREFIX}:{token}"


def _build_rate_key(user_id: str) -> str:
    return f"{_LOCAL_HELPER_RATE_PREFIX}:{user_id}"


async def _client() -> redis_async.Redis:
    return redis_async.from_url(settings.redis_url, decode_responses=True)


async def create_local_helper_session(
    *,
    user_id: str,
    video_id: str,
    upload_key: str,
    source_url: str,
    ttl_seconds: int,
) -> LocalHelperSessionPayload:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=max(60, int(ttl_seconds)))
    key = _build_key(token)
    payload = {
        "token": token,
        "user_id": str(user_id),
        "video_id": str(video_id),
        "upload_key": upload_key,
        "source_url": source_url,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    client = await _client()
    try:
        await client.set(key, json.dumps(payload), ex=max(60, int(ttl_seconds)))
    except Exception as exc:
        logger.warning("[youtube] local helper session store failed video_id=%s", video_id)
        raise LocalHelperSessionError("Could not start local helper session") from exc
    finally:
        await client.aclose()

    return LocalHelperSessionPayload(
        token=token,
        user_id=str(user_id),
        video_id=str(video_id),
        upload_key=upload_key,
        source_url=source_url,
        expires_at=expires_at,
    )


async def consume_local_helper_rate_limit(*, user_id: str, limit_per_hour: int) -> tuple[bool, int]:
    clean_user = (user_id or "").strip()
    if not clean_user:
        raise LocalHelperSessionError("Missing user identity for helper rate limit")
    limit = max(1, int(limit_per_hour))
    key = _build_rate_key(clean_user)
    client = await _client()
    try:
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, 3600)
        return current <= limit, int(current)
    except Exception as exc:
        logger.warning("[youtube] local helper rate limit check failed user_id=%s", clean_user)
        raise LocalHelperSessionError("Could not validate helper rate limit") from exc
    finally:
        await client.aclose()


async def consume_local_helper_session(*, token: str) -> LocalHelperSessionPayload:
    clean_token = (token or "").strip()
    if not clean_token:
        raise LocalHelperSessionError("Missing helper session token")

    key = _build_key(clean_token)
    client = await _client()
    try:
        raw = await client.getdel(key)
    except Exception as exc:
        logger.warning("[youtube] local helper session consume failed")
        raise LocalHelperSessionError("Could not validate local helper session") from exc
    finally:
        await client.aclose()

    if not raw:
        raise LocalHelperSessionError("Local helper session expired or already used")

    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise LocalHelperSessionError("Invalid local helper session payload") from exc

    expires_at_raw = str(payload.get("expires_at") or "").strip()
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except Exception as exc:
        raise LocalHelperSessionError("Local helper session missing expiry") from exc

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise LocalHelperSessionError("Local helper session expired")

    user_id = str(payload.get("user_id") or "").strip()
    video_id = str(payload.get("video_id") or "").strip()
    upload_key = str(payload.get("upload_key") or "").strip()
    source_url = str(payload.get("source_url") or "").strip()
    if not all((user_id, video_id, upload_key, source_url)):
        raise LocalHelperSessionError("Local helper session is incomplete")

    return LocalHelperSessionPayload(
        token=clean_token,
        user_id=user_id,
        video_id=video_id,
        upload_key=upload_key,
        source_url=source_url,
        expires_at=expires_at,
    )
