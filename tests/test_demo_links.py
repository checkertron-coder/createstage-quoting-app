"""
P53B: Demo Magic Links + Frictionless Beta Onboarding — Tests

Tests:
1. Admin can create demo link
2. Admin can list demo links
3. Demo link redemption creates provisional user
4. Demo link re-redemption reissues tokens (same user)
5. Expired demo link returns 410
6. Invalid demo token returns 404
7. Demo user quota enforced
8. Demo user status endpoint
9. Passwordless beta registration with invite code
10. Passwordless registration requires invite code
11. Demo user upgrade via registration
12. Demo route serves app page
13. NDA field removed from User model
"""

import uuid
from datetime import datetime, timedelta

from backend import models


# --- Helpers ---

def _admin_headers():
    return {"x-admin-secret": "test-admin-secret"}


def _create_demo_link(client, label="Test Demo", max_quotes=3, expires_hours=48):
    """Create a demo link via admin endpoint."""
    resp = client.post("/api/admin/demo-links", json={
        "label": label,
        "max_quotes": max_quotes,
        "expires_hours": expires_hours,
    }, headers=_admin_headers())
    assert resp.status_code == 200
    return resp.json()


def _seed_demo_link(db, max_quotes=3, expires_hours=48, is_used=False):
    """Seed a demo link directly in the database."""
    import secrets
    token = secrets.token_urlsafe(24)
    link = models.DemoLink(
        token=token,
        label="Test",
        tier="professional",
        max_quotes=max_quotes,
        expires_at=datetime.utcnow() + timedelta(hours=expires_hours),
        is_used=is_used,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def _seed_expired_demo_link(db):
    """Seed an expired demo link."""
    import secrets
    token = secrets.token_urlsafe(24)
    link = models.DemoLink(
        token=token,
        label="Expired",
        tier="professional",
        max_quotes=3,
        expires_at=datetime.utcnow() - timedelta(hours=1),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def _seed_invite_code(db, code="BETA-DEMO-TEST"):
    """Seed an invite code for passwordless tests."""
    ic = models.InviteCode(
        code=code,
        tier="professional",
        max_uses=10,
        uses=0,
        created_by="test",
        is_active=True,
    )
    db.add(ic)
    db.commit()
    db.refresh(ic)
    return ic


# === 1. Admin can create demo link ===

def test_admin_create_demo_link(client):
    """POST /api/admin/demo-links creates a demo link."""
    data = _create_demo_link(client, label="For Jim Lai")
    assert "token" in data
    assert data["label"] == "For Jim Lai"
    assert data["max_quotes"] == 3
    assert "/demo/" in data["url"]


# === 2. Admin can list demo links ===

def test_admin_list_demo_links(client):
    """GET /api/admin/demo-links lists all demo links."""
    _create_demo_link(client, label="Link A")
    _create_demo_link(client, label="Link B")
    resp = client.get("/api/admin/demo-links", headers=_admin_headers())
    assert resp.status_code == 200
    labels = [dl["label"] for dl in resp.json()]
    assert "Link A" in labels
    assert "Link B" in labels


# === 3. Demo link redemption creates provisional user ===

def test_demo_redemption_creates_user(client, db):
    """Redeeming a demo link creates a provisional user and returns JWT."""
    link = _seed_demo_link(db)
    resp = client.post("/api/auth/redeem-demo", params={"token": link.token})
    assert resp.status_code == 200
    data = resp.json()
    assert data["demo"] is True
    assert "access_token" in data
    assert data["user"]["is_provisional"] is True
    assert data["user"]["tier"] == "professional"

    # Demo link should be marked as used
    db.expire_all()
    updated = db.query(models.DemoLink).filter(
        models.DemoLink.id == link.id).first()
    assert updated.is_used is True
    assert updated.demo_user_id == data["user"]["id"]


# === 4. Demo link re-redemption reissues tokens ===

def test_demo_re_redemption_same_user(client, db):
    """Redeeming the same demo link twice returns the same user."""
    link = _seed_demo_link(db)

    resp1 = client.post("/api/auth/redeem-demo", params={"token": link.token})
    assert resp1.status_code == 200
    user_id_1 = resp1.json()["user"]["id"]

    resp2 = client.post("/api/auth/redeem-demo", params={"token": link.token})
    assert resp2.status_code == 200
    user_id_2 = resp2.json()["user"]["id"]

    assert user_id_1 == user_id_2


# === 5. Expired demo link returns 410 ===

def test_expired_demo_link_returns_410(client, db):
    """Redeeming an expired demo link returns 410."""
    link = _seed_expired_demo_link(db)
    resp = client.post("/api/auth/redeem-demo", params={"token": link.token})
    assert resp.status_code == 410
    assert "expired" in resp.json()["detail"].lower()


# === 6. Invalid demo token returns 404 ===

def test_invalid_demo_token_returns_404(client):
    """Redeeming a non-existent token returns 404."""
    resp = client.post("/api/auth/redeem-demo",
                       params={"token": "nonexistent-token-abc"})
    assert resp.status_code == 404


# === 7. Demo user quota enforced ===

def test_demo_user_quota_enforced(client, db):
    """Demo user hitting max_quotes gets 403 on /session/start."""
    link = _seed_demo_link(db, max_quotes=2)

    # Redeem demo link
    resp = client.post("/api/auth/redeem-demo", params={"token": link.token})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    headers = {"Authorization": "Bearer %s" % token}

    # Set quotes_this_month to the demo limit
    user = db.query(models.User).filter(
        models.User.id == resp.json()["user"]["id"]).first()
    user.quotes_this_month = 2
    db.commit()

    # Try to start a session
    start_resp = client.post("/api/session/start", json={
        "description": "test gate",
    }, headers=headers)
    assert start_resp.status_code == 403
    assert "demo" in start_resp.json()["detail"].lower()


# === 8. Demo user status endpoint ===

def test_demo_status_endpoint(client, db):
    """GET /api/auth/demo-status returns demo user info."""
    link = _seed_demo_link(db, max_quotes=5)

    # Redeem
    resp = client.post("/api/auth/redeem-demo", params={"token": link.token})
    token = resp.json()["access_token"]
    headers = {"Authorization": "Bearer %s" % token}

    # Check demo status
    status_resp = client.get("/api/auth/demo-status", headers=headers)
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["is_demo"] is True
    assert data["max_quotes"] == 5
    assert data["quotes_remaining"] == 5


# === 9. Passwordless beta registration with invite code ===

def test_passwordless_registration_with_invite_code(client, db):
    """Register with invite code and no password → provisional account created."""
    _seed_invite_code(db, "PW-OPTIONAL")
    email = "beta_%s@test.local" % uuid.uuid4().hex[:8]
    resp = client.post("/api/auth/register", json={
        "email": email,
        "invite_code": "PW-OPTIONAL",
        "terms_accepted": True,
    })
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["tier"] == "professional"
    assert user["is_provisional"] is True  # No password = provisional


# === 10. Passwordless registration requires invite code ===

def test_passwordless_requires_invite_code(client):
    """Register without password and without invite code → 400."""
    email = "nopw_%s@test.local" % uuid.uuid4().hex[:8]
    resp = client.post("/api/auth/register", json={
        "email": email,
        "terms_accepted": True,
    })
    assert resp.status_code == 400
    assert "8 characters" in resp.json()["detail"]


# === 11. Demo user upgrade via registration ===

def test_demo_user_upgrade(client, db):
    """Demo user registering with real email transfers quotes."""
    link = _seed_demo_link(db)

    # Redeem demo link
    resp = client.post("/api/auth/redeem-demo", params={"token": link.token})
    assert resp.status_code == 200
    demo_user_id = resp.json()["user"]["id"]

    # Upgrade by registering with demo_token
    email = "upgrade_%s@test.local" % uuid.uuid4().hex[:8]
    upgrade_resp = client.post("/api/auth/register", json={
        "email": email,
        "password": "newpassword123",
        "demo_token": link.token,
        "terms_accepted": True,
    })
    assert upgrade_resp.status_code == 200
    data = upgrade_resp.json()
    assert data.get("upgraded_demo") is True
    # Same user ID — quotes transfer automatically
    assert data["user"]["id"] == demo_user_id
    assert data["user"]["email"] == email


# === 12. Demo route serves app page ===

def test_demo_route_serves_app(client, db):
    """GET /demo/{token} serves app.html."""
    link = _seed_demo_link(db)
    resp = client.get("/demo/%s" % link.token)
    assert resp.status_code == 200
    assert "CreateQuote" in resp.text


# === 13. NDA field removed from User model ===

def test_nda_field_removed():
    """User model should not have nda_accepted_at column."""
    columns = [c.name for c in models.User.__table__.columns]
    assert "nda_accepted_at" not in columns
    assert "terms_accepted_at" in columns  # Terms stays


# === 14. Non-demo user demo-status returns is_demo=False ===

def test_non_demo_user_status(client):
    """Regular user's demo-status returns is_demo=False."""
    email = "regular_%s@test.local" % uuid.uuid4().hex[:8]
    reg = client.post("/api/auth/register", json={
        "email": email,
        "password": "testpass123",
        "terms_accepted": True,
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": "Bearer %s" % token}

    resp = client.get("/api/auth/demo-status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_demo"] is False
