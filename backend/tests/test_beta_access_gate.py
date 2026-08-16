from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.api.deps import get_current_user
from app.api.routes.auth import create_access_token
from app.models.user import User


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, user):
        self.user = user
        self.commits = 0

    async def execute(self, _query):
        return _ScalarResult(self.user)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_expired_beta_access_transitions_to_pending_checkout():
    user = User(
        id=uuid.uuid4(),
        email="expired-beta@example.com",
        password_hash="hash",
        subscription_status="beta_active",
        is_beta_tester=True,
        beta_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        platforms_allowed=5,
    )
    db = _FakeSession(user)
    request = Request({"type": "http", "method": "GET", "path": "/api/videos", "headers": []})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token(str(user.id)))

    with pytest.raises(HTTPException) as err:
        await get_current_user(request=request, credentials=credentials, db=db)

    assert err.value.status_code == 403
    assert user.subscription_status == "pending_checkout"
    assert user.platforms_allowed == 0
    assert user.is_beta_tester is True
    assert db.commits == 1
