from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.connected_account import ConnectedAccount, SocialPlatform
from app.services.token_refresh import get_access_token, mark_reconnect_required

logger = logging.getLogger(__name__)

EMPTY_METRICS = {
    "views": 0,
    "likes": 0,
    "comments": 0,
    "shares": 0,
    "reach": 0,
    "impressions": 0,
    "fetch_error": None,
    "raw_response": None,
}


def _metrics(**overrides: Any) -> dict[str, Any]:
    data = dict(EMPTY_METRICS)
    data.update(overrides)
    for key in ["views", "likes", "comments", "shares", "reach", "impressions"]:
        try:
            data[key] = max(0, int(data.get(key) or 0))
        except (TypeError, ValueError):
            data[key] = 0
    return data


def _maybe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return {"text": response.text[:1000]}


def _token_expired_response(platform: str, account: ConnectedAccount, db: Session, response: httpx.Response) -> bool:
    if response.status_code == 401:
        return True
    if platform in {"facebook", "instagram", "threads"} and response.status_code in {400, 401, 403}:
        payload = _maybe_json(response)
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict) and str(error.get("code")) == "190":
            mark_reconnect_required(account, db, reason="provider_token_expired")
            return True
    return False


def _request_with_refresh(
    *,
    account: ConnectedAccount,
    db: Session,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[httpx.Response | None, dict[str, Any] | None]:
    token = get_access_token(account, db)
    if not token:
        return None, _metrics(fetch_error="token_expired")

    request_headers = dict(headers or {})
    request_params = dict(params or {})
    if "{token}" in request_headers.get("Authorization", ""):
        request_headers["Authorization"] = request_headers["Authorization"].replace("{token}", token)
    elif "access_token" in request_params and request_params["access_token"] == "{token}":
        request_params["access_token"] = token

    with httpx.Client(timeout=30) as client:
        response = client.request(method, url, headers=request_headers, params=request_params, json=json_body)
        if _token_expired_response(account.platform.value, account, db, response):
            token = get_access_token(account, db, force_refresh=True)
            if not token:
                return response, _metrics(fetch_error="token_expired", raw_response=_maybe_json(response))
            request_headers = dict(headers or {})
            request_params = dict(params or {})
            if "{token}" in request_headers.get("Authorization", ""):
                request_headers["Authorization"] = request_headers["Authorization"].replace("{token}", token)
            elif "access_token" in request_params and request_params["access_token"] == "{token}":
                request_params["access_token"] = token
            response = client.request(method, url, headers=request_headers, params=request_params, json=json_body)
    return response, None


def fetch_youtube_metrics(account: ConnectedAccount, external_post_id: str, db: Session) -> dict[str, Any]:
    response, early = _request_with_refresh(
        account=account,
        db=db,
        method="GET",
        url="https://www.googleapis.com/youtube/v3/videos",
        headers={"Authorization": "Bearer {token}"},
        params={"part": "statistics", "id": external_post_id},
    )
    if early:
        return early
    assert response is not None
    payload = _maybe_json(response)
    if not response.is_success:
        return _metrics(fetch_error="permission_denied", raw_response=payload)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    stats = items[0].get("statistics", {}) if items and isinstance(items[0], dict) else {}
    return _metrics(
        views=stats.get("viewCount"),
        likes=stats.get("likeCount"),
        comments=stats.get("commentCount"),
        shares=stats.get("favoriteCount"),
        raw_response=payload,
    )


def fetch_x_metrics(account: ConnectedAccount, external_post_id: str, db: Session) -> dict[str, Any]:
    response, early = _request_with_refresh(
        account=account,
        db=db,
        method="GET",
        url=f"https://api.twitter.com/2/tweets/{external_post_id}",
        headers={"Authorization": "Bearer {token}"},
        params={"tweet.fields": "public_metrics"},
    )
    if early:
        return early
    assert response is not None
    payload = _maybe_json(response)
    if not response.is_success:
        return _metrics(fetch_error="permission_denied", raw_response=payload)
    metrics = (payload.get("data") or {}).get("public_metrics") if isinstance(payload.get("data"), dict) else {}
    return _metrics(
        likes=metrics.get("like_count"),
        comments=metrics.get("reply_count"),
        shares=(int(metrics.get("retweet_count") or 0) + int(metrics.get("quote_count") or 0)),
        raw_response=payload,
    )


def fetch_facebook_metrics(account: ConnectedAccount, external_post_id: str, db: Session) -> dict[str, Any]:
    response, early = _request_with_refresh(
        account=account,
        db=db,
        method="GET",
        url=f"https://graph.facebook.com/v21.0/{external_post_id}/insights",
        params={
            "metric": "post_impressions,post_reach,post_reactions_by_type_total,post_comments,post_shares",
            "access_token": "{token}",
        },
    )
    if early:
        return early
    assert response is not None
    payload = _maybe_json(response)
    if not response.is_success:
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict) and str(error.get("code")) == "190":
            return _metrics(fetch_error="token_expired", raw_response=payload)
        return _metrics(fetch_error="permission_denied", raw_response=payload)

    values = {item.get("name"): item.get("values", [{}])[0].get("value") for item in payload.get("data", []) if isinstance(item, dict)}
    reactions = values.get("post_reactions_by_type_total") or {}
    likes = sum(int(value or 0) for value in reactions.values()) if isinstance(reactions, dict) else 0
    return _metrics(
        views=values.get("post_impressions"),
        impressions=values.get("post_impressions"),
        reach=values.get("post_reach"),
        likes=likes,
        comments=values.get("post_comments"),
        shares=values.get("post_shares"),
        raw_response=payload,
    )


def fetch_tiktok_metrics(account: ConnectedAccount, external_post_id: str, db: Session) -> dict[str, Any]:
    response, early = _request_with_refresh(
        account=account,
        db=db,
        method="POST",
        url="https://open.tiktokapis.com/v2/video/query/",
        headers={"Authorization": "Bearer {token}", "Content-Type": "application/json"},
        params={"fields": "id,view_count,like_count,comment_count,share_count"},
        json_body={"filters": {"video_ids": [external_post_id]}},
    )
    if early:
        return early
    assert response is not None
    payload = _maybe_json(response)
    if not response.is_success:
        return _metrics(fetch_error="permission_denied", raw_response=payload)
    videos = ((payload.get("data") or {}).get("videos") or []) if isinstance(payload.get("data"), dict) else []
    video = videos[0] if videos and isinstance(videos[0], dict) else {}
    return _metrics(
        views=video.get("view_count"),
        likes=video.get("like_count"),
        comments=video.get("comment_count"),
        shares=video.get("share_count"),
        raw_response=payload,
    )


def fetch_threads_metrics(account: ConnectedAccount, external_post_id: str, db: Session) -> dict[str, Any]:
    response, early = _request_with_refresh(
        account=account,
        db=db,
        method="GET",
        url=f"https://graph.threads.net/v1.0/{external_post_id}/insights",
        params={"metric": "views,likes,replies,reposts,reach", "access_token": "{token}"},
    )
    if early:
        return early
    assert response is not None
    payload = _maybe_json(response)
    if not response.is_success:
        return _metrics(fetch_error="permission_denied", raw_response=payload)
    values = {item.get("name"): item.get("values", [{}])[0].get("value") for item in payload.get("data", []) if isinstance(item, dict)}
    return _metrics(
        views=values.get("views"),
        likes=values.get("likes"),
        comments=values.get("replies"),
        shares=values.get("reposts"),
        reach=values.get("reach"),
        raw_response=payload,
    )


def fetch_instagram_metrics(account: ConnectedAccount, external_post_id: str, db: Session) -> dict[str, Any]:
    """
    IMPORTANT IMPLEMENTATION NOTES:
    1. Uses graph.instagram.com NOT graph.facebook.com. PostBandit uses
       Instagram Login API tokens, which are incompatible with Facebook Graph
       API endpoints.
    2. Does NOT request the "impressions" metric. Meta does not support
       impressions for Reels media type; use "views" instead for video content.
    3. Verified working via API test on 2026-07-11 with the ANGELIC ACTION
       account. Confirmed metrics: views, reach, likes, comments, saved,
       shares, total_interactions, ig_reels_video_view_total_time, and
       ig_reels_avg_watch_time.
    """
    response, early = _request_with_refresh(
        account=account,
        db=db,
        method="GET",
        url=f"https://graph.instagram.com/v18.0/{external_post_id}/insights",
        params={
            "metric": (
                "views,reach,likes,comments,saved,shares,total_interactions,"
                "ig_reels_video_view_total_time,ig_reels_avg_watch_time"
            ),
            "access_token": "{token}",
        },
    )
    if early:
        return early
    assert response is not None

    payload = _maybe_json(response)
    if not response.is_success:
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict) and str(error.get("code")) == "190":
            return _metrics(fetch_error="token_expired", raw_response=payload)
        return _metrics(fetch_error="permission_denied", raw_response=payload)

    values = {
        item.get("name"): item.get("values", [{}])[0].get("value")
        for item in payload.get("data", [])
        if isinstance(item, dict)
    }
    return _metrics(
        views=values.get("views"),
        likes=values.get("likes"),
        comments=values.get("comments"),
        shares=values.get("shares"),
        reach=values.get("reach"),
        impressions=0,
        raw_response=payload,
    )


FETCHERS = {
    SocialPlatform.youtube: fetch_youtube_metrics,
    SocialPlatform.x: fetch_x_metrics,
    SocialPlatform.facebook: fetch_facebook_metrics,
    SocialPlatform.tiktok: fetch_tiktok_metrics,
    SocialPlatform.threads: fetch_threads_metrics,
    SocialPlatform.instagram: fetch_instagram_metrics,
}


def fetch_metrics_for_job(account: ConnectedAccount, external_post_id: str, db: Session) -> dict[str, Any]:
    fetcher = FETCHERS.get(account.platform)
    if not fetcher:
        return _metrics(fetch_error="not_available")
    try:
        return fetcher(account, external_post_id, db)
    except Exception as exc:
        logger.warning(
            "[analytics] fetch failed platform=%s account_id=%s reason=%s",
            account.platform.value,
            account.id,
            exc.__class__.__name__,
        )
        return _metrics(fetch_error="not_available", raw_response={"error": exc.__class__.__name__})
