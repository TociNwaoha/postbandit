from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.twitch_channel import TwitchChannel, TwitchChannelStatus
from app.models.user import User
from app.services.twitch import (
    TwitchAPIError,
    TwitchConfigurationError,
    claim_event_message,
    ensure_channel_subscriptions,
    get_twitch_user,
    verify_eventsub_signature,
)
from app.api.routes.auth import get_current_user

router = APIRouter(tags=["twitch"])


class TwitchChannelCreate(BaseModel):
    login: str = Field(min_length=1, max_length=255)

    @field_validator("login")
    @classmethod
    def validate_login(cls, value: str) -> str:
        login = value.strip().lower()
        if not login.replace("_", "").isalnum():
            raise ValueError("Enter a valid Twitch username")
        return login


class TwitchChannelResponse(BaseModel):
    id: uuid.UUID
    twitch_broadcaster_id: str
    twitch_login: str
    display_name: str
    is_live: bool
    last_live_event_at: datetime | None
    status: TwitchChannelStatus
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/twitch-channels", response_model=list[TwitchChannelResponse])
async def list_twitch_channels(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(TwitchChannel)
        .where(TwitchChannel.owner_user_id == current_user.id)
        .order_by(TwitchChannel.created_at.desc())
    )
    return result.scalars().all()


@router.post("/twitch-channels", response_model=TwitchChannelResponse, status_code=status.HTTP_201_CREATED)
async def connect_twitch_channel(
    body: TwitchChannelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        profile = await asyncio.to_thread(get_twitch_user, body.login)
        await asyncio.to_thread(ensure_channel_subscriptions, str(profile["id"]))
    except TwitchConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TwitchAPIError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc

    existing = await db.scalar(
        select(TwitchChannel).where(
            TwitchChannel.owner_user_id == current_user.id,
            TwitchChannel.twitch_broadcaster_id == str(profile["id"]),
        )
    )
    if existing:
        existing.status = TwitchChannelStatus.active
        return existing
    channel = TwitchChannel(
        owner_user_id=current_user.id,
        twitch_broadcaster_id=str(profile["id"]),
        twitch_login=str(profile.get("login") or body.login),
        display_name=str(profile.get("display_name") or body.login),
    )
    db.add(channel)
    await db.flush()
    return channel


@router.post("/webhooks/twitch/eventsub", include_in_schema=False)
async def twitch_eventsub_webhook(
    request: Request,
    twitch_message_id: str | None = Header(default=None, alias="Twitch-Eventsub-Message-Id"),
    twitch_message_timestamp: str | None = Header(default=None, alias="Twitch-Eventsub-Message-Timestamp"),
    twitch_message_signature: str | None = Header(default=None, alias="Twitch-Eventsub-Message-Signature"),
    twitch_message_type: str | None = Header(default=None, alias="Twitch-Eventsub-Message-Type"),
    db: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()
    if not verify_eventsub_signature(
        message_id=twitch_message_id or "",
        timestamp=twitch_message_timestamp or "",
        raw_body=raw_body,
        signature=twitch_message_signature or "",
    ):
        raise HTTPException(status_code=403, detail="Invalid Twitch EventSub signature")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Twitch EventSub payload") from exc

    if twitch_message_type == "webhook_callback_verification":
        challenge = str(payload.get("challenge") or "")
        if not challenge:
            raise HTTPException(status_code=400, detail="Missing Twitch EventSub challenge")
        return PlainTextResponse(challenge)
    if twitch_message_type != "notification" or not twitch_message_id or not claim_event_message(twitch_message_id):
        return {"received": True}

    event_type = str(payload.get("subscription", {}).get("type") or "")
    broadcaster_id = str(payload.get("event", {}).get("broadcaster_user_id") or "")
    if event_type not in {"stream.online", "stream.offline"} or not broadcaster_id:
        return {"received": True}
    result = await db.execute(select(TwitchChannel).where(TwitchChannel.twitch_broadcaster_id == broadcaster_id))
    for channel in result.scalars():
        channel.is_live = event_type == "stream.online"
        channel.last_live_event_at = datetime.now(timezone.utc)
    return {"received": True}
