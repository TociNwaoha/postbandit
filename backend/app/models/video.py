import uuid
from datetime import datetime
from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    Text,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Boolean,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import enum


class VideoSourceType(str, enum.Enum):
    upload = "upload"
    youtube_single = "youtube_single"
    youtube_playlist = "youtube_playlist"
    youtube = "youtube"
    instagram = "instagram"
    facebook = "facebook"
    tiktok = "tiktok"
    x = "x"
    twitch = "twitch"


class VideoStatus(str, enum.Enum):
    queued = "queued"
    downloading = "downloading"
    transcribing = "transcribing"
    scoring = "scoring"
    ready = "ready"
    error = "error"


class VideoImportMode(str, enum.Enum):
    server_download = "server_download"
    embed_only = "embed_only"
    manual_upload = "manual_upload"


class ClipProfile(str, enum.Enum):
    viral = "viral"
    sermon = "sermon"


class VideoImportState(str, enum.Enum):
    not_applicable = "not_applicable"
    queued = "queued"
    metadata_extracting = "metadata_extracting"
    downloadable = "downloadable"
    downloading = "downloading"
    blocked = "blocked"
    replacement_upload_required = "replacement_upload_required"
    helper_required = "helper_required"
    embed_only = "embed_only"
    processing = "processing"
    ready = "ready"
    failed_retryable = "failed_retryable"
    failed_terminal = "failed_terminal"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(500))
    source_type: Mapped[VideoSourceType] = mapped_column(
        SAEnum(VideoSourceType, name="video_source_type"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    source_video_id: Mapped[str | None] = mapped_column(String(128), index=True)
    source_playlist_id: Mapped[str | None] = mapped_column(String(64), index=True)
    source_playlist_title: Mapped[str | None] = mapped_column(String(500))
    playlist_index: Mapped[int | None] = mapped_column(Integer, index=True)
    import_parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("youtube_playlist_imports.id", ondelete="SET NULL"), index=True
    )
    embed_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    import_state: Mapped[VideoImportState] = mapped_column(
        SAEnum(VideoImportState, name="video_import_state"),
        default=VideoImportState.not_applicable,
        nullable=False,
        index=True,
    )
    import_state_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    import_mode: Mapped[VideoImportMode] = mapped_column(
        SAEnum(VideoImportMode, name="video_import_mode"),
        default=VideoImportMode.server_download,
        nullable=False,
    )
    is_download_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    debug_error_message: Mapped[str | None] = mapped_column(Text)
    external_metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    resolution: Mapped[str | None] = mapped_column(String(20))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[VideoStatus] = mapped_column(
        SAEnum(VideoStatus, name="video_status"), default=VideoStatus.queued, nullable=False, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    clip_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="videos")
    transcript_segments: Mapped[list["TranscriptSegment"]] = relationship(
        "TranscriptSegment", back_populates="video", cascade="all, delete-orphan"
    )
    clips: Mapped[list["Clip"]] = relationship("Clip", back_populates="video", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="video", cascade="all, delete-orphan")
    exclude_zones: Mapped[list["ExcludeZone"]] = relationship(
        "ExcludeZone", back_populates="video", cascade="all, delete-orphan"
    )
    playlist_import: Mapped["YoutubePlaylistImport | None"] = relationship(
        "YoutubePlaylistImport", back_populates="videos"
    )
    editor_projects: Mapped[list["EditorProject"]] = relationship(
        "EditorProject", back_populates="video", cascade="all, delete-orphan"
    )
