"""
Prompt 44 — "No Orphans, No Assumptions"

Tests for:
AC-1: BOM validator (orphaned hardware detection)
AC-2: Dedup + tiered BOM (shop stock separation)
AC-3: Preference questions expansion (sign-specific)
AC-4: Shop Stock section in PDF + subtotal
AC-5: Sheet/plate weight calculation
"""

import os
import inspect

import pytest


# ── AC-1: BOM Validator ──


def test_bom_validator_keeps_matching_hardware():
    """Hardware item whose description matches a build step title is kept."""
    from backend.bom_validator import validate_bom_against_build

    hardware = [
        {"description": "Heavy duty weld-on hinge pair", "quantity": 2},
    ]
    build_instructions = [
        {"step": 1, "title": "Install hinges", "description": "Weld hinge plates to frame"},
    ]
    result = validate_bom_against_build(hardware, build_instructions)
    assert len(result["kept"]) == 1
    assert len(result["orphaned"]) == 0


def test_bom_validator_orphans_unmatched():
    """Hardware item with no matching build step is flagged as orphaned."""
    from backend.bom_validator import validate_bom_against_build

    hardware = [
        {"description": "Decorative rosette accent", "quantity": 4},
    ]
    build_instructions = [
        {"step": 1, "title": "Weld frame", "description": "Assemble main frame tubes"},
        {"step": 2, "title": "Install posts", "description": "Set posts in concrete"},
    ]
    result = validate_bom_against_build(hardware, build_instructions)
    assert len(result["orphaned"]) == 1
    assert len(result["kept"]) == 0
    assert "rosette" in result["orphan_reasons"][0].lower() or \
           "no matching" in result["orphan_reasons"][0].lower()


def test_bom_validator_consumables_always_pass():
    """Shop consumables (wire, discs, gas) are never orphaned."""
    from backend.bom_validator import validate_bom_against_build

    hardware = [
        {"description": "ER70S-6 welding wire (2 lbs)", "quantity": 1},
        {"description": "4.5\" grinding disc x3", "quantity": 3},
        {"description": "75/25 shielding gas (20 cu ft)", "quantity": 1},
    ]
    build_instructions = [
        {"step": 1, "title": "Weld frame", "description": "MIG weld all joints"},
    ]
    result = validate_bom_against_build(hardware, build_instructions)
    assert len(result["kept"]) == 3
    assert len(result["orphaned"]) == 0


def test_bom_validator_electronics_pass_with_wiring_step():
    """Electronics items pass when build instructions mention wiring/electronics."""
    from backend.bom_validator import validate_bom_against_build

    hardware = [
        {"description": "ESP32 Dev Board", "quantity": 1},
        {"description": "LED Strip 5m RGBW", "quantity": 2},
    ]
    build_instructions = [
        {"step": 1, "title": "Fabricate frame", "description": "Weld sign frame"},
        {"step": 2, "title": "Install electronics", "description": "Mount LED strips and controller"},
    ]
    result = validate_bom_against_build(hardware, build_instructions)
    assert len(result["kept"]) == 2
    assert len(result["orphaned"]) == 0


def test_bom_validator_no_build_instructions_keeps_all():
    """With no build instructions, all hardware is kept (can't validate)."""
    from backend.bom_validator import validate_bom_against_build

    hardware = [
        {"description": "Random item", "quantity": 1},
    ]
    result = validate_bom_against_build(hardware, [])
    assert len(result["kept"]) == 1
    assert len(result["orphaned"]) == 0


# ── AC-2: Dedup + Tiering ──


def test_dedup_hardware_merges_duplicates():
    """Two items with same normalized description are merged, quantities summed."""
    from backend.pricing_engine import PricingEngine

    pe = PricingEngine()
    items = [
        {"description": "ESP32 Dev Board (Est.)", "quantity": 1, "options": [
            {"supplier": "Amazon", "price": 12.00},
        ]},
        {"description": "ESP32 Dev Board (Est.)", "quantity": 1, "options": [
            {"supplier": "Amazon", "price": 12.00},
            {"supplier": "Specialty", "price": 14.40},
        ]},
    ]
    result = pe._dedup_hardware(items)
    assert len(result) == 1
    assert result[0]["quantity"] == 2
    # Should keep the version with more options
    assert len(result[0]["options"]) == 2


def test_tier_consumables_to_shop_stock():
    """Welding consumables move from consumables to shop_stock."""
    from backend.pricing_engine import PricingEngine

    pe = PricingEngine()
    hardware = [
        {"description": "Heavy duty hinge pair", "quantity": 2, "options": [
            {"supplier": "McMaster", "price": 145.00},
        ]},
    ]
    consumables = [
        {"description": "ER70S-6 welding wire (1 lbs)", "quantity": 1,
         "unit_price": 3.50, "line_total": 3.50, "category": "consumable"},
        {"description": "4.5\" grinding disc x1", "quantity": 1,
         "unit_price": 4.50, "line_total": 4.50, "category": "consumable"},
    ]
    result = pe._tier_items(hardware, consumables)
    # Hardware (hinge) stays in hardware
    assert len(result["hardware"]) == 1
    assert "hinge" in result["hardware"][0]["description"].lower()
    # Consumables move to shop_stock
    assert len(result["shop_stock"]) == 2
    assert all(s.get("allocation_pct") == 100 for s in result["shop_stock"])
    # No consumables remaining
    assert len(result["consumables"]) == 0


def test_tier_hardware_stays_tier1():
    """Project-specific hardware (gate operator) stays in hardware list."""
    from backend.pricing_engine import PricingEngine

    pe = PricingEngine()
    hardware = [
        {"description": "LiftMaster LA412 gate operator", "quantity": 1, "options": [
            {"supplier": "Gate Depot", "price": 1249.00},
        ]},
    ]
    consumables = []
    result = pe._tier_items(hardware, consumables)
    assert len(result["hardware"]) == 1
    assert "LiftMaster" in result["hardware"][0]["description"]
    assert len(result["shop_stock"]) == 0


# ── AC-3: Preference Questions Expansion ──


def test_preference_prompt_expanded():
    """Prompt includes HIGH-IMPACT PREFERENCES and SIGN-SPECIFIC PREFERENCES."""
    from backend.question_trees.engine import QuestionTreeEngine

    engine = QuestionTreeEngine()
    # Read the source code of suggest_additional_questions to check prompt content
    source = inspect.getsource(engine.suggest_additional_questions)
    assert "HIGH-IMPACT PREFERENCES" in source, \
        "Prompt should include HIGH-IMPACT PREFERENCES section"
    assert "SIGN-SPECIFIC PREFERENCES" in source, \
        "Prompt should include SIGN-SPECIFIC PREFERENCES section"
    assert "Weld finish quality" in source, \
        "Prompt should mention weld finish quality preference"
    assert "LED pixel density" in source, \
        "Prompt should mention LED pixel density for sign jobs"


# ── AC-4: Shop Stock in PDF + Subtotal ──


def test_shop_stock_subtotal_in_priced_quote():
    """PricingEngine produces shop_stock and shop_stock_subtotal fields."""
    from backend.pricing_engine import PricingEngine

    pe = PricingEngine()
    session_data = {
        "job_type": "swing_gate",
        "fields": {"description": "6ft wide swing gate", "finish": "raw"},
        "material_list": {
            "items": [
                {"description": "2\" sq tube frame", "material_type": "mild_steel",
                 "profile": "sq_tube_2x2_11ga", "length_inches": 72,
                 "quantity": 2, "unit_price": 3.50, "line_total": 42.00,
                 "cut_type": "square", "waste_factor": 0.05},
            ],
            "hardware": [
                {"description": "Heavy duty weld-on hinge pair", "quantity": 1,
                 "options": [{"supplier": "McMaster", "price": 145.00}]},
            ],
            "weld_linear_inches": 100,
            "total_sq_ft": 10,
            "total_weight_lbs": 50,
            "assumptions": [],
        },
        "labor_estimate": {
            "processes": [
                {"process": "fit_tack", "hours": 1.0, "rate": 75.0, "notes": ""},
                {"process": "full_weld", "hours": 1.5, "rate": 75.0, "notes": ""},
            ],
            "total_hours": 2.5,
            "flagged": False,
        },
        "finishing": {"method": "raw", "area_sq_ft": 10, "hours": 0,
                      "materials_cost": 0, "outsource_cost": 0, "total": 0},
    }
    user = {"id": 1, "shop_name": "Test Shop", "markup_default": 0}

    result = pe.build_priced_quote(session_data, user)
    # shop_stock field exists
    assert "shop_stock" in result
    assert "shop_stock_subtotal" in result
    # All consumables should have moved to shop_stock
    assert isinstance(result["shop_stock"], list)
    assert isinstance(result["shop_stock_subtotal"], float)


def test_shop_stock_section_in_pdf():
    """PDF generator renders Shop Stock section when shop_stock is present."""
    from backend.pdf_generator import generate_quote_pdf

    priced_quote = {
        "quote_id": 999,
        "job_type": "swing_gate",
        "client_name": "Test Client",
        "job_description": "Test gate",
        "materials": [],
        "hardware": [],
        "consumables": [],
        "shop_stock": [
            {"description": "ER70S-6 welding wire (1 lbs)", "quantity": 1,
             "unit_price": 3.50, "line_total": 3.50, "allocation_pct": 100,
             "category": "consumable"},
        ],
        "labor": [],
        "finishing": {"method": "raw", "area_sq_ft": 0, "hours": 0,
                      "materials_cost": 0, "outsource_cost": 0, "total": 0},
        "material_subtotal": 0,
        "hardware_subtotal": 0,
        "consumable_subtotal": 0,
        "shop_stock_subtotal": 3.50,
        "labor_subtotal": 0,
        "finishing_subtotal": 0,
        "subtotal": 3.50,
        "markup_options": {"0": 3.50},
        "selected_markup_pct": 0,
        "total": 3.50,
        "created_at": "2026-03-10T00:00:00",
        "assumptions": [],
        "exclusions": [],
    }
    user_profile = {"shop_name": "Test Shop"}
    pdf_bytes = generate_quote_pdf(priced_quote, user_profile)
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert len(pdf_bytes) > 500


# ── AC-5: Sheet/Plate Weight ──


def test_sheet_weight_calculated():
    """sheet_11ga item gets weight_lbs > 0 from knowledge/materials.py."""
    from backend.pricing_engine import PricingEngine

    pe = PricingEngine()
    materials = [
        {"description": "11ga sheet panel", "material_type": "mild_steel",
         "profile": "sheet_11ga", "length_inches": 96, "quantity": 1,
         "unit_price": 50.00, "line_total": 50.00, "cut_type": "square",
         "waste_factor": 0.05},
    ]
    summary = pe._aggregate_materials(materials)
    assert len(summary) == 1
    assert summary[0]["weight_lbs"] > 0, \
        "Sheet weight should be > 0, got %s" % summary[0]["weight_lbs"]
    # sheet_11ga = 5.0 lb/sqft, total_ft = 96/12 = 8, weight = 5.0 * 8 = 40
    assert summary[0]["weight_lbs"] == 40.0, \
        "Expected 40.0 lbs, got %s" % summary[0]["weight_lbs"]


def test_al_sheet_weight_uses_density_ratio():
    """Aluminum sheet weight uses steel weight * 0.344 density ratio."""
    from backend.pricing_engine import PricingEngine

    pe = PricingEngine()
    materials = [
        {"description": "14ga aluminum sheet", "material_type": "aluminum_6061",
         "profile": "al_sheet_14ga", "length_inches": 48, "quantity": 1,
         "unit_price": 40.00, "line_total": 40.00, "cut_type": "square",
         "waste_factor": 0.05},
    ]
    summary = pe._aggregate_materials(materials)
    assert len(summary) == 1
    weight = summary[0]["weight_lbs"]
    assert weight > 0, "Al sheet weight should be > 0"
    # sheet_14ga steel = 3.125 lb/sqft * 0.344 = 1.075 lb/sqft
    # total_ft = 48/12 = 4, weight = 1.075 * 4 = 4.3
    assert weight < 5.0, \
        "Al sheet should weigh less than steel equivalent, got %s" % weight


def test_plate_weight_calculated():
    """1/4 inch plate gets weight from knowledge/materials.py."""
    from backend.pricing_engine import PricingEngine

    pe = PricingEngine()
    materials = [
        {"description": "1/4 plate base", "material_type": "mild_steel",
         "profile": "plate_0.25", "length_inches": 24, "quantity": 2,
         "unit_price": 25.00, "line_total": 50.00, "cut_type": "square",
         "waste_factor": 0.05},
    ]
    summary = pe._aggregate_materials(materials)
    assert len(summary) == 1
    weight = summary[0]["weight_lbs"]
    assert weight > 0, "Plate weight should be > 0"
    # plate_0.25 = 10.2 lb/sqft, total_ft = (24*2)/12 = 4, weight = 10.2 * 4 = 40.8
    assert weight == 40.8, "Expected 40.8 lbs, got %s" % weight
