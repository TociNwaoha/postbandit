import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.plans import get_platforms_allowed
from app.models.connected_account import ConnectedAccount, SocialPlatform
from app.models.user import User


async def count_connected_platforms(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(func.distinct(ConnectedAccount.platform))).where(ConnectedAccount.user_id == user_id)
    )
    return int(result.scalar() or 0)


async def user_has_platform(db: AsyncSession, user_id: uuid.UUID, platform: SocialPlatform) -> bool:
    result = await db.execute(
        select(ConnectedAccount.id)
        .where(ConnectedAccount.user_id == user_id, ConnectedAccount.platform == platform)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def enforce_platform_limit(
    *,
    db: AsyncSession,
    user: User,
    platform: SocialPlatform,
) -> None:
    if await user_has_platform(db, user.id, platform):
        return

    limit = get_platforms_allowed(user.billing_plan, user.subscription_status)
    current = await count_connected_platforms(db, user.id)
    if current < limit:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "platform_limit_reached",
            "message": "You have reached your connected platform limit. Upgrade billing to connect more platforms.",
            "current_platforms": current,
            "platforms_allowed": limit,
            "plan_tier": user.billing_plan,
        },
    )
