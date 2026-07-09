from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.billing.enforcement import count_connected_platforms
from app.billing.plans import get_platforms_allowed, get_price_id
from app.billing.stripe_client import (
    BillingConfigurationError,
    create_checkout_session,
    create_customer,
    create_portal_session,
    update_subscription_price,
)
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.billing import (
    BillingCheckoutResponse,
    BillingPlanName,
    BillingPortalResponse,
    BillingStatusResponse,
    BillingUpgradeResponse,
)

router = APIRouter(prefix="/billing", tags=["billing"])


def _frontend_url(path: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}{path}"


def _billing_unavailable(exc: BillingConfigurationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
    )


async def _ensure_customer(user: User, db: AsyncSession) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id

    try:
        customer = await create_customer(email=user.email, user_id=str(user.id))
    except BillingConfigurationError as exc:
        raise _billing_unavailable(exc) from exc

    user.stripe_customer_id = customer["id"]
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.stripe_customer_id


@router.get("/status", response_model=BillingStatusResponse)
async def billing_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connected = await count_connected_platforms(db, current_user.id)
    current_user.platforms_allowed = get_platforms_allowed(
        current_user.billing_plan,
        current_user.subscription_status,
    )
    return BillingStatusResponse(
        plan_tier=current_user.billing_plan,
        subscription_status=current_user.subscription_status,
        trial_ends_at=current_user.trial_ends_at,
        billing_period_start=current_user.billing_period_start,
        billing_period_end=current_user.billing_period_end,
        platforms_allowed=current_user.platforms_allowed,
        platforms_connected=connected,
        stripe_publishable_key=settings.stripe_publishable_key if settings.stripe_billing_enabled else "",
        billing_enabled=settings.stripe_billing_enabled,
    )


@router.post("/checkout", response_model=BillingCheckoutResponse)
async def create_billing_checkout(
    plan: BillingPlanName = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer_id = await _ensure_customer(current_user, db)
    try:
        session = await create_checkout_session(
            customer_id=customer_id,
            user_id=str(current_user.id),
            plan=plan,
            price_id=get_price_id(plan),
            success_url=_frontend_url("/billing?status=checkout_success"),
            cancel_url=_frontend_url("/billing?status=checkout_cancelled"),
        )
    except BillingConfigurationError as exc:
        raise _billing_unavailable(exc) from exc

    return BillingCheckoutResponse(checkout_url=session["url"])


@router.post("/portal", response_model=BillingPortalResponse)
async def create_billing_portal(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    customer_id = await _ensure_customer(current_user, db)
    try:
        session = await create_portal_session(
            customer_id=customer_id,
            return_url=_frontend_url("/billing"),
        )
    except BillingConfigurationError as exc:
        raise _billing_unavailable(exc) from exc

    return BillingPortalResponse(portal_url=session["url"])


@router.post("/upgrade", response_model=BillingUpgradeResponse)
async def upgrade_subscription(
    plan: BillingPlanName = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start checkout before upgrading a subscription.",
        )

    try:
        subscription = await update_subscription_price(
            subscription_id=current_user.stripe_subscription_id,
            price_id=get_price_id(plan),
        )
    except BillingConfigurationError as exc:
        raise _billing_unavailable(exc) from exc

    current_user.subscription_status = subscription["status"]
    current_user.billing_plan = plan
    current_user.platforms_allowed = get_platforms_allowed(plan, current_user.subscription_status)
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return BillingUpgradeResponse(
        subscription_id=current_user.stripe_subscription_id,
        status=current_user.subscription_status,
        plan_tier=current_user.billing_plan,
    )
