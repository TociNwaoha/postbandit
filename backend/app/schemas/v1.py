import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.connected_account import SocialPlatform
from app.models.export import AspectRatio, CaptionCadence
from app.models.publish_job import PublishStatus


class V1Meta(BaseModel):
    request_id: str
    timestamp: datetime


class V1Envelope(BaseModel):
    data: Any
    meta: V1Meta


class V1VideoImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=5000)
    title: str | None = Field(default=None, max_length=500)


class V1ClipExportRequest(BaseModel):
    aspect_ratio: AspectRatio
    caption_style: Literal["none", "split_line", "word_by_word", "subtitle_block"] = "split_line"


class V1PublishCopy(BaseModel):
    caption: str | None = None
    hashtags: list[str] | None = None
    title: str | None = None
    description: str | None = None


class V1PublishItem(BaseModel):
    export_id: uuid.UUID
    provider: SocialPlatform
    connected_account_id: uuid.UUID
    scheduled_at: datetime | None = None
    timezone: str | None = None
    privacy: str | None = None
    copy: V1PublishCopy = Field(default_factory=V1PublishCopy)


class V1CopyRequest(BaseModel):
    platforms: list[SocialPlatform]
    topic_hint: str | None = None


class V1Pagination(BaseModel):
    page: int
    limit: int
    count: int


def cadence_from_public_style(value: str) -> tuple[str, CaptionCadence]:
    if value == "none":
        return "none", CaptionCadence.split_line
    return "burned_in", CaptionCadence(value)
