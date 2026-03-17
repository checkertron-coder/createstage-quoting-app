"""
P55: Kill Free Trial, Enforce Payment-First — Tests

Covers: trial removal, subscription_status defaults, quotes_this_month
increment, free tier quota enforcement, preview mode flag, landing page
button text, legacy trial status handling.
"""

from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend import models
from backend.stripe_service import create_checkout_session


# --- Helpers ---

def _register(client, email="p55@test.com", password="testpass123", invite_code=None):
    body = {"email": email, "password": password, "terms_accepted": True}
    if invite_code:
        body["invite_code"] = invite_code
    return client.post("/api/auth/register", json=body)


def _seed_code(db, code, tier="professional", max_uses=100):
    ic = models.InviteCode(
        code=code, tier=tier, max_uses=max_uses, uses=0, created_by="test",
    )
    db.add(ic)
    db.commit()


def _auth(client, email="p55@test.com", password="testpass123"):
    resp = _register(client, email, password)
    assert resp.status_code == 200
    return {"Authorization": "Bearer " + resp.json()["access_token"]}


# === 1. Registration without invite code → free status, no trial_ends_at ===

def test_register_no_code_is_free(client):
    """New user without invite code gets subscription_status='free', no trial."""
    resp = _register(client)
    user = resp.json()["user"]
    assert user["subscription_status"] == "free"
    assert user["tier"] == "free"
    assert user["trial_ends_at"] is None


# === 2. Registration with invite code → active status, professional tier ===

def test_register_with_code_is_active(client, db):
    """Beta invite code user gets subscription_status='active'."""
    _seed_code(db, "P55-BETA", "professional")
    resp = _register(client, "beta55@test.com", "testpass123", "P55-BETA")
    user = resp.json()["user"]
    assert user["subscription_status"] == "active"
    assert user["tier"] == "professional"
    assert user["trial_ends_at"] is None


# === 3. quotes_this_month incremented on /price ===

def test_quotes_counter_incremented(client, db):
    """Running the full pipeline to /price increments quotes_this_month."""
    headers = _auth(client, "counter@test.com")
    # Set user to professional so pipeline isn't blocked
    user = db.query(models.User).filter(models.User.email == "counter@test.com").first()
    user.tier = "professional"
    user.subscription_status = "active"
    db.commit()
    assert user.quotes_this_month == 0

    # Start session
    resp = client.post("/api/session/start", json={
        "description": "10 foot cantilever gate"
    }, headers=headers)
    assert resp.status_code == 200
    sid = resp.json()["session_id"]

    # Answer required fields
    client.post(f"/api/session/{sid}/answer", json={
        "answers": {"clear_width": "10", "height": "6", "frame_material": "steel",
                     "post_count": "2", "infill_style": "Solid Sheet",
                     "finish": "Raw (No Finish)", "has_motor": "No",
                     "installation_type": "In-Shop Pickup"}
    }, headers=headers)

    # Calculate, estimate, price
    client.post(f"/api/session/{sid}/calculate", headers=headers)
    client.post(f"/api/session/{sid}/estimate", headers=headers)
    resp = client.post(f"/api/session/{sid}/price", headers=headers)
    assert resp.status_code == 200

    db.refresh(user)
    assert user.quotes_this_month == 1


# === 4. Free tier blocked after 1 quote ===

def test_free_tier_blocked_after_one(client, db):
    """Free user with quotes_this_month=1 gets 403 on /start."""
    headers = _auth(client, "blocked@test.com")
    user = db.query(models.User).filter(models.User.email == "blocked@test.com").first()
    user.quotes_this_month = 1
    db.commit()

    resp = client.post("/api/session/start", json={
        "description": "small table"
    }, headers=headers)
    assert resp.status_code == 403
    assert "limit" in resp.json()["detail"].lower() or "quota" in resp.json()["detail"].lower() or "reached" in resp.json()["detail"].lower()


# === 5. Legacy "trial" status treated as free ===

def test_legacy_trial_treated_as_free(client, db):
    """Existing user with subscription_status='trial', tier='free' is treated as free."""
    headers = _auth(client, "legacy@test.com")
    user = db.query(models.User).filter(models.User.email == "legacy@test.com").first()
    user.subscription_status = "trial"
    user.tier = "free"
    user.quotes_this_month = 1
    db.commit()

    resp = client.post("/api/session/start", json={
        "description": "gate"
    }, headers=headers)
    assert resp.status_code == 403


# === 6. Professional tier with legacy "trial" status still works ===

def test_professional_with_trial_status_ok(client, db):
    """User with tier=professional, subscription_status=trial can still quote."""
    headers = _auth(client, "protrial@test.com")
    user = db.query(models.User).filter(models.User.email == "protrial@test.com").first()
    user.subscription_status = "trial"
    user.tier = "professional"
    user.quotes_this_month = 5
    db.commit()

    resp = client.post("/api/session/start", json={
        "description": "10 foot gate"
    }, headers=headers)
    assert resp.status_code == 200


# === 7. Stripe checkout has no trial_period_days ===

def test_checkout_no_trial_period(db):
    """create_checkout_session does not pass trial_period_days to Stripe."""
    mock_stripe = MagicMock()
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test"
    mock_stripe.checkout.Session.create.return_value = mock_session

    with patch("backend.stripe_service._get_client", return_value=mock_stripe), \
         patch("backend.stripe_service.TIER_TO_PRICE_ID", {"starter": "price_test"}):
        url = create_checkout_session("cus_test", "starter", "/ok", "/cancel")

    assert url == "https://checkout.stripe.com/test"
    call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
    # No trial — subscription_data should not be in kwargs
    assert "subscription_data" not in call_kwargs


# === 8. Landing page says "Subscribe" not "Start Free Trial" ===

def test_landing_page_subscribe_buttons(client):
    """Pricing buttons say 'Subscribe', not 'Start Free Trial'."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert "Start Free Trial" not in html
    assert "Subscribe" in html


# === 9. Provisional account claim with invite code → active ===

def test_provisional_claim_with_code_active(client, db):
    """Claiming a provisional account with invite code sets status='active'."""
    # Create provisional user first (register without password via invite code)
    _seed_code(db, "P55-CLAIM", "professional")

    # Register with invite code
    resp = client.post("/api/auth/register", json={
        "email": "claim@test.com",
        "invite_code": "P55-CLAIM",
        "terms_accepted": True,
    })
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["subscription_status"] == "active"
    assert user["tier"] == "professional"
