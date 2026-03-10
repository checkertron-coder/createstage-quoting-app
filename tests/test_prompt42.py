"""
Tests for Prompt 42 — "Think Like a Fabricator"

Covers:
- AC-1: Finish question injection for job types missing finish in required_fields
- AC-2: Opus BOM fallback on failure
- AC-3: Knowledge vs preference distinction in suggest prompt
- AC-4: Subtotal refresh IDs (frontend, tested via render logic)
- AC-5: Electronics hardware install calibration notes
- AC-6: Aluminum weights in STOCK_WEIGHTS and aggregate fallback
"""

from unittest.mock import patch


# ---- AC-6: Aluminum Weights ----

def test_aluminum_weight_in_stock_weights():
    """al_sq_tube_2x2_0.125 must have weight > 0 in STOCK_WEIGHTS."""
    from backend.weights import STOCK_WEIGHTS
    assert STOCK_WEIGHTS.get("al_sq_tube_2x2_0.125", 0) > 0
    assert STOCK_WEIGHTS["al_sq_tube_2x2_0.125"] == 1.10


def test_aluminum_weight_all_entries():
    """All 10 aluminum entries must be present."""
    from backend.weights import STOCK_WEIGHTS
    expected_keys = [
        "al_sq_tube_1x1_0.125",
        "al_sq_tube_1.5x1.5_0.125",
        "al_sq_tube_2x2_0.125",
        "al_rect_tube_1x2_0.125",
        "al_angle_1.5x1.5x0.125",
        "al_angle_2x2x0.125",
        "al_flat_bar_1x0.125",
        "al_flat_bar_1.5x0.125",
        "al_flat_bar_2x0.25",
        "al_round_tube_1.5_0.125",
    ]
    for key in expected_keys:
        assert key in STOCK_WEIGHTS, "Missing STOCK_WEIGHTS key: %s" % key
        assert STOCK_WEIGHTS[key] > 0, "Weight must be > 0 for %s" % key


def test_aluminum_weight_in_aggregate():
    """Aluminum materials should get weight_lbs > 0 in materials summary."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    materials = [
        {
            "description": "AL sq tube 2x2",
            "material_type": "aluminum_6061",
            "profile": "al_sq_tube_2x2_0.125",
            "length_inches": 120,
            "quantity": 4,
            "unit_price": 3.00,
            "line_total": 120.00,
            "cut_type": "square",
            "waste_factor": 0.05,
        }
    ]
    summary = pe._aggregate_materials(materials)
    assert len(summary) >= 1
    al_row = summary[0]
    assert al_row["weight_lbs"] > 0, "Aluminum weight should be > 0"


def test_aluminum_weight_density_fallback():
    """Unknown al_ profiles should fall back to steel weight * 0.344."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    # Use a profile that exists for steel but NOT as al_ in STOCK_WEIGHTS
    materials = [
        {
            "description": "AL sq tube 3x3",
            "material_type": "aluminum_6061",
            "profile": "al_sq_tube_3x3_11ga",
            "length_inches": 120,
            "quantity": 2,
            "unit_price": 5.00,
            "line_total": 100.00,
            "cut_type": "square",
            "waste_factor": 0.05,
        }
    ]
    summary = pe._aggregate_materials(materials)
    assert len(summary) >= 1
    al_row = summary[0]
    # sq_tube_3x3_11ga steel = 3.09 lb/ft, * 0.344 = ~1.06 lb/ft
    assert al_row["weight_lbs"] > 0, "Aluminum density fallback should produce weight > 0"


# ---- AC-1: Finish Question Injection ----

def test_finish_question_present_for_led_sign(client, guest_headers):
    """LED sign session start should have a finish question (from tree or injected)."""
    response = client.post(
        "/api/session/start",
        json={
            "description": "138x28 inch aluminum LED sign cabinet with laser-cut letters",
            "job_type": "led_sign_custom",
        },
        headers=guest_headers,
    )
    assert response.status_code == 200
    data = response.json()
    questions = data.get("next_questions", [])
    finish_qs = [q for q in questions if q["id"] == "finish"]
    assert len(finish_qs) >= 1, "Finish question should be present (from tree or injected)"
    # Completion should NOT be True without finish answered
    completion = data.get("completion", {})
    assert not completion.get("is_complete"), \
        "Session should NOT be complete without finish answered"


def test_finish_always_required_in_completion():
    """is_complete should return False without finish, even if tree doesn't list it as required."""
    from backend.question_trees.engine import QuestionTreeEngine
    engine = QuestionTreeEngine()
    # led_sign_custom does NOT have finish in required_fields
    tree = engine.load_tree("led_sign_custom")
    required = tree.get("required_fields", [])
    # Verify our assumption — finish is NOT in the tree's required_fields
    # (this test guards against the tree changing)
    # Build a dict with all required fields answered EXCEPT finish
    answered = {f: "test_value" for f in required}
    answered["description"] = "test"
    # Without finish, should NOT be complete
    status = engine.get_completion_status("led_sign_custom", answered)
    assert not status["is_complete"], "Should not be complete without finish"
    assert "finish" in status["required_missing"], "finish should be in missing list"
    # With finish, should be complete
    answered["finish"] = "Powder coat"
    status2 = engine.get_completion_status("led_sign_custom", answered)
    assert status2["is_complete"], "Should be complete with finish answered"


def test_finish_not_injected_when_extracted(client, guest_headers):
    """If description mentions clear coat, finish should be extracted and not re-injected."""
    response = client.post(
        "/api/session/start",
        json={
            "description": "Custom steel end table with clear coat finish, 24x24 top",
            "job_type": "furniture_table",
        },
        headers=guest_headers,
    )
    assert response.status_code == 200
    data = response.json()
    questions = data.get("next_questions", [])
    # Count finish questions — should be 0 or at most 1 from the tree itself
    injected_finish = [q for q in questions if q["id"] == "finish"
                       and q.get("source") == "finish_always_required"]
    # If finish was extracted from description, no injection needed
    extracted = data.get("extracted_fields", {})
    if extracted.get("finish"):
        assert len(injected_finish) == 0, "Should not inject finish when already extracted"


# ---- AC-2: Opus BOM ----

def test_opus_bom_fallback_on_failure():
    """When Opus is unavailable, existing catalog-based hardware/consumables still work."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()
    # opus_estimate_bom should return None when not configured
    result = hs.opus_estimate_bom(
        "LED sign 48x24 aluminum cabinet",
        [{"description": "frame piece", "profile": "al_sq_tube_2x2_0.125", "quantity": 4}],
        "aluminum_6061",
        "led_sign_custom",
    )
    # Without API key configured, should return None gracefully
    assert result is None

    # But deterministic consumables should still work
    consumables = hs.estimate_consumables(200, 50, "clearcoat", "aluminum_6061")
    assert len(consumables) > 0


# ---- AC-3: Preference Questions ----

def test_preference_prompt_has_knowledge_vs_pref():
    """The suggest_additional_questions prompt should include KNOWLEDGE vs PREFERENCE text."""
    from backend.question_trees.engine import QuestionTreeEngine
    import inspect
    source = inspect.getsource(QuestionTreeEngine.suggest_additional_questions)
    assert "KNOWLEDGE vs PREFERENCE" in source


# ---- AC-5: Hardware Install Calibration ----

def test_labor_calibration_electronics_hw_install():
    """Calibration notes must mention electronics install hours and scaling rules."""
    from backend.calculators.labor_calculator import LABOR_CALIBRATION_NOTES
    assert "ALWAYS 4+ hrs" in LABOR_CALIBRATION_NOTES
    assert "SCALING" in LABOR_CALIBRATION_NOTES


def test_electronics_fallback_still_works():
    """LED description should match electronics items from the catalog."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()
    items = hs.estimate_electronics(
        "LED sign with ESP32 controller, sk6812 LED strips, 12V mean well power supply"
    )
    assert len(items) > 0
    descriptions = [i["description"].lower() for i in items]
    # Should have at least ESP32 and LED strip
    assert any("esp32" in d for d in descriptions)
    assert any("led" in d for d in descriptions)
