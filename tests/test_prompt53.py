"""
P53: Landing Page + Auth Overhaul — Tests

Tests:
1. Guest endpoint returns 410
2. Registration without invite code → free tier
3. Registration with valid invite code → professional tier
4. Registration with invalid invite code → 400
5. Registration with expired invite code → 400
6. Registration with maxed-out invite code → 400
7. Invite code uses increment on register
8. Validate-code endpoint — valid code
9. Validate-code endpoint — invalid code
10. Password minimum 8 characters
11. Terms accepted timestamp set
12. Quote access — free tier limit
13. Quote access — professional tier unlimited
14. Landing page loads (GET /)
15. App page loads (GET /app)
16. Terms page loads (GET /terms)
17. NDA page loads (GET /nda)
18. Admin invite code creation
19. Admin invite code list
20. Admin requires secret
"""

import uuid
from datetime import datetime, timedelta

from backend import models


# --- Helper ---

def _register(client, email=None, password="testpass123", invite_code=None,
              terms_accepted=True, nda_accepted=True):
    """Register a user and return response."""
    if email is None:
        email = "user_%s@test.local" % uuid.uuid4().hex[:8]
    body = {"email": email, "password": password}
    if invite_code:
        body["invite_code"] = invite_code
    if terms_accepted:
        body["terms_accepted"] = True
    if nda_accepted:
        body["nda_accepted"] = True
    return client.post("/api/auth/register", json=body)


def _seed_code(db, code="TESTCODE", tier="professional", max_uses=None,
               expires_at=None, is_active=True):
    """Seed an invite code directly in the database."""
    ic = models.InviteCode(
        code=code,
        tier=tier,
        max_uses=max_uses,
        uses=0,
        expires_at=expires_at,
        created_by="test",
        is_active=is_active,
    )
    db.add(ic)
    db.commit()
    db.refresh(ic)
    return ic


# === 1. Guest returns 410 ===

def test_guest_returns_410(client):
    """POST /api/auth/guest returns 410 Gone."""
    resp = client.post("/api/auth/guest")
    assert resp.status_code == 410
    assert "removed" in resp.json()["detail"].lower()


# === 2. Registration without invite code → free tier ===

def test_register_no_code_gets_free_tier(client):
    """Register without invite code → free tier, trial status."""
    resp = _register(client)
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["tier"] == "free"
    assert user["subscription_status"] == "trial"


# === 3. Registration with valid invite code → professional tier ===

def test_register_with_valid_code(client, db):
    """Register with valid invite code → gets the code's tier."""
    _seed_code(db, "BETA-TEST-VALID", "professional")
    resp = _register(client, invite_code="BETA-TEST-VALID")
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["tier"] == "professional"


# === 4. Registration with invalid code → 400 ===

def test_register_with_invalid_code(client):
    """Register with non-existent invite code → 400."""
    resp = _register(client, invite_code="DOES-NOT-EXIST")
    assert resp.status_code == 400
    assert "invalid" in resp.json()["detail"].lower()


# === 5. Expired invite code → 400 ===

def test_register_with_expired_code(client, db):
    """Register with expired invite code → 400."""
    _seed_code(db, "EXPIRED-CODE",
               expires_at=datetime.utcnow() - timedelta(days=1))
    resp = _register(client, invite_code="EXPIRED-CODE")
    assert resp.status_code == 400


# === 6. Maxed-out invite code → 400 ===

def test_register_with_maxed_code(client, db):
    """Register with maxed-out invite code → 400."""
    ic = _seed_code(db, "MAXED-CODE", max_uses=1)
    ic.uses = 1
    db.commit()
    resp = _register(client, invite_code="MAXED-CODE")
    assert resp.status_code == 400


# === 7. Invite code uses increment ===

def test_invite_code_uses_increment(client, db):
    """Using an invite code increments its uses counter."""
    _seed_code(db, "COUNT-CODE", max_uses=5)
    resp = _register(client, invite_code="COUNT-CODE")
    assert resp.status_code == 200
    db.expire_all()
    code = db.query(models.InviteCode).filter(
        models.InviteCode.code == "COUNT-CODE").first()
    assert code.uses == 1


# === 8. Validate-code endpoint — valid ===

def test_validate_code_valid(client, db):
    """POST /api/auth/validate-code with valid code returns valid=True."""
    _seed_code(db, "VALIDATE-OK")
    resp = client.post("/api/auth/validate-code", json={"code": "VALIDATE-OK"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["tier"] == "professional"


# === 9. Validate-code endpoint — invalid ===

def test_validate_code_invalid(client):
    """POST /api/auth/validate-code with bad code returns valid=False."""
    resp = client.post("/api/auth/validate-code", json={"code": "NOPE"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


# === 10. Password minimum 8 characters ===

def test_password_minimum_length(client):
    """Register with short password → 400."""
    resp = _register(client, password="short")
    assert resp.status_code == 400
    assert "8 characters" in resp.json()["detail"]


# === 11. Terms accepted timestamp set ===

def test_terms_accepted_timestamp(client, db):
    """Register with terms_accepted=True sets terms_accepted_at."""
    email = "terms_%s@test.local" % uuid.uuid4().hex[:8]
    resp = _register(client, email=email, terms_accepted=True)
    assert resp.status_code == 200
    user = db.query(models.User).filter(models.User.email == email).first()
    assert user.terms_accepted_at is not None


# === 12. Quote access — free tier limit ===

def test_free_tier_quota_enforced(client, db):
    """Free tier user hitting quota → 403 on /session/start."""
    resp = _register(client)
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    headers = {"Authorization": "Bearer %s" % token}

    # Set quotes_this_month to the free limit
    user = db.query(models.User).filter(
        models.User.id == resp.json()["user_id"]).first()
    user.quotes_this_month = 3  # free limit
    db.commit()

    # Try to start a session
    start_resp = client.post("/api/session/start", json={
        "description": "test gate",
    }, headers=headers)
    assert start_resp.status_code == 403
    assert "limit" in start_resp.json()["detail"].lower()


# === 13. Professional tier — unlimited access ===

def test_professional_tier_unlimited(client, db):
    """Professional tier user can start sessions without quota block."""
    _seed_code(db, "PRO-ACCESS", "professional")
    resp = _register(client, invite_code="PRO-ACCESS")
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    headers = {"Authorization": "Bearer %s" % token}

    # Set high usage — should still be allowed
    user = db.query(models.User).filter(
        models.User.id == resp.json()["user_id"]).first()
    user.quotes_this_month = 100
    db.commit()

    # Should not get 403 (may fail for other reasons like missing Gemini,
    # but should NOT be a quota error)
    start_resp = client.post("/api/session/start", json={
        "description": "test gate 24ft cantilever",
    }, headers=headers)
    assert start_resp.status_code != 403


# === 14. Landing page loads ===

def test_landing_page_loads(client):
    """GET / returns 200 with landing page content."""
    resp = client.get("/")
    assert resp.status_code == 200
    text = resp.text
    assert "CreateQuote" in text
    assert "Metal Fabrication" in text
    assert "Start Quoting Free" in text


# === 15. App page loads ===

def test_app_page_loads(client):
    """GET /app returns 200."""
    resp = client.get("/app")
    assert resp.status_code == 200
    assert "CreateQuote" in resp.text


# === 16. Terms page loads ===

def test_terms_page_loads(client):
    """GET /terms returns 200 with terms content."""
    resp = client.get("/terms")
    assert resp.status_code == 200
    assert "Terms of Service" in resp.text


# === 17. NDA page loads ===

def test_nda_page_loads(client):
    """GET /nda returns 200 with NDA content."""
    resp = client.get("/nda")
    assert resp.status_code == 200
    assert "Non-Disclosure" in resp.text


# === 18. Admin invite code creation ===

def test_admin_create_invite_code(client):
    """POST /api/admin/invite-codes creates a code with valid admin secret."""
    resp = client.post("/api/admin/invite-codes", json={
        "code": "ADMIN-TEST-CODE",
        "tier": "starter",
        "max_uses": 10,
    }, headers={"x-admin-secret": "createstage-admin-2026"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "ADMIN-TEST-CODE"
    assert data["tier"] == "starter"
    assert data["max_uses"] == 10


# === 19. Admin invite code list ===

def test_admin_list_invite_codes(client, db):
    """GET /api/admin/invite-codes lists all codes."""
    _seed_code(db, "LIST-CODE-1")
    _seed_code(db, "LIST-CODE-2")
    resp = client.get("/api/admin/invite-codes",
                      headers={"x-admin-secret": "createstage-admin-2026"})
    assert resp.status_code == 200
    codes = [c["code"] for c in resp.json()]
    assert "LIST-CODE-1" in codes
    assert "LIST-CODE-2" in codes


# === 20. Admin requires secret ===

def test_admin_requires_secret(client):
    """Admin endpoints without secret → 401."""
    resp = client.post("/api/admin/invite-codes", json={
        "code": "SHOULD-FAIL",
    })
    assert resp.status_code == 401

    resp = client.get("/api/admin/invite-codes")
    assert resp.status_code == 401
