import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ContentQueueItem(Base):
    __tablename__ = "content_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, default="carousel")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    slide_urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    slide_keys_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    zip_key: Mapped[str | None] = mapped_column(Text)
    preview_key: Mapped[str | None] = mapped_column(Text)
    asset_cleanup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    assets_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    platforms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_topic: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="content_queue_items")
