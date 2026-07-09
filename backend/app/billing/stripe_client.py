from typing import Any

import stripe
from fastapi.concurrency import run_in_threadpool

from app.config import settings


STRIPE_API_VERSION = "2024-06-20"


class BillingConfigurationError(RuntimeError):
    pass


def validate_billing_config() -> None:
    if not settings.stripe_billing_enabled:
        return

    missing = [
        name
        for name, value in {
            "STRIPE_SECRET_KEY": settings.stripe_secret_key,
            "STRIPE_PUBLISHABLE_KEY": settings.stripe_publishable_key,
            "STRIPE_WEBHOOK_SECRET": settings.stripe_webhook_secret,
            "STRIPE_CREATOR_PRICE_ID": settings.stripe_creator_price_id,
            "STRIPE_PRO_PRICE_ID": settings.stripe_pro_price_id,
            "STRIPE_ELITE_PRICE_ID": settings.stripe_elite_price_id,
        }.items()
        if not value
    ]
    if missing:
        raise BillingConfigurationError(f"Stripe billing is enabled but missing: {', '.join(missing)}")


def configure_stripe() -> None:
    validate_billing_config()
    if settings.stripe_secret_key:
        stripe.api_key = settings.stripe_secret_key
        stripe.api_version = STRIPE_API_VERSION


def require_billing_enabled() -> None:
    if not settings.stripe_billing_enabled:
        raise BillingConfigurationError("Billing is not enabled for this environment.")
    configure_stripe()


async def create_customer(email: str, user_id: str) -> Any:
    require_billing_enabled()
    return await run_in_threadpool(
        stripe.Customer.create,
        email=email,
        metadata={"user_id": user_id},
    )


async def create_checkout_session(
    *,
    customer_id: str,
    user_id: str,
    plan: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> Any:
    require_billing_enabled()
    return await run_in_threadpool(
        stripe.checkout.Session.create,
        mode="subscription",
        customer=customer_id,
        client_reference_id=user_id,
        line_items=[{"price": price_id, "quantity": 1}],
        payment_method_collection="always",
        subscription_data={
            "trial_period_days": 7,
            "metadata": {"user_id": user_id, "plan": plan},
        },
        metadata={"user_id": user_id, "plan": plan},
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
    )


async def create_portal_session(*, customer_id: str, return_url: str) -> Any:
    require_billing_enabled()
    return await run_in_threadpool(
        stripe.billing_portal.Session.create,
        customer=customer_id,
        return_url=return_url,
    )


async def retrieve_subscription(subscription_id: str) -> Any:
    require_billing_enabled()
    return await run_in_threadpool(
        stripe.Subscription.retrieve,
        subscription_id,
        expand=["items.data.price"],
    )


async def update_subscription_price(*, subscription_id: str, price_id: str) -> Any:
    subscription = await retrieve_subscription(subscription_id)
    item_id = subscription["items"]["data"][0]["id"]
    plan = "elite" if price_id == settings.stripe_elite_price_id else "pro" if price_id == settings.stripe_pro_price_id else "creator"
    return await run_in_threadpool(
        stripe.Subscription.modify,
        subscription_id,
        items=[{"id": item_id, "price": price_id}],
        proration_behavior="create_prorations",
        metadata={"plan": plan},
    )


def construct_webhook_event(payload: bytes, signature: str) -> Any:
    require_billing_enabled()
    return stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
