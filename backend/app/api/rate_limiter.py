from urllib.parse import urlsplit, urlunsplit

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def auth_rate_limit_redis_url() -> str:
    parsed = urlsplit(settings.redis_url)
    path = f"/{int(settings.auth_rate_limit_redis_db)}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=auth_rate_limit_redis_url(),
)
