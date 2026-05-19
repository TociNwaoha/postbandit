from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_connect: bool
    supports_publish_now: bool
    supports_schedule: bool
    supports_video_upload: bool
    supports_caption: bool
    supports_title: bool
    supports_description: bool
    supports_hashtags: bool
    supports_privacy: bool
    supports_multiple_accounts: bool
    may_require_user_completion: bool


@dataclass(frozen=True)
class OAuthAccountPayload:
    external_account_id: str
    display_name: str | None
    username_or_channel_name: str | None
    access_token: str
    refresh_token: str | None
    token_expires_at: datetime | None
    scopes: list[str]
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OAuthExchangeResult:
    accounts: list[OAuthAccountPayload]
    provider_metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublishPayload:
    title: str | None
    description: str | None
    caption: str | None
    hashtags: list[str] | None
    privacy: str | None
    scheduled_for: datetime | None
    media_url: str | None = None
    destination_external_id: str | None = None
    destination_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class PublishResult:
    status: str
    external_post_id: str | None = None
    external_post_url: str | None = None
    error_message: str | None = None
    provider_metadata_json: dict[str, Any] = field(default_factory=dict)
    updated_access_token: str | None = None
    updated_refresh_token: str | None = None
    updated_token_expires_at: datetime | None = None
