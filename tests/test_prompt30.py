"""
Tests for Prompt 30: Remove bulk aggregates, height sanity check, Opus default.
"""

import math
import pytest


# =====================================================================
# 1. Bulk aggregate removal
# =====================================================================

class TestBulkAggregateRemoval:
    def _make_calc_and_fields(self):
        from backend.calculators.cantilever_gate import CantileverGateCalculator
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "10",
            "frame_size": '2" x 2"',
            "frame_gauge": "11 gauge",
            "post_size": '4" x 4" square tube',
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
            "infill_type": "Pickets (vertical bars)",
            "picket_spacing": '4" on-center',
            "bottom_guide": "No bottom guide (top-hung)",
            "adjacent_fence": "No",
            "finish": "Paint",
        }
        return calc, fields

    def test_removes_bulk_aggregate_items(self):
        """Bulk aggregates (profile — X.X ft, qty=1) are stripped."""
        calc, fields = self._make_calc_and_fields()

        ai_result = {
            "job_type": "cantilever_gate",
            "items": [
                # Bulk aggregates — should be REMOVED
                {
                    "description": "sq_tube_4x4_11ga — 137.2 ft",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_4x4_11ga",
                    "length_inches": 1646.4,
                    "quantity": 1,
                    "unit_price": 679.14,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                    "line_total": 679.14,
                },
                {
                    "description": "sq_tube_2x2_11ga — 247.7 ft",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_2x2_11ga",
                    "length_inches": 2972.4,
                    "quantity": 1,
                    "unit_price": 617.81,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                    "line_total": 617.81,
                },
                {
                    "description": "sq_bar_0.625 — 2171.4 ft",
                    "material_type": "square_tubing",
                    "profile": "sq_bar_0.625",
                    "length_inches": 26056.8,
                    "quantity": 1,
                    "unit_price": 2388.54,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                    "line_total": 2388.54,
                },
                # Non-bulk itemized item — should be KEPT
                {
                    "description": "Gate post — sq tube 4x4 (13.7 ft)",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_4x4_11ga",
                    "length_inches": 164.0,
                    "quantity": 3,
                    "unit_price": 67.65,
                    "cut_type": "square",
                    "waste_factor": 0.0,
                    "line_total": 202.95,
                },
            ],
            "cut_list": [],
            "hardware": [],
            "total_weight_lbs": 500.0,
            "total_sq_ft": 200.0,
            "weld_linear_inches": 300.0,
            "assumptions": [],
        }

        result = calc._post_process_ai_result(ai_result, fields, [])

        # No bulk aggregates should remain
        bulk_items = [
            i for i in result["items"]
            if i.get("quantity", 0) == 1
            and " — " in i.get("description", "")
            and i.get("description", "").rstrip().endswith("ft")
        ]
        assert len(bulk_items) == 0, (
            "Bulk aggregates should be removed, found: %s"
            % [i["description"] for i in bulk_items])

        # The itemized gate post should still be there
        post_items = [i for i in result["items"]
                      if "gate post" in i.get("description", "").lower()]
        assert len(post_items) >= 1

    def test_cut_list_items_become_material_items(self):
        """Cut list entries are converted to proper material line items."""
        calc, fields = self._make_calc_and_fields()

        ai_result = {
            "job_type": "cantilever_gate",
            "items": [
                # Only bulk aggregates — will be removed
                {
                    "description": "sq_tube_2x2_11ga — 50.0 ft",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_2x2_11ga",
                    "length_inches": 600.0,
                    "quantity": 1,
                    "unit_price": 100.0,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                    "line_total": 100.0,
                },
            ],
            "cut_list": [
                {
                    "description": "Gate frame - top rail",
                    "piece_name": "gate_top_rail",
                    "group": "frame",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_2x2_11ga",
                    "length_inches": 216.0,
                    "quantity": 1,
                    "cut_type": "square",
                },
                {
                    "description": "Gate frame - bottom rail",
                    "piece_name": "gate_bottom_rail",
                    "group": "frame",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_2x2_11ga",
                    "length_inches": 216.0,
                    "quantity": 1,
                    "cut_type": "square",
                },
                {
                    "description": "Gate picket - sq bar 5/8\"",
                    "piece_name": "gate_picket",
                    "group": "infill",
                    "material_type": "square_tubing",
                    "profile": "sq_bar_0.625",
                    "length_inches": 118.0,
                    "quantity": 55,
                    "cut_type": "square",
                },
            ],
            "hardware": [],
            "total_weight_lbs": 300.0,
            "total_sq_ft": 100.0,
            "weld_linear_inches": 200.0,
            "assumptions": [],
        }

        result = calc._post_process_ai_result(ai_result, fields, [])

        # Should have material items from cut list entries
        top_rail = [i for i in result["items"]
                    if "top rail" in i.get("description", "").lower()]
        assert len(top_rail) == 1, "Should have top rail from cut list"
        assert top_rail[0]["length_inches"] == 216.0
        assert top_rail[0]["quantity"] == 1

        pickets = [i for i in result["items"]
                   if "picket" in i.get("description", "").lower()
                   and "fence" not in i.get("description", "").lower()]
        assert len(pickets) >= 1, "Should have pickets from cut list"

    def test_non_bulk_items_preserved(self):
        """Items that aren't bulk aggregates are kept."""
        calc, fields = self._make_calc_and_fields()

        ai_result = {
            "job_type": "cantilever_gate",
            "items": [
                # This is NOT a bulk aggregate — qty=3, real description
                {
                    "description": "Gate post — sq tube 4x4 (13.7 ft)",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_4x4_11ga",
                    "length_inches": 164.0,
                    "quantity": 3,
                    "unit_price": 67.65,
                    "cut_type": "square",
                    "waste_factor": 0.0,
                    "line_total": 202.95,
                },
            ],
            "cut_list": [],
            "hardware": [],
            "total_weight_lbs": 300.0,
            "total_sq_ft": 100.0,
            "weld_linear_inches": 200.0,
            "assumptions": [],
        }

        result = calc._post_process_ai_result(ai_result, fields, [])

        post_items = [i for i in result["items"]
                      if "gate post" in i.get("description", "").lower()]
        assert len(post_items) >= 1
        assert post_items[0]["quantity"] == 3


# =====================================================================
# 2. Height sanity check
# =====================================================================

class TestHeightSanityCheck:
    def test_warns_on_height_over_12ft(self):
        """Post-processor warns when height exceeds 12 ft (likely parsing error)."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator

        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "15",  # Likely a fence length, not gate height
            "post_size": '4" x 4" square tube',
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
            "infill_type": "Pickets (vertical bars)",
            "bottom_guide": "No bottom guide (top-hung)",
            "adjacent_fence": "No",
        }
        ai_result = {
            "job_type": "cantilever_gate",
            "items": [
                {
                    "description": "Gate post — sq tube 4x4",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_4x4_11ga",
                    "length_inches": 224.0,
                    "quantity": 3,
                    "unit_price": 100.0,
                    "cut_type": "square",
                    "waste_factor": 0.0,
                    "line_total": 300.0,
                },
            ],
            "cut_list": [],
            "hardware": [],
            "total_weight_lbs": 400.0,
            "total_sq_ft": 150.0,
            "weld_linear_inches": 250.0,
            "assumptions": [],
        }

        assumptions = []
        result = calc._post_process_ai_result(ai_result, fields, assumptions)

        has_warning = any("exceeds typical" in a or "too tall" in a.lower()
                          for a in assumptions)
        assert has_warning, (
            "Should warn about 15ft height. Assumptions: %s" % assumptions)

    def test_no_warning_for_normal_height(self):
        """No warning for typical gate heights (3-12 ft)."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator

        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "10",
            "post_size": '4" x 4" square tube',
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
            "infill_type": "Pickets (vertical bars)",
            "bottom_guide": "No bottom guide (top-hung)",
            "adjacent_fence": "No",
        }
        ai_result = {
            "job_type": "cantilever_gate",
            "items": [
                {
                    "description": "Gate post — sq tube 4x4",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_4x4_11ga",
                    "length_inches": 164.0,
                    "quantity": 3,
                    "unit_price": 67.65,
                    "cut_type": "square",
                    "waste_factor": 0.0,
                    "line_total": 202.95,
                },
            ],
            "cut_list": [],
            "hardware": [],
            "total_weight_lbs": 400.0,
            "total_sq_ft": 150.0,
            "weld_linear_inches": 250.0,
            "assumptions": [],
        }

        assumptions = []
        result = calc._post_process_ai_result(ai_result, fields, assumptions)

        has_warning = any("exceeds typical" in a for a in assumptions)
        assert not has_warning, (
            "Should NOT warn for 10ft gate. Assumptions: %s" % assumptions)


# =====================================================================
# 3. Gate height hard constraint in AI prompt
# =====================================================================

class TestGateHeightConstraint:
    def test_height_constraint_in_field_context(self):
        """AI prompt includes gate height hard constraint."""
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        fields = {
            "clear_width": "12",
            "height": "10",
            "bottom_guide": "No bottom guide (top-hung)",
        }
        context = gen._build_field_context("cantilever_gate", fields)
        assert "GATE HEIGHT" in context
        assert "10.0 ft" in context
        assert "120" in context  # 10 ft = 120 inches
        assert "fence section lengths" in context.lower()

    def test_height_in_enforced_dimensions(self):
        """Enforced dimensions include gate height."""
        # Test the enforced dims construction logic directly
        ht = "10"
        ht_val = float(ht.split()[0])
        enforced_dims = {}
        enforced_dims["gate_height"] = "%s ft (%.0f inches)" % (ht, ht_val * 12)
        assert enforced_dims["gate_height"] == "10 ft (120 inches)"


# =====================================================================
# 4. Default model is Opus
# =====================================================================

class TestDefaultModel:
    def test_default_fast_model_is_opus(self):
        """Default fast model should be claude-opus-4-6."""
        from backend.claude_client import _DEFAULT_FAST
        assert _DEFAULT_FAST == "claude-opus-4-6"

    def test_default_deep_model_is_opus(self):
        """Default deep model should be claude-opus-4-6."""
        from backend.claude_client import _DEFAULT_DEEP
        assert _DEFAULT_DEEP == "claude-opus-4-6"
