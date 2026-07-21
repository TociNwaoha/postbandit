import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.connected_account import SocialPlatform
from app.models.publish_job import PublishMode, PublishStatus


_PLATFORM_DISPLAY_NAMES = {
    SocialPlatform.instagram: "Instagram",
    SocialPlatform.threads: "Threads",
    SocialPlatform.facebook: "Facebook",
    SocialPlatform.youtube: "YouTube",
    SocialPlatform.x: "X",
    SocialPlatform.tiktok: "TikTok",
    SocialPlatform.linkedin: "LinkedIn",
}


def _safe_publish_error_message(
    platform: SocialPlatform,
    error_message: str | None,
    provider_metadata_json: dict | None,
) -> str | None:
    if not error_message:
        return None

    metadata = provider_metadata_json or {}
    action = str(metadata.get("action") or "").lower()
    reason = str(metadata.get("reason") or "").lower()
    normalized = error_message.lower()
    display_name = _PLATFORM_DISPLAY_NAMES.get(platform, platform.value.title())

    if action.startswith("reconnect_") or reason == "reconnect_required" or "reconnect" in normalized:
        return f"Reconnect {display_name} in Connections, then retry this post."

    provider_error_markers = (
        "client error",
        "bad request",
        "unauthorized",
        "invalid token",
        "access token",
        "oauth",
        "googleapis.com",
        "graph.facebook.com",
        "graph.instagram.com",
        "api.twitter.com",
        "api.x.com",
        "open.tiktokapis.com",
        "api.linkedin.com",
        "developer.mozilla.org",
    )
    if any(marker in normalized for marker in provider_error_markers):
        return f"Reconnect {display_name} in Connections, then retry this post."

    return error_message


class ProviderCapabilitiesResponse(BaseModel):
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


class SocialProviderResponse(BaseModel):
    platform: SocialPlatform
    display_name: str
    setup_status: str
    setup_message: str | None = None
    setup_details: dict | None = None
    connected_account_count: int
    capabilities: ProviderCapabilitiesResponse


class ConnectedAccountResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    platform: SocialPlatform
    external_account_id: str
    display_name: str | None
    username_or_channel_name: str | None
    destination_type: str
    token_expires_at: datetime | None
    token_expired: bool = False
    last_token_refresh: datetime | None = None
    scopes: list[str] | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConnectStartRequest(BaseModel):
    return_to: str | None = "/connections"


class ConnectStartResponse(BaseModel):
    authorization_url: str


class PublishContentInput(BaseModel):
    caption: str | None = None
    title: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    privacy: str | None = None
    scheduled_for: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=100)


class PublishTargetInput(BaseModel):
    platform: SocialPlatform
    connected_account_id: uuid.UUID
    override: PublishContentInput | None = None


class PublishCreateRequest(BaseModel):
    export_id: uuid.UUID
    universal: PublishContentInput = Field(default_factory=PublishContentInput)
    targets: list[PublishTargetInput]


class PublishJobResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    export_id: uuid.UUID | None
    clip_id: uuid.UUID | None
    platform: SocialPlatform
    connected_account_id: uuid.UUID | None
    workflow_source_post_id: uuid.UUID | None = None
    workflow_run_id: uuid.UUID | None = None
    status: PublishStatus
    publish_mode: PublishMode
    caption: str | None
    title: str | None
    description: str | None
    hashtags: list[str] | None
    privacy: str | None
    scheduled_for: datetime | None
    timezone: str | None
    destination_display_name: str | None
    content_title_snapshot: str | None
    external_post_id: str | None
    external_post_url: str | None
    error_message: str | None
    provider_metadata_json: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def hide_raw_provider_errors(self):
        self.error_message = _safe_publish_error_message(
            self.platform,
            self.error_message,
            self.provider_metadata_json,
        )
        return self


class PublishJobPatchRequest(BaseModel):
    scheduled_for: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    caption: str | None = None
    title: str | None = None
    description: str | None = None
    hashtags: list[str] | None = None
    privacy: str | None = None
    action: Literal["cancel", "post_now"] | None = None


class PublishCalendarItemResponse(PublishJobResponse):
    thumbnail_url: str | None = None


class PublishCalendarResponse(BaseModel):
    items: list[PublishCalendarItemResponse]
    page: int
    page_size: int
    total: int


class FullVideoExportResponse(BaseModel):
    clip_id: uuid.UUID
    export_id: uuid.UUID
    export_status: str
    reused_existing_export: bool = False
