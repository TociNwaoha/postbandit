from __future__ import annotations

import argparse
import logging
import tempfile
from pathlib import Path

from sqlalchemy import select

from app.database import SyncSessionLocal
from app.models.clip import Clip
from app.models.export import Export
from app.models.social_workflow_source_post import SocialWorkflowSourcePost
from app.models.video import Video
from app.services.ffmpeg import extract_thumbnail
from app.services.object_storage import object_storage_client
from app.services.storage import clip_thumbnail_key

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_workflow_clip_thumbnails")


def _candidate_rows(limit: int | None):
    stmt = (
        select(Clip, Video, SocialWorkflowSourcePost)
        .join(Video, Clip.video_id == Video.id)
        .join(Export, Export.clip_id == Clip.id)
        .join(SocialWorkflowSourcePost, SocialWorkflowSourcePost.export_id == Export.id)
        .where(Clip.thumbnail_key.is_(None), Video.storage_key.is_not(None))
        .order_by(Clip.created_at.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    with SyncSessionLocal() as db:
        return db.execute(stmt).all()


def _timestamps(clip: Clip) -> list[float]:
    start = float(clip.start_time or 0.0)
    end = float(clip.end_time or start)
    duration = max(end - start, 0.0)
    offsets = [
        min(max(duration * 0.12, 0.25), max(duration - 0.25, 0.25)),
        min(max(duration * 0.5, 0.25), max(duration - 0.25, 0.25)),
        0.0,
    ]
    seen: set[float] = set()
    values: list[float] = []
    for offset in offsets:
        timestamp = round(start + max(offset, 0.0), 3)
        if timestamp not in seen:
            seen.add(timestamp)
            values.append(timestamp)
    return values


def _generate_thumbnail(clip: Clip, video: Video, dry_run: bool) -> str | None:
    if not video.storage_key:
        return None
    key = clip_thumbnail_key(str(video.user_id), str(video.id), str(clip.id))
    if dry_run:
        logger.info("DRY RUN would generate clip_id=%s key=%s", clip.id, key)
        return key

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"clipbandit-thumb-backfill-{clip.id}-"))
    source_path = tmp_dir / "source.mp4"
    thumb_path = tmp_dir / "thumbnail.jpg"
    try:
        object_storage_client.download_file(video.storage_key, str(source_path))
        last_error: Exception | None = None
        for timestamp in _timestamps(clip):
            try:
                extract_thumbnail(str(source_path), str(thumb_path), timestamp)
                object_storage_client.upload_file(str(thumb_path), key)
                return key
            except Exception as exc:
                last_error = exc
                logger.warning("thumbnail attempt failed clip_id=%s ts=%s error=%s", clip.id, timestamp, exc)
        if last_error:
            raise last_error
        return None
    finally:
        for path in (source_path, thumb_path):
            path.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing thumbnails for workflow source clips.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    rows = _candidate_rows(args.limit)
    checked = len(rows)
    generated = 0
    failed = 0

    logger.info("workflow clips needing thumbnails: %s", checked)
    for clip, video, source_post in rows:
        try:
            key = _generate_thumbnail(clip, video, args.dry_run)
            if key and not args.dry_run:
                with SyncSessionLocal() as db:
                    db_clip = db.get(Clip, clip.id)
                    if db_clip and not db_clip.thumbnail_key:
                        db_clip.thumbnail_key = key
                        db.commit()
                logger.info("generated thumbnail clip_id=%s source_post_id=%s key=%s", clip.id, source_post.id, key)
            generated += 1 if key else 0
        except Exception as exc:
            failed += 1
            logger.warning("failed thumbnail backfill clip_id=%s source_post_id=%s error=%s", clip.id, source_post.id, exc)

    print(
        "summary "
        f"checked={checked} "
        f"generated={'would_generate' if args.dry_run else generated} "
        f"failed={failed} "
        f"dry_run={args.dry_run}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
