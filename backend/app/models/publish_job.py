import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.connected_account import SocialPlatform


class PublishStatus(str, enum.Enum):
    scheduled = "scheduled"
    queued = "queued"
    publishing = "publishing"
    published = "published"
    failed = "failed"
    waiting_user_action = "waiting_user_action"
    provider_not_configured = "provider_not_configured"
    cancelled = "cancelled"


class PublishMode(str, enum.Enum):
    now = "now"
    scheduled = "scheduled"


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    export_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    clip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clips.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[SocialPlatform] = mapped_column(
        SAEnum(
            SocialPlatform,
            name="social_platform",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    connected_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connected_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[PublishStatus] = mapped_column(
        SAEnum(
            PublishStatus,
            name="publish_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=PublishStatus.queued,
        nullable=False,
        index=True,
    )
    publish_mode: Mapped[PublishMode] = mapped_column(
        SAEnum(
            PublishMode,
            name="publish_mode",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=PublishMode.now,
        nullable=False,
    )
    caption: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    hashtags: Mapped[list[str] | None] = mapped_column(JSONB)
    privacy: Mapped[str | None] = mapped_column(String(64))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    timezone: Mapped[str | None] = mapped_column(String(100))
    destination_display_name: Mapped[str | None] = mapped_column(String(255))
    content_title_snapshot: Mapped[str | None] = mapped_column(String(500))
    external_post_id: Mapped[str | None] = mapped_column(String(255))
    external_post_url: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    provider_metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="publish_jobs")
    export: Mapped["Export | None"] = relationship("Export", back_populates="publish_jobs")
    clip: Mapped["Clip | None"] = relationship("Clip", back_populates="publish_jobs")
    connected_account: Mapped["ConnectedAccount | None"] = relationship(
        "ConnectedAccount", back_populates="publish_jobs"
    )
    attempts: Mapped[list["PublishAttempt"]] = relationship(
        "PublishAttempt", back_populates="publish_job", cascade="all, delete-orphan"
    )
