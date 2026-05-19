import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AspectRatio(str, enum.Enum):
    original = "original"
    vertical = "9:16"
    landscape = "16:9"
    square = "1:1"


class CaptionStyle(str, enum.Enum):
    bold_boxed = "bold_boxed"
    sermon_quote = "sermon_quote"
    clean_minimal = "clean_minimal"
    kinetic_bold = "kinetic_bold"
    cinema_outline = "cinema_outline"
    clean_highlight = "clean_highlight"


class CaptionFormat(str, enum.Enum):
    burned_in = "burned_in"
    srt = "srt"


class CaptionColorVariant(str, enum.Enum):
    classic = "classic"
    warm = "warm"
    cool = "cool"


class ExportStatus(str, enum.Enum):
    queued = "queued"
    rendering = "rendering"
    ready = "ready"
    error = "error"


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    retry_of_export_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exports.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    aspect_ratio: Mapped[AspectRatio] = mapped_column(
        SAEnum(
            AspectRatio,
            name="aspect_ratio",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    caption_style: Mapped[CaptionStyle | None] = mapped_column(SAEnum(CaptionStyle, name="caption_style"))
    caption_color_variant: Mapped[CaptionColorVariant | None] = mapped_column(
        SAEnum(CaptionColorVariant, name="caption_color_variant")
    )
    caption_format: Mapped[CaptionFormat] = mapped_column(SAEnum(CaptionFormat, name="caption_format"), nullable=False)
    caption_vertical_position: Mapped[float | None] = mapped_column(Float)
    caption_scale: Mapped[float | None] = mapped_column(Float)
    frame_anchor_x: Mapped[float | None] = mapped_column(Float)
    frame_anchor_y: Mapped[float | None] = mapped_column(Float)
    frame_zoom: Mapped[float | None] = mapped_column(Float)
    storage_key: Mapped[str | None] = mapped_column(Text)
    srt_key: Mapped[str | None] = mapped_column(Text)
    download_url: Mapped[str | None] = mapped_column(Text)
    url_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ExportStatus] = mapped_column(
        SAEnum(ExportStatus, name="export_status"), default=ExportStatus.queued, nullable=False, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    render_time_sec: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    clip: Mapped["Clip"] = relationship("Clip", back_populates="exports")
    user: Mapped["User"] = relationship("User", back_populates="exports")
    publish_jobs: Mapped[list["PublishJob"]] = relationship(
        "PublishJob", back_populates="export", cascade="all, delete-orphan"
    )
