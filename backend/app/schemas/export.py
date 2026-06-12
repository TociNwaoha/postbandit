import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator
from app.models.export import (
    AspectRatio,
    CaptionColorVariant,
    CaptionCadence,
    CaptionStyle,
    CaptionFormat,
    ExportStatus,
)

HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class ExportOverlayImageConfig(BaseModel):
    x: float = Field(default=0.82, ge=0, le=1)
    y: float = Field(default=0.15, ge=0, le=1)
    width: float = Field(default=0.22, ge=0.03, le=1)
    opacity: float = Field(default=1, ge=0, le=1)


class ExportOverlayTextHighlight(BaseModel):
    word_index: int = Field(ge=0, le=199)
    color: str = Field(pattern=HEX_COLOR_PATTERN)


class ExportOverlayTextConfig(BaseModel):
    text: str = Field(min_length=1, max_length=280)
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.2, ge=0, le=1)
    font_size: int = Field(default=52, ge=16, le=160)
    text_color: str = Field(default="#FFFFFF", pattern=HEX_COLOR_PATTERN)
    highlights: list[ExportOverlayTextHighlight] = Field(default_factory=list, max_length=100)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def remove_invalid_or_duplicate_highlights(self):
        word_count = len(self.text.split())
        deduped: dict[int, ExportOverlayTextHighlight] = {}
        for highlight in self.highlights:
            if highlight.word_index < word_count:
                deduped[highlight.word_index] = highlight
        self.highlights = [deduped[index] for index in sorted(deduped)]
        return self


class ExportCreate(BaseModel):
    clip_id: uuid.UUID
    aspect_ratio: AspectRatio
    caption_style: CaptionStyle | None = None
    caption_color_variant: CaptionColorVariant | None = None
    caption_format: CaptionFormat = CaptionFormat.burned_in
    caption_cadence: CaptionCadence = CaptionCadence.split_line
    caption_vertical_position: float | None = None
    caption_scale: float | None = None
    frame_anchor_x: float | None = None
    frame_anchor_y: float | None = None
    frame_zoom: float | None = None
    overlay_image_asset_id: uuid.UUID | None = None
    overlay_image_config: ExportOverlayImageConfig | None = None
    overlay_text_config: ExportOverlayTextConfig | None = None

    @model_validator(mode="after")
    def validate_overlay_image_pair(self):
        if bool(self.overlay_image_asset_id) != bool(self.overlay_image_config):
            raise ValueError("overlay image asset and configuration must be provided together")
        return self


class ExportResponse(BaseModel):
    id: uuid.UUID
    clip_id: uuid.UUID
    retry_of_export_id: uuid.UUID | None
    user_id: uuid.UUID
    aspect_ratio: AspectRatio
    caption_style: CaptionStyle | None
    caption_color_variant: CaptionColorVariant
    caption_format: CaptionFormat
    caption_cadence: CaptionCadence
    caption_vertical_position: float | None = None
    caption_scale: float | None = None
    frame_anchor_x: float | None = None
    frame_anchor_y: float | None = None
    frame_zoom: float | None = None
    overlay_image_asset_id: uuid.UUID | None = None
    overlay_image_config: ExportOverlayImageConfig | None = None
    overlay_text_config: ExportOverlayTextConfig | None = None
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
