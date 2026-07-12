import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import clips as clip_routes
from app.api.routes import exports as export_routes
from app.api.routes import social as social_routes
from app.api.routes import videos as video_routes
from app.api.v1_auth import get_v1_current_user
from app.database import get_db
from app.models.connected_account import ConnectedAccount, SocialPlatform
from app.models.publish_job import PublishJob, PublishStatus
from app.models.user import User
from app.models.video import Video
from app.schemas.clip import PlatformCopyGenerateRequest
from app.schemas.export import ExportCreate
from app.schemas.social import PublishContentInput, PublishCreateRequest, PublishJobResponse, PublishTargetInput
from app.schemas.v1 import (
    V1ClipExportRequest,
    V1CopyRequest,
    V1Envelope,
    V1Meta,
    V1Pagination,
    V1PublishItem,
    V1VideoImportRequest,
    cadence_from_public_style,
)
from app.models.export import CaptionFormat, CaptionStyle
from app.schemas.video import VideoImportYoutubeRequest
from app.services.api_rate_limits import get_plan_limits

router = APIRouter(tags=["public-v1"])


def envelope(request: Request, data: Any) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    request.state.request_id = request_id
    return V1Envelope(
        data=data,
        meta=V1Meta(request_id=request_id, timestamp=datetime.now(timezone.utc)),
    ).model_dump(mode="json")


def model_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "body"):
        try:
            return json.loads(value.body.decode())
        except Exception:
            return value.body.decode()
    if isinstance(value, list):
        return [model_data(item) for item in value]
    return value


@router.get("/me")
async def get_me_v1(request: Request, current_user: User = Depends(get_v1_current_user)):
    platforms = [item.value for item in SocialPlatform]
    plan = current_user.tier.value if hasattr(current_user.tier, "value") else str(current_user.tier)
    return envelope(
        request,
        {
            "user_id": str(current_user.id),
            "email": current_user.email,
            "plan_tier": plan,
            "api_limits": get_plan_limits(current_user.tier),
            "platforms_allowed": platforms,
        },
    )


@router.get("/accounts")
async def list_accounts_v1(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    result = await db.execute(
        select(ConnectedAccount)
        .where(ConnectedAccount.user_id == current_user.id)
        .order_by(ConnectedAccount.platform.asc(), ConnectedAccount.created_at.desc())
    )
    rows = result.scalars().all()
    return envelope(
        request,
        [
            {
                "id": str(row.id),
                "provider": row.platform.value,
                "display_name": row.display_name or row.username_or_channel_name or row.external_account_id,
                "destination_type": row.metadata_json.get("destination_type") or "account",
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    )


@router.post("/videos/import")
async def import_video_v1(
    request: Request,
    body: V1VideoImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    result = await video_routes.import_youtube(
        VideoImportYoutubeRequest(url=body.url),
        db=db,
        current_user=current_user,
    )
    data = model_data(result)
    if body.title and data.get("video_id"):
        video = await db.get(Video, uuid.UUID(data["video_id"]))
        if video and video.user_id == current_user.id:
            video.title = body.title
            await db.flush()
    return envelope(
        request,
        {
            "video_id": data.get("video_id"),
            "status": "processing" if data.get("status") not in {"error", "ready"} else data.get("status"),
            "estimated_time_seconds": 300,
            "import_kind": data.get("import_kind"),
            "message": data.get("message"),
        },
    )


@router.get("/videos")
async def list_videos_v1(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    offset = (page - 1) * limit
    rows = await video_routes.list_videos(limit=limit, offset=offset, db=db, current_user=current_user)
    return envelope(
        request,
        {
            "items": model_data(rows),
            "pagination": V1Pagination(page=page, limit=limit, count=len(rows)).model_dump(),
        },
    )


@router.get("/videos/{video_id}")
async def get_video_v1(
    request: Request,
    video_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    row = await video_routes.get_video(video_id=video_id, db=db, current_user=current_user)
    return envelope(request, model_data(row))


@router.get("/videos/{video_id}/clips")
async def list_video_clips_v1(
    request: Request,
    video_id: uuid.UUID,
    min_score: float = Query(default=0.0, ge=0.0),
    limit: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    rows = await clip_routes.list_clips(video_id=str(video_id), db=db, current_user=current_user)
    filtered = [item for item in rows if (item.score or 0) >= min_score][:limit]
    return envelope(request, model_data(filtered))


@router.get("/clips/{clip_id}")
async def get_clip_v1(
    request: Request,
    clip_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    row = await clip_routes.get_clip(clip_id=clip_id, db=db, current_user=current_user)
    data = model_data(row)
    if data.get("transcript_text"):
        data["transcript_excerpt"] = data["transcript_text"][:1000]
    return envelope(request, data)


@router.post("/clips/{clip_id}/export")
async def export_clip_v1(
    request: Request,
    clip_id: uuid.UUID,
    body: V1ClipExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    caption_format, caption_cadence = cadence_from_public_style(body.caption_style)
    result = await export_routes.create_export(
        ExportCreate(
            clip_id=clip_id,
            aspect_ratio=body.aspect_ratio,
            caption_style=None if caption_format == "none" else CaptionStyle.clean_minimal,
            caption_format=CaptionFormat(caption_format),
            caption_cadence=caption_cadence,
        ),
        db=db,
        current_user=current_user,
    )
    data = model_data(result)
    return envelope(request, {"export_id": data.get("id"), "status": data.get("status")})


@router.get("/exports/{export_id}")
async def get_export_v1(
    request: Request,
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    row = await export_routes.get_export(export_id=export_id, db=db, current_user=current_user)
    data = model_data(row)
    return envelope(
        request,
        {
            "export_id": data.get("id"),
            "status": data.get("status"),
            "download_url": data.get("download_url"),
            "progress_percent": 100 if data.get("status") == "ready" else 0,
            "error_message": data.get("error_message"),
        },
    )


@router.post("/publish")
async def publish_v1(
    request: Request,
    body: list[V1PublishItem],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    jobs: list[dict[str, Any]] = []
    for item in body:
        created = await social_routes.create_publish_jobs(
            PublishCreateRequest(
                export_id=item.export_id,
                universal=PublishContentInput(
                    caption=item.copy.caption,
                    title=item.copy.title,
                    description=item.copy.description,
                    hashtags=item.copy.hashtags,
                    privacy=item.privacy,
                    scheduled_for=item.scheduled_at,
                    timezone=item.timezone,
                ),
                targets=[PublishTargetInput(platform=item.provider, connected_account_id=item.connected_account_id)],
            ),
            db=db,
            current_user=current_user,
        )
        jobs.extend(model_data(created))
    return envelope(
        request,
        [
            {
                "job_id": item.get("id"),
                "provider": item.get("platform"),
                "scheduled_at": item.get("scheduled_for"),
                "status": item.get("status"),
            }
            for item in jobs
        ],
    )


@router.get("/publish/jobs")
async def list_publish_jobs_v1(
    request: Request,
    publish_status: PublishStatus | None = Query(default=None, alias="status"),
    provider: SocialPlatform | None = Query(default=None),
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    query = select(PublishJob).where(PublishJob.user_id == current_user.id)
    if publish_status:
        query = query.where(PublishJob.status == publish_status)
    if provider:
        query = query.where(PublishJob.platform == provider)
    if from_date:
        query = query.where(PublishJob.created_at >= from_date)
    if to_date:
        query = query.where(PublishJob.created_at <= to_date)
    result = await db.execute(query.order_by(PublishJob.created_at.desc()).limit(limit))
    rows = [
        PublishJobResponse.model_validate(row).model_dump(mode="json")
        for row in result.scalars().all()
    ]
    return envelope(request, rows)


@router.get("/publish/jobs/{job_id}")
async def get_publish_job_v1(
    request: Request,
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    row = await social_routes.get_publish_job(publish_job_id=job_id, db=db, current_user=current_user)
    return envelope(request, model_data(row))


@router.post("/clips/{clip_id}/copy")
async def generate_copy_v1(
    request: Request,
    clip_id: str,
    body: V1CopyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_v1_current_user),
):
    row = await clip_routes.generate_platform_copy_for_clip(
        clip_id=clip_id,
        body=PlatformCopyGenerateRequest(platforms=body.platforms, topic_hint=body.topic_hint),
        db=db,
        current_user=current_user,
    )
    return envelope(request, model_data(row))
