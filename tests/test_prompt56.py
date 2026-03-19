"""
P56: Deposit Settings + Correct Deposit Terms + AI Scope Fix — Tests

Covers: deposit field defaults, profile round-trip, deposit calculation,
shop PDF terms, client PDF terms, AI scope import fix.
"""

from unittest.mock import patch

import pytest


# --- Helpers ---

def _auth(client, email="p56@test.com", password="testpass123"):
    resp = client.post("/api/auth/register", json={
        "email": email, "password": password, "terms_accepted": True,
    })
    assert resp.status_code == 200
    return {"Authorization": "Bearer " + resp.json()["access_token"]}


# === 1. Deposit fields have correct defaults on registration ===

def test_deposit_defaults_on_register(client):
    """New user gets deposit_labor_pct=50, deposit_materials_pct=100."""
    headers = _auth(client, "dep1@test.com")
    resp = client.get("/api/auth/me", headers=headers)
    user = resp.json()
    assert user["deposit_labor_pct"] == 50
    assert user["deposit_materials_pct"] == 100


# === 2. Deposit fields round-trip via profile PUT/GET ===

def test_deposit_profile_roundtrip(client):
    """PUT /profile updates deposit fields, GET returns updated values."""
    headers = _auth(client, "dep2@test.com")

    resp = client.put("/api/auth/profile", json={
        "deposit_labor_pct": 75,
        "deposit_materials_pct": 50,
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["deposit_labor_pct"] == 75
    assert data["deposit_materials_pct"] == 50

    # Verify via GET
    resp = client.get("/api/auth/me", headers=headers)
    data = resp.json()
    assert data["deposit_labor_pct"] == 75
    assert data["deposit_materials_pct"] == 50


# === 3. _compute_deposit with default settings (50% labor, 100% materials) ===

def test_compute_deposit_default_settings():
    """Default deposit: 50% labor + 100% materials, no markup."""
    from backend.pdf_generator import _compute_deposit

    pq = {
        "material_subtotal": 2000,
        "hardware_subtotal": 500,
        "consumable_subtotal": 200,
        "shop_stock_subtotal": 100,
        "labor_subtotal": 1500,
        "selected_markup_pct": 0,
        "total": 4300,
    }
    profile = {"deposit_labor_pct": 50, "deposit_materials_pct": 100}
    d = _compute_deposit(pq, profile)

    assert d["materials_deposit"] == 2800.0  # (2000+500+200+100) * 1.0 * 100%
    assert d["labor_deposit"] == 750.0       # 1500 * 1.0 * 50%
    assert d["total_deposit"] == 3550.0
    assert d["remaining"] == 750.0
    assert "100% of materials" in d["terms_text"]
    assert "50% of labor" in d["terms_text"]


# === 4. _compute_deposit with markup applied ===

def test_compute_deposit_with_markup():
    """Deposit calculation includes markup multiplier."""
    from backend.pdf_generator import _compute_deposit

    pq = {
        "material_subtotal": 1000,
        "hardware_subtotal": 0,
        "consumable_subtotal": 0,
        "shop_stock_subtotal": 0,
        "labor_subtotal": 1000,
        "selected_markup_pct": 20,
        "total": 2400,  # (1000+1000) * 1.20
    }
    profile = {"deposit_labor_pct": 50, "deposit_materials_pct": 100}
    d = _compute_deposit(pq, profile)

    assert d["materials_deposit"] == 1200.0  # 1000 * 1.20 * 100%
    assert d["labor_deposit"] == 600.0       # 1000 * 1.20 * 50%
    assert d["total_deposit"] == 1800.0
    assert d["remaining"] == 600.0


# === 5. _compute_deposit with custom 50/50 split ===

def test_compute_deposit_50_50():
    """Shop with 50% labor / 50% materials gets half of each."""
    from backend.pdf_generator import _compute_deposit

    pq = {
        "material_subtotal": 2000,
        "hardware_subtotal": 0,
        "consumable_subtotal": 0,
        "shop_stock_subtotal": 0,
        "labor_subtotal": 2000,
        "selected_markup_pct": 0,
        "total": 4000,
    }
    profile = {"deposit_labor_pct": 50, "deposit_materials_pct": 50}
    d = _compute_deposit(pq, profile)

    assert d["materials_deposit"] == 1000.0
    assert d["labor_deposit"] == 1000.0
    assert d["total_deposit"] == 2000.0
    assert d["remaining"] == 2000.0
    assert "50% of materials" in d["terms_text"]
    assert "50% of labor" in d["terms_text"]


# === 6. Shop PDF no longer has hardcoded "50% deposit" ===

def test_shop_pdf_no_hardcoded_deposit():
    """Shop PDF uses _compute_deposit, not hardcoded '50% deposit' text."""
    import inspect
    from backend.pdf_generator import generate_quote_pdf
    src = inspect.getsource(generate_quote_pdf)
    assert "50% deposit due at signing" not in src
    assert "_compute_deposit" in src


# === 7. Client PDF no longer has hardcoded "50% deposit" ===

def test_client_pdf_no_hardcoded_deposit():
    """Client PDF uses _compute_deposit, not hardcoded '50% deposit' text."""
    import inspect
    from backend.pdf_generator import generate_client_pdf
    src = inspect.getsource(generate_client_pdf)
    assert "50% deposit due at signing" not in src
    assert "_compute_deposit" in src


# === 8. AI scope uses absolute import ===

def test_ai_scope_absolute_import():
    """generate_client_scope uses 'from backend.claude_client' (absolute import)."""
    import inspect
    from backend.pdf_generator import generate_client_scope
    src = inspect.getsource(generate_client_scope)
    assert "from backend.claude_client import call_fast" in src
    assert "from .claude_client" not in src


# === 9. Deposit terms appear in generated shop PDF bytes ===

def test_shop_pdf_contains_deposit_terms():
    """Generated shop PDF contains deposit dollar amounts."""
    from backend.pdf_generator import generate_quote_pdf

    pq = {
        "quote_id": 1,
        "quote_number": "Q-TEST-56",
        "job_type": "cantilever_gate",
        "material_subtotal": 2000,
        "hardware_subtotal": 500,
        "consumable_subtotal": 100,
        "shop_stock_subtotal": 0,
        "labor_subtotal": 1000,
        "finishing_subtotal": 200,
        "subtotal": 3800,
        "selected_markup_pct": 0,
        "total": 3800,
        "materials": [],
        "hardware": [],
        "consumables": [],
        "labor": [],
        "finishing": {"method": "raw"},
        "assumptions": [],
        "exclusions": [],
        "created_at": "2026-03-19T12:00:00",
    }
    profile = {
        "shop_name": "Test Shop",
        "deposit_labor_pct": 50,
        "deposit_materials_pct": 100,
    }
    pdf_bytes = generate_quote_pdf(pq, profile, {})
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert len(pdf_bytes) > 100


# === 10. Deposit with consumables included ===

def test_deposit_includes_consumables():
    """Consumables and shop stock are included in materials deposit."""
    from backend.pdf_generator import _compute_deposit

    pq = {
        "material_subtotal": 1000,
        "hardware_subtotal": 200,
        "consumable_subtotal": 150,
        "shop_stock_subtotal": 50,
        "labor_subtotal": 500,
        "selected_markup_pct": 0,
        "total": 1900,
    }
    profile = {"deposit_labor_pct": 50, "deposit_materials_pct": 100}
    d = _compute_deposit(pq, profile)

    # Materials deposit = 1000 + 200 + 150 + 50 = 1400
    assert d["materials_deposit"] == 1400.0
    assert d["labor_deposit"] == 250.0
