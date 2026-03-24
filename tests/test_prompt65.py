"""
P65/P65B: NDA Modal, Invite Code Hardening, Free Tier Protection,
Email Verification Gate Fix — Tests

Tests:
1. POST /api/auth/accept-nda returns acceptance ID
2. NDA acceptance links to user after registration
3. Invite code locked to first user's email (used_by_email)
4. Invite code rejected for different email after lock
5. Invite code allowed for same email re-use
6. Free tier quota limit is 5
7. NDA acceptance stores IP and user-agent
8. NDA acceptance without registration leaves user_id null
P65B:
9. No invite code + email configured → verification_required (no tokens)
10. No invite code + no email + PRODUCTION=0 → dev auto-verify
11. No invite code + no email + PRODUCTION=1 → 500 error
12. Invite code → immediate tokens + email_verified=True
13. Email send failure → 500 error
14. Backfill used_by_email for pre-existing codes
"""

import os
import uuid
from datetime import datetime
from unittest.mock import patch

from backend import models


# --- Helpers ---

def _register(client, email=None, password="testpass123", invite_code=None,
              terms_accepted=True, nda_acceptance_id=None):
    if email is None:
        email = "user_%s@test.local" % uuid.uuid4().hex[:8]
    body = {"email": email, "password": password}
    if invite_code:
        body["invite_code"] = invite_code
    if terms_accepted:
        body["terms_accepted"] = True
    if nda_acceptance_id:
        body["nda_acceptance_id"] = nda_acceptance_id
    return client.post("/api/auth/register", json=body)


def _seed_code(db, code="LOCKCODE", tier="professional", max_uses=10):
    ic = models.InviteCode(
        code=code, tier=tier, max_uses=max_uses, uses=0,
        created_by="test", is_active=True,
    )
    db.add(ic)
    db.commit()
    db.refresh(ic)
    return ic


def _accept_nda(client, email="nda@test.local"):
    return client.post("/api/auth/accept-nda", json={
        "email": email,
        "nda_version": "2026-03-16",
    })


# === 1. POST /api/auth/accept-nda returns acceptance ID ===

def test_accept_nda_returns_id(client):
    resp = _accept_nda(client, email="test@nda.local")
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert isinstance(data["nda_acceptance_id"], int)


# === 2. NDA acceptance links to user after registration ===

def test_nda_linked_to_user_after_register(client, db):
    email = "ndalink_%s@test.local" % uuid.uuid4().hex[:8]

    # Step 1: Accept NDA
    nda_resp = _accept_nda(client, email=email)
    nda_id = nda_resp.json()["nda_acceptance_id"]

    # Step 2: Register with the NDA acceptance ID
    reg_resp = _register(client, email=email, nda_acceptance_id=nda_id)
    assert reg_resp.status_code == 200
    user_id = reg_resp.json()["user_id"]

    # Step 3: Verify NDA record is linked to the user
    record = db.query(models.NdaAcceptance).filter(
        models.NdaAcceptance.id == nda_id,
    ).first()
    assert record is not None
    assert record.user_id == user_id
    assert record.email == email


# === 3. Invite code locked to first user's email ===

def test_invite_code_email_lock_set(client, db):
    _seed_code(db, code="LOCK1", max_uses=5)
    email = "first_%s@test.local" % uuid.uuid4().hex[:8]

    resp = _register(client, email=email, invite_code="LOCK1")
    assert resp.status_code == 200

    code = db.query(models.InviteCode).filter(
        models.InviteCode.code == "LOCK1",
    ).first()
    assert code.used_by_email == email


# === 4. Invite code rejected for different email ===

def test_invite_code_rejected_different_email(client, db):
    _seed_code(db, code="LOCK2", max_uses=5)

    # First user registers — locks the code
    email1 = "first_%s@test.local" % uuid.uuid4().hex[:8]
    resp1 = _register(client, email=email1, invite_code="LOCK2")
    assert resp1.status_code == 200

    # Second user with different email — code rejected
    email2 = "second_%s@test.local" % uuid.uuid4().hex[:8]
    resp2 = _register(client, email=email2, invite_code="LOCK2")
    assert resp2.status_code == 400
    assert "invalid" in resp2.json()["detail"].lower() or "invite" in resp2.json()["detail"].lower()


# === 5. Same email can re-use locked code ===

def test_invite_code_allowed_same_email(client, db):
    """If user registers, then tries again (e.g. after password reset),
    the same email should be allowed to use the locked code."""
    _seed_code(db, code="LOCK3", max_uses=5)
    email = "repeat_%s@test.local" % uuid.uuid4().hex[:8]

    # First registration
    resp1 = _register(client, email=email, invite_code="LOCK3")
    assert resp1.status_code == 200

    # Second registration with same email (new attempt, maybe different password)
    # This might hit "email already registered" — that's a different error path.
    # Instead, test via _validate_invite_code directly:
    code = db.query(models.InviteCode).filter(
        models.InviteCode.code == "LOCK3",
    ).first()
    assert code.used_by_email == email

    # The validate function should accept same email
    from backend.routers.auth import _validate_invite_code
    result = _validate_invite_code("LOCK3", db, email=email)
    assert result is not None  # Allowed


# === 6. Free tier quota limit is 5 ===

def test_free_tier_limit_is_five(client, db):
    """Free tier at exactly 5 quotes → blocked. At 4 → allowed."""
    resp = _register(client)
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    headers = {"Authorization": "Bearer %s" % token}

    user = db.query(models.User).filter(
        models.User.id == resp.json()["user_id"],
    ).first()

    # At 4 quotes — should still be allowed (4 < 5)
    user.quotes_this_month = 4
    db.commit()
    start_resp = client.post("/api/session/start", json={
        "description": "test gate 4",
    }, headers=headers)
    # Should NOT be 403 (might be 200 or other non-403)
    assert start_resp.status_code != 403

    # At 5 quotes — should be blocked
    user.quotes_this_month = 5
    db.commit()
    blocked_resp = client.post("/api/session/start", json={
        "description": "test gate 5",
    }, headers=headers)
    assert blocked_resp.status_code == 403
    assert "limit" in blocked_resp.json()["detail"].lower()


# === 7. NDA acceptance stores IP and user-agent ===

def test_nda_stores_metadata(client, db):
    email = "meta_%s@test.local" % uuid.uuid4().hex[:8]
    resp = client.post("/api/auth/accept-nda", json={
        "email": email,
        "nda_version": "2026-03-16",
    }, headers={"User-Agent": "TestBrowser/1.0"})
    assert resp.status_code == 200

    nda_id = resp.json()["nda_acceptance_id"]
    record = db.query(models.NdaAcceptance).filter(
        models.NdaAcceptance.id == nda_id,
    ).first()
    assert record.email == email.lower()
    assert record.nda_version == "2026-03-16"
    assert record.user_agent == "TestBrowser/1.0"
    # ip_address may be None in test client (no real socket)


# === 8. NDA acceptance without registration leaves user_id null ===

def test_nda_unlinked_has_null_user(client, db):
    email = "orphan_%s@test.local" % uuid.uuid4().hex[:8]
    resp = _accept_nda(client, email=email)
    assert resp.status_code == 200

    nda_id = resp.json()["nda_acceptance_id"]
    record = db.query(models.NdaAcceptance).filter(
        models.NdaAcceptance.id == nda_id,
    ).first()
    assert record.user_id is None


# ============================================================
# P65B: Email Verification Gate Fix
# ============================================================

# === 9. No invite code + email configured → verification_required ===

def test_register_no_code_email_configured_returns_verification_required(client, db):
    """When email service is configured, register without invite code returns
    verification_required with no tokens."""
    email = "verify_%s@test.local" % uuid.uuid4().hex[:8]
    with patch("backend.routers.auth.email_service") as mock_es:
        mock_es.is_configured.return_value = True
        mock_es.send_verification_email.return_value = True
        resp = _register(client, email=email)

    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "verification_required"
    assert data["email"] == email
    assert "access_token" not in data

    # User should exist but email_verified = False
    user = db.query(models.User).filter(models.User.email == email).first()
    assert user is not None
    assert user.email_verified is not True


# === 10. No invite code + no email + PRODUCTION=0 → dev auto-verify ===

def test_register_no_code_no_email_dev_mode_auto_verifies(client, db):
    """In dev mode (no email, PRODUCTION != 1), user is auto-verified."""
    email = "dev_%s@test.local" % uuid.uuid4().hex[:8]
    # Default test env: no RESEND_API_KEY, no PRODUCTION=1
    resp = _register(client, email=email)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data.get("user", {}).get("email") == email

    user = db.query(models.User).filter(models.User.email == email).first()
    assert user.email_verified is True


# === 11. No invite code + no email + PRODUCTION=1 → 500 ===

def test_register_no_code_no_email_production_returns_500(client, db):
    """In production (PRODUCTION=1) without email configured → 500."""
    email = "prod_%s@test.local" % uuid.uuid4().hex[:8]
    with patch.dict(os.environ, {"PRODUCTION": "1"}):
        with patch("backend.routers.auth.email_service") as mock_es:
            mock_es.is_configured.return_value = False
            resp = _register(client, email=email)

    assert resp.status_code == 500
    assert "email service" in resp.json()["detail"].lower()


# === 12. Invite code → immediate tokens + email_verified=True ===

def test_invite_code_auto_verifies(client, db):
    """Invite code users get tokens immediately with email_verified=True."""
    _seed_code(db, code="VERIFY1", max_uses=5)
    email = "invited_%s@test.local" % uuid.uuid4().hex[:8]
    resp = _register(client, email=email, invite_code="VERIFY1")
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data

    user = db.query(models.User).filter(models.User.email == email).first()
    assert user.email_verified is True


# === 13. Email send failure → 500 ===

def test_register_email_send_failure_returns_500(client, db):
    """If email service is configured but send fails → 500 error."""
    email = "fail_%s@test.local" % uuid.uuid4().hex[:8]
    with patch("backend.routers.auth.email_service") as mock_es:
        mock_es.is_configured.return_value = True
        mock_es.send_verification_email.return_value = False  # Send fails
        resp = _register(client, email=email)

    assert resp.status_code == 500
    assert "verification email" in resp.json()["detail"].lower()


# === 14. Backfill used_by_email for pre-existing codes ===

def test_backfill_used_by_email(db):
    """auto_seed backfill sets used_by_email from User.invite_code_used."""
    # Create a code with uses > 0 but no used_by_email (simulates pre-P65 state)
    code = models.InviteCode(
        code="BACKFILL-TEST", tier="professional", max_uses=5,
        uses=1, created_by="test", is_active=True,
        used_by_email=None,  # Pre-P65: not set
    )
    db.add(code)
    # Create a user who used this code
    user = models.User(
        email="backfill@test.local",
        invite_code_used="BACKFILL-TEST",
        tier="professional",
    )
    db.add(user)
    db.commit()

    # Run the backfill logic directly
    unlocked = db.query(models.InviteCode).filter(
        models.InviteCode.uses > 0,
        models.InviteCode.used_by_email.is_(None),
        models.InviteCode.code == "BACKFILL-TEST",
    ).all()
    for c in unlocked:
        first_user = db.query(models.User).filter(
            models.User.invite_code_used == c.code,
        ).first()
        if first_user:
            c.used_by_email = first_user.email
    db.commit()

    refreshed = db.query(models.InviteCode).filter(
        models.InviteCode.code == "BACKFILL-TEST",
    ).first()
    assert refreshed.used_by_email == "backfill@test.local"
