"""
Tests for Prompt 43 — Fabricator Feedback Fixes (Quotes #85-88)

Covers:
- AC-1: Finish pipeline data flow — finishing section rebuilt at /price time
- AC-2: Subtotal refresh — all 7 section subtotal IDs present in template
- AC-3: Labor calibration notes — scaling references, no bare hours
- Fix 1: "sticks" → "ft" display text
- Fix 2: Weight total row in materials table
- Fix 3: Plate remainder sqft for area-sold items
- Fix 4: Gauge enforcement in _build_prompt()
- Fix 5: LED sign question tree — 3 new construction questions
- Fix 6: Clearcoat finishing — 2K urethane vs spray can
"""

import json
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


# ---- Fix 1: "sticks" → "ft" ----

def test_stock_col_no_sticks_word():
    """PDF generator must not use 'sticks' in stock column display."""
    pdf_path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "pdf_generator.py"
    )
    with open(pdf_path) as f:
        content = f.read()
    # "sticks" should not appear as display text in stock columns
    # Internal field names like sticks_needed are OK
    assert "sticks\"" not in content and "sticks'" not in content, \
        "PDF still uses 'sticks' in display text"


# ---- Fix 2: Weight Total Row ----

def test_materials_summary_total_weight():
    """Materials summary entries must have weight_lbs and sum > 0."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    session_data = {
        "session_id": "test-43-weight",
        "job_type": "straight_railing",
        "fields": {"description": "10ft railing with 1.5\" sq tube", "finish": "raw"},
        "material_list": {
            "items": [
                {"description": "1.5\" sq tube", "material_type": "steel",
                 "profile": "sq_tube_1.5x1.5_11ga", "length_inches": 120,
                 "quantity": 2, "unit_price": 1.80, "line_total": 36.00,
                 "cut_type": "square", "waste_factor": 0.05},
                {"description": "0.5\" sq bar pickets", "material_type": "steel",
                 "profile": "sq_bar_0.5", "length_inches": 36,
                 "quantity": 20, "unit_price": 0.65, "line_total": 39.00,
                 "cut_type": "square", "waste_factor": 0.05},
            ],
            "hardware": [], "total_weight_lbs": 60.0,
            "total_sq_ft": 15.0, "weld_linear_inches": 120,
            "assumptions": [],
        },
        "labor_estimate": {
            "processes": [{"process": "cut_prep", "hours": 1.0, "rate": 125, "notes": ""}],
            "total_hours": 1.0,
        },
        "finishing": {"method": "raw", "area_sq_ft": 15, "hours": 0,
                      "materials_cost": 0, "outsource_cost": 0, "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 0,
            "rate_inshop": 125, "rate_onsite": 145}
    pq = pe.build_priced_quote(session_data, user)
    summary = pq.get("materials_summary", [])
    assert len(summary) > 0, "materials_summary should not be empty"
    total_weight = sum(s.get("weight_lbs", 0) for s in summary)
    assert total_weight > 0, "Total weight should be > 0, got %.1f" % total_weight


# ---- Fix 3: Plate Remainder sqft ----

def test_plate_remainder_sqft_in_aggregate():
    """Area-sold items (sheet/plate) should get remainder_sqft > 0
    when the ordered sheet area exceeds the actual piece area."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    session_data = {
        "session_id": "test-43-plate-rem",
        "job_type": "led_sign_custom",
        "fields": {"description": "sign panel", "finish": "raw"},
        "material_list": {
            "items": [
                {"description": "AL sheet panel", "material_type": "aluminum_6061",
                 "profile": "al_sheet_0.125", "length_inches": 24,
                 "quantity": 1, "unit_price": 5.10, "line_total": 5.10,
                 "cut_type": "square", "waste_factor": 0.0,
                 "width_inches": 24},
            ],
            "hardware": [], "total_weight_lbs": 10.0,
            "total_sq_ft": 4.0, "weld_linear_inches": 0,
            "assumptions": [],
        },
        # detailed_cut_list needed for profile_piece_areas calculation
        "detailed_cut_list": [
            {"profile": "al_sheet_0.125", "length_inches": 24,
             "width_inches": 24, "quantity": 1, "piece_name": "panel"},
        ],
        "labor_estimate": {
            "processes": [], "total_hours": 0,
        },
        "finishing": {"method": "raw", "area_sq_ft": 4, "hours": 0,
                      "materials_cost": 0, "outsource_cost": 0, "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 0,
            "rate_inshop": 125, "rate_onsite": 145}
    pq = pe.build_priced_quote(session_data, user)
    summary = pq.get("materials_summary", [])
    # Find the sheet entry
    sheet_entries = [s for s in summary if "sheet" in str(s.get("profile", "")).lower()]
    if sheet_entries:
        entry = sheet_entries[0]
        # If a full sheet was ordered for a small piece, remainder_sqft should exist
        if entry.get("sheets_needed", 0) > 0:
            assert "remainder_sqft" in entry, \
                "Area-sold entry should have remainder_sqft field"


def test_linear_stock_no_remainder_sqft():
    """Linear stock (tube, bar) should NOT get remainder_sqft."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    session_data = {
        "session_id": "test-43-linear-rem",
        "job_type": "furniture_table",
        "fields": {"description": "table base", "finish": "raw"},
        "material_list": {
            "items": [
                {"description": "2\" sq tube legs", "material_type": "steel",
                 "profile": "sq_tube_2x2_11ga", "length_inches": 30,
                 "quantity": 4, "unit_price": 2.50, "line_total": 25.00,
                 "cut_type": "square", "waste_factor": 0.05},
            ],
            "hardware": [], "total_weight_lbs": 30.0,
            "total_sq_ft": 8.0, "weld_linear_inches": 60,
            "assumptions": [],
        },
        "labor_estimate": {
            "processes": [], "total_hours": 0,
        },
        "finishing": {"method": "raw", "area_sq_ft": 8, "hours": 0,
                      "materials_cost": 0, "outsource_cost": 0, "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 0,
            "rate_inshop": 125, "rate_onsite": 145}
    pq = pe.build_priced_quote(session_data, user)
    summary = pq.get("materials_summary", [])
    for s in summary:
        prof = str(s.get("profile", "")).lower()
        if "tube" in prof or "bar" in prof:
            # Linear stock should use remainder_ft, not remainder_sqft
            assert s.get("remainder_sqft", 0) == 0, \
                "Linear stock '%s' should not have remainder_sqft" % prof


# ---- Fix 4: Gauge Enforcement ----

def test_gauge_constraint_in_build_prompt():
    """_build_prompt() output must contain 'MATERIAL GAUGE' when fields have gauge."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    gen = AICutListGenerator.__new__(AICutListGenerator)
    fields = {
        "description": "aluminum sign cabinet 48x24",
        "material": "Aluminum",
        "material_thickness": "0.125\"",
    }
    prompt = gen._build_prompt("led_sign_custom", fields)
    assert "MATERIAL GAUGE" in prompt, \
        "_build_prompt should include gauge constraint when fields have gauge"


def test_gauge_constraint_covers_all_materials():
    """Gauge constraint text must mention tube, bar, angle — not just sheet/plate."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    gen = AICutListGenerator.__new__(AICutListGenerator)
    fields = {
        "description": "railing",
        "material_thickness": "11ga",
    }
    constraint = gen._detect_gauge_constraint(fields)
    assert "tube" in constraint.lower(), "Constraint should mention tube"
    assert "bar" in constraint.lower(), "Constraint should mention bar"
    assert "angle" in constraint.lower(), "Constraint should mention angle"


# ---- Fix 5: LED Sign Question Tree ----

def test_led_sign_has_construction_questions():
    """LED sign question tree must have material_thickness, cabinet_construction,
    and cabinet_depth questions."""
    tree_path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "question_trees",
        "data", "led_sign_custom.json"
    )
    with open(tree_path) as f:
        tree = json.load(f)
    question_ids = [q["id"] for q in tree["questions"]]
    for qid in ("material_thickness", "cabinet_construction", "cabinet_depth"):
        assert qid in question_ids, \
            "LED sign tree missing question '%s'" % qid


def test_led_sign_cabinet_branches():
    """sign_type branches should include cabinet construction questions."""
    tree_path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "question_trees",
        "data", "led_sign_custom.json"
    )
    with open(tree_path) as f:
        tree = json.load(f)
    sign_type_q = [q for q in tree["questions"] if q["id"] == "sign_type"][0]
    branches = sign_type_q.get("branches", {})
    cabinet_branch = branches.get("Cabinet / box sign (illuminated panel)", [])
    assert "material_thickness" in cabinet_branch, \
        "Cabinet branch should include material_thickness"
    assert "cabinet_construction" in cabinet_branch, \
        "Cabinet branch should include cabinet_construction"
    assert "cabinet_depth" in cabinet_branch, \
        "Cabinet branch should include cabinet_depth"


# ---- Fix 6: Clearcoat Finishing ----

def test_clearcoat_2k_urethane_pricing():
    """50 sqft x $1.50/coat x 3 coats = $225.00 for 2K urethane."""
    from backend.finishing import FinishingBuilder
    fb = FinishingBuilder()
    result = fb.build(
        finish_type="clearcoat",
        total_sq_ft=50.0,
        labor_processes=[],
        clear_coat_type="2K urethane (professional — 3 coats)",
    )
    assert result["materials_cost"] == 225.00, \
        "2K clearcoat: 50 sqft x $1.50 x 3 = $225, got $%.2f" % result["materials_cost"]
    assert result["coat_count"] == 3
    assert result["clear_coat_type"] == "2k"


def test_clearcoat_spray_can_pricing():
    """50 sqft x $0.35/coat x 2 coats = $35.00 for spray can."""
    from backend.finishing import FinishingBuilder
    fb = FinishingBuilder()
    result = fb.build(
        finish_type="clearcoat",
        total_sq_ft=50.0,
        labor_processes=[],
        clear_coat_type="Spray can (basic — 2 coats)",
    )
    assert result["materials_cost"] == 35.00, \
        "Spray clearcoat: 50 sqft x $0.35 x 2 = $35, got $%.2f" % result["materials_cost"]
    assert result["coat_count"] == 2
    assert result["clear_coat_type"] == "spray"


def test_clearcoat_default_is_2k():
    """Empty clear_coat_type should default to 2K urethane."""
    from backend.finishing import FinishingBuilder
    fb = FinishingBuilder()
    result = fb.build(
        finish_type="clearcoat",
        total_sq_ft=50.0,
        labor_processes=[],
        clear_coat_type="",
    )
    assert result["clear_coat_type"] == "2k", \
        "Default should be '2k', got '%s'" % result["clear_coat_type"]
    assert result["coat_count"] == 3, \
        "Default 2K should be 3 coats, got %d" % result["coat_count"]
    assert result["materials_cost"] == 225.00, \
        "Default 2K: 50 x $1.50 x 3 = $225, got $%.2f" % result["materials_cost"]


# ---- Fix 8: Laser Cutting Pricing ----

def test_laser_rate_realistic():
    """1000" perimeter should cost > $350 at the new $0.35/inch rate."""
    from backend.calculators.custom_fab import CustomFabCalculator
    calc = CustomFabCalculator()
    # Simulate _build_from_ai_cuts with sheet items
    ai_cuts = [
        {"profile": "al_sheet_0.125", "length_inches": 48, "width_inches": 24,
         "quantity": 4, "piece_name": "panel"},
    ]
    fields = {"description": "aluminum sign", "material_type": "Aluminum"}
    result = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])
    # Find laser hardware item
    hw = result.get("hardware", [])
    laser_items = [h for h in hw if "laser" in h["description"].lower()]
    assert len(laser_items) == 1, "Should have exactly one laser cutting hardware item"
    # 4 panels: perimeter = 2*(48+24)*4 = 576". Cost = 4*75 + 576*0.35 = 501.60
    laser_cost = laser_items[0]["options"][0]["price"]
    assert laser_cost > 350, \
        "Laser cost should be > $350 for 576\" perimeter, got $%.2f" % laser_cost


def test_laser_setup_fee_per_sheet():
    """3 small pieces fitting on 1 sheet should use 1-sheet setup, not 3-piece setup."""
    from backend.calculators.custom_fab import CustomFabCalculator
    calc = CustomFabCalculator()
    ai_cuts = [
        {"profile": "al_sheet_0.125", "length_inches": 24, "width_inches": 12,
         "quantity": 3, "piece_name": "small panel",
         "sheet_stock_size": [60, 120]},
    ]
    fields = {"description": "aluminum box", "material_type": "Aluminum"}
    result = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])
    hw = result.get("hardware", [])
    laser_items = [h for h in hw if "laser" in h["description"].lower()]
    assert len(laser_items) == 1
    # 3 pieces of 24x12 = 864 sq in total, 1 sheet (5x10') = 5400 usable → 1 sheet
    # Setup = 1*75 = 75, perimeter = 2*(24+12)*3 = 216", cut = 216*0.35 = 75.60
    # Total = 75 + 75.60 = 150.60
    laser_cost = laser_items[0]["options"][0]["price"]
    assert laser_cost < 200, \
        "1-sheet laser should be < $200 (not per-piece), got $%.2f" % laser_cost
    assert "sheet" in laser_items[0]["description"].lower(), \
        "Description should mention sheets"


def test_opus_exclusions_passthrough():
    """ALL Opus exclusions pass through unmodified — no filtering."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    session_data = {
        "session_id": "test-excl-passthrough",
        "job_type": "led_sign_custom",
        "fields": {"description": "aluminum sign", "finish": "raw"},
        "material_list": {
            "items": [],
            "hardware": [
                {"description": "Laser cutting service — 500\" perimeter, 2 pieces",
                 "quantity": 1,
                 "options": [{"supplier": "Local", "price": 250.0,
                              "url": "", "part_number": None, "lead_days": None}]},
            ],
            "total_weight_lbs": 10.0,
            "total_sq_ft": 5.0,
            "weld_linear_inches": 0,
            "assumptions": [],
            "_opus_exclusions": [
                "Laser cutting / CNC routing for letter faces — typically $500-$1,500",
                "Electrical wiring for LED modules",
            ],
        },
        "labor_estimate": {"processes": [], "total_hours": 0},
        "finishing": {"method": "raw", "area_sq_ft": 5, "hours": 0,
                      "materials_cost": 0, "outsource_cost": 0, "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 0,
            "rate_inshop": 125, "rate_onsite": 145}
    pq = pe.build_priced_quote(session_data, user)
    excl = pq.get("exclusions", [])
    # ALL Opus exclusions should pass through — including laser
    laser_excl = [e for e in excl if "laser cut" in e.lower()]
    assert len(laser_excl) > 0, \
        "Laser exclusion should pass through (no filtering), got: %s" % excl
    led_excl = [e for e in excl if "LED" in e or "Electrical" in e]
    assert len(led_excl) > 0, "Non-laser exclusions should also pass through"


def test_laser_exclusion_kept_when_no_hardware():
    """Opus laser exclusion should be kept when no laser hardware is present."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    session_data = {
        "session_id": "test-laser-kept",
        "job_type": "led_sign_custom",
        "fields": {"description": "steel sign", "finish": "raw"},
        "material_list": {
            "items": [],
            "hardware": [],  # No laser hardware
            "total_weight_lbs": 10.0,
            "total_sq_ft": 5.0,
            "weld_linear_inches": 0,
            "assumptions": [],
            "_opus_exclusions": [
                "Laser cutting / CNC routing — typically $500-$1,500",
            ],
        },
        "labor_estimate": {"processes": [], "total_hours": 0},
        "finishing": {"method": "raw", "area_sq_ft": 5, "hours": 0,
                      "materials_cost": 0, "outsource_cost": 0, "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 0,
            "rate_inshop": 125, "rate_onsite": 145}
    pq = pe.build_priced_quote(session_data, user)
    excl = pq.get("exclusions", [])
    laser_excl = [e for e in excl if "laser" in e.lower()]
    assert len(laser_excl) > 0, \
        "Laser exclusion should be kept when no laser hardware present"


# ---- Fix A: Sheet Counting (Area-Based) ----

def test_sheet_count_area_based():
    """3 pieces that fit on one 5x10' sheet should give sheets_needed=1, not 3."""
    from backend.calculators.custom_fab import CustomFabCalculator
    calc = CustomFabCalculator()
    # 3 pieces: 24x24 each = 576 sq in each = 1728 total
    # One 5x10' sheet = 60x120 = 7200 sq in, 75% usable = 5400
    # 1728 / 5400 = 0.32 → 1 sheet
    ai_cuts = [
        {"profile": "al_sheet_0.125", "length_inches": 24, "width_inches": 24,
         "quantity": 1, "piece_name": "panel_a",
         "sheet_stock_size": [60, 120], "sheets_needed": 1},
        {"profile": "al_sheet_0.125", "length_inches": 24, "width_inches": 24,
         "quantity": 1, "piece_name": "panel_b",
         "sheet_stock_size": [60, 120], "sheets_needed": 1},
        {"profile": "al_sheet_0.125", "length_inches": 24, "width_inches": 24,
         "quantity": 1, "piece_name": "panel_c",
         "sheet_stock_size": [60, 120], "sheets_needed": 1},
    ]
    fields = {"description": "aluminum sign", "material_type": "Aluminum"}
    result = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])
    # Find the sheet material item
    sheet_items = [m for m in result["items"]
                   if "sheet" in m.get("profile", "").lower()]
    assert len(sheet_items) == 1
    # Should be 1 sheet, not 3 (old bug: summed per-piece)
    assert sheet_items[0].get("sheets_needed", 0) == 1, \
        "3 small pieces on one 5x10' sheet should be 1 sheet, got %d" \
        % sheet_items[0].get("sheets_needed", 0)


def test_sheet_count_exceeds_one_sheet():
    """Pieces exceeding one sheet's area should give sheets_needed=2+."""
    from backend.calculators.custom_fab import CustomFabCalculator
    calc = CustomFabCalculator()
    # 2 pieces: 60x60 each = 3600 sq in each = 7200 total
    # One 5x10' sheet = 7200 sq in, 75% usable = 5400
    # 7200 / 5400 = 1.33 → 2 sheets
    ai_cuts = [
        {"profile": "al_sheet_0.125", "length_inches": 60, "width_inches": 60,
         "quantity": 1, "piece_name": "disc_front",
         "sheet_stock_size": [60, 120], "sheets_needed": 1},
        {"profile": "al_sheet_0.125", "length_inches": 60, "width_inches": 60,
         "quantity": 1, "piece_name": "disc_back",
         "sheet_stock_size": [60, 120], "sheets_needed": 1},
    ]
    fields = {"description": "aluminum sign", "material_type": "Aluminum"}
    result = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])
    sheet_items = [m for m in result["items"]
                   if "sheet" in m.get("profile", "").lower()]
    assert len(sheet_items) == 1
    assert sheet_items[0].get("sheets_needed", 0) == 2, \
        "Two 60x60 circles on 5x10' sheets should need 2, got %d" \
        % sheet_items[0].get("sheets_needed", 0)


# ---- Fix B: Opus Scope Constraint ----

def test_opus_scope_constraint_in_prompt():
    """Full package prompt must contain SCOPE BOUNDARY rule."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    gen = AICutListGenerator.__new__(AICutListGenerator)
    fields = {"description": "aluminum sign 5ft circle"}
    prompt = gen._build_full_package_prompt("sign_frame", fields)
    assert "SCOPE BOUNDARY" in prompt, \
        "Full package prompt should contain SCOPE BOUNDARY constraint"
    assert "exclusions" in prompt.lower(), \
        "Scope constraint should mention putting extra items in exclusions"


# ---- Fix C: Laser Setup Per-Sheet ----

def test_laser_setup_per_sheet_not_per_piece():
    """5 pieces on 2 sheets should use 2×$75 setup, not 5×$75."""
    from backend.calculators.custom_fab import CustomFabCalculator
    calc = CustomFabCalculator()
    # 5 pieces: 30x30 each = 900 sq in each = 4500 total
    # One 5x10' sheet = 7200, 75% usable = 5400
    # 4500 / 5400 = 0.83 → 1 sheet
    ai_cuts = [
        {"profile": "al_sheet_0.125", "length_inches": 30, "width_inches": 30,
         "quantity": 5, "piece_name": "panel",
         "sheet_stock_size": [60, 120], "sheets_needed": 1},
    ]
    fields = {"description": "aluminum sign laser cut", "material_type": "Aluminum"}
    result = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])
    hw = result.get("hardware", [])
    laser_items = [h for h in hw if "laser" in h["description"].lower()]
    assert len(laser_items) == 1
    desc = laser_items[0]["description"]
    # Should say "1 sheets" (area-based), not "5 pieces"
    assert "sheets" in desc, "Laser description should mention sheets, not pieces"
    # Setup = 1 sheet × $75 = $75, not 5 × $75 = $375
    laser_cost = laser_items[0]["options"][0]["price"]
    # 5 pieces of 30x30: perimeter = 2*(30+30)*5 = 600". Cost = 75 + 600*0.35 = 285
    assert laser_cost < 400, \
        "1-sheet laser setup should be < $400, got $%.2f" % laser_cost


# ---- P43c: Full Package Passthrough (Override Removal) ----

def test_full_package_no_waste_factor():
    """Full package path: tube footage should NOT be inflated by waste factor."""
    from backend.calculators.custom_fab import CustomFabCalculator
    calc = CustomFabCalculator()
    ai_cuts = [
        {"profile": "sq_tube_2x2_11ga", "length_inches": 30, "quantity": 4,
         "piece_name": "legs", "material_type": "mild_steel"},
    ]
    fields = {"description": "table base"}

    # Legacy path (trust_opus=False) — should add waste
    legacy = calc._build_from_ai_cuts("furniture_table", ai_cuts, fields, [])
    # Full package path (trust_opus=True) — no waste
    trusted = calc._build_from_ai_cuts("furniture_table", ai_cuts, fields, [],
                                        trust_opus=True)

    legacy_ft = sum(m["length_inches"] for m in legacy["items"]) / 12.0
    trusted_ft = sum(m["length_inches"] for m in trusted["items"]) / 12.0

    assert trusted_ft < legacy_ft, \
        "trust_opus path should NOT add waste (%.1f should be < %.1f)" % (
            trusted_ft, legacy_ft)
    # Trusted should be exact: 4 × 30in = 120in = 10ft
    assert abs(trusted_ft - 10.0) < 0.1, \
        "trust_opus footage should be 10.0 ft (no waste), got %.1f" % trusted_ft


def test_full_package_no_laser_injection():
    """Full package path: no auto-laser hardware for aluminum description."""
    from backend.calculators.custom_fab import CustomFabCalculator
    calc = CustomFabCalculator()
    ai_cuts = [
        {"profile": "al_sheet_0.125", "length_inches": 48, "width_inches": 24,
         "quantity": 2, "piece_name": "panel"},
    ]
    fields = {"description": "aluminum sign", "material_type": "Aluminum"}

    # Legacy path — should inject laser
    legacy = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])
    legacy_laser = [h for h in legacy.get("hardware", [])
                    if "laser" in h["description"].lower()]

    # Full package path — should NOT inject laser
    trusted = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [],
                                        trust_opus=True)
    trusted_laser = [h for h in trusted.get("hardware", [])
                     if "laser" in h["description"].lower()]

    assert len(legacy_laser) == 1, "Legacy should inject laser hardware"
    assert len(trusted_laser) == 0, \
        "trust_opus should NOT inject laser hardware — Opus provides it if needed"


def test_full_package_hardware_single_option():
    """Full package hardware should have 1 option (no 'Premium' tier)."""
    from backend.calculators.custom_fab import CustomFabCalculator
    calc = CustomFabCalculator()
    package = {
        "cut_list": [
            {"profile": "sq_tube_2x2_11ga", "length_inches": 30,
             "quantity": 4, "piece_name": "legs"},
        ],
        "hardware": [
            {"description": "Heavy duty weld-on hinges", "quantity": 2,
             "estimated_price": 45.00},
        ],
        "consumables": [],
        "labor_hours": {"cut_prep": 1.0},
        "build_instructions": [{"step": 1, "description": "Cut legs"}],
        "finishing_method": "raw",
        "assumptions": [],
        "exclusions": [],
    }
    result = calc._build_from_full_package("furniture_table", package,
                                            {"description": "table"})
    opus_hw = result.get("_opus_hardware", [])
    assert len(opus_hw) == 1, "Should have 1 hardware item"
    assert len(opus_hw[0]["options"]) == 1, \
        "Hardware should have 1 option (no Premium tier), got %d" % len(opus_hw[0]["options"])
    assert opus_hw[0]["options"][0]["supplier"] == "Estimated"


def test_full_package_consumables_passthrough():
    """Opus consumable prices should pass through unchanged — no override."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    opus_consumables = [
        {"description": "Welding wire ER70S-6", "quantity": 1,
         "unit_price": 32.50, "line_total": 32.50},
        {"description": "Grinding discs", "quantity": 3,
         "unit_price": 0, "line_total": 0},  # $0 price — should stay $0
    ]
    session_data = {
        "session_id": "test-cons-pass",
        "job_type": "custom_fab",
        "fields": {"description": "metal work", "finish": "raw"},
        "material_list": {
            "items": [],
            "hardware": [],
            "total_weight_lbs": 10.0,
            "total_sq_ft": 5.0,
            "weld_linear_inches": 0,
            "assumptions": [],
            "_opus_hardware": [],
            "_opus_consumables": opus_consumables,
            "_opus_labor_hours": {"cut_prep": 1.0},
            "_opus_finishing_method": "raw",
            "_opus_exclusions": [],
        },
        "labor_estimate": {
            "processes": [{"process": "cut_prep", "hours": 1.0, "rate": 125, "notes": ""}],
            "total_hours": 1.0,
        },
        "finishing": {"method": "raw", "area_sq_ft": 5, "hours": 0,
                      "materials_cost": 0, "outsource_cost": 0, "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 0,
            "rate_inshop": 125, "rate_onsite": 145}
    pq = pe.build_priced_quote(session_data, user)
    # Consumables with shop stock keywords get tiered into shop_stock
    all_items = pq.get("consumables", []) + pq.get("shop_stock", [])
    # Wire should keep its $32.50 price
    wire = [c for c in all_items if "wire" in c.get("description", "").lower()]
    assert len(wire) == 1
    assert wire[0]["unit_price"] == 32.50, \
        "Wire price should be Opus's $32.50, got $%.2f" % wire[0]["unit_price"]
    # Grinding discs with $0 should stay $0 (no override to $5 or $12)
    discs = [c for c in all_items if "disc" in c.get("description", "").lower()]
    assert len(discs) == 1
    assert discs[0]["unit_price"] == 0, \
        "Opus $0 price should pass through unchanged, got $%.2f" % discs[0]["unit_price"]


def test_full_package_surface_area_from_cuts():
    """trust_opus path should calculate surface area from cut dimensions, not hardcode."""
    from backend.calculators.custom_fab import CustomFabCalculator
    calc = CustomFabCalculator()
    # Sheet pieces: 48×24 × 2 = 2304 sq in = 16.0 sq ft
    ai_cuts = [
        {"profile": "al_sheet_0.125", "length_inches": 48, "width_inches": 24,
         "quantity": 2, "piece_name": "panel"},
    ]
    fields = {"description": "sign panels"}

    trusted = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [],
                                        trust_opus=True)
    sq_ft = trusted.get("total_sq_ft", 0)
    # 2 panels of 48×24 = 2304 sq in / 144 = 16.0 sq ft
    assert abs(sq_ft - 16.0) < 1.0, \
        "Surface area should be ~16.0 sqft from cut dims, got %.1f" % sq_ft


def test_no_banned_term_stripping():
    """Build instructions should not strip or annotate banned terms."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    import inspect
    source = inspect.getsource(AICutListGenerator.generate_build_instructions)
    assert "_strip_banned_terms" not in source, \
        "generate_build_instructions should not call _strip_banned_terms_from_steps"
    assert "check_banned_terms" not in source, \
        "generate_build_instructions should not call check_banned_terms"
