"""
Session 4 acceptance tests — AI labor estimation engine (Stage 4).

Tests:
1-6.   Labor estimator core tests
7-10.  Fallback tests
11-16. Finishing builder tests
17-18. Historical validator tests
19-22. Prompt construction tests
23-26. Pipeline integration tests

All tests mock Gemini — no API key required.
"""

import json
import math
import pytest
from unittest.mock import patch, MagicMock

from backend.labor_estimator import LaborEstimator, LABOR_PROCESSES
from backend.finishing import FinishingBuilder
from backend.historical_validator import HistoricalValidator
from backend.calculators.cantilever_gate import CantileverGateCalculator
from backend.calculators.straight_railing import StraightRailingCalculator
from backend.calculators.repair_decorative import RepairDecorativeCalculator


# --- Test fixtures ---

def _sample_material_list():
    """A realistic cantilever gate material list for testing."""
    calc = CantileverGateCalculator()
    fields = {
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
    return calc.calculate(fields), fields


def _sample_quote_params(fields=None):
    """Sample QuoteParams for testing."""
    if fields is None:
        _, fields = _sample_material_list()
    return {
        "job_type": "cantilever_gate",
        "user_id": 1,
        "session_id": "test-session-123",
        "fields": fields,
        "photos": [],
        "notes": "",
    }


def _sample_rates():
    return {"rate_inshop": 125.00, "rate_onsite": 145.00}


def _mock_gemini_response():
    """A realistic Gemini response for a cantilever gate."""
    return json.dumps({
        "layout_setup": {"hours": 1.5, "notes": "Complex gate with motor prep, 3 post layout"},
        "cut_prep": {"hours": 2.0, "notes": "15 pieces, mixed miter and square cuts on 11ga tube"},
        "fit_tack": {"hours": 3.5, "notes": "Gate frame assembly + expanded metal infill fitting"},
        "full_weld": {"hours": 4.0, "notes": "~336 linear inches, MIG on 11ga mild steel"},
        "grind_clean": {"hours": 1.5, "notes": "All welds ground for powder coat prep"},
        "finish_prep": {"hours": 1.0, "notes": "Sand and degrease for outsourced powder coat"},
        "clearcoat": {"hours": 0.0, "notes": "N/A — powder coat finish (outsourced)"},
        "paint": {"hours": 0.0, "notes": "N/A — powder coat finish (outsourced)"},
        "hardware_install": {"hours": 2.5, "notes": "Motor mount, 2 roller carriages, latch, gate stops"},
        "site_install": {"hours": 6.0, "notes": "3 posts in concrete, gate hang, motor wiring, alignment"},
        "final_inspection": {"hours": 0.5, "notes": "Function test, touch-up, client walkthrough"},
    })


# ============================================================
# Labor Estimator Core Tests
# ============================================================

def test_estimator_returns_all_11_processes():
    """Every LaborEstimate must have all 11 processes, even if hours=0."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    result = estimator.estimate(ml, _sample_quote_params(fields), _sample_rates())

    assert len(result["processes"]) == 11
    process_names = [p["process"] for p in result["processes"]]
    for proc in LABOR_PROCESSES:
        assert proc in process_names, f"Missing process: {proc}"


def test_estimator_total_is_sum_not_ai():
    """total_hours must equal sum of all process hours — never trust AI total."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    result = estimator.estimate(ml, _sample_quote_params(fields), _sample_rates())

    computed_sum = round(sum(p["hours"] for p in result["processes"]), 2)
    assert result["total_hours"] == computed_sum


def test_estimator_never_returns_single_total():
    """If AI response has a 'total' key, it is ignored — total is always computed."""
    # Inject a 'total' into the AI response
    ai_response = json.loads(_mock_gemini_response())
    ai_response["total"] = 999.0  # This should be ignored
    response_text = json.dumps(ai_response)

    estimator = LaborEstimator()
    result = estimator._parse_response(response_text, _sample_rates(), is_onsite=False)

    # Total should be sum of process hours, NOT 999
    assert result["total_hours"] != 999.0
    computed_sum = round(sum(p["hours"] for p in result["processes"]), 2)
    assert result["total_hours"] == computed_sum


def test_estimator_applies_inshop_rate():
    """Non-install processes use rate_inshop."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    result = estimator.estimate(ml, _sample_quote_params(fields), _sample_rates())

    for p in result["processes"]:
        if p["process"] != "site_install":
            assert p["rate"] == 125.00, \
                f"{p['process']} should use inshop rate 125, got {p['rate']}"


def test_estimator_applies_onsite_rate_for_install():
    """site_install uses rate_onsite."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    result = estimator.estimate(ml, _sample_quote_params(fields), _sample_rates())

    install_process = [p for p in result["processes"] if p["process"] == "site_install"]
    assert len(install_process) == 1
    assert install_process[0]["rate"] == 145.00


def test_estimator_onsite_job_all_onsite_rate():
    """If entire job is on-site (repair in place), all processes use rate_onsite."""
    calc = RepairDecorativeCalculator()
    fields = {
        "repair_type": "Broken weld (piece detached)",
        "item_type": "Railing (stair or flat)",
        "material_type": "Mild steel / carbon steel",
        "can_remove": "Must repair in place — cannot remove",
        "finish": "Match existing",
    }
    ml = calc.calculate(fields)
    qp = {
        "job_type": "repair_decorative",
        "fields": fields,
        "photos": [],
        "notes": "",
    }

    estimator = LaborEstimator()
    result = estimator.estimate(ml, qp, _sample_rates())

    for p in result["processes"]:
        assert p["rate"] == 145.00, \
            f"On-site job: {p['process']} should use onsite rate 145, got {p['rate']}"


# ============================================================
# Fallback Tests
# ============================================================

def test_fallback_when_no_api_key():
    """No GEMINI_API_KEY → fallback estimate returned, not an error."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    # No API key is set in test env — should use fallback automatically
    result = estimator.estimate(ml, _sample_quote_params(fields), _sample_rates())

    assert "processes" in result
    assert "total_hours" in result
    assert result["total_hours"] > 0


def test_fallback_produces_valid_contract():
    """Fallback output matches LaborEstimate TypedDict."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    result = estimator._fallback_estimate(ml, _sample_quote_params(fields), _sample_rates())

    # Check contract
    assert "processes" in result
    assert "total_hours" in result
    assert "flagged" in result
    assert "flag_reason" in result
    assert isinstance(result["processes"], list)
    assert len(result["processes"]) == 11

    for p in result["processes"]:
        assert "process" in p
        assert "hours" in p
        assert "rate" in p
        assert "notes" in p
        assert isinstance(p["hours"], float)
        assert p["hours"] >= 0.0


def test_fallback_layout_and_inspection_never_zero():
    """layout_setup and final_inspection always > 0."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    result = estimator._fallback_estimate(ml, _sample_quote_params(fields), _sample_rates())

    processes_by_name = {p["process"]: p for p in result["processes"]}
    assert processes_by_name["layout_setup"]["hours"] > 0
    assert processes_by_name["final_inspection"]["hours"] > 0


def test_fallback_notes_indicate_rule_based():
    """Every process note mentions rule-based/fallback."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    result = estimator._fallback_estimate(ml, _sample_quote_params(fields), _sample_rates())

    for p in result["processes"]:
        assert "rule-based" in p["notes"].lower() or "fallback" in p["notes"].lower(), \
            f"Process {p['process']} note should mention rule-based: {p['notes']}"


# ============================================================
# Finishing Builder Tests
# ============================================================

def test_finishing_raw_steel():
    """raw finish → method=raw, hours=0, costs=0."""
    fb = FinishingBuilder()
    result = fb.build("raw", 100.0, [])

    assert result["method"] == "raw"
    assert result["area_sq_ft"] > 0
    assert result["hours"] == 0.0
    assert result["materials_cost"] == 0.0
    assert result["outsource_cost"] == 0.0
    assert result["total"] == 0.0


def test_finishing_clearcoat():
    """clearcoat → in-house hours, material cost from sq_ft."""
    processes = [
        {"process": "finish_prep", "hours": 1.0, "rate": 125.0, "notes": ""},
        {"process": "clearcoat", "hours": 0.5, "rate": 125.0, "notes": ""},
    ]
    fb = FinishingBuilder()
    result = fb.build("Clear coat / lacquer", 100.0, processes)

    assert result["method"] == "clearcoat"
    assert result["area_sq_ft"] == 100.0
    assert result["hours"] == 1.5  # finish_prep + clearcoat
    assert result["materials_cost"] == round(100.0 * 0.35, 2)
    assert result["outsource_cost"] == 0.0
    assert result["total"] == result["materials_cost"]


def test_finishing_powder_coat_outsourced():
    """powder coat → outsource_cost calculated, in-house hours = prep only."""
    processes = [
        {"process": "finish_prep", "hours": 0.75, "rate": 125.0, "notes": ""},
        {"process": "clearcoat", "hours": 0.0, "rate": 125.0, "notes": ""},
        {"process": "paint", "hours": 0.0, "rate": 125.0, "notes": ""},
    ]
    fb = FinishingBuilder()
    result = fb.build("Powder coat (most durable, outsourced)", 200.0, processes)

    assert result["method"] == "powder_coat"
    assert result["area_sq_ft"] == 200.0
    assert result["hours"] == 0.75  # Just prep
    assert result["materials_cost"] == 0.0
    assert result["outsource_cost"] == round(200.0 * 3.50, 2)
    assert result["total"] == result["outsource_cost"]


def test_finishing_galvanized_outsourced():
    """galvanized → outsource_cost calculated."""
    fb = FinishingBuilder()
    result = fb.build("Hot-dip galvanized", 150.0, [])

    assert result["method"] == "galvanized"
    assert result["outsource_cost"] == round(150.0 * 2.00, 2)
    assert result["hours"] == 0.0
    assert result["materials_cost"] == 0.0


def test_finishing_always_has_area():
    """Every finish type has area_sq_ft > 0 (even raw)."""
    fb = FinishingBuilder()

    for finish_type in ["raw", "clearcoat", "paint", "powder_coat", "galvanized"]:
        result = fb.build(finish_type, 50.0, [])
        assert result["area_sq_ft"] > 0, f"{finish_type} should have positive area"

    # Even with 0 sq ft input, should get at least 1.0
    result = fb.build("raw", 0.0, [])
    assert result["area_sq_ft"] >= 1.0


def test_finishing_never_optional():
    """FinishingSection is always present — build() always returns a dict."""
    fb = FinishingBuilder()

    # Even with empty/weird inputs
    for finish in ["raw", "", "unknown finish", "Rust-oleum spray", "powder_coat"]:
        result = fb.build(finish, 10.0, [])
        assert isinstance(result, dict)
        assert "method" in result
        assert "area_sq_ft" in result
        assert "hours" in result
        assert "materials_cost" in result
        assert "outsource_cost" in result
        assert "total" in result


# ============================================================
# Historical Validator Tests
# ============================================================

def test_validator_no_history_not_flagged():
    """No historical data → flagged=False."""
    validator = HistoricalValidator()
    estimate = {
        "processes": [],
        "total_hours": 20.0,
        "flagged": False,
        "flag_reason": None,
    }

    result = validator.validate(estimate, "cantilever_gate")
    assert result["flagged"] is False
    assert result["flag_reason"] is None


def test_validator_records_actual(db):
    """record_actual creates entry in historical_actuals table."""
    from backend import models

    # Create a user and a quote first
    user = models.User(email="validator@test.com", password_hash="hash")
    db.add(user)
    db.commit()

    quote = models.Quote(
        quote_number="Q-VAL-001",
        user_id=user.id,
        job_type="cantilever_gate",
    )
    db.add(quote)
    db.commit()

    validator = HistoricalValidator()
    validator.record_actual(
        quote_id=quote.id,
        actual_hours_by_process={"layout_setup": 1.5, "cut_prep": 2.0, "full_weld": 5.0},
        actual_material_cost=450.0,
        notes="Test actual recording",
        db_session=db,
    )

    # Verify the record was created
    actuals = db.query(models.HistoricalActual).filter(
        models.HistoricalActual.quote_id == quote.id,
    ).all()
    assert len(actuals) == 1
    assert actuals[0].actual_hours_by_process["layout_setup"] == 1.5
    assert actuals[0].actual_material_cost == 450.0
    assert actuals[0].notes == "Test actual recording"


# ============================================================
# Prompt Construction Tests
# ============================================================

def test_prompt_includes_piece_count():
    """Gemini prompt contains material piece count."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    prompt = estimator._build_prompt(ml, _sample_quote_params(fields))

    assert "pieces" in prompt.lower() or "piece" in prompt.lower()
    # Should contain the actual count
    piece_count = sum(item.get("quantity", 1) for item in ml["items"])
    assert str(piece_count) in prompt


def test_prompt_includes_weld_inches():
    """Gemini prompt contains weld_linear_inches."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    prompt = estimator._build_prompt(ml, _sample_quote_params(fields))

    weld_str = f"{ml['weld_linear_inches']:.1f}"
    assert weld_str in prompt


def test_prompt_includes_finish_type():
    """Gemini prompt mentions the finish type."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    prompt = estimator._build_prompt(ml, _sample_quote_params(fields))

    assert "powder" in prompt.lower() or "finish" in prompt.lower()


def test_prompt_forbids_total():
    """Prompt text contains instruction not to return total."""
    ml, fields = _sample_material_list()
    estimator = LaborEstimator()
    prompt = estimator._build_prompt(ml, _sample_quote_params(fields))

    assert "do not" in prompt.lower() and "total" in prompt.lower()


# ============================================================
# Pipeline Integration Tests
# ============================================================

def test_estimate_endpoint_after_calculate(client, auth_headers):
    """Session in 'estimate' stage → /estimate returns labor breakdown."""
    # Start session
    start_resp = client.post("/api/session/start", json={
        "description": "10 ft cantilever gate, 6 ft tall, with motor",
        "job_type": "cantilever_gate",
    }, headers=auth_headers)
    assert start_resp.status_code == 200
    session_id = start_resp.json()["session_id"]

    # Answer all required fields
    client.post(f"/api/session/{session_id}/answer", json={
        "answers": {
            "clear_width": "10",
            "height": "6",
            "frame_material": "Square tube (most common)",
            "frame_gauge": "11 gauge (0.120\" - standard for gates)",
            "infill_type": "Expanded metal",
            "post_count": "3 posts (standard)",
            "finish": "Powder coat (most durable, outsourced)",
            "installation": "Full installation (gate + posts + concrete)",
        },
    }, headers=auth_headers)

    # Calculate (Stage 3)
    calc_resp = client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    assert calc_resp.status_code == 200

    # Estimate (Stage 4)
    est_resp = client.post(f"/api/session/{session_id}/estimate", headers=auth_headers)
    assert est_resp.status_code == 200
    data = est_resp.json()

    assert "labor_estimate" in data
    assert "finishing" in data
    assert "total_labor_hours" in data
    assert "total_labor_cost" in data
    assert len(data["labor_estimate"]["processes"]) == 11
    assert data["total_labor_hours"] > 0
    assert data["total_labor_cost"] > 0
    assert data["finishing"]["method"] == "powder_coat"


def test_estimate_endpoint_wrong_stage(client, auth_headers):
    """Session not in 'estimate' stage → 400 error."""
    # Start session but don't calculate
    start_resp = client.post("/api/session/start", json={
        "description": "Need a railing",
        "job_type": "straight_railing",
    }, headers=auth_headers)
    session_id = start_resp.json()["session_id"]

    # Try to estimate without calculating first
    est_resp = client.post(f"/api/session/{session_id}/estimate", headers=auth_headers)
    assert est_resp.status_code == 400
    assert "estimate" in est_resp.json()["detail"].lower() or "stage" in est_resp.json()["detail"].lower()


def test_estimate_stores_in_session(client, auth_headers):
    """After /estimate, session params_json contains labor_estimate and finishing."""
    # Full pipeline: start → answer → calculate → estimate
    start_resp = client.post("/api/session/start", json={
        "description": "10 ft cantilever gate",
        "job_type": "cantilever_gate",
    }, headers=auth_headers)
    session_id = start_resp.json()["session_id"]

    client.post(f"/api/session/{session_id}/answer", json={
        "answers": {
            "clear_width": "10",
            "height": "6",
            "frame_material": "Square tube (most common)",
            "frame_gauge": "11 gauge (0.120\" - standard for gates)",
            "infill_type": "Expanded metal",
            "post_count": "3 posts (standard)",
            "finish": "Powder coat (most durable, outsourced)",
            "installation": "Full installation (gate + posts + concrete)",
        },
    }, headers=auth_headers)

    client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    client.post(f"/api/session/{session_id}/estimate", headers=auth_headers)

    # Check session status — stage should be "price"
    status_resp = client.get(f"/api/session/{session_id}/status", headers=auth_headers)
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["stage"] == "price"


def test_full_pipeline_intake_to_estimate(client, auth_headers):
    """Start session → answer questions → calculate → estimate — full Stage 1-4 flow."""
    # Stage 1: Start session
    start_resp = client.post("/api/session/start", json={
        "description": "I need a 40 foot straight railing, 42 inches tall, picket infill, powder coat",
        "job_type": "straight_railing",
    }, headers=auth_headers)
    assert start_resp.status_code == 200
    session_id = start_resp.json()["session_id"]

    # Stage 2: Answer required fields
    answer_resp = client.post(f"/api/session/{session_id}/answer", json={
        "answers": {
            "linear_footage": "40",
            "location": "Exterior — exposed to weather",
            "application": "Porch / deck railing",
            "railing_height": "42\" (commercial standard / IBC compliant)",
            "infill_style": "Pickets (vertical bars — most common)",
            "top_rail_profile": "2\" square tube",
            "baluster_spacing": "4\" on-center (standard code compliant)",
            "post_mount_type": "Surface mount (flange bolted to concrete)",
            "post_spacing": "6 feet (standard)",
            "finish": "Powder coat (most durable, outsourced)",
            "installation": "Full installation",
        },
    }, headers=auth_headers)
    assert answer_resp.status_code == 200
    assert answer_resp.json()["is_complete"] is True

    # Stage 3: Calculate materials
    calc_resp = client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    assert calc_resp.status_code == 200
    material_list = calc_resp.json()["material_list"]
    assert len(material_list["items"]) >= 3
    assert material_list["total_weight_lbs"] > 0

    # Stage 4: Estimate labor
    est_resp = client.post(f"/api/session/{session_id}/estimate", headers=auth_headers)
    assert est_resp.status_code == 200
    data = est_resp.json()

    # Verify full labor estimate structure
    assert len(data["labor_estimate"]["processes"]) == 11
    assert data["total_labor_hours"] > 0
    assert data["total_labor_cost"] > 0

    # Verify finishing section
    assert data["finishing"]["method"] == "powder_coat"
    assert data["finishing"]["area_sq_ft"] > 0
    assert data["finishing"]["outsource_cost"] > 0

    # Verify session transitioned to "price" stage
    status_resp = client.get(f"/api/session/{session_id}/status", headers=auth_headers)
    assert status_resp.json()["stage"] == "price"
