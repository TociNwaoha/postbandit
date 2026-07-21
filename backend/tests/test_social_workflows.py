from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.connected_account import SocialPlatform
from app.models.social_workflow import WorkflowCopyMode
from app.schemas.workflow import WorkflowCreateRequest
from app.services.workflow_detection import source_capability
from app.services.workflow_engine import _source_copy, _validate_destination_media
from app.services.workflows.official_sources import (
    is_reconnect_required_source_error,
    source_poll_error_message,
)


def _account(platform: SocialPlatform, scopes: list[str], **metadata):
    return SimpleNamespace(
        id=uuid4(),
        platform=platform,
        scopes=scopes,
        metadata_json=metadata,
    )


def test_youtube_source_requires_read_scope():
    account = _account(
        SocialPlatform.youtube,
        ["https://www.googleapis.com/auth/youtube.upload"],
    )
    status, message, missing = source_capability(account)
    assert status == "reconnect_required"
    assert "Reconnect" in message
    assert missing == ["https://www.googleapis.com/auth/youtube.readonly"]


def test_supported_source_with_scope_is_ready():
    account = _account(SocialPlatform.x, ["tweet.read", "users.read", "tweet.write"])
    assert source_capability(account) == ("ready", None, [])


def test_facebook_profile_is_not_a_monitorable_source():
    account = _account(
        SocialPlatform.facebook,
        ["pages_read_engagement"],
        destination_type="facebook_account",
    )
    status, message, missing = source_capability(account)
    assert status == "unsupported"
    assert "Page" in message
    assert missing == []


def test_workflow_rejects_source_as_destination():
    source_id = uuid4()
    with pytest.raises(ValidationError, match="source account"):
        WorkflowCreateRequest(
            name="Loop",
            source_account_id=source_id,
            copy_mode=WorkflowCopyMode.reuse_source,
            destinations=[
                {
                    "connected_account_id": source_id,
                    "platform": "youtube",
                }
            ],
        )


def test_reuse_source_copy_keeps_title_and_description():
    run = SimpleNamespace(source_title="Original title", source_description="Original description #Test")
    youtube = _source_copy(run, SocialPlatform.youtube)
    instagram = _source_copy(run, SocialPlatform.instagram)
    assert youtube["title"] == "Original title"
    assert youtube["description"] == "Original description #Test"
    assert youtube["hashtags"] == ["#Test"]
    assert instagram["caption"] == "Original description #Test"


def test_media_preflight_skips_overlong_destination(monkeypatch):
    class _Capabilities:
        supports_video_upload = True

    monkeypatch.setattr(
        "app.services.workflow_engine.get_adapter",
        lambda _platform: SimpleNamespace(capabilities=lambda: _Capabilities()),
    )
    account = _account(SocialPlatform.threads, ["threads_basic"])
    clip = SimpleNamespace(start_time=0, end_time=360)
    assert "exceeds" in _validate_destination_media(account, clip)


def test_youtube_oauth_token_poll_failure_is_reconnect_message():
    raw_error = (
        "YouTube uploads poll failed: Client error '400 Bad Request' for url "
        "'https://oauth2.googleapis.com/token' For more information check: "
        "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400"
    )

    assert is_reconnect_required_source_error(raw_error) is True
    assert source_poll_error_message(SocialPlatform.youtube, raw_error) == (
        "Reconnect the YouTube source account with readonly permissions."
    )
