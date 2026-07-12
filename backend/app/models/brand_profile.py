import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BrandProfile(Base):
    __tablename__ = "brand_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    handle: Mapped[str] = mapped_column(String(100), nullable=False)
    niche: Mapped[str] = mapped_column(String(200), nullable=False)
    target_audience: Mapped[str] = mapped_column(String(300), nullable=False)
    tone: Mapped[str] = mapped_column(String(50), nullable=False)
    use_phrases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    avoid_phrases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    ai_cmo_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    post_frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    preferred_platforms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="brand_profile")
