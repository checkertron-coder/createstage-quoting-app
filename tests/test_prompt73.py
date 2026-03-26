"""
P73 — Four-Bug Fix Tests

Bug A: Shop stock subtotal included in subtotal cross-validation
Bug B: Finish/labor consistency — raw finish filters out paint/clearcoat labor
Bug C: BOM prompt includes user preferences (fields)
Bug D: Question tree hints injected into followup prompt
"""

from unittest.mock import patch, MagicMock


# ── Bug A: Shop stock subtotal validation ──

def test_shop_stock_subtotal_included_in_subtotal():
    """shop_stock_subtotal must be part of the total subtotal."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()

    # Calculate shop stock subtotal for items with valid line_totals
    shop_stock = [
        {"description": "Welding wire", "line_total": 42.00, "allocation_pct": 100},
        {"description": "Grinding discs", "line_total": 27.00, "allocation_pct": 100},
    ]
    ss_sub = pe._calculate_shop_stock_subtotal(shop_stock)
    assert ss_sub == 69.00


def test_shop_stock_subtotal_zero_when_empty():
    """Empty shop stock list should return 0."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    assert pe._calculate_shop_stock_subtotal([]) == 0.0
    assert pe._calculate_shop_stock_subtotal(None) == 0.0


def test_shop_stock_allocation_pct():
    """allocation_pct should scale the line_total."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()

    shop_stock = [
        {"description": "Gas", "line_total": 100.00, "allocation_pct": 50},
    ]
    assert pe._calculate_shop_stock_subtotal(shop_stock) == 50.00


# ── Bug B: Finish/labor consistency ──

def test_build_labor_from_opus_raw_filters_paint():
    """When finish_method='raw', paint/clearcoat/finish_prep hours are dropped."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()

    opus_labor = {
        "layout_setup": 2.0,
        "cut_prep": 3.0,
        "full_weld": 8.0,
        "paint": 4.0,         # Should be filtered
        "clearcoat": 2.5,     # Should be filtered
        "finish_prep": 1.5,   # Should be filtered
    }
    user = {"rate_inshop": 125.00, "rate_onsite": 145.00}

    processes = pe._build_labor_from_opus(
        opus_labor, [], user, finish_method="raw"
    )
    process_names = [p["process"] for p in processes]
    assert "paint" not in process_names
    assert "clearcoat" not in process_names
    assert "finish_prep" not in process_names
    assert "layout_setup" in process_names
    assert "cut_prep" in process_names
    assert "full_weld" in process_names


def test_build_labor_from_opus_paint_keeps_paint():
    """When finish_method='paint', paint hours are kept."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()

    opus_labor = {
        "layout_setup": 2.0,
        "paint": 4.0,
        "clearcoat": 0,
    }
    user = {"rate_inshop": 125.00, "rate_onsite": 145.00}

    processes = pe._build_labor_from_opus(
        opus_labor, [], user, finish_method="paint"
    )
    process_names = [p["process"] for p in processes]
    assert "paint" in process_names
    assert "layout_setup" in process_names


def test_build_labor_from_opus_powder_coat_keeps_finish():
    """When finish_method='powder_coat', finish processes are kept."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()

    opus_labor = {
        "full_weld": 8.0,
        "finish_prep": 1.5,
        "paint": 3.0,
    }
    user = {"rate_inshop": 125.00, "rate_onsite": 145.00}

    processes = pe._build_labor_from_opus(
        opus_labor, [], user, finish_method="powder_coat"
    )
    process_names = [p["process"] for p in processes]
    assert "finish_prep" in process_names
    assert "paint" in process_names


def test_build_labor_from_opus_none_finish_treated_as_raw():
    """finish_method=None or '' should be treated as raw."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()

    opus_labor = {"paint": 4.0, "full_weld": 8.0}
    user = {"rate_inshop": 125.00, "rate_onsite": 145.00}

    for fm in (None, "", "none"):
        processes = pe._build_labor_from_opus(
            opus_labor, [], user, finish_method=fm
        )
        process_names = [p["process"] for p in processes]
        assert "paint" not in process_names, "finish_method=%r should filter paint" % fm
        assert "full_weld" in process_names


# ── Bug C: BOM prompt includes user preferences ──

def test_opus_bom_prompt_includes_user_fields():
    """When fields are passed, the BOM prompt should contain user preferences."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()

    captured_prompt = {}

    def mock_call_deep(prompt, **kwargs):
        captured_prompt["text"] = prompt
        return None  # Don't need a real response for this test

    fields = {
        "roller_type": "top rollers only",
        "motor": "no",
        "description": "should be excluded from prefs",
        "_internal_key": "should be excluded",
    }

    with patch("backend.claude_client.call_deep", mock_call_deep):
        with patch("backend.claude_client.is_configured", return_value=True):
            result = hs.opus_estimate_bom(
                "Build a cantilever gate",
                [{"description": "2x2 tube", "quantity": 4}],
                "mild_steel",
                "cantilever_gate",
                fields=fields,
            )

    prompt_text = captured_prompt["text"]
    assert "top rollers only" in prompt_text
    assert "motor: no" in prompt_text
    assert "USER SPECIFICATIONS" in prompt_text
    assert "CRITICAL" in prompt_text
    # Excluded keys should not appear
    assert "_internal_key" not in prompt_text
    assert "should be excluded from prefs" not in prompt_text


def test_opus_bom_prompt_no_fields_still_works():
    """BOM prompt works fine when no fields are passed."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()

    captured_prompt = {}

    def mock_call_deep(prompt, **kwargs):
        captured_prompt["text"] = prompt
        return None

    with patch("backend.claude_client.call_deep", mock_call_deep):
        with patch("backend.claude_client.is_configured", return_value=True):
            hs.opus_estimate_bom(
                "Build a gate",
                [],
                "mild_steel",
                "cantilever_gate",
                fields=None,
            )

    prompt_text = captured_prompt["text"]
    assert "USER SPECIFICATIONS" not in prompt_text
    assert "cantilever_gate" in prompt_text


# ── Bug D: Calculator-required fields in followup ──

def test_calc_required_fields_ornamental_fence():
    """ornamental_fence required fields should include picket_spacing."""
    from backend.question_trees.universal_intake import _get_calculator_required_fields
    fields = _get_calculator_required_fields("ornamental_fence")
    assert fields  # non-empty
    assert "picket_spacing" in fields


def test_calc_required_fields_cantilever_gate():
    """cantilever_gate required fields should include clear_width and picket_spacing."""
    from backend.question_trees.universal_intake import _get_calculator_required_fields
    fields = _get_calculator_required_fields("cantilever_gate")
    assert fields
    assert "clear_width" in fields
    assert "picket_spacing" in fields


def test_calc_required_fields_unknown_type():
    """Unknown job type returns empty string."""
    from backend.question_trees.universal_intake import _get_calculator_required_fields
    fields = _get_calculator_required_fields("nonexistent_job_type_xyz")
    assert fields == ""


def test_calc_required_fields_empty_string():
    """Empty string job type returns empty."""
    from backend.question_trees.universal_intake import _get_calculator_required_fields
    assert _get_calculator_required_fields("") == ""
    assert _get_calculator_required_fields(None) == ""


def test_followup_prompt_includes_calc_requirements():
    """When job_type is provided, followup prompt should include calculator requirements."""
    captured_prompt = {}

    def mock_call_deep(prompt, **kwargs):
        captured_prompt["text"] = prompt
        return '{"known_facts": {}, "questions": [], "readiness": "ready", "readiness_reason": "ok"}'

    with patch("backend.question_trees.universal_intake.call_deep", mock_call_deep):
        with patch("backend.question_trees.universal_intake.is_configured",
                   return_value=True):
            from backend.question_trees.universal_intake import generate_followup_questions
            generate_followup_questions(
                description="Build a 6ft ornamental fence",
                known_facts={"material": "mild steel"},
                qa_history=[],
                photo_observations="",
                job_type="ornamental_fence",
            )

    prompt_text = captured_prompt["text"]
    assert "CALCULATOR REQUIREMENTS" in prompt_text
    assert "picket_spacing" in prompt_text
    assert "Ornamental Fence" in prompt_text


def test_followup_prompt_no_calc_requirements_without_job_type():
    """Without job_type, followup prompt should NOT include calculator requirements."""
    captured_prompt = {}

    def mock_call_deep(prompt, **kwargs):
        captured_prompt["text"] = prompt
        return '{"known_facts": {}, "questions": [], "readiness": "ready", "readiness_reason": "ok"}'

    with patch("backend.question_trees.universal_intake.call_deep", mock_call_deep):
        with patch("backend.question_trees.universal_intake.is_configured",
                   return_value=True):
            from backend.question_trees.universal_intake import generate_followup_questions
            generate_followup_questions(
                description="Build something",
                known_facts={},
                qa_history=[],
                photo_observations="",
                job_type="",
            )

    prompt_text = captured_prompt["text"]
    assert "CALCULATOR REQUIREMENTS" not in prompt_text
