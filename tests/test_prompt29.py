"""
Tests for Prompt 29: Fix aggregated cut list, overhead beam qty, gate picket count,
fence picket description/qty mismatch, degreaser banned term.
"""

import math

import pytest


# =====================================================================
# 1. Cut list prompt — individual cuttable pieces (max 240")
# =====================================================================

class TestCutListPromptRules:
    def test_prompt_contains_max_stock_length_rule(self):
        """AI cut list prompt requires individual pieces within 240" stock."""
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        prompt = gen._build_prompt("cantilever_gate", {"description": "test gate"})

        assert "240" in prompt
        assert "chop saw" in prompt.lower()
        assert "INDIVIDUAL CUTTABLE PIECES" in prompt

    def test_prompt_contains_gate_picket_count_rule(self):
        """AI cut list prompt specifies pickets span full panel (opening x 1.5)."""
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        prompt = gen._build_prompt("cantilever_gate", {"description": "test gate"})

        assert "GATE PICKET COUNT" in prompt
        assert "FULL gate panel length" in prompt
        assert "opening x 1.5" in prompt.lower() or "opening × 1.5" in prompt

    def test_prompt_contains_overhead_beam_rule(self):
        """AI cut list prompt specifies ONE overhead beam, never qty 2."""
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        prompt = gen._build_prompt("cantilever_gate", {"description": "test gate"})

        assert "OVERHEAD BEAM" in prompt
        assert "ONE (1)" in prompt or "exactly ONE" in prompt
        assert "Never qty 2" in prompt


# =====================================================================
# 2. Overhead beam qty=1 enforcement in post-processor
# =====================================================================

class TestOverheadBeamQtyEnforcement:
    def _make_calc_and_fields(self):
        from backend.calculators.cantilever_gate import CantileverGateCalculator
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "frame_size": '2" x 2"',
            "frame_gauge": "11 gauge",
            "post_size": '4" x 4" square tube',
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
            "infill_type": "Pickets (vertical bars)",
            "bottom_guide": "No bottom guide (top-hung)",
            "adjacent_fence": "No",
            "finish": "Paint",
        }
        return calc, fields

    def test_corrects_overhead_beam_qty_2_to_1(self):
        """Post-processor corrects qty=2 overhead beam to qty=1."""
        calc, fields = self._make_calc_and_fields()

        ai_result = {
            "job_type": "cantilever_gate",
            "items": [
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
                {
                    "description": "Overhead support beam — HSS 6x4x1/4",
                    "material_type": "hss_structural_tube",
                    "profile": "hss_6x4_0.25",
                    "length_inches": 240.0,
                    "quantity": 2,
                    "unit_price": 247.20,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                    "line_total": 494.40,
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

        beam_items = [i for i in result["items"]
                      if "overhead" in i.get("description", "").lower()
                      or i.get("profile", "").startswith("hss_")]
        assert len(beam_items) == 1
        assert beam_items[0]["quantity"] == 1
        # Should have assumption about qty correction
        has_qty_note = any("quantity corrected to 1" in a.lower()
                          for a in assumptions)
        assert has_qty_note, "Should note qty correction in assumptions"

    def test_trusts_ai_beam_profile(self):
        """Post-processor trusts AI beam profile — no override."""
        calc, fields = self._make_calc_and_fields()

        ai_result = {
            "job_type": "cantilever_gate",
            "items": [
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
                {
                    "description": "Overhead support beam — HSS 6x4x1/4",
                    "material_type": "hss_structural_tube",
                    "profile": "hss_6x4_0.25",
                    "length_inches": 240.0,
                    "quantity": 1,
                    "unit_price": 247.20,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                    "line_total": 247.20,
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

        beam_items = [i for i in result["items"]
                      if "overhead" in i.get("description", "").lower()
                      or i.get("profile", "").startswith("hss_")]
        assert len(beam_items) == 1
        # Profile kept as-is — trust Opus
        assert beam_items[0]["profile"] == "hss_6x4_0.25"
        has_profile_note = any("profile corrected" in a.lower()
                               for a in assumptions)
        assert not has_profile_note, "Should NOT override profile"

    def test_keeps_correct_beam_profile(self):
        """Post-processor keeps hss_4x4 for a light gate (no correction needed)."""
        calc, fields = self._make_calc_and_fields()

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
                {
                    "description": "Overhead support beam — HSS 4x4x1/4",
                    "material_type": "hss_structural_tube",
                    "profile": "hss_4x4_0.25",
                    "length_inches": 240.0,
                    "quantity": 1,
                    "unit_price": 190.0,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                    "line_total": 190.0,
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

        beam_items = [i for i in result["items"]
                      if i.get("profile", "").startswith("hss_")]
        assert len(beam_items) == 1
        assert beam_items[0]["profile"] == "hss_4x4_0.25"
        # No profile correction needed
        has_profile_note = any("profile corrected" in a.lower()
                               for a in assumptions)
        assert not has_profile_note


# =====================================================================
# 3. Gate picket count validation
# =====================================================================

class TestGatePicretCountValidation:
    def test_warns_on_low_picket_count(self):
        """Post-processor warns when AI provides too few gate pickets."""
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
        }

        # 12' opening x 1.5 = 18' = 216". At 4" OC: 216/4+1 = 55 pickets.
        # AI only provides 39 (covers 12' opening, not full 18' panel)
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
                {
                    "description": "Infill - Pickets at 4\" OC",
                    "material_type": "square_tubing",
                    "profile": "sq_bar_0.625",
                    "length_inches": 118.0,
                    "quantity": 39,
                    "unit_price": 10.82,
                    "cut_type": "square",
                    "waste_factor": 0.03,
                    "line_total": 421.98,
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

        has_warning = any("picket count" in a.lower() and "low" in a.lower()
                          for a in assumptions)
        assert has_warning, (
            "Should warn about low picket count. Assumptions: %s" % assumptions)

    def test_no_warning_when_picket_count_correct(self):
        """No warning when AI provides enough pickets."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator

        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "frame_size": '2" x 2"',
            "frame_gauge": "11 gauge",
            "post_size": '4" x 4" square tube',
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
            "infill_type": "Pickets (vertical bars)",
            "picket_spacing": '4" on-center',
            "bottom_guide": "No bottom guide (top-hung)",
            "adjacent_fence": "No",
        }

        # 12' x 1.5 = 18' = 216". 216/4+1 = 55. Provide 55.
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
                {
                    "description": "Gate pickets — sq bar 5/8\"",
                    "material_type": "square_tubing",
                    "profile": "sq_bar_0.625",
                    "length_inches": 70.0,
                    "quantity": 55,
                    "unit_price": 10.82,
                    "cut_type": "square",
                    "waste_factor": 0.03,
                    "line_total": 595.10,
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

        has_warning = any("picket count" in a.lower() and "low" in a.lower()
                          for a in assumptions)
        assert not has_warning, (
            "Should NOT warn — picket count is correct. Assumptions: %s" % assumptions)


# =====================================================================
# 4. Fence picket description/qty mismatch fix
# =====================================================================

class TestFencePicketDescriptionQty:
    def test_fence_picket_description_includes_waste(self):
        """Fence picket description shows waste-adjusted count matching qty."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator

        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "frame_size": '2" x 2"',
            "frame_gauge": "11 gauge",
            "post_size": '4" x 4" square tube',
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
            "infill_type": "Pickets (vertical bars)",
            "picket_spacing": '4" on-center',
            "adjacent_fence": "Yes — one side",
            "fence_side_1_length": "15",
            "fence_infill_match": "match",
        }

        # Trigger fence generation by omitting fence items from AI
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
            "total_weight_lbs": 300.0,
            "total_sq_ft": 100.0,
            "weld_linear_inches": 200.0,
            "assumptions": [],
        }

        assumptions = []
        result = calc._post_process_ai_result(ai_result, fields, assumptions)

        fence_picket_items = [
            i for i in result["items"]
            if "fence picket" in i.get("description", "").lower()
        ]
        assert len(fence_picket_items) >= 1, "Should have fence pickets"

        for item in fence_picket_items:
            desc = item["description"]
            qty = item["quantity"]
            # Description should include waste-adjusted count matching qty
            assert str(qty) in desc, (
                "Description '%s' should contain qty %d (waste-adjusted)" % (desc, qty))
            assert "waste" in desc.lower(), (
                "Description '%s' should mention waste" % desc)


# =====================================================================
# 5. Degreaser banned term
# =====================================================================

class TestDegreaserBannedTerm:
    def test_degreaser_in_banned_terms(self):
        """'degreaser' is in BANNED_TERM_REPLACEMENTS."""
        from backend.calculators.ai_cut_list import BANNED_TERM_REPLACEMENTS

        assert "degreaser" in BANNED_TERM_REPLACEMENTS
        assert "surface prep solvent" in BANNED_TERM_REPLACEMENTS["degreaser"]

    def test_degreaser_wipedown_replaced(self):
        """'degreaser wipe-down' is replaced with surface prep solvent."""
        from backend.calculators.ai_cut_list import BANNED_TERM_REPLACEMENTS

        assert "degreaser wipe-down" in BANNED_TERM_REPLACEMENTS
        assert "surface prep solvent" in BANNED_TERM_REPLACEMENTS["degreaser wipe-down"]

    def test_fab_sequence_prompt_has_surface_prep_rule(self):
        """Fab sequence prompt includes Rule 16 about surface prep solvent."""
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        prompt = gen._build_instructions_prompt(
            "cantilever_gate", {"description": "test gate"}, [])

        assert "surface prep solvent" in prompt.lower()
        assert "denatured alcohol" in prompt.lower()


# =====================================================================
# 6. Existing Prompt 28 tests still pass (sanity check)
# =====================================================================

class TestPrompt28StillWorks:
    def test_overhead_beam_hard_constraint_in_field_context(self):
        """Field context for top-hung gate still has overhead beam constraint."""
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung)",
        }
        context = gen._build_field_context("cantilever_gate", fields)
        assert "ONE beam" in context or "Quantity: 1" in context
        assert "hss_4x4_0.25" in context

    def test_enforced_dims_still_work(self):
        """Enforced dimensions still appear in build instructions prompt."""
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        enforced = {"opening_width": "12 ft", "gate_length": "18.0 ft"}
        prompt = gen._build_instructions_prompt(
            "cantilever_gate", {"description": "test"}, [],
            enforced_dimensions=enforced)
        assert "12 ft" in prompt
        assert "18.0 ft" in prompt
