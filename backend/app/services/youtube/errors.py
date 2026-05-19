from dataclasses import dataclass


YT_SIGNIN_REQUIRED = "YT_SIGNIN_REQUIRED"
YT_BOT_VERIFICATION = "YT_BOT_VERIFICATION"
YT_PO_TOKEN_REQUIRED = "YT_PO_TOKEN_REQUIRED"
YT_NO_FORMATS = "YT_NO_FORMATS"
YT_PRIVATE_OR_MEMBERS_ONLY = "YT_PRIVATE_OR_MEMBERS_ONLY"
YT_GEO_RESTRICTED = "YT_GEO_RESTRICTED"
YT_RATE_LIMITED = "YT_RATE_LIMITED"
YT_UNKNOWN_FAILURE = "YT_UNKNOWN_FAILURE"
NON_RETRYABLE_BLOCKED_ERROR_CODES = {
    YT_SIGNIN_REQUIRED,
    YT_BOT_VERIFICATION,
    YT_PO_TOKEN_REQUIRED,
    YT_NO_FORMATS,
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


def classify_yt_dlp_error(error: Exception | str) -> YtErrorClassification:
    raw = str(error or "").strip()
    lower = raw.lower()

    def cls(code: str, user_msg: str, retryable: bool, fallback_action: str) -> YtErrorClassification:
        return YtErrorClassification(
            code=code,
            user_facing_error_message=user_msg,
            developer_debug_message=raw[:2000],
            retryable=retryable,
            fallback_action=fallback_action,
        )

    if "po token" in lower or "po-token" in lower:
        return cls(
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
        return cls(
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
        return cls(
            YT_SIGNIN_REQUIRED,
            "This video requires sign-in to download from server. Keep as embed or upload manually.",
            False,
            "embed_only",
        )
    if any(marker in lower for marker in ["private video", "members-only", "members only", "private"]):
        return cls(
            YT_PRIVATE_OR_MEMBERS_ONLY,
            "This video is private or members-only and cannot be server-imported.",
            False,
            "upload_manual",
        )
    if any(marker in lower for marker in ["geo", "country", "region", "not available in your country"]):
        return cls(
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
        return cls(
            YT_NO_FORMATS,
            "No downloadable format was available from server runtime. You can keep embed or upload manually.",
            False,
            "embed_only",
        )
    if any(marker in lower for marker in ["429", "too many requests", "rate limit"]):
        return cls(
            YT_RATE_LIMITED,
            "YouTube is rate-limiting this import right now. Please retry later.",
            True,
            "retry_later",
        )

    return cls(
        YT_UNKNOWN_FAILURE,
        "Could not import this YouTube item from server runtime.",
        True,
        "retry_later",
    )
