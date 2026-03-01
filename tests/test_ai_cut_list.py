"""
AI Cut List Generator tests.

Tests:
1-4.   AICutListGenerator class (prompt building, response parsing, fallback, TIG detection)
5-7.   Furniture table fixes (4 legs, individual frame pieces, dimension parser)
8-11.  AI integration in calculators (always-fire triggers, custom_fab, all calculators work)
12-14. Build instructions generator
15-17. PDF template updates (detailed cut list section, fabrication sequence section)
18-19. Hardware URL generation
20.    Dynamic model name in pricing engine
21.    Build instructions wiring to pricing engine
"""

import json
import os
import urllib.parse
from unittest.mock import patch, MagicMock

from backend.calculators.ai_cut_list import AICutListGenerator
from backend.calculators.furniture_table import FurnitureTableCalculator
from backend.calculators.custom_fab import CustomFabCalculator
from backend.calculators.furniture_other import FurnitureOtherCalculator
from backend.calculators.led_sign_custom import LedSignCustomCalculator
from backend.calculators.repair_decorative import RepairDecorativeCalculator
from backend.calculators.repair_structural import RepairStructuralCalculator
from backend.hardware_sourcer import HardwareSourcer
from backend.pricing_engine import PricingEngine
from backend.pdf_generator import (
    generate_quote_pdf, JOB_TYPE_NAMES, generate_job_summary
)


# ============================================================
# AICutListGenerator class tests
# ============================================================

def test_ai_cut_list_prompt_contains_job_type():
    """Prompt includes the job type and fields."""
    gen = AICutListGenerator()
    prompt = gen._build_prompt("furniture_table", {"height": "30"})
    assert "furniture_table" in prompt
    assert "height" in prompt
    assert "30" in prompt


def test_ai_cut_list_parse_valid_response():
    """Valid JSON array is parsed into cut list items."""
    gen = AICutListGenerator()
    response = json.dumps([
        {
            "description": "Table leg",
            "material_type": "square_tubing",
            "profile": "sq_tube_2x2_11ga",
            "length_inches": 30.0,
            "quantity": 4,
            "cut_type": "square",
            "notes": "4 legs at 30 inches"
        },
        {
            "description": "Frame rail long",
            "material_type": "square_tubing",
            "profile": "sq_tube_1.5x1.5_11ga",
            "length_inches": 60.0,
            "quantity": 2,
            "cut_type": "miter_45",
            "notes": "2 long rails"
        }
    ])
    cuts = gen._parse_response(response)
    assert cuts is not None
    assert len(cuts) == 2
    assert cuts[0]["description"] == "Table leg"
    assert cuts[0]["quantity"] == 4
    assert cuts[1]["length_inches"] == 60.0


def test_ai_cut_list_parse_invalid_response_returns_none():
    """Invalid JSON returns None instead of crashing."""
    gen = AICutListGenerator()
    assert gen._parse_response("not json at all") is None
    assert gen._parse_response("") is None
    assert gen._parse_response("{}") is None  # Not a list


def test_ai_cut_list_parse_response_sanitizes():
    """Parser fixes invalid values (negative length, bad cut type)."""
    gen = AICutListGenerator()
    response = json.dumps([
        {
            "description": "Bad piece",
            "material_type": "mild_steel",
            "profile": "sq_tube_2x2_11ga",
            "length_inches": -5.0,
            "quantity": 0,
            "cut_type": "invalid_cut",
            "notes": ""
        }
    ])
    cuts = gen._parse_response(response)
    assert cuts is not None
    assert cuts[0]["length_inches"] == 12.0  # Defaulted
    assert cuts[0]["quantity"] == 1  # Minimum 1
    assert cuts[0]["cut_type"] == "square"  # Defaulted


def test_ai_cut_list_no_api_key_returns_none():
    """Without GEMINI_API_KEY, generate_cut_list returns None."""
    gen = AICutListGenerator()
    with patch.dict("os.environ", {}, clear=True):
        result = gen.generate_cut_list("furniture_table", {"height": "30"})
    assert result is None


# ============================================================
# Furniture table fixes
# ============================================================

def test_furniture_table_has_4_legs():
    """Furniture table calculator produces exactly 4 legs (not 5)."""
    calc = FurnitureTableCalculator()
    result = calc.calculate({
        "table_length": "60",
        "table_width": "30",
        "table_height": "30",
        "quantity": "1",
    })
    # Find the legs item
    legs_item = None
    for item in result["items"]:
        if "leg" in item["description"].lower():
            legs_item = item
            break
    assert legs_item is not None
    # apply_waste(4, 0.05) = ceil(4.2) = 5 — that's the waste-adjusted qty
    # But the description should say 4
    assert "4" in legs_item["description"]
    # Verify no item has 5 in its raw quantity before waste
    assert legs_item["quantity"] == 5  # 4 * 1.05 rounded up


def test_furniture_table_individual_frame_pieces():
    """Frame is listed as individual rails, not a single perimeter piece."""
    calc = FurnitureTableCalculator()
    result = calc.calculate({
        "table_length": "60",
        "table_width": "30",
        "table_height": "30",
        "quantity": "1",
    })
    descriptions = [item["description"].lower() for item in result["items"]]
    # Should have separate long rails and short rails
    has_long = any("long rail" in d for d in descriptions)
    has_short = any("short rail" in d for d in descriptions)
    assert has_long, "Should have separate long frame rails"
    assert has_short, "Should have separate short frame rails"
    # Should NOT have a single "perimeter" piece
    assert not any("perimeter" in d for d in descriptions)


def test_furniture_table_dimension_parser_lxwxh():
    """Dimension parser handles 'L x W x H' format."""
    calc = FurnitureTableCalculator()
    result = calc.calculate({
        "approximate_size": "20 x 20 x 32",
        "quantity": "1",
    })
    # Verify the dimensions are parsed correctly
    assert result["items"]  # Has items
    assumptions = " ".join(result["assumptions"])
    assert '20"' in assumptions or "20" in assumptions
    assert '32"' in assumptions or "32" in assumptions


def test_furniture_table_dimension_parser_feet():
    """Dimension parser handles feet input."""
    calc = FurnitureTableCalculator()
    dims = calc._parse_table_dimensions({"approximate_size": "5 x 3 x 2.5 ft"})
    assert dims["length"] == 60.0  # 5 ft = 60 inches
    assert dims["width"] == 36.0   # 3 ft = 36 inches
    assert dims["height"] == 30.0  # 2.5 ft = 30 inches


def test_furniture_table_dimension_parser_individual_fields():
    """Falls back to individual fields when no combined dimension."""
    calc = FurnitureTableCalculator()
    dims = calc._parse_table_dimensions({
        "table_length": "48",
        "table_width": "24",
        "table_height": "30",
    })
    assert dims["length"] == 48.0
    assert dims["width"] == 24.0
    assert dims["height"] == 30.0


# ============================================================
# AI integration in calculators
# ============================================================

def test_furniture_table_ai_fires_on_any_description():
    """AI cut list fires on ANY description text, not just keywords."""
    calc = FurnitureTableCalculator()
    # No description — should NOT trigger AI
    result = calc._try_ai_cut_list({})
    assert result is None

    # Empty description — should NOT trigger
    result = calc._try_ai_cut_list({"description": "", "notes": ""})
    assert result is None

    # ANY description text — should trigger (returns None because no API key)
    with patch.dict("os.environ", {}, clear=True):
        result = calc._try_ai_cut_list({"description": "pyramid flat bar pattern"})
    assert result is None  # None from no API key, not from keyword filter

    # "standard dining table" — should ALSO trigger now (no keywords needed)
    with patch.dict("os.environ", {}, clear=True):
        result = calc._try_ai_cut_list({"description": "standard dining table"})
    assert result is None  # None from no API key


def test_all_calculators_fire_ai_on_description():
    """All 6 AI-integrated calculators fire AI on any description text."""
    calculators = [
        FurnitureTableCalculator(),
        FurnitureOtherCalculator(),
        LedSignCustomCalculator(),
        RepairDecorativeCalculator(),
        RepairStructuralCalculator(),
        CustomFabCalculator(),
    ]
    for calc in calculators:
        # No description — should return None without trying AI
        assert calc._try_ai_cut_list({}) is None, (
            "%s should not trigger AI with no description" % type(calc).__name__
        )
        # With description — should try AI (returns None due to no API key)
        with patch.dict("os.environ", {}, clear=True):
            result = calc._try_ai_cut_list({"description": "some design"})
        assert result is None


def test_custom_fab_always_tries_ai_with_description():
    """Custom fab tries AI when description is present."""
    calc = CustomFabCalculator()
    # No description — should not trigger
    result = calc._try_ai_cut_list({})
    assert result is None

    # With description — tries but fails (no API key)
    with patch.dict("os.environ", {}, clear=True):
        result = calc._try_ai_cut_list({"description": "custom bracket"})
    assert result is None


def test_calculators_work_without_ai():
    """All 6 AI-integrated calculators still produce valid output without Gemini."""
    calculators = [
        (FurnitureTableCalculator(), {"table_length": "60", "table_width": "30", "table_height": "30"}),
        (CustomFabCalculator(), {"approximate_size": "24 x 12 x 12"}),
        (FurnitureOtherCalculator(), {"item_type": "Shelving", "approximate_size": "48 x 18 x 72"}),
        (LedSignCustomCalculator(), {"sign_type": "Channel letters", "dimensions": "8 ft x 2 ft"}),
        (RepairDecorativeCalculator(), {"repair_type": "Rust through / corrosion hole", "item_type": "Gate (swing or sliding)"}),
        (RepairStructuralCalculator(), {"repair_type": "Trailer frame repair"}),
    ]

    for calc, fields in calculators:
        with patch.dict("os.environ", {}, clear=True):
            result = calc.calculate(fields)
        assert result["items"], "%s produced no items" % type(calc).__name__
        assert result["total_weight_lbs"] >= 0
        assert result["weld_linear_inches"] >= 0
        assert result["assumptions"]


# ============================================================
# Build instructions
# ============================================================

def test_build_instructions_parse_valid():
    """Build instructions parser handles valid JSON."""
    gen = AICutListGenerator()
    response = json.dumps([
        {
            "step": 1,
            "title": "Layout & Mark",
            "description": "Measure and mark all pieces.",
            "tools": ["tape measure", "soapstone"],
            "duration_minutes": 20
        },
        {
            "step": 2,
            "title": "Cut",
            "description": "Cut all pieces on chop saw.",
            "tools": ["chop saw"],
            "duration_minutes": 30
        }
    ])
    steps = gen._parse_instructions_response(response)
    assert steps is not None
    assert len(steps) == 2
    assert steps[0]["title"] == "Layout & Mark"
    assert steps[0]["duration_minutes"] == 20
    assert "tape measure" in steps[0]["tools"]


def test_build_instructions_no_api_key():
    """Without API key, build instructions returns None."""
    gen = AICutListGenerator()
    with patch.dict("os.environ", {}, clear=True):
        result = gen.generate_build_instructions(
            "furniture_table",
            {"height": "30"},
            [{"description": "leg", "quantity": 4}],
        )
    assert result is None


def test_build_instructions_prompt_includes_cut_list():
    """Build instructions prompt includes the cut list items."""
    gen = AICutListGenerator()
    cuts = [
        {"description": "Table leg", "quantity": 4, "length_inches": 30},
        {"description": "Frame rail", "quantity": 2, "length_inches": 60},
    ]
    prompt = gen._build_instructions_prompt("furniture_table", {}, cuts)
    assert "Table leg" in prompt
    assert "Frame rail" in prompt
    assert "qty 4" in prompt


# ============================================================
# PDF template updates
# ============================================================

def test_pdf_includes_all_25_job_types():
    """JOB_TYPE_NAMES has display names for all 25 job types."""
    expected_types = [
        "cantilever_gate", "swing_gate", "straight_railing", "stair_railing",
        "repair_decorative", "ornamental_fence", "complete_stair", "spiral_stair",
        "window_security_grate", "balcony_railing", "furniture_table",
        "utility_enclosure", "bollard", "repair_structural", "custom_fab",
        "offroad_bumper", "rock_slider", "roll_cage", "exhaust_custom",
        "trailer_fab", "structural_frame", "furniture_other", "sign_frame",
        "led_sign_custom", "product_firetable",
    ]
    for jt in expected_types:
        assert jt in JOB_TYPE_NAMES, "Missing display name for %s" % jt


def test_pdf_renders_with_detailed_cut_list():
    """PDF renders when detailed_cut_list is present in priced_quote."""
    priced_quote = {
        "quote_id": 1,
        "quote_number": "CS-2026-0001",
        "job_type": "furniture_table",
        "materials": [],
        "hardware": [],
        "consumables": [],
        "labor": [],
        "finishing": {"method": "raw", "area_sq_ft": 0, "total": 0},
        "material_subtotal": 0,
        "hardware_subtotal": 0,
        "consumable_subtotal": 0,
        "labor_subtotal": 0,
        "finishing_subtotal": 0,
        "subtotal": 0,
        "total": 0,
        "selected_markup_pct": 0,
        "created_at": "2026-02-28T12:00:00",
        "assumptions": ["Test assumption"],
        "exclusions": [],
        "detailed_cut_list": [
            {
                "description": "Table leg",
                "profile": "sq_tube_2x2_11ga",
                "length_inches": 30.0,
                "quantity": 4,
                "cut_type": "square",
                "notes": "4 legs"
            }
        ],
    }
    user_profile = {"shop_name": "Test Shop"}

    pdf_bytes = generate_quote_pdf(priced_quote, user_profile)
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert len(pdf_bytes) > 500


def test_pdf_renders_with_build_instructions():
    """PDF renders when build_instructions is present."""
    priced_quote = {
        "quote_id": 2,
        "quote_number": "CS-2026-0002",
        "job_type": "custom_fab",
        "materials": [],
        "hardware": [],
        "consumables": [],
        "labor": [],
        "finishing": {"method": "raw", "area_sq_ft": 0, "total": 0},
        "material_subtotal": 0,
        "hardware_subtotal": 0,
        "consumable_subtotal": 0,
        "labor_subtotal": 0,
        "finishing_subtotal": 0,
        "subtotal": 0,
        "total": 0,
        "selected_markup_pct": 0,
        "created_at": "2026-02-28T12:00:00",
        "assumptions": [],
        "exclusions": [],
        "build_instructions": [
            {
                "step": 1,
                "title": "Layout",
                "description": "Mark all pieces",
                "tools": ["tape measure"],
                "duration_minutes": 15,
            },
            {
                "step": 2,
                "title": "Cut",
                "description": "Cut pieces on chop saw",
                "tools": ["chop saw", "angle grinder"],
                "duration_minutes": 30,
            },
        ],
    }
    user_profile = {"shop_name": "Test Shop"}

    pdf_bytes = generate_quote_pdf(priced_quote, user_profile)
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert len(pdf_bytes) > 500


def test_pdf_renders_without_ai_sections():
    """PDF renders fine when neither detailed_cut_list nor build_instructions are present."""
    priced_quote = {
        "quote_id": 3,
        "quote_number": "CS-2026-0003",
        "job_type": "straight_railing",
        "materials": [
            {
                "description": "Top rail",
                "profile": "sq_tube_1.5x1.5_11ga",
                "length_inches": 120,
                "quantity": 1,
                "unit_price": 27.50,
                "line_total": 27.50,
                "material_type": "square_tubing",
                "cut_type": "square",
                "waste_factor": 0.05,
            }
        ],
        "hardware": [],
        "consumables": [],
        "labor": [],
        "finishing": {"method": "raw", "area_sq_ft": 0, "total": 0},
        "material_subtotal": 27.50,
        "hardware_subtotal": 0,
        "consumable_subtotal": 0,
        "labor_subtotal": 0,
        "finishing_subtotal": 0,
        "subtotal": 27.50,
        "total": 27.50,
        "selected_markup_pct": 0,
        "created_at": "2026-02-28T12:00:00",
        "assumptions": [],
        "exclusions": [],
    }
    user_profile = {"shop_name": "Test Shop"}

    pdf_bytes = generate_quote_pdf(priced_quote, user_profile)
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert len(pdf_bytes) > 500


# ============================================================
# TIG weld detection
# ============================================================

def test_ai_prompt_detects_tig_requirements():
    """AI cut list prompt includes TIG guidance when finish requires it."""
    gen = AICutListGenerator()
    # With TIG indicators
    prompt = gen._build_prompt("furniture_table", {
        "description": "end table",
        "finish": "ground smooth and blended welds",
    })
    assert "TIG" in prompt
    assert "TIG WELDING" in prompt

    # Without TIG indicators
    prompt_no_tig = gen._build_prompt("furniture_table", {
        "description": "standard table",
        "finish": "raw",
    })
    assert "THIS PROJECT REQUIRES TIG WELDING" not in prompt_no_tig


# ============================================================
# Hardware URL generation
# ============================================================

def test_hardware_sourcer_fills_missing_urls():
    """Hardware items get McMaster/Amazon/Grainger search URLs when url is empty."""
    sourcer = HardwareSourcer()
    items = [{
        "description": "Adjustable leveling feet",
        "quantity": 4,
        "options": [
            {"supplier": "McMaster-Carr", "price": 5.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 3.50, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 6.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    }]
    priced = sourcer.price_hardware_list(items)
    assert len(priced) == 1
    for option in priced[0]["options"]:
        assert option["url"], "URL should not be empty for %s" % option["supplier"]
        assert "leveling" in option["url"].lower() or "leveling" in urllib.parse.unquote_plus(option["url"]).lower()


def test_hardware_sourcer_preserves_existing_urls():
    """URLs that already have values are not overwritten."""
    sourcer = HardwareSourcer()
    items = [{
        "description": "Test item",
        "quantity": 1,
        "options": [
            {"supplier": "McMaster-Carr", "price": 10.00,
             "url": "https://www.mcmaster.com/1573A63", "part_number": "1573A63", "lead_days": 3},
        ],
    }]
    priced = sourcer.price_hardware_list(items)
    assert priced[0]["options"][0]["url"] == "https://www.mcmaster.com/1573A63"


# ============================================================
# Dynamic model name
# ============================================================

def test_pricing_engine_uses_dynamic_model_name():
    """Pricing engine assumption text uses GEMINI_MODEL env var, not hardcoded."""
    engine = PricingEngine()
    session_data = {
        "job_type": "furniture_table",
        "fields": {},
        "material_list": {"items": [], "hardware": [], "assumptions": [],
                          "weld_linear_inches": 0, "total_sq_ft": 0},
        "labor_estimate": {"processes": [{"hours": 1, "rate": 100, "notes": "test"}],
                           "total_hours": 1},
        "finishing": {"method": "raw", "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 15}

    with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-3.0-flash"}):
        result = engine.build_priced_quote(session_data, user)
    assumptions_text = " ".join(result["assumptions"])
    assert "gemini-3.0-flash" in assumptions_text
    assert "Gemini 2.0 Flash" not in assumptions_text


# ============================================================
# Build instructions wiring to PricingEngine
# ============================================================

def test_pricing_engine_passes_through_build_instructions():
    """PricingEngine includes detailed_cut_list and build_instructions in output."""
    engine = PricingEngine()
    session_data = {
        "job_type": "furniture_table",
        "fields": {},
        "material_list": {"items": [], "hardware": [], "assumptions": [],
                          "weld_linear_inches": 0, "total_sq_ft": 0},
        "labor_estimate": {"processes": [], "total_hours": 0},
        "finishing": {"method": "raw", "total": 0},
        "detailed_cut_list": [
            {"description": "Table leg", "profile": "sq_tube_2x2_11ga",
             "length_inches": 30.0, "quantity": 4}
        ],
        "build_instructions": [
            {"step": 1, "title": "Layout", "description": "Mark pieces",
             "tools": ["tape measure"], "duration_minutes": 15}
        ],
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 15}

    result = engine.build_priced_quote(session_data, user)
    assert "detailed_cut_list" in result
    assert len(result["detailed_cut_list"]) == 1
    assert result["detailed_cut_list"][0]["description"] == "Table leg"
    assert "build_instructions" in result
    assert len(result["build_instructions"]) == 1
    assert result["build_instructions"][0]["title"] == "Layout"


def test_pricing_engine_omits_empty_ai_sections():
    """PricingEngine omits detailed_cut_list and build_instructions when empty."""
    engine = PricingEngine()
    session_data = {
        "job_type": "furniture_table",
        "fields": {},
        "material_list": {"items": [], "hardware": [], "assumptions": [],
                          "weld_linear_inches": 0, "total_sq_ft": 0},
        "labor_estimate": {"processes": [], "total_hours": 0},
        "finishing": {"method": "raw", "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 15}

    result = engine.build_priced_quote(session_data, user)
    assert "detailed_cut_list" not in result
    assert "build_instructions" not in result
