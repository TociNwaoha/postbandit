from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import redis
import redis.asyncio as redis_async

from app.config import settings

logger = logging.getLogger(__name__)

_BLOCKED_SOURCE_PREFIX = "youtube:blocked-source-video"
_DEFAULT_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class BlockedSourceHint:
    source_video_id: str
    error_code: str


def _key(source_video_id: str) -> str:
    return f"{_BLOCKED_SOURCE_PREFIX}:{source_video_id}"


def _sanitize_source_video_id(source_video_id: str | None) -> str:
    return (source_video_id or "").strip()


def _sync_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


async def _async_client() -> redis_async.Redis:
    return redis_async.from_url(settings.redis_url, decode_responses=True)


def set_blocked_source_hint_sync(*, source_video_id: str, error_code: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
    clean_video_id = _sanitize_source_video_id(source_video_id)
    clean_code = (error_code or "").strip()
    if not clean_video_id or not clean_code:
        return

    payload = {"source_video_id": clean_video_id, "error_code": clean_code}
    client = _sync_client()
    try:
        client.set(_key(clean_video_id), json.dumps(payload), ex=max(60, int(ttl_seconds)))
    except Exception as exc:
        logger.warning(
            "[youtube] blocked source hint write failed source_video_id=%s error=%s",
            clean_video_id,
            exc,
        )
    finally:
        try:
            client.close()
        except Exception:
            pass


async def get_blocked_source_hint(source_video_id: str | None) -> BlockedSourceHint | None:
    clean_video_id = _sanitize_source_video_id(source_video_id)
    if not clean_video_id:
        return None

    client = await _async_client()
    try:
        raw = await client.get(_key(clean_video_id))
    except Exception as exc:
        logger.warning(
            "[youtube] blocked source hint read failed source_video_id=%s error=%s",
            clean_video_id,
            exc,
        )
        return None
    finally:
        await client.aclose()

    if not raw:
        return None

    try:
        payload = json.loads(raw)
    except Exception:
        return None

    code = str(payload.get("error_code") or "").strip()
    if not code:
        return None
    return BlockedSourceHint(source_video_id=clean_video_id, error_code=code)
