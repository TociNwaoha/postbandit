from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel


class PostAnalyticsSummary(BaseModel):
    total_posts: int
    total_views: int
    total_likes: int
    total_comments: int
    total_shares: int
    total_reach: int
    total_impressions: int
    posts_with_errors: int
    top_platform: str | None = None


class PostAnalyticsTimeseriesPoint(BaseModel):
    date: str
    platform: str
    views: int
    likes: int
    comments: int
    shares: int
    reach: int
    impressions: int


class PostAnalyticsTopPerformer(BaseModel):
    publish_job_id: uuid.UUID
    platform: str
    title: str
    external_post_url: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    views: int
    likes: int
    comments: int
    shares: int
    reach: int
    impressions: int
    fetch_error: str | None = None


class PostAnalyticsSnapshot(BaseModel):
    publish_job_id: uuid.UUID
    platform: str
    title: str
    caption: str | None = None
    external_post_id: str | None = None
    external_post_url: str | None = None
    fetched_at: datetime | None = None
    published_at: datetime | None = None
    views: int
    likes: int
    comments: int
    shares: int
    reach: int
    impressions: int
    fetch_error: str | None = None
    raw_response: dict | None = None
