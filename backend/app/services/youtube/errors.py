from __future__ import annotations

from dataclasses import dataclass


YT_SIGNIN_REQUIRED = "YT_SIGNIN_REQUIRED"
YT_BOT_VERIFICATION = "YT_BOT_VERIFICATION"
YT_PO_TOKEN_REQUIRED = "YT_PO_TOKEN_REQUIRED"
YT_NO_FORMATS = "YT_NO_FORMATS"
YT_PRIVATE_OR_MEMBERS_ONLY = "YT_PRIVATE_OR_MEMBERS_ONLY"
YT_GEO_RESTRICTED = "YT_GEO_RESTRICTED"
YT_RATE_LIMITED = "YT_RATE_LIMITED"
YT_UNKNOWN_FAILURE = "YT_UNKNOWN_FAILURE"
IG_PRIVATE_OR_UNAVAILABLE = "IG_PRIVATE_OR_UNAVAILABLE"
IG_RATE_LIMITED = "IG_RATE_LIMITED"
IG_UNKNOWN_FAILURE = "IG_UNKNOWN_FAILURE"
PLATFORM_DISPLAY_NAMES = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "x": "X",
    "twitch": "Twitch",
}
NON_RETRYABLE_BLOCKED_ERROR_CODES = {
    YT_SIGNIN_REQUIRED,
    YT_BOT_VERIFICATION,
    YT_PO_TOKEN_REQUIRED,
    YT_NO_FORMATS,
    IG_PRIVATE_OR_UNAVAILABLE,
}


@dataclass(frozen=True)
class YtErrorClassification:
    code: str
    user_facing_error_message: str
    developer_debug_message: str
    retryable: bool
    fallback_action: str


def is_non_retryable_blocked_error_code(code: str | None) -> bool:
    return (code or "").strip() in NON_RETRYABLE_BLOCKED_ERROR_CODES


def _classify(raw: str, code: str, user_msg: str, retryable: bool, fallback_action: str) -> YtErrorClassification:
    return YtErrorClassification(
        code=code,
        user_facing_error_message=user_msg,
        developer_debug_message=raw[:2000],
        retryable=retryable,
        fallback_action=fallback_action,
    )


def classify_yt_dlp_error(error: Exception | str) -> YtErrorClassification:
    raw = str(error or "").strip()
    lower = raw.lower()

    if "po token" in lower or "po-token" in lower:
        return _classify(
            raw,
            YT_PO_TOKEN_REQUIRED,
            "This video currently requires extra YouTube verification on server imports.",
            False,
            "embed_only",
        )
    if any(
        marker in lower
        for marker in [
            "confirm you're not a bot",
            "bot verification",
            "human verification",
            "unusual traffic",
        ]
    ):
        return _classify(
            raw,
            YT_BOT_VERIFICATION,
            "YouTube blocked server download for this item. You can keep it as embed or upload manually.",
            False,
            "embed_only",
        )
    if any(
        marker in lower
        for marker in [
            "sign in",
            "signin",
            "sign-in",
            "login required",
            "authentication required",
        ]
    ):
        return _classify(
            raw,
            YT_SIGNIN_REQUIRED,
            "This video requires sign-in to download from server. Keep as embed or upload manually.",
            False,
            "embed_only",
        )
    if any(marker in lower for marker in ["private video", "members-only", "members only", "private"]):
        return _classify(
            raw,
            YT_PRIVATE_OR_MEMBERS_ONLY,
            "This video is private or members-only and cannot be server-imported.",
            False,
            "upload_manual",
        )
    if any(marker in lower for marker in ["geo", "country", "region", "not available in your country"]):
        return _classify(
            raw,
            YT_GEO_RESTRICTED,
            "This video is geo-restricted from the server region.",
            False,
            "upload_manual",
        )
    if any(
        marker in lower
        for marker in [
            "requested format is not available",
            "no video formats",
            "no downloadable formats",
            "unable to extract",
        ]
    ):
        return _classify(
            raw,
            YT_NO_FORMATS,
            "No downloadable format was available from server runtime. You can keep embed or upload manually.",
            False,
            "embed_only",
        )
    if any(marker in lower for marker in ["429", "too many requests", "rate limit"]):
        return _classify(
            raw,
            YT_RATE_LIMITED,
            "YouTube is rate-limiting this import right now. Please retry later.",
            True,
            "retry_later",
        )

    return _classify(
        raw,
        YT_UNKNOWN_FAILURE,
        "Could not import this YouTube item from server runtime.",
        True,
        "retry_later",
    )


def classify_platform_yt_dlp_error(error: Exception | str, *, platform: str) -> YtErrorClassification:
    raw = str(error or "").strip()
    lower = raw.lower()
    platform_key = (platform or "platform").strip().lower().replace("-", "_")
    platform_code = platform_key.upper()
    platform_name = PLATFORM_DISPLAY_NAMES.get(platform_key, platform_key.replace("_", " ").title() or "this platform")

    if platform_key == "instagram":
        if any(marker in lower for marker in ["429", "too many requests", "rate limit", "rate-limit"]):
            return _classify(
                raw,
                IG_RATE_LIMITED,
                "Instagram is rate-limiting this import right now. Please retry later or upload the file directly.",
                True,
                "retry_later",
            )
        if any(
            marker in lower
            for marker in [
                "private",
                "login",
                "log in",
                "sign in",
                "signin",
                "not available",
                "unavailable",
                "requested content is not available",
                "rate-limit reached",
            ]
        ):
            return _classify(
                raw,
                IG_PRIVATE_OR_UNAVAILABLE,
                "This Instagram post is private or unavailable. PostBandit can only import public Instagram content.",
                False,
                "upload_manual",
            )
        return _classify(
            raw,
            IG_UNKNOWN_FAILURE,
            "Could not download this Instagram video. Make sure the URL is correct and the post is publicly visible.",
            True,
            "retry_later",
        )

    if any(marker in lower for marker in ["429", "too many requests", "rate limit", "rate-limit"]):
        return _classify(
            raw,
            f"{platform_code}_RATE_LIMITED",
            f"{platform_name} is rate-limiting this import right now. Please retry later or upload the file directly.",
            True,
            "retry_later",
        )

    if any(marker in lower for marker in ["live stream", "is live", "this live event", "live from"]):
        return _classify(
            raw,
            f"{platform_code}_LIVE_UNSUPPORTED",
            "Live streams cannot be imported. Try again after the stream ends and the VOD is available.",
            False,
            "upload_manual",
        )

    if platform_key == "twitch" and any(marker in lower for marker in ["subscriber", "subscribers-only", "sub-only"]):
        return _classify(
            raw,
            "TWITCH_SUBSCRIBER_ONLY",
            "This Twitch VOD is subscriber-only and cannot be imported.",
            False,
            "upload_manual",
        )

    if platform_key == "tiktok" and "copyright" in lower:
        return _classify(
            raw,
            "TIKTOK_COPYRIGHT_RESTRICTED",
            "This TikTok video is unavailable due to copyright restrictions.",
            False,
            "upload_manual",
        )

    if any(
        marker in lower
        for marker in [
            "private",
            "login required",
            "log in",
            "sign in",
            "signin",
            "authentication required",
            "not available",
            "unavailable",
            "restricted",
            "forbidden",
            "403",
            "404",
        ]
    ):
        return _classify(
            raw,
            f"{platform_code}_PRIVATE_OR_RESTRICTED",
            f"This {platform_name} content is private, restricted, or unavailable. PostBandit can only import public content.",
            False,
            "upload_manual",
        )

    return _classify(
        raw,
        f"{platform_code}_UNKNOWN_FAILURE",
        f"Could not download this {platform_name} video. Make sure the URL is correct and the content is publicly visible.",
        True,
        "retry_later",
    )


def classify_instagram_yt_dlp_error(error: Exception | str) -> YtErrorClassification:
    return classify_platform_yt_dlp_error(error, platform="instagram")
