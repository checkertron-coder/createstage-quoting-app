"""
P70 — Admin Invite Code Management (DELETE + PATCH reset)

Tests:
1. DELETE /api/admin/invite-codes/{code} — success
2. DELETE /api/admin/invite-codes/{code} — 404 for non-existent code
3. DELETE /api/admin/invite-codes/{code} — 401 without admin secret
4. PATCH /api/admin/invite-codes/{code}/reset — success
5. PATCH /api/admin/invite-codes/{code}/reset — 404 for non-existent code
6. PATCH /api/admin/invite-codes/{code}/reset — 401 without admin secret
"""

from backend import models


ADMIN_HEADERS = {"x-admin-secret": "test-admin-secret"}


def _seed_code(db, code="P70-TEST", tier="professional", max_uses=1,
               uses=0, used_by_email=None):
    """Seed an invite code directly in the database."""
    ic = models.InviteCode(
        code=code,
        tier=tier,
        max_uses=max_uses,
        uses=uses,
        used_by_email=used_by_email,
        created_by="test",
        is_active=True,
    )
    db.add(ic)
    db.commit()
    db.refresh(ic)
    return ic


# === 1. DELETE success ===

def test_delete_invite_code(client, db):
    """DELETE /api/admin/invite-codes/{code} removes the code."""
    _seed_code(db, "DELETE-ME")
    resp = client.delete("/api/admin/invite-codes/DELETE-ME",
                         headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["deleted"] == "DELETE-ME"

    # Verify it's gone
    gone = db.query(models.InviteCode).filter(
        models.InviteCode.code == "DELETE-ME"
    ).first()
    assert gone is None


# === 2. DELETE 404 ===

def test_delete_invite_code_not_found(client):
    """DELETE non-existent code → 404."""
    resp = client.delete("/api/admin/invite-codes/DOES-NOT-EXIST",
                         headers=ADMIN_HEADERS)
    assert resp.status_code == 404


# === 3. DELETE 401 without secret ===

def test_delete_invite_code_no_auth(client, db):
    """DELETE without admin secret → 401."""
    _seed_code(db, "NO-AUTH-DEL")
    resp = client.delete("/api/admin/invite-codes/NO-AUTH-DEL")
    assert resp.status_code == 401


# === 4. PATCH reset success ===

def test_reset_invite_code(client, db):
    """PATCH /api/admin/invite-codes/{code}/reset clears uses and used_by_email."""
    _seed_code(db, "RESET-ME", uses=3, used_by_email="someone@test.com")
    resp = client.patch("/api/admin/invite-codes/RESET-ME/reset",
                        headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == "RESET-ME"
    assert data["uses"] == 0
    assert data["used_by_email"] is None
    assert data["is_active"] is True


# === 5. PATCH reset 404 ===

def test_reset_invite_code_not_found(client):
    """PATCH reset non-existent code → 404."""
    resp = client.patch("/api/admin/invite-codes/GHOST-CODE/reset",
                        headers=ADMIN_HEADERS)
    assert resp.status_code == 404


# === 6. PATCH reset 401 without secret ===

def test_reset_invite_code_no_auth(client, db):
    """PATCH reset without admin secret → 401."""
    _seed_code(db, "NO-AUTH-RESET", uses=2, used_by_email="test@test.com")
    resp = client.patch("/api/admin/invite-codes/NO-AUTH-RESET/reset")
    assert resp.status_code == 401


# === 7. DELETE is case-insensitive ===

def test_delete_case_insensitive(client, db):
    """DELETE with lowercase code still finds uppercase-stored code."""
    _seed_code(db, "CASE-TEST")
    resp = client.delete("/api/admin/invite-codes/case-test",
                         headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["deleted"] == "CASE-TEST"
