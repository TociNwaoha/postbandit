import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.connected_account import SocialPlatform


class WorkflowCopyMode(str, enum.Enum):
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
    source_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connected_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
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
    copy_mode: Mapped[WorkflowCopyMode] = mapped_column(
        SAEnum(
            WorkflowCopyMode,
            name="workflow_copy_mode",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=WorkflowCopyMode.ai_platform,
        nullable=False,
    )
    destination_configs: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    cursor_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="social_workflows")
    source_account: Mapped["ConnectedAccount | None"] = relationship("ConnectedAccount")
    runs: Mapped[list["SocialWorkflowRun"]] = relationship(
        "SocialWorkflowRun", back_populates="workflow", cascade="all, delete-orphan"
    )


class SocialWorkflowRun(Base):
    __tablename__ = "social_workflow_runs"
    __table_args__ = (
        UniqueConstraint("workflow_id", "source_external_post_id", name="uq_workflow_source_post"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_publish_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publish_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_export_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exports.id", ondelete="SET NULL"), nullable=True, index=True
    )
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
    source_external_post_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_external_url: Mapped[str | None] = mapped_column(Text)
    source_title: Mapped[str | None] = mapped_column(String(500))
    source_description: Mapped[str | None] = mapped_column(Text)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[WorkflowRunStatus] = mapped_column(
        SAEnum(
            WorkflowRunStatus,
            name="workflow_run_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=WorkflowRunStatus.waiting_asset,
        nullable=False,
        index=True,
    )
    generated_copy_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    workflow: Mapped["SocialWorkflow"] = relationship("SocialWorkflow", back_populates="runs")
    user: Mapped["User"] = relationship("User")
    source_publish_job: Mapped["PublishJob | None"] = relationship(
        "PublishJob", foreign_keys=[source_publish_job_id]
    )
    source_export: Mapped["Export | None"] = relationship("Export", foreign_keys=[source_export_id])
    publish_jobs: Mapped[list["PublishJob"]] = relationship(
        "PublishJob", back_populates="workflow_run", foreign_keys="PublishJob.workflow_run_id"
    )
