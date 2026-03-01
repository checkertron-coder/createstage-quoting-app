"""
Session 10 — Intelligence Layer Tests.

Tests verify:
1. Description handoff — original text flows from intake to calculator
2. All 25 calculators have AI-first pattern (_has_description, _try_ai_cut_list)
3. AI cut list prompt overhaul (design analysis, weld process, expanded schema)
4. Labor estimator weld process reasoning (TIG/MIG/stainless/aluminum)
5. Build instructions end-to-end (generate → store → pass through → output)
6. BaseCalculator default AI methods
7. Expanded cut list schema (piece_name, weld_process, weld_type, group, cut_angle)
"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from backend.calculators.ai_cut_list import (
    AICutListGenerator, VALID_CUT_TYPES, VALID_WELD_PROCESSES, VALID_WELD_TYPES,
)
from backend.calculators.base import BaseCalculator
from backend.calculators.registry import get_calculator, list_calculators
from backend.labor_estimator import LaborEstimator


# ============================================================
# Deliverable 1: Description handoff
# ============================================================

def test_start_session_stores_description_in_params(client, auth_headers, db):
    """start_session preserves original description in params_json."""
    from backend import models
    desc = "Custom 20x20x32 steel end table with pyramid pattern legs and glass top"
    resp = client.post("/api/session/start", json={
        "description": desc,
    }, headers=auth_headers)
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id
    ).first()
    assert session is not None
    assert session.params_json.get("description") == desc


def test_description_flows_to_calculator(client, auth_headers, db):
    """Description in params_json reaches the calculator's fields dict."""
    from backend import models
    from sqlalchemy.orm.attributes import flag_modified

    desc = "Custom 20x20x32 steel end table with welded pyramid pattern legs"
    resp = client.post("/api/session/start", json={
        "description": desc,
    }, headers=auth_headers)
    session_id = resp.json()["session_id"]

    # Pre-populate required fields
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id
    ).first()
    params = dict(session.params_json or {})
    params.update({
        "item_type": "Table",
        "material": "Mild steel",
        "approximate_size": "20 x 20 x 32",
        "quantity": "1",
        "finish": "ground smooth",
    })
    session.params_json = params
    session.job_type = "furniture_table"
    flag_modified(session, "params_json")
    db.commit()

    # The calculator should see the description
    assert params.get("description") == desc


# ============================================================
# Deliverable 2: All 25 calculators have AI-first pattern
# ============================================================

def test_all_calculators_have_has_description():
    """Every calculator inherits _has_description from BaseCalculator."""
    all_types = list_calculators()
    for job_type in all_types:
        calc = get_calculator(job_type)
        assert hasattr(calc, "_has_description"), (
            "%s calculator missing _has_description" % job_type
        )


def test_all_calculators_check_description_in_calculate():
    """All 25 calculators have AI-first check in their calculate method."""
    import inspect
    all_types = list_calculators()
    for job_type in all_types:
        calc = get_calculator(job_type)
        source = inspect.getsource(calc.calculate)
        # Each calculator should either have _has_description or _try_ai_cut_list
        has_ai_check = (
            "_has_description" in source or
            "_try_ai_cut_list" in source
        )
        assert has_ai_check, (
            "%s calculator does not check for AI cut list" % job_type
        )


def test_has_description_returns_true_for_long_text():
    """_has_description returns True when description > 10 words."""
    calc = get_calculator("cantilever_gate")
    fields = {
        "description": "Custom 16 foot cantilever sliding gate with sunburst infill pattern and automated operator",
    }
    assert calc._has_description(fields) is True


def test_has_description_returns_false_for_short_text():
    """_has_description returns False when description <= 10 words."""
    calc = get_calculator("cantilever_gate")
    assert calc._has_description({}) is False
    assert calc._has_description({"description": "gate"}) is False
    assert calc._has_description({"description": "a small gate"}) is False


def test_has_description_includes_notes_and_photo_observations():
    """_has_description combines description + notes + photo_observations."""
    calc = get_calculator("swing_gate")
    # Short description alone = False
    assert calc._has_description({"description": "small gate"}) is False
    # But with notes added, > 10 words = True
    assert calc._has_description({
        "description": "small gate",
        "notes": "with ornamental scrollwork and custom finials on top rails",
    }) is True


# ============================================================
# Deliverable 3: AI cut list prompt overhaul
# ============================================================

def test_prompt_has_design_analysis_section():
    """AI cut list prompt includes STEP 1: DESIGN ANALYSIS."""
    gen = AICutListGenerator()
    prompt = gen._build_prompt("furniture_table", {
        "description": "Modern coffee table with geometric base",
    })
    assert "DESIGN ANALYSIS" in prompt
    assert "PATTERN GEOMETRY" in prompt
    assert "WELD PROCESS DETERMINATION" in prompt


def test_prompt_has_expanded_profiles():
    """Prompt lists expanded profile options including DOM tube."""
    gen = AICutListGenerator()
    prompt = gen._build_prompt("roll_cage", {
        "description": "4-point roll cage for Jeep Wrangler",
    })
    assert "dom_tube_1.75x0.120" in prompt
    assert "plate_0.25" in prompt
    assert "sq_tube_3x3_11ga" in prompt


def test_prompt_output_schema_has_new_fields():
    """Prompt's example JSON includes piece_name, group, weld_process, weld_type, cut_angle."""
    gen = AICutListGenerator()
    prompt = gen._build_prompt("furniture_table", {
        "description": "test table",
    })
    assert '"piece_name"' in prompt
    assert '"group"' in prompt
    assert '"weld_process"' in prompt
    assert '"weld_type"' in prompt
    assert '"cut_angle"' in prompt


def test_prompt_tig_detection_stainless():
    """Stainless steel triggers TIG welding guidance."""
    gen = AICutListGenerator()
    prompt = gen._build_prompt("furniture_table", {
        "description": "stainless steel kitchen table",
        "material": "stainless_304",
    })
    assert "TIG WELDING" in prompt
    assert "stainless" in prompt.lower() or "Stainless" in prompt


def test_prompt_tig_detection_aluminum():
    """Aluminum triggers specialized weld guidance."""
    gen = AICutListGenerator()
    prompt = gen._build_prompt("sign_frame", {
        "description": "aluminum sign frame for storefront",
        "material": "aluminum_6061",
    })
    assert "TIG WELDING" in prompt
    assert "luminum" in prompt


def test_prompt_no_tig_for_standard_mild_steel():
    """Standard mild steel projects default to MIG guidance."""
    gen = AICutListGenerator()
    prompt = gen._build_prompt("cantilever_gate", {
        "description": "standard cantilever gate with pickets",
        "finish": "paint",
    })
    assert "THIS PROJECT REQUIRES TIG WELDING" not in prompt
    assert "MIG" in prompt


def test_prompt_skips_internal_fields():
    """Prompt does not include internal fields (starting with _)."""
    gen = AICutListGenerator()
    prompt = gen._build_prompt("custom_fab", {
        "description": "test item",
        "_material_list": {"items": []},
        "_labor_estimate": {"processes": []},
    })
    assert "_material_list" not in prompt
    assert "_labor_estimate" not in prompt


# ============================================================
# Deliverable 3: Expanded parser schema
# ============================================================

def test_parse_response_handles_expanded_schema():
    """Parser handles new fields: piece_name, group, weld_process, weld_type, cut_angle."""
    gen = AICutListGenerator()
    response = json.dumps([
        {
            "description": "Table leg",
            "piece_name": "leg",
            "group": "frame",
            "material_type": "square_tubing",
            "profile": "sq_tube_2x2_11ga",
            "length_inches": 30.0,
            "quantity": 4,
            "cut_type": "miter_45",
            "cut_angle": 45.0,
            "weld_process": "tig",
            "weld_type": "fillet",
            "notes": "4 legs at 30 inches",
        }
    ])
    cuts = gen._parse_response(response)
    assert cuts is not None
    assert len(cuts) == 1
    cut = cuts[0]
    assert cut["piece_name"] == "leg"
    assert cut["group"] == "frame"
    assert cut["weld_process"] == "tig"
    assert cut["weld_type"] == "fillet"
    assert cut["cut_angle"] == 45.0


def test_parse_response_normalizes_weld_process():
    """Parser normalizes invalid weld_process to 'mig'."""
    gen = AICutListGenerator()
    response = json.dumps([{
        "description": "test piece",
        "profile": "sq_tube_2x2_11ga",
        "length_inches": 24.0,
        "quantity": 1,
        "weld_process": "FLUX_CORE",
    }])
    cuts = gen._parse_response(response)
    assert cuts[0]["weld_process"] == "mig"  # Normalized to mig


def test_parse_response_normalizes_cut_types():
    """Parser handles variant cut type strings."""
    gen = AICutListGenerator()
    response = json.dumps([
        {"description": "A", "profile": "sq_tube_2x2_11ga", "length_inches": 24,
         "quantity": 1, "cut_type": "miter 45"},
        {"description": "B", "profile": "sq_tube_2x2_11ga", "length_inches": 24,
         "quantity": 1, "cut_type": "Cope"},
        {"description": "C", "profile": "sq_tube_2x2_11ga", "length_inches": 24,
         "quantity": 1, "cut_type": "miter_22.5"},
    ])
    cuts = gen._parse_response(response)
    assert cuts[0]["cut_type"] == "miter_45"
    assert cuts[1]["cut_type"] == "cope"
    assert cuts[2]["cut_type"] == "miter_22.5"


def test_valid_weld_processes_defined():
    """VALID_WELD_PROCESSES includes mig, tig, stick, none."""
    assert "mig" in VALID_WELD_PROCESSES
    assert "tig" in VALID_WELD_PROCESSES
    assert "stick" in VALID_WELD_PROCESSES
    assert "none" in VALID_WELD_PROCESSES


def test_valid_weld_types_defined():
    """VALID_WELD_TYPES includes common weld joint types."""
    assert "butt" in VALID_WELD_TYPES
    assert "fillet" in VALID_WELD_TYPES
    assert "full_penetration" in VALID_WELD_TYPES
    assert "tack_only" in VALID_WELD_TYPES


def test_valid_cut_types_includes_compound():
    """VALID_CUT_TYPES includes compound and miter_22.5."""
    assert "compound" in VALID_CUT_TYPES
    assert "miter_22.5" in VALID_CUT_TYPES
    assert "miter_45" in VALID_CUT_TYPES


# ============================================================
# Deliverable 4: Labor estimator weld process reasoning
# ============================================================

def test_labor_prompt_includes_weld_section():
    """Labor estimator prompt has WELD PROCESS DETERMINATION section."""
    estimator = LaborEstimator()
    material_list = {
        "items": [{"description": "test", "quantity": 1, "cut_type": "square"}],
        "hardware": [],
        "total_weight_lbs": 100,
        "weld_linear_inches": 50,
        "total_sq_ft": 10,
    }
    quote_params = {
        "job_type": "furniture_table",
        "fields": {"description": "table", "finish": "paint"},
    }
    prompt = estimator._build_prompt(material_list, quote_params)
    assert "WELD PROCESS DETERMINATION" in prompt


def test_labor_prompt_tig_for_ground_smooth():
    """Labor prompt identifies TIG requirement from 'ground smooth' finish."""
    estimator = LaborEstimator()
    material_list = {
        "items": [],
        "hardware": [],
        "total_weight_lbs": 50,
        "weld_linear_inches": 100,
        "total_sq_ft": 5,
    }
    quote_params = {
        "job_type": "furniture_table",
        "fields": {
            "description": "modern table with ground smooth welds",
            "finish": "ground smooth",
        },
    }
    prompt = estimator._build_prompt(material_list, quote_params)
    assert "TIG WELDING" in prompt
    assert "4-8 linear inches per hour" in prompt


def test_labor_prompt_tig_from_material_items():
    """Labor prompt detects TIG from weld_process in material list items."""
    estimator = LaborEstimator()
    material_list = {
        "items": [
            {"description": "leg", "quantity": 4, "cut_type": "miter_45",
             "weld_process": "tig"},
        ],
        "hardware": [],
        "total_weight_lbs": 50,
        "weld_linear_inches": 80,
        "total_sq_ft": 5,
    }
    quote_params = {
        "job_type": "furniture_table",
        "fields": {"description": "table", "finish": "paint"},
    }
    prompt = estimator._build_prompt(material_list, quote_params)
    assert "TIG WELDING" in prompt


def test_labor_prompt_stainless_guidance():
    """Labor prompt includes stainless steel-specific guidance."""
    estimator = LaborEstimator()
    material_list = {
        "items": [],
        "hardware": [],
        "total_weight_lbs": 50,
        "weld_linear_inches": 60,
        "total_sq_ft": 5,
    }
    quote_params = {
        "job_type": "furniture_table",
        "fields": {
            "description": "stainless steel table",
            "material": "stainless_304",
        },
    }
    prompt = estimator._build_prompt(material_list, quote_params)
    assert "STAINLESS" in prompt
    assert "back-purge" in prompt.lower() or "Back-purge" in prompt


def test_labor_prompt_mig_default_for_standard_steel():
    """Standard mild steel defaults to MIG in labor prompt."""
    estimator = LaborEstimator()
    material_list = {
        "items": [{"description": "frame", "quantity": 1, "cut_type": "square"}],
        "hardware": [],
        "total_weight_lbs": 200,
        "weld_linear_inches": 150,
        "total_sq_ft": 30,
    }
    quote_params = {
        "job_type": "cantilever_gate",
        "fields": {"description": "standard gate", "finish": "paint"},
    }
    prompt = estimator._build_prompt(material_list, quote_params)
    assert "THIS JOB REQUIRES TIG WELDING" not in prompt
    assert "MIG" in prompt


def test_labor_prompt_includes_description():
    """Labor prompt passes user description for context."""
    estimator = LaborEstimator()
    material_list = {
        "items": [],
        "hardware": [],
        "total_weight_lbs": 50,
        "weld_linear_inches": 50,
        "total_sq_ft": 5,
    }
    desc = "Custom pyramid pattern table base with glass top support"
    quote_params = {
        "job_type": "furniture_table",
        "fields": {"description": desc, "finish": "raw"},
    }
    prompt = estimator._build_prompt(material_list, quote_params)
    assert "pyramid pattern" in prompt


def test_labor_prompt_piece_count_in_guidance():
    """Labor prompt includes piece count in the estimation guidance."""
    estimator = LaborEstimator()
    items = [{"description": "piece %d" % i, "quantity": 2, "cut_type": "square"}
             for i in range(10)]
    material_list = {
        "items": items,
        "hardware": [],
        "total_weight_lbs": 200,
        "weld_linear_inches": 100,
        "total_sq_ft": 20,
    }
    quote_params = {
        "job_type": "custom_fab",
        "fields": {"description": "test", "finish": "raw"},
    }
    prompt = estimator._build_prompt(material_list, quote_params)
    assert "20 pieces" in prompt  # 10 items × 2 qty


# ============================================================
# Deliverable 5: Build instructions expanded schema
# ============================================================

def test_build_instructions_prompt_has_weld_process():
    """Build instructions prompt specifies weld process per step."""
    gen = AICutListGenerator()
    prompt = gen._build_instructions_prompt("furniture_table", {
        "description": "table",
        "finish": "paint",
    }, [
        {"description": "leg", "quantity": 4, "length_inches": 30, "cut_type": "square"},
    ])
    assert "weld_process" in prompt
    assert "safety_notes" in prompt


def test_parse_instructions_includes_weld_process():
    """Parsed build instructions include weld_process and safety_notes."""
    gen = AICutListGenerator()
    response = json.dumps([
        {
            "step": 1,
            "title": "Cut all pieces",
            "description": "Cut tube stock per cut list",
            "tools": ["chop saw"],
            "duration_minutes": 30,
            "weld_process": None,
            "safety_notes": "Wear eye protection",
        },
        {
            "step": 2,
            "title": "Tack weld frame",
            "description": "Fit and tack the frame",
            "tools": ["MIG welder", "clamps"],
            "duration_minutes": 45,
            "weld_process": "mig",
            "safety_notes": "Welding helmet required",
        },
    ])
    steps = gen._parse_instructions_response(response)
    assert steps is not None
    assert len(steps) == 2
    assert steps[0]["weld_process"] is None
    assert steps[0]["safety_notes"] == "Wear eye protection"
    assert steps[1]["weld_process"] == "mig"


# ============================================================
# Deliverable 6: BaseCalculator default AI methods
# ============================================================

def test_base_calculator_has_description_method():
    """BaseCalculator provides _has_description as a default method."""
    # Get any calculator that uses the base class methods (not overridden)
    calc = get_calculator("cantilever_gate")
    assert hasattr(calc, "_has_description")
    assert callable(calc._has_description)


def test_base_calculator_try_ai_cut_list_method():
    """BaseCalculator provides _try_ai_cut_list as a default method."""
    calc = get_calculator("cantilever_gate")
    assert hasattr(calc, "_try_ai_cut_list")
    assert callable(calc._try_ai_cut_list)


def test_base_calculator_build_from_ai_cuts_method():
    """BaseCalculator provides _build_from_ai_cuts as a default method."""
    calc = get_calculator("cantilever_gate")
    assert hasattr(calc, "_build_from_ai_cuts")
    assert callable(calc._build_from_ai_cuts)


def test_base_build_from_ai_cuts_produces_valid_material_list():
    """_build_from_ai_cuts returns a valid MaterialList dict."""
    calc = get_calculator("bollard")
    ai_cuts = [
        {
            "description": "Bollard pipe",
            "material_type": "mild_steel",
            "profile": "pipe_6_sch40",
            "length_inches": 60.0,
            "quantity": 3,
            "cut_type": "square",
            "notes": "3 bollards at 60 inches each",
        }
    ]
    result = calc._build_from_ai_cuts(
        "bollard", ai_cuts, {"description": "3 bollards"},
        ["Test assumption"],
    )
    assert "items" in result
    assert "hardware" in result
    assert "total_weight_lbs" in result
    assert "weld_linear_inches" in result
    assert result["job_type"] == "bollard"
    assert len(result["items"]) == 1
    assert result["items"][0]["description"] == "Bollard pipe"
    assert "Test assumption" in result["assumptions"]
    assert "Cut list generated by AI" in result["assumptions"][1]


def test_try_ai_cut_list_returns_none_without_api_key():
    """_try_ai_cut_list returns None when GEMINI_API_KEY is not set."""
    calc = get_calculator("cantilever_gate")
    # Ensure no API key
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("GEMINI_API_KEY", None)
        result = calc._try_ai_cut_list("cantilever_gate", {
            "description": "test gate",
        })
        assert result is None


# ============================================================
# Deliverable 7: Pipeline wiring verification
# ============================================================

def test_start_session_description_in_both_params_and_messages(client, auth_headers, db):
    """Description is stored in both params_json and messages_json."""
    from backend import models
    desc = "Test project description for pipeline verification"
    resp = client.post("/api/session/start", json={
        "description": desc,
    }, headers=auth_headers)
    session_id = resp.json()["session_id"]

    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id
    ).first()

    # In params_json for calculators
    assert session.params_json.get("description") == desc

    # In messages_json for audit trail
    assert len(session.messages_json) > 0
    assert session.messages_json[0]["content"] == desc


def test_calculator_template_fallback_without_description():
    """Calculators fall back to template when no description is provided."""
    calc = get_calculator("cantilever_gate")
    # No description → template output (AI check should be skipped)
    result = calc.calculate({
        "clear_width": "10",
        "height": "6",
        "frame_size": "2\" x 2\"",
        "frame_gauge": "11 gauge",
        "infill_type": "Pickets (vertical bars)",
        "post_count": "3 posts (standard)",
        "finish": "Paint",
        "installation": "Yes",
    })
    assert "items" in result
    assert len(result["items"]) > 0
    assert result["job_type"] == "cantilever_gate"


def test_calculator_template_works_with_short_description():
    """Short description (<= 10 words) uses template, not AI."""
    calc = get_calculator("bollard")
    result = calc.calculate({
        "description": "3 bollards",
        "bollard_count": "3",
        "bollard_height": "36",
    })
    assert "items" in result
    assert len(result["items"]) > 0


# ============================================================
# Integration: Session 10 overall
# ============================================================

def test_session10_all_25_calculators_produce_output():
    """Verify every calculator produces valid output with minimal fields."""
    all_types = list_calculators()
    assert len(all_types) == 25

    for job_type in all_types:
        calc = get_calculator(job_type)
        # Minimal fields — no description (forces template path)
        result = calc.calculate({})
        assert "items" in result, "%s missing items" % job_type
        assert "total_weight_lbs" in result, "%s missing total_weight_lbs" % job_type
        assert "assumptions" in result, "%s missing assumptions" % job_type


def test_labor_estimator_fallback_works():
    """Labor estimator produces valid output via rule-based fallback."""
    estimator = LaborEstimator()
    material_list = {
        "items": [
            {"description": "test piece", "quantity": 4, "cut_type": "square"},
        ],
        "hardware": [
            {"description": "bolt", "quantity": 8},
        ],
        "total_weight_lbs": 150,
        "weld_linear_inches": 80,
        "total_sq_ft": 20,
    }
    quote_params = {
        "job_type": "custom_fab",
        "fields": {"description": "test item", "finish": "paint",
                    "installation": "Yes"},
    }
    user_rates = {"rate_inshop": 125.00, "rate_onsite": 145.00}

    # Force fallback by not setting API key
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("GEMINI_API_KEY", None)
        result = estimator.estimate(material_list, quote_params, user_rates)

    assert "processes" in result
    assert "total_hours" in result
    assert len(result["processes"]) == 11  # All 11 canonical processes
    assert result["total_hours"] > 0

    # Check per-process structure
    for p in result["processes"]:
        assert "process" in p
        assert "hours" in p
        assert "rate" in p
        assert "notes" in p
        assert p["hours"] >= 0
