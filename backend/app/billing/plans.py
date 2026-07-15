from dataclasses import dataclass
from typing import Literal

from app.config import settings


PlanTier = Literal["trial", "creator", "pro", "elite"]


@dataclass(frozen=True)
class BillingPlan:
    tier: str
    name: str
    monthly_price_cents: int
    platforms_allowed: int
    storage_quota_bytes: int
    storage_hard_stop_bytes: int
    description: str


PLATFORM_COUNT_ALL = 7
GB = 1024 * 1024 * 1024

PLANS: dict[str, BillingPlan] = {
    "trial": BillingPlan(
        tier="trial",
        name="Trial",
        monthly_price_cents=0,
        platforms_allowed=5,
        storage_quota_bytes=5 * GB,
        storage_hard_stop_bytes=6 * GB,
        description="7-day trial with card required at signup.",
    ),
    "creator": BillingPlan(
        tier="creator",
        name="Creator",
        monthly_price_cents=1800,
        platforms_allowed=5,
        storage_quota_bytes=5 * GB,
        storage_hard_stop_bytes=6 * GB,
        description="Creator plan with 5 connected social platforms.",
    ),
    "pro": BillingPlan(
        tier="pro",
        name="Pro",
        monthly_price_cents=4900,
        platforms_allowed=10,
        storage_quota_bytes=25 * GB,
        storage_hard_stop_bytes=30 * GB,
        description="Pro plan with 10 connected social platforms.",
    ),
    "elite": BillingPlan(
        tier="elite",
        name="Elite",
        monthly_price_cents=25000,
        platforms_allowed=PLATFORM_COUNT_ALL,
        storage_quota_bytes=100 * GB,
        storage_hard_stop_bytes=120 * GB,
        description="Elite plan with every supported social platform.",
    ),
    "past_due": BillingPlan(
        tier="past_due",
        name="Past Due",
        monthly_price_cents=0,
        platforms_allowed=0,
        storage_quota_bytes=0,
        storage_hard_stop_bytes=0,
        description="Payment issue. Billing must be resolved to continue connecting platforms.",
    ),
    "cancelled": BillingPlan(
        tier="cancelled",
        name="Cancelled",
        monthly_price_cents=0,
        platforms_allowed=0,
        storage_quota_bytes=0,
        storage_hard_stop_bytes=0,
        description="Subscription cancelled.",
    ),
    "expired": BillingPlan(
        tier="expired",
        name="Expired",
        monthly_price_cents=0,
        platforms_allowed=0,
        storage_quota_bytes=0,
        storage_hard_stop_bytes=0,
        description="Trial expired.",
    ),
}


def _effective_plan(plan_tier: str, subscription_status: str | None = None) -> BillingPlan:
    if subscription_status in {"past_due", "unpaid", "incomplete_expired"}:
        return PLANS["past_due"]
    if subscription_status == "canceled":
        return PLANS["cancelled"]
    return PLANS.get(plan_tier, PLANS["trial"])


def get_platforms_allowed(plan_tier: str, subscription_status: str | None = None) -> int:
    return _effective_plan(plan_tier, subscription_status).platforms_allowed


def get_storage_limits(plan_tier: str, subscription_status: str | None = None) -> tuple[int, int]:
    plan = _effective_plan(plan_tier, subscription_status)
    return plan.storage_quota_bytes, plan.storage_hard_stop_bytes


def storage_hard_stop_from_quota_bytes(quota_bytes: int) -> int:
    if quota_bytes <= 0:
        return 0
    return int(quota_bytes * 1.2)


def get_price_id(plan: str) -> str:
    if plan == "creator":
        return settings.stripe_creator_price_id
    if plan == "pro":
        return settings.stripe_pro_price_id
    if plan == "elite":
        return settings.stripe_elite_price_id
    raise ValueError("Unsupported billing plan")


def plan_from_price_id(price_id: str | None) -> str:
    if price_id and price_id == settings.stripe_creator_price_id:
        return "creator"
    if price_id and price_id == settings.stripe_pro_price_id:
        return "pro"
    if price_id and price_id == settings.stripe_elite_price_id:
        return "elite"
    return "trial"
