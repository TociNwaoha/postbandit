import uuid

import pytest

from app.models.video import VideoImportState, VideoSourceType, VideoStatus
from app.services.youtube.import_state import (
    derive_youtube_ui_state,
    is_retryable_import_state,
    transition_import_state,
)


class DummySession:
    def __init__(self) -> None:
        self.events = []

    def add(self, obj) -> None:
        self.events.append(obj)


class DummyVideo:
    def __init__(
        self,
        *,
        import_state: VideoImportState,
        status: VideoStatus,
        source_type: VideoSourceType = VideoSourceType.youtube_single,
    ) -> None:
        self.id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.import_state = import_state
        self.import_state_version = 0
        self.status = status
        self.source_type = source_type


def test_retryable_import_state_checks():
    assert is_retryable_import_state(VideoImportState.failed_retryable) is True
    assert is_retryable_import_state(VideoImportState.replacement_upload_required) is True
    assert is_retryable_import_state(VideoImportState.ready) is False


def test_derive_ui_state_processing():
    video = DummyVideo(import_state=VideoImportState.processing, status=VideoStatus.transcribing)
    assert derive_youtube_ui_state(video) == "processing:transcribing"


def test_transition_records_event():
    session = DummySession()
    video = DummyVideo(import_state=VideoImportState.queued, status=VideoStatus.downloading)
    moved = transition_import_state(
        session,
        video,
        to_state=VideoImportState.metadata_extracting,
        reason_code="unit_test_transition",
        actor="test",
    )
    assert moved is True
    assert video.import_state == VideoImportState.metadata_extracting
    assert video.import_state_version == 1
    assert len(session.events) == 1
    assert session.events[0].reason_code == "unit_test_transition"


def test_transition_rejects_illegal_state_change():
    session = DummySession()
    video = DummyVideo(import_state=VideoImportState.queued, status=VideoStatus.downloading)
    with pytest.raises(ValueError):
        transition_import_state(
            session,
            video,
            to_state=VideoImportState.ready,
            reason_code="illegal_transition",
            actor="test",
        )

