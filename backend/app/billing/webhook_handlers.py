import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.plans import get_platforms_allowed, plan_from_price_id
from app.billing.stripe_client import retrieve_subscription
from app.models.user import User, UserTier

logger = logging.getLogger(__name__)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    if hasattr(obj, "get"):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _metadata_value(obj: Any, key: str) -> str | None:
    metadata = _get(obj, "metadata") or {}
    value = _get(metadata, key)
    return str(value) if value else None


def _from_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def _subscription_price_id(subscription: Any) -> str | None:
    items = _get(_get(subscription, "items") or {}, "data") or []
    if not items:
        return None
    price = _get(items[0], "price") or {}
    return _get(price, "id")


async def _find_user_for_customer(
    db: AsyncSession,
    *,
    customer_id: str | None,
    user_id: str | None = None,
) -> User | None:
    if user_id:
        try:
            parsed_user_id = uuid.UUID(user_id)
        except ValueError:
            parsed_user_id = None
        if parsed_user_id:
            result = await db.execute(select(User).where(User.id == parsed_user_id))
            user = result.scalar_one_or_none()
            if user:
                return user

    if customer_id:
        result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
        return result.scalar_one_or_none()

    return None


def _apply_subscription(user: User, subscription: Any) -> None:
    price_id = _subscription_price_id(subscription)
    billing_plan = _metadata_value(subscription, "plan") or plan_from_price_id(price_id)
    status = str(_get(subscription, "status") or "incomplete")

    user.stripe_subscription_id = _get(subscription, "id")
    user.billing_plan = billing_plan
    if billing_plan == "creator":
        user.tier = UserTier.creator
    elif billing_plan in {"pro", "elite"}:
        user.tier = UserTier.agency
    else:
        user.tier = UserTier.starter
    user.subscription_status = status
    user.trial_ends_at = _from_timestamp(_get(subscription, "trial_end"))
    user.billing_period_start = _from_timestamp(_get(subscription, "current_period_start"))
    user.billing_period_end = _from_timestamp(_get(subscription, "current_period_end"))
    user.platforms_allowed = get_platforms_allowed(billing_plan, status)


async def handle_checkout_session_completed(db: AsyncSession, session: Any) -> None:
    customer_id = _get(session, "customer")
    subscription_id = _get(session, "subscription")
    user_id = _get(session, "client_reference_id") or _metadata_value(session, "user_id")

    user = await _find_user_for_customer(db, customer_id=customer_id, user_id=user_id)
    if not user:
        logger.warning("Stripe checkout completed for unknown customer/user.")
        return

    user.stripe_customer_id = customer_id
    if subscription_id:
        subscription = await retrieve_subscription(subscription_id)
        _apply_subscription(user, subscription)


async def handle_subscription_updated(db: AsyncSession, subscription: Any) -> None:
    customer_id = _get(subscription, "customer")
    user_id = _metadata_value(subscription, "user_id")
    user = await _find_user_for_customer(db, customer_id=customer_id, user_id=user_id)
    if not user:
        logger.warning("Stripe subscription update for unknown customer.")
        return
    user.stripe_customer_id = customer_id
    _apply_subscription(user, subscription)


async def handle_subscription_deleted(db: AsyncSession, subscription: Any) -> None:
    await handle_subscription_updated(db, subscription)


async def handle_invoice_payment_succeeded(db: AsyncSession, invoice: Any) -> None:
    subscription_id = _get(invoice, "subscription")
    if subscription_id:
        subscription = await retrieve_subscription(subscription_id)
        await handle_subscription_updated(db, subscription)


async def handle_invoice_payment_failed(db: AsyncSession, invoice: Any) -> None:
    subscription_id = _get(invoice, "subscription")
    if subscription_id:
        subscription = await retrieve_subscription(subscription_id)
        await handle_subscription_updated(db, subscription)


async def handle_trial_will_end(db: AsyncSession, subscription: Any) -> None:
    await handle_subscription_updated(db, subscription)


async def handle_dispute_created(db: AsyncSession, charge: Any) -> None:
    customer_id = _get(charge, "customer")
    user = await _find_user_for_customer(db, customer_id=customer_id)
    if not user:
        logger.warning("Stripe dispute for unknown customer.")
        return
    user.subscription_status = "past_due"
    user.platforms_allowed = get_platforms_allowed(user.billing_plan, user.subscription_status)


async def handle_stripe_event(db: AsyncSession, event: Any) -> None:
    event_type = str(_get(event, "type") or "")
    data_object = _get(_get(event, "data") or {}, "object") or {}

    if event_type == "checkout.session.completed":
        await handle_checkout_session_completed(db, data_object)
    elif event_type == "customer.subscription.updated":
        await handle_subscription_updated(db, data_object)
    elif event_type == "customer.subscription.deleted":
        await handle_subscription_deleted(db, data_object)
    elif event_type == "customer.subscription.trial_will_end":
        await handle_trial_will_end(db, data_object)
    elif event_type == "invoice.payment_succeeded":
        await handle_invoice_payment_succeeded(db, data_object)
    elif event_type == "invoice.payment_failed":
        await handle_invoice_payment_failed(db, data_object)
    elif event_type == "charge.dispute.created":
        await handle_dispute_created(db, data_object)
