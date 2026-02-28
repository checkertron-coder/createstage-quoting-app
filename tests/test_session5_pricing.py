"""
Session 5 acceptance tests — Hardware Sourcing + Pricing Engine (Stage 5).

Tests:
1-5.   Hardware sourcer tests
6-10.  Pricing engine tests
11-14. Quote storage tests (/price endpoint)
15-17. Markup endpoint tests
18-22. Consumable estimation tests
23-26. Full pipeline tests (intake → price)

No AI — Stage 5 is pure math.
"""

import pytest

from backend.hardware_sourcer import HardwareSourcer, HARDWARE_PRICES, CONSUMABLES
from backend.pricing_engine import PricingEngine
from backend.calculators.cantilever_gate import CantileverGateCalculator
from backend.calculators.straight_railing import StraightRailingCalculator


# --- Test fixtures ---

def _sample_cantilever_fields():
    """Complete cantilever gate fields."""
    return {
        "clear_width": "10",
        "height": "6",
        "frame_material": "Square tube (most common)",
        "frame_gauge": "11 gauge (0.120\" - standard for gates)",
        "infill_type": "Expanded metal",
        "post_count": "3 posts (standard)",
        "finish": "Powder coat (most durable, outsourced)",
        "installation": "Full installation (gate + posts + concrete)",
        "has_motor": "Yes",
        "motor_brand": "LiftMaster LA412",
        "latch_lock": "Gravity latch",
    }


def _sample_material_list():
    """Generate a cantilever gate material list."""
    calc = CantileverGateCalculator()
    return calc.calculate(_sample_cantilever_fields())


def _sample_labor_estimate():
    """Sample labor estimate matching LaborEstimate contract."""
    processes = [
        {"process": "layout_setup", "hours": 0.5, "rate": 125.0, "notes": "Rule-based fallback"},
        {"process": "cut_prep", "hours": 1.2, "rate": 125.0, "notes": "Rule-based fallback"},
        {"process": "fit_tack", "hours": 2.0, "rate": 125.0, "notes": "Rule-based fallback"},
        {"process": "full_weld", "hours": 3.5, "rate": 125.0, "notes": "Rule-based fallback"},
        {"process": "grind_clean", "hours": 1.0, "rate": 125.0, "notes": "Rule-based fallback"},
        {"process": "finish_prep", "hours": 0.5, "rate": 125.0, "notes": "Rule-based fallback"},
        {"process": "clearcoat", "hours": 0.0, "rate": 125.0, "notes": "Rule-based fallback"},
        {"process": "paint", "hours": 0.0, "rate": 125.0, "notes": "Rule-based fallback"},
        {"process": "hardware_install", "hours": 1.5, "rate": 125.0, "notes": "Rule-based fallback"},
        {"process": "site_install", "hours": 4.0, "rate": 145.0, "notes": "Rule-based fallback"},
        {"process": "final_inspection", "hours": 0.5, "rate": 125.0, "notes": "Rule-based fallback"},
    ]
    total_hours = sum(p["hours"] for p in processes)
    return {
        "processes": processes,
        "total_hours": total_hours,
        "flagged": False,
        "flag_reason": None,
    }


def _sample_finishing():
    """Sample finishing section for powder coat."""
    return {
        "method": "powder_coat",
        "area_sq_ft": 75.0,
        "hours": 0.0,
        "materials_cost": 0.0,
        "outsource_cost": 262.50,
        "total": 262.50,
    }


def _sample_user():
    """Sample user profile dict."""
    return {
        "id": 1,
        "shop_name": "Test Fabrication",
        "markup_default": 15,
        "rate_inshop": 125.00,
        "rate_onsite": 145.00,
    }


def _sample_session_data(material_list=None, labor_estimate=None, finishing=None, fields=None):
    """Build session_data dict for PricingEngine."""
    return {
        "session_id": "test-session-123",
        "job_type": "cantilever_gate",
        "fields": fields or _sample_cantilever_fields(),
        "material_list": material_list or _sample_material_list(),
        "labor_estimate": labor_estimate or _sample_labor_estimate(),
        "finishing": finishing or _sample_finishing(),
    }


# ============================================================
# 1-5. Hardware Sourcer Tests
# ============================================================

def test_hardware_sourcer_prices_gate_hardware():
    """Hardware items from Stage 3 get upgraded with catalog prices."""
    sourcer = HardwareSourcer()
    hardware = [
        {"description": "Heavy duty weld-on gate hinge pair", "quantity": 2, "options": []},
        {"description": "Gravity latch", "quantity": 1, "options": []},
    ]
    priced = sourcer.price_hardware_list(hardware)
    assert len(priced) == 2
    # Should have 3 options each from catalog
    assert len(priced[0]["options"]) == 3
    assert len(priced[1]["options"]) == 3
    # Verify suppliers present
    suppliers = [o["supplier"] for o in priced[0]["options"]]
    assert "McMaster-Carr" in suppliers or "Grainger" in suppliers


def test_hardware_sourcer_three_options_per_item():
    """Every catalog-matched item gets exactly 3 pricing options."""
    sourcer = HardwareSourcer()
    for key, data in HARDWARE_PRICES.items():
        assert len(data["options"]) == 3, f"{key} should have 3 options"
        for opt in data["options"]:
            assert "supplier" in opt
            assert "price" in opt
            assert opt["price"] > 0


def test_hardware_select_cheapest():
    """select_cheapest_option returns the lowest price."""
    sourcer = HardwareSourcer()
    item = {
        "options": [
            {"supplier": "McMaster-Carr", "price": 145.00},
            {"supplier": "Amazon", "price": 89.99},
            {"supplier": "Grainger", "price": 125.00},
        ]
    }
    price, supplier = sourcer.select_cheapest_option(item)
    assert price == 89.99
    assert supplier == "Amazon"


def test_hardware_bulk_discount_suggestion():
    """Bulk discount suggestions trigger at correct thresholds."""
    sourcer = HardwareSourcer()
    # Below threshold
    assert sourcer.suggest_bulk_discount(400) == {}
    # Medium threshold
    medium = sourcer.suggest_bulk_discount(600)
    assert medium["threshold"] == "medium"
    assert "5-10%" in medium["suggestion"]
    # High threshold
    high = sourcer.suggest_bulk_discount(2500)
    assert high["threshold"] == "high"
    assert "10-20%" in high["suggestion"]


def test_hardware_mcmaster_only_flag():
    """Items with only McMaster pricing get flagged."""
    sourcer = HardwareSourcer()
    items = [
        {"description": "Item A", "options": [
            {"supplier": "McMaster-Carr", "price": 50.00},
            {"supplier": "Amazon", "price": None},
        ]},
        {"description": "Item B", "options": [
            {"supplier": "McMaster-Carr", "price": 50.00},
            {"supplier": "Amazon", "price": 40.00},
        ]},
    ]
    flagged = sourcer.flag_mcmaster_only(items)
    assert "Item A" in flagged
    assert "Item B" not in flagged


# ============================================================
# 6-10. Pricing Engine Tests
# ============================================================

def test_pricing_engine_returns_all_required_fields():
    """PricedQuote matches the CLAUDE.md contract fields."""
    engine = PricingEngine()
    session_data = _sample_session_data()
    user = _sample_user()
    result = engine.build_priced_quote(session_data, user)

    required_fields = [
        "quote_id", "user_id", "job_type", "client_name",
        "materials", "hardware", "consumables", "labor", "finishing",
        "material_subtotal", "hardware_subtotal", "consumable_subtotal",
        "labor_subtotal", "finishing_subtotal", "subtotal",
        "markup_options", "selected_markup_pct", "total",
        "created_at", "assumptions", "exclusions",
    ]
    for field in required_fields:
        assert field in result, f"Missing field: {field}"


def test_pricing_engine_subtotal_is_sum_of_parts():
    """Subtotal = material + hardware + consumable + labor + finishing."""
    engine = PricingEngine()
    session_data = _sample_session_data()
    user = _sample_user()
    result = engine.build_priced_quote(session_data, user)

    expected = round(
        result["material_subtotal"] +
        result["hardware_subtotal"] +
        result["consumable_subtotal"] +
        result["labor_subtotal"] +
        result["finishing_subtotal"],
        2,
    )
    assert result["subtotal"] == expected


def test_pricing_engine_markup_options():
    """Markup options include 0% through 30% in 5% increments."""
    engine = PricingEngine()
    session_data = _sample_session_data()
    user = _sample_user()
    result = engine.build_priced_quote(session_data, user)

    options = result["markup_options"]
    assert "0" in options
    assert "5" in options
    assert "10" in options
    assert "15" in options
    assert "20" in options
    assert "25" in options
    assert "30" in options

    subtotal = result["subtotal"]
    assert options["0"] == subtotal
    assert options["15"] == round(subtotal * 1.15, 2)
    assert options["30"] == round(subtotal * 1.30, 2)


def test_pricing_engine_default_markup_from_user():
    """Default markup comes from user profile."""
    engine = PricingEngine()
    session_data = _sample_session_data()
    user = _sample_user()
    user["markup_default"] = 20
    result = engine.build_priced_quote(session_data, user)

    assert result["selected_markup_pct"] == 20
    assert result["total"] == result["markup_options"]["20"]


def test_pricing_engine_assumptions_always_present():
    """Assumptions list is always non-empty."""
    engine = PricingEngine()
    session_data = _sample_session_data()
    user = _sample_user()
    result = engine.build_priced_quote(session_data, user)

    assert isinstance(result["assumptions"], list)
    assert len(result["assumptions"]) >= 3  # material prices, labor method, hardware prices


# ============================================================
# 11-14. Quote Storage Tests (/price endpoint)
# ============================================================

def test_price_endpoint_creates_quote(client, auth_headers):
    """POST /price creates a Quote record and returns quote_id."""
    # Run full pipeline: start → answer → calculate → estimate → price
    session_id = _run_pipeline_to_price_stage(client, auth_headers)

    # Run /price
    resp = client.post(f"/api/session/{session_id}/price", headers=auth_headers)
    assert resp.status_code == 200, f"Price failed: {resp.json()}"
    data = resp.json()

    assert "quote_id" in data
    assert data["quote_id"] is not None
    assert "quote_number" in data
    assert data["quote_number"].startswith("CS-")
    assert "priced_quote" in data


def test_price_endpoint_stores_outputs_json(client, auth_headers, db):
    """Quote record has outputs_json with full PricedQuote."""
    from backend.models import Quote

    session_id = _run_pipeline_to_price_stage(client, auth_headers)
    resp = client.post(f"/api/session/{session_id}/price", headers=auth_headers)
    assert resp.status_code == 200
    quote_id = resp.json()["quote_id"]

    # Check database directly
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    assert quote is not None
    assert quote.outputs_json is not None
    assert "materials" in quote.outputs_json
    assert "labor" in quote.outputs_json
    assert "subtotal" in quote.outputs_json


def test_price_endpoint_transitions_session_to_output(client, auth_headers):
    """After /price, session stage becomes 'output' and status 'complete'."""
    session_id = _run_pipeline_to_price_stage(client, auth_headers)
    client.post(f"/api/session/{session_id}/price", headers=auth_headers)

    # Check session status
    resp = client.get(f"/api/session/{session_id}/status", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["stage"] == "output"
    assert resp.json()["status"] == "complete"


def test_price_endpoint_rejects_wrong_stage(client, auth_headers):
    """POST /price fails if session is not at 'price' stage."""
    # Start a session but don't complete the pipeline
    resp = client.post("/api/session/start", json={
        "description": "10 foot cantilever gate",
        "job_type": "cantilever_gate",
    }, headers=auth_headers)
    session_id = resp.json()["session_id"]

    resp = client.post(f"/api/session/{session_id}/price", headers=auth_headers)
    assert resp.status_code == 400
    assert "not 'price'" in resp.json()["detail"]


# ============================================================
# 15-17. Markup Endpoint Tests
# ============================================================

def test_markup_endpoint_recalculates_total(client, auth_headers):
    """PUT /markup recalculates total from subtotal."""
    session_id = _run_pipeline_to_price_stage(client, auth_headers)
    resp = client.post(f"/api/session/{session_id}/price", headers=auth_headers)
    quote_id = resp.json()["quote_id"]
    subtotal = resp.json()["priced_quote"]["subtotal"]

    # Change markup to 25%
    resp = client.put(f"/api/quotes/{quote_id}/markup", json={
        "markup_pct": 25,
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["selected_markup_pct"] == 25
    assert data["total"] == round(subtotal * 1.25, 2)


def test_markup_endpoint_rejects_invalid_pct(client, auth_headers):
    """PUT /markup rejects values not in [0, 5, 10, 15, 20, 25, 30]."""
    session_id = _run_pipeline_to_price_stage(client, auth_headers)
    resp = client.post(f"/api/session/{session_id}/price", headers=auth_headers)
    quote_id = resp.json()["quote_id"]

    resp = client.put(f"/api/quotes/{quote_id}/markup", json={
        "markup_pct": 12,
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "must be one of" in resp.json()["detail"]


def test_markup_endpoint_returns_all_options(client, auth_headers):
    """PUT /markup response includes markup_options for slider UI."""
    session_id = _run_pipeline_to_price_stage(client, auth_headers)
    resp = client.post(f"/api/session/{session_id}/price", headers=auth_headers)
    quote_id = resp.json()["quote_id"]

    resp = client.put(f"/api/quotes/{quote_id}/markup", json={
        "markup_pct": 10,
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "markup_options" in data
    assert "0" in data["markup_options"]
    assert "30" in data["markup_options"]


# ============================================================
# 18-22. Consumable Estimation Tests
# ============================================================

def test_consumables_from_weld_inches():
    """Consumable estimation produces items from weld inches."""
    sourcer = HardwareSourcer()
    consumables = sourcer.estimate_consumables(
        weld_linear_inches=200.0,
        total_sq_ft=50.0,
        finish_type="raw",
    )
    assert len(consumables) >= 3  # wire, grinding disc, flap disc, gas at minimum
    descriptions = [c["description"] for c in consumables]
    assert any("welding wire" in d.lower() for d in descriptions)
    assert any("grinding" in d.lower() for d in descriptions)


def test_consumables_clearcoat_included():
    """Clearcoat finish adds clearcoat spray consumable."""
    sourcer = HardwareSourcer()
    consumables = sourcer.estimate_consumables(
        weld_linear_inches=100.0,
        total_sq_ft=50.0,
        finish_type="clearcoat",
    )
    descriptions = [c["description"].lower() for c in consumables]
    assert any("clear coat" in d for d in descriptions)


def test_consumables_paint_includes_primer():
    """Paint finish adds primer spray consumable."""
    sourcer = HardwareSourcer()
    consumables = sourcer.estimate_consumables(
        weld_linear_inches=100.0,
        total_sq_ft=50.0,
        finish_type="paint",
    )
    descriptions = [c["description"].lower() for c in consumables]
    assert any("primer" in d for d in descriptions)


def test_consumables_have_line_totals():
    """Every consumable has a line_total > 0."""
    sourcer = HardwareSourcer()
    consumables = sourcer.estimate_consumables(
        weld_linear_inches=150.0,
        total_sq_ft=40.0,
    )
    for c in consumables:
        assert "line_total" in c
        assert c["line_total"] > 0
        assert c["line_total"] == round(c["quantity"] * c["unit_price"], 2)


def test_consumables_zero_weld_returns_empty():
    """Zero weld inches produces no consumables."""
    sourcer = HardwareSourcer()
    consumables = sourcer.estimate_consumables(
        weld_linear_inches=0.0,
        total_sq_ft=0.0,
    )
    assert consumables == []


# ============================================================
# 23-26. Full Pipeline Tests
# ============================================================

def test_full_pipeline_cantilever_gate(client, auth_headers):
    """Full pipeline: intake → clarify → calculate → estimate → price for cantilever gate."""
    session_id = _run_pipeline_to_price_stage(client, auth_headers)

    resp = client.post(f"/api/session/{session_id}/price", headers=auth_headers)
    assert resp.status_code == 200

    data = resp.json()
    pq = data["priced_quote"]

    # Verify all sections present
    assert len(pq["materials"]) > 0
    assert pq["subtotal"] > 0
    assert pq["total"] > 0
    assert pq["total"] >= pq["subtotal"]  # markup >= 0%
    assert len(pq["assumptions"]) >= 3
    assert len(pq["exclusions"]) >= 2

    # Finishing is never optional
    assert pq["finishing"] is not None
    assert "method" in pq["finishing"]


def test_full_pipeline_straight_railing(client, auth_headers):
    """Full pipeline for straight railing — different job type, same flow."""
    # Start session
    resp = client.post("/api/session/start", json={
        "description": "20 foot exterior railing with cable infill",
        "job_type": "straight_railing",
    }, headers=auth_headers)
    session_id = resp.json()["session_id"]

    # Answer all required fields
    answers = {
        "linear_footage": "20",
        "railing_height": "42 inches (standard)",
        "infill_style": "Cable rail",
        "post_mount_type": "Surface mount flange (bolted on top of slab)",
        "top_rail_profile": "Round tube (1.5\" OD)",
        "finish": "Clearcoat (shows natural steel)",
        "location": "Exterior — exposed to weather",
        "application": "Porch / deck railing",
        "installation": "Full installation (we install on-site)",
    }
    answer_resp = client.post(f"/api/session/{session_id}/answer",
                              json={"answers": answers}, headers=auth_headers)
    assert answer_resp.status_code == 200, f"Answer failed: {answer_resp.json()}"
    assert answer_resp.json()["is_complete"] is True, f"Not complete: {answer_resp.json()}"

    # Calculate
    resp = client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    assert resp.status_code == 200, f"Calculate failed: {resp.json()}"

    # Estimate
    resp = client.post(f"/api/session/{session_id}/estimate", headers=auth_headers)
    assert resp.status_code == 200, f"Estimate failed: {resp.json()}"

    # Price
    resp = client.post(f"/api/session/{session_id}/price", headers=auth_headers)
    assert resp.status_code == 200, f"Price failed: {resp.json()}"
    pq = resp.json()["priced_quote"]

    assert pq["job_type"] == "straight_railing"
    assert pq["subtotal"] > 0
    assert len(pq["exclusions"]) >= 2


def test_pipeline_exclusions_gate_with_motor(client, auth_headers):
    """Gate with motor gets electrical wiring exclusion."""
    session_id = _run_pipeline_to_price_stage(client, auth_headers)

    resp = client.post(f"/api/session/{session_id}/price", headers=auth_headers)
    assert resp.status_code == 200
    exclusions = resp.json()["priced_quote"]["exclusions"]

    # Motor-related exclusion
    exclusion_text = " ".join(exclusions).lower()
    assert "electrical" in exclusion_text or "wiring" in exclusion_text


def test_recalculate_with_markup():
    """PricingEngine.recalculate_with_markup updates total correctly."""
    engine = PricingEngine()
    quote = {"subtotal": 1000.00, "selected_markup_pct": 15, "total": 1150.00}

    updated = engine.recalculate_with_markup(quote, 25)
    assert updated["selected_markup_pct"] == 25
    assert updated["total"] == 1250.00


# ============================================================
# Pipeline helper
# ============================================================

def _run_pipeline_to_price_stage(client, auth_headers) -> str:
    """Run pipeline for cantilever gate up to price stage. Returns session_id."""
    # Start session
    resp = client.post("/api/session/start", json={
        "description": "10 foot cantilever sliding gate with motor",
        "job_type": "cantilever_gate",
    }, headers=auth_headers)
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    # Answer all required fields
    answers = _sample_cantilever_fields()
    resp = client.post(f"/api/session/{session_id}/answer",
                       json={"answers": answers}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_complete"] is True

    # Calculate (Stage 3)
    resp = client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    assert resp.status_code == 200

    # Estimate (Stage 4)
    resp = client.post(f"/api/session/{session_id}/estimate", headers=auth_headers)
    assert resp.status_code == 200

    return session_id
