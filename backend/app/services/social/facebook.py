from __future__ import annotations

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

FACEBOOK_SCOPES = [
    "pages_show_list",
    "pages_manage_posts",
    "pages_read_engagement",
    "public_profile",
]

FACEBOOK_PAGE_FIELDS = "id,name,category,link,picture{url},access_token,tasks"
FACEBOOK_ACCOUNT_FIELDS = "id,name,link,picture{url}"


def _graph_base() -> str:
    return f"https://graph.facebook.com/{settings.meta_graph_api_version}"


def _auth_url() -> str:
    return f"https://www.facebook.com/{settings.meta_graph_api_version}/dialog/oauth"


def _token_url() -> str:
    return f"{_graph_base()}/oauth/access_token"


def _normalize_page_metadata(page: dict) -> dict:
    picture = page.get("picture") if isinstance(page, dict) else None
    picture_data = picture.get("data") if isinstance(picture, dict) else None
    return {
        "provider_family": "meta",
        "destination_type": "facebook_page",
        "destination_id": page.get("id"),
        "destination_name": page.get("name"),
        "category": page.get("category"),
        "link": page.get("link"),
        "profile_picture_url": picture_data.get("url") if isinstance(picture_data, dict) else None,
        "tasks": page.get("tasks") if isinstance(page.get("tasks"), list) else [],
        "page": {
            "id": page.get("id"),
            "name": page.get("name"),
            "category": page.get("category"),
            "link": page.get("link"),
        },
    }


def _normalize_account_metadata(account: dict) -> dict:
    picture = account.get("picture") if isinstance(account, dict) else None
    picture_data = picture.get("data") if isinstance(picture, dict) else None
    return {
        "provider_family": "meta",
        "destination_type": "facebook_account",
        "destination_id": account.get("id"),
        "destination_name": account.get("name"),
        "link": account.get("link"),
        "profile_picture_url": picture_data.get("url") if isinstance(picture_data, dict) else None,
        "account": {
            "id": account.get("id"),
            "name": account.get("name"),
            "link": account.get("link"),
        },
    }


def _canonical_post_url(post_id: str | None, page_id: str) -> str | None:
    if post_id and "_" in post_id:
        page_part, post_part = post_id.split("_", 1)
        if page_part and post_part:
            return f"https://www.facebook.com/{page_part}/posts/{post_part}"
    if post_id:
        return f"https://www.facebook.com/{post_id}"
    if page_id:
        return f"https://www.facebook.com/{page_id}"
    return None


class FacebookAdapter(SocialProviderAdapter):
    platform = SocialPlatform.facebook
    display_name = "Facebook"

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
            primary_id_attr="facebook_app_id",
            primary_secret_attr="facebook_app_secret",
            required_scopes=list(FACEBOOK_SCOPES),
            notes="Publishes to Facebook Pages only (not personal profiles).",
            supports_publish=True,
        )
        details.update(
            {
                "supports_page_auto_publish": True,
                "supports_profile_auto_publish": False,
                "supports_profile_manual_share": True,
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
            primary_id_attr="facebook_app_id",
            primary_secret_attr="facebook_app_secret",
        )

    def build_connect_url(self, *, state: str, redirect_uri: str, oauth_context: dict | None = None) -> str:
        status, message = self.setup_status()
        if status != "ready":
            raise ProviderOperationError(message or "Facebook provider not configured")

        creds = self._credentials()
        if not creds.client_id:
            raise ProviderOperationError("Facebook app credentials are missing")

        return build_oauth_url(
            authorize_url=_auth_url(),
            client_id=creds.client_id,
            redirect_uri=redirect_uri,
            state=state,
            scopes=list(FACEBOOK_SCOPES),
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
            raise ProviderOperationError(message or "Facebook provider not configured")

        creds = self._credentials()
        if not creds.client_id or not creds.client_secret:
            raise ProviderOperationError("Facebook app credentials are missing")

        token_expires_at = None
        accounts: list[OAuthAccountPayload] = []
        pages_count = 0

        try:
            with httpx.Client(timeout=30) as client:
                token_data = graph_get(
                    client,
                    url=_token_url(),
                    params={
                        "client_id": creds.client_id,
                        "client_secret": creds.client_secret,
                        "redirect_uri": redirect_uri,
                        "code": code,
                    },
                )

                access_token = str(token_data.get("access_token") or "").strip()
                if not access_token:
                    raise ProviderOperationError("Facebook OAuth response missing access token")

                expires_in = token_data.get("expires_in")
                if isinstance(expires_in, (int, float)):
                    token_expires_at = utcnow() + timedelta(seconds=int(expires_in))

                account_data = graph_get(
                    client,
                    url=f"{_graph_base()}/me",
                    params={
                        "fields": FACEBOOK_ACCOUNT_FIELDS,
                        "access_token": access_token,
                    },
                )

                pages_data = graph_get(
                    client,
                    url=f"{_graph_base()}/me/accounts",
                    params={
                        "fields": FACEBOOK_PAGE_FIELDS,
                        "access_token": access_token,
                    },
                )
        except GraphRequestError as exc:
            raise ProviderOperationError(f"Facebook OAuth failed: {exc}") from exc

        account_id = str(account_data.get("id") or "").strip()
        if not account_id:
            raise ProviderOperationError(
                "Facebook OAuth completed, but account identity was not returned."
            )

        account_name = str(account_data.get("name") or "").strip() or None
        accounts.append(
            OAuthAccountPayload(
                external_account_id=account_id,
                display_name=account_name,
                username_or_channel_name=account_name,
                access_token=access_token,
                refresh_token=None,
                token_expires_at=token_expires_at,
                scopes=list(FACEBOOK_SCOPES),
                metadata_json=_normalize_account_metadata(account_data),
            )
        )

        rows = pages_data.get("data")
        if not isinstance(rows, list):
            rows = []

        for page in rows:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("id") or "").strip()
            page_token = str(page.get("access_token") or "").strip()
            if not page_id or not page_token:
                continue

            page_name = str(page.get("name") or "").strip() or None
            metadata = _normalize_page_metadata(page)
            metadata["source_account_external_id"] = account_id
            accounts.append(
                OAuthAccountPayload(
                    external_account_id=page_id,
                    display_name=page_name,
                    username_or_channel_name=page_name,
                    access_token=page_token,
                    refresh_token=None,
                    token_expires_at=token_expires_at,
                    scopes=list(FACEBOOK_SCOPES),
                    metadata_json=metadata,
                )
            )
            pages_count += 1

        return OAuthExchangeResult(
            accounts=accounts,
            provider_metadata_json={
                "destination_count": len(accounts),
                "facebook_account_count": 1,
                "facebook_page_count": pages_count,
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
                error_message="Facebook publishing requires a reachable media URL.",
            )

        page_id = (payload.destination_external_id or "").strip()
        if not page_id:
            return PublishResult(
                status="failed",
                error_message="Facebook destination Page ID is missing for this publish job.",
            )

        title = (payload.title or payload.caption or "").strip()
        description_parts = [item.strip() for item in [payload.description, payload.caption] if item and item.strip()]
        if payload.hashtags:
            description_parts.append(" ".join(payload.hashtags))
        description = "\n\n".join(description_parts).strip() or title or "Published via PostBandit"

        try:
            with httpx.Client(timeout=120) as client:
                response = graph_post(
                    client,
                    url=f"{_graph_base()}/{page_id}/videos",
                    data={
                        "access_token": access_token,
                        "file_url": media_url,
                        "title": title[:255] if title else None,
                        "description": description[:5000],
                    },
                )
        except GraphRequestError as exc:
            reason = str(exc).lower()
            if any(key in reason for key in ("permission", "authorized", "access token", "review")):
                return PublishResult(
                    status="waiting_user_action",
                    error_message=f"Facebook publish requires additional page permissions: {exc}",
                    provider_metadata_json={
                        "stage": "publish_video",
                        "reason": "permissions_or_review",
                        "action": "reconnect_facebook",
                    },
                )
            return PublishResult(
                status="failed",
                error_message=f"Facebook publish failed: {exc}",
                provider_metadata_json={"stage": "publish_video"},
            )

        external_id = str(response.get("post_id") or response.get("id") or "").strip() or None
        return PublishResult(
            status="published",
            external_post_id=external_id,
            external_post_url=_canonical_post_url(external_id, page_id),
            provider_metadata_json={"facebook_response": response},
        )
