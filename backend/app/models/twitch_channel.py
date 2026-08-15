import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TwitchChannelStatus(str, enum.Enum):
    active = "active"
    disconnected = "disconnected"


class TwitchChannel(Base):
    __tablename__ = "twitch_channels"
    __table_args__ = (UniqueConstraint("owner_user_id", "twitch_broadcaster_id", name="uq_twitch_channel_owner_broadcaster"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    twitch_broadcaster_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    twitch_login: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    last_live_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[TwitchChannelStatus] = mapped_column(
        SAEnum(TwitchChannelStatus, name="twitch_channel_status"),
        default=TwitchChannelStatus.active,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
