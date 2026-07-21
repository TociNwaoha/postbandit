from __future__ import annotations

import json
import logging
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.object_storage import object_storage_client
from app.services.workspace import finalize_workspace, heartbeat_workspace, start_workspace

logger = logging.getLogger(__name__)

EDITOR_PREVIEW_KEY = "editor_preview_key"
EDITOR_PREVIEW_STATUS_KEY = "editor_preview_status"
EDITOR_PREVIEW_ERROR_KEY = "editor_preview_error"
EDITOR_PREVIEW_SOURCE_KEY = "editor_preview_source_key"
EDITOR_PREVIEW_ENQUEUED_AT_KEY = "editor_preview_enqueued_at"
EDITOR_PREVIEW_UPDATED_AT_KEY = "editor_preview_updated_at"
EDITOR_PREVIEW_PROFILE_VERSION_KEY = "editor_preview_profile_version"
EDITOR_PREVIEW_PROFILE_VERSION = 2

EDITOR_PREVIEW_STATUS_PENDING = "pending"
EDITOR_PREVIEW_STATUS_READY = "ready"
EDITOR_PREVIEW_STATUS_FAILED = "failed"
EDITOR_PREVIEW_FAILED_RETRY_AFTER = timedelta(hours=6)

HDR_COLOR_SPACES = {"bt2020", "bt2020nc", "bt2020ncl"}
HDR_COLOR_TRANSFERS = {"arib-std-b67", "smpte2084", "pq"}
HDR_PRIMARIES = {"bt2020"}


@dataclass
class EditorPreviewResult:
    preview_key: str
    used_proxy: bool
    command_debug: str
    source_profile: str


class EditorPreviewError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def build_editor_preview_key(video_id: str) -> str:
    return f"uploads/{video_id}/editor_preview_720sdr.mp4"


def parse_editor_preview_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(metadata or {})
    status = payload.get(EDITOR_PREVIEW_STATUS_KEY)
    if status not in {EDITOR_PREVIEW_STATUS_PENDING, EDITOR_PREVIEW_STATUS_READY, EDITOR_PREVIEW_STATUS_FAILED}:
        status = None
    key = payload.get(EDITOR_PREVIEW_KEY)
    if not isinstance(key, str) or not key.strip():
        key = None
    source_key = payload.get(EDITOR_PREVIEW_SOURCE_KEY)
    if not isinstance(source_key, str) or not source_key.strip():
        source_key = None
    error = payload.get(EDITOR_PREVIEW_ERROR_KEY)
    if not isinstance(error, str):
        error = None
    profile_version = payload.get(EDITOR_PREVIEW_PROFILE_VERSION_KEY)
    if not isinstance(profile_version, int):
        profile_version = None
    updated_at = _parse_iso(payload.get(EDITOR_PREVIEW_UPDATED_AT_KEY))
    return {
        "status": status,
        "key": key,
        "source_key": source_key,
        "error": error,
        "profile_version": profile_version,
        "updated_at": updated_at,
    }


def mark_editor_preview_pending(metadata: dict[str, Any] | None, *, source_key: str) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload[EDITOR_PREVIEW_STATUS_KEY] = EDITOR_PREVIEW_STATUS_PENDING
    payload[EDITOR_PREVIEW_SOURCE_KEY] = source_key
    payload[EDITOR_PREVIEW_ENQUEUED_AT_KEY] = _now_iso()
    payload[EDITOR_PREVIEW_UPDATED_AT_KEY] = _now_iso()
    payload[EDITOR_PREVIEW_PROFILE_VERSION_KEY] = EDITOR_PREVIEW_PROFILE_VERSION
    payload.pop(EDITOR_PREVIEW_KEY, None)
    payload.pop(EDITOR_PREVIEW_ERROR_KEY, None)
    return payload


def mark_editor_preview_ready(
    metadata: dict[str, Any] | None,
    *,
    source_key: str,
    preview_key: str,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload[EDITOR_PREVIEW_STATUS_KEY] = EDITOR_PREVIEW_STATUS_READY
    payload[EDITOR_PREVIEW_SOURCE_KEY] = source_key
    payload[EDITOR_PREVIEW_KEY] = preview_key
    payload[EDITOR_PREVIEW_UPDATED_AT_KEY] = _now_iso()
    payload[EDITOR_PREVIEW_PROFILE_VERSION_KEY] = EDITOR_PREVIEW_PROFILE_VERSION
    payload.pop(EDITOR_PREVIEW_ERROR_KEY, None)
    return payload


def mark_editor_preview_failed(
    metadata: dict[str, Any] | None,
    *,
    source_key: str,
    error: str,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload[EDITOR_PREVIEW_STATUS_KEY] = EDITOR_PREVIEW_STATUS_FAILED
    payload[EDITOR_PREVIEW_SOURCE_KEY] = source_key
    payload[EDITOR_PREVIEW_ERROR_KEY] = error[:1000]
    payload[EDITOR_PREVIEW_UPDATED_AT_KEY] = _now_iso()
    payload[EDITOR_PREVIEW_PROFILE_VERSION_KEY] = EDITOR_PREVIEW_PROFILE_VERSION
    return payload


def should_enqueue_editor_preview(
    *,
    storage_key: str | None,
    metadata: dict[str, Any] | None,
) -> bool:
    if not storage_key:
        return False
    preview = parse_editor_preview_metadata(metadata)
    source_key = preview["source_key"]
    status = preview["status"]
    key = preview["key"]
    profile_version = preview["profile_version"]

    if source_key != storage_key:
        return True
    if profile_version != EDITOR_PREVIEW_PROFILE_VERSION:
        return True
    if status == EDITOR_PREVIEW_STATUS_PENDING:
        return False
    if status == EDITOR_PREVIEW_STATUS_READY and key:
        # Old rows may have preview_key==source_key from prior behavior.
        # Treat those as stale so we generate a deterministic editor-safe proxy.
        if key == storage_key:
            return True
        return not object_storage_client.file_exists(key)
    if status == EDITOR_PREVIEW_STATUS_FAILED:
        updated_at = preview.get("updated_at")
        if isinstance(updated_at, datetime):
            return datetime.now(timezone.utc) - updated_at >= EDITOR_PREVIEW_FAILED_RETRY_AFTER
        return False
    return True


def resolve_editor_preview_download_key(
    *,
    storage_key: str | None,
    metadata: dict[str, Any] | None,
) -> str | None:
    if not storage_key:
        return None
    preview = parse_editor_preview_metadata(metadata)
    if preview["status"] != EDITOR_PREVIEW_STATUS_READY:
        return None
    if preview["source_key"] != storage_key:
        return None
    key = preview["key"]
    if not key:
        return None
    if key == storage_key:
        return None
    if not object_storage_client.file_exists(key):
        return None
    return key


def _probe_video_stream(video_path: Path) -> dict[str, str]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,pix_fmt,color_space,color_transfer,color_primaries",
        str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise EditorPreviewError(f"ffprobe failed: {(proc.stderr or proc.stdout or '').strip()[:300]}")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise EditorPreviewError(f"Unable to parse ffprobe output: {exc}") from exc
    streams = payload.get("streams") or []
    if not streams:
        raise EditorPreviewError("No video stream found in source")
    stream = streams[0] or {}
    return {
        "codec_name": str(stream.get("codec_name") or "").lower(),
        "pix_fmt": str(stream.get("pix_fmt") or "").lower(),
        "color_space": str(stream.get("color_space") or "").lower(),
        "color_transfer": str(stream.get("color_transfer") or "").lower(),
        "color_primaries": str(stream.get("color_primaries") or "").lower(),
    }


def _needs_proxy(stream: dict[str, str]) -> tuple[bool, str]:
    codec = stream.get("codec_name", "")
    pix_fmt = stream.get("pix_fmt", "")
    color_space = stream.get("color_space", "")
    color_transfer = stream.get("color_transfer", "")
    color_primaries = stream.get("color_primaries", "")

    reasons: list[str] = []
    if codec != "h264":
        reasons.append(f"codec={codec or 'unknown'}")
    if pix_fmt != "yuv420p":
        reasons.append(f"pix_fmt={pix_fmt or 'unknown'}")
    if color_transfer in HDR_COLOR_TRANSFERS:
        reasons.append(f"transfer={color_transfer}")
    if color_space in HDR_COLOR_SPACES:
        reasons.append(f"space={color_space}")
    if color_primaries in HDR_PRIMARIES:
        reasons.append(f"primaries={color_primaries}")

    return bool(reasons), ",".join(reasons) if reasons else "already_compatible"


def _sdr_filter_chain_fallback() -> str:
    return "scale='min(720,iw)':-2:flags=lanczos,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"


def _hdr_to_sdr_filter_chain(*, stream: dict[str, str]) -> str:
    transfer_in = stream.get("color_transfer") or "arib-std-b67"
    matrix_in = stream.get("color_space") or "bt2020nc"
    primaries_in = stream.get("color_primaries") or "bt2020"
    # Convert HDR/HLG content to SDR BT.709 for deterministic browser playback.
    return (
        f"zscale=tin={transfer_in}:min={matrix_in}:pin={primaries_in}:rin=tv:t=linear:npl=100,"
        "format=gbrpf32le,"
        "tonemap=tonemap=hable:desat=0,"
        "zscale=t=bt709:m=bt709:p=bt709:r=tv,"
        "scale='min(720,iw)':-2:flags=lanczos,"
        "format=yuv420p"
    )


def _can_use_fast_sdr_retag(stream: dict[str, str]) -> bool:
    # Some phone/browser exports are H.264 yuv420p but carry BT.2020/HLG tags.
    # Full tonemap is too slow for long sources; editor preview only needs stable,
    # browser-visible frames, so retag/downscale these quickly to BT.709.
    return stream.get("codec_name") == "h264" and stream.get("pix_fmt") == "yuv420p"


def _build_proxy_command(*, source_path: Path, output_path: Path, stream: dict[str, str], hdr_like: bool) -> list[str]:
    # Keep proxy generation fast for long-form media. We retag output to BT.709
    # and use a browser-safe H.264/AAC profile regardless of source HDR metadata.
    use_fast_retag = _can_use_fast_sdr_retag(stream)
    vf = _hdr_to_sdr_filter_chain(stream=stream) if hdr_like and not use_fast_retag else _sdr_filter_chain_fallback()
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-vf",
        vf,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-r",
        "30",
        "-g",
        "60",
        "-keyint_min",
        "60",
        "-sc_threshold",
        "0",
        "-fps_mode",
        "cfr",
        "-pix_fmt",
        "yuv420p",
        "-x264-params",
        "colorprim=bt709:transfer=bt709:colormatrix=bt709",
        "-bsf:v",
        "filter_units=remove_types=6",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        str(output_path),
    ]
    return cmd


def generate_editor_preview_proxy(*, video_id: str, source_key: str) -> EditorPreviewResult:
    workspace = start_workspace(
        job_type="ingest",
        workspace_key=f"editor-preview-{video_id}",
        refs={"video_id": video_id, "source_key": source_key},
    )
    source_path = workspace.path / "source_input"
    output_path = workspace.path / "editor_preview_720sdr.mp4"

    try:
        object_storage_client.download_file(source_key, str(source_path))
        heartbeat_workspace(workspace)

        stream = _probe_video_stream(source_path)
        _, source_profile = _needs_proxy(stream)

        hdr_like = (
            stream.get("color_transfer") in HDR_COLOR_TRANSFERS
            or stream.get("color_space") in HDR_COLOR_SPACES
            or stream.get("color_primaries") in HDR_PRIMARIES
        )
        command = _build_proxy_command(source_path=source_path, output_path=output_path, stream=stream, hdr_like=hdr_like)
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(120, int(settings.editor_preview_proxy_timeout_seconds)),
            check=False,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout or "").strip()
            raise EditorPreviewError(f"ffmpeg preview proxy failed: {stderr[-800:]}")

        preview_key = build_editor_preview_key(video_id)
        object_storage_client.upload_file(str(output_path), preview_key)
        heartbeat_workspace(workspace)

        finalize_workspace(
            workspace,
            state="terminal_success",
            metadata={"proxy_needed": True, "preview_key": preview_key, "source_profile": source_profile},
        )
        return EditorPreviewResult(
            preview_key=preview_key,
            used_proxy=True,
            command_debug=shlex.join(command)[:2000],
            source_profile=source_profile,
        )
    except Exception:
        finalize_workspace(workspace, state="terminal_failed")
        raise
    finally:
        shutil.rmtree(workspace.path, ignore_errors=True)
