import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.connected_account import SocialPlatform


class SocialWorkflowStatus(str, enum.Enum):
    active = "active"
    paused = "paused"


class SocialWorkflowCopyMode(str, enum.Enum):
    reuse_source = "reuse_source"
    platform_ai = "platform_ai"
    both = "both"


class WorkflowCopyMode(str, enum.Enum):
    # Legacy names retained for main-branch workflow helpers/tests that are no
    # longer the primary workflow path after the official-source workflow work.
    ai_platform = "ai_platform"
    reuse_source = "reuse_source"


class WorkflowRunStatus(str, enum.Enum):
    waiting_asset = "waiting_asset"
    processing = "processing"
    queued = "queued"
    completed = "completed"
    partial_failed = "partial_failed"
    failed = "failed"
    skipped = "skipped"


class SocialWorkflow(Base):
    __tablename__ = "social_workflows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_platform: Mapped[SocialPlatform] = mapped_column(
        SAEnum(
            SocialPlatform,
            name="social_platform",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            create_type=False,
        ),
        nullable=False,
        index=True,
    )
    source_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connected_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[SocialWorkflowStatus] = mapped_column(
        SAEnum(
            SocialWorkflowStatus,
            name="social_workflow_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SocialWorkflowStatus.active,
        nullable=False,
        index=True,
    )
    copy_mode: Mapped[SocialWorkflowCopyMode] = mapped_column(
        SAEnum(
            SocialWorkflowCopyMode,
            name="social_workflow_copy_mode",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SocialWorkflowCopyMode.both,
        nullable=False,
    )
    auto_publish: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    destination_targets_json: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    poll_cursor_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="social_workflows")
    source_account: Mapped["ConnectedAccount | None"] = relationship("ConnectedAccount", foreign_keys=[source_account_id])
    source_posts: Mapped[list["SocialWorkflowSourcePost"]] = relationship(
        "SocialWorkflowSourcePost", back_populates="workflow", cascade="all, delete-orphan"
    )
    runs: Mapped[list["SocialWorkflowRun"]] = relationship(
        "SocialWorkflowRun", back_populates="workflow", cascade="all, delete-orphan"
    )


from app.models.social_workflow_run import SocialWorkflowRun  # noqa: E402
