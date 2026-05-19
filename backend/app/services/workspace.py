from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any
import uuid

import redis

from app.config import settings

logger = logging.getLogger(__name__)

WORKSPACE_ROOTS = {
    "ingest": Path("/tmp/clipbandit"),
    "transcribe": Path("/tmp/clipbandit"),
    "score": Path("/tmp/clipbandit-score"),
    "render": Path("/tmp/clipbandit-render"),
    "publish": Path("/tmp/clipbandit-publish"),
}
MANIFEST_FILENAME = "workspace_manifest.json"
LEASE_PREFIX = "workspace:lease"


@dataclass
class WorkspaceLease:
    job_type: str
    workspace_key: str
    path: Path
    lease_id: str


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _lease_key(lease_id: str) -> str:
    return f"{LEASE_PREFIX}:{lease_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_workspace_path(job_type: str, workspace_key: str) -> Path:
    if job_type not in WORKSPACE_ROOTS:
        raise ValueError(f"Unsupported workspace job_type: {job_type}")
    root = WORKSPACE_ROOTS[job_type]
    root.mkdir(parents=True, exist_ok=True)
    target = (root / workspace_key).resolve()
    safe_root = root.resolve()
    if target == safe_root or safe_root not in target.parents:
        raise ValueError("Invalid workspace path")
    return target


def start_workspace(
    *,
    job_type: str,
    workspace_key: str,
    video_id: str | None = None,
    user_id: str | None = None,
    expected_paths: list[str] | None = None,
    refs: dict[str, Any] | None = None,
) -> WorkspaceLease:
    path = _safe_workspace_path(job_type, workspace_key)
    path.mkdir(parents=True, exist_ok=True)
    lease_id = uuid.uuid4().hex
    manifest = {
        "job_type": job_type,
        "workspace_key": workspace_key,
        "video_id": video_id,
        "user_id": user_id,
        "created_at": _now_iso(),
        "last_heartbeat_at": _now_iso(),
        "state": "active",
        "expected_paths": expected_paths or [],
        "bytes_written": 0,
        "lease_id": lease_id,
        "refs": refs or {},
    }
    _write_manifest(path, manifest)
    touch_workspace_lease(lease_id)
    return WorkspaceLease(job_type=job_type, workspace_key=workspace_key, path=path, lease_id=lease_id)


def touch_workspace_lease(lease_id: str) -> None:
    ttl = max(60, int(settings.workspace_lease_ttl_seconds))
    client = _redis_client()
    try:
        client.set(_lease_key(lease_id), _now_iso(), ex=ttl)
    finally:
        client.close()


def release_workspace_lease(lease_id: str) -> None:
    client = _redis_client()
    try:
        client.delete(_lease_key(lease_id))
    finally:
        client.close()


def is_workspace_lease_active(lease_id: str) -> bool:
    if not lease_id:
        return False
    client = _redis_client()
    try:
        return bool(client.exists(_lease_key(lease_id)))
    finally:
        client.close()


def finalize_workspace(
    lease: WorkspaceLease,
    *,
    state: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    manifest = read_workspace_manifest(lease.path) or {}
    manifest["state"] = state
    manifest["last_heartbeat_at"] = _now_iso()
    manifest["bytes_written"] = _dir_size_bytes(lease.path)
    if metadata:
        manifest.setdefault("metadata", {}).update(metadata)
    _write_manifest(lease.path, manifest)
    release_workspace_lease(lease.lease_id)


def heartbeat_workspace(lease: WorkspaceLease) -> None:
    manifest = read_workspace_manifest(lease.path)
    if manifest is not None:
        manifest["last_heartbeat_at"] = _now_iso()
        _write_manifest(lease.path, manifest)
    touch_workspace_lease(lease.lease_id)


def read_workspace_manifest(path: Path) -> dict[str, Any] | None:
    manifest_path = path / MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[workspace] invalid manifest path=%s error=%s", manifest_path, exc)
        return None


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    manifest_path = path / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total

