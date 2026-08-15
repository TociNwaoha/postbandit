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
from app.models.job import Job, JobStatus
from app.models.twitch_channel import TwitchChannel, TwitchChannelStatus
from app.models.user import User
from app.models.video import Video, VideoImportMode, VideoImportState, VideoSourceType, VideoStatus
from app.services.twitch import (
    TwitchAPIError,
    TwitchConfigurationError,
    claim_event_message,
    ensure_channel_subscriptions,
    get_live_stream,
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


class TwitchClipRequestResponse(BaseModel):
    video_id: uuid.UUID
    task_id: str
    status: str = "queued"
    message: str


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


@router.post("/twitch-channels/{channel_id}/clip", response_model=TwitchClipRequestResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_twitch_live_clip(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    channel = await db.scalar(
        select(TwitchChannel).where(
            TwitchChannel.id == channel_id,
            TwitchChannel.owner_user_id == current_user.id,
            TwitchChannel.status == TwitchChannelStatus.active,
        )
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Twitch channel not found")
    try:
        stream = await asyncio.to_thread(get_live_stream, channel.twitch_broadcaster_id)
    except TwitchAPIError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc

    channel.is_live = bool(stream)
    if stream:
        channel.last_live_event_at = datetime.now(timezone.utc)
    if not stream:
        raise HTTPException(status_code=409, detail="This Twitch channel is not live right now")

    active_job = await db.scalar(
        select(Job)
        .join(Video, Job.video_id == Video.id)
        .where(
            Video.triggering_channel_id == channel.id,
            Job.type == "twitch_live_clip",
            Job.status.in_([JobStatus.queued, JobStatus.running]),
        )
    )
    if active_job:
        raise HTTPException(status_code=409, detail="A live clip is already being created for this channel")

    video = Video(
        user_id=current_user.id,
        title=f"Live clip from {channel.display_name}",
        source_type=VideoSourceType.twitch_live,
        source_url=f"https://www.twitch.tv/{channel.twitch_login}",
        import_mode=VideoImportMode.server_download,
        import_state=VideoImportState.queued,
        status=VideoStatus.queued,
        triggering_channel_id=channel.id,
        triggered_by_user_id=current_user.id,
        external_metadata_json={"twitch_live": {"broadcaster_id": channel.twitch_broadcaster_id}},
    )
    db.add(video)
    await db.flush()
    job = Job(video_id=video.id, type="twitch_live_clip", payload={"channel_id": str(channel.id)}, status=JobStatus.queued)
    db.add(job)
    await db.flush()
    try:
        from app.worker.tasks.twitch_live import create_live_clip

        task = create_live_clip.apply_async(args=[str(video.id)], queue="twitch_live_clips")
        job.celery_task_id = task.id
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not queue Twitch live clip") from exc
    return TwitchClipRequestResponse(video_id=video.id, task_id=task.id, message="Twitch clip request queued")


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
