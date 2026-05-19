from app.services.youtube.errors import (
    YT_BOT_VERIFICATION,
    YT_GEO_RESTRICTED,
    YT_NO_FORMATS,
    YT_PO_TOKEN_REQUIRED,
    YT_PRIVATE_OR_MEMBERS_ONLY,
    YT_RATE_LIMITED,
    YT_SIGNIN_REQUIRED,
    YT_UNKNOWN_FAILURE,
    classify_yt_dlp_error,
)


def test_classify_signin_required():
    result = classify_yt_dlp_error("Sign in to confirm you’re not a bot")
    assert result.code in {YT_SIGNIN_REQUIRED, YT_BOT_VERIFICATION}
    assert result.fallback_action == "embed_only"


def test_classify_po_token():
    result = classify_yt_dlp_error("This content requires a PO Token")
    assert result.code == YT_PO_TOKEN_REQUIRED
    assert result.fallback_action == "embed_only"


def test_classify_no_formats():
    result = classify_yt_dlp_error("Requested format is not available")
    assert result.code == YT_NO_FORMATS
    assert result.fallback_action == "embed_only"


def test_classify_private():
    result = classify_yt_dlp_error("Private video. Sign in if you've been granted access.")
    assert result.code == YT_PRIVATE_OR_MEMBERS_ONLY
    assert result.fallback_action == "upload_manual"


def test_classify_geo():
    result = classify_yt_dlp_error("The uploader has not made this video available in your country")
    assert result.code == YT_GEO_RESTRICTED
    assert result.fallback_action == "upload_manual"


def test_classify_rate_limit():
    result = classify_yt_dlp_error("HTTP Error 429: Too Many Requests")
    assert result.code == YT_RATE_LIMITED
    assert result.retryable is True
    assert result.fallback_action == "retry_later"


def test_classify_unknown():
    result = classify_yt_dlp_error("some unexpected extractor blow-up")
    assert result.code == YT_UNKNOWN_FAILURE

