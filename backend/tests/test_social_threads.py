from __future__ import annotations

from datetime import timedelta

import httpx

from app.services.social.meta.auth import ProviderCredentials
from app.services.social.threads import ThreadsAdapter, utcnow
from app.services.social.types import PublishPayload


class DummyResponse:
    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code
        self.text = str(data)

    def json(self) -> dict:
        return self._data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://graph.threads.net")
            response = httpx.Response(self.status_code, request=request, json=self._data)
            raise httpx.HTTPStatusError("request failed", request=request, response=response)


def _ready_credentials() -> ProviderCredentials:
    return ProviderCredentials(
        client_id="threads-client-id",
        client_secret="threads-client-secret",
        source="THREADS_APP_ID/THREADS_APP_SECRET",
        missing_fields=[],
        rejected_sources=[],
        validation_warning=None,
    )


def _payload(*, destination_external_id: str = "123", caption: str = "Hello from PostBandit") -> PublishPayload:
    return PublishPayload(
        title=None,
        description=None,
        caption=caption,
        hashtags=None,
        privacy=None,
        scheduled_for=None,
        media_url=None,
        destination_external_id=destination_external_id,
        destination_metadata={},
    )


def test_threads_exchange_code_uses_long_lived_exchange(monkeypatch):
    adapter = ThreadsAdapter()
    monkeypatch.setattr(adapter, "setup_status", lambda: ("ready", None))
    monkeypatch.setattr(adapter, "_credentials", lambda: _ready_credentials())

    class FakeClient:
        def __init__(self, timeout: int):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, data=None, headers=None):
            assert url.endswith("/oauth/access_token")
            assert data["grant_type"] == "authorization_code"
            return DummyResponse({"access_token": "short-lived-token", "expires_in": 3600})

        def get(self, url, params=None, headers=None):
            if url.endswith("/access_token"):
                assert params["grant_type"] == "th_exchange_token"
                return DummyResponse({"access_token": "long-lived-token", "expires_in": 5184000})
            if url.endswith("/me"):
                return DummyResponse(
                    {
                        "id": "17841400000000000",
                        "username": "postbandit_test",
                        "name": "PostBandit Test",
                        "threads_profile_picture_url": "https://example.com/avatar.jpg",
                    }
                )
            raise AssertionError(f"Unexpected GET url in test: {url}")

    monkeypatch.setattr("app.services.social.threads.httpx.Client", FakeClient)

    payload = adapter.exchange_code(
        code="oauth-code",
        redirect_uri="https://api.postbandit.com/api/social/threads/callback",
    )

    assert payload.access_token == "long-lived-token"
    assert payload.token_expires_at is not None
    assert payload.external_account_id == "17841400000000000"
    assert payload.metadata_json.get("destination_type") == "threads_profile"


def test_threads_publish_supports_text_and_video(monkeypatch):
    adapter = ThreadsAdapter()
    monkeypatch.setattr(adapter, "setup_status", lambda: ("ready", None))

    calls: list[tuple[str, dict]] = []

    def fake_graph_post(client, *, url, data=None, json_body=None, headers=None):
        calls.append((url, dict(data or {})))
        if url.endswith("/threads"):
            return {"id": "creation-123"}
        if url.endswith("/threads_publish"):
            return {"id": "post-123"}
        raise AssertionError(f"Unexpected POST url in test: {url}")

    monkeypatch.setattr("app.services.social.threads.graph_post", fake_graph_post)
    monkeypatch.setattr("app.services.social.threads.graph_get", lambda *args, **kwargs: {"id": "post-123"})

    text_result = adapter.publish(
        media_path="/tmp/export.mp4",
        media_url=None,
        payload=_payload(),
        access_token="access-token",
        refresh_token=None,
        token_expires_at=None,
    )
    assert text_result.status == "published"
    assert calls[0][0].endswith("/me/threads")
    assert calls[0][1].get("media_type") == "TEXT"
    assert "video_url" not in calls[0][1]

    calls.clear()
    video_result = adapter.publish(
        media_path="/tmp/export.mp4",
        media_url="https://cdn.postbandit.com/exports/video.mp4",
        payload=_payload(caption="Video caption"),
        access_token="access-token",
        refresh_token=None,
        token_expires_at=None,
    )
    assert video_result.status == "published"
    assert calls[0][0].endswith("/me/threads")
    assert calls[0][1].get("media_type") == "VIDEO"
    assert calls[0][1].get("video_url") == "https://cdn.postbandit.com/exports/video.mp4"


def test_threads_publish_refreshes_token_when_near_expiry(monkeypatch):
    adapter = ThreadsAdapter()
    monkeypatch.setattr(adapter, "setup_status", lambda: ("ready", None))

    refreshed_expires_at = utcnow() + timedelta(days=45)
    monkeypatch.setattr(
        "app.services.social.threads._refresh_long_lived_token",
        lambda client, *, access_token: ("refreshed-token", refreshed_expires_at),
    )

    observed_tokens: list[str] = []

    def fake_graph_post(client, *, url, data=None, json_body=None, headers=None):
        if isinstance(data, dict) and "access_token" in data:
            observed_tokens.append(str(data["access_token"]))
        if url.endswith("/threads"):
            return {"id": "creation-456"}
        if url.endswith("/threads_publish"):
            return {"id": "post-456"}
        raise AssertionError(f"Unexpected POST url in test: {url}")

    monkeypatch.setattr("app.services.social.threads.graph_post", fake_graph_post)
    monkeypatch.setattr("app.services.social.threads.graph_get", lambda *args, **kwargs: {"id": "post-456"})

    result = adapter.publish(
        media_path="/tmp/export.mp4",
        media_url=None,
        payload=_payload(),
        access_token="stale-token",
        refresh_token=None,
        token_expires_at=utcnow() + timedelta(hours=1),
    )

    assert result.status == "published"
    assert observed_tokens
    assert all(token == "refreshed-token" for token in observed_tokens)
    assert result.updated_access_token == "refreshed-token"
    assert result.updated_token_expires_at == refreshed_expires_at
