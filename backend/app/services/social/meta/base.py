from __future__ import annotations

from app.config import settings
from app.services.social.base import is_placeholder
from app.services.social.meta.auth import build_callback_url, resolve_provider_credentials


def build_provider_setup_details(
    *,
    platform_value: str,
    primary_id_attr: str,
    primary_secret_attr: str,
    validate_with_client_credentials: bool = True,
    required_scopes: list[str],
    notes: str,
    supports_publish: bool,
) -> dict:
    credentials = resolve_provider_credentials(
        primary_id_attr=primary_id_attr,
        primary_secret_attr=primary_secret_attr,
        validate_with_client_credentials=validate_with_client_credentials,
    )
    callback_url, callback_error, callback_missing = build_callback_url(platform_value)

    missing_fields = list(credentials.missing_fields)
    if is_placeholder(settings.social_token_encryption_key):
        missing_fields.append("SOCIAL_TOKEN_ENCRYPTION_KEY")
    missing_fields.extend(callback_missing)
    missing_fields = sorted(set(missing_fields))

    configured = len(missing_fields) == 0
    message = None if configured else f"Missing/invalid required config: {', '.join(missing_fields)}"

    return {
        "configured": configured,
        "missing_fields": missing_fields,
        "message": message,
        "callback_url": callback_url,
        "callback_error": callback_error,
        "credential_source": credentials.source,
        "credential_rejections": [
            {"source": item.source, "reason": item.reason}
            for item in credentials.rejected_sources
        ],
        "fallback_in_use": credentials.source == "META_APP_ID/META_APP_SECRET"
        and len(credentials.rejected_sources) > 0,
        "validation_warning": credentials.validation_warning,
        "required_scopes": required_scopes,
        "supports_publish": supports_publish,
        "notes": notes,
    }
