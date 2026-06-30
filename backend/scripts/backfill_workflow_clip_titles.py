from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app.database import SyncSessionLocal
from app.models.clip import Clip
from app.models.export import Export
from app.models.social_workflow_source_post import SocialWorkflowSourcePost
from app.models.video import Video
from app.services.workflows.official_sources import (
    WORKFLOW_SOURCE_PLACEHOLDER_TITLE,
    workflow_source_clip_title,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_workflow_clip_titles")


def _candidate_rows(limit: int | None):
    stmt = (
        select(Clip, Video, SocialWorkflowSourcePost)
        .join(Video, Clip.video_id == Video.id)
        .join(Export, Export.clip_id == Clip.id)
        .join(SocialWorkflowSourcePost, SocialWorkflowSourcePost.export_id == Export.id)
        .where(Clip.title == WORKFLOW_SOURCE_PLACEHOLDER_TITLE)
        .order_by(Clip.created_at.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    with SyncSessionLocal() as db:
        return db.execute(stmt).all()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill workflow source clip titles from imported source metadata.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    rows = _candidate_rows(args.limit)
    checked = len(rows)
    updated = 0
    skipped = 0
    failed = 0

    logger.info("workflow source clips with placeholder titles: %s", checked)
    for clip, video, source_post in rows:
        try:
            next_title = workflow_source_clip_title(source_post, video)
            if not next_title or next_title == clip.title:
                skipped += 1
                continue
            if args.dry_run:
                logger.info(
                    "DRY RUN would update clip_id=%s source_post_id=%s title=%r",
                    clip.id,
                    source_post.id,
                    next_title,
                )
            else:
                with SyncSessionLocal() as db:
                    db_clip = db.get(Clip, clip.id)
                    if db_clip and db_clip.title == WORKFLOW_SOURCE_PLACEHOLDER_TITLE:
                        db_clip.title = next_title
                        db.commit()
                        logger.info("updated clip_id=%s title=%r", clip.id, next_title)
                    else:
                        skipped += 1
                        continue
            updated += 1
        except Exception as exc:
            failed += 1
            logger.warning("failed title backfill clip_id=%s source_post_id=%s error=%s", clip.id, source_post.id, exc)

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
