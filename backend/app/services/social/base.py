from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from app.models.connected_account import SocialPlatform
from app.services.social.types import (
    OAuthAccountPayload,
    OAuthExchangeResult,
    ProviderCapabilities,
    PublishPayload,
    PublishResult,
)


class ProviderNotConfiguredError(Exception):
    pass


class ProviderOperationError(Exception):
    pass


def is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    return normalized in {"", "placeholder", "changeme"} or "placeholder" in normalized


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SocialProviderAdapter(ABC):
    platform: SocialPlatform
    display_name: str

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    @abstractmethod
    def setup_status(self) -> tuple[str, str | None]:
        raise NotImplementedError

    def setup_details(self) -> dict:
        status, message = self.setup_status()
        return {
            "configured": status == "ready",
            "missing_fields": [],
            "message": message,
        }

    @abstractmethod
    def build_connect_url(self, *, state: str, redirect_uri: str, oauth_context: dict | None = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        oauth_context: dict | None = None,
    ) -> OAuthAccountPayload:
        raise NotImplementedError

    def exchange_code_result(
        self,
        *,
        code: str,
        redirect_uri: str,
        oauth_context: dict | None = None,
    ) -> OAuthExchangeResult:
        return OAuthExchangeResult(
            accounts=[self.exchange_code(code=code, redirect_uri=redirect_uri, oauth_context=oauth_context)]
        )

    @abstractmethod
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
        raise NotImplementedError


class ScaffoldProviderAdapter(SocialProviderAdapter):
    def __init__(
        self,
        *,
        platform: SocialPlatform,
        display_name: str,
        may_require_user_completion: bool = False,
        setup_message: str | None = None,
    ):
        self.platform = platform
        self.display_name = display_name
        self._may_require_user_completion = may_require_user_completion
        self._setup_message = setup_message or "Provider adapter scaffold only in this MVP pass"

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
            may_require_user_completion=self._may_require_user_completion,
        )

    def setup_status(self) -> tuple[str, str | None]:
        return "provider_not_configured", self._setup_message

    def build_connect_url(self, *, state: str, redirect_uri: str, oauth_context: dict | None = None) -> str:
        raise ProviderNotConfiguredError(self._setup_message)

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        oauth_context: dict | None = None,
    ) -> OAuthAccountPayload:
        raise ProviderNotConfiguredError(self._setup_message)

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
        return PublishResult(status="provider_not_configured", error_message=self._setup_message)
