import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.connected_account import SocialPlatform
from app.models.social_workflow_run import SocialWorkflowRunStatus


class SocialWorkflowSourceStatus(str, enum.Enum):
    detected = "detected"
    importing = "importing"
    imported_processing = "imported_processing"
    ready_to_publish = "ready_to_publish"
    publishing = "publishing"
    completed = "completed"
    original_required = "original_required"
    import_failed = "import_failed"
    partial_failed = "partial_failed"


_STATUS_TO_RUN_STATUS = {
    SocialWorkflowSourceStatus.detected: SocialWorkflowRunStatus.detected,
    SocialWorkflowSourceStatus.importing: SocialWorkflowRunStatus.importing,
    SocialWorkflowSourceStatus.imported_processing: SocialWorkflowRunStatus.imported_processing,
    SocialWorkflowSourceStatus.ready_to_publish: SocialWorkflowRunStatus.ready_to_publish,
    SocialWorkflowSourceStatus.publishing: SocialWorkflowRunStatus.publishing,
    SocialWorkflowSourceStatus.completed: SocialWorkflowRunStatus.completed,
    SocialWorkflowSourceStatus.original_required: SocialWorkflowRunStatus.original_required,
    SocialWorkflowSourceStatus.import_failed: SocialWorkflowRunStatus.import_failed,
    SocialWorkflowSourceStatus.partial_failed: SocialWorkflowRunStatus.partial_failed,
}


def source_status_to_run_status(status: SocialWorkflowSourceStatus) -> SocialWorkflowRunStatus:
    return _STATUS_TO_RUN_STATUS[status]


class SocialWorkflowSourcePost(Base):
    __tablename__ = "social_workflow_source_posts"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "source_platform",
            "external_post_id",
            name="uq_social_workflow_source_post_external",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
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
    external_post_id: Mapped[str] = mapped_column(String(255), nullable=False)
    permalink: Mapped[str | None] = mapped_column(Text)
    caption_snapshot: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[SocialWorkflowSourceStatus] = mapped_column(
        SAEnum(
            SocialWorkflowSourceStatus,
            name="social_workflow_source_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SocialWorkflowSourceStatus.detected,
        nullable=False,
        index=True,
    )
    video_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    export_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_workflow_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    workflow: Mapped["SocialWorkflow"] = relationship("SocialWorkflow", back_populates="source_posts")
    source_account: Mapped["ConnectedAccount | None"] = relationship("ConnectedAccount", foreign_keys=[source_account_id])
    video: Mapped["Video | None"] = relationship("Video")
    export: Mapped["Export | None"] = relationship("Export")
    workflow_run: Mapped["SocialWorkflowRun | None"] = relationship(
        "SocialWorkflowRun", back_populates="source_post"
    )
