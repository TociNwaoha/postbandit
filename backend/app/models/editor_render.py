import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EditorRenderStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class EditorRenderPreset(str, enum.Enum):
    tiktok = "tiktok"
    reels = "reels"
    shorts = "shorts"
    linkedin = "linkedin"
    square = "square"
    landscape = "landscape"


class EditorRender(Base):
    __tablename__ = "editor_renders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("editor_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    export_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exports.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[EditorRenderStatus] = mapped_column(
        SAEnum(
            EditorRenderStatus,
            name="editor_render_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EditorRenderStatus.queued,
        index=True,
    )
    preset: Mapped[EditorRenderPreset] = mapped_column(
        SAEnum(
            EditorRenderPreset,
            name="editor_render_preset",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EditorRenderPreset.tiktok,
    )
    output_storage_key: Mapped[str | None] = mapped_column(Text)
    output_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    error_message: Mapped[str | None] = mapped_column(Text)
    ffmpeg_command_debug: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    project: Mapped["EditorProject"] = relationship(
        "EditorProject", back_populates="renders", foreign_keys=[project_id]
    )
    user: Mapped["User"] = relationship("User", back_populates="editor_renders")
    export: Mapped["Export | None"] = relationship("Export", back_populates="editor_renders")
