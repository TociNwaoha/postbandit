from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.onboarding import OnboardingProfilePatch, OnboardingStatusResponse

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _status(user: User) -> OnboardingStatusResponse:
    return OnboardingStatusResponse(
        completed_at=user.onboarding_completed_at,
        skipped_at=user.onboarding_skipped_at,
        role=user.onboarding_role,
        tier=user.tier,
        metadata=user.onboarding_metadata_json or {},
        should_onboard=user.onboarding_completed_at is None and user.onboarding_skipped_at is None,
    )


@router.get("/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(current_user: User = Depends(get_current_user)):
    return _status(current_user)


@router.patch("/profile", response_model=OnboardingStatusResponse)
async def update_onboarding_profile(
    body: OnboardingProfilePatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.role is not None:
        current_user.onboarding_role = body.role
    if body.tier is not None:
        current_user.tier = body.tier
    if body.metadata is not None:
        current_user.onboarding_metadata_json = body.metadata

    await db.commit()
    await db.refresh(current_user)
    return _status(current_user)


@router.post("/complete", response_model=OnboardingStatusResponse)
async def complete_onboarding(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.onboarding_completed_at = datetime.now(timezone.utc)
    current_user.onboarding_skipped_at = None
    await db.commit()
    await db.refresh(current_user)
    return _status(current_user)


@router.post("/skip", response_model=OnboardingStatusResponse)
async def skip_onboarding(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.onboarding_skipped_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(current_user)
    return _status(current_user)
