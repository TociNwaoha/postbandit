from __future__ import annotations

import argparse
import logging

from sqlalchemy import or_, select

from app.database import SyncSessionLocal
from app.models.clip import Clip
from app.models.export import Export
from app.models.publish_job import PublishJob
from app.models.social_workflow_source_post import SocialWorkflowSourcePost
from app.services.workflows.official_sources import (
    WORKFLOW_SOURCE_PLACEHOLDER_TITLE,
    workflow_source_clip_title,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_workflow_publish_job_titles")


def _candidate_rows(limit: int | None):
    stmt = (
        select(PublishJob, Clip, SocialWorkflowSourcePost)
        .join(Export, Export.id == PublishJob.export_id)
        .join(Clip, Clip.id == Export.clip_id)
        .join(SocialWorkflowSourcePost, SocialWorkflowSourcePost.id == PublishJob.workflow_source_post_id)
        .where(
            PublishJob.workflow_source_post_id.is_not(None),
            or_(
                PublishJob.title == WORKFLOW_SOURCE_PLACEHOLDER_TITLE,
                PublishJob.content_title_snapshot == WORKFLOW_SOURCE_PLACEHOLDER_TITLE,
            ),
        )
        .order_by(PublishJob.created_at.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    with SyncSessionLocal() as db:
        return db.execute(stmt).all()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill workflow publish-job titles from source metadata.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    rows = _candidate_rows(args.limit)
    checked = len(rows)
    updated = 0
    skipped = 0
    failed = 0

    logger.info("workflow publish jobs with placeholder titles: %s", checked)
    for publish_job, clip, source_post in rows:
        try:
            next_title = clip.title if clip.title and clip.title != WORKFLOW_SOURCE_PLACEHOLDER_TITLE else workflow_source_clip_title(source_post)
            if not next_title or next_title == WORKFLOW_SOURCE_PLACEHOLDER_TITLE:
                skipped += 1
                continue
            if args.dry_run:
                logger.info("DRY RUN would update publish_job_id=%s title=%r", publish_job.id, next_title)
            else:
                with SyncSessionLocal() as db:
                    db_job = db.get(PublishJob, publish_job.id)
                    if not db_job:
                        skipped += 1
                        continue
                    changed = False
                    if db_job.title == WORKFLOW_SOURCE_PLACEHOLDER_TITLE:
                        db_job.title = next_title[:500]
                        changed = True
                    if db_job.content_title_snapshot == WORKFLOW_SOURCE_PLACEHOLDER_TITLE:
                        db_job.content_title_snapshot = next_title[:500]
                        changed = True
                    if changed:
                        db.commit()
                        logger.info("updated publish_job_id=%s title=%r", publish_job.id, next_title)
                    else:
                        skipped += 1
                        continue
            updated += 1
        except Exception as exc:
            failed += 1
            logger.warning("failed publish-job title backfill publish_job_id=%s error=%s", publish_job.id, exc)

    print(
        "summary "
        f"checked={checked} "
        f"updated={'would_update' if args.dry_run else updated} "
        f"skipped={skipped} "
        f"failed={failed} "
        f"dry_run={args.dry_run}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
