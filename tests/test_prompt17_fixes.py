"""
Prompt 17 fixes — 18 tests.

Tests:
1-3.   Banned term stripping (replacements dict, step cleaning, tools cleaning)
4-5.   Gas estimation (500 weld inches < 200 cu ft, small job < $5)
6-7.   Geometry summary (prompt includes GEOMETRY SUMMARY, uniform step detected)
8-9.   Canonical processes (stock_prep_grind accepted, no warnings)
10-11. Material types (square_tubing accepted, no warnings)
12.    Flat bar cut rule (prompt contains flat bar square cut guidance)
13-14. Grind spec NEVER list (80→120 in NEVER list, in replacements dict)
15-18. Leveler install (process exists, drill-into-tube banned, threaded bung
       in hardware, context checked in ai_cut_list)
"""

from backend.calculators.ai_cut_list import (
    AICutListGenerator, BANNED_TERM_REPLACEMENTS,
    _strip_banned_terms_from_steps, _build_geometry_summary,
)
from backend.calculators.furniture_table import FurnitureTableCalculator
from backend.hardware_sourcer import HardwareSourcer
from backend.knowledge.validation import (
    BANNED_TERMS, VALID_MATERIAL_TYPES, validate_labor_processes,
    validate_cut_list_item,
)
from backend.knowledge.processes import get_process, get_banned_terms


# -------------------------------------------------------------------------
# 1-3: Banned term stripping
# -------------------------------------------------------------------------

def test_banned_term_replacements_dict_exists():
    """BANNED_TERM_REPLACEMENTS dict has required entries."""
    assert isinstance(BANNED_TERM_REPLACEMENTS, dict)
    assert "baking soda" in BANNED_TERM_REPLACEMENTS
    assert "compressed air" in BANNED_TERM_REPLACEMENTS
    assert "wire brush" in BANNED_TERM_REPLACEMENTS
    assert "80 grit then 120 grit" in BANNED_TERM_REPLACEMENTS
    assert "drill into tube" in BANNED_TERM_REPLACEMENTS
    assert "dry fit entire pattern" in BANNED_TERM_REPLACEMENTS


def test_strip_banned_terms_cleans_description():
    """_strip_banned_terms_from_steps replaces banned terms in description."""
    steps = [
        {
            "step": 1,
            "title": "Cleanup",
            "description": "After pulling from vinegar, use baking soda to neutralize.",
            "tools": ["wire brush", "bucket"],
            "safety_notes": "Use compressed air to dry parts.",
        },
    ]
    _strip_banned_terms_from_steps(steps)
    desc = steps[0]["description"]
    assert "baking soda" not in desc.lower()
    assert "dish soap" in desc.lower()


def test_strip_banned_terms_cleans_tools():
    """_strip_banned_terms_from_steps replaces banned terms in tools list."""
    steps = [
        {
            "step": 1,
            "title": "Cleanup",
            "description": "Some step.",
            "tools": ["wire brush", "baking soda", "compressed air"],
            "safety_notes": "",
        },
    ]
    _strip_banned_terms_from_steps(steps)
    tools_text = " ".join(steps[0]["tools"]).lower()
    assert "wire brush" not in tools_text
    assert "baking soda" not in tools_text
    assert "compressed air" not in tools_text


# -------------------------------------------------------------------------
# 4-5: Gas estimation fix
# -------------------------------------------------------------------------

def test_gas_estimation_500_weld_inches():
    """500 weld inches should produce < 200 cu ft of gas (not 1250)."""
    sourcer = HardwareSourcer()
    items = sourcer.estimate_consumables(500.0, 20.0, "raw")
    gas_items = [i for i in items if "shielding gas" in i["description"].lower()]
    assert len(gas_items) == 1
    gas = gas_items[0]
    assert gas["quantity"] < 200, "Gas should be < 200 cu ft, got %d" % gas["quantity"]
    assert gas["line_total"] < 20.0, "Gas cost should be < $20, got $%.2f" % gas["line_total"]


def test_gas_estimation_small_job():
    """A small 50 weld-inch job should have gas cost < $5."""
    sourcer = HardwareSourcer()
    items = sourcer.estimate_consumables(50.0, 5.0, "raw")
    gas_items = [i for i in items if "shielding gas" in i["description"].lower()]
    assert len(gas_items) == 1
    assert gas_items[0]["line_total"] < 5.0


# -------------------------------------------------------------------------
# 6-7: Geometry summary
# -------------------------------------------------------------------------

def test_geometry_summary_in_prompt():
    """Build instructions prompt includes GEOMETRY SUMMARY when cut list has groups."""
    cut_list = [
        {"description": "Leg", "group": "frame", "profile": "sq_tube_2x2_11ga",
         "length_inches": 30.0, "quantity": 4, "cut_type": "miter_45",
         "weld_process": "tig"},
        {"description": "Long rail", "group": "frame", "profile": "sq_tube_1.5x1.5_11ga",
         "length_inches": 48.0, "quantity": 2, "cut_type": "miter_45",
         "weld_process": "tig"},
    ]
    summary = _build_geometry_summary(cut_list)
    assert "GEOMETRY SUMMARY" in summary
    assert "frame" in summary


def test_geometry_summary_detects_uniform_step():
    """Geometry summary detects uniform step pattern in concentric layers."""
    cut_list = [
        {"description": "Layer 1", "group": "pattern", "profile": "flat_bar_1x0.125",
         "length_inches": 18.0, "quantity": 4},
        {"description": "Layer 2", "group": "pattern", "profile": "flat_bar_1x0.125",
         "length_inches": 16.0, "quantity": 4},
        {"description": "Layer 3", "group": "pattern", "profile": "flat_bar_1x0.125",
         "length_inches": 14.0, "quantity": 4},
        {"description": "Layer 4", "group": "pattern", "profile": "flat_bar_1x0.125",
         "length_inches": 12.0, "quantity": 4},
    ]
    summary = _build_geometry_summary(cut_list)
    assert "uniform step" in summary
    assert "2.0" in summary  # -2" step


# -------------------------------------------------------------------------
# 8-9: Canonical processes
# -------------------------------------------------------------------------

def test_stock_prep_grind_is_canonical():
    """stock_prep_grind should be accepted without warning."""
    result = validate_labor_processes([
        {"process": "stock_prep_grind", "hours": 2.0},
        {"process": "cut_prep", "hours": 1.5},
        {"process": "fit_tack", "hours": 3.0},
    ])
    # No warnings about non-canonical process names
    non_canonical_warnings = [
        w for w in result.warnings if "non-canonical" in w.lower()
    ]
    assert len(non_canonical_warnings) == 0


def test_post_weld_cleanup_and_powder_coat_canonical():
    """post_weld_cleanup and powder_coat should be accepted without warning."""
    result = validate_labor_processes([
        {"process": "post_weld_cleanup", "hours": 1.0},
        {"process": "powder_coat", "hours": 0.5},
        {"process": "full_weld", "hours": 4.0},
    ])
    non_canonical_warnings = [
        w for w in result.warnings if "non-canonical" in w.lower()
    ]
    assert len(non_canonical_warnings) == 0


# -------------------------------------------------------------------------
# 10-11: Material types
# -------------------------------------------------------------------------

def test_square_tubing_valid_material_type():
    """square_tubing should be in VALID_MATERIAL_TYPES."""
    assert "square_tubing" in VALID_MATERIAL_TYPES


def test_ai_material_types_accepted():
    """AI-generated material types should pass validation without warnings."""
    for mt in ["square_tubing", "round_tubing", "dom_tubing",
               "mild_steel", "stainless_304", "aluminum_6061"]:
        result = validate_cut_list_item({
            "description": "Test piece",
            "profile": "sq_tube_2x2_11ga",
            "length_inches": 24.0,
            "quantity": 2,
            "cut_type": "square",
            "material_type": mt,
        })
        mat_warnings = [w for w in result.warnings if "material type" in w.lower()]
        assert len(mat_warnings) == 0, "material_type '%s' should be valid" % mt


# -------------------------------------------------------------------------
# 12: Flat bar cut rule
# -------------------------------------------------------------------------

def test_flat_bar_square_cut_rule_in_prompt():
    """AI cut list prompt should contain flat bar square cut guidance."""
    gen = AICutListGenerator()
    prompt = gen._build_prompt("furniture_table", {
        "description": "End table with pyramid flat bar pattern",
        "table_length": "20",
        "table_width": "20",
        "table_height": "24",
    })
    assert "flat bar" in prompt.lower()
    assert "square cut" in prompt.lower()
    # Rule 10 should mention decorative flat bar = square cut
    assert "ALWAYS square cut" in prompt


# -------------------------------------------------------------------------
# 13-14: Grind spec NEVER list
# -------------------------------------------------------------------------

def test_80_120_grit_in_never_list():
    """decorative_stock_prep NEVER list should include 80→120 grit sequence."""
    proc = get_process("decorative_stock_prep")
    assert proc is not None
    never_list = proc.get("NEVER", [])
    never_text = " ".join(never_list).lower()
    assert "80 grit" in never_text
    assert "120 grit" in never_text
    assert "progressive grit" in never_text


def test_grit_sequence_in_replacements():
    """80→120 grit sequence should be in BANNED_TERM_REPLACEMENTS."""
    assert "80 grit then 120 grit" in BANNED_TERM_REPLACEMENTS
    replacement = BANNED_TERM_REPLACEMENTS["80 grit then 120 grit"]
    assert "40-grit" in replacement


# -------------------------------------------------------------------------
# 15-18: Leveler install
# -------------------------------------------------------------------------

def test_leveler_foot_install_process_exists():
    """leveler_foot_install process should exist in PROCESSES registry."""
    proc = get_process("leveler_foot_install")
    assert proc is not None
    assert proc["name"] == "Leveler Foot Installation (Weld-In Threaded Bung)"
    assert proc["category"] == "install"


def test_drill_into_tube_banned_in_leveler():
    """drill into tube variants should be in leveler_foot_install NEVER list."""
    proc = get_process("leveler_foot_install")
    assert proc is not None
    never_list = proc.get("NEVER", [])
    assert "drill into tube" in never_list
    assert "drill and tap tube wall" in never_list
    assert "self-tapping screw into tube" in never_list


def test_threaded_bung_in_furniture_table_hardware():
    """FurnitureTableCalculator should include threaded bung hardware."""
    calc = FurnitureTableCalculator()
    result = calc.calculate({
        "table_length": "48",
        "table_width": "24",
        "table_height": "30",
    })
    hardware = result.get("hardware", [])
    bung_items = [
        h for h in hardware
        if "bung" in h.get("description", "").lower()
    ]
    assert len(bung_items) == 1, "Expected 1 threaded bung hardware item"
    assert bung_items[0]["quantity"] == 4


def test_leveler_install_context_checked_in_ai_cut_list():
    """leveler_install should be in BANNED_TERMS and checked by ai_cut_list."""
    # Verify the banned terms context exists
    assert "leveler_install" in BANNED_TERMS
    assert "drill into tube" in BANNED_TERMS["leveler_install"]

    # Verify the replacement dict covers leveler terms
    assert "drill into tube" in BANNED_TERM_REPLACEMENTS
    assert "weld in threaded bung" in BANNED_TERM_REPLACEMENTS["drill into tube"]
