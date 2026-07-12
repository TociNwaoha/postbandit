from datetime import timezone
import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.developer import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    ApiLimitsResponse,
    ApiUsageCounts,
    ApiUsageReset,
    ApiUsageResponse,
)
from app.services.api_keys import create_api_key, list_api_keys, revoke_api_key
from app.services.api_rate_limits import get_plan_limits, get_usage

router = APIRouter(prefix="/developer", tags=["developer"])


def _plan_name(user: User) -> str:
    return user.tier.value if hasattr(user.tier, "value") else str(user.tier)


@router.post("/keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_developer_key(
    body: ApiKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row, full_key = await create_api_key(db, user_id=current_user.id, name=body.name)
    return ApiKeyCreateResponse.model_validate({**ApiKeyResponse.model_validate(row).model_dump(), "full_key": full_key})


@router.get("/keys", response_model=list[ApiKeyResponse])
async def list_developer_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await list_api_keys(db, user_id=current_user.id)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_developer_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await revoke_api_key(db, user_id=current_user.id, key_id=key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/limits", response_model=ApiLimitsResponse)
async def get_developer_limits(current_user: User = Depends(get_current_user)):
    plan = _plan_name(current_user)
    return ApiLimitsResponse(plan=plan, limits=get_plan_limits(current_user.tier))


@router.get("/usage", response_model=ApiUsageResponse)
async def get_developer_usage(current_user: User = Depends(get_current_user)):
    plan = _plan_name(current_user)
    result = await get_usage(str(current_user.id), current_user.tier)
    hour_percent = round((result.current_hour / result.limit_hour) * 100, 2) if result.limit_hour else 0
    day_percent = round((result.current_day / result.limit_day) * 100, 2) if result.limit_day else 0
    return ApiUsageResponse(
        plan=plan,
        limits={"per_hour": result.limit_hour, "per_day": result.limit_day},
        usage=ApiUsageCounts(
            this_hour=result.current_hour,
            today=result.current_day,
            hour_percent=hour_percent,
            day_percent=day_percent,
            warning=result.warning,
        ),
        reset=ApiUsageReset(
            hour_resets_at=result.reset_hour.astimezone(timezone.utc),
            day_resets_at=result.reset_day.astimezone(timezone.utc),
        ),
    )
