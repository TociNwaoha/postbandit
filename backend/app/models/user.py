import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserTier(str, enum.Enum):
    starter = "starter"
    creator = "creator"
    agency = "agency"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[UserTier] = mapped_column(
        SAEnum(UserTier, name="user_tier"), default=UserTier.starter, nullable=False
    )
    videos_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    billing_plan: Mapped[str] = mapped_column(String(50), default="trial", nullable=False)
    subscription_status: Mapped[str] = mapped_column(String(50), default="trialing", nullable=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    platforms_allowed: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_skipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    onboarding_metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    videos: Mapped[list["Video"]] = relationship("Video", back_populates="user", cascade="all, delete-orphan")
    exports: Mapped[list["Export"]] = relationship("Export", back_populates="user", cascade="all, delete-orphan")
    connected_accounts: Mapped[list["ConnectedAccount"]] = relationship(
        "ConnectedAccount", back_populates="user", cascade="all, delete-orphan"
    )
    publish_jobs: Mapped[list["PublishJob"]] = relationship(
        "PublishJob", back_populates="user", cascade="all, delete-orphan"
    )
    carousel_exports: Mapped[list["CarouselExport"]] = relationship(
        "CarouselExport", back_populates="user", cascade="all, delete-orphan"
    )
    brand_profile: Mapped["BrandProfile | None"] = relationship(
        "BrandProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    content_queue_items: Mapped[list["ContentQueueItem"]] = relationship(
        "ContentQueueItem", back_populates="user", cascade="all, delete-orphan"
    )
    editor_projects: Mapped[list["EditorProject"]] = relationship(
        "EditorProject", back_populates="user", cascade="all, delete-orphan"
    )
    editor_assets: Mapped[list["EditorAsset"]] = relationship(
        "EditorAsset", back_populates="user", cascade="all, delete-orphan"
    )
    clip_overlay_assets: Mapped[list["ClipOverlayAsset"]] = relationship(
        "ClipOverlayAsset", back_populates="user", cascade="all, delete-orphan"
    )
    editor_renders: Mapped[list["EditorRender"]] = relationship(
        "EditorRender", back_populates="user", cascade="all, delete-orphan"
    )
    storage_usage: Mapped["UserStorageUsage | None"] = relationship(
        "UserStorageUsage", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    social_workflows: Mapped[list["SocialWorkflow"]] = relationship(
        "SocialWorkflow", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="user", cascade="all, delete-orphan"
    )
