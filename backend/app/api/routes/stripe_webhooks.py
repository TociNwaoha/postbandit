from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from stripe.error import SignatureVerificationError

from app.billing.stripe_client import BillingConfigurationError, construct_webhook_event
from app.billing.webhook_handlers import handle_stripe_event
from app.database import get_db
from app.models.processed_stripe_event import ProcessedStripeEvent

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    if not stripe_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe signature")

    payload = await request.body()
    try:
        event = construct_webhook_event(payload, stripe_signature)
    except BillingConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (ValueError, SignatureVerificationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe webhook") from exc

    event_id = event["id"]
    event_type = event["type"]
    existing = await db.scalar(
        select(ProcessedStripeEvent).where(ProcessedStripeEvent.event_id == event_id)
    )
    if existing:
        return {"received": True, "duplicate": True}

    await handle_stripe_event(db, event)
    db.add(ProcessedStripeEvent(event_id=event_id, event_type=event_type))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return {"received": True, "duplicate": True}

    return {"received": True}
