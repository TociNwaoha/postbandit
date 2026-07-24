"""Regenerate existing clip thumbnails with caption text."""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import SyncSessionLocal
from app.models.clip import Clip
from app.models.video import Video
from app.services.object_storage import object_storage_client
from app.worker.tasks.score import generate_thumbnail_with_caption, get_thumbnail_caption_words


def _timestamp_for_clip(clip: Clip) -> float:
    clip_start = max(float(clip.start_time or 0), 0.0)
    clip_end = max(float(clip.end_time or clip_start), clip_start)
    duration = max(clip_end - clip_start, 0.0)
    return clip_start + min(1.0, duration * 0.15)


def _load_clips(limit: int | None = None) -> list[Clip]:
    statement = (
        select(Clip)
        .options(joinedload(Clip.video))
        .where(Clip.thumbnail_key.is_not(None))
        .order_by(Clip.created_at.desc())
    )
    if limit:
        statement = statement.limit(limit)

    with SyncSessionLocal() as db:
        return list(db.execute(statement).scalars().all())


def backfill(*, limit: int | None = None) -> dict[str, int]:
    clips = _load_clips(limit=limit)
    print(f"Found {len(clips)} clips with thumbnail_key")

    stats = {
        "updated": 0,
        "skipped_no_source": 0,
        "skipped_no_transcript": 0,
        "failed": 0,
    }

    clips_by_video: dict[UUID, list[Clip]] = defaultdict(list)
    for clip in clips:
        if not clip.video_id:
            stats["skipped_no_source"] += 1
            continue
        clips_by_video[clip.video_id].append(clip)

    with tempfile.TemporaryDirectory(prefix="caption-thumb-backfill-") as tmp_root:
        tmp_dir = Path(tmp_root)

        for video_id, video_clips in clips_by_video.items():
            video: Video | None = video_clips[0].video
            if not video or not video.storage_key:
                stats["skipped_no_source"] += len(video_clips)
                print(f"SKIP video={video_id} missing source storage key ({len(video_clips)} clips)")
                continue

            source_path = tmp_dir / f"{video_id}.mp4"
            try:
                object_storage_client.download_file(video.storage_key, str(source_path))
            except Exception as exc:
                stats["skipped_no_source"] += len(video_clips)
                print(f"SKIP video={video_id} source unavailable: {exc}")
                continue

            for clip in video_clips:
                if not clip.thumbnail_key:
                    stats["skipped_no_source"] += 1
                    continue

                local_thumb = object_storage_client.local_thumbnail_path(clip.thumbnail_key)
                if not local_thumb.exists():
                    stats["skipped_no_source"] += 1
                    print(f"  SKIP no local thumbnail clip={clip.id}")
                    continue

                line1, line2 = get_thumbnail_caption_words(clip)
                if not line1:
                    stats["skipped_no_transcript"] += 1
                    print(f"  SKIP no caption words clip={clip.id}")
                    continue

                ok = generate_thumbnail_with_caption(
                    source_path=str(source_path),
                    thumbnail_path=str(local_thumb),
                    timestamp=_timestamp_for_clip(clip),
                    line1=line1,
                    line2=line2,
                )
                if ok:
                    stats["updated"] += 1
                    print(f"  OK  clip={clip.id} caption='{line1} / {line2}'")
                else:
                    stats["failed"] += 1
                    print(f"  ERR clip={clip.id}")

            source_path.unlink(missing_ok=True)

    attempted = stats["updated"] + stats["failed"]
    if attempted and (stats["failed"] / attempted) > 0.2:
        raise SystemExit(f"Backfill failure rate exceeded 20%: {stats['failed']} failed of {attempted} attempted")

    print(
        "\nDone: {updated} updated, {skipped_no_source} skipped (no source), "
        "{skipped_no_transcript} skipped (no transcript), {failed} failed".format(**stats)
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate clip thumbnails with burned-in caption text.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of clips to process.")
    args = parser.parse_args()
    backfill(limit=args.limit)


if __name__ == "__main__":
    main()
