from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from app.config import settings
from app.services.social.tiktok import TikTokAdapter, utcnow
from app.services.social.types import PublishPayload


class DummyResponse:
    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def json(self) -> dict:
        return self._data


class SequencedClient:
    def __init__(self, sequence: list[tuple[str, str, DummyResponse]], timeout: int = 60):
        self._sequence = list(sequence)
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def request(self, method, url, headers=None, params=None, data=None, json=None):
        if not self._sequence:
            raise AssertionError(f"Unexpected request with empty sequence: {method} {url}")
        expected_method, expected_url, response = self._sequence.pop(0)
        if method != expected_method or url != expected_url:
            raise AssertionError(f"Unexpected request. expected={expected_method} {expected_url} got={method} {url}")
        return response


def _configure_tiktok(monkeypatch):
    monkeypatch.setattr(settings, "tiktok_client_key", "tk_client_key")
    monkeypatch.setattr(settings, "tiktok_client_secret", "tk_client_secret")
    monkeypatch.setattr(settings, "social_token_encryption_key", "0123456789abcdef0123456789abcdef")
    monkeypatch.setattr(settings, "backend_public_url", "https://api.postbandit.com")
    monkeypatch.setattr(settings, "tiktok_publish_poll_interval_seconds", 1)
    monkeypatch.setattr(settings, "tiktok_publish_poll_timeout_seconds", 30)


def _publish_payload(*, privacy: str = "SELF_ONLY", scopes: list[str] | None = None) -> PublishPayload:
    return PublishPayload(
        title="Clip title",
        description="Clip description",
        caption="Clip caption",
        hashtags=["#postbandit"],
        privacy=privacy,
        scheduled_for=None,
        media_url="https://cdn.postbandit.com/export.mp4",
        destination_external_id="open-id-123",
        destination_metadata={
            "destination_type": "tiktok_profile",
            "profile": {"username": "postbandit_user"},
            "scopes": scopes or ["video.publish", "video.upload"],
        },
    )


def test_tiktok_build_connect_url(monkeypatch):
    _configure_tiktok(monkeypatch)
    adapter = TikTokAdapter()

    url = adapter.build_connect_url(
        state="oauth-state-token",
        redirect_uri="https://api.postbandit.com/api/social/tiktok/callback",
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "www.tiktok.com"
    assert parsed.path == "/v2/auth/authorize/"
    assert query.get("client_key") == ["tk_client_key"]
    assert query.get("response_type") == ["code"]
    assert query.get("redirect_uri") == ["https://api.postbandit.com/api/social/tiktok/callback"]
    assert query.get("state") == ["oauth-state-token"]


def test_tiktok_exchange_code_returns_connected_profile(monkeypatch):
    _configure_tiktok(monkeypatch)
    adapter = TikTokAdapter()

    sequence = [
        (
            "POST",
            "https://open.tiktokapis.com/v2/oauth/token/",
            DummyResponse(
                {
                    "access_token": "access-123",
                    "refresh_token": "refresh-123",
                    "expires_in": 86400,
                    "refresh_expires_in": 31536000,
                    "open_id": "open-id-123",
                    "scope": "user.info.basic,user.info.profile,video.publish,video.upload",
                    "token_type": "Bearer",
                }
            ),
        ),
        (
            "GET",
            "https://open.tiktokapis.com/v2/user/info/",
            DummyResponse(
                {
                    "data": {
                        "user": {
                            "open_id": "open-id-123",
                            "display_name": "PostBandit User",
                            "username": "postbandit_user",
                            "avatar_url": "https://cdn.example/avatar.jpg",
                            "profile_deep_link": "https://www.tiktok.com/@postbandit_user",
                        }
                    },
                    "error": {"code": "ok", "message": "", "log_id": "log-user"},
                }
            ),
        ),
        (
            "POST",
            "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
            DummyResponse(
                {
                    "data": {
                        "creator_username": "postbandit_user",
                        "creator_nickname": "PostBandit User",
                        "privacy_level_options": ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS"],
                        "comment_disabled": False,
                        "duet_disabled": False,
                        "stitch_disabled": False,
                        "max_video_post_duration_sec": 600,
                    },
                    "error": {"code": "ok", "message": "", "log_id": "log-creator"},
                }
            ),
        ),
    ]

    monkeypatch.setattr(
        "app.services.social.tiktok.httpx.Client",
        lambda timeout=45: SequencedClient(sequence, timeout=timeout),
    )

    account = adapter.exchange_code(
        code="oauth-code",
        redirect_uri="https://api.postbandit.com/api/social/tiktok/callback",
    )

    assert account.external_account_id == "open-id-123"
    assert account.display_name == "PostBandit User"
    assert account.username_or_channel_name == "postbandit_user"
    assert account.access_token == "access-123"
    assert account.refresh_token == "refresh-123"
    assert account.token_expires_at is not None
    assert account.metadata_json.get("destination_type") == "tiktok_profile"
    creator_info = account.metadata_json.get("tiktok_creator_info")
    assert isinstance(creator_info, dict)
    assert creator_info.get("privacy_level_options") == ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS"]


def test_tiktok_publish_direct_post_success(monkeypatch):
    _configure_tiktok(monkeypatch)
    adapter = TikTokAdapter()

    sequence = [
        (
            "POST",
            "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
            DummyResponse(
                {
                    "data": {
                        "creator_username": "postbandit_user",
                        "privacy_level_options": ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS"],
                        "comment_disabled": False,
                        "duet_disabled": False,
                        "stitch_disabled": False,
                        "max_video_post_duration_sec": 600,
                    },
                    "error": {"code": "ok", "message": "", "log_id": "creator-ok"},
                }
            ),
        ),
        (
            "POST",
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            DummyResponse(
                {
                    "data": {"publish_id": "v_pub_url~v2.111"},
                    "error": {"code": "ok", "message": "", "log_id": "init-ok"},
                }
            ),
        ),
        (
            "POST",
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            DummyResponse(
                {
                    "data": {
                        "status": "PUBLISH_COMPLETE",
                        "publicly_available_post_id": ["7450000000000000001"],
                    },
                    "error": {"code": "ok", "message": "", "log_id": "status-ok"},
                }
            ),
        ),
    ]

    monkeypatch.setattr(
        "app.services.social.tiktok.httpx.Client",
        lambda timeout=60: SequencedClient(sequence, timeout=timeout),
    )

    result = adapter.publish(
        media_path="/tmp/export.mp4",
        media_url="https://cdn.postbandit.com/export.mp4",
        payload=_publish_payload(privacy="SELF_ONLY"),
        access_token="access-123",
        refresh_token="refresh-123",
        token_expires_at=utcnow() + timedelta(hours=2),
    )

    assert result.status == "published"
    assert result.external_post_id == "7450000000000000001"
    assert result.external_post_url == "https://www.tiktok.com/@postbandit_user/video/7450000000000000001"
    assert result.provider_metadata_json.get("publish_mode") == "direct"


def test_tiktok_publish_falls_back_to_inbox_and_returns_waiting_user_action(monkeypatch):
    _configure_tiktok(monkeypatch)
    adapter = TikTokAdapter()

    sequence = [
        (
            "POST",
            "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
            DummyResponse(
                {
                    "data": {
                        "creator_username": "postbandit_user",
                        "privacy_level_options": ["SELF_ONLY"],
                        "comment_disabled": False,
                        "duet_disabled": False,
                        "stitch_disabled": False,
                        "max_video_post_duration_sec": 600,
                    },
                    "error": {"code": "ok", "message": "", "log_id": "creator-ok"},
                }
            ),
        ),
        (
            "POST",
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            DummyResponse(
                {
                    "error": {
                        "code": "scope_not_authorized",
                        "message": "video.publish scope is not authorized",
                        "log_id": "direct-blocked",
                    }
                },
                status_code=401,
            ),
        ),
        (
            "POST",
            "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
            DummyResponse(
                {
                    "data": {"publish_id": "v_inbox_url~v2.222"},
                    "error": {"code": "ok", "message": "", "log_id": "inbox-init-ok"},
                }
            ),
        ),
        (
            "POST",
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            DummyResponse(
                {
                    "data": {"status": "SEND_TO_USER_INBOX"},
                    "error": {"code": "ok", "message": "", "log_id": "status-inbox"},
                }
            ),
        ),
    ]

    monkeypatch.setattr(
        "app.services.social.tiktok.httpx.Client",
        lambda timeout=60: SequencedClient(sequence, timeout=timeout),
    )

    result = adapter.publish(
        media_path="/tmp/export.mp4",
        media_url="https://cdn.postbandit.com/export.mp4",
        payload=_publish_payload(privacy="SELF_ONLY", scopes=["video.upload"]),
        access_token="access-123",
        refresh_token="refresh-123",
        token_expires_at=utcnow() + timedelta(hours=2),
    )

    assert result.status == "waiting_user_action"
    assert result.external_post_id == "v_inbox_url~v2.222"
    assert "Open TikTok inbox" in (result.error_message or "")
    assert result.provider_metadata_json.get("publish_mode") == "inbox_upload"
