"""
Tests for Prompt 24 — Calculator-Enforced Constraints + Real Pricing

Covers:
1. Conditional required fields in question tree engine
2. _post_process_ai_result enforces gate geometry, posts, beam, fence
3. Hard constraint blocks in AI prompts (gate length, picket, beam, welding)
4. Real Osorio-based material pricing
5. mid_rail_type depends on adjacent_fence (not infill_type)
6. HSS profiles in AI profile list
7. Rule 13 includes flux core (FCAW-S) for field welding
"""

import json
import math
import pytest

from backend.calculators.cantilever_gate import (
    CantileverGateCalculator, _resolve_picket_profile,
)
from backend.calculators.material_lookup import MaterialLookup, PRICE_PER_FOOT
from backend.calculators.ai_cut_list import AICutListGenerator, _PROFILE_GROUPS
from backend.question_trees.engine import QuestionTreeEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ai_cut_list(items):
    """Build a minimal AI cut list for testing _build_from_ai_cuts."""
    cuts = []
    for desc, profile, length_in, qty in items:
        cuts.append({
            "description": desc,
            "piece_name": desc.lower().replace(" ", "_"),
            "group": "general",
            "material_type": "mild_steel",
            "profile": profile,
            "length_inches": length_in,
            "quantity": qty,
            "cut_type": "square",
            "cut_angle": 90.0,
            "weld_process": "mig",
            "weld_type": "fillet",
            "notes": "",
        })
    return cuts


class TestConditionalRequiredFields:
    """Part 1: Branch-dependent fields should not block completion."""

    def test_pickets_required_when_selected(self):
        """When Pickets infill selected, picket_material IS required."""
        engine = QuestionTreeEngine()
        answered = {
            "clear_width": "12",
            "height": "6",
            "frame_material": "Square tube (most common)",
            "frame_gauge": "11 gauge (0.120\" - standard for gates)",
            "infill_type": "Pickets (vertical bars)",
            "post_count": "3 posts (standard)",
            "finish": "Powder coat (most durable, outsourced)",
            "installation": "Shop pickup (no installation)",
            # picket_material and picket_spacing NOT provided
        }
        assert not engine.is_complete("cantilever_gate", answered), \
            "Should NOT be complete — picket_material required when Pickets selected"

    def test_pickets_not_required_for_expanded_metal(self):
        """When Expanded metal infill selected, picket_material NOT required."""
        engine = QuestionTreeEngine()
        answered = {
            "clear_width": "12",
            "height": "6",
            "frame_material": "Square tube (most common)",
            "frame_gauge": "11 gauge (0.120\" - standard for gates)",
            "infill_type": "Expanded metal",
            "post_count": "3 posts (standard)",
            "finish": "Powder coat (most durable, outsourced)",
            "installation": "Shop pickup (no installation)",
            # picket_material and picket_spacing NOT provided — should be OK
        }
        assert engine.is_complete("cantilever_gate", answered), \
            "Should be complete — picket fields not required for Expanded metal"

    def test_completion_status_excludes_inactive_branches(self):
        """get_completion_status should not list inactive branch fields as missing."""
        engine = QuestionTreeEngine()
        answered = {
            "clear_width": "12",
            "height": "6",
            "frame_material": "Square tube (most common)",
            "frame_gauge": "11 gauge (0.120\" - standard for gates)",
            "infill_type": "Expanded metal",
            "post_count": "3 posts (standard)",
            "finish": "Powder coat (most durable, outsourced)",
            "installation": "Shop pickup (no installation)",
        }
        status = engine.get_completion_status("cantilever_gate", answered)
        assert status["is_complete"] is True
        assert "picket_material" not in status["required_missing"]
        assert "picket_spacing" not in status["required_missing"]

    def test_completion_with_pickets_answered(self):
        """Full completion with picket fields answered."""
        engine = QuestionTreeEngine()
        answered = {
            "clear_width": "12",
            "height": "6",
            "frame_material": "Square tube (most common)",
            "frame_gauge": "11 gauge (0.120\" - standard for gates)",
            "infill_type": "Pickets (vertical bars)",
            "picket_material": '3/4" square bar (standard)',
            "picket_spacing": '4" on-center (code compliant)',
            "post_count": "3 posts (standard)",
            "finish": "Powder coat (most durable, outsourced)",
            "installation": "Shop pickup (no installation)",
        }
        assert engine.is_complete("cantilever_gate", answered)


class TestPostProcessEnforcesGeometry:
    """Part 2: _post_process_ai_result enforces gate dimensions."""

    def test_enforces_gate_length_assumption(self):
        """Gate panel length assumption = opening × 1.5."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 222, 1),
        ])
        assumptions = ["Test"]
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields, assumptions, hardware=[])
        result = calc._post_process_ai_result(result, fields, assumptions)

        # Check that the gate panel length assumption exists
        has_length = any("1.5 ratio" in a or "× 1.5" in a for a in assumptions)
        assert has_length, "Should include gate panel × 1.5 ratio in assumptions"

    def test_enforces_gate_posts(self):
        """When AI omits gate posts, post-processing adds them."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "post_size": '4" x 4" square tube',
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
        }
        # AI cut list WITHOUT any posts
        ai_cuts = _make_ai_cut_list([
            ("Gate frame top rail", "sq_tube_2x2_11ga", 216, 1),
            ("Gate frame bottom rail", "sq_tube_2x2_11ga", 216, 1),
        ])
        assumptions = ["Test"]
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields, assumptions, hardware=[])
        result = calc._post_process_ai_result(result, fields, assumptions)

        descs = [item["description"].lower() for item in result["items"]]
        has_posts = any("gate post" in d for d in descs)
        assert has_posts, "Should add gate posts when AI omits them"

    def test_enforces_post_concrete(self):
        """When posts have concrete, post-processing adds it."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "post_concrete": "Yes",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 216, 1),
        ])
        assumptions = ["Test"]
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields, assumptions, hardware=[])
        result = calc._post_process_ai_result(result, fields, assumptions)

        descs = [item["description"].lower() for item in result["items"]]
        has_concrete = any("concrete" in d for d in descs)
        assert has_concrete, "Should add post concrete"

    def test_overhead_beam_qty_one(self):
        """Overhead beam for top-hung gate has quantity=1."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung only)",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 216, 1),
        ])
        assumptions = ["Test"]
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields, assumptions, hardware=[])
        result = calc._post_process_ai_result(result, fields, assumptions)

        beam_items = [i for i in result["items"]
                      if "overhead" in i["description"].lower()
                      or "support beam" in i["description"].lower()]
        assert len(beam_items) == 1, "Should have exactly 1 overhead beam item"
        assert beam_items[0]["quantity"] == 1, "Overhead beam quantity must be 1"

    def test_overhead_beam_hss_profile(self):
        """Overhead beam uses HSS profile (not square tube)."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung only)",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 216, 1),
        ])
        assumptions = ["Test"]
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields, assumptions, hardware=[])
        result = calc._post_process_ai_result(result, fields, assumptions)

        beam_items = [i for i in result["items"]
                      if "overhead" in i["description"].lower()]
        assert len(beam_items) > 0
        assert beam_items[0]["profile"] == "hss_4x4_0.25", \
            "Light gate (<800 lbs) should use hss_4x4_0.25"

    def test_fence_sections_enforced(self):
        """Adjacent fence sections are added when AI omits them."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "15",
            "fence_side_2_length": "13",
            "fence_post_count": "4",
            "post_size": '4" x 4" square tube',
            "post_concrete": "Yes",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 216, 1),
        ])
        assumptions = ["Test"]
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields, assumptions, hardware=[])
        result = calc._post_process_ai_result(result, fields, assumptions)

        descs = [i["description"].lower() for i in result["items"]]
        has_fence = any("fence" in d for d in descs)
        assert has_fence, "Should add fence section materials"

    def test_post_length_validation(self):
        """Short AI-generated posts get flagged in assumptions."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "10",  # 120" + 2" + 42" = 164"
            "post_concrete": "Yes",
        }
        # AI generates short posts (only 120")
        ai_cuts = _make_ai_cut_list([
            ("Gate post", "sq_tube_4x4_11ga", 120, 3),
        ])
        assumptions = ["Test"]
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields, assumptions, hardware=[])
        result = calc._post_process_ai_result(result, fields, assumptions)

        has_warning = any("short" in a.lower() or "warning" in a.lower()
                         for a in assumptions)
        assert has_warning, "Should warn about short AI-generated posts"


class TestHardConstraintsInPrompt:
    """Part 3: Hard constraint blocks injected into Gemini prompts."""

    def test_gate_length_constraint(self):
        """AI prompt includes gate length hard constraint."""
        gen = AICutListGenerator()
        fields = {
            "clear_width": "12",
            "height": "6",
        }
        ctx = gen._build_field_context("cantilever_gate", fields)
        assert "HARD CONSTRAINT" in ctx
        assert "18.0 ft" in ctx  # 12 × 1.5 = 18

    def test_picket_material_constraint(self):
        """AI prompt includes picket material hard constraint."""
        gen = AICutListGenerator()
        fields = {
            "height": "6",
            "infill_type": "Pickets (vertical bars)",
            "picket_material": '5/8" square bar',
        }
        ctx = gen._build_field_context("cantilever_gate", fields)
        assert "sq_bar_0.625" in ctx
        assert "HARD CONSTRAINT" in ctx

    def test_overhead_beam_constraint(self):
        """AI prompt includes overhead beam hard constraint."""
        gen = AICutListGenerator()
        fields = {
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung only)",
        }
        ctx = gen._build_field_context("cantilever_gate", fields)
        assert "ONE beam" in ctx or "qty 1" in ctx.lower() or "Quantity: 1" in ctx

    def test_field_welding_constraint(self):
        """AI prompt includes SMAW/FCAW-S for field welding."""
        gen = AICutListGenerator()
        fields = {
            "height": "6",
            "installation": "Full installation (gate + posts + concrete)",
        }
        ctx = gen._build_field_context("cantilever_gate", fields)
        assert "SMAW" in ctx
        assert "FCAW-S" in ctx
        assert "NEVER" in ctx


class TestOsorioPricing:
    """Part 4: Real Osorio-based material pricing."""

    def test_sq_tube_2x2_price(self):
        """sq_tube_2x2_11ga should be $2.75/ft (Osorio-based)."""
        assert PRICE_PER_FOOT["sq_tube_2x2_11ga"] == 2.75

    def test_hss_4x4_price(self):
        """hss_4x4_0.25 should be $8.25/ft."""
        assert PRICE_PER_FOOT["hss_4x4_0.25"] == 8.25

    def test_new_profiles_exist(self):
        """New profiles added: sq_tube_1.25x1.25_11ga, 1.75x1.75, 3x3_7ga, 6x6_7ga."""
        new_profiles = [
            "sq_tube_1.25x1.25_11ga",
            "sq_tube_1.75x1.75_11ga",
            "sq_tube_3x3_7ga",
            "sq_tube_6x6_7ga",
            "angle_2x2x0.125",
            "angle_3x3x0.1875",
            "flat_bar_3x0.25",
        ]
        for profile in new_profiles:
            assert profile in PRICE_PER_FOOT, \
                "Profile %s should exist in PRICE_PER_FOOT" % profile

    def test_prices_reasonable_range(self):
        """All prices should be positive and under $20/ft."""
        for profile, price in PRICE_PER_FOOT.items():
            assert 0 < price <= 20.0, \
                "Profile %s price $%.2f outside range" % (profile, price)

    def test_lookup_returns_positive_price(self):
        """MaterialLookup.get_price_per_foot returns positive for known profiles."""
        ml = MaterialLookup()
        # Seeded prices may override fallback, but price must be positive
        price = ml.get_price_per_foot("sq_tube_2x2_11ga")
        assert price > 0, "sq_tube_2x2_11ga should have a positive price"
        # New profiles should also resolve
        for profile in ["sq_tube_1.25x1.25_11ga", "sq_tube_3x3_7ga", "angle_3x3x0.1875"]:
            p = ml.get_price_per_foot(profile)
            assert p > 0, "Profile %s should have a price via fallback" % profile


class TestMidRailTypeDependency:
    """Part 5: mid_rail_type depends on adjacent_fence, not infill_type."""

    def test_mid_rail_depends_on_adjacent_fence(self):
        """mid_rail_type.depends_on should be 'adjacent_fence'."""
        with open("backend/question_trees/data/cantilever_gate.json") as f:
            tree = json.load(f)
        q = next(q for q in tree["questions"] if q["id"] == "mid_rail_type")
        assert q["depends_on"] == "adjacent_fence"

    def test_adjacent_fence_branches_include_mid_rail(self):
        """adjacent_fence branches include mid_rail_type."""
        with open("backend/question_trees/data/cantilever_gate.json") as f:
            tree = json.load(f)
        q = next(q for q in tree["questions"] if q["id"] == "adjacent_fence")
        for branch_val, activated in q["branches"].items():
            assert "mid_rail_type" in activated, \
                "Branch '%s' should include mid_rail_type" % branch_val

    def test_infill_branches_no_mid_rail(self):
        """infill_type branches should NOT include mid_rail_type."""
        with open("backend/question_trees/data/cantilever_gate.json") as f:
            tree = json.load(f)
        q = next(q for q in tree["questions"] if q["id"] == "infill_type")
        for branch_val, activated in q["branches"].items():
            assert "mid_rail_type" not in activated, \
                "infill_type branch '%s' should NOT include mid_rail_type" % branch_val


class TestHSSProfilesAndRule13:
    """Parts 6-7: HSS profiles in AI list + rule 13 flux core."""

    def test_hss_profiles_in_ai_list(self):
        """HSS profiles exist in _PROFILE_GROUPS."""
        hss_line = _PROFILE_GROUPS.get("hss", "")
        assert "hss_4x4_0.25" in hss_line
        assert "hss_6x4_0.25" in hss_line

    def test_rule_13_includes_fcaw(self):
        """Rule 13 in build instructions mentions FCAW-S."""
        gen = AICutListGenerator()
        # Build a prompt to check rule 13 content
        fields = {"height": "6", "finish": "Paint"}
        cut_list = [{"description": "Frame", "profile": "sq_tube_2x2_11ga",
                     "length_inches": 100, "quantity": 1, "cut_type": "square"}]
        prompt = gen._build_instructions_prompt("cantilever_gate", fields, cut_list)
        assert "FCAW-S" in prompt
        assert "self-shielded flux core" in prompt

    def test_rule_13_bans_mig_outdoors(self):
        """Rule 13 explicitly bans MIG and TIG for outdoor field work."""
        gen = AICutListGenerator()
        fields = {"height": "6", "finish": "Paint"}
        cut_list = [{"description": "Frame", "profile": "sq_tube_2x2_11ga",
                     "length_inches": 100, "quantity": 1, "cut_type": "square"}]
        prompt = gen._build_instructions_prompt("cantilever_gate", fields, cut_list)
        assert "NEVER specify MIG (GMAW) or TIG (GTAW)" in prompt


class TestRequiredFieldsInJSON:
    """Verify picket_material and picket_spacing are in required_fields."""

    def test_picket_material_in_required(self):
        """picket_material should be in cantilever_gate required_fields."""
        with open("backend/question_trees/data/cantilever_gate.json") as f:
            tree = json.load(f)
        assert "picket_material" in tree["required_fields"]

    def test_picket_spacing_in_required(self):
        """picket_spacing should be in cantilever_gate required_fields."""
        with open("backend/question_trees/data/cantilever_gate.json") as f:
            tree = json.load(f)
        assert "picket_spacing" in tree["required_fields"]
