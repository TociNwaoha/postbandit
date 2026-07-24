import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.models.clip import ClipStatus
from app.models.connected_account import SocialPlatform


class ClipUpdateRequest(BaseModel):
    video_id: uuid.UUID
    start_time: float
    end_time: float


class ClipResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    start_time: float
    end_time: float
    duration_sec: float | None
    score: float | None
    hook_score: float | None
    energy_score: float | None
    title: str | None
    hashtags: list[str] | None
    title_options: list[str] | None
    hashtag_options: list[list[str]] | None
    copy_generation_status: str | None
    copy_generation_error: str | None
    thumbnail_key: str | None
    thumbnail_url: str | None = None
    transcript_text: str | None
    content_brief: str | None
    status: ClipStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClipOverlayAssetResponse(BaseModel):
    id: uuid.UUID
    clip_id: uuid.UUID
    user_id: uuid.UUID
    original_filename: str | None
    mime_type: str
    size_bytes: int
    width: int
    height: int
    download_url: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PlatformCopyGenerateRequest(BaseModel):
    platforms: list[SocialPlatform] = Field(min_length=1, max_length=7)
    topic_hint: str | None = Field(default=None, max_length=500)

    @field_validator("platforms")
    @classmethod
    def deduplicate_platforms(cls, value: list[SocialPlatform]) -> list[SocialPlatform]:
        return list(dict.fromkeys(value))


class PlatformCopyFields(BaseModel):
    title: str | None = None
    caption: str | None = None
    description: str | None = None
    hashtags: list[str] = Field(default_factory=list)


class PlatformCopyGenerateResponse(BaseModel):
    provider_used: str
    results: dict[str, PlatformCopyFields]
    errors: dict[str, str]


class ClipCopyOptionsResponse(BaseModel):
    provider_used: str = "deepseek"
    titles: list[str] = Field(min_length=5, max_length=5)
    captions: list[str] = Field(min_length=5, max_length=5)
    descriptions: list[str] = Field(min_length=5, max_length=5)
    hashtag_sets: list[list[str]] = Field(min_length=5, max_length=5)
    platform: str | None = None
