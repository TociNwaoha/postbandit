from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import redis.asyncio as redis_async

from app.config import settings
from app.models.user import UserTier

API_RATE_LIMITS: dict[str, dict[str, int]] = {
    "starter": {"per_hour": 50, "per_day": 200},
    "creator": {"per_hour": 200, "per_day": 2000},
    "agency": {"per_hour": 1000, "per_day": 10000},
}
DEFAULT_LIMITS = API_RATE_LIMITS["starter"]


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    current_hour: int
    current_day: int
    limit_hour: int
    limit_day: int
    warning: bool
    reset_hour: datetime
    reset_day: datetime
    exceeded_scope: str | None = None


def redis_db3_url() -> str:
    parsed = urlsplit(settings.redis_url)
    path = f"/{int(settings.api_rate_limit_redis_db)}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def get_plan_limits(plan: str | UserTier | None) -> dict[str, int]:
    key = plan.value if hasattr(plan, "value") else str(plan or "starter")
    return dict(API_RATE_LIMITS.get(key, DEFAULT_LIMITS))


def _window_times(now: datetime) -> tuple[int, int, datetime, datetime]:
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    hour_reset = hour_start + timedelta(hours=1)
    day_reset = day_start + timedelta(days=1)
    return int(hour_start.timestamp()), int(day_start.timestamp()), hour_reset, day_reset


async def get_usage(user_id: str, plan: str | UserTier | None) -> RateLimitResult:
    now = datetime.now(timezone.utc)
    hour_ts, day_ts, hour_reset, day_reset = _window_times(now)
    limits = get_plan_limits(plan)
    client = redis_async.from_url(redis_db3_url(), decode_responses=True)
    try:
        hour_key = f"rate:{user_id}:hour:{hour_ts}"
        day_key = f"rate:{user_id}:day:{day_ts}"
        values = await client.mget(hour_key, day_key)
        current_hour = int(values[0] or 0)
        current_day = int(values[1] or 0)
    finally:
        await client.aclose()

    limit_hour = limits["per_hour"]
    limit_day = limits["per_day"]
    warning = current_hour >= limit_hour * 0.8 or current_day >= limit_day * 0.8
    return RateLimitResult(
        allowed=current_hour < limit_hour and current_day < limit_day,
        current_hour=current_hour,
        current_day=current_day,
        limit_hour=limit_hour,
        limit_day=limit_day,
        warning=warning,
        reset_hour=hour_reset,
        reset_day=day_reset,
    )


async def consume_rate_limit(user_id: str, plan: str | UserTier | None) -> RateLimitResult:
    now = datetime.now(timezone.utc)
    hour_ts, day_ts, hour_reset, day_reset = _window_times(now)
    limits = get_plan_limits(plan)
    hour_key = f"rate:{user_id}:hour:{hour_ts}"
    day_key = f"rate:{user_id}:day:{day_ts}"
    client = redis_async.from_url(redis_db3_url(), decode_responses=True)
    try:
        pipe = client.pipeline(transaction=True)
        pipe.incr(hour_key)
        pipe.expire(hour_key, 3600)
        pipe.incr(day_key)
        pipe.expire(day_key, 86400)
        result = await pipe.execute()
        current_hour = int(result[0])
        current_day = int(result[2])
    finally:
        await client.aclose()

    limit_hour = limits["per_hour"]
    limit_day = limits["per_day"]
    exceeded_scope = None
    if current_hour > limit_hour:
        exceeded_scope = "hour"
    elif current_day > limit_day:
        exceeded_scope = "day"
    warning = current_hour >= limit_hour * 0.8 or current_day >= limit_day * 0.8
    return RateLimitResult(
        allowed=exceeded_scope is None,
        current_hour=current_hour,
        current_day=current_day,
        limit_hour=limit_hour,
        limit_day=limit_day,
        warning=warning,
        reset_hour=hour_reset,
        reset_day=day_reset,
        exceeded_scope=exceeded_scope,
    )
