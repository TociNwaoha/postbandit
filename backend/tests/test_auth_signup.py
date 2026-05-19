import pytest
from fastapi import HTTPException

from app.api.routes.auth import signup
from app.schemas.user import SignupRequest


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
