import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.export import AspectRatio


class EditorProjectStatus(str, enum.Enum):
    draft = "draft"
    rendering = "rendering"
    ready = "ready"
    error = "error"
    archived = "archived"


class EditorProject(Base):
    __tablename__ = "editor_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[EditorProjectStatus] = mapped_column(
        SAEnum(
            EditorProjectStatus,
            name="editor_project_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=EditorProjectStatus.draft,
        nullable=False,
        index=True,
    )
    aspect_ratio: Mapped[AspectRatio] = mapped_column(
        SAEnum(
            AspectRatio,
            name="aspect_ratio",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=AspectRatio.vertical,
    )
    trim_start_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trim_end_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    project_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    revision: Mapped[int] = mapped_column(nullable=False, default=1)
    last_render_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("editor_renders.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="editor_projects")
    video: Mapped["Video"] = relationship("Video", back_populates="editor_projects")
    clip: Mapped["Clip"] = relationship("Clip", back_populates="editor_projects")
    assets: Mapped[list["EditorAsset"]] = relationship(
        "EditorAsset", back_populates="project", cascade="all, delete-orphan"
    )
    renders: Mapped[list["EditorRender"]] = relationship(
        "EditorRender",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="EditorRender.project_id",
    )
    last_render: Mapped["EditorRender | None"] = relationship(
        "EditorRender",
        foreign_keys=[last_render_id],
        post_update=True,
    )
