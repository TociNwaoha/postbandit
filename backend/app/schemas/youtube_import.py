import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.video import VideoImportMode, VideoImportState, VideoStatus


class PlaylistImportItemResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    status: VideoStatus
    import_state: VideoImportState
    import_state_ui: str | None = None
    playlist_index: int | None
    source_video_id: str | None
    embed_url: str | None
    thumbnail_url: str | None
    import_mode: VideoImportMode
    is_download_blocked: bool
    error_code: str | None
    error_message: str | None


class PlaylistImportResponse(BaseModel):
    id: uuid.UUID
    source_url: str
    playlist_id: str
    title: str | None
    status: str
    total_items: int
    completed_items: int
    failed_items: int
    created_at: datetime
    updated_at: datetime
    items: list[PlaylistImportItemResponse]


class VideoManualUploadUrlResponse(BaseModel):
    video_id: uuid.UUID
    upload_url: str
    upload_fields: dict[str, str]
    storage_key: str
    use_local: bool


class VideoManualUploadConfirmResponse(BaseModel):
    video_id: uuid.UUID
    status: VideoStatus
    message: str


class LocalHelperSessionRequest(BaseModel):
    video_id: uuid.UUID


class LocalHelperSessionResponse(BaseModel):
    video_id: uuid.UUID
    helper_session_token: str
    upload_url: str
    upload_fields: dict[str, str]
    upload_key: str
    use_local: bool
    source_url: str
    complete_url: str
    expires_at: datetime


class LocalHelperCompleteRequest(BaseModel):
    helper_session_token: str
    upload_key: str
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None


class LocalHelperCompleteResponse(BaseModel):
    video_id: uuid.UUID
    status: VideoStatus
    message: str
