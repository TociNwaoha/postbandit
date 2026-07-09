import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.api_keys import find_active_api_key, looks_like_api_key, mark_api_key_used
from app.services.api_rate_limits import RateLimitResult, consume_rate_limit

optional_bearer_scheme = HTTPBearer(auto_error=False)


class V1Error(HTTPException):
    def __init__(self, status_code: int, error: str, message: str, headers: dict[str, str] | None = None):
        super().__init__(status_code=status_code, detail={"error": error, "message": message}, headers=headers)
        self.error = error
        self.message = message


def apply_rate_headers(response: Response, result: RateLimitResult) -> None:
    remaining_hour = max(0, result.limit_hour - result.current_hour)
    remaining_day = max(0, result.limit_day - result.current_day)
    response.headers["X-RateLimit-Limit-Hour"] = str(result.limit_hour)
    response.headers["X-RateLimit-Remaining-Hour"] = str(remaining_hour)
    response.headers["X-RateLimit-Limit-Day"] = str(result.limit_day)
    response.headers["X-RateLimit-Remaining-Day"] = str(remaining_day)
    response.headers["X-RateLimit-Reset-Hour"] = str(int(result.reset_hour.timestamp()))
    if result.warning:
        response.headers["X-RateLimit-Warning"] = "true"


def rate_headers(result: RateLimitResult) -> dict[str, str]:
    headers = {
        "X-RateLimit-Limit-Hour": str(result.limit_hour),
        "X-RateLimit-Remaining-Hour": str(max(0, result.limit_hour - result.current_hour)),
        "X-RateLimit-Limit-Day": str(result.limit_day),
        "X-RateLimit-Remaining-Day": str(max(0, result.limit_day - result.current_day)),
        "X-RateLimit-Reset-Hour": str(int(result.reset_hour.timestamp())),
    }
    if result.warning:
        headers["X-RateLimit-Warning"] = "true"
    return headers


async def _user_from_jwt(token: str, db: AsyncSession) -> User:
    credentials_exception = V1Error(status.HTTP_401_UNAUTHORIZED, "invalid_token", "Invalid or expired token")
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        user_uuid = uuid.UUID(user_id)
    except (JWTError, ValueError) as exc:
        raise credentials_exception from exc

    user = await db.scalar(select(User).where(User.id == user_uuid))
    if user is None:
        raise credentials_exception
    return user


async def get_v1_current_user(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else None
    if not token:
        raise V1Error(status.HTTP_401_UNAUTHORIZED, "missing_authorization", "Authorization bearer token is required")

    if looks_like_api_key(token):
        api_key = await find_active_api_key(db, full_key=token)
        if not api_key:
            raise V1Error(status.HTTP_401_UNAUTHORIZED, "invalid_api_key", "The API key is invalid or revoked")
        user = await db.scalar(select(User).where(User.id == api_key.user_id))
        if not user:
            raise V1Error(status.HTTP_401_UNAUTHORIZED, "invalid_api_key", "The API key user no longer exists")
        rate = await consume_rate_limit(str(user.id), user.tier)
        apply_rate_headers(response, rate)
        if not rate.allowed:
            reset_at = rate.reset_hour if rate.exceeded_scope == "hour" else rate.reset_day
            limit = rate.limit_hour if rate.exceeded_scope == "hour" else rate.limit_day
            raise V1Error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "rate_limit_exceeded",
                f"You have exceeded your {rate.exceeded_scope or 'API'} API limit. Upgrade for higher limits.",
                headers={
                    **rate_headers(rate),
                    "Retry-After": str(max(1, int((reset_at - datetime.now(timezone.utc)).total_seconds()))),
                },
            )
        mark_api_key_used(api_key)
        request.state.v1_auth_type = "api_key"
        return user

    user = await _user_from_jwt(token, db)
    rate = await consume_rate_limit(str(user.id), user.tier)
    apply_rate_headers(response, rate)
    if not rate.allowed:
        raise V1Error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limit_exceeded",
            "You have exceeded your API limit.",
            headers=rate_headers(rate),
        )
    request.state.v1_auth_type = "jwt"
    return user
