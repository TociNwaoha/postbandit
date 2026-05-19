from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.models.connected_account import SocialPlatform
from app.services.social.base import ProviderOperationError, SocialProviderAdapter, utcnow
from app.services.social.meta import (
    GraphRequestError,
    build_provider_setup_details,
    graph_get,
    graph_post,
    resolve_provider_credentials,
)
from app.services.social.types import OAuthAccountPayload, ProviderCapabilities, PublishPayload, PublishResult

THREADS_SCOPES = [
    "threads_basic",
    "threads_content_publish",
]
THREADS_MAX_TEXT = 500
THREADS_REFRESH_WINDOW = timedelta(hours=12)


def _threads_auth_url() -> str:
    return "https://threads.net/oauth/authorize"


def _threads_token_url() -> str:
    return "https://graph.threads.net/oauth/access_token"


def _threads_long_lived_token_url() -> str:
    return "https://graph.threads.net/access_token"


def _threads_refresh_token_url() -> str:
    return "https://graph.threads.net/refresh_access_token"


def _threads_base() -> str:
    return f"https://graph.threads.net/{settings.threads_graph_api_version}"


def _parse_token_response(token_data: dict, *, missing_message: str) -> tuple[str, datetime | None]:
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise ProviderOperationError(missing_message)

    expires_in = token_data.get("expires_in")
    token_expires_at = None
    if isinstance(expires_in, (int, float)):
        token_expires_at = utcnow() + timedelta(seconds=int(expires_in))
    return access_token, token_expires_at


def _compose_text(payload: PublishPayload, *, allow_empty: bool = False) -> str | None:
    caption = (payload.caption or "").strip()
    if caption:
        return caption[:THREADS_MAX_TEXT]

    parts: list[str] = []
    title = (payload.title or "").strip()
    description = (payload.description or "").strip()
    if title:
        parts.append(title)
    if description:
        parts.append(description)
    if payload.hashtags:
        parts.append(" ".join(payload.hashtags))

    text = "\n\n".join(parts).strip()
    if not text:
        if allow_empty:
            return None
        raise ProviderOperationError("Threads publish text is empty. Provide caption/title/description/hashtags.")
    return text[:THREADS_MAX_TEXT]


def _exchange_long_lived_token(
    client: httpx.Client,
    *,
    short_lived_access_token: str,
    client_secret: str,
) -> tuple[str, datetime | None]:
    response = client.get(
        _threads_long_lived_token_url(),
        params={
            "grant_type": "th_exchange_token",
            "client_secret": client_secret,
            "access_token": short_lived_access_token,
        },
    )
    response.raise_for_status()
    token_data = response.json()
    if not isinstance(token_data, dict):
        raise ProviderOperationError("Threads long-lived token exchange returned invalid payload")
    return _parse_token_response(
        token_data,
        missing_message="Threads long-lived token exchange response missing access token",
    )


def _refresh_long_lived_token(
    client: httpx.Client,
    *,
    access_token: str,
) -> tuple[str, datetime | None]:
    response = client.get(
        _threads_refresh_token_url(),
        params={
            "grant_type": "th_refresh_token",
            "access_token": access_token,
        },
    )
    response.raise_for_status()
    token_data = response.json()
    if not isinstance(token_data, dict):
        raise ProviderOperationError("Threads token refresh returned invalid payload")
    return _parse_token_response(
        token_data,
        missing_message="Threads token refresh response missing access token",
    )


def _should_refresh_token(token_expires_at: datetime | None, *, now: datetime | None = None) -> bool:
    if token_expires_at is None:
        return False
    reference = now or utcnow()
    return token_expires_at <= (reference + THREADS_REFRESH_WINDOW)


def _resolve_threads_permalink(client: httpx.Client, *, access_token: str, post_id: str) -> str | None:
    details = graph_get(
        client,
        url=f"{_threads_base()}/{post_id}",
        params={"fields": "id,permalink", "access_token": access_token},
    )
    permalink = details.get("permalink")
    if isinstance(permalink, str) and permalink.startswith("http"):
        return permalink
    return None


class ThreadsAdapter(SocialProviderAdapter):
    platform = SocialPlatform.threads
    display_name = "Threads"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_connect=True,
            supports_publish_now=True,
            supports_schedule=True,
            supports_video_upload=True,
            supports_caption=True,
            supports_title=True,
            supports_description=True,
            supports_hashtags=True,
            supports_privacy=False,
            supports_multiple_accounts=True,
            may_require_user_completion=False,
        )

    def setup_details(self) -> dict:
        details = build_provider_setup_details(
            platform_value=self.platform.value,
            primary_id_attr="threads_app_id",
            primary_secret_attr="threads_app_secret",
            validate_with_client_credentials=False,
            required_scopes=list(THREADS_SCOPES),
            notes="Threads connect and publish are implemented for text and video using the Threads API container flow.",
            supports_publish=True,
        )
        return {
            **details,
            "login_model": "threads_oauth",
            "token_lifecycle": "short_to_long_with_refresh",
            "connect_ready": details["configured"],
            "publish_text_ready": details["configured"],
            "publish_media_ready": details["configured"],
        }

    def setup_status(self) -> tuple[str, str | None]:
        details = self.setup_details()
        if details["configured"]:
            return "ready", None
        return "provider_not_configured", details["message"]

    def _credentials(self):
        return resolve_provider_credentials(
            primary_id_attr="threads_app_id",
            primary_secret_attr="threads_app_secret",
            validate_with_client_credentials=False,
        )

    def build_connect_url(self, *, state: str, redirect_uri: str, oauth_context: dict | None = None) -> str:
        status, message = self.setup_status()
        if status != "ready":
            raise ProviderOperationError(message or "Threads provider not configured")

        creds = self._credentials()
        if not creds.client_id:
            raise ProviderOperationError("Threads app credentials are missing")

        params = {
            "client_id": creds.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(THREADS_SCOPES),
            "state": state,
        }
        return f"{_threads_auth_url()}?{urlencode(params)}"

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        oauth_context: dict | None = None,
    ) -> OAuthAccountPayload:
        status, message = self.setup_status()
        if status != "ready":
            raise ProviderOperationError(message or "Threads provider not configured")

        creds = self._credentials()
        if not creds.client_id or not creds.client_secret:
            raise ProviderOperationError("Threads app credentials are missing")

        try:
            with httpx.Client(timeout=30) as client:
                token_response = client.post(
                    _threads_token_url(),
                    data={
                        "client_id": creds.client_id,
                        "client_secret": creds.client_secret,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri,
                        "code": code,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                token_response.raise_for_status()
                token_data = token_response.json()
                if not isinstance(token_data, dict):
                    raise ProviderOperationError("Threads OAuth response payload was invalid")

                short_lived_access_token, _ = _parse_token_response(
                    token_data,
                    missing_message="Threads OAuth response missing access token",
                )
                access_token, token_expires_at = _exchange_long_lived_token(
                    client,
                    short_lived_access_token=short_lived_access_token,
                    client_secret=creds.client_secret,
                )

                profile = graph_get(
                    client,
                    url=f"{_threads_base()}/me",
                    params={
                        "fields": "id,username,name,threads_profile_picture_url,threads_biography",
                        "access_token": access_token,
                    },
                )
        except httpx.HTTPStatusError as exc:
            error_message = exc.response.text[:240] if exc.response is not None else "token_exchange_failed"
            raise ProviderOperationError(f"Threads OAuth failed: {error_message}") from exc
        except GraphRequestError as exc:
            raise ProviderOperationError(f"Threads OAuth failed: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderOperationError("Threads OAuth request failed. Please retry.") from exc

        external_id = str(profile.get("id") or "").strip()
        if not external_id:
            raise ProviderOperationError("Threads OAuth did not return account identity")

        username = str(profile.get("username") or "").strip() or None
        display_name = str(profile.get("name") or profile.get("username") or "").strip() or None

        metadata = {
            "provider_family": "meta",
            "destination_type": "threads_profile",
            "destination_id": external_id,
            "destination_name": display_name,
            "profile": {
                "id": external_id,
                "username": username,
                "name": display_name,
                "threads_profile_picture_url": profile.get("threads_profile_picture_url"),
                "threads_biography": profile.get("threads_biography"),
            },
        }

        return OAuthAccountPayload(
            external_account_id=external_id,
            display_name=display_name,
            username_or_channel_name=username,
            access_token=access_token,
            refresh_token=None,
            token_expires_at=token_expires_at,
            scopes=list(THREADS_SCOPES),
            metadata_json=metadata,
        )

    def publish(
        self,
        *,
        media_path: str,
        media_url: str | None,
        payload: PublishPayload,
        access_token: str,
        refresh_token: str | None,
        token_expires_at,
    ) -> PublishResult:
        status, message = self.setup_status()
        if status != "ready":
            return PublishResult(status="provider_not_configured", error_message=message)

        user_id = (payload.destination_external_id or "").strip()
        if not user_id:
            return PublishResult(
                status="failed",
                error_message="Threads destination profile is missing for this publish job.",
            )

        try:
            text = _compose_text(payload, allow_empty=bool(media_url))
            active_token = access_token
            active_expires_at = token_expires_at
            refresh_metadata: dict = {}
            with httpx.Client(timeout=60) as client:
                now = utcnow()
                if _should_refresh_token(active_expires_at, now=now):
                    try:
                        refreshed_token, refreshed_expires_at = _refresh_long_lived_token(
                            client,
                            access_token=active_token,
                        )
                        active_token = refreshed_token
                        if refreshed_expires_at is not None:
                            active_expires_at = refreshed_expires_at
                        refresh_metadata["token_refreshed"] = True
                    except (ProviderOperationError, httpx.HTTPStatusError, httpx.RequestError) as refresh_exc:
                        refresh_metadata["token_refresh_error"] = str(refresh_exc)[:240]
                        if active_expires_at is not None and active_expires_at <= now:
                            return PublishResult(
                                status="waiting_user_action",
                                error_message="Threads token expired and refresh failed. Reconnect Threads.",
                                provider_metadata_json={
                                    "stage": "token_refresh",
                                    "reason": "token_expired_refresh_failed",
                                    "action": "reconnect_threads",
                                    **refresh_metadata,
                                },
                            )

                media_type = "VIDEO" if media_url else "TEXT"
                create_data = {
                    "media_type": media_type,
                    "access_token": active_token,
                }
                if text:
                    create_data["text"] = text
                if media_url:
                    create_data["video_url"] = media_url

                creation = graph_post(
                    client,
                    url=f"{_threads_base()}/me/threads",
                    data=create_data,
                )
                creation_id = str(creation.get("id") or "").strip()
                if not creation_id:
                    raise ProviderOperationError("Threads create payload returned no creation id")

                publish_data = graph_post(
                    client,
                    url=f"{_threads_base()}/me/threads_publish",
                    data={
                        "creation_id": creation_id,
                        "access_token": active_token,
                    },
                )
                post_id = str(publish_data.get("id") or "").strip()
                if not post_id:
                    raise ProviderOperationError("Threads publish returned no post id")

                permalink = _resolve_threads_permalink(client, access_token=active_token, post_id=post_id)
        except GraphRequestError as exc:
            reason = str(exc).lower()
            if any(
                key in reason
                for key in (
                    "permission",
                    "authorized",
                    "not_authorized",
                    "review",
                    "not allowed",
                    "live mode",
                    "threads_content_publish",
                )
            ):
                return PublishResult(
                    status="waiting_user_action",
                    error_message=f"Threads publish requires additional app permissions or review state: {exc}",
                    provider_metadata_json={
                        "stage": "publish_media" if media_url else "publish_text",
                        "reason": "permissions_or_review",
                        "action": "check_threads_app_permissions",
                    },
                )
            return PublishResult(
                status="failed",
                error_message=f"Threads publish failed: {exc}",
                provider_metadata_json={"stage": "publish_media" if media_url else "publish_text"},
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            return PublishResult(
                status="failed",
                error_message=f"Threads publish request failed: {exc}",
                provider_metadata_json={"stage": "publish_media" if media_url else "publish_text"},
            )
        except ProviderOperationError as exc:
            return PublishResult(
                status="failed",
                error_message=str(exc),
                provider_metadata_json={"stage": "compose_or_publish", "media_mode": "video" if media_url else "text"},
            )

        token_updated = active_token != access_token
        expires_at_updated = active_expires_at != token_expires_at
        return PublishResult(
            status="published",
            external_post_id=post_id,
            external_post_url=permalink,
            provider_metadata_json={
                "threads_create_response": creation,
                "threads_publish_response": publish_data,
                "publish_mode": "video" if media_url else "text",
                "destination_external_id": user_id,
                **refresh_metadata,
            },
            updated_access_token=active_token if token_updated else None,
            updated_token_expires_at=active_expires_at if (token_updated or expires_at_updated) else None,
        )
