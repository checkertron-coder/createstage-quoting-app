"""
Tests for Prompt 47 — "One Call, One Truth"

Covers:
- Full package prompt generation (shape)
- Full package response parsing (validation)
- _opus_* key passthrough from calculator to pricing engine
- _build_labor_from_opus conversion
- /estimate shortcut when opus data present
- Fallback: when _opus_* keys absent, existing code runs
"""

import json
import pytest


# ---------------------------------------------------------------------------
# 1. Prompt shape — _build_full_package_prompt includes all required sections
# ---------------------------------------------------------------------------

def test_full_package_prompt_has_all_sections():
    """Prompt must include: job type, profiles, labor processes, JSON schema."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    gen = AICutListGenerator()
    prompt = gen._build_full_package_prompt("swing_gate", {
        "description": "6ft wide single swing gate with pickets",
        "height": "6",
        "clear_width": "6",
        "material": "Mild steel",
        "finish": "Powder coat",
    })
    assert "swing_gate" in prompt
    assert "AVAILABLE PROFILES" in prompt
    assert "LABOR PROCESSES" in prompt
    assert "cut_list" in prompt
    assert "build_instructions" in prompt
    assert "hardware" in prompt
    assert "consumables" in prompt
    assert "labor_hours" in prompt
    assert "finishing_method" in prompt
    assert "layout_setup" in prompt
    assert "final_inspection" in prompt


def test_full_package_prompt_includes_weld_guidance():
    """Weld guidance must be injected based on material type."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    gen = AICutListGenerator()
    prompt = gen._build_full_package_prompt("furniture_table", {
        "description": "Stainless steel coffee table with glass top",
        "material": "Stainless steel (304)",
    })
    assert "WELD PROCESS" in prompt or "weld" in prompt.lower()
    # Stainless should trigger TIG guidance
    assert "tig" in prompt.lower() or "TIG" in prompt


# ---------------------------------------------------------------------------
# 2. Parse full package — validation logic
# ---------------------------------------------------------------------------

def test_parse_full_package_valid():
    """Valid JSON response returns complete package dict."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    gen = AICutListGenerator()
    response = json.dumps({
        "cut_list": [
            {
                "description": "Frame leg",
                "piece_name": "leg",
                "group": "frame",
                "material_type": "mild_steel",
                "profile": "sq_tube_2x2_11ga",
                "length_inches": 30.0,
                "quantity": 4,
                "cut_type": "square",
                "weld_process": "mig",
            }
        ],
        "build_instructions": [
            {
                "step": 1,
                "title": "Cut legs",
                "description": "Cut 4 legs to 30 inches",
                "tools": ["chop saw"],
                "duration_minutes": 15,
            }
        ],
        "hardware": [
            {"description": "Leveling feet", "quantity": 4, "estimated_price": 3.50}
        ],
        "consumables": [
            {"description": "MIG wire spool", "quantity": 1, "unit_price": 25.00}
        ],
        "labor_hours": {
            "layout_setup": {"hours": 0.5, "notes": "Simple layout"},
            "cut_prep": {"hours": 1.0, "notes": "4 cuts"},
            "fit_tack": {"hours": 1.0, "notes": "4 joints"},
            "full_weld": {"hours": 1.5, "notes": "Fillet welds"},
            "grind_clean": {"hours": 0.5, "notes": "Grind flush"},
            "finish_prep": {"hours": 0.5, "notes": "Sand and clean"},
            "hardware_install": {"hours": 0.25, "notes": "Feet install"},
            "final_inspection": {"hours": 0.25, "notes": "QC check"},
        },
        "finishing_method": "powder_coat",
        "assumptions": ["Standard 2x2 tube used"],
        "exclusions": ["Delivery not included"],
    })
    result = gen._parse_full_package(response)
    assert result is not None
    assert len(result["cut_list"]) == 1
    assert result["cut_list"][0]["profile"] == "sq_tube_2x2_11ga"
    assert result["build_instructions"] is not None
    assert len(result["hardware"]) == 1
    assert result["hardware"][0]["estimated_price"] == 3.50
    assert len(result["consumables"]) == 1
    assert result["consumables"][0]["line_total"] == 25.00
    assert result["labor_hours"]["cut_prep"]["hours"] == 1.0
    assert result["finishing_method"] == "powder_coat"
    assert len(result["assumptions"]) == 1
    assert len(result["exclusions"]) == 1


def test_parse_full_package_empty_cut_list_returns_none():
    """Empty cut_list should trigger fallback (return None)."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    gen = AICutListGenerator()
    response = json.dumps({
        "cut_list": [],
        "build_instructions": [],
        "hardware": [],
        "consumables": [],
        "labor_hours": {},
        "finishing_method": "raw",
        "assumptions": [],
        "exclusions": [],
    })
    result = gen._parse_full_package(response)
    assert result is None


def test_parse_full_package_invalid_finishing_defaults_raw():
    """Invalid finishing_method should default to 'raw'."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    gen = AICutListGenerator()
    response = json.dumps({
        "cut_list": [
            {
                "description": "Test piece",
                "material_type": "mild_steel",
                "profile": "sq_tube_1x1_14ga",
                "length_inches": 24.0,
                "quantity": 1,
                "cut_type": "square",
            }
        ],
        "finishing_method": "sparkle_chrome_deluxe",
    })
    result = gen._parse_full_package(response)
    assert result is not None
    assert result["finishing_method"] == "raw"


def test_parse_full_package_labor_numeric_shorthand():
    """Labor hours can be plain numbers (not just dicts)."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    gen = AICutListGenerator()
    response = json.dumps({
        "cut_list": [
            {
                "description": "Leg",
                "material_type": "mild_steel",
                "profile": "sq_tube_2x2_11ga",
                "length_inches": 30.0,
                "quantity": 4,
                "cut_type": "square",
            }
        ],
        "labor_hours": {
            "layout_setup": 0.5,
            "cut_prep": 1.0,
            "fit_tack": 2.0,
        },
    })
    result = gen._parse_full_package(response)
    assert result is not None
    assert result["labor_hours"]["layout_setup"]["hours"] == 0.5
    assert result["labor_hours"]["cut_prep"]["hours"] == 1.0
    assert result["labor_hours"]["fit_tack"]["hours"] == 2.0


# ---------------------------------------------------------------------------
# 3. _build_from_full_package attaches _opus_* keys
# ---------------------------------------------------------------------------

def test_build_from_full_package_attaches_opus_keys():
    """_build_from_full_package must put _opus_* keys on the result dict."""
    from backend.calculators.swing_gate import SwingGateCalculator
    calc = SwingGateCalculator()
    package = {
        "cut_list": [
            {
                "description": "Gate frame rail",
                "material_type": "mild_steel",
                "profile": "sq_tube_2x2_11ga",
                "length_inches": 72.0,
                "quantity": 2,
                "cut_type": "miter_45",
                "piece_name": "rail",
                "group": "frame",
            }
        ],
        "build_instructions": [
            {"step": 1, "title": "Cut rails", "description": "Cut 2 rails",
             "tools": ["chop saw"], "duration_minutes": 10}
        ],
        "hardware": [
            {"description": "Weld-on hinges", "quantity": 2, "estimated_price": 35.00}
        ],
        "consumables": [
            {"description": "Grinding disc", "quantity": 2, "unit_price": 4.50,
             "line_total": 9.00, "category": "consumable"}
        ],
        "labor_hours": {
            "layout_setup": {"hours": 0.5, "notes": ""},
            "cut_prep": {"hours": 1.0, "notes": ""},
        },
        "finishing_method": "paint",
        "assumptions": ["Standard hinges"],
        "exclusions": ["Post installation"],
    }
    fields = {"description": "6ft swing gate", "material": "Mild steel"}
    result = calc._build_from_full_package("swing_gate", package, fields)

    assert "_opus_hardware" in result
    assert "_opus_consumables" in result
    assert "_opus_labor_hours" in result
    assert "_opus_build_instructions" in result
    assert "_opus_finishing_method" in result
    assert "_opus_assumptions" in result
    assert "_opus_exclusions" in result
    assert result["_opus_finishing_method"] == "paint"
    assert len(result["_opus_hardware"]) == 1
    assert result["_opus_labor_hours"]["cut_prep"]["hours"] == 1.0


# ---------------------------------------------------------------------------
# 4. Pricing engine — _build_labor_from_opus
# ---------------------------------------------------------------------------

def test_build_labor_from_opus_converts_dict_to_processes():
    """Opus labor hours dict → standard LaborProcess list."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    opus_labor = {
        "layout_setup": {"hours": 1.0, "notes": ""},
        "cut_prep": {"hours": 2.0, "notes": ""},
        "site_install": {"hours": 3.0, "notes": "On-site work"},
    }
    user = {"rate_inshop": 125.0, "rate_onsite": 150.0}
    processes = pe._build_labor_from_opus(opus_labor, [], user)

    assert len(processes) == 3
    layout = next(p for p in processes if p["process"] == "layout_setup")
    assert layout["hours"] == 1.0
    assert layout["rate"] == 125.0  # In-shop rate
    site = next(p for p in processes if p["process"] == "site_install")
    assert site["hours"] == 3.0
    assert site["rate"] == 150.0  # On-site rate


def test_build_labor_from_opus_skips_zero_hours():
    """Processes with 0 hours should be omitted."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    opus_labor = {
        "layout_setup": {"hours": 1.0, "notes": ""},
        "clearcoat": {"hours": 0.0, "notes": "Not needed"},
        "paint": {"hours": 0.0, "notes": "Not needed"},
    }
    user = {"rate_inshop": 125.0, "rate_onsite": 145.0}
    processes = pe._build_labor_from_opus(opus_labor, [], user)
    assert len(processes) == 1
    assert processes[0]["process"] == "layout_setup"


def test_build_labor_from_opus_falls_back_on_empty():
    """If opus_labor has no valid entries, return existing_processes."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    existing = [{"process": "cut_prep", "hours": 2.0, "rate": 125, "notes": "fallback"}]
    opus_labor = {"layout_setup": {"hours": 0.0, "notes": ""}}
    processes = pe._build_labor_from_opus(opus_labor, existing, {})
    assert processes == existing


# ---------------------------------------------------------------------------
# 5. Pricing engine — full package path uses opus hardware/consumables
# ---------------------------------------------------------------------------

def test_pricing_engine_full_package_path():
    """When _opus_hardware is present, pricing engine uses opus data directly."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()

    session_data = {
        "session_id": "test-47-full",
        "job_type": "swing_gate",
        "fields": {
            "description": "6ft swing gate",
            "finish": "paint",
        },
        "material_list": {
            "items": [
                {
                    "description": "Frame rail",
                    "material_type": "mild_steel",
                    "profile": "sq_tube_2x2_11ga",
                    "length_inches": 72,
                    "quantity": 2,
                    "unit_price": 12.0,
                    "line_total": 24.0,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                }
            ],
            "hardware": [],
            "total_weight_lbs": 20.0,
            "total_sq_ft": 18.0,
            "weld_linear_inches": 100,
            "assumptions": ["Test assumption"],
            # _opus_* keys from full package
            "_opus_hardware": [
                {
                    "description": "Weld-on hinges (pair)",
                    "quantity": 1,
                    "options": [
                        {"supplier": "Estimated", "price": 35.00,
                         "url": "", "part_number": None, "lead_days": None},
                    ],
                }
            ],
            "_opus_consumables": [
                {"description": "Grinding disc", "quantity": 2,
                 "unit_price": 4.50, "line_total": 9.00, "category": "consumable"}
            ],
            "_opus_labor_hours": {
                "layout_setup": {"hours": 0.5, "notes": ""},
                "cut_prep": {"hours": 1.0, "notes": ""},
                "fit_tack": {"hours": 2.0, "notes": ""},
                "full_weld": {"hours": 2.0, "notes": ""},
                "grind_clean": {"hours": 0.5, "notes": ""},
                "hardware_install": {"hours": 0.5, "notes": ""},
                "final_inspection": {"hours": 0.25, "notes": ""},
            },
            "_opus_finishing_method": "paint",
            "_opus_assumptions": ["Opus: standard hinge placement"],
            "_opus_exclusions": ["Opus: concrete work not included"],
        },
        "labor_estimate": {
            "processes": [
                {"process": "cut_prep", "hours": 99.0, "rate": 125, "notes": "old"},
            ],
            "total_hours": 99.0,
        },
        "finishing": {"method": "raw", "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 15,
            "rate_inshop": 125, "rate_onsite": 145}
    pq = pe.build_priced_quote(session_data, user)

    # Hardware should come from opus, not the catalog
    assert any("hinge" in h.get("description", "").lower()
               for h in pq.get("hardware", []) + pq.get("shop_stock", []))

    # Labor should use opus hours (NOT 99.0 from fallback)
    total_hours = sum(p["hours"] for p in pq["labor"])
    assert total_hours < 20, "Expected opus hours (~6.75), got %.1f" % total_hours

    # Finishing should be paint (from _opus_finishing_method)
    assert pq["finishing"]["method"] == "paint"

    # Opus assumptions should appear
    assert any("Opus:" in a for a in pq["assumptions"])

    # Opus exclusions should appear
    assert any("Opus:" in e for e in pq["exclusions"])


# ---------------------------------------------------------------------------
# 6. Fallback — no _opus_* keys means existing behavior
# ---------------------------------------------------------------------------

def test_pricing_engine_fallback_without_opus_keys():
    """Without _opus_* keys, pricing engine runs existing code path."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()

    session_data = {
        "session_id": "test-47-fallback",
        "job_type": "bollard",
        "fields": {"description": "4 bollards", "finish": "paint"},
        "material_list": {
            "items": [
                {
                    "description": "Bollard pipe",
                    "material_type": "mild_steel",
                    "profile": "pipe_4_sch40",
                    "length_inches": 48,
                    "quantity": 4,
                    "unit_price": 15.0,
                    "line_total": 60.0,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                }
            ],
            "hardware": [],
            "total_weight_lbs": 80.0,
            "total_sq_ft": 20.0,
            "weld_linear_inches": 50,
            "assumptions": [],
            # NO _opus_* keys — should run existing code
        },
        "labor_estimate": {
            "processes": [
                {"process": "cut_prep", "hours": 1.0, "rate": 125, "notes": "fallback"},
                {"process": "full_weld", "hours": 2.0, "rate": 125, "notes": "fallback"},
            ],
            "total_hours": 3.0,
        },
        "finishing": {"method": "raw", "total": 0},
    }
    user = {"id": 1, "shop_name": "Test", "markup_default": 10,
            "rate_inshop": 125, "rate_onsite": 145}
    pq = pe.build_priced_quote(session_data, user)

    # Should use labor from labor_estimate (the normal path)
    labor_hours = sum(p["hours"] for p in pq["labor"])
    assert labor_hours >= 3.0, "Fallback labor should be >=3.0, got %.1f" % labor_hours


# ---------------------------------------------------------------------------
# 7. /estimate shortcut — _estimate_from_opus_package helper
# ---------------------------------------------------------------------------

def test_estimate_from_opus_package_builds_labor():
    """Helper should convert opus labor dict to standard LaborEstimate."""
    from unittest.mock import patch
    from backend.routers.quote_session import _estimate_from_opus_package

    class FakeSession:
        id = "test-session"
        job_type = "swing_gate"
        params_json = {}
        stage = "estimate"
        updated_at = None

    class FakeUser:
        id = 1
        rate_inshop = 125.0
        rate_onsite = 150.0

    class FakeDB:
        def commit(self):
            pass

    material_list = {
        "items": [],
        "total_sq_ft": 20.0,
        "_opus_labor_hours": {
            "layout_setup": {"hours": 0.5, "notes": ""},
            "cut_prep": {"hours": 1.5, "notes": ""},
            "full_weld": {"hours": 3.0, "notes": ""},
            "site_install": {"hours": 2.0, "notes": "On site"},
            "final_inspection": {"hours": 0.25, "notes": ""},
        },
        "_opus_build_instructions": [
            {"step": 1, "title": "Cut", "description": "Cut parts",
             "tools": ["saw"], "duration_minutes": 30, "safety_notes": ""}
        ],
        "_opus_finishing_method": "powder_coat",
    }
    current_params = {"description": "test gate", "finish": "Powder coat"}

    with patch("sqlalchemy.orm.attributes.flag_modified", lambda *a: None):
        result = _estimate_from_opus_package(
            FakeSession(), current_params, material_list, FakeUser(), FakeDB(),
        )

    assert "labor_estimate" in result
    procs = result["labor_estimate"]["processes"]
    assert len(procs) == 5
    # site_install should use onsite rate
    site = next(p for p in procs if p["process"] == "site_install")
    assert site["rate"] == 150.0
    # Total hours
    assert result["total_labor_hours"] == 7.25
    # Build instructions passed through
    assert "ok (1 steps)" in result["build_instructions_status"]
    # Finishing
    assert result["finishing"]["method"] == "powder_coat"


# ---------------------------------------------------------------------------
# 8. Calculator integration — full package tried before ai_cut_list
# ---------------------------------------------------------------------------

def test_calculators_try_full_package_first():
    """Every calculator's calculate() should call _try_full_package before _try_ai_cut_list."""
    import inspect
    from backend.calculators.registry import CALCULATOR_REGISTRY
    for job_type, calc_class in CALCULATOR_REGISTRY.items():
        source = inspect.getsource(calc_class.calculate)
        assert "_try_full_package" in source, (
            "%s.calculate() missing _try_full_package call" % calc_class.__name__
        )


# ---------------------------------------------------------------------------
# 9. Canonical process list consistency
# ---------------------------------------------------------------------------

def test_canonical_processes_match_between_modules():
    """The canonical process list should be consistent across ai_cut_list and labor_calculator."""
    from backend.calculators.ai_cut_list import AICutListGenerator
    gen = AICutListGenerator()
    ai_procs = set(gen._CANONICAL_PROCESSES)

    # Check that the prompt references these same processes
    prompt = gen._build_full_package_prompt("custom_fab", {
        "description": "test"
    })
    for proc in ai_procs:
        assert proc in prompt, "Process '%s' missing from full package prompt" % proc
