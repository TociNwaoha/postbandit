from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.models.connected_account import ConnectedAccount, SocialPlatform
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.social.base import ProviderOperationError, utcnow
from app.services.social.instagram import ensure_instagram_account_token
from app.services.social.tiktok import TikTokAdapter
from app.services.social.threads import _refresh_long_lived_token as refresh_threads_long_lived_token
from app.services.social.x import XAdapter
from app.services.social.youtube import YouTubeAdapter

logger = logging.getLogger(__name__)
REFRESH_WINDOW = timedelta(minutes=5)


def _is_expiring_soon(account: ConnectedAccount) -> bool:
    if account.token_expires_at is None:
        return False
    expires_at = account.token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= (utcnow() + REFRESH_WINDOW)


def mark_reconnect_required(account: ConnectedAccount, db: Session, *, reason: str | None = None) -> None:
    account.token_expired = True
    metadata = dict(account.metadata_json or {})
    metadata["token_status"] = "reconnect_required"
    if reason:
        metadata["token_error"] = reason[:250]
    account.metadata_json = metadata
    db.add(account)
    db.commit()


def clear_reconnect_required(account: ConnectedAccount, db: Session) -> None:
    account.token_expired = False
    account.last_token_refresh = datetime.now(timezone.utc)
    metadata = dict(account.metadata_json or {})
    metadata.pop("token_status", None)
    metadata.pop("token_error", None)
    account.metadata_json = metadata
    db.add(account)
    db.commit()


def _store_refreshed_token(
    account: ConnectedAccount,
    db: Session,
    *,
    access_token: str,
    refresh_token: str | None = None,
    token_expires_at: datetime | None = None,
) -> str:
    account.access_token_encrypted = encrypt_secret(access_token)
    if refresh_token:
        account.refresh_token_encrypted = encrypt_secret(refresh_token)
    if token_expires_at:
        account.token_expires_at = token_expires_at
    clear_reconnect_required(account, db)
    return access_token


def refresh_connected_account_token(account: ConnectedAccount, db: Session) -> str | None:
    try:
        if account.platform == SocialPlatform.youtube:
            if not account.refresh_token_encrypted:
                mark_reconnect_required(account, db, reason="missing_refresh_token")
                return None
            refresh_token = decrypt_secret(account.refresh_token_encrypted)
            access_token, expires_at = YouTubeAdapter()._refresh_access_token(refresh_token)
            return _store_refreshed_token(account, db, access_token=access_token, token_expires_at=expires_at)

        if account.platform == SocialPlatform.x:
            if not account.refresh_token_encrypted:
                mark_reconnect_required(account, db, reason="missing_refresh_token")
                return None
            refresh_token = decrypt_secret(account.refresh_token_encrypted)
            access_token, new_refresh_token, expires_at = XAdapter()._refresh_access_token(refresh_token)
            return _store_refreshed_token(
                account,
                db,
                access_token=access_token,
                refresh_token=new_refresh_token,
                token_expires_at=expires_at,
            )

        if account.platform == SocialPlatform.tiktok:
            if not account.refresh_token_encrypted:
                mark_reconnect_required(account, db, reason="missing_refresh_token")
                return None
            refresh_token = decrypt_secret(account.refresh_token_encrypted)
            with httpx.Client(timeout=30) as client:
                payload = TikTokAdapter()._refresh_token(client, refresh_token=refresh_token)
            access_token = str(payload.get("access_token") or "").strip()
            if not access_token:
                raise ProviderOperationError("TikTok refresh token response missing access token")
            new_refresh_token = str(payload.get("refresh_token") or "").strip() or None
            expires_in = payload.get("expires_in")
            expires_at = utcnow() + timedelta(seconds=int(expires_in)) if isinstance(expires_in, (int, float)) else None
            return _store_refreshed_token(
                account,
                db,
                access_token=access_token,
                refresh_token=new_refresh_token,
                token_expires_at=expires_at,
            )

        if account.platform == SocialPlatform.instagram:
            access_token = ensure_instagram_account_token(account)
            clear_reconnect_required(account, db)
            return access_token

        if account.platform == SocialPlatform.threads:
            current_token = decrypt_secret(account.access_token_encrypted)
            with httpx.Client(timeout=30) as client:
                access_token, expires_at = refresh_threads_long_lived_token(client, access_token=current_token)
            return _store_refreshed_token(account, db, access_token=access_token, token_expires_at=expires_at)

        mark_reconnect_required(account, db, reason="refresh_not_supported")
        return None
    except Exception as exc:
        logger.warning(
            "[token_refresh] refresh failed platform=%s account_id=%s reason=%s",
            account.platform.value,
            account.id,
            exc.__class__.__name__,
        )
        mark_reconnect_required(account, db, reason=exc.__class__.__name__)
        return None


def get_access_token(account: ConnectedAccount, db: Session, *, force_refresh: bool = False) -> str | None:
    if account.token_expired and not force_refresh:
        return None
    if force_refresh or _is_expiring_soon(account):
        return refresh_connected_account_token(account, db)
    try:
        return decrypt_secret(account.access_token_encrypted)
    except Exception as exc:
        mark_reconnect_required(account, db, reason=exc.__class__.__name__)
        return None
