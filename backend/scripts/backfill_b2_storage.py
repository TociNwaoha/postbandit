from __future__ import annotations

import argparse
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_b2_storage")

JSON_STORAGE_KEY_NAMES = {
    "editor_preview_key",
    "editor_preview_source_key",
    "preview_key",
    "source_key",
}


@dataclass(frozen=True)
class KeyRef:
    key: str
    source: str


@dataclass
class Summary:
    rows_checked: int = 0
    keys_checked: int = 0
    uploaded: int = 0
    already_present: int = 0
    skipped_missing: int = 0
    failed: int = 0
    deleted_local: int = 0


def _clean_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip().lstrip("/")
    if not key:
        return None
    return key


def _json_key_refs(value: Any, *, source: str) -> Iterable[KeyRef]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in JSON_STORAGE_KEY_NAMES:
                clean = _clean_key(item)
                if clean:
                    yield KeyRef(clean, f"{source}.{key}")
            yield from _json_key_refs(item, source=source)
    elif isinstance(value, list):
        for item in value:
            yield from _json_key_refs(item, source=source)


def collect_key_refs() -> tuple[list[KeyRef], int]:
    from sqlalchemy import select

    from app.database import SyncSessionLocal
    from app.models.carousel_export import CarouselExport
    from app.models.clip import Clip
    from app.models.clip_overlay_asset import ClipOverlayAsset
    from app.models.editor_asset import EditorAsset
    from app.models.editor_project import EditorProject
    from app.models.editor_render import EditorRender
    from app.models.export import Export
    from app.models.video import Video

    refs: list[KeyRef] = []
    rows_checked = 0
    with SyncSessionLocal() as db:
        videos = db.execute(select(Video)).scalars().all()
        rows_checked += len(videos)
        for video in videos:
            if video.storage_key:
                refs.append(KeyRef(video.storage_key, f"videos:{video.id}.storage_key"))
            refs.append(KeyRef(f"transcripts/{video.id}/transcript.json", f"videos:{video.id}.transcript"))
            refs.extend(_json_key_refs(video.external_metadata_json or {}, source=f"videos:{video.id}.external_metadata_json"))

        clips = db.execute(select(Clip)).scalars().all()
        rows_checked += len(clips)
        refs.extend(
            KeyRef(clip.thumbnail_key, f"clips:{clip.id}.thumbnail_key")
            for clip in clips
            if clip.thumbnail_key
        )

        exports = db.execute(select(Export)).scalars().all()
        rows_checked += len(exports)
        for export in exports:
            if export.storage_key:
                refs.append(KeyRef(export.storage_key, f"exports:{export.id}.storage_key"))
            if export.srt_key:
                refs.append(KeyRef(export.srt_key, f"exports:{export.id}.srt_key"))

        carousel_exports = db.execute(select(CarouselExport)).scalars().all()
        rows_checked += len(carousel_exports)
        for carousel_export in carousel_exports:
            for key in carousel_export.slide_keys_json or []:
                clean = _clean_key(key)
                if clean:
                    refs.append(KeyRef(clean, f"carousel_exports:{carousel_export.id}.slide_keys_json"))
            refs.append(KeyRef(carousel_export.zip_key, f"carousel_exports:{carousel_export.id}.zip_key"))
            refs.append(KeyRef(carousel_export.preview_key, f"carousel_exports:{carousel_export.id}.preview_key"))

        editor_assets = db.execute(select(EditorAsset)).scalars().all()
        rows_checked += len(editor_assets)
        refs.extend(
            KeyRef(asset.storage_key, f"editor_assets:{asset.id}.storage_key")
            for asset in editor_assets
            if asset.storage_key
        )

        editor_renders = db.execute(select(EditorRender)).scalars().all()
        rows_checked += len(editor_renders)
        refs.extend(
            KeyRef(render.output_storage_key, f"editor_renders:{render.id}.output_storage_key")
            for render in editor_renders
            if render.output_storage_key
        )

        overlay_assets = db.execute(select(ClipOverlayAsset)).scalars().all()
        rows_checked += len(overlay_assets)
        refs.extend(
            KeyRef(asset.storage_key, f"clip_overlay_assets:{asset.id}.storage_key")
            for asset in overlay_assets
            if asset.storage_key
        )

        editor_projects = db.execute(select(EditorProject)).scalars().all()
        rows_checked += len(editor_projects)
        for project in editor_projects:
            refs.extend(_json_key_refs(project.project_json or {}, source=f"editor_projects:{project.id}.project_json"))

    return refs, rows_checked


def dedupe_refs(refs: Iterable[KeyRef]) -> list[KeyRef]:
    seen: set[str] = set()
    deduped: list[KeyRef] = []
    for ref in refs:
        clean = _clean_key(ref.key)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        deduped.append(KeyRef(clean, ref.source))
    return deduped


def backfill(*, dry_run: bool) -> Summary:
    from app.services.object_storage import object_storage_client

    if not dry_run and not object_storage_client.configured:
        raise RuntimeError("Backblaze B2 storage is not configured; refusing to run non-dry-run backfill.")

    refs, rows_checked = collect_key_refs()
    deduped = dedupe_refs(refs)
    summary = Summary(rows_checked=rows_checked, keys_checked=len(deduped))

    for ref in deduped:
        try:
            local_path = object_storage_client.local_fallback_path(ref.key)
        except ValueError as exc:
            logger.warning("skip invalid key source=%s key=%s error=%s", ref.source, ref.key, exc)
            summary.failed += 1
            continue

        if not local_path.exists() or not local_path.is_file():
            logger.info("skip missing source=%s key=%s", ref.source, ref.key)
            summary.skipped_missing += 1
            continue

        local_size = local_path.stat().st_size
        if dry_run:
            logger.info("would upload source=%s key=%s size=%s", ref.source, ref.key, local_size)
            continue

        remote_size = object_storage_client.remote_file_size(ref.key)
        if remote_size == local_size:
            logger.info("already present source=%s key=%s size=%s", ref.source, ref.key, local_size)
            summary.already_present += 1
            if object_storage_client.delete_local_fallback_file(ref.key):
                summary.deleted_local += 1
            continue

        logger.info("upload source=%s key=%s size=%s", ref.source, ref.key, local_size)
        try:
            object_storage_client.upload_file(str(local_path), ref.key)
            verified_size = object_storage_client.remote_file_size(ref.key)
            if verified_size != local_size:
                logger.error(
                    "size mismatch key=%s local_size=%s remote_size=%s",
                    ref.key,
                    local_size,
                    verified_size,
                )
                summary.failed += 1
                continue
            object_storage_client.delete_local_fallback_file(ref.key)
            summary.uploaded += 1
            summary.deleted_local += 1
        except Exception as exc:
            logger.exception("failed key=%s source=%s error=%s", ref.key, ref.source, exc)
            summary.failed += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill local ClipBandit storage files into Backblaze B2.")
    parser.add_argument("--dry-run", action="store_true", help="Report actions without uploading or deleting files.")
    args = parser.parse_args()

    summary = backfill(dry_run=args.dry_run)
    print(
        "summary "
        f"dry_run={args.dry_run} "
        f"rows_checked={summary.rows_checked} "
        f"keys_checked={summary.keys_checked} "
        f"uploaded={summary.uploaded} "
        f"already_present={summary.already_present} "
        f"skipped_missing={summary.skipped_missing} "
        f"failed={summary.failed} "
        f"deleted_local={summary.deleted_local}"
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
