import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.editor_asset import EditorAssetType
from app.models.editor_project import EditorProjectStatus
from app.models.editor_render import EditorRenderPreset, EditorRenderStatus
from app.models.export import AspectRatio


class EditorCaptionStyle(BaseModel):
    font_family: str = "Inter"
    font_size: float = 54
    text_color: str = "#FFFFFF"
    bg_color: str = "#000000CC"
    position: Literal["top", "middle", "bottom"] = "bottom"
    uppercase: bool = False


class EditorCaptionGroupTransform(BaseModel):
    anchor_x: float | None = None
    anchor_y: float | None = None
    scale: float | None = None


class EditorCaptionOverride(BaseModel):
    segment_id: str | None = None
    start_sec: float
    end_sec: float
    text: str


class EditorCaptionConfig(BaseModel):
    enabled: bool = True
    source: Literal["transcript_segments"] = "transcript_segments"
    active_word_highlight: bool = False
    style: EditorCaptionStyle = Field(default_factory=EditorCaptionStyle)
    group: EditorCaptionGroupTransform = Field(default_factory=EditorCaptionGroupTransform)
    overrides: list[EditorCaptionOverride] = Field(default_factory=list)


class EditorOverlayStyle(BaseModel):
    font_family: str | None = None
    font_size: float | None = None
    font_weight: float | None = None
    alignment: Literal["left", "center", "right"] | None = None
    color: str | None = None
    bg_color: str | None = None


class EditorOverlay(BaseModel):
    id: str
    type: Literal["text", "image"]
    start_sec: float
    end_sec: float
    x: float = 0.5
    y: float = 0.5
    width: float = 0.4
    height: float = 0.2
    rotation_deg: float = 0
    opacity: float = 1
    z_index: int = 0
    content: str | None = None
    asset_id: str | None = None
    style: EditorOverlayStyle | None = None


class EditorClipRef(BaseModel):
    video_id: str
    clip_id: str
    source_storage_key: str | None = None
    source_duration_sec: float | None = None


class EditorCanvas(BaseModel):
    aspect_ratio: Literal["9:16", "1:1", "16:9"] = "9:16"
    width: int = 720
    height: int = 1280
    safe_area_preset: Literal["tiktok", "reels", "shorts", "linkedin", "square", "landscape"] = "tiktok"


class EditorTrim(BaseModel):
    start_sec: float
    end_sec: float


class EditorReframe(BaseModel):
    anchor_x: float = 0.5
    anchor_y: float = 0.5
    zoom: float = 1.0
    fit_mode: Literal["fill", "fit"] = "fill"


class EditorExportSettings(BaseModel):
    preset: EditorRenderPreset = EditorRenderPreset.tiktok
    video_codec: Literal["h264"] = "h264"
    audio_codec: Literal["aac"] = "aac"


class EditorProjectMeta(BaseModel):
    aspect_auto_inferred_v1: bool = False
    editor_preview_status: Literal["pending", "ready", "failed"] | None = None
    editor_preview_key: str | None = None
    editor_preview_source_key: str | None = None
    editor_preview_profile_version: int | None = None
    editor_preview_offset_sec: float | None = None
    editor_preview_duration_sec: float | None = None
    editor_preview_error: str | None = None
    editor_preview_enqueued_at: str | None = None
    editor_preview_updated_at: str | None = None


class EditorProjectSchemaV1(BaseModel):
    version: Literal[1] = 1
    clip_ref: EditorClipRef
    meta: EditorProjectMeta = Field(default_factory=EditorProjectMeta)
    canvas: EditorCanvas
    trim: EditorTrim
    reframe: EditorReframe
    captions: EditorCaptionConfig = Field(default_factory=EditorCaptionConfig)
    overlays: list[EditorOverlay] = Field(default_factory=list)
    export: EditorExportSettings = Field(default_factory=EditorExportSettings)


class EditorProjectCreateFromClipRequest(BaseModel):
    clip_id: uuid.UUID
    aspect_ratio: AspectRatio | None = None


class EditorProjectPatchRequest(BaseModel):
    name: str | None = None
    aspect_ratio: AspectRatio | None = None
    trim_start_sec: float | None = None
    trim_end_sec: float | None = None
    is_pinned: bool | None = None
    project_json: EditorProjectSchemaV1 | None = None
    revision: int | None = None


class EditorAssetResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    asset_type: EditorAssetType
    storage_key: str
    original_filename: str | None
    mime_type: str | None
    size_bytes: int
    width: int | None
    height: int | None
    download_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EditorRenderRequest(BaseModel):
    preset: EditorRenderPreset = EditorRenderPreset.tiktok


class EditorRenderResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    export_id: uuid.UUID | None
    status: EditorRenderStatus
    preset: EditorRenderPreset
    output_storage_key: str | None
    output_size_bytes: int | None
    error_message: str | None
    download_url: str | None = None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserStorageUsageResponse(BaseModel):
    quota_bytes: int
    hard_stop_bytes: int
    used_bytes: int
    raw_video_bytes: int
    editor_asset_bytes: int
    render_output_bytes: int
    warning: bool
    blocked: bool


class EditorProjectResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    video_id: uuid.UUID
    clip_id: uuid.UUID
    name: str | None
    status: EditorProjectStatus
    aspect_ratio: AspectRatio
    trim_start_sec: float
    trim_end_sec: float
    is_pinned: bool
    revision: int
    project_json: EditorProjectSchemaV1
    last_render_id: uuid.UUID | None
    assets: list[EditorAssetResponse] = Field(default_factory=list)
    latest_render: EditorRenderResponse | None = None
    storage_usage: UserStorageUsageResponse | None = None
    preview_status: Literal["pending", "ready", "failed"] | None = None
    preview_download_url: str | None = None
    preview_offset_sec: float | None = None
    preview_duration_sec: float | None = None
    preview_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EditorProjectDuplicateResponse(BaseModel):
    project_id: uuid.UUID


class EditorProjectFromClipResponse(BaseModel):
    project_id: uuid.UUID
