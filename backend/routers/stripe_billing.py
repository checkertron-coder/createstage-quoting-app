"""
Stripe billing endpoints — checkout, webhook, portal.

- POST /api/stripe/create-checkout → creates Stripe Checkout Session, returns URL
- POST /api/stripe/webhook → Stripe webhook (signature verified, no auth)
- GET /api/stripe/portal → creates Stripe Customer Portal session, returns URL
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, stripe_service
from ..auth import get_current_user
from ..database import get_db

logger = logging.getLogger("createstage.stripe")

router = APIRouter(prefix="/stripe", tags=["stripe"])


class CreateCheckoutRequest(BaseModel):
    tier: str  # 'starter' | 'professional' | 'shop'
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@router.post("/create-checkout")
def create_checkout(
    request: CreateCheckoutRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a Stripe Checkout Session for a subscription.

    Returns { url: "https://checkout.stripe.com/..." } — redirect user there.
    """
    if not stripe_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured. Contact support.",
        )

    if request.tier not in ("starter", "professional", "shop"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tier. Choose starter, professional, or shop.",
        )

    # Ensure user has a valid Stripe customer ID
    # If stale (e.g. created in test mode, now using live key), recreate
    customer_id = current_user.stripe_customer_id
    if not customer_id:
        try:
            customer_id = stripe_service.create_customer(
                current_user.email, current_user.id,
            )
            current_user.stripe_customer_id = customer_id
            db.commit()
        except Exception as e:
            logger.error("Stripe customer creation failed: %s: %s", type(e).__name__, e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Stripe customer creation failed: %s" % str(e),
            )

    success_url = request.success_url or "/app?checkout=success"
    cancel_url = request.cancel_url or "/app?checkout=cancelled"

    # Log what we're sending to Stripe for diagnostics
    price_id = stripe_service.TIER_TO_PRICE_ID.get(request.tier, "")
    logger.info(
        "Checkout: user=%d tier=%s price_id=%s customer=%s success=%s",
        current_user.id, request.tier, price_id or "MISSING", customer_id, success_url,
    )

    try:
        checkout_url = stripe_service.create_checkout_session(
            customer_id=customer_id,
            tier=request.tier,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        # If stale customer ID (test→live switch), recreate and retry once
        if "No such customer" in str(e):
            logger.warning("Stale customer %s — recreating in live mode", customer_id)
            try:
                customer_id = stripe_service.create_customer(
                    current_user.email, current_user.id,
                )
                current_user.stripe_customer_id = customer_id
                db.commit()
                checkout_url = stripe_service.create_checkout_session(
                    customer_id=customer_id,
                    tier=request.tier,
                    success_url=success_url,
                    cancel_url=cancel_url,
                )
            except Exception as retry_err:
                logger.error("Stripe retry failed: %s: %s", type(retry_err).__name__, retry_err)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Stripe error: %s" % str(retry_err),
                )
        else:
            logger.error("Stripe checkout failed: %s: %s", type(e).__name__, e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Stripe error: %s" % str(e),
            )

    return {"url": checkout_url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe webhook endpoint. No auth — Stripe calls this directly.

    Signature is verified via STRIPE_WEBHOOK_SECRET.
    """
    if not stripe_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe not configured",
        )

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe_service.verify_webhook_signature(payload, sig_header)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )

    result = stripe_service.handle_webhook_event(event, db)
    logger.info("Webhook %s → %s", event.get("type", "?"), result)
    return {"status": "ok", "result": result}


@router.get("/portal")
def billing_portal(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a Stripe Customer Portal session for managing billing.

    Returns { url: "https://billing.stripe.com/..." } — redirect user there.
    """
    if not stripe_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured.",
        )

    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing account found. Subscribe to a plan first.",
        )

    try:
        portal_url = stripe_service.create_portal_session(
            customer_id=current_user.stripe_customer_id,
            return_url="/app",
        )
    except Exception as e:
        logger.error("Stripe portal creation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to open billing portal. Please try again.",
        )

    return {"url": portal_url}
