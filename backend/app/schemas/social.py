import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.connected_account import SocialPlatform
from app.models.publish_job import PublishMode, PublishStatus


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
    export_id: uuid.UUID
    clip_id: uuid.UUID
    platform: SocialPlatform
    connected_account_id: uuid.UUID
    status: PublishStatus
    publish_mode: PublishMode
    caption: str | None
    title: str | None
    description: str | None
    hashtags: list[str] | None
    privacy: str | None
    scheduled_for: datetime | None
    external_post_id: str | None
    external_post_url: str | None
    error_message: str | None
    provider_metadata_json: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FullVideoExportResponse(BaseModel):
    clip_id: uuid.UUID
    export_id: uuid.UUID
    export_status: str
    reused_existing_export: bool = False
