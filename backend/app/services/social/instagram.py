from __future__ import annotations

import time
from datetime import timedelta

import httpx

from app.config import settings
from app.models.connected_account import SocialPlatform
from app.services.social.base import ProviderOperationError, SocialProviderAdapter, utcnow
from app.services.social.meta import (
    GraphRequestError,
    build_oauth_url,
    build_provider_setup_details,
    graph_get,
    graph_post,
    resolve_provider_credentials,
)
from app.services.social.types import (
    OAuthAccountPayload,
    OAuthExchangeResult,
    ProviderCapabilities,
    PublishPayload,
    PublishResult,
)

INSTAGRAM_SCOPES = [
    "instagram_business_basic",
    "instagram_business_content_publish",
]

INSTAGRAM_ACCOUNT_FIELDS = "id,username,name,account_type,profile_picture_url"
INSTAGRAM_ACCOUNT_FIELDS_FALLBACK = "id,username"

IG_CONTAINER_POLL_SECONDS = 4
IG_CONTAINER_MAX_WAIT_SECONDS = 180


def _graph_base() -> str:
    return "https://graph.instagram.com"


def _auth_url() -> str:
    return "https://www.instagram.com/oauth/authorize"


def _token_url() -> str:
    return "https://api.instagram.com/oauth/access_token"


def _extract_scopes(token_data: dict) -> list[str]:
    granted = token_data.get("granted_scopes")
    if isinstance(granted, list):
        values = [str(item).strip() for item in granted if str(item).strip()]
        if values:
            return values

    scope_raw = token_data.get("scope")
    if isinstance(scope_raw, list):
        values = [str(item).strip() for item in scope_raw if str(item).strip()]
        if values:
            return values
    if isinstance(scope_raw, str):
        values = [item.strip() for item in scope_raw.replace(",", " ").split() if item.strip()]
        if values:
            return values

    return list(INSTAGRAM_SCOPES)


def _normalize_profile(profile: dict, *, source: str) -> dict:
    metadata = {
        "provider_family": "meta",
        "destination_type": "instagram_professional",
        "destination_id": profile.get("id"),
        "destination_name": profile.get("name") or profile.get("username"),
        "account_type": profile.get("account_type"),
        "source": source,
        "profile": {
            "id": profile.get("id"),
            "username": profile.get("username"),
            "name": profile.get("name"),
            "account_type": profile.get("account_type"),
            "profile_picture_url": profile.get("profile_picture_url"),
        },
    }
    return metadata


def _resolve_permalink(client: httpx.Client, *, access_token: str, media_id: str) -> str | None:
    details = graph_get(
        client,
        url=f"{_graph_base()}/{media_id}",
        params={"fields": "id,permalink,shortcode", "access_token": access_token},
    )
    permalink = details.get("permalink")
    if isinstance(permalink, str) and permalink.startswith("http"):
        return permalink
    shortcode = details.get("shortcode")
    if isinstance(shortcode, str) and shortcode.strip():
        return f"https://www.instagram.com/p/{shortcode.strip()}/"
    return None


class InstagramAdapter(SocialProviderAdapter):
    platform = SocialPlatform.instagram
    display_name = "Instagram"

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
            primary_id_attr="instagram_app_id",
            primary_secret_attr="instagram_app_secret",
            validate_with_client_credentials=False,
            required_scopes=list(INSTAGRAM_SCOPES),
            notes="Connects Instagram professional (Business/Creator) accounts via Instagram Login.",
            supports_publish=True,
        )
        details.update(
            {
                "login_model": "instagram_login",
                "connect_ready": details.get("configured", False),
                "publish_ready": details.get("configured", False),
            }
        )
        return details

    def setup_status(self) -> tuple[str, str | None]:
        details = self.setup_details()
        if details["configured"]:
            return "ready", None
        return "provider_not_configured", details["message"]

    def _credentials(self):
        return resolve_provider_credentials(
            primary_id_attr="instagram_app_id",
            primary_secret_attr="instagram_app_secret",
            validate_with_client_credentials=False,
        )

    def build_connect_url(self, *, state: str, redirect_uri: str, oauth_context: dict | None = None) -> str:
        status, message = self.setup_status()
        if status != "ready":
            raise ProviderOperationError(message or "Instagram provider not configured")

        creds = self._credentials()
        if not creds.client_id:
            raise ProviderOperationError("Instagram app credentials are missing")

        return build_oauth_url(
            authorize_url=_auth_url(),
            client_id=creds.client_id,
            redirect_uri=redirect_uri,
            state=state,
            scopes=list(INSTAGRAM_SCOPES),
            scope_delimiter=",",
        )

    def exchange_code_result(
        self,
        *,
        code: str,
        redirect_uri: str,
        oauth_context: dict | None = None,
    ) -> OAuthExchangeResult:
        status, message = self.setup_status()
        if status != "ready":
            raise ProviderOperationError(message or "Instagram provider not configured")

        creds = self._credentials()
        if not creds.client_id or not creds.client_secret:
            raise ProviderOperationError("Instagram app credentials are missing")

        token_expires_at = None
        profile_source = "graph.instagram.com/me"

        try:
            with httpx.Client(timeout=30) as client:
                token_data = graph_post(
                    client,
                    url=_token_url(),
                    data={
                        "client_id": creds.client_id,
                        "client_secret": creds.client_secret,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri,
                        "code": code,
                    },
                )

                access_token = str(token_data.get("access_token") or "").strip()
                if not access_token:
                    raise ProviderOperationError("Instagram OAuth response missing access token")

                expires_in = token_data.get("expires_in")
                if isinstance(expires_in, (int, float)):
                    token_expires_at = utcnow() + timedelta(seconds=int(expires_in))

                try:
                    profile = graph_get(
                        client,
                        url=f"{_graph_base()}/me",
                        params={
                            "fields": INSTAGRAM_ACCOUNT_FIELDS,
                            "access_token": access_token,
                        },
                    )
                except GraphRequestError:
                    profile_source = "graph.instagram.com/me (fallback)"
                    profile = graph_get(
                        client,
                        url=f"{_graph_base()}/me",
                        params={
                            "fields": INSTAGRAM_ACCOUNT_FIELDS_FALLBACK,
                            "access_token": access_token,
                        },
                    )
        except GraphRequestError as exc:
            raise ProviderOperationError(f"Instagram OAuth failed: {exc}") from exc

        external_account_id = str(profile.get("id") or token_data.get("user_id") or "").strip()
        if not external_account_id:
            raise ProviderOperationError(
                "Instagram OAuth completed, but account identity was not returned."
            )

        account_type = str(profile.get("account_type") or "").strip().lower()
        if account_type and all(term not in account_type for term in ("business", "creator", "professional")):
            raise ProviderOperationError(
                "Instagram OAuth completed, but the connected account is not a professional (Business/Creator) account."
            )

        display_name = str(profile.get("name") or profile.get("username") or "").strip() or None
        username = str(profile.get("username") or "").strip() or None
        metadata = _normalize_profile(
            {
                "id": external_account_id,
                "username": username,
                "name": display_name,
                "account_type": profile.get("account_type"),
                "profile_picture_url": profile.get("profile_picture_url"),
            },
            source=profile_source,
        )

        accounts = [
            OAuthAccountPayload(
                external_account_id=external_account_id,
                display_name=display_name,
                username_or_channel_name=username,
                access_token=access_token,
                refresh_token=None,
                token_expires_at=token_expires_at,
                scopes=_extract_scopes(token_data),
                metadata_json=metadata,
            )
        ]

        return OAuthExchangeResult(
            accounts=accounts,
            provider_metadata_json={
                "destination_count": 1,
                "destination_type": "instagram_professional",
                "login_model": "instagram_login",
            },
        )

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        oauth_context: dict | None = None,
    ) -> OAuthAccountPayload:
        result = self.exchange_code_result(code=code, redirect_uri=redirect_uri, oauth_context=oauth_context)
        return result.accounts[0]

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

        if not media_url:
            return PublishResult(
                status="failed",
                error_message="Instagram publishing requires a reachable media URL.",
            )

        ig_user_id = (payload.destination_external_id or "").strip()
        if not ig_user_id:
            return PublishResult(
                status="failed",
                error_message="Instagram destination account is missing for this publish job.",
            )

        caption_parts = [item.strip() for item in [payload.caption, payload.description] if item and item.strip()]
        if payload.hashtags:
            caption_parts.append(" ".join(payload.hashtags))
        caption = "\n\n".join(caption_parts).strip()
        if not caption:
            caption = (payload.title or "Published via PostBandit").strip()

        try:
            with httpx.Client(timeout=120) as client:
                creation = graph_post(
                    client,
                    url=f"{_graph_base()}/{ig_user_id}/media",
                    data={
                        "access_token": access_token,
                        "media_type": "REELS",
                        "video_url": media_url,
                        "caption": caption[:2200],
                    },
                )
                creation_id = str(creation.get("id") or "").strip()
                if not creation_id:
                    raise ProviderOperationError("Instagram media container was not created")

                started = time.monotonic()
                while True:
                    status_payload = graph_get(
                        client,
                        url=f"{_graph_base()}/{creation_id}",
                        params={
                            "fields": "id,status_code,status,error_message",
                            "access_token": access_token,
                        },
                    )
                    status_code = str(status_payload.get("status_code") or status_payload.get("status") or "").upper()
                    if status_code in {"FINISHED", "PUBLISHED"}:
                        break
                    if status_code in {"ERROR", "EXPIRED"}:
                        error_detail = (
                            str(status_payload.get("error_message") or "").strip() or "Instagram processing failed"
                        )
                        raise ProviderOperationError(error_detail)
                    if time.monotonic() - started > IG_CONTAINER_MAX_WAIT_SECONDS:
                        raise ProviderOperationError("Instagram media processing timed out")
                    time.sleep(IG_CONTAINER_POLL_SECONDS)

                publish_data = graph_post(
                    client,
                    url=f"{_graph_base()}/{ig_user_id}/media_publish",
                    data={
                        "access_token": access_token,
                        "creation_id": creation_id,
                    },
                )
                media_id = str(publish_data.get("id") or "").strip()
                if not media_id:
                    raise ProviderOperationError("Instagram publish completed without media id")

                permalink = _resolve_permalink(client, access_token=access_token, media_id=media_id)
        except GraphRequestError as exc:
            reason = str(exc).lower()
            if any(key in reason for key in ("permission", "authorized", "professional", "review")):
                return PublishResult(
                    status="waiting_user_action",
                    error_message=f"Instagram publishing requires additional permissions or professional-account setup: {exc}",
                    provider_metadata_json={
                        "stage": "publish_reel",
                        "reason": "permissions_or_professional_account",
                        "action": "reconnect_instagram",
                    },
                )
            return PublishResult(
                status="failed",
                error_message=f"Instagram publish failed: {exc}",
                provider_metadata_json={"stage": "publish_reel"},
            )
        except ProviderOperationError as exc:
            return PublishResult(
                status="failed",
                error_message=str(exc),
                provider_metadata_json={"stage": "publish_reel"},
            )

        return PublishResult(
            status="published",
            external_post_id=media_id,
            external_post_url=permalink,
            provider_metadata_json={
                "container_id": creation_id,
                "instagram_publish_response": publish_data,
            },
        )
