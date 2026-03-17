"""
P54: Stripe Subscription Paywall — Tests

Tests Stripe integration with mocked Stripe API calls.
Covers: webhook handling, tier enforcement, checkout flow, portal flow.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend import models
from backend.stripe_service import (
    handle_webhook_event,
    is_configured,
    TIER_TO_PRICE_ID,
    PRICE_ID_TO_TIER,
)


# --- Helpers ---

def _register(client, email="stripe@test.com", password="testpass123", invite_code=None):
    body = {"email": email, "password": password, "terms_accepted": True}
    if invite_code:
        body["invite_code"] = invite_code
    return client.post("/api/auth/register", json=body)


def _auth_headers(client, email="stripe@test.com", password="testpass123"):
    resp = _register(client, email, password)
    token = resp.json()["access_token"]
    return {"Authorization": "Bearer %s" % token}


def _seed_invite(db, code="BETA-TEST", tier="professional"):
    ic = models.InviteCode(
        code=code, tier=tier, max_uses=100, created_by="test",
    )
    db.add(ic)
    db.commit()


# === 1. Stripe service — is_configured ===

def test_stripe_not_configured_by_default():
    """Stripe should not be configured in test environment."""
    # In tests, STRIPE_SECRET_KEY is empty
    assert not is_configured()


# === 2. User model — stripe fields exist ===

def test_user_has_stripe_fields(db):
    """User model has stripe_customer_id and stripe_subscription_id."""
    user = models.User(email="stripe-fields@test.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.stripe_customer_id is None
    assert user.stripe_subscription_id is None

    user.stripe_customer_id = "cus_test123"
    user.stripe_subscription_id = "sub_test456"
    db.commit()
    db.refresh(user)
    assert user.stripe_customer_id == "cus_test123"
    assert user.stripe_subscription_id == "sub_test456"


# === 3. Webhook: checkout.session.completed ===

def test_webhook_checkout_completed(db):
    """checkout.session.completed activates subscription."""
    user = models.User(
        email="checkout@test.com",
        stripe_customer_id="cus_abc",
        tier="free",
        subscription_status="free",
    )
    db.add(user)
    db.commit()

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_abc",
                "subscription": "sub_xyz",
            }
        },
    }

    with patch("backend.stripe_service._resolve_tier_from_subscription", return_value="professional"):
        result = handle_webhook_event(event, db)

    assert result == "activated"
    db.refresh(user)
    assert user.subscription_status == "active"
    assert user.stripe_subscription_id == "sub_xyz"
    assert user.tier == "professional"


# === 4. Webhook: invoice.payment_succeeded ===

def test_webhook_payment_succeeded(db):
    """invoice.payment_succeeded keeps subscription active and resets quota."""
    user = models.User(
        email="paid@test.com",
        stripe_customer_id="cus_paid",
        tier="professional",
        subscription_status="active",
        quotes_this_month=15,
    )
    db.add(user)
    db.commit()

    event = {
        "type": "invoice.payment_succeeded",
        "data": {"object": {"customer": "cus_paid"}},
    }
    result = handle_webhook_event(event, db)

    assert result == "payment_ok"
    db.refresh(user)
    assert user.subscription_status == "active"
    assert user.quotes_this_month == 0  # Reset on payment


# === 5. Webhook: invoice.payment_failed ===

def test_webhook_payment_failed(db):
    """invoice.payment_failed sets status to past_due."""
    user = models.User(
        email="failed@test.com",
        stripe_customer_id="cus_fail",
        tier="starter",
        subscription_status="active",
    )
    db.add(user)
    db.commit()

    event = {
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_fail"}},
    }
    result = handle_webhook_event(event, db)

    assert result == "past_due"
    db.refresh(user)
    assert user.subscription_status == "past_due"


# === 6. Webhook: customer.subscription.deleted ===

def test_webhook_subscription_deleted(db):
    """customer.subscription.deleted downgrades to free."""
    user = models.User(
        email="cancel@test.com",
        stripe_customer_id="cus_cancel",
        stripe_subscription_id="sub_old",
        tier="professional",
        subscription_status="active",
    )
    db.add(user)
    db.commit()

    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_cancel"}},
    }
    result = handle_webhook_event(event, db)

    assert result == "cancelled"
    db.refresh(user)
    assert user.tier == "free"
    assert user.subscription_status == "cancelled"
    assert user.stripe_subscription_id is None


# === 7. Webhook: unknown customer ===

def test_webhook_unknown_customer(db):
    """Webhook for unknown customer returns user_not_found."""
    event = {
        "type": "invoice.payment_succeeded",
        "data": {"object": {"customer": "cus_unknown"}},
    }
    result = handle_webhook_event(event, db)
    assert result == "user_not_found"


# === 8. Webhook: unhandled event type ===

def test_webhook_unhandled_event(db):
    """Unhandled event types are ignored gracefully."""
    event = {
        "type": "some.unknown.event",
        "data": {"object": {}},
    }
    result = handle_webhook_event(event, db)
    assert result == "ignored"


# === 9. Tier enforcement: free tier limited to 1 ===

def test_free_tier_limit(client, db):
    """Free tier user gets 403 after 1 quote."""
    headers = _auth_headers(client, "free-limit@test.com")
    # Set user to free with 1 quote used
    user = db.query(models.User).filter(
        models.User.email == "free-limit@test.com"
    ).first()
    user.tier = "free"
    user.quotes_this_month = 1
    db.commit()

    resp = client.post("/api/session/start", json={
        "description": "test gate",
    }, headers=headers)
    assert resp.status_code == 403
    assert "1-quote limit" in resp.json()["detail"]


# === 10. Tier enforcement: starter limited to 3 ===

def test_starter_tier_limit(client, db):
    """Starter tier user gets 403 after 3 quotes."""
    headers = _auth_headers(client, "starter-limit@test.com")
    user = db.query(models.User).filter(
        models.User.email == "starter-limit@test.com"
    ).first()
    user.tier = "starter"
    user.quotes_this_month = 3
    db.commit()

    resp = client.post("/api/session/start", json={
        "description": "test gate",
    }, headers=headers)
    assert resp.status_code == 403
    assert "3-quote limit" in resp.json()["detail"]


# === 11. Tier enforcement: professional limited to 25 ===

def test_professional_tier_limit(client, db):
    """Professional tier user gets 403 after 25 quotes."""
    headers = _auth_headers(client, "pro-limit@test.com")
    user = db.query(models.User).filter(
        models.User.email == "pro-limit@test.com"
    ).first()
    user.tier = "professional"
    user.quotes_this_month = 25
    db.commit()

    resp = client.post("/api/session/start", json={
        "description": "test gate",
    }, headers=headers)
    assert resp.status_code == 403
    assert "25-quote limit" in resp.json()["detail"]


# === 12. Tier enforcement: shop tier unlimited ===

def test_shop_tier_unlimited(client, db):
    """Shop tier user is never quota-blocked."""
    headers = _auth_headers(client, "shop@test.com")
    user = db.query(models.User).filter(
        models.User.email == "shop@test.com"
    ).first()
    user.tier = "shop"
    user.quotes_this_month = 1000
    db.commit()

    resp = client.post("/api/session/start", json={
        "description": "test gate",
    }, headers=headers)
    # Should NOT be 403 (may be other status like 200 or 500, but not quota block)
    assert resp.status_code != 403


# === 13. Tier enforcement: past_due blocks new quotes ===

def test_past_due_blocks_quotes(client, db):
    """Past due users cannot create new quotes."""
    headers = _auth_headers(client, "pastdue@test.com")
    user = db.query(models.User).filter(
        models.User.email == "pastdue@test.com"
    ).first()
    user.tier = "professional"
    user.subscription_status = "past_due"
    user.quotes_this_month = 0
    db.commit()

    resp = client.post("/api/session/start", json={
        "description": "test gate",
    }, headers=headers)
    assert resp.status_code == 403
    assert "past due" in resp.json()["detail"].lower()


# === 14. Checkout endpoint: returns 503 when Stripe not configured ===

def test_checkout_503_when_not_configured(client, db):
    """create-checkout returns 503 when Stripe is not configured."""
    headers = _auth_headers(client, "checkout503@test.com")
    resp = client.post("/api/stripe/create-checkout", json={
        "tier": "starter",
    }, headers=headers)
    assert resp.status_code == 503


# === 15. Portal endpoint: returns 503 when Stripe not configured ===

def test_portal_503_when_not_configured(client, db):
    """portal returns 503 when Stripe is not configured."""
    headers = _auth_headers(client, "portal503@test.com")
    resp = client.get("/api/stripe/portal", headers=headers)
    assert resp.status_code == 503


# === 16. User response includes has_billing ===

def test_user_response_has_billing_field(client, db):
    """User response includes has_billing boolean."""
    headers = _auth_headers(client, "billing-field@test.com")
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "has_billing" in data
    assert data["has_billing"] is False  # No Stripe customer yet


# === 17. Beta invite code: professional tier, no payment ===

def test_beta_invite_gets_professional(client, db):
    """Beta invite code users get professional tier without payment."""
    _seed_invite(db, "BETA-PRO", "professional")
    resp = _register(client, "beta-pro@test.com", "testpass123", "BETA-PRO")
    assert resp.status_code == 200
    user_data = resp.json()["user"]
    assert user_data["tier"] == "professional"
    assert user_data["subscription_status"] == "active"


# === 18. Free→paid→cancelled flow ===

def test_free_to_paid_to_cancelled(db):
    """Full lifecycle: free → checkout → active → cancel → free."""
    user = models.User(
        email="lifecycle@test.com",
        stripe_customer_id="cus_lifecycle",
        tier="free",
        subscription_status="free",
    )
    db.add(user)
    db.commit()

    # Step 1: Checkout completed → active
    checkout_event = {
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_lifecycle", "subscription": "sub_life"}},
    }
    with patch("backend.stripe_service._resolve_tier_from_subscription", return_value="starter"):
        handle_webhook_event(checkout_event, db)

    db.refresh(user)
    assert user.tier == "starter"
    assert user.subscription_status == "active"

    # Step 2: Payment succeeded — reset quota
    pay_event = {
        "type": "invoice.payment_succeeded",
        "data": {"object": {"customer": "cus_lifecycle"}},
    }
    handle_webhook_event(pay_event, db)
    db.refresh(user)
    assert user.quotes_this_month == 0

    # Step 3: Subscription deleted → free
    cancel_event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_lifecycle"}},
    }
    handle_webhook_event(cancel_event, db)
    db.refresh(user)
    assert user.tier == "free"
    assert user.subscription_status == "cancelled"


# === 19. Webhook endpoint requires signature (returns 400 without) ===

def test_webhook_endpoint_rejects_no_signature(client):
    """Webhook endpoint returns 400/503 without valid signature."""
    resp = client.post("/api/stripe/webhook", content=b'{}', headers={
        "stripe-signature": "invalid",
    })
    # 503 because Stripe not configured, or 400 for bad signature
    assert resp.status_code in (400, 503)


# === 20. Checkout rejects invalid tier ===

def test_checkout_rejects_invalid_tier(client, db):
    """create-checkout rejects invalid tier names."""
    headers = _auth_headers(client, "bad-tier@test.com")
    # Even though Stripe isn't configured, the tier check happens first...
    # Actually Stripe check happens first (503), so let's mock it
    with patch("backend.stripe_service.is_configured", return_value=True):
        resp = client.post("/api/stripe/create-checkout", json={
            "tier": "enterprise",  # Not a valid tier
        }, headers=headers)
    assert resp.status_code == 400
    assert "Invalid tier" in resp.json()["detail"]
