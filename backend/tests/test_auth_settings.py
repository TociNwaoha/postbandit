import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.routes.auth import delete_account, pwd_context, update_email, update_password
from app.schemas.user import DeleteAccountRequest, UpdateEmailRequest, UpdatePasswordRequest


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, execute_values=None):
        self.execute_values = list(execute_values or [])
        self.commits = 0
        self.refresh_calls = 0
        self.deleted = []

    async def execute(self, _query):
        value = self.execute_values.pop(0) if self.execute_values else None
        return _ScalarResult(value)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _entity):
        self.refresh_calls += 1

    async def delete(self, entity):
        self.deleted.append(entity)


def _user(email: str, password: str):
    now = datetime.now(timezone.utc)
    return type(
        "User",
        (),
        {
            "id": uuid.uuid4(),
            "email": email,
            "password_hash": pwd_context.hash(password),
            "tier": "starter",
            "videos_used": 0,
            "created_at": now,
            "updated_at": now,
        },
    )()


@pytest.mark.asyncio
async def test_update_email_success():
    current_user = _user("old@example.com", "correct-pass-123")
    db = _FakeSession(execute_values=[None])
    body = UpdateEmailRequest(new_email="new@example.com", current_password="correct-pass-123")

    response = await update_email(body=body, db=db, current_user=current_user)

    assert response.user.email == "new@example.com"
    assert response.message == "Email updated successfully"
    assert db.commits == 1
    assert db.refresh_calls == 1


@pytest.mark.asyncio
async def test_update_email_rejects_duplicate():
    current_user = _user("old@example.com", "correct-pass-123")
    duplicate_user = _user("new@example.com", "other-pass-123")
    db = _FakeSession(execute_values=[duplicate_user])
    body = UpdateEmailRequest(new_email="new@example.com", current_password="correct-pass-123")

    with pytest.raises(HTTPException) as err:
        await update_email(body=body, db=db, current_user=current_user)

    assert err.value.status_code == 409
    assert err.value.detail == "Email is already registered"


@pytest.mark.asyncio
async def test_update_email_rejects_wrong_password():
    current_user = _user("old@example.com", "correct-pass-123")
    db = _FakeSession()
    body = UpdateEmailRequest(new_email="new@example.com", current_password="wrong-pass")

    with pytest.raises(HTTPException) as err:
        await update_email(body=body, db=db, current_user=current_user)

    assert err.value.status_code == 401
    assert err.value.detail == "Current password is incorrect"


@pytest.mark.asyncio
async def test_update_password_success():
    current_user = _user("user@example.com", "old-password-123")
    old_hash = current_user.password_hash
    db = _FakeSession()
    body = UpdatePasswordRequest(current_password="old-password-123", new_password="new-password-123")

    response = await update_password(body=body, db=db, current_user=current_user)

    assert response.message == "Password updated successfully"
    assert current_user.password_hash != old_hash
    assert pwd_context.verify("new-password-123", current_user.password_hash)
    assert db.commits == 1


@pytest.mark.asyncio
async def test_update_password_rejects_short_password():
    current_user = _user("user@example.com", "old-password-123")
    db = _FakeSession()
    body = UpdatePasswordRequest(current_password="old-password-123", new_password="short")

    with pytest.raises(HTTPException) as err:
        await update_password(body=body, db=db, current_user=current_user)

    assert err.value.status_code == 400
    assert err.value.detail == "New password must be at least 8 characters"


@pytest.mark.asyncio
async def test_delete_account_success():
    current_user = _user("user@example.com", "old-password-123")
    db = _FakeSession()
    body = DeleteAccountRequest(current_password="old-password-123", confirm_text="DELETE")

    response = await delete_account(body=body, db=db, current_user=current_user)

    assert response.status_code == 204
    assert db.deleted == [current_user]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_delete_account_rejects_bad_confirmation():
    current_user = _user("user@example.com", "old-password-123")
    db = _FakeSession()
    body = DeleteAccountRequest(current_password="old-password-123", confirm_text="delete")

    with pytest.raises(HTTPException) as err:
        await delete_account(body=body, db=db, current_user=current_user)

    assert err.value.status_code == 400
    assert err.value.detail == "Confirmation text must be DELETE"


@pytest.mark.asyncio
async def test_delete_account_rejects_wrong_password():
    current_user = _user("user@example.com", "old-password-123")
    db = _FakeSession()
    body = DeleteAccountRequest(current_password="wrong-password", confirm_text="DELETE")

    with pytest.raises(HTTPException) as err:
        await delete_account(body=body, db=db, current_user=current_user)

    assert err.value.status_code == 401
    assert err.value.detail == "Current password is incorrect"
