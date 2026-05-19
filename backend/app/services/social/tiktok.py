from __future__ import annotations

import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.models.connected_account import SocialPlatform
from app.services.social.base import (
    ProviderOperationError,
    SocialProviderAdapter,
    is_placeholder,
    utcnow,
)
from app.services.social.meta.auth import build_callback_url
from app.services.social.types import OAuthAccountPayload, ProviderCapabilities, PublishPayload, PublishResult

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_OAUTH_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
TIKTOK_CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
TIKTOK_DIRECT_POST_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_UPLOAD_DRAFT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
TIKTOK_STATUS_FETCH_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

TIKTOK_SCOPES = [
    "user.info.basic",
    "user.info.profile",
    "video.publish",
    "video.upload",
]

TIKTOK_DEFAULT_PRIVACY_OPTIONS = [
    "PUBLIC_TO_EVERYONE",
    "MUTUAL_FOLLOW_FRIENDS",
    "FOLLOWER_OF_CREATOR",
    "SELF_ONLY",
]

TIKTOK_REFRESH_WINDOW = timedelta(minutes=10)
TIKTOK_CAPTION_LIMIT = 2200


class TikTokAPIResponseError(ProviderOperationError):
    def __init__(
        self,
        *,
        context: str,
        code: str | None,
        message: str | None,
        log_id: str | None,
        status_code: int,
    ):
        self.context = context
        self.code = (code or "").strip() or None
        self.message = (message or "").strip() or None
        self.log_id = (log_id or "").strip() or None
        self.status_code = status_code

        pieces = [f"TikTok {context} failed"]
        if self.code:
            pieces.append(f"({self.code})")
        if self.message:
            pieces.append(f": {self.message}")
        if self.log_id:
            pieces.append(f" [log_id={self.log_id}]")
        super().__init__("".join(pieces))


def _callback_url() -> str | None:
    callback_url, _callback_error, _missing_fields = build_callback_url("tiktok")
    return callback_url


def _parse_json(response: httpx.Response, *, context: str) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderOperationError(f"TikTok {context} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderOperationError(f"TikTok {context} returned an invalid payload")
    return payload


def _extract_error(payload: dict) -> tuple[str | None, str | None, str | None]:
    error_obj = payload.get("error")
    if isinstance(error_obj, dict):
        code = error_obj.get("code")
        message = error_obj.get("message")
        log_id = error_obj.get("log_id") or error_obj.get("logid")
        return (
            str(code).strip() if code is not None else None,
            str(message).strip() if message is not None else None,
            str(log_id).strip() if log_id is not None else None,
        )

    if isinstance(error_obj, str) and error_obj.strip():
        message = payload.get("error_description") or payload.get("message")
        log_id = payload.get("log_id") or payload.get("logid")
        return (
            error_obj.strip(),
            str(message).strip() if isinstance(message, str) else None,
            str(log_id).strip() if isinstance(log_id, str) else None,
        )

    return None, None, None


def _ensure_success(
    response: httpx.Response,
    *,
    context: str,
    payload: dict,
) -> dict:
    code, message, log_id = _extract_error(payload)
    if response.status_code >= 400:
        raise TikTokAPIResponseError(
            context=context,
            code=code,
            message=message,
            log_id=log_id,
            status_code=response.status_code,
        )

    if code and code.lower() != "ok":
        raise TikTokAPIResponseError(
            context=context,
            code=code,
            message=message,
            log_id=log_id,
            status_code=response.status_code,
        )

    return payload


def _request_json(
    client: httpx.Client,
    *,
    method: str,
    url: str,
    context: str,
    headers: dict[str, str] | None = None,
    params: dict | None = None,
    data: dict | None = None,
    json_body: dict | None = None,
) -> dict:
    try:
        response = client.request(
            method,
            url,
            headers=headers,
            params=params,
            data=data,
            json=json_body,
        )
    except httpx.RequestError as exc:
        raise ProviderOperationError(f"TikTok {context} request failed. Please retry.") from exc

    payload = _parse_json(response, context=context)
    return _ensure_success(response, context=context, payload=payload)


def _scopes_from_raw(raw_scope: str | None) -> list[str]:
    if not raw_scope:
        return []
    scopes: list[str] = []
    seen: set[str] = set()
    for chunk in raw_scope.replace(" ", ",").split(","):
        scope = chunk.strip()
        if not scope:
            continue
        key = scope.lower()
        if key in seen:
            continue
        seen.add(key)
        scopes.append(scope)
    return scopes


def _token_expiry(expires_in: int | float | None) -> datetime | None:
    if isinstance(expires_in, (int, float)):
        return utcnow() + timedelta(seconds=int(expires_in))
    return None


def _clean_privacy_options(options_value) -> list[str]:
    options: list[str] = []
    seen: set[str] = set()
    if isinstance(options_value, list):
        for value in options_value:
            if not isinstance(value, str):
                continue
            option = value.strip().upper()
            if not option or option in seen:
                continue
            seen.add(option)
            options.append(option)
    return options


def _compose_caption(payload: PublishPayload) -> str:
    base = (payload.caption or "").strip()
    if not base:
        parts: list[str] = []
        if payload.title and payload.title.strip():
            parts.append(payload.title.strip())
        if payload.description and payload.description.strip():
            parts.append(payload.description.strip())
        if payload.hashtags:
            parts.append(" ".join(payload.hashtags))
        base = "\n\n".join(parts).strip()

    if not base:
        raise ProviderOperationError("TikTok post caption is empty. Provide caption/title/description/hashtags.")
    return base[:TIKTOK_CAPTION_LIMIT]


def _build_post_url(*, username: str | None, post_id: str | None) -> str | None:
    normalized_post_id = (post_id or "").strip()
    if not normalized_post_id:
        return None
    normalized_username = (username or "").strip().lstrip("@")
    if normalized_username:
        return f"https://www.tiktok.com/@{normalized_username}/video/{normalized_post_id}"
    return f"https://www.tiktok.com/video/{normalized_post_id}"


def _contains_scope(scopes: list[str], scope_name: str) -> bool:
    target = scope_name.strip().lower()
    return any(item.strip().lower() == target for item in scopes)


def _extract_public_post_id(status_payload: dict) -> str | None:
    data = status_payload.get("data") if isinstance(status_payload, dict) else None
    if not isinstance(data, dict):
        return None

    for key in ("publicly_available_post_id", "publicaly_available_post_id", "post_id"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()

    return None


def _normalize_status(value: str | None) -> str:
    return (value or "").strip().upper()


def _is_direct_fallback_candidate(error: TikTokAPIResponseError) -> bool:
    code = (error.code or "").lower()
    message = (error.message or "").lower()

    if code in {
        "scope_not_authorized",
        "unaudited_client_can_only_post_to_private_accounts",
        "privacy_level_option_mismatch",
    }:
        return True

    # Preserve safety around common direct-post gating language while avoiding broad masking.
    if "direct" in message and "not" in message and "allow" in message:
        return True

    return False


def _is_setup_blocking_code(code: str | None) -> bool:
    normalized = (code or "").strip().lower()
    return normalized in {
        "scope_not_authorized",
        "access_token_invalid",
        "url_ownership_unverified",
        "unaudited_client_can_only_post_to_private_accounts",
        "reached_active_user_cap",
        "spam_risk_too_many_posts",
        "spam_risk_user_banned_from_posting",
    }


def _creator_info_from_payload(payload: dict) -> dict:
    raw_data = payload.get("data")
    if isinstance(raw_data, dict):
        return raw_data
    return {}


def _creator_blocked_for_new_posts(creator_info: dict) -> bool:
    # No direct "blocked" flag exists; if privacy options are empty, we treat it as not publish-ready.
    options = _clean_privacy_options(creator_info.get("privacy_level_options"))
    return len(options) == 0


class TikTokAdapter(SocialProviderAdapter):
    platform = SocialPlatform.tiktok
    display_name = "TikTok"

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
            may_require_user_completion=True,
        )

    def setup_details(self) -> dict:
        callback_url, callback_error, callback_missing = build_callback_url(self.platform.value)

        missing_fields: list[str] = []
        if is_placeholder(settings.tiktok_client_key):
            missing_fields.append("TIKTOK_CLIENT_KEY")
        if is_placeholder(settings.tiktok_client_secret):
            missing_fields.append("TIKTOK_CLIENT_SECRET")
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
            "required_scopes": list(TIKTOK_SCOPES),
            "credential_source": "TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET",
            "connect_ready": configured,
            "publish_direct_ready": configured,
            "publish_upload_ready": configured,
            "mode_support": {
                "direct": True,
                "inbox_upload": True,
            },
            "login_model": "tiktok_login_kit_web",
            "notes": "Direct post is attempted first; inbox upload fallback is used when direct posting is blocked and upload scope is authorized.",
        }

    def setup_status(self) -> tuple[str, str | None]:
        details = self.setup_details()
        if details["configured"]:
            return "ready", None
        return "provider_not_configured", details["message"]

    def build_connect_url(self, *, state: str, redirect_uri: str, oauth_context: dict | None = None) -> str:
        status, message = self.setup_status()
        if status != "ready":
            raise ProviderOperationError(message or "TikTok provider not configured")

        params = {
            "client_key": settings.tiktok_client_key,
            "response_type": "code",
            "scope": ",".join(TIKTOK_SCOPES),
            "redirect_uri": redirect_uri,
            "state": state,
            "disable_auto_auth": "1",
        }
        return f"{TIKTOK_AUTH_URL}?{urlencode(params)}"

    def _token_exchange(self, client: httpx.Client, *, code: str, redirect_uri: str) -> dict:
        return _request_json(
            client,
            method="POST",
            url=TIKTOK_OAUTH_TOKEN_URL,
            context="token_exchange",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )

    def _refresh_token(self, client: httpx.Client, *, refresh_token: str) -> dict:
        return _request_json(
            client,
            method="POST",
            url=TIKTOK_OAUTH_TOKEN_URL,
            context="refresh_token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

    def _query_user_info(self, client: httpx.Client, *, access_token: str) -> dict:
        payload = _request_json(
            client,
            method="GET",
            url=TIKTOK_USER_INFO_URL,
            context="user_info",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "fields": "open_id,union_id,display_name,avatar_url,avatar_large_url,bio_description,profile_deep_link,is_verified",
            },
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ProviderOperationError("TikTok user info payload missing data")

        user_obj = data.get("user")
        if isinstance(user_obj, dict):
            return user_obj
        return data

    def _query_creator_info(self, client: httpx.Client, *, access_token: str) -> dict:
        payload = _request_json(
            client,
            method="POST",
            url=TIKTOK_CREATOR_INFO_URL,
            context="creator_info",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json_body={},
        )
        return _creator_info_from_payload(payload)

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        oauth_context: dict | None = None,
    ) -> OAuthAccountPayload:
        status, message = self.setup_status()
        if status != "ready":
            raise ProviderOperationError(message or "TikTok provider not configured")

        try:
            with httpx.Client(timeout=45) as client:
                token_data = self._token_exchange(client, code=code, redirect_uri=redirect_uri)
                access_token = str(token_data.get("access_token") or "").strip()
                if not access_token:
                    raise ProviderOperationError("TikTok OAuth response missing access token")

                user_info = self._query_user_info(client, access_token=access_token)
                creator_info = self._query_creator_info(client, access_token=access_token)
        except TikTokAPIResponseError as exc:
            raise ProviderOperationError(str(exc)) from exc

        open_id = str(user_info.get("open_id") or token_data.get("open_id") or "").strip()
        if not open_id:
            raise ProviderOperationError("TikTok OAuth completed but account identity (open_id) was not returned")

        display_name = str(user_info.get("display_name") or creator_info.get("creator_nickname") or "").strip() or None
        username = str(
            user_info.get("username")
            or creator_info.get("creator_username")
            or user_info.get("profile_deep_link")
            or ""
        ).strip() or None

        raw_scope = str(token_data.get("scope") or "").strip()
        scopes = _scopes_from_raw(raw_scope) or list(TIKTOK_SCOPES)
        token_expires_at = _token_expiry(token_data.get("expires_in"))

        privacy_options = _clean_privacy_options(creator_info.get("privacy_level_options"))
        if not privacy_options:
            privacy_options = list(TIKTOK_DEFAULT_PRIVACY_OPTIONS)

        metadata = {
            "provider_family": "tiktok",
            "destination_type": "tiktok_profile",
            "destination_id": open_id,
            "destination_name": display_name,
            "profile": {
                "open_id": open_id,
                "union_id": user_info.get("union_id"),
                "display_name": display_name,
                "username": username,
                "avatar_url": user_info.get("avatar_url") or creator_info.get("creator_avatar_url"),
                "avatar_large_url": user_info.get("avatar_large_url"),
                "profile_deep_link": user_info.get("profile_deep_link"),
                "bio_description": user_info.get("bio_description"),
                "is_verified": user_info.get("is_verified"),
            },
            "tiktok_creator_info": {
                "creator_username": creator_info.get("creator_username"),
                "creator_nickname": creator_info.get("creator_nickname"),
                "creator_avatar_url": creator_info.get("creator_avatar_url"),
                "privacy_level_options": privacy_options,
                "comment_disabled": creator_info.get("comment_disabled"),
                "duet_disabled": creator_info.get("duet_disabled"),
                "stitch_disabled": creator_info.get("stitch_disabled"),
                "max_video_post_duration_sec": creator_info.get("max_video_post_duration_sec"),
            },
            "token_info": {
                "refresh_expires_in": token_data.get("refresh_expires_in"),
                "token_type": token_data.get("token_type"),
                "scope": raw_scope,
            },
        }

        refresh_token = str(token_data.get("refresh_token") or "").strip() or None

        return OAuthAccountPayload(
            external_account_id=open_id,
            display_name=display_name,
            username_or_channel_name=username,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            scopes=scopes,
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
        token_expires_at: datetime | None,
    ) -> PublishResult:
        status, message = self.setup_status()
        if status != "ready":
            return PublishResult(status="provider_not_configured", error_message=message)

        if not media_url:
            return PublishResult(
                status="failed",
                error_message="TikTok publish requires a media URL from a ready export.",
                provider_metadata_json={"stage": "preflight", "reason": "missing_media_url"},
            )

        destination_external_id = (payload.destination_external_id or "").strip()
        if not destination_external_id:
            return PublishResult(
                status="failed",
                error_message="TikTok destination profile is missing for this publish job.",
                provider_metadata_json={"stage": "preflight", "reason": "missing_destination"},
            )

        privacy_level = (payload.privacy or "").strip().upper()
        if not privacy_level:
            return PublishResult(
                status="failed",
                error_message="TikTok publish requires an explicit privacy selection.",
                provider_metadata_json={"stage": "preflight", "reason": "missing_privacy"},
            )

        destination_metadata = payload.destination_metadata or {}
        creator_info_cached = destination_metadata.get("tiktok_creator_info")
        if not isinstance(creator_info_cached, dict):
            creator_info_cached = {}

        username = (
            str(creator_info_cached.get("creator_username") or "").strip()
            or str((destination_metadata.get("profile") or {}).get("username") if isinstance(destination_metadata.get("profile"), dict) else "").strip()
            or None
        )

        original_access_token = access_token
        original_refresh_token = refresh_token
        active_access_token = access_token
        active_refresh_token = refresh_token
        active_token_expires_at = token_expires_at
        refreshed = False

        try:
            with httpx.Client(timeout=60) as client:
                poll_interval_seconds = max(1, int(settings.tiktok_publish_poll_interval_seconds))
                poll_timeout = timedelta(
                    seconds=max(30, int(settings.tiktok_publish_poll_timeout_seconds))
                )
                if (
                    active_token_expires_at
                    and active_token_expires_at <= (utcnow() + TIKTOK_REFRESH_WINDOW)
                    and active_refresh_token
                ):
                    refreshed_payload = self._refresh_token(client, refresh_token=active_refresh_token)
                    refreshed_access_token = str(refreshed_payload.get("access_token") or "").strip()
                    if not refreshed_access_token:
                        raise ProviderOperationError("TikTok refresh token response missing access token")
                    active_access_token = refreshed_access_token
                    refreshed_token = str(refreshed_payload.get("refresh_token") or "").strip()
                    if refreshed_token:
                        active_refresh_token = refreshed_token
                    active_token_expires_at = _token_expiry(refreshed_payload.get("expires_in"))
                    refreshed = True

                creator_info = self._query_creator_info(client, access_token=active_access_token)
                privacy_options = _clean_privacy_options(creator_info.get("privacy_level_options"))
                if privacy_options and privacy_level not in privacy_options:
                    allowed = ", ".join(privacy_options)
                    return PublishResult(
                        status="waiting_user_action",
                        error_message=f"TikTok privacy option mismatch. Allowed values: {allowed}",
                        provider_metadata_json={
                            "stage": "creator_info",
                            "reason": "privacy_level_option_mismatch",
                            "action": "choose_allowed_privacy",
                            "privacy_level_options": privacy_options,
                        },
                        updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                        updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                        updated_token_expires_at=active_token_expires_at if refreshed else None,
                    )

                if _creator_blocked_for_new_posts(creator_info):
                    return PublishResult(
                        status="waiting_user_action",
                        error_message="TikTok account is not currently eligible to publish. Try again later in TikTok.",
                        provider_metadata_json={
                            "stage": "creator_info",
                            "reason": "creator_not_publish_ready",
                            "action": "retry_later",
                        },
                        updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                        updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                        updated_token_expires_at=active_token_expires_at if refreshed else None,
                    )

                caption_text = _compose_caption(payload)
                max_duration = creator_info.get("max_video_post_duration_sec")

                init_payload = {
                    "post_info": {
                        "title": caption_text,
                        "privacy_level": privacy_level,
                        "disable_comment": bool(creator_info.get("comment_disabled", False)),
                        "disable_duet": bool(creator_info.get("duet_disabled", False)),
                        "disable_stitch": bool(creator_info.get("stitch_disabled", False)),
                    },
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "video_url": media_url,
                    },
                }

                publish_mode = "direct"
                publish_init_context = "direct_init"
                fallback_trigger: dict | None = None

                try:
                    direct_init_response = _request_json(
                        client,
                        method="POST",
                        url=TIKTOK_DIRECT_POST_INIT_URL,
                        context=publish_init_context,
                        headers={
                            "Authorization": f"Bearer {active_access_token}",
                            "Content-Type": "application/json; charset=UTF-8",
                        },
                        json_body=init_payload,
                    )
                    init_response = direct_init_response
                except TikTokAPIResponseError as exc:
                    token_scopes = []
                    destination_scopes = destination_metadata.get("scopes")
                    if isinstance(destination_scopes, list):
                        token_scopes = [str(item) for item in destination_scopes if isinstance(item, str)]
                    if not token_scopes:
                        token_scopes = _scopes_from_raw(
                            str((destination_metadata.get("token_info") or {}).get("scope") if isinstance(destination_metadata.get("token_info"), dict) else "")
                        )

                    upload_scope_present = _contains_scope(token_scopes, "video.upload") or _contains_scope(
                        _scopes_from_raw(str((destination_metadata.get("oauth_scope") or ""))),
                        "video.upload",
                    )

                    if _is_direct_fallback_candidate(exc) and upload_scope_present:
                        publish_mode = "inbox_upload"
                        publish_init_context = "inbox_init"
                        fallback_trigger = {
                            "direct_error_code": exc.code,
                            "direct_error_message": exc.message,
                            "direct_error_log_id": exc.log_id,
                        }
                        init_response = _request_json(
                            client,
                            method="POST",
                            url=TIKTOK_UPLOAD_DRAFT_INIT_URL,
                            context=publish_init_context,
                            headers={
                                "Authorization": f"Bearer {active_access_token}",
                                "Content-Type": "application/json; charset=UTF-8",
                            },
                            json_body={
                                "source_info": {
                                    "source": "PULL_FROM_URL",
                                    "video_url": media_url,
                                }
                            },
                        )
                    else:
                        if _is_setup_blocking_code(exc.code):
                            return PublishResult(
                                status="waiting_user_action",
                                error_message=str(exc),
                                provider_metadata_json={
                                    "stage": publish_init_context,
                                    "reason": exc.code or "publish_init_failed",
                                    "action": "check_tiktok_app_setup",
                                    "max_video_post_duration_sec": max_duration,
                                    "privacy_level": privacy_level,
                                },
                                updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                                updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                                updated_token_expires_at=active_token_expires_at if refreshed else None,
                            )
                        return PublishResult(
                            status="failed",
                            error_message=str(exc),
                            provider_metadata_json={
                                "stage": publish_init_context,
                                "reason": exc.code or "publish_init_failed",
                                "max_video_post_duration_sec": max_duration,
                                "privacy_level": privacy_level,
                            },
                            updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                            updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                            updated_token_expires_at=active_token_expires_at if refreshed else None,
                        )

                init_data = init_response.get("data") if isinstance(init_response, dict) else None
                if not isinstance(init_data, dict):
                    return PublishResult(
                        status="failed",
                        error_message="TikTok publish init response missing data payload",
                        provider_metadata_json={"stage": publish_init_context, "publish_mode": publish_mode},
                        updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                        updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                        updated_token_expires_at=active_token_expires_at if refreshed else None,
                    )

                publish_id = str(init_data.get("publish_id") or "").strip()
                if not publish_id:
                    return PublishResult(
                        status="failed",
                        error_message="TikTok publish init did not return publish_id",
                        provider_metadata_json={"stage": publish_init_context, "publish_mode": publish_mode},
                        updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                        updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                        updated_token_expires_at=active_token_expires_at if refreshed else None,
                    )

                deadline = utcnow() + poll_timeout
                last_status_payload: dict | None = None

                while utcnow() < deadline:
                    status_payload = _request_json(
                        client,
                        method="POST",
                        url=TIKTOK_STATUS_FETCH_URL,
                        context="status_fetch",
                        headers={
                            "Authorization": f"Bearer {active_access_token}",
                            "Content-Type": "application/json; charset=UTF-8",
                        },
                        json_body={"publish_id": publish_id},
                    )
                    last_status_payload = status_payload
                    status_data = status_payload.get("data") if isinstance(status_payload, dict) else None
                    status_value = _normalize_status(status_data.get("status") if isinstance(status_data, dict) else None)

                    if status_value == "PUBLISH_COMPLETE":
                        post_id = _extract_public_post_id(status_payload)
                        return PublishResult(
                            status="published",
                            external_post_id=post_id or publish_id,
                            external_post_url=_build_post_url(username=username, post_id=post_id),
                            provider_metadata_json={
                                "publish_mode": publish_mode,
                                "publish_id": publish_id,
                                "privacy_level": privacy_level,
                                "creator_info": creator_info,
                                "status_fetch": status_payload,
                                "fallback_trigger": fallback_trigger,
                            },
                            updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                            updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                            updated_token_expires_at=active_token_expires_at if refreshed else None,
                        )

                    if status_value == "SEND_TO_USER_INBOX":
                        return PublishResult(
                            status="waiting_user_action",
                            external_post_id=publish_id,
                            error_message="TikTok draft uploaded. Open TikTok inbox to review and publish.",
                            provider_metadata_json={
                                "publish_mode": publish_mode,
                                "publish_id": publish_id,
                                "privacy_level": privacy_level,
                                "creator_info": creator_info,
                                "status_fetch": status_payload,
                                "fallback_trigger": fallback_trigger,
                                "action": "open_tiktok_inbox_and_publish",
                            },
                            updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                            updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                            updated_token_expires_at=active_token_expires_at if refreshed else None,
                        )

                    if status_value == "FAILED":
                        fail_reason = None
                        if isinstance(status_data, dict):
                            fail_reason = status_data.get("fail_reason")
                        fail_reason_text = str(fail_reason).strip() if fail_reason is not None else "unknown"
                        return PublishResult(
                            status="failed",
                            external_post_id=publish_id,
                            error_message=f"TikTok publish failed: {fail_reason_text}",
                            provider_metadata_json={
                                "publish_mode": publish_mode,
                                "publish_id": publish_id,
                                "privacy_level": privacy_level,
                                "creator_info": creator_info,
                                "status_fetch": status_payload,
                                "fallback_trigger": fallback_trigger,
                            },
                            updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                            updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                            updated_token_expires_at=active_token_expires_at if refreshed else None,
                        )

                    # Processing states: PROCESSING_UPLOAD / PROCESSING_DOWNLOAD / other in-flight statuses.
                    if status_value == "" or status_value.startswith("PROCESSING"):
                        time.sleep(poll_interval_seconds)
                        continue

                    # Unknown non-terminal status, keep polling until timeout.
                    time.sleep(poll_interval_seconds)

                return PublishResult(
                    status="failed",
                    external_post_id=publish_id,
                    error_message="TikTok publish status polling timed out before terminal state.",
                    provider_metadata_json={
                        "stage": "status_poll_timeout",
                        "publish_mode": publish_mode,
                        "publish_id": publish_id,
                        "privacy_level": privacy_level,
                        "last_status": last_status_payload,
                        "fallback_trigger": fallback_trigger,
                    },
                    updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                    updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                    updated_token_expires_at=active_token_expires_at if refreshed else None,
                )
        except TikTokAPIResponseError as exc:
            if _is_setup_blocking_code(exc.code):
                return PublishResult(
                    status="waiting_user_action",
                    error_message=str(exc),
                    provider_metadata_json={
                        "stage": "tiktok_api",
                        "reason": exc.code or "api_error",
                        "action": "check_tiktok_app_setup",
                    },
                    updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                    updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                    updated_token_expires_at=active_token_expires_at if refreshed else None,
                )
            return PublishResult(
                status="failed",
                error_message=str(exc),
                provider_metadata_json={
                    "stage": "tiktok_api",
                    "reason": exc.code or "api_error",
                },
                updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                updated_token_expires_at=active_token_expires_at if refreshed else None,
            )
        except ProviderOperationError as exc:
            return PublishResult(
                status="failed",
                error_message=str(exc),
                provider_metadata_json={"stage": "publish_operation"},
                updated_access_token=active_access_token if refreshed and active_access_token != original_access_token else None,
                updated_refresh_token=active_refresh_token if refreshed and active_refresh_token != original_refresh_token else None,
                updated_token_expires_at=active_token_expires_at if refreshed else None,
            )
