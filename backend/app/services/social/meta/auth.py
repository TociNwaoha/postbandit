from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlencode, urlparse

import httpx

from app.config import settings
from app.services.social.base import is_placeholder


@dataclass(frozen=True)
class CredentialRejection:
    source: str
    reason: str


@dataclass(frozen=True)
class ProviderCredentials:
    client_id: str | None
    client_secret: str | None
    source: str | None
    missing_fields: list[str]
    rejected_sources: list[CredentialRejection] = field(default_factory=list)
    validation_warning: str | None = None


def _env_name(setting_name: str) -> str:
    return setting_name.upper()


def _extract_meta_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = None

    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            message = err.get("message")
            code = err.get("code")
            if isinstance(message, str) and message.strip():
                if isinstance(code, int):
                    return f"{message.strip()} (code {code})"[:220]
                return message.strip()[:220]
        for key in ("error_description", "error_message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:220]

    return f"http_{response.status_code}"


@lru_cache(maxsize=64)
def _validate_meta_credentials(
    client_id: str,
    client_secret: str,
    graph_api_version: str,
) -> tuple[str, str | None]:
    token_url = f"https://graph.facebook.com/{graph_api_version}/oauth/access_token"
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }

    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(token_url, params=params)
    except httpx.RequestError:
        return "unknown", "Meta credential validation request failed"

    if response.status_code >= 400:
        return "invalid", _extract_meta_error(response)

    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        return "invalid", "Meta credential validation returned invalid JSON"

    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if isinstance(access_token, str) and access_token.strip():
        return "valid", None

    return "invalid", "Meta credential validation response missing access token"


def resolve_provider_credentials(
    *,
    primary_id_attr: str,
    primary_secret_attr: str,
    fallback_id_attr: str = "meta_app_id",
    fallback_secret_attr: str = "meta_app_secret",
    validate_with_client_credentials: bool = True,
) -> ProviderCredentials:
    primary_id = getattr(settings, primary_id_attr, None)
    primary_secret = getattr(settings, primary_secret_attr, None)
    fallback_id = getattr(settings, fallback_id_attr, None)
    fallback_secret = getattr(settings, fallback_secret_attr, None)

    primary_ready = not is_placeholder(primary_id) and not is_placeholder(primary_secret)
    fallback_ready = not is_placeholder(fallback_id) and not is_placeholder(fallback_secret)

    missing_fields: list[str] = []
    if is_placeholder(primary_id) and is_placeholder(fallback_id):
        missing_fields.extend([_env_name(primary_id_attr), _env_name(fallback_id_attr)])
    if is_placeholder(primary_secret) and is_placeholder(fallback_secret):
        missing_fields.extend([_env_name(primary_secret_attr), _env_name(fallback_secret_attr)])

    candidate_specs: list[tuple[str, str, str, str]] = []
    if primary_ready:
        candidate_specs.append(
            (
                str(primary_id),
                str(primary_secret),
                _env_name(primary_id_attr),
                _env_name(primary_secret_attr),
            )
        )
    if fallback_ready:
        candidate_specs.append(
            (
                str(fallback_id),
                str(fallback_secret),
                _env_name(fallback_id_attr),
                _env_name(fallback_secret_attr),
            )
        )

    rejected_sources: list[CredentialRejection] = []
    validation_warning: str | None = None

    if not validate_with_client_credentials:
        if candidate_specs:
            client_id, client_secret, id_env, secret_env = candidate_specs[0]
            return ProviderCredentials(
                client_id=client_id,
                client_secret=client_secret,
                source=f"{id_env}/{secret_env}",
                missing_fields=sorted(set(missing_fields)),
                rejected_sources=[],
                validation_warning="Credential preflight skipped for provider",
            )
        return ProviderCredentials(
            client_id=None,
            client_secret=None,
            source=None,
            missing_fields=sorted(set(missing_fields)),
            rejected_sources=[],
            validation_warning=None,
        )

    for client_id, client_secret, id_env, secret_env in candidate_specs:
        source = f"{id_env}/{secret_env}"
        status, reason = _validate_meta_credentials(
            client_id=client_id,
            client_secret=client_secret,
            graph_api_version=settings.meta_graph_api_version,
        )

        if status == "valid":
            return ProviderCredentials(
                client_id=client_id,
                client_secret=client_secret,
                source=source,
                missing_fields=sorted(set(missing_fields)),
                rejected_sources=rejected_sources,
                validation_warning=validation_warning,
            )

        if status == "unknown":
            validation_warning = reason
            return ProviderCredentials(
                client_id=client_id,
                client_secret=client_secret,
                source=source,
                missing_fields=sorted(set(missing_fields)),
                rejected_sources=rejected_sources,
                validation_warning=validation_warning,
            )

        rejected_sources.append(
            CredentialRejection(
                source=source,
                reason=reason or "Meta rejected app credentials",
            )
        )
        missing_fields.extend([id_env, secret_env])

    return ProviderCredentials(
        client_id=None,
        client_secret=None,
        source=None,
        missing_fields=sorted(set(missing_fields)),
        rejected_sources=rejected_sources,
        validation_warning=validation_warning,
    )


def build_callback_url(platform_value: str) -> tuple[str | None, str | None, list[str]]:
    missing_fields: list[str] = []
    backend_public_url = (settings.backend_public_url or "").strip()
    if is_placeholder(backend_public_url):
        missing_fields.append("BACKEND_PUBLIC_URL")
        return None, "BACKEND_PUBLIC_URL is missing", missing_fields

    parsed = urlparse(backend_public_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        missing_fields.append("BACKEND_PUBLIC_URL")
        return None, "BACKEND_PUBLIC_URL must be an absolute http(s) URL", missing_fields

    callback_url = f"{backend_public_url.rstrip('/')}/api/social/{platform_value}/callback"
    return callback_url, None, missing_fields


def build_oauth_url(
    *,
    authorize_url: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: list[str],
    scope_delimiter: str = ",",
    extra_params: dict[str, str] | None = None,
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "scope": scope_delimiter.join(scopes),
    }
    if extra_params:
        params.update(extra_params)
    return f"{authorize_url}?{urlencode(params)}"
