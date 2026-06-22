from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_PARAM_NAMES = {
    "access_token",
    "refresh_token",
    "client_secret",
    "appsecret_proof",
    "code",
}
_TOKEN_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+\-/=]+", re.IGNORECASE),
    re.compile(r"(access_token=)[^\s&]+", re.IGNORECASE),
    re.compile(r"(refresh_token=)[^\s&]+", re.IGNORECASE),
    re.compile(r"(client_secret=)[^\s&]+", re.IGNORECASE),
]


def redact_url(value: str | None) -> str | None:
    if not value:
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return sanitize_sensitive_text(value)
    if not parts.query:
        return value
    query = []
    for key, raw_value in parse_qsl(parts.query, keep_blank_values=True):
        query.append((key, "[REDACTED]" if key.lower() in SENSITIVE_PARAM_NAMES else raw_value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def sanitize_sensitive_text(value: object, *, max_length: int = 500) -> str:
    text = str(value or "")
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(r"\1[REDACTED]", text)
    return text[:max_length]
