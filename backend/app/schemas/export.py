import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.export import (
    AspectRatio,
    CaptionColorVariant,
    CaptionStyle,
    CaptionFormat,
    ExportStatus,
)


class ExportCreate(BaseModel):
    clip_id: uuid.UUID
    aspect_ratio: AspectRatio
    caption_style: CaptionStyle | None = None
    caption_color_variant: CaptionColorVariant | None = None
    caption_format: CaptionFormat
    caption_vertical_position: float | None = None
    caption_scale: float | None = None
    frame_anchor_x: float | None = None
    frame_anchor_y: float | None = None
    frame_zoom: float | None = None


class ExportResponse(BaseModel):
    id: uuid.UUID
    clip_id: uuid.UUID
    retry_of_export_id: uuid.UUID | None
    user_id: uuid.UUID
    aspect_ratio: AspectRatio
    caption_style: CaptionStyle | None
    caption_color_variant: CaptionColorVariant
    caption_format: CaptionFormat
    caption_vertical_position: float | None = None
    caption_scale: float | None = None
    frame_anchor_x: float | None = None
    frame_anchor_y: float | None = None
    frame_zoom: float | None = None
    storage_key: str | None
    srt_key: str | None
    download_url: str | None
    srt_download_url: str | None = None
    url_expires_at: datetime | None
    status: ExportStatus
    error_message: str | None
    render_time_sec: int | None
    reused: bool = False
    video_id: uuid.UUID | None = None
    video_title: str | None = None
    clip_title: str | None = None
    clip_transcript_text: str | None = None
    clip_thumbnail_url: str | None = None
    clip_title_options: list[str] | None = None
    clip_hashtag_options: list[list[str]] | None = None
    clip_copy_generation_status: str | None = None
    clip_copy_generation_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PublicExportShareResponse(BaseModel):
    export_id: uuid.UUID
    clip_id: uuid.UUID
    video_id: uuid.UUID
    title: str
    description: str
    thumbnail_url: str | None
    media_url: str
    share_url: str
