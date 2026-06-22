from app.services.social.security import redact_url, sanitize_sensitive_text
from app.models.connected_account import SocialPlatform
from app.models.video import VideoSourceType
from app.services.workflows.official_sources import (
    is_reconnect_required_source_error,
    _parse_facebook_timestamp,
    _parse_instagram_timestamp,
    _parse_youtube_timestamp,
    source_poll_error_message,
    _video_source_type_for_platform,
)


def test_sanitize_sensitive_text_redacts_tokens():
    text = "GET https://graph.instagram.com/me?access_token=secret123&fields=id Authorization: Bearer abc.def"
    sanitized = sanitize_sensitive_text(text)
    assert "secret123" not in sanitized
    assert "abc.def" not in sanitized
    assert "access_token=[REDACTED]" in sanitized
    assert "Bearer [REDACTED]" in sanitized


def test_redact_url_preserves_non_sensitive_params():
    url = "https://graph.instagram.com/me/media?fields=id,media_url&access_token=secret123&limit=25"
    redacted = redact_url(url)
    assert redacted is not None
    assert "secret123" not in redacted
    assert "fields=id%2Cmedia_url" in redacted
    assert "limit=25" in redacted
    assert "access_token=%5BREDACTED%5D" in redacted


def test_parse_instagram_timestamp_returns_utc_datetime():
    parsed = _parse_instagram_timestamp("2026-06-21T12:34:56+00:00")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.isoformat().startswith("2026-06-21T12:34:56")


def test_parse_youtube_timestamp_returns_utc_datetime():
    parsed = _parse_youtube_timestamp("2026-06-21T12:34:56Z")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.isoformat().startswith("2026-06-21T12:34:56")


def test_parse_facebook_timestamp_returns_utc_datetime():
    parsed = _parse_facebook_timestamp("2026-06-21T12:34:56+0000")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.isoformat().startswith("2026-06-21T12:34:56")


def test_workflow_video_source_type_for_platform():
    assert _video_source_type_for_platform(SocialPlatform.instagram) == VideoSourceType.instagram
    assert _video_source_type_for_platform(SocialPlatform.youtube) == VideoSourceType.youtube
    assert _video_source_type_for_platform(SocialPlatform.facebook) == VideoSourceType.facebook


def test_source_poll_error_message_marks_expired_instagram_session_as_reconnect_required():
    raw_error = (
        'Instagram media poll failed: HTTP 400: {"error":{"message":"Error validating access token: '
        'Session has expired on Monday.","type":"OAuthException","code":190}}'
    )

    assert is_reconnect_required_source_error(raw_error) is True
    assert source_poll_error_message(SocialPlatform.instagram, raw_error) == "Reconnect the Instagram source account."
    assert is_reconnect_required_source_error("Reconnect the Instagram source account.") is True
