import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator
from app.models.video import (
    ClipProfile,
    VideoImportMode,
    VideoImportState,
    VideoSourceType,
    VideoStatus,
)


STORAGE_TEMPORARILY_UNAVAILABLE_MESSAGE = (
    "Source video is temporarily unavailable from storage. Try again after the storage download limit resets."
)


def _safe_video_error_message(value: str | None) -> str | None:
    if not value:
        return value
    normalized = value.lower()
    storage_markers = (
        "headobject",
        "getobject",
        "download_file",
        "backblaze",
        "b2",
        "forbidden",
        "403",
    )
    if any(marker in normalized for marker in storage_markers) and (
        "storage" in normalized or "forbidden" in normalized or "headobject" in normalized
    ):
        return STORAGE_TEMPORARILY_UNAVAILABLE_MESSAGE
    return value


class VideoResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    source_type: VideoSourceType
    source_url: str | None
    source_video_id: str | None
    source_playlist_id: str | None
    source_playlist_title: str | None
    playlist_index: int | None
    import_parent_id: uuid.UUID | None
    embed_url: str | None
    thumbnail_url: str | None
    clip_profile: ClipProfile
    import_state: VideoImportState
    import_state_ui: str | None = None
    import_mode: VideoImportMode
    is_download_blocked: bool
    error_code: str | None
    debug_error_message: str | None
    external_metadata_json: dict
    storage_key: str | None
    source_download_url: str | None = None
    editor_preview_download_url: str | None = None
    editor_preview_status: str | None = None
    duration_sec: int | None
    resolution: str | None
    file_size_bytes: int | None
    raw_source_expires_at: datetime | None = None
    raw_source_days_remaining: int | None = None
    status: VideoStatus
    error_message: str | None
    clip_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("error_message", mode="before")
    @classmethod
    def sanitize_error_message(cls, value):
        return _safe_video_error_message(value)


class VideoCreate(BaseModel):
    title: str | None = None
    source_type: VideoSourceType
    source_url: str | None = None


class VideoUploadUrlRequest(BaseModel):
    filename: str
    file_size: int
    content_type: str
    clip_profile: ClipProfile | None = None

    @field_validator("clip_profile", mode="before")
    @classmethod
    def normalize_clip_profile_alias(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
            if normalized == "long_form_speaking":
                return ClipProfile.sermon.value
        return value


class VideoUploadUrlResponse(BaseModel):
    video_id: uuid.UUID
    upload_url: str
    upload_fields: dict[str, str]
    storage_key: str
    use_local: bool


class VideoConfirmUploadRequest(BaseModel):
    video_id: uuid.UUID


class VideoConfirmUploadResponse(BaseModel):
    video_id: uuid.UUID
    status: VideoStatus


class VideoImportYoutubeRequest(BaseModel):
    url: str
    clip_profile: ClipProfile | None = None

    @field_validator("clip_profile", mode="before")
    @classmethod
    def normalize_clip_profile_alias(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
            if normalized == "long_form_speaking":
                return ClipProfile.sermon.value
        return value


class VideoGenerateClipsRequest(BaseModel):
    clip_profile: ClipProfile | None = None

    @field_validator("clip_profile", mode="before")
    @classmethod
    def normalize_clip_profile_alias(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
            if normalized == "long_form_speaking":
                return ClipProfile.sermon.value
        return value


class VideoGenerateClipsResponse(BaseModel):
    video_id: uuid.UUID
    status: str
    clip_profile: ClipProfile
    message: str


class VideoImportYoutubeResponse(BaseModel):
    video_id: uuid.UUID | None = None
    playlist_import_id: uuid.UUID | None = None
    import_kind: str
    status: VideoStatus | str
    message: str
    recovery_required: bool = False
    recovery_reason: str | None = None
    recovery_action: str | None = None


class VideoListItem(BaseModel):
    id: uuid.UUID
    title: str | None
    status: VideoStatus
    duration_sec: int | None
    clip_count: int
    created_at: datetime
    thumbnail_url: str | None
    clip_profile: ClipProfile
    source_type: VideoSourceType
    source_url: str | None
    source_video_id: str | None
    source_playlist_id: str | None
    source_playlist_title: str | None
    playlist_index: int | None
    import_parent_id: uuid.UUID | None
    embed_url: str | None
    import_state: VideoImportState
    import_state_ui: str | None = None
    import_mode: VideoImportMode
    is_download_blocked: bool
    error_code: str | None
    error_message: str | None
    raw_source_expires_at: datetime | None = None
    raw_source_days_remaining: int | None = None

    @field_validator("error_message", mode="before")
    @classmethod
    def sanitize_error_message(cls, value):
        return _safe_video_error_message(value)


class VideoStatusResponse(BaseModel):
    video_id: uuid.UUID
    status: VideoStatus
    import_state: VideoImportState | None = None
    import_state_ui: str | None = None
    title: str | None
    clip_count: int
    error_message: str | None

    @field_validator("error_message", mode="before")
    @classmethod
    def sanitize_error_message(cls, value):
        return _safe_video_error_message(value)


class TranscriptWordSegment(BaseModel):
    word: str | None
    start: float
    end: float
    confidence: float | None = None
    segment_index: int | None = None


class VideoTranscriptResponse(BaseModel):
    video_id: uuid.UUID
    word_count: int
    duration: float
    language: str | None
    full_text: str
    segments: list[dict]
