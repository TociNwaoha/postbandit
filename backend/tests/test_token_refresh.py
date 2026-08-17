from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from app.models.connected_account import SocialPlatform
from app.services.social.types import PublishPayload
from app.services.social.x import XAdapter, _compose_x_text, _media_category_for_type, build_pkce_challenge
from app.services import token_refresh


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0

    def add(self, value) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1


def account(**overrides):
    defaults = {
        "platform": SocialPlatform.youtube,
        "access_token_encrypted": "encrypted-access",
        "refresh_token_encrypted": "encrypted-refresh",
        "token_expires_at": None,
        "token_expired": False,
        "metadata_json": {},
        "last_token_refresh": None,
        "id": "account-1",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_get_access_token_returns_decrypted_token_when_not_expiring(monkeypatch):
    db = FakeSession()
    connected = account()
    monkeypatch.setattr(token_refresh, "decrypt_secret", lambda value: f"plain:{value}")

    assert token_refresh.get_access_token(connected, db) == "plain:encrypted-access"
    assert db.commits == 0


def test_get_access_token_marks_reconnect_when_decryption_fails(monkeypatch):
    db = FakeSession()
    connected = account()
    monkeypatch.setattr(token_refresh, "decrypt_secret", lambda value: (_ for _ in ()).throw(ValueError("bad token")))

    assert token_refresh.get_access_token(connected, db) is None
    assert connected.token_expired is True
    assert connected.metadata_json["token_status"] == "reconnect_required"
    assert connected.metadata_json["token_error"] == "ValueError"
    assert db.commits == 1


def test_youtube_refresh_without_refresh_token_requires_reconnect():
    db = FakeSession()
    connected = account(refresh_token_encrypted=None)

    assert token_refresh.refresh_connected_account_token(connected, db) is None
    assert connected.metadata_json["token_error"] == "missing_refresh_token"
    assert db.commits == 1


def test_youtube_refresh_stores_access_token_and_clears_reconnect(monkeypatch):
    db = FakeSession()
    expires_at = token_refresh.utcnow() + timedelta(hours=1)
    connected = account(token_expired=True, metadata_json={"token_status": "reconnect_required", "token_error": "old"})
    monkeypatch.setattr(token_refresh, "decrypt_secret", lambda value: "plain-refresh")
    monkeypatch.setattr(token_refresh, "encrypt_secret", lambda value: f"encrypted:{value}")
    monkeypatch.setattr(token_refresh.YouTubeAdapter, "_refresh_access_token", lambda self, value: ("fresh-access", expires_at))

    assert token_refresh.refresh_connected_account_token(connected, db) == "fresh-access"
    assert connected.access_token_encrypted == "encrypted:fresh-access"
    assert connected.token_expires_at == expires_at
    assert connected.token_expired is False
    assert "token_status" not in connected.metadata_json
    assert db.commits == 1


def test_expiring_token_triggers_refresh_without_real_provider_call(monkeypatch):
    db = FakeSession()
    connected = account(token_expires_at=token_refresh.utcnow() + timedelta(seconds=30))
    monkeypatch.setattr(token_refresh, "refresh_connected_account_token", lambda account, db: "refreshed")

    assert token_refresh.get_access_token(connected, db) == "refreshed"


def test_x_connect_url_contains_pkce_context(monkeypatch):
    adapter = XAdapter()
    monkeypatch.setattr(adapter, "setup_status", lambda: ("ready", None))
    monkeypatch.setattr("app.services.social.x.settings.x_client_id", "x-client")
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert build_pkce_challenge(verifier) == challenge

    url = adapter.build_connect_url(
        state="state-1",
        redirect_uri="https://api.example.test/callback",
        oauth_context={"code_challenge": challenge},
    )
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["x-client"]
    assert query["state"] == ["state-1"]
    assert query["code_challenge"] == [challenge]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["https://api.example.test/callback"]


def test_x_exchange_code_sends_raw_pkce_verifier(monkeypatch):
    adapter = XAdapter()
    monkeypatch.setattr(adapter, "setup_status", lambda: ("ready", None))
    monkeypatch.setattr("app.services.social.x.settings.x_client_id", "x-client")
    monkeypatch.setattr("app.services.social.x.settings.x_client_secret", "x-secret")

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, data=None, headers=None):
            assert url.endswith("/oauth2/token")
            assert data["code_verifier"] == "verifier-value"
            assert "code_challenge" not in data
            return Response({"access_token": "access", "refresh_token": "refresh"})

        def get(self, url, headers=None, params=None):
            assert url.endswith("/2/users/me")
            return Response({"data": {"id": "x-user", "name": "PostBandit", "username": "postbandit"}})

    monkeypatch.setattr("app.services.social.x.httpx.Client", Client)

    result = adapter.exchange_code(
        code="oauth-code",
        redirect_uri="https://api.example.test/callback",
        oauth_context={"code_verifier": "verifier-value"},
    )

    assert result.external_account_id == "x-user"
    assert result.refresh_token == "refresh"


def test_x_payload_builder_normalizes_tags_and_clamps_caption():
    payload = PublishPayload(
        title="ignored",
        description="also ignored",
        caption="x" * 300,
        hashtags=["PostBandit", "#postbandit"],
        privacy=None,
        scheduled_for=None,
        media_url=None,
        destination_external_id=None,
        destination_metadata={},
    )
    assert _compose_x_text(payload) == ("x" * 277) + "..."


def test_x_payload_builder_uses_title_description_and_unique_tags():
    payload = PublishPayload(
        title="A title",
        description="A description",
        caption=None,
        hashtags=["PostBandit", "#postbandit", "clips"],
        privacy=None,
        scheduled_for=None,
        media_url=None,
        destination_external_id=None,
        destination_metadata={},
    )
    assert _compose_x_text(payload) == "A title\n\nA description\n\n#PostBandit #clips"
    assert _media_category_for_type("video/mp4") == "tweet_video"
    assert _media_category_for_type("image/png") == "tweet_image"
