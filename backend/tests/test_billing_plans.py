from app.billing.plans import get_platforms_allowed, plan_from_price_id
from app.config import settings


def test_platform_limits_by_plan():
    assert get_platforms_allowed("trial", "trialing") == 3
    assert get_platforms_allowed("creator", "active") == 3
    assert get_platforms_allowed("pro", "active") == 6
    assert get_platforms_allowed("elite", "active") == 7


def test_restricted_status_blocks_new_platforms():
    assert get_platforms_allowed("pro", "past_due") == 0
    assert get_platforms_allowed("creator", "canceled") == 0


def test_plan_from_price_id(monkeypatch):
    monkeypatch.setattr(settings, "stripe_creator_price_id", "price_creator")
    monkeypatch.setattr(settings, "stripe_pro_price_id", "price_pro")
    monkeypatch.setattr(settings, "stripe_elite_price_id", "price_elite")

    assert plan_from_price_id("price_creator") == "creator"
    assert plan_from_price_id("price_pro") == "pro"
    assert plan_from_price_id("price_elite") == "elite"
    assert plan_from_price_id("price_unknown") == "trial"
