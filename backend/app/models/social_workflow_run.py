import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SocialWorkflowRunStatus(str, enum.Enum):
    detected = "detected"
    importing = "importing"
    imported_processing = "imported_processing"
    ready_to_publish = "ready_to_publish"
    publishing = "publishing"
    completed = "completed"
    original_required = "original_required"
    import_failed = "import_failed"
    partial_failed = "partial_failed"


class SocialWorkflowRun(Base):
    __tablename__ = "social_workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[SocialWorkflowRunStatus] = mapped_column(
        SAEnum(
            SocialWorkflowRunStatus,
            name="social_workflow_run_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=SocialWorkflowRunStatus.detected,
        nullable=False,
        index=True,
    )
    publish_job_ids_json: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    destination_results_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    workflow: Mapped["SocialWorkflow"] = relationship("SocialWorkflow", back_populates="runs")
    source_post: Mapped["SocialWorkflowSourcePost | None"] = relationship(
        "SocialWorkflowSourcePost", back_populates="workflow_run", uselist=False
    )
