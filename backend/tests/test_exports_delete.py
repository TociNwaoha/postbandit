import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes.carousels import delete_carousel_export
from app.api.routes.exports import delete_export
from app.models.export import ExportStatus


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, execute_values=None, scalar_values=None):
        self.execute_values = list(execute_values or [])
        self.scalar_values = list(scalar_values or [])
        self.deleted = []
        self.commits = 0

    async def execute(self, _query):
        value = self.execute_values.pop(0) if self.execute_values else None
        return _ScalarResult(value)

    async def scalar(self, _query):
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def delete(self, entity):
        self.deleted.append(entity)

    async def commit(self):
        self.commits += 1


def _current_user():
    return SimpleNamespace(id=uuid.uuid4())


def _video_export(user_id: uuid.UUID, status: ExportStatus):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        status=status,
        storage_key="exports/video.mp4",
        srt_key="exports/video.srt",
        created_at=now,
        updated_at=now,
    )


def _carousel_export(user_id: uuid.UUID):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        zip_key="carousels/u1/w1/carousel.zip",
        preview_key="carousels/u1/w1/slides/slide_1.png",
        slide_keys_json=["carousels/u1/w1/slides/slide_1.png", "carousels/u1/w1/slides/slide_2.png"],
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_delete_video_export_success(monkeypatch):
    user = _current_user()
    export = _video_export(user.id, ExportStatus.ready)
    db = _FakeSession(execute_values=[export])
    deleted_keys = []

    from app.api.routes import exports as exports_route

    monkeypatch.setattr(exports_route.r2_client, "delete_file", lambda key: deleted_keys.append(key) or True)

    response = await delete_export(export_id=export.id, db=db, current_user=user)

    assert response.status_code == 204
    assert db.deleted == [export]
    assert db.commits == 1
    assert sorted(deleted_keys) == sorted(["exports/video.mp4", "exports/video.srt"])


@pytest.mark.asyncio
async def test_delete_video_export_blocks_active_status():
    user = _current_user()
    export = _video_export(user.id, ExportStatus.rendering)
    db = _FakeSession(execute_values=[export])

    with pytest.raises(HTTPException) as err:
        await delete_export(export_id=export.id, db=db, current_user=user)

    assert err.value.status_code == 409
    assert "queued or rendering" in err.value.detail
    assert db.deleted == []
    assert db.commits == 0


@pytest.mark.asyncio
async def test_delete_video_export_not_found():
    user = _current_user()
    db = _FakeSession(execute_values=[None])

    with pytest.raises(HTTPException) as err:
        await delete_export(export_id=uuid.uuid4(), db=db, current_user=user)

    assert err.value.status_code == 404
    assert err.value.detail == "Export not found"


@pytest.mark.asyncio
async def test_delete_video_export_storage_failures_are_non_blocking(monkeypatch):
    user = _current_user()
    export = _video_export(user.id, ExportStatus.error)
    db = _FakeSession(execute_values=[export])

    from app.api.routes import exports as exports_route

    def _delete_file(_key: str):
        raise RuntimeError("storage down")

    monkeypatch.setattr(exports_route.r2_client, "delete_file", _delete_file)

    response = await delete_export(export_id=export.id, db=db, current_user=user)

    assert response.status_code == 204
    assert db.deleted == [export]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_delete_carousel_export_success(monkeypatch):
    user = _current_user()
    row = _carousel_export(user.id)
    db = _FakeSession(execute_values=[row])
    deleted_keys = []

    from app.api.routes import carousels as carousels_route

    monkeypatch.setattr(carousels_route.r2_client, "delete_file", lambda key: deleted_keys.append(key) or True)

    response = await delete_carousel_export(export_id=row.id, db=db, current_user=user)

    assert response.status_code == 204
    assert db.deleted == [row]
    assert db.commits == 1
    assert sorted(deleted_keys) == sorted(
        [
            "carousels/u1/w1/carousel.zip",
            "carousels/u1/w1/slides/slide_1.png",
            "carousels/u1/w1/slides/slide_2.png",
        ]
    )


@pytest.mark.asyncio
async def test_delete_carousel_export_not_found():
    user = _current_user()
    db = _FakeSession(execute_values=[None])

    with pytest.raises(HTTPException) as err:
        await delete_carousel_export(export_id=uuid.uuid4(), db=db, current_user=user)

    assert err.value.status_code == 404
    assert err.value.detail == "Carousel export not found"
