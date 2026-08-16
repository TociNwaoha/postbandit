import pytest
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException

from app.api.routes.auth import activate_beta_access, signup
from app.config import settings
from app.schemas.user import BetaActivationRequest, SignupRequest


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, existing_user=None):
        self._existing_user = existing_user
        self.added = None
        self.committed = False
        self.refreshed = False

    async def execute(self, _query):
        return _ScalarResult(self._existing_user)

    def add(self, entity):
        self.added = entity

    async def commit(self):
        self.committed = True

    async def refresh(self, _entity):
        _entity.id = _entity.id or uuid.uuid4()
        _entity.tier = _entity.tier or "starter"
        _entity.videos_used = _entity.videos_used or 0
        _entity.billing_plan = _entity.billing_plan or "trial"
        _entity.is_beta_tester = bool(_entity.is_beta_tester)
        _entity.created_at = _entity.created_at or datetime.now(timezone.utc)
        _entity.updated_at = _entity.updated_at or datetime.now(timezone.utc)
        self.refreshed = True


@pytest.mark.asyncio
async def test_signup_creates_user_with_hashed_password():
    db = _FakeSession(existing_user=None)
    request = SignupRequest(email="new-user@example.com", password="testpass123")

    response = await signup(request, db=db)

    assert response.user.email == "new-user@example.com"
    assert response.message == "Account created successfully"
    assert db.added is not None
    assert db.added.password_hash != "testpass123"
    assert db.added.subscription_status == "pending_checkout"
    assert db.added.platforms_allowed == 0
    assert db.added.trial_ends_at is None
    assert db.committed is True
    assert db.refreshed is True


@pytest.mark.asyncio
async def test_signup_rejects_duplicate_email():
    existing = type("ExistingUser", (), {"email": "taken@example.com"})()
    db = _FakeSession(existing_user=existing)
    request = SignupRequest(email="taken@example.com", password="testpass123")

    with pytest.raises(HTTPException) as err:
        await signup(request, db=db)

    assert err.value.status_code == 409
    assert err.value.detail == "Email is already registered"


@pytest.mark.asyncio
async def test_signup_rejects_short_password():
    db = _FakeSession(existing_user=None)
    request = SignupRequest(email="new-user@example.com", password="short")

    with pytest.raises(HTTPException) as err:
        await signup(request, db=db)

    assert err.value.status_code == 400
    assert err.value.detail == "Password must be at least 8 characters"


@pytest.mark.asyncio
async def test_signup_with_valid_beta_code_skips_checkout(monkeypatch):
    monkeypatch.setattr(settings, "beta_access_code", "shared-beta-code")
    db = _FakeSession(existing_user=None)
    request = SignupRequest(email="beta@example.com", password="testpass123", beta_access_code="shared-beta-code")

    response = await signup(request, db=db)

    assert response.user.subscription_status == "beta_active"
    assert db.added.is_beta_tester is True
    assert db.added.beta_expires_at is not None
    assert db.added.stripe_customer_id is None
    assert db.added.stripe_subscription_id is None


@pytest.mark.asyncio
async def test_beta_activation_does_not_create_stripe_objects(monkeypatch):
    monkeypatch.setattr(settings, "beta_access_code", "shared-beta-code")
    db = _FakeSession(existing_user=None)
    user = type(
        "PendingUser",
        (),
        {
            "subscription_status": "pending_checkout",
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
            "billing_plan": "trial",
            "platforms_allowed": 0,
        },
    )()

    response = await activate_beta_access(
        BetaActivationRequest(beta_access_code="shared-beta-code"),
        db=db,
        current_user=user,
    )

    assert response.message == "Beta access activated"
    assert user.subscription_status == "beta_active"
    assert user.is_beta_tester is True
    assert user.beta_expires_at is not None
    assert user.stripe_customer_id is None
    assert user.stripe_subscription_id is None
