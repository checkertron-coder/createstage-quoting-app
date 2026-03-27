"""
Stripe service — all Stripe API calls go through here.

Same pattern as gemini_client.py: centralized, testable, mockable.
Never logs keys, secrets, or customer payment data.
"""

import logging
import os
from typing import Optional

import stripe

from . import models

logger = logging.getLogger("createstage.stripe")

# --- Configuration ---

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# Price IDs — accept both naming conventions (Railway may use either)
STRIPE_PRICE_STARTER = os.environ.get("STRIPE_PRICE_STARTER") or os.environ.get("STRIPE_STARTER_PRICE_ID", "")
STRIPE_PRICE_PROFESSIONAL = os.environ.get("STRIPE_PRICE_PROFESSIONAL") or os.environ.get("STRIPE_PRO_PRICE_ID", "")
STRIPE_PRICE_SHOP = os.environ.get("STRIPE_PRICE_SHOP") or os.environ.get("STRIPE_SHOP_PRICE_ID", "")

TIER_TO_PRICE_ID = {
    "starter": STRIPE_PRICE_STARTER,
    "professional": STRIPE_PRICE_PROFESSIONAL,
    "shop": STRIPE_PRICE_SHOP,
}

# Annual price IDs
STRIPE_PRICE_STARTER_ANNUAL = os.environ.get("STRIPE_PRICE_STARTER_ANNUAL", "")
STRIPE_PRICE_PROFESSIONAL_ANNUAL = os.environ.get("STRIPE_PRICE_PROFESSIONAL_ANNUAL", "")
STRIPE_PRICE_SHOP_ANNUAL = os.environ.get("STRIPE_PRICE_SHOP_ANNUAL", "")

TIER_TO_ANNUAL_PRICE_ID = {
    "starter": STRIPE_PRICE_STARTER_ANNUAL,
    "professional": STRIPE_PRICE_PROFESSIONAL_ANNUAL,
    "shop": STRIPE_PRICE_SHOP_ANNUAL,
}

PRICE_ID_TO_TIER = {}
for _tier, _price_id in TIER_TO_PRICE_ID.items():
    if _price_id:
        PRICE_ID_TO_TIER[_price_id] = _tier
for _tier, _price_id in TIER_TO_ANNUAL_PRICE_ID.items():
    if _price_id:
        PRICE_ID_TO_TIER[_price_id] = _tier


def is_configured() -> bool:
    """Check if Stripe is configured (secret key set)."""
    return bool(STRIPE_SECRET_KEY)


def _get_client():
    """Get a configured Stripe client."""
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


def create_customer(email: str, user_id: int) -> str:
    """Create a Stripe Customer and return the customer ID."""
    client = _get_client()
    customer = client.Customer.create(
        email=email,
        metadata={"user_id": str(user_id)},
    )
    logger.info("Created Stripe customer for user %d", user_id)
    return customer.id


def create_checkout_session(
    customer_id: str,
    tier: str,
    success_url: str,
    cancel_url: str,
    billing_period: str = "monthly",
) -> str:
    """
    Create a Stripe Checkout Session for a subscription.

    Returns the checkout session URL to redirect the user to.
    """
    if billing_period == "annual":
        price_id = TIER_TO_ANNUAL_PRICE_ID.get(tier)
        if not price_id:
            logger.warning("No annual price ID for tier %s — falling back to monthly", tier)
            price_id = TIER_TO_PRICE_ID.get(tier)
    else:
        price_id = TIER_TO_PRICE_ID.get(tier)

    if not price_id:
        raise ValueError("No Stripe Price ID configured for tier: %s" % tier)

    client = _get_client()
    session = client.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
    )
    logger.info("Created checkout session for customer %s, tier %s", customer_id, tier)
    return session.url


def create_portal_session(customer_id: str, return_url: str) -> str:
    """
    Create a Stripe Customer Portal session.

    Returns the portal URL for managing billing.
    """
    client = _get_client()
    session = client.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    logger.info("Created portal session for customer %s", customer_id)
    return session.url


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """
    Verify and parse a Stripe webhook event.

    Returns the event dict. Raises ValueError on invalid signature.
    """
    if not STRIPE_WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured")

    client = _get_client()
    event = client.Webhook.construct_event(
        payload, sig_header, STRIPE_WEBHOOK_SECRET,
    )
    return event


def handle_webhook_event(event: dict, db) -> Optional[str]:
    """
    Process a Stripe webhook event. Updates user subscription state.

    Returns a short status string for logging.
    """
    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        return _handle_checkout_completed(data, db)
    elif event_type == "invoice.payment_succeeded":
        return _handle_payment_succeeded(data, db)
    elif event_type == "invoice.payment_failed":
        return _handle_payment_failed(data, db)
    elif event_type == "customer.subscription.deleted":
        return _handle_subscription_deleted(data, db)
    else:
        logger.info("Unhandled Stripe event: %s", event_type)
        return "ignored"


def _find_user_by_customer_id(customer_id: str, db) -> Optional[models.User]:
    """Look up user by stripe_customer_id."""
    return db.query(models.User).filter(
        models.User.stripe_customer_id == customer_id,
    ).first()


def _handle_checkout_completed(data: dict, db) -> str:
    """checkout.session.completed — activate subscription."""
    customer_id = data.get("customer")
    subscription_id = data.get("subscription")

    user = _find_user_by_customer_id(customer_id, db)
    if not user:
        logger.warning("Checkout completed for unknown customer: %s", customer_id)
        return "user_not_found"

    user.stripe_subscription_id = subscription_id
    user.subscription_status = "active"

    # Determine tier from the subscription's price
    tier = _resolve_tier_from_subscription(subscription_id)
    if tier:
        user.tier = tier

    db.commit()
    logger.info("Activated subscription for user %d, tier %s", user.id, user.tier)
    return "activated"


def _handle_payment_succeeded(data: dict, db) -> str:
    """invoice.payment_succeeded — keep subscription active."""
    customer_id = data.get("customer")
    user = _find_user_by_customer_id(customer_id, db)
    if not user:
        return "user_not_found"

    user.subscription_status = "active"
    # Reset monthly quote counter on successful payment
    user.quotes_this_month = 0
    from datetime import datetime
    user.billing_cycle_start = datetime.utcnow()
    db.commit()
    logger.info("Payment succeeded for user %d", user.id)
    return "payment_ok"


def _handle_payment_failed(data: dict, db) -> str:
    """invoice.payment_failed — set status to past_due."""
    customer_id = data.get("customer")
    user = _find_user_by_customer_id(customer_id, db)
    if not user:
        return "user_not_found"

    user.subscription_status = "past_due"
    db.commit()
    logger.info("Payment failed for user %d — set to past_due", user.id)
    return "past_due"


def _handle_subscription_deleted(data: dict, db) -> str:
    """customer.subscription.deleted — downgrade to free."""
    customer_id = data.get("customer")
    user = _find_user_by_customer_id(customer_id, db)
    if not user:
        return "user_not_found"

    user.subscription_status = "cancelled"
    user.tier = "free"
    user.stripe_subscription_id = None
    db.commit()
    logger.info("Subscription cancelled for user %d — downgraded to free", user.id)
    return "cancelled"


def _resolve_tier_from_subscription(subscription_id: str) -> Optional[str]:
    """Look up the tier for a subscription by checking its price ID."""
    if not subscription_id:
        return None
    try:
        client = _get_client()
        sub = client.Subscription.retrieve(subscription_id)
        items = sub.get("items", {}).get("data", [])
        if items:
            price_id = items[0].get("price", {}).get("id", "")
            return PRICE_ID_TO_TIER.get(price_id)
    except Exception as e:
        logger.warning("Failed to resolve tier for subscription %s: %s", subscription_id, e)
    return None
