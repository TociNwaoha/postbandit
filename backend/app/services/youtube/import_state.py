from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.video import Video, VideoImportState, VideoSourceType, VideoStatus
from app.models.video_import_state_event import VideoImportStateEvent

ACTIVE_IMPORT_STATES = {
    VideoImportState.queued,
    VideoImportState.metadata_extracting,
    VideoImportState.downloadable,
    VideoImportState.downloading,
    VideoImportState.processing,
}

RETRYABLE_IMPORT_STATES = {
    VideoImportState.failed_retryable,
    VideoImportState.blocked,
    VideoImportState.replacement_upload_required,
    VideoImportState.helper_required,
    VideoImportState.embed_only,
}

TERMINAL_IMPORT_STATES = {
    VideoImportState.ready,
    VideoImportState.failed_retryable,
    VideoImportState.failed_terminal,
    VideoImportState.embed_only,
    VideoImportState.not_applicable,
}

_ALLOWED_TRANSITIONS: dict[VideoImportState, set[VideoImportState]] = {
    VideoImportState.not_applicable: {VideoImportState.not_applicable},
    VideoImportState.queued: {
        VideoImportState.metadata_extracting,
        VideoImportState.failed_retryable,
        VideoImportState.failed_terminal,
    },
    VideoImportState.metadata_extracting: {
        VideoImportState.downloadable,
        VideoImportState.failed_retryable,
        VideoImportState.failed_terminal,
    },
    VideoImportState.downloadable: {
        VideoImportState.downloading,
        VideoImportState.failed_retryable,
    },
    VideoImportState.downloading: {
        VideoImportState.processing,
        VideoImportState.blocked,
        VideoImportState.failed_retryable,
        VideoImportState.failed_terminal,
    },
    VideoImportState.blocked: {
        VideoImportState.replacement_upload_required,
        VideoImportState.helper_required,
        VideoImportState.embed_only,
        VideoImportState.queued,
        VideoImportState.failed_retryable,
    },
    VideoImportState.replacement_upload_required: {
        VideoImportState.processing,
        VideoImportState.helper_required,
        VideoImportState.embed_only,
        VideoImportState.queued,
        VideoImportState.failed_retryable,
    },
    VideoImportState.helper_required: {
        VideoImportState.processing,
        VideoImportState.replacement_upload_required,
        VideoImportState.embed_only,
        VideoImportState.queued,
        VideoImportState.failed_retryable,
    },
    VideoImportState.embed_only: {
        VideoImportState.replacement_upload_required,
        VideoImportState.helper_required,
        VideoImportState.queued,
    },
    VideoImportState.processing: {
        VideoImportState.processing,
        VideoImportState.ready,
        VideoImportState.failed_retryable,
        VideoImportState.failed_terminal,
    },
    VideoImportState.ready: {VideoImportState.ready},
    VideoImportState.failed_retryable: {
        VideoImportState.queued,
        VideoImportState.replacement_upload_required,
        VideoImportState.helper_required,
        VideoImportState.embed_only,
        VideoImportState.failed_terminal,
    },
    VideoImportState.failed_terminal: {
        VideoImportState.replacement_upload_required,
        VideoImportState.helper_required,
        VideoImportState.embed_only,
    },
}


def is_youtube_source(source_type: VideoSourceType) -> bool:
    return source_type in {
        VideoSourceType.youtube,
        VideoSourceType.youtube_single,
        VideoSourceType.youtube_playlist,
    }


def default_import_state_for_video(video: Video) -> VideoImportState:
    if not is_youtube_source(video.source_type):
        return VideoImportState.not_applicable
    return VideoImportState.queued


def is_retryable_import_state(import_state: VideoImportState | str | None) -> bool:
    if import_state is None:
        return False
    try:
        state = VideoImportState(import_state)
    except ValueError:
        return False
    return state in RETRYABLE_IMPORT_STATES


def derive_youtube_ui_state(video: Video) -> str:
    state = video.import_state or default_import_state_for_video(video)
    if state == VideoImportState.processing:
        return f"processing:{video.status.value}"
    return state.value


def _resolve_terminal_from_video_status(video: Video) -> VideoImportState | None:
    if video.status == VideoStatus.ready:
        return VideoImportState.ready
    if video.status == VideoStatus.error:
        if video.error_code and (
            video.error_code.endswith("RATE_LIMITED") or video.error_code.endswith("UNKNOWN_FAILURE")
        ):
            return VideoImportState.failed_retryable
        if video.is_download_blocked:
            return VideoImportState.replacement_upload_required
        return VideoImportState.failed_terminal
    if video.status in {VideoStatus.transcribing, VideoStatus.scoring}:
        return VideoImportState.processing
    return None


def sync_import_state_from_video_status(
    session: Any,
    video: Video,
    *,
    reason_code: str,
    actor: str = "system",
    metadata: dict[str, Any] | None = None,
) -> VideoImportState | None:
    if not is_youtube_source(video.source_type):
        return None
    next_state = _resolve_terminal_from_video_status(video)
    if next_state is None:
        return None
    transition_import_state(
        session,
        video,
        to_state=next_state,
        reason_code=reason_code,
        actor=actor,
        metadata=metadata,
        allow_noop=True,
    )
    return next_state


def transition_import_state(
    session: Any,
    video: Video,
    *,
    to_state: VideoImportState,
    reason_code: str,
    actor: str = "system",
    metadata: dict[str, Any] | None = None,
    allow_noop: bool = False,
    strict: bool = True,
) -> bool:
    from_state = video.import_state

    if not is_youtube_source(video.source_type):
        if to_state != VideoImportState.not_applicable:
            raise ValueError(f"Non-YouTube video cannot transition to {to_state.value}")
    if from_state == to_state:
        if not allow_noop:
            return False
        _record_transition_event(
            session=session,
            video=video,
            from_state=from_state,
            to_state=to_state,
            reason_code=reason_code,
            actor=actor,
            metadata={**(metadata or {}), "noop": True},
        )
        return False

    allowed = _ALLOWED_TRANSITIONS.get(from_state, set())
    if to_state not in allowed and strict:
        raise ValueError(f"Illegal import_state transition {from_state.value} -> {to_state.value}")

    video.import_state = to_state
    video.import_state_version = int(video.import_state_version or 0) + 1
    _record_transition_event(
        session=session,
        video=video,
        from_state=from_state,
        to_state=to_state,
        reason_code=reason_code,
        actor=actor,
        metadata=metadata or {},
    )
    return True


def initialize_import_state(
    session: Any,
    video: Video,
    *,
    actor: str = "system",
    reason_code: str = "import_state_initialized",
    metadata: dict[str, Any] | None = None,
) -> VideoImportState:
    state = default_import_state_for_video(video)
    video.import_state = state
    video.import_state_version = int(video.import_state_version or 0)
    _record_transition_event(
        session=session,
        video=video,
        from_state=None,
        to_state=state,
        reason_code=reason_code,
        actor=actor,
        metadata=metadata or {},
    )
    return state


def _record_transition_event(
    *,
    session: Any,
    video: Video,
    from_state: VideoImportState | None,
    to_state: VideoImportState,
    reason_code: str,
    actor: str,
    metadata: dict[str, Any],
) -> None:
    payload = {
        **metadata,
        "status": video.status.value if hasattr(video.status, "value") else str(video.status),
        "source_type": video.source_type.value if hasattr(video.source_type, "value") else str(video.source_type),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    event = VideoImportStateEvent(
        video_id=video.id,
        user_id=video.user_id,
        from_state=from_state.value if from_state else None,
        to_state=to_state.value,
        reason_code=reason_code,
        actor=actor,
        version=video.import_state_version,
        metadata_json=payload,
    )
    session.add(event)
