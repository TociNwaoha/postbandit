import uuid
from types import SimpleNamespace

from app.models.video import VideoStatus
from app.worker.tasks import cleanup


class DummySession:
    def __init__(self) -> None:
        self.deleted: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def delete(self, obj) -> None:
        self.deleted.append(obj)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class DummySessionFactory:
    def __init__(self, session: DummySession) -> None:
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_failed_import_cleanup_deletes_eligible_rows(monkeypatch):
    session = DummySession()
    session_factory = DummySessionFactory(session)
    video_id = uuid.uuid4()
    video = SimpleNamespace(id=video_id, storage_key="uploads/abc.mp4")
    deleted_keys: list[str] = []

    monkeypatch.setattr(cleanup, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(cleanup, "_list_failed_import_video_ids", lambda db, cutoff: [video_id])
    monkeypatch.setattr(cleanup, "_has_active_jobs", lambda db, video_id: False)
    monkeypatch.setattr(cleanup, "_load_video_for_cleanup", lambda db, video_id: video)
    monkeypatch.setattr(cleanup, "_collect_video_storage_keys", lambda db, video: {"k1", "k2"})
    monkeypatch.setattr(cleanup.object_storage_client, "delete_file", lambda key: deleted_keys.append(key) or True)

    result = cleanup.sweep_failed_imports_impl(dry_run=False)

    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["deleted"] == 1
    assert result["skipped_active_job"] == 0
    assert result["storage_delete_failures"] == 0
    assert result["db_delete_failures"] == 0
    assert session.deleted == [video]
    assert session.commits == 1
    assert session.rollbacks == 0
    assert sorted(deleted_keys) == ["k1", "k2"]


def test_failed_import_cleanup_skips_when_active_job(monkeypatch):
    session = DummySession()
    session_factory = DummySessionFactory(session)
    video_id = uuid.uuid4()
    delete_calls: list[str] = []

    monkeypatch.setattr(cleanup, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(cleanup, "_list_failed_import_video_ids", lambda db, cutoff: [video_id])
    monkeypatch.setattr(cleanup, "_has_active_jobs", lambda db, video_id: True)
    monkeypatch.setattr(cleanup.object_storage_client, "delete_file", lambda key: delete_calls.append(key) or True)

    result = cleanup.sweep_failed_imports_impl(dry_run=False)

    assert result["scanned"] == 1
    assert result["eligible"] == 0
    assert result["deleted"] == 0
    assert result["skipped_active_job"] == 1
    assert session.deleted == []
    assert session.commits == 0
    assert delete_calls == []


def test_failed_import_cleanup_respects_dry_run(monkeypatch):
    session = DummySession()
    session_factory = DummySessionFactory(session)
    video_id = uuid.uuid4()
    video = SimpleNamespace(id=video_id, storage_key="uploads/abc.mp4")
    delete_calls: list[str] = []

    monkeypatch.setattr(cleanup, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(cleanup, "_list_failed_import_video_ids", lambda db, cutoff: [video_id])
    monkeypatch.setattr(cleanup, "_has_active_jobs", lambda db, video_id: False)
    monkeypatch.setattr(cleanup, "_load_video_for_cleanup", lambda db, video_id: video)
    monkeypatch.setattr(cleanup, "_collect_video_storage_keys", lambda db, video: {"k1", "k2"})
    monkeypatch.setattr(cleanup.object_storage_client, "delete_file", lambda key: delete_calls.append(key) or True)

    result = cleanup.sweep_failed_imports_impl(dry_run=True)

    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["deleted"] == 0
    assert result["skipped_active_job"] == 0
    assert session.deleted == []
    assert session.commits == 0
    assert delete_calls == []


def test_failed_import_cleanup_counts_failures(monkeypatch):
    session = DummySession()
    session_factory = DummySessionFactory(session)
    video_id = uuid.uuid4()
    video = SimpleNamespace(id=video_id, storage_key="uploads/abc.mp4")

    def fail_delete(_key: str) -> bool:
        return False

    def fail_db_delete(_obj) -> None:
        raise RuntimeError("delete failed")

    monkeypatch.setattr(cleanup, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(cleanup, "_list_failed_import_video_ids", lambda db, cutoff: [video_id])
    monkeypatch.setattr(cleanup, "_has_active_jobs", lambda db, video_id: False)
    monkeypatch.setattr(cleanup, "_load_video_for_cleanup", lambda db, video_id: video)
    monkeypatch.setattr(cleanup, "_collect_video_storage_keys", lambda db, video: {"k1"})
    monkeypatch.setattr(cleanup.object_storage_client, "delete_file", fail_delete)
    monkeypatch.setattr(session, "delete", fail_db_delete)

    result = cleanup.sweep_failed_imports_impl(dry_run=False)

    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["deleted"] == 0
    assert result["storage_delete_failures"] == 1
    assert result["db_delete_failures"] == 1
    assert session.rollbacks == 1


def test_stale_queued_cleanup_marks_missing_uploads_error(monkeypatch):
    session = DummySession()
    session_factory = DummySessionFactory(session)
    video_id = uuid.uuid4()
    video = SimpleNamespace(
        id=video_id,
        storage_key="uploads/missing.mp4",
        status=VideoStatus.queued,
        error_message=None,
        external_metadata_json={"upload_confirmed": False},
    )

    monkeypatch.setattr(cleanup, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(cleanup, "_list_stale_queued_upload_video_ids", lambda db, cutoff: [video_id])
    monkeypatch.setattr(cleanup, "_has_active_jobs", lambda db, video_id: False)
    monkeypatch.setattr(cleanup, "_load_video_for_cleanup", lambda db, video_id: video)
    monkeypatch.setattr(cleanup.object_storage_client, "file_exists", lambda key: False)
    monkeypatch.setattr(cleanup, "_enqueue_recovery_transcribe_job", lambda db, video: True)

    result = cleanup.sweep_stale_queued_uploads_impl(dry_run=False)

    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["stale_queued_marked_error"] == 1
    assert result["stale_queued_recovered_enqueued"] == 0
    assert video.status == VideoStatus.error
    assert "not completed" in (video.error_message or "").lower()
    assert session.commits == 1


def test_stale_queued_cleanup_recovers_when_file_exists(monkeypatch):
    session = DummySession()
    session_factory = DummySessionFactory(session)
    video_id = uuid.uuid4()
    video = SimpleNamespace(
        id=video_id,
        storage_key="uploads/existing.mp4",
        status=VideoStatus.queued,
        error_message="stale",
        external_metadata_json={"upload_confirmed": False},
    )
    enqueued: list[uuid.UUID] = []

    monkeypatch.setattr(cleanup, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(cleanup, "_list_stale_queued_upload_video_ids", lambda db, cutoff: [video_id])
    monkeypatch.setattr(cleanup, "_has_active_jobs", lambda db, video_id: False)
    monkeypatch.setattr(cleanup, "_load_video_for_cleanup", lambda db, video_id: video)
    monkeypatch.setattr(cleanup.object_storage_client, "file_exists", lambda key: True)
    monkeypatch.setattr(cleanup, "_enqueue_recovery_transcribe_job", lambda db, video: enqueued.append(video.id) or True)

    result = cleanup.sweep_stale_queued_uploads_impl(dry_run=False)

    assert result["eligible"] == 1
    assert result["stale_queued_recovered_enqueued"] == 1
    assert result["stale_queued_marked_error"] == 0
    assert video.status == VideoStatus.transcribing
    assert video.external_metadata_json.get("upload_confirmed") is True
    assert video.error_message is None
    assert enqueued == [video_id]
    assert session.commits == 2


def test_stale_queued_cleanup_respects_dry_run(monkeypatch):
    session = DummySession()
    session_factory = DummySessionFactory(session)
    video_id = uuid.uuid4()
    video = SimpleNamespace(
        id=video_id,
        storage_key="uploads/missing.mp4",
        status=VideoStatus.queued,
        error_message=None,
        external_metadata_json={"upload_confirmed": False},
    )

    monkeypatch.setattr(cleanup, "SyncSessionLocal", session_factory)
    monkeypatch.setattr(cleanup, "_list_stale_queued_upload_video_ids", lambda db, cutoff: [video_id])
    monkeypatch.setattr(cleanup, "_has_active_jobs", lambda db, video_id: False)
    monkeypatch.setattr(cleanup, "_load_video_for_cleanup", lambda db, video_id: video)
    monkeypatch.setattr(cleanup.object_storage_client, "file_exists", lambda key: False)
    monkeypatch.setattr(cleanup, "_enqueue_recovery_transcribe_job", lambda db, video: True)

    result = cleanup.sweep_stale_queued_uploads_impl(dry_run=True)

    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert result["stale_queued_marked_error"] == 0
    assert result["stale_queued_recovered_enqueued"] == 0
    assert video.status == VideoStatus.queued
    assert session.commits == 0
