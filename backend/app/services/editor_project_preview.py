from __future__ import annotations

import json
import logging
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.clip import Clip
from app.models.editor_project import EditorProject
from app.models.video import Video
from app.services.r2 import r2_client
from app.services.workspace import finalize_workspace, heartbeat_workspace, start_workspace

logger = logging.getLogger(__name__)

PROJECT_PREVIEW_PROFILE_VERSION = 3
PROJECT_PREVIEW_HANDLE_SECONDS = 2.0

PROJECT_PREVIEW_STATUS_PENDING = "pending"
PROJECT_PREVIEW_STATUS_READY = "ready"
PROJECT_PREVIEW_STATUS_FAILED = "failed"

HDR_COLOR_SPACES = {"bt2020", "bt2020nc", "bt2020ncl"}
HDR_COLOR_TRANSFERS = {"arib-std-b67", "smpte2084", "pq"}
HDR_PRIMARIES = {"bt2020"}

PROJECT_PREVIEW_META_KEYS = {
    "editor_preview_status",
    "editor_preview_key",
    "editor_preview_source_key",
    "editor_preview_profile_version",
    "editor_preview_offset_sec",
    "editor_preview_duration_sec",
    "editor_preview_error",
    "editor_preview_enqueued_at",
    "editor_preview_updated_at",
}


@dataclass(frozen=True)
class ProjectPreviewWindow:
    offset_sec: float
    duration_sec: float


@dataclass(frozen=True)
class ProjectPreviewMetadata:
    status: str | None
    key: str | None
    source_key: str | None
    profile_version: int | None
    offset_sec: float | None
    duration_sec: float | None
    error: str | None


@dataclass(frozen=True)
class ProjectPreviewResult:
    preview_key: str
    command_debug: str
    source_profile: str
    offset_sec: float
    duration_sec: float


class ProjectPreviewError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_project_preview_key(*, user_id: str, project_id: str) -> str:
    return f"editor/{user_id}/{project_id}/preview/editor_preview_clip_720sdr_v{PROJECT_PREVIEW_PROFILE_VERSION}.mp4"


def resolve_project_preview_window(
    *,
    project: EditorProject,
    clip: Clip,
    video: Video,
) -> ProjectPreviewWindow:
    start = float(project.trim_start_sec if project.trim_start_sec is not None else clip.start_time)
    end = float(project.trim_end_sec if project.trim_end_sec is not None else clip.end_time)
    if end <= start:
        start = float(clip.start_time)
        end = float(clip.end_time)

    source_duration = float(video.duration_sec or 0)
    offset = max(0.0, start - PROJECT_PREVIEW_HANDLE_SECONDS)
    window_end = end + PROJECT_PREVIEW_HANDLE_SECONDS
    if source_duration > 0:
        window_end = min(source_duration, window_end)
    duration = max(0.25, window_end - offset)
    return ProjectPreviewWindow(offset_sec=round(offset, 3), duration_sec=round(duration, 3))


def parse_project_preview_metadata(project_json: dict[str, Any] | None) -> ProjectPreviewMetadata:
    meta = dict((project_json or {}).get("meta") or {})
    status = meta.get("editor_preview_status")
    if status not in {PROJECT_PREVIEW_STATUS_PENDING, PROJECT_PREVIEW_STATUS_READY, PROJECT_PREVIEW_STATUS_FAILED}:
        status = None

    key = meta.get("editor_preview_key")
    source_key = meta.get("editor_preview_source_key")
    error = meta.get("editor_preview_error")
    profile_version = meta.get("editor_preview_profile_version")
    offset_sec = meta.get("editor_preview_offset_sec")
    duration_sec = meta.get("editor_preview_duration_sec")

    return ProjectPreviewMetadata(
        status=status,
        key=key if isinstance(key, str) and key.strip() else None,
        source_key=source_key if isinstance(source_key, str) and source_key.strip() else None,
        profile_version=profile_version if isinstance(profile_version, int) else None,
        offset_sec=float(offset_sec) if isinstance(offset_sec, int | float) else None,
        duration_sec=float(duration_sec) if isinstance(duration_sec, int | float) else None,
        error=error if isinstance(error, str) else None,
    )


def _with_preview_meta(project_json: dict[str, Any] | None, values: dict[str, Any]) -> dict[str, Any]:
    payload = dict(project_json or {})
    meta = dict(payload.get("meta") or {})
    meta.update(values)
    payload["meta"] = meta
    return payload


def mark_project_preview_pending(
    project_json: dict[str, Any] | None,
    *,
    source_key: str,
    preview_key: str,
    window: ProjectPreviewWindow,
) -> dict[str, Any]:
    return _with_preview_meta(
        project_json,
        {
            "editor_preview_status": PROJECT_PREVIEW_STATUS_PENDING,
            "editor_preview_key": preview_key,
            "editor_preview_source_key": source_key,
            "editor_preview_profile_version": PROJECT_PREVIEW_PROFILE_VERSION,
            "editor_preview_offset_sec": window.offset_sec,
            "editor_preview_duration_sec": window.duration_sec,
            "editor_preview_enqueued_at": _now_iso(),
            "editor_preview_updated_at": _now_iso(),
            "editor_preview_error": None,
        },
    )


def mark_project_preview_ready(
    project_json: dict[str, Any] | None,
    *,
    source_key: str,
    preview_key: str,
    window: ProjectPreviewWindow,
) -> dict[str, Any]:
    return _with_preview_meta(
        project_json,
        {
            "editor_preview_status": PROJECT_PREVIEW_STATUS_READY,
            "editor_preview_key": preview_key,
            "editor_preview_source_key": source_key,
            "editor_preview_profile_version": PROJECT_PREVIEW_PROFILE_VERSION,
            "editor_preview_offset_sec": window.offset_sec,
            "editor_preview_duration_sec": window.duration_sec,
            "editor_preview_updated_at": _now_iso(),
            "editor_preview_error": None,
        },
    )


def mark_project_preview_failed(
    project_json: dict[str, Any] | None,
    *,
    source_key: str | None,
    preview_key: str | None,
    window: ProjectPreviewWindow | None,
    error: str,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "editor_preview_status": PROJECT_PREVIEW_STATUS_FAILED,
        "editor_preview_source_key": source_key,
        "editor_preview_profile_version": PROJECT_PREVIEW_PROFILE_VERSION,
        "editor_preview_updated_at": _now_iso(),
        "editor_preview_error": error[:1000],
    }
    if preview_key:
        values["editor_preview_key"] = preview_key
    if window:
        values["editor_preview_offset_sec"] = window.offset_sec
        values["editor_preview_duration_sec"] = window.duration_sec
    return _with_preview_meta(project_json, values)


def preserve_project_preview_metadata(*, current_json: dict[str, Any] | None, incoming_json: dict[str, Any]) -> dict[str, Any]:
    current_meta = dict((current_json or {}).get("meta") or {})
    server_preview_values = {key: current_meta.get(key) for key in PROJECT_PREVIEW_META_KEYS if key in current_meta}
    if not server_preview_values:
        return incoming_json
    payload = dict(incoming_json or {})
    incoming_meta = dict(payload.get("meta") or {})
    incoming_meta.update(server_preview_values)
    payload["meta"] = incoming_meta
    return payload


def should_enqueue_project_preview(
    *,
    project_json: dict[str, Any] | None,
    source_key: str | None,
    preview_key: str,
    window: ProjectPreviewWindow,
    force: bool = False,
) -> bool:
    if force:
        return True
    if not source_key:
        return False

    meta = parse_project_preview_metadata(project_json)
    if meta.source_key != source_key:
        return True
    if meta.profile_version != PROJECT_PREVIEW_PROFILE_VERSION:
        return True
    if meta.key != preview_key:
        return True
    if meta.offset_sec is None or abs(meta.offset_sec - window.offset_sec) > 0.01:
        return True
    if meta.duration_sec is None or abs(meta.duration_sec - window.duration_sec) > 0.01:
        return True
    if meta.status == PROJECT_PREVIEW_STATUS_PENDING:
        return False
    if meta.status == PROJECT_PREVIEW_STATUS_READY:
        return not r2_client.file_exists(preview_key)
    if meta.status == PROJECT_PREVIEW_STATUS_FAILED:
        return False
    return True


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
        raise ProjectPreviewError(f"ffprobe failed: {(proc.stderr or proc.stdout or '').strip()[:300]}")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ProjectPreviewError(f"Unable to parse ffprobe output: {exc}") from exc
    streams = payload.get("streams") or []
    if not streams:
        raise ProjectPreviewError("No video stream found in source")
    stream = streams[0] or {}
    return {
        "codec_name": str(stream.get("codec_name") or "").lower(),
        "pix_fmt": str(stream.get("pix_fmt") or "").lower(),
        "color_space": str(stream.get("color_space") or "").lower(),
        "color_transfer": str(stream.get("color_transfer") or "").lower(),
        "color_primaries": str(stream.get("color_primaries") or "").lower(),
    }


def _source_profile(stream: dict[str, str]) -> str:
    return ",".join(
        [
            f"codec={stream.get('codec_name') or 'unknown'}",
            f"pix_fmt={stream.get('pix_fmt') or 'unknown'}",
            f"space={stream.get('color_space') or 'unknown'}",
            f"transfer={stream.get('color_transfer') or 'unknown'}",
            f"primaries={stream.get('color_primaries') or 'unknown'}",
        ]
    )


def _hdr_like(stream: dict[str, str]) -> bool:
    return (
        stream.get("color_transfer") in HDR_COLOR_TRANSFERS
        or stream.get("color_space") in HDR_COLOR_SPACES
        or stream.get("color_primaries") in HDR_PRIMARIES
    )


def _sdr_filter_chain() -> str:
    return "scale='min(720,iw)':-2:flags=lanczos,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"


def _hdr_to_sdr_filter_chain(*, stream: dict[str, str]) -> str:
    transfer_in = stream.get("color_transfer") or "arib-std-b67"
    matrix_in = stream.get("color_space") or "bt2020nc"
    primaries_in = stream.get("color_primaries") or "bt2020"
    return (
        f"zscale=tin={transfer_in}:min={matrix_in}:pin={primaries_in}:rin=tv:t=linear:npl=100,"
        "format=gbrpf32le,"
        "tonemap=tonemap=hable:desat=0,"
        "zscale=t=bt709:m=bt709:p=bt709:r=tv,"
        "scale='min(720,iw)':-2:flags=lanczos,"
        "format=yuv420p"
    )


def _build_clip_proxy_command(
    *,
    source_path: Path,
    output_path: Path,
    stream: dict[str, str],
    window: ProjectPreviewWindow,
) -> list[str]:
    vf = _hdr_to_sdr_filter_chain(stream=stream) if _hdr_like(stream) else _sdr_filter_chain()
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{window.offset_sec:.3f}",
        "-i",
        str(source_path),
        "-t",
        f"{window.duration_sec:.3f}",
        "-vf",
        vf,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
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


def generate_project_preview_proxy(
    *,
    project_id: str,
    user_id: str,
    source_key: str,
    window: ProjectPreviewWindow,
) -> ProjectPreviewResult:
    workspace = start_workspace(
        job_type="ingest",
        workspace_key=f"editor-project-preview-{project_id}",
        refs={"project_id": project_id, "source_key": source_key},
    )
    source_path = workspace.path / "source_input"
    output_path = workspace.path / "editor_preview_clip_720sdr.mp4"

    try:
        r2_client.download_file(source_key, str(source_path))
        heartbeat_workspace(workspace)

        stream = _probe_video_stream(source_path)
        command = _build_clip_proxy_command(
            source_path=source_path,
            output_path=output_path,
            stream=stream,
            window=window,
        )
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(120, int(settings.editor_preview_proxy_timeout_seconds)),
            check=False,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout or "").strip()
            raise ProjectPreviewError(f"ffmpeg project preview failed: {stderr[-800:]}")

        preview_key = build_project_preview_key(user_id=user_id, project_id=project_id)
        r2_client.upload_file(str(output_path), preview_key)
        heartbeat_workspace(workspace)

        source_profile = _source_profile(stream)
        finalize_workspace(
            workspace,
            state="terminal_success",
            metadata={
                "preview_key": preview_key,
                "source_profile": source_profile,
                "offset_sec": window.offset_sec,
                "duration_sec": window.duration_sec,
            },
        )
        return ProjectPreviewResult(
            preview_key=preview_key,
            command_debug=shlex.join(command)[:2000],
            source_profile=source_profile,
            offset_sec=window.offset_sec,
            duration_sec=window.duration_sec,
        )
    except Exception:
        finalize_workspace(workspace, state="terminal_failed")
        raise
    finally:
        shutil.rmtree(workspace.path, ignore_errors=True)
