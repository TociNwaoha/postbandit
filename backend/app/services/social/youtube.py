from __future__ import annotations

import json
import os
import logging
from datetime import timedelta
from urllib.parse import urlencode, urlparse

import httpx

from app.config import settings
from app.models.connected_account import SocialPlatform
from app.services.social.base import ProviderOperationError, SocialProviderAdapter, is_placeholder, utcnow
from app.services.social.types import OAuthAccountPayload, ProviderCapabilities, PublishPayload, PublishResult

YOUTUBE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/userinfo.profile",
]

logger = logging.getLogger(__name__)


def _extract_google_error(response: httpx.Response) -> str:
    """Return a short, non-sensitive Google OAuth/API error summary."""
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = {}

    if isinstance(payload, dict):
        if isinstance(payload.get("error"), str):
            detail = payload.get("error_description") or payload.get("error")
            return str(detail)[:200]
        err_obj = payload.get("error")
        if isinstance(err_obj, dict):
            detail = err_obj.get("message") or err_obj.get("status") or err_obj.get("code")
            if detail:
                return str(detail)[:200]

    # Fall back to status only; do not include sensitive payloads.
    return f"http_{response.status_code}"


def _http_error_endpoint(exc: httpx.HTTPStatusError) -> str:
    path = exc.request.url.path or ""
    if path.endswith("/token"):
        return "token_exchange"
    if "youtube/v3/channels" in path:
        return "channel_lookup"
    if "oauth2" in path and "userinfo" in path:
        return "userinfo_lookup"
    return "google_api"


class YouTubeAdapter(SocialProviderAdapter):
    platform = SocialPlatform.youtube
    display_name = "YouTube"

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
            supports_privacy=True,
            supports_multiple_accounts=True,
            may_require_user_completion=False,
        )

    def setup_details(self) -> dict:
        missing_fields: list[str] = []

        if is_placeholder(settings.youtube_client_id):
            missing_fields.append("YOUTUBE_CLIENT_ID")
        if is_placeholder(settings.youtube_client_secret):
            missing_fields.append("YOUTUBE_CLIENT_SECRET")
        if is_placeholder(settings.social_token_encryption_key):
            missing_fields.append("SOCIAL_TOKEN_ENCRYPTION_KEY")

        callback_url: str | None = None
        callback_error: str | None = None
        backend_public_url = (settings.backend_public_url or "").strip()
        if is_placeholder(backend_public_url):
            missing_fields.append("BACKEND_PUBLIC_URL")
            callback_error = "BACKEND_PUBLIC_URL is missing"
        else:
            parsed = urlparse(backend_public_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                missing_fields.append("BACKEND_PUBLIC_URL")
                callback_error = "BACKEND_PUBLIC_URL must be an absolute http(s) URL"
            else:
                callback_url = f"{backend_public_url.rstrip('/')}/api/social/{self.platform.value}/callback"

        missing_fields = sorted(set(missing_fields))
        configured = len(missing_fields) == 0
        message = None if configured else f"Missing/invalid required config: {', '.join(missing_fields)}"
        return {
            "configured": configured,
            "missing_fields": missing_fields,
            "message": message,
            "callback_url": callback_url,
            "callback_error": callback_error,
        }

    def setup_status(self) -> tuple[str, str | None]:
        details = self.setup_details()
        if details["configured"]:
            return "ready", None
        return "provider_not_configured", details["message"]

    def build_connect_url(self, *, state: str, redirect_uri: str, oauth_context: dict | None = None) -> str:
        status, message = self.setup_status()
        if status != "ready":
            raise ProviderOperationError(message or "YouTube provider not configured")

        params = {
            "client_id": settings.youtube_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "scope": " ".join(YOUTUBE_SCOPES),
            "state": state,
            "include_granted_scopes": "true",
        }
        return f"{YOUTUBE_AUTH_URL}?{urlencode(params)}"

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        oauth_context: dict | None = None,
    ) -> OAuthAccountPayload:
        status, message = self.setup_status()
        if status != "ready":
            raise ProviderOperationError(message or "YouTube provider not configured")

        token_payload = {
            "code": code,
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        try:
            with httpx.Client(timeout=30) as client:
                token_resp = client.post(YOUTUBE_TOKEN_URL, data=token_payload)
                token_resp.raise_for_status()
                token_data = token_resp.json()

                access_token = token_data.get("access_token")
                if not access_token:
                    raise ProviderOperationError("YouTube OAuth response missing access token")

                headers = {"Authorization": f"Bearer {access_token}"}
                metadata_json: dict = {}
                external_account_id = "youtube-account"
                display_name = None
                username_or_channel_name = None

                try:
                    channels_resp = client.get(
                        YOUTUBE_CHANNELS_URL,
                        headers=headers,
                        params={"part": "id,snippet", "mine": "true"},
                    )
                    channels_resp.raise_for_status()
                    channels_data = channels_resp.json()
                    channel_item = (channels_data.get("items") or [None])[0] or {}
                    snippet = channel_item.get("snippet") or {}
                    external_account_id = str(
                        channel_item.get("id") or snippet.get("customUrl") or "youtube-account"
                    )
                    display_name = snippet.get("title")
                    username_or_channel_name = snippet.get("customUrl")
                    metadata_json = {"channel": channel_item}
                except httpx.HTTPStatusError as channel_exc:
                    channel_reason = _extract_google_error(channel_exc.response)
                    if (
                        channel_exc.response.status_code == 403
                        and "insufficient authentication scopes" in channel_reason.lower()
                    ):
                        logging.warning(
                            "[social] youtube oauth channel lookup fallback reason=%s",
                            channel_reason,
                        )
                        userinfo_resp = client.get(YOUTUBE_USERINFO_URL, headers=headers)
                        userinfo_resp.raise_for_status()
                        userinfo_data = userinfo_resp.json()
                        external_account_id = str(
                            userinfo_data.get("sub")
                            or userinfo_data.get("id")
                            or "youtube-account"
                        )
                        display_name = userinfo_data.get("name")
                        username_or_channel_name = userinfo_data.get("given_name")
                        metadata_json = {
                            "userinfo": {
                                "sub": userinfo_data.get("sub"),
                                "name": userinfo_data.get("name"),
                                "given_name": userinfo_data.get("given_name"),
                            },
                            "channel_lookup": {
                                "status": "skipped_insufficient_scopes",
                                "reason": channel_reason,
                            },
                        }
                    else:
                        raise
        except httpx.HTTPStatusError as exc:
            api_error = _extract_google_error(exc.response)
            endpoint = _http_error_endpoint(exc)
            logging.warning(
                "[social] youtube oauth http error endpoint=%s status=%s reason=%s",
                endpoint,
                exc.response.status_code,
                api_error,
            )
            raise ProviderOperationError(f"YouTube OAuth failed: {api_error}") from exc
        except httpx.RequestError as exc:
            logging.warning("[social] youtube oauth network error: %s", exc.__class__.__name__)
            raise ProviderOperationError("YouTube OAuth request failed. Please retry.") from exc

        expires_in = token_data.get("expires_in")
        token_expires_at = None
        if isinstance(expires_in, (int, float)):
            token_expires_at = utcnow() + timedelta(seconds=int(expires_in))

        scope_raw = str(token_data.get("scope") or "")
        scopes = [part for part in scope_raw.split() if part]

        return OAuthAccountPayload(
            external_account_id=external_account_id,
            display_name=display_name,
            username_or_channel_name=username_or_channel_name,
            access_token=access_token,
            refresh_token=token_data.get("refresh_token"),
            token_expires_at=token_expires_at,
            scopes=scopes,
            metadata_json=metadata_json,
        )

    def _refresh_access_token(self, refresh_token: str) -> tuple[str, str | None]:
        payload = {
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        with httpx.Client(timeout=30) as client:
            token_resp = client.post(YOUTUBE_TOKEN_URL, data=payload)
            token_resp.raise_for_status()
            data = token_resp.json()

        access_token = data.get("access_token")
        if not access_token:
            raise ProviderOperationError("YouTube token refresh returned no access token")
        expires_in = data.get("expires_in")
        expires_at = None
        if isinstance(expires_in, (int, float)):
            expires_at = utcnow() + timedelta(seconds=int(expires_in))
        return access_token, expires_at

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

        token_to_use = access_token
        updated_access_token = None
        updated_token_expires_at = None

        if token_expires_at and token_expires_at <= (utcnow() + timedelta(seconds=60)) and refresh_token:
            refreshed_token, refreshed_expiry = self._refresh_access_token(refresh_token)
            token_to_use = refreshed_token
            updated_access_token = refreshed_token
            updated_token_expires_at = refreshed_expiry

        title = (payload.title or payload.caption or "PostBandit Export").strip()[:100]
        description_parts = [part.strip() for part in [payload.description, payload.caption] if part and part.strip()]
        if payload.hashtags:
            description_parts.append(" ".join(payload.hashtags))
        description = "\n\n".join(description_parts)[:4900]

        privacy_status = (payload.privacy or "private").strip().lower()
        if privacy_status not in {"public", "private", "unlisted"}:
            return PublishResult(
                status="failed",
                error_message="Invalid YouTube privacy value. Allowed: private, unlisted, public.",
            )

        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": payload.hashtags or [],
            },
            "status": {
                "privacyStatus": privacy_status,
            },
        }

        file_size = os.path.getsize(media_path)
        headers = {
            "Authorization": f"Bearer {token_to_use}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(file_size),
            "X-Upload-Content-Type": "video/mp4",
        }

        with httpx.Client(timeout=120) as client:
            init_resp = client.post(
                YOUTUBE_UPLOAD_URL,
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers=headers,
                json=metadata,
            )
            init_resp.raise_for_status()
            upload_url = init_resp.headers.get("Location")
            if not upload_url:
                raise ProviderOperationError("YouTube upload session did not return upload location")

            with open(media_path, "rb") as media_file:
                upload_resp = client.put(
                    upload_url,
                    headers={"Authorization": f"Bearer {token_to_use}", "Content-Type": "video/mp4"},
                    content=media_file,
                )
                upload_resp.raise_for_status()
                upload_data = upload_resp.json()

        video_id = upload_data.get("id")
        if not video_id:
            raise ProviderOperationError("YouTube upload completed but no video id was returned")

        return PublishResult(
            status="published",
            external_post_id=video_id,
            external_post_url=f"https://www.youtube.com/watch?v={video_id}",
            provider_metadata_json={"youtube_response": upload_data},
            updated_access_token=updated_access_token,
            updated_token_expires_at=updated_token_expires_at,
        )
