"""
One-time script: download existing clip thumbnails from B2 to local storage.

Run inside the backend container after deploying the local thumbnail mount:
    python scripts/backfill_thumbnails_to_local.py
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import select

from app.database import SyncSessionLocal
from app.models.clip import Clip
from app.services.object_storage import THUMBNAIL_DIR, object_storage_client


def backfill() -> None:
    with SyncSessionLocal() as db:
        clips = db.execute(select(Clip).where(Clip.thumbnail_key.is_not(None))).scalars().all()

    print(f"Found {len(clips)} clips with thumbnail_key")

    success = 0
    skipped = 0
    failed = 0

    for clip in clips:
        key = clip.thumbnail_key
        if not key:
            continue

        try:
            local_path = object_storage_client.local_thumbnail_path(key)
        except ValueError as exc:
            failed += 1
            print(f"  ERR {key}: {exc}")
            continue

        if local_path.exists():
            skipped += 1
            continue

        try:
            os.makedirs(local_path.parent, exist_ok=True)
            object_storage_client.download_file(key, str(local_path))
            success += 1
            print(f"  OK  {key}")
        except Exception as exc:
            failed += 1
            print(f"  ERR {key}: {exc}")

    print(f"\nThumbnail directory: {Path(THUMBNAIL_DIR)}")
    print(f"Done: {success} downloaded, {skipped} already existed, {failed} failed")
    if failed > max(12, int(len(clips) * 0.1)):
        print("WARNING: >10% failure rate - review errors before continuing")
        raise SystemExit(1)


if __name__ == "__main__":
    backfill()
