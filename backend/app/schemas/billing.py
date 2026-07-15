from datetime import datetime
from typing import Literal

from pydantic import BaseModel


BillingPlanName = Literal["creator", "pro", "elite"]


class BillingCheckoutResponse(BaseModel):
    checkout_url: str


class BillingPortalResponse(BaseModel):
    portal_url: str


class BillingUpgradeResponse(BaseModel):
    subscription_id: str
    status: str
    plan_tier: str


class BillingStatusResponse(BaseModel):
    plan_tier: str
    subscription_status: str
    trial_ends_at: datetime | None
    billing_period_start: datetime | None
    billing_period_end: datetime | None
    platforms_allowed: int
    platforms_connected: int
    storage_quota_bytes: int
    storage_hard_stop_bytes: int
    storage_used_bytes: int
    storage_raw_video_bytes: int
    storage_editor_asset_bytes: int
    storage_render_output_bytes: int
    storage_warning: bool
    storage_blocked: bool
    stripe_publishable_key: str
    billing_enabled: bool
