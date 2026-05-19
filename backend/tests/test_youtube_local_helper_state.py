import asyncio

import pytest

from app.services.youtube.local_helper_state import (
    LocalHelperSessionError,
    consume_local_helper_session,
    create_local_helper_session,
)


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def getdel(self, key: str) -> str | None:
        return self._store.pop(key, None)

    async def aclose(self) -> None:
        return None


def test_local_helper_session_is_one_time(monkeypatch):
    fake = _FakeRedis()

    async def _fake_client():
        return fake

    monkeypatch.setattr("app.services.youtube.local_helper_state._client", _fake_client)

    async def _run():
        created = await create_local_helper_session(
            user_id="u1",
            video_id="v1",
            upload_key="uploads/v1/local-helper.mp4",
            source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            ttl_seconds=900,
        )
        consumed = await consume_local_helper_session(token=created.token)
        assert consumed.video_id == "v1"
        assert consumed.upload_key == "uploads/v1/local-helper.mp4"

        with pytest.raises(LocalHelperSessionError):
            await consume_local_helper_session(token=created.token)

    asyncio.run(_run())


def test_local_helper_session_rejects_missing_token():
    async def _run():
        with pytest.raises(LocalHelperSessionError):
            await consume_local_helper_session(token=" ")

    asyncio.run(_run())
