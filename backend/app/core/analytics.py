"""Best-effort product analytics that must never affect product workflows."""

from __future__ import annotations

import logging
from typing import Any

from posthog import Posthog

from app.config import settings

logger = logging.getLogger(__name__)
_client: Posthog | None = None


def _get_client() -> Posthog | None:
    global _client
    if _client is not None:
        return _client

    api_key = settings.posthog_api_key.strip()
    if not api_key:
        return None

    _client = Posthog(api_key, host=settings.posthog_host)
    return _client


def track(distinct_id: str, event: str, properties: dict[str, Any] | None = None) -> None:
    """Capture an event without allowing analytics failures to affect product behavior."""
    try:
        client = _get_client()
        if client is not None:
            client.capture(event, distinct_id=distinct_id, properties=properties or {})
    except Exception:
        logger.debug("PostHog capture failed for event=%s", event, exc_info=True)
