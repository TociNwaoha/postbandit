from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.clip import Clip
from app.models.post_analytics import PostAnalytics
from app.models.publish_job import PublishJob, PublishStatus
from app.models.user import User
from app.schemas.analytics import (
    PostAnalyticsSnapshot,
    PostAnalyticsSummary,
    PostAnalyticsTimeseriesPoint,
    PostAnalyticsTopPerformer,
)
from app.services.object_storage import object_storage_client

router = APIRouter(prefix="/analytics", tags=["analytics"])

METRIC_COLUMNS = {
    "views": PostAnalytics.views,
    "likes": PostAnalytics.likes,
    "comments": PostAnalytics.comments,
    "shares": PostAnalytics.shares,
    "reach": PostAnalytics.reach,
    "impressions": PostAnalytics.impressions,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_from() -> datetime:
    return _utc_now() - timedelta(days=30)


def _date_filters(from_date: datetime | None, to_date: datetime | None):
    start = from_date or _default_from()
    end = to_date or _utc_now()
    return and_(PublishJob.updated_at >= start, PublishJob.updated_at <= end)


def _title_for_job(job: PublishJob) -> str:
    return job.content_title_snapshot or job.title or (job.caption or "Published post")[:80] or "Published post"


def _thumbnail_url_for_clip(clip: Clip | None) -> str | None:
    if not clip or not clip.thumbnail_key:
        return None
    try:
        return object_storage_client.get_presigned_download_url(clip.thumbnail_key)
    except Exception:
        return None


@router.get("/summary", response_model=PostAnalyticsSummary)
async def get_analytics_summary(
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conditions = [PublishJob.user_id == current_user.id, _date_filters(from_date, to_date)]
    result = await db.execute(
        select(
            func.count(PostAnalytics.id),
            func.coalesce(func.sum(PostAnalytics.views), 0),
            func.coalesce(func.sum(PostAnalytics.likes), 0),
            func.coalesce(func.sum(PostAnalytics.comments), 0),
            func.coalesce(func.sum(PostAnalytics.shares), 0),
            func.coalesce(func.sum(PostAnalytics.reach), 0),
            func.coalesce(func.sum(PostAnalytics.impressions), 0),
            func.coalesce(func.sum(case((PostAnalytics.fetch_error.is_not(None), 1), else_=0)), 0),
        )
        .join(PublishJob, PublishJob.id == PostAnalytics.publish_job_id)
        .where(*conditions)
    )
    row = result.one()

    platform_result = await db.execute(
        select(PostAnalytics.provider, func.coalesce(func.sum(PostAnalytics.views), 0).label("views"))
        .join(PublishJob, PublishJob.id == PostAnalytics.publish_job_id)
        .where(*conditions)
        .group_by(PostAnalytics.provider)
        .order_by(desc("views"))
        .limit(1)
    )
    top_platform = platform_result.first()

    return PostAnalyticsSummary(
        total_posts=int(row[0] or 0),
        total_views=int(row[1] or 0),
        total_likes=int(row[2] or 0),
        total_comments=int(row[3] or 0),
        total_shares=int(row[4] or 0),
        total_reach=int(row[5] or 0),
        total_impressions=int(row[6] or 0),
        posts_with_errors=int(row[7] or 0),
        top_platform=str(top_platform[0]) if top_platform else None,
    )


@router.get("/timeseries", response_model=list[PostAnalyticsTimeseriesPoint])
async def get_analytics_timeseries(
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    platform: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    day = func.date(PublishJob.updated_at).label("day")
    conditions = [PublishJob.user_id == current_user.id, _date_filters(from_date, to_date)]
    if platform:
        conditions.append(PostAnalytics.provider == platform)

    result = await db.execute(
        select(
            day,
            PostAnalytics.provider,
            func.coalesce(func.sum(PostAnalytics.views), 0),
            func.coalesce(func.sum(PostAnalytics.likes), 0),
            func.coalesce(func.sum(PostAnalytics.comments), 0),
            func.coalesce(func.sum(PostAnalytics.shares), 0),
            func.coalesce(func.sum(PostAnalytics.reach), 0),
            func.coalesce(func.sum(PostAnalytics.impressions), 0),
        )
        .join(PublishJob, PublishJob.id == PostAnalytics.publish_job_id)
        .where(*conditions)
        .group_by(day, PostAnalytics.provider)
        .order_by(day.asc(), PostAnalytics.provider.asc())
    )

    return [
        PostAnalyticsTimeseriesPoint(
            date=str(row[0]),
            platform=str(row[1]),
            views=int(row[2] or 0),
            likes=int(row[3] or 0),
            comments=int(row[4] or 0),
            shares=int(row[5] or 0),
            reach=int(row[6] or 0),
            impressions=int(row[7] or 0),
        )
        for row in result.all()
    ]


@router.get("/top-performers", response_model=list[PostAnalyticsTopPerformer])
async def get_top_performers(
    limit: int = Query(default=10, ge=1, le=50),
    metric: str = Query(default="views"),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    metric_column = METRIC_COLUMNS.get(metric)
    if metric_column is None:
        raise HTTPException(status_code=400, detail="Unsupported metric")

    result = await db.execute(
        select(PostAnalytics, PublishJob, Clip)
        .join(PublishJob, PublishJob.id == PostAnalytics.publish_job_id)
        .outerjoin(Clip, Clip.id == PublishJob.clip_id)
        .where(PublishJob.user_id == current_user.id, _date_filters(from_date, to_date))
        .order_by(metric_column.desc(), PostAnalytics.views.desc())
        .limit(limit)
    )

    rows = []
    for analytics, job, clip in result.all():
        rows.append(
            PostAnalyticsTopPerformer(
                publish_job_id=job.id,
                platform=analytics.provider,
                title=_title_for_job(job),
                external_post_url=job.external_post_url,
                thumbnail_url=_thumbnail_url_for_clip(clip),
                published_at=job.updated_at if job.status == PublishStatus.published else None,
                views=analytics.views,
                likes=analytics.likes,
                comments=analytics.comments,
                shares=analytics.shares,
                reach=analytics.reach,
                impressions=analytics.impressions,
                fetch_error=analytics.fetch_error,
            )
        )
    return rows


@router.get("/posts/{publish_job_id}", response_model=PostAnalyticsSnapshot)
async def get_post_analytics(
    publish_job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PostAnalytics, PublishJob)
        .join(PublishJob, PublishJob.id == PostAnalytics.publish_job_id)
        .where(PublishJob.id == publish_job_id, PublishJob.user_id == current_user.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Analytics not found")

    analytics, job = row
    return PostAnalyticsSnapshot(
        publish_job_id=job.id,
        platform=analytics.provider,
        title=_title_for_job(job),
        caption=job.caption,
        external_post_id=job.external_post_id,
        external_post_url=job.external_post_url,
        fetched_at=analytics.fetched_at,
        published_at=job.updated_at if job.status == PublishStatus.published else None,
        views=analytics.views,
        likes=analytics.likes,
        comments=analytics.comments,
        shares=analytics.shares,
        reach=analytics.reach,
        impressions=analytics.impressions,
        fetch_error=analytics.fetch_error,
        raw_response=analytics.raw_response,
    )
