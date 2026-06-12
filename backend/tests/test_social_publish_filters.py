from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.routes.social import _build_publish_job_list_query, list_publish_jobs


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarsResult(self._values)


class _FakeSession:
    def __init__(self, values):
        self.values = values
        self.last_query = None

    async def execute(self, query):
        self.last_query = query
        return _ExecuteResult(self.values)


def _sql_text(query) -> str:
    return str(query)


def test_build_publish_job_list_query_unfiltered():
    user_id = uuid4()

    query = _build_publish_job_list_query(user_id=user_id)

    sql = _sql_text(query)
    assert "publish_jobs.user_id" in sql
    assert "publish_jobs.export_id" not in sql
    assert "publish_jobs.publish_mode" not in sql
    assert "publish_jobs.scheduled_for >=" not in sql
    assert "publish_jobs.scheduled_for <" not in sql


def test_build_publish_job_list_query_with_scheduled_filters():
    user_id = uuid4()
    export_id = uuid4()
    now = datetime.now(timezone.utc)
    start = now + timedelta(days=1)
    end = start + timedelta(days=31)

    query = _build_publish_job_list_query(
        user_id=user_id,
        export_id=export_id,
        scheduled_only=True,
        scheduled_from=start,
        scheduled_to=end,
        future_only=True,
        now_utc=now,
    )

    sql = _sql_text(query)
    assert "publish_jobs.export_id" in sql
    assert "publish_jobs.publish_mode" in sql
    assert "publish_jobs.scheduled_for IS NOT NULL" in sql
    # Range + future constraints
    assert sql.count("publish_jobs.scheduled_for >=") == 2
    assert "publish_jobs.scheduled_for <" in sql


@pytest.mark.asyncio
async def test_list_publish_jobs_keeps_existing_behavior_without_filters():
    user = SimpleNamespace(id=uuid4())
    db = _FakeSession(values=[])

    result = await list_publish_jobs(
        export_id=None,
        scheduled_only=False,
        scheduled_from=None,
        scheduled_to=None,
        future_only=False,
        db=db,
        current_user=user,
    )

    assert result == []
    sql = _sql_text(db.last_query)
    assert "publish_jobs.user_id" in sql
    assert "publish_jobs.publish_mode" not in sql


@pytest.mark.asyncio
async def test_list_publish_jobs_applies_all_new_filters():
    user = SimpleNamespace(id=uuid4())
    db = _FakeSession(values=[])

    now = datetime.now(timezone.utc)
    start = now + timedelta(days=2)
    end = start + timedelta(days=7)

    await list_publish_jobs(
        export_id=uuid4(),
        scheduled_only=True,
        scheduled_from=start,
        scheduled_to=end,
        future_only=True,
        db=db,
        current_user=user,
    )

    sql = _sql_text(db.last_query)
    assert "publish_jobs.export_id" in sql
    assert "publish_jobs.publish_mode" in sql
    assert "publish_jobs.scheduled_for IS NOT NULL" in sql
    assert sql.count("publish_jobs.scheduled_for >=") == 2
    assert "publish_jobs.scheduled_for <" in sql
