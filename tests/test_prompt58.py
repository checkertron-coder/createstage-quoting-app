"""
P58 — Shop Equipment Profile: Conversational Onboarding + Context Injection.

Tests:
1. ShopEquipment model creation
2. Onboarding endpoint stores profile
3. Onboarding sets onboarding_complete
4. build_shop_context() returns formatted string for known profile
5. build_shop_context() returns empty string when no profile
6. build_shop_context_block() includes header
7. GET /api/shop/equipment returns profile
8. PUT /api/shop/equipment updates profile
9. Fallback interpreter extracts capabilities from text
10. onboarding_complete in user response
11. Shop context injected into params during calculate
12. Existing quote flow still works (no profile = no change)
"""

import uuid
from datetime import datetime

import pytest


# --- Helpers ---

def _register(client, email=None, password="testpass123"):
    if email is None:
        email = "p58_%s@test.local" % uuid.uuid4().hex[:8]
    resp = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
    })
    assert resp.status_code == 200, resp.json()
    return resp.json()


def _auth_headers(client, email=None):
    data = _register(client, email=email)
    return {"Authorization": "Bearer %s" % data["access_token"]}, data


# --- Tests ---

class TestShopEquipmentModel:
    """ShopEquipment ORM model."""

    def test_create_shop_equipment(self, db):
        from backend import models

        user = models.User(
            email="equip_%s@test.local" % uuid.uuid4().hex[:8],
            password_hash="fakehash",
        )
        db.add(user)
        db.commit()

        equipment = models.ShopEquipment(
            user_id=user.id,
            welding_processes=[{"process": "MIG", "primary": True, "wire_type": "flux core"}],
            cutting_capabilities=[{"tool": "hand plasma", "cnc": False}],
            forming_equipment=[],
            finishing_capabilities=[{"method": "powder coat", "in_house": False}],
            raw_welding_answer="MIG with flux core, hand plasma",
            raw_forming_answer="Nothing",
            raw_finishing_answer="Send out for powder coat",
        )
        db.add(equipment)
        db.commit()

        found = db.query(models.ShopEquipment).filter(
            models.ShopEquipment.user_id == user.id
        ).first()
        assert found is not None
        assert found.welding_processes[0]["process"] == "MIG"
        assert found.cutting_capabilities[0]["tool"] == "hand plasma"
        assert found.finishing_capabilities[0]["in_house"] is False

    def test_user_onboarding_complete_field(self, db):
        from backend import models

        user = models.User(
            email="onboard_%s@test.local" % uuid.uuid4().hex[:8],
            password_hash="fakehash",
        )
        db.add(user)
        db.commit()

        assert user.onboarding_complete is False
        user.onboarding_complete = True
        db.commit()
        db.refresh(user)
        assert user.onboarding_complete is True


class TestOnboardingEndpoint:
    """POST /api/shop/onboarding."""

    def test_onboarding_stores_profile(self, client):
        headers, data = _auth_headers(client)

        resp = client.post("/api/shop/onboarding", json={
            "welding_answer": "MIG with flux core, hand plasma cutter, chop saw",
            "forming_answer": "No press brake, just a welding table with clamps",
            "finishing_answer": "Send out for powder coat, I spray paint small stuff in house",
        }, headers=headers)

        assert resp.status_code == 200
        result = resp.json()
        assert result["message"] == "Shop profile saved"
        assert result["equipment"]["onboarding_complete"] is True

    def test_onboarding_sets_onboarding_complete(self, client, db):
        from backend import models

        headers, data = _auth_headers(client)

        # Before onboarding
        user = db.query(models.User).filter(models.User.id == data["user_id"]).first()
        assert user.onboarding_complete is False

        client.post("/api/shop/onboarding", json={
            "welding_answer": "TIG and MIG",
            "forming_answer": "Press brake 60 ton",
            "finishing_answer": "Media blast in house, send out for powder",
        }, headers=headers)

        db.refresh(user)
        assert user.onboarding_complete is True

    def test_onboarding_complete_in_user_response(self, client):
        headers, data = _auth_headers(client)

        # Before onboarding — should be False
        resp = client.get("/api/auth/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["onboarding_complete"] is False

        # Complete onboarding
        client.post("/api/shop/onboarding", json={
            "welding_answer": "Stick welder",
            "forming_answer": "None",
            "finishing_answer": "Spray paint",
        }, headers=headers)

        # After onboarding — should be True
        resp = client.get("/api/auth/me", headers=headers)
        assert resp.json()["onboarding_complete"] is True


class TestEquipmentCRUD:
    """GET/PUT /api/shop/equipment."""

    def test_get_equipment_empty(self, client):
        headers, _ = _auth_headers(client)
        resp = client.get("/api/shop/equipment", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["onboarding_complete"] is False
        assert resp.json()["welding_processes"] == []

    def test_get_equipment_after_onboarding(self, client):
        headers, _ = _auth_headers(client)

        client.post("/api/shop/onboarding", json={
            "welding_answer": "MIG flux core",
            "forming_answer": "Nothing",
            "finishing_answer": "Spray paint",
        }, headers=headers)

        resp = client.get("/api/shop/equipment", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["onboarding_complete"] is True
        assert resp.json()["raw_welding_answer"] == "MIG flux core"

    def test_put_equipment_update(self, client):
        headers, _ = _auth_headers(client)

        # Direct update without onboarding
        resp = client.put("/api/shop/equipment", json={
            "welding_processes": [{"process": "TIG", "primary": True}],
            "shop_notes": "Mobile rig",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["welding_processes"][0]["process"] == "TIG"
        assert resp.json()["shop_notes"] == "Mobile rig"
        assert resp.json()["onboarding_complete"] is True


class TestShopContext:
    """backend/shop_context.py — context builder."""

    def test_build_context_no_profile(self, db):
        from backend.shop_context import build_shop_context
        # Non-existent user
        result = build_shop_context(99999, db)
        assert result == ""

    def test_build_context_with_profile(self, db):
        from backend import models
        from backend.shop_context import build_shop_context

        user = models.User(
            email="ctx_%s@test.local" % uuid.uuid4().hex[:8],
            password_hash="fakehash",
        )
        db.add(user)
        db.commit()

        equipment = models.ShopEquipment(
            user_id=user.id,
            welding_processes=[
                {"process": "MIG", "primary": True, "wire_type": "flux core", "notes": ""},
            ],
            cutting_capabilities=[
                {"tool": "hand plasma", "cnc": False, "notes": ""},
                {"tool": "cold saw", "cnc": False, "notes": ""},
            ],
            forming_equipment=[],
            finishing_capabilities=[
                {"method": "spray paint", "in_house": True, "notes": ""},
                {"method": "powder coat", "in_house": False, "notes": "sends out"},
            ],
        )
        db.add(equipment)
        db.commit()

        context = build_shop_context(user.id, db)
        assert "MIG (flux core) [primary]" in context
        assert "hand plasma" in context
        assert "cold saw" in context
        assert "Forming: none" in context
        assert "In-house: spray paint" in context
        assert "Outsource: powder coat" in context

    def test_build_context_block_has_header(self, db):
        from backend import models
        from backend.shop_context import build_shop_context_block

        user = models.User(
            email="blk_%s@test.local" % uuid.uuid4().hex[:8],
            password_hash="fakehash",
        )
        db.add(user)
        db.commit()

        equipment = models.ShopEquipment(
            user_id=user.id,
            welding_processes=[{"process": "TIG", "primary": True}],
        )
        db.add(equipment)
        db.commit()

        block = build_shop_context_block(user.id, db)
        assert "SHOP EQUIPMENT & CAPABILITIES" in block
        assert "TIG [primary]" in block

    def test_build_context_block_empty_when_no_profile(self, db):
        from backend.shop_context import build_shop_context_block
        block = build_shop_context_block(99999, db)
        assert block == ""


class TestFallbackInterpreter:
    """Keyword-based fallback when Opus is unavailable."""

    def test_fallback_extracts_mig_flux_core(self):
        from backend.routers.shop_profile import _fallback_interpret
        result = _fallback_interpret(
            "MIG with flux core wire, hand plasma cutter, chop saw",
            "No press brake",
            "Send out for powder coat",
        )
        weld_processes = [w["process"] for w in result["welding_processes"]]
        assert "MIG" in weld_processes
        assert result["welding_processes"][0]["wire_type"] == "flux core"

        cut_tools = [c["tool"] for c in result["cutting_capabilities"]]
        assert "hand plasma" in cut_tools
        assert "chop saw" in cut_tools

        finishing_methods = [f["method"] for f in result["finishing_capabilities"]]
        assert "powder coat" in finishing_methods
        outsourced = [f for f in result["finishing_capabilities"] if not f["in_house"]]
        assert len(outsourced) >= 1

    def test_fallback_detects_tig(self):
        from backend.routers.shop_profile import _fallback_interpret
        result = _fallback_interpret("TIG welder, stick welder", "", "")
        processes = [w["process"] for w in result["welding_processes"]]
        assert "TIG" in processes
        assert "Stick" in processes

    def test_fallback_detects_cnc_plasma(self):
        from backend.routers.shop_profile import _fallback_interpret
        result = _fallback_interpret("CNC plasma table and MIG", "", "")
        cnc_tools = [c for c in result["cutting_capabilities"] if c.get("cnc")]
        assert len(cnc_tools) >= 1


class TestContextInjection:
    """Shop context flows into AI prompts via _shop_context field."""

    def test_shop_context_in_calculate_params(self, client, db):
        """After /calculate, _shop_context should be in session params if user has profile."""
        from backend import models

        headers, data = _auth_headers(client)
        user_id = data["user_id"]

        # Promote to professional so pipeline works
        user = db.query(models.User).filter(models.User.id == user_id).first()
        user.tier = "professional"
        user.subscription_status = "active"
        db.commit()

        # Create equipment profile
        equipment = models.ShopEquipment(
            user_id=user_id,
            welding_processes=[{"process": "MIG", "primary": True, "wire_type": "flux core"}],
            cutting_capabilities=[{"tool": "chop saw", "cnc": False}],
        )
        db.add(equipment)
        db.commit()

        # Start session
        resp = client.post("/api/session/start", json={
            "description": "6ft wide cantilever gate, 6ft tall, steel frame",
        }, headers=headers)
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Calculate
        resp = client.post("/api/session/%s/calculate" % session_id, headers=headers)
        assert resp.status_code == 200

        # Check session params for _shop_context
        session = db.query(models.QuoteSession).filter(
            models.QuoteSession.id == session_id
        ).first()
        params = session.params_json or {}
        assert "_shop_context" in params
        assert "MIG (flux core)" in params["_shop_context"]

    def test_no_profile_no_context(self, client, db):
        """Without equipment profile, _shop_context should not be in params."""
        from backend import models

        headers, data = _auth_headers(client)
        user_id = data["user_id"]

        user = db.query(models.User).filter(models.User.id == user_id).first()
        user.tier = "professional"
        user.subscription_status = "active"
        db.commit()

        resp = client.post("/api/session/start", json={
            "description": "Simple straight railing, 10 feet, steel",
        }, headers=headers)
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        resp = client.post("/api/session/%s/calculate" % session_id, headers=headers)
        assert resp.status_code == 200

        session = db.query(models.QuoteSession).filter(
            models.QuoteSession.id == session_id
        ).first()
        params = session.params_json or {}
        assert "_shop_context" not in params
