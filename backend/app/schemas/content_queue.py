import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


_ALLOWED_STATUSES = {"draft", "rendering", "ready", "approved", "rejected", "posted"}
_ALLOWED_TONES = {"professional", "casual", "edgy", "educational"}


class BrandProfileUpsertRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    handle: str = Field(min_length=1, max_length=100)
    niche: str = Field(min_length=1, max_length=200)
    target_audience: str = Field(min_length=1, max_length=300)
    tone: str = Field(min_length=1, max_length=50)
    use_phrases: list[str] = Field(default_factory=list)
    avoid_phrases: list[str] = Field(default_factory=list)
    ai_cmo_enabled: bool = True
    post_frequency: int = Field(default=1, ge=0, le=5)
    preferred_platforms: list[str] = Field(default_factory=list)

    @field_validator("display_name", "handle", "niche", "target_audience", mode="before")
    @classmethod
    def _clean_text(cls, value: Any) -> str:
        text = " ".join(str(value or "").strip().split())
        if not text:
            raise ValueError("Field is required")
        return text

    @field_validator("tone", mode="before")
    @classmethod
    def _clean_tone(cls, value: Any) -> str:
        text = " ".join(str(value or "").strip().split()).lower()
        if text not in _ALLOWED_TONES:
            raise ValueError("Invalid tone")
        return text


class BrandProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    handle: str
    niche: str
    target_audience: str
    tone: str
    use_phrases: list[str]
    avoid_phrases: list[str]
    ai_cmo_enabled: bool
    post_frequency: int
    preferred_platforms: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContentQueueGenerateRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=5000)
    template_id: str = Field(default="viral-dark", min_length=1, max_length=100)
    platforms: list[str] = Field(default_factory=list)

    @field_validator("topic")
    @classmethod
    def _normalize_topic(cls, value: str) -> str:
        text = " ".join((value or "").strip().split())
        if not text:
            raise ValueError("Topic is required")
        return text


class ContentQueueUpdateRequest(BaseModel):
    config: dict | None = None
    platforms: list[str] | None = None
    scheduled_at: datetime | None = None


class ContentQueueItemResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    content_type: str
    config: dict
    slide_urls: list[str]
    slide_keys_json: list[str]
    zip_key: str | None
    preview_key: str | None
    asset_cleanup_at: datetime | None
    assets_deleted_at: datetime | None
    status: str
    platforms: list[str]
    scheduled_at: datetime | None
    generation_topic: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContentQueueStatusFilter(str):
    pass


def validate_status_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in _ALLOWED_STATUSES:
        raise ValueError("Invalid status filter")
    return normalized
