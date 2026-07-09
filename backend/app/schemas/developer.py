import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreateResponse(ApiKeyResponse):
    full_key: str
    warning: str = "Store this key securely. It will not be shown again."


class ApiLimitsResponse(BaseModel):
    plan: str
    limits: dict[str, int]


class ApiUsageCounts(BaseModel):
    this_hour: int
    today: int
    hour_percent: float
    day_percent: float
    warning: bool


class ApiUsageReset(BaseModel):
    hour_resets_at: datetime
    day_resets_at: datetime


class ApiUsageResponse(BaseModel):
    plan: str
    limits: dict[str, int]
    usage: ApiUsageCounts
    reset: ApiUsageReset
