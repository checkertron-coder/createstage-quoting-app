"""
Tests for Prompt 43 — "Fix the Foundation"

Covers:
- AC-1: Finish pipeline data flow — finishing section rebuilt at /price time
- AC-2: Subtotal refresh — all 7 section subtotal IDs present in template
- AC-3: Labor calibration notes — scaling references, no bare hours
"""

import os


# ---- AC-1: Finish Pipeline ----

def test_finish_field_reaches_finishing_section():
    """PricedQuote built with finish='Powder coat' must NOT have method='raw'."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    session_data = {
        "session_id": "test-43-finish",
        "job_type": "led_sign_custom",
        "fields": {
            "description": "138x28 aluminum LED sign cabinet",
            "finish": "Powder coat (most common)",
            "sign_type": "Cabinet / box sign",
            "dimensions": "138x28x6",
            "letter_height": "18 inches",
            "material": "Aluminum (6061-T6)",
        },
        "material_list": {
            "items": [
                {
                    "description": "AL sq tube 2x2 frame",
                    "material_type": "aluminum_6061",
                    "profile": "al_sq_tube_2x2_0.125",
                    "length_inches": 120,
                    "quantity": 4,
                    "unit_price": 3.00,
                    "line_total": 120.00,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                },
            ],
            "hardware": [],
            "total_weight_lbs": 44.0,
            "total_sq_ft": 50.0,
            "weld_linear_inches": 200,
            "assumptions": [],
        },
        "labor_estimate": {
            "processes": [
                {"process": "layout_setup", "hours": 1.5, "rate": 125, "notes": ""},
                {"process": "cut_prep", "hours": 2.0, "rate": 125, "notes": ""},
                {"process": "fit_tack", "hours": 6.0, "rate": 125, "notes": ""},
                {"process": "full_weld", "hours": 6.0, "rate": 125, "notes": ""},
                {"process": "grind_clean", "hours": 4.0, "rate": 125, "notes": ""},
                {"process": "finish_prep", "hours": 1.0, "rate": 125, "notes": ""},
                {"process": "coating_application", "hours": 0.0, "rate": 125, "notes": ""},
                {"process": "final_inspection", "hours": 0.5, "rate": 125, "notes": ""},
            ],
            "total_hours": 21.0,
        },
        # Pre-built finishing from /estimate — intentionally wrong ("raw")
        # to verify pricing engine REBUILDS it from fields
        "finishing": {
            "method": "raw",
            "area_sq_ft": 50.0,
            "hours": 0.0,
            "materials_cost": 0.0,
            "outsource_cost": 0.0,
            "total": 0.0,
        },
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 15,
            "rate_inshop": 125, "rate_onsite": 145}
    pq = pe.build_priced_quote(session_data, user)
    finishing = pq["finishing"]
    # P43 fix: pricing engine should rebuild finishing from fields.get("finish")
    assert finishing["method"] == "powder_coat", \
        "Finishing should be 'powder_coat', got '%s'" % finishing["method"]
    assert finishing["total"] > 0, "Finishing total should be > $0"
    assert finishing["outsource_cost"] > 0, "Powder coat has outsource cost"


def test_finish_field_missing_uses_description():
    """When finish field is empty, pricing engine extracts from description."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    session_data = {
        "session_id": "test-43-desc",
        "job_type": "led_sign_custom",
        "fields": {
            "description": "aluminum LED sign cabinet, powder coated black",
            # No "finish" key — simulates the field being missing
        },
        "material_list": {
            "items": [],
            "hardware": [],
            "total_weight_lbs": 10.0,
            "total_sq_ft": 30.0,
            "weld_linear_inches": 80,
            "assumptions": [],
        },
        "labor_estimate": {
            "processes": [
                {"process": "finish_prep", "hours": 1.0, "rate": 125, "notes": ""},
            ],
            "total_hours": 1.0,
        },
        "finishing": {"method": "raw", "area_sq_ft": 30, "hours": 0,
                      "materials_cost": 0, "outsource_cost": 0, "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 0,
            "rate_inshop": 125, "rate_onsite": 145}
    pq = pe.build_priced_quote(session_data, user)
    # Description says "powder coated" — should extract that
    assert pq["finishing"]["method"] == "powder_coat", \
        "Should extract powder_coat from description, got '%s'" % pq["finishing"]["method"]


# ---- AC-2: Subtotal Refresh ----

def test_subtotal_ids_in_template():
    """All 7 section subtotal element IDs must exist in quote-flow.js template."""
    js_path = os.path.join(
        os.path.dirname(__file__), "..", "frontend", "js", "quote-flow.js"
    )
    with open(js_path) as f:
        content = f.read()

    required_ids = [
        "material-subtotal-amount",
        "hardware-subtotal-amount",
        "consumable-subtotal-amount",
        "labor-subtotal-amount",
        "finishing-subtotal-amount",
        "subtotal-amount",
        "grand-total-amount",
    ]
    for eid in required_ids:
        assert ('id="%s"' % eid) in content, \
            "Missing element ID '%s' in quote-flow.js template" % eid


def test_recalc_totals_updates_all_subtotals():
    """_recalcTotals must reference all 7 subtotal element IDs."""
    js_path = os.path.join(
        os.path.dirname(__file__), "..", "frontend", "js", "quote-flow.js"
    )
    with open(js_path) as f:
        content = f.read()

    # Find the _recalcTotals function DEFINITION (not a call site)
    idx = content.find("_recalcTotals() {")
    assert idx > 0, "_recalcTotals function definition not found"
    region = content[idx:idx + 1500]

    for eid in ("material-subtotal-amount", "hardware-subtotal-amount",
                "consumable-subtotal-amount", "labor-subtotal-amount",
                "finishing-subtotal-amount", "subtotal-amount",
                "grand-total-amount"):
        assert eid in region, \
            "_recalcTotals does not update '%s'" % eid


# ---- AC-3: Labor Calibration ----

def test_labor_calibration_has_scaling_rules():
    """Calibration notes must have SCALING RULES section."""
    from backend.calculators.labor_calculator import LABOR_CALIBRATION_NOTES
    assert "SCALING RULES" in LABOR_CALIBRATION_NOTES
    assert "BENCHMARK" in LABOR_CALIBRATION_NOTES


def test_labor_calibration_no_verbatim_copy_risk():
    """Calibration notes should present benchmarks with scope context,
    not bare hour values that Opus will copy verbatim.

    The old format had: 'Fit & Tack: ~6 hrs' which Opus copied for every job.
    The new format should have scope descriptors (piece count, weld inches)
    alongside hour benchmarks so Opus scales proportionally.
    """
    from backend.calculators.labor_calculator import LABOR_CALIBRATION_NOTES
    # Should NOT have old-style bare hour pattern without scope context
    # Old: "Fit & Tack: ~6 hrs | Full Weld: ~6-8 hrs"
    # New: hours appear only inside benchmark blocks with scope descriptors
    assert "Pieces:" in LABOR_CALIBRATION_NOTES, \
        "Benchmarks should include piece count for scaling context"
    assert "Weld:" in LABOR_CALIBRATION_NOTES, \
        "Benchmarks should include weld inches for scaling context"
    # The scaling rule about proportionality
    assert "Scale" in LABOR_CALIBRATION_NOTES
