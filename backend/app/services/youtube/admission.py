from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import shutil
from pathlib import Path

from sqlalchemy import func, select

from app.config import settings
from app.models.job import Job, JobStatus
from app.models.video import Video, VideoImportState, VideoSourceType
from app.services.youtube import ACTIVE_IMPORT_STATES
from app.services.r2 import LOCAL_STORAGE_ROOT


@dataclass(frozen=True)
class AdmissionSnapshot:
    free_disk_bytes: int
    free_disk_gb: float
    active_user_imports: int
    active_global_imports: int
    ingest_queue_depth: int
    user_window_count: int


@dataclass(frozen=True)
class AdmissionDecision:
    mode: str
    allow: bool
    reasons: list[str]
    snapshot: AdmissionSnapshot


def _youtube_source_types() -> tuple[VideoSourceType, ...]:
    return (
        VideoSourceType.youtube,
        VideoSourceType.youtube_single,
        VideoSourceType.youtube_playlist,
    )


async def evaluate_youtube_admission(db, *, user_id) -> AdmissionDecision:
    mode = (settings.youtube_import_admission_mode or "warn").strip().lower()
    if mode not in {"off", "warn", "enforce"}:
        mode = "warn"

    storage_path = Path(settings.youtube_import_admission_storage_path or str(LOCAL_STORAGE_ROOT))
    usage = shutil.disk_usage(storage_path)
    free_disk_bytes = int(usage.free)
    free_disk_gb = free_disk_bytes / (1024**3)

    active_user_imports = int(
        (
            await db.execute(
                select(func.count(Video.id)).where(
                    Video.user_id == user_id,
                    Video.source_type.in_(_youtube_source_types()),
                    Video.import_state.in_(list(ACTIVE_IMPORT_STATES)),
                )
            )
        ).scalar_one()
        or 0
    )

    active_global_imports = int(
        (
            await db.execute(
                select(func.count(Video.id)).where(
                    Video.source_type.in_(_youtube_source_types()),
                    Video.import_state.in_(list(ACTIVE_IMPORT_STATES)),
                )
            )
        ).scalar_one()
        or 0
    )

    ingest_queue_depth = int(
        (
            await db.execute(
                select(func.count(Job.id)).where(
                    Job.type == "ingest",
                    Job.status.in_([JobStatus.queued, JobStatus.running]),
                )
            )
        ).scalar_one()
        or 0
    )

    window_start = datetime.now(timezone.utc) - timedelta(hours=1)
    user_window_count = int(
        (
            await db.execute(
                select(func.count(Video.id)).where(
                    Video.user_id == user_id,
                    Video.source_type.in_(_youtube_source_types()),
                    Video.created_at >= window_start,
                )
            )
        ).scalar_one()
        or 0
    )

    reasons: list[str] = []
    if free_disk_gb < float(settings.youtube_import_min_free_disk_gb):
        reasons.append("low_free_disk")
    if active_user_imports >= int(settings.youtube_import_max_active_per_user):
        reasons.append("per_user_active_limit")
    if active_global_imports >= int(settings.youtube_import_max_active_global):
        reasons.append("global_active_limit")
    if ingest_queue_depth >= int(settings.youtube_import_max_ingest_queue_depth):
        reasons.append("ingest_queue_depth_limit")
    if user_window_count >= int(settings.youtube_import_rate_limit_per_hour):
        reasons.append("per_user_rate_limit")

    snapshot = AdmissionSnapshot(
        free_disk_bytes=free_disk_bytes,
        free_disk_gb=round(free_disk_gb, 2),
        active_user_imports=active_user_imports,
        active_global_imports=active_global_imports,
        ingest_queue_depth=ingest_queue_depth,
        user_window_count=user_window_count,
    )
    if mode == "off":
        return AdmissionDecision(mode=mode, allow=True, reasons=[], snapshot=snapshot)

    allow = len(reasons) == 0 or mode == "warn"
    return AdmissionDecision(mode=mode, allow=allow, reasons=reasons, snapshot=snapshot)

