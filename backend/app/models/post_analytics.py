import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PostAnalytics(Base):
    __tablename__ = "post_analytics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publish_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("publish_jobs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    views: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    likes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    comments: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    shares: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    reach: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    impressions: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    fetch_error: Mapped[str | None] = mapped_column(String(100))
    raw_response: Mapped[dict | None] = mapped_column(JSONB)

    publish_job: Mapped["PublishJob"] = relationship("PublishJob")
