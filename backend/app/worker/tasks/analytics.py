from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import joinedload

from app.celery_app import celery_app
from app.analytics.fetchers import fetch_metrics_for_job
from app.database import SyncSessionLocal
from app.models.post_analytics import PostAnalytics
from app.models.publish_job import PublishJob, PublishStatus

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.analytics.refresh_post_analytics")
def refresh_post_analytics(batch_size: int = 50, lookback_days: int = 30) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    stats = {"checked": 0, "updated": 0, "skipped": 0, "failed": 0}

    with SyncSessionLocal() as db:
        jobs = (
            db.execute(
                select(PublishJob)
                .options(joinedload(PublishJob.connected_account))
                .where(
                    PublishJob.status == PublishStatus.published,
                    PublishJob.external_post_id.is_not(None),
                    PublishJob.connected_account_id.is_not(None),
                    PublishJob.updated_at >= cutoff,
                )
                .order_by(PublishJob.updated_at.desc())
                .limit(batch_size)
            )
            .scalars()
            .all()
        )

        for job in jobs:
            stats["checked"] += 1
            account = job.connected_account
            if not account or not job.external_post_id:
                stats["skipped"] += 1
                continue

            try:
                metrics = fetch_metrics_for_job(account, job.external_post_id, db)
                values = {
                    "publish_job_id": job.id,
                    "provider": job.platform.value,
                    "fetched_at": datetime.now(timezone.utc),
                    "views": metrics.get("views") or 0,
                    "likes": metrics.get("likes") or 0,
                    "comments": metrics.get("comments") or 0,
                    "shares": metrics.get("shares") or 0,
                    "reach": metrics.get("reach") or 0,
                    "impressions": metrics.get("impressions") or 0,
                    "fetch_error": metrics.get("fetch_error"),
                    "raw_response": metrics.get("raw_response"),
                }
                stmt = insert(PostAnalytics).values(**values)
                update_values = {key: values[key] for key in values if key != "publish_job_id"}
                db.execute(stmt.on_conflict_do_update(index_elements=["publish_job_id"], set_=update_values))
                db.commit()
                stats["updated"] += 1
            except Exception as exc:
                db.rollback()
                stats["failed"] += 1
                logger.warning(
                    "[analytics] job refresh failed publish_job_id=%s platform=%s reason=%s",
                    job.id,
                    job.platform.value,
                    exc.__class__.__name__,
                )

    return stats
