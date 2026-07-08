from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.user import UserTier


_ALLOWED_ROLES = {"creator", "founder", "agency", "team"}


class OnboardingStatusResponse(BaseModel):
    completed_at: datetime | None
    skipped_at: datetime | None
    role: str | None
    tier: UserTier
    metadata: dict[str, Any]
    should_onboard: bool


class OnboardingProfilePatch(BaseModel):
    role: str | None = Field(default=None, max_length=50)
    tier: UserTier | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in _ALLOWED_ROLES:
            raise ValueError("Invalid onboarding role")
        return normalized
