"""
Tests for Prompts 20-21 — Compound Jobs, Top-Mount Cantilever, Bottom Guide Logic,
Hardware Pipeline Fix, Fence Post Count.

Tests:
- Question tree: fence questions added to cantilever_gate.json (P20+P21 updates)
- Bottom guide: conditional logic (surface mount / embedded / top-hung w/ overhead beam)
- Fence sections: material generation for adjacent fence (fence_post_count)
- AI cut list: field context enrichment
- Material profiles: HSS profiles added
- Hardware pipeline: latch, carriage qty=2, top-mount description
"""

import json
import math
import os
import pytest

# ---------------------------------------------------------------------------
# Question tree tests
# ---------------------------------------------------------------------------

class TestCantileverQuestionTree:
    """Verify cantilever_gate.json has the new fence questions."""

    @pytest.fixture
    def tree(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend",
            "question_trees", "data", "cantilever_gate.json",
        )
        with open(path) as f:
            return json.load(f)

    def test_adjacent_fence_question_exists(self, tree):
        ids = [q["id"] for q in tree["questions"]]
        assert "adjacent_fence" in ids

    def test_fence_side_lengths_exist(self, tree):
        ids = [q["id"] for q in tree["questions"]]
        assert "fence_side_1_length" in ids
        assert "fence_side_2_length" in ids

    def test_fence_post_count_exists(self, tree):
        ids = [q["id"] for q in tree["questions"]]
        assert "fence_post_count" in ids

    def test_fence_infill_match_exists(self, tree):
        ids = [q["id"] for q in tree["questions"]]
        assert "fence_infill_match" in ids

    def test_fence_questions_depend_on_adjacent_fence(self, tree):
        fence_qs = [q for q in tree["questions"]
                    if q["id"] in ("fence_side_1_length", "fence_side_2_length",
                                   "fence_post_count", "fence_infill_match")]
        for q in fence_qs:
            assert q["depends_on"] == "adjacent_fence", (
                "%s should depend on adjacent_fence" % q["id"])

    def test_adjacent_fence_has_three_options(self, tree):
        q = next(q for q in tree["questions"] if q["id"] == "adjacent_fence")
        assert len(q["options"]) == 3
        options_text = " ".join(q["options"]).lower()
        assert "both sides" in options_text
        assert "one side" in options_text
        assert "gate only" in options_text

    def test_adjacent_fence_branches_both_sides(self, tree):
        q = next(q for q in tree["questions"] if q["id"] == "adjacent_fence")
        assert q["branches"] is not None
        both_key = "Yes — fence on both sides"
        assert both_key in q["branches"]
        branch_ids = q["branches"][both_key]
        assert "fence_side_1_length" in branch_ids
        assert "fence_side_2_length" in branch_ids
        assert "fence_post_count" in branch_ids

    def test_adjacent_fence_branches_one_side(self, tree):
        q = next(q for q in tree["questions"] if q["id"] == "adjacent_fence")
        one_key = "Yes — fence on one side only"
        assert one_key in q["branches"]
        branch_ids = q["branches"][one_key]
        assert "fence_side_1_length" in branch_ids
        # Side 2 should NOT be in one-side branch
        assert "fence_side_2_length" not in branch_ids

    def test_fence_post_count_is_number_type(self, tree):
        q = next(q for q in tree["questions"] if q["id"] == "fence_post_count")
        assert q["type"] == "number"

    def test_decorative_elements_still_last(self, tree):
        """decorative_elements should still be the last question."""
        last_q = tree["questions"][-1]
        assert last_q["id"] == "decorative_elements"


# ---------------------------------------------------------------------------
# Bottom guide conditional logic
# ---------------------------------------------------------------------------

class TestBottomGuideLogic:
    """Verify cantilever gate calculator respects bottom_guide field."""

    def _calculate(self, fields):
        from backend.calculators.cantilever_gate import CantileverGateCalculator
        calc = CantileverGateCalculator()
        return calc.calculate(fields)

    def test_surface_mount_produces_angle_iron(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "bottom_guide": "Surface mount guide roller",
        })
        guide_items = [i for i in result["items"]
                       if "guide" in i["description"].lower() and "bottom" in i["description"].lower()]
        assert len(guide_items) == 1
        assert guide_items[0]["profile"] == "angle_2x2x0.25"

    def test_embedded_produces_channel(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "bottom_guide": "Embedded track (flush with ground)",
        })
        guide_items = [i for i in result["items"]
                       if "guide" in i["description"].lower() or "embedded" in i["description"].lower()]
        assert len(guide_items) == 1
        assert guide_items[0]["profile"] == "channel_4x5.4"

    def test_top_hung_produces_overhead_beam(self):
        """Top-hung should skip bottom guide but add an overhead support beam."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung only)",
        })
        # No bottom guide items
        guide_items = [i for i in result["items"]
                       if "guide" in i["description"].lower()
                       and ("bottom" in i["description"].lower() or "embedded" in i["description"].lower())]
        assert len(guide_items) == 0

        # Overhead beam should exist
        beam_items = [i for i in result["items"]
                      if "overhead" in i["description"].lower() and "beam" in i["description"].lower()]
        assert len(beam_items) == 1
        assert beam_items[0]["profile"].startswith("hss_")

        # Check assumption note
        assert any("top-hung" in a.lower() or "overhead" in a.lower()
                    for a in result["assumptions"])

    def test_default_is_surface_mount(self):
        """When bottom_guide field is missing, default to surface mount."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
        })
        guide_items = [i for i in result["items"]
                       if "guide" in i["description"].lower() and "bottom" in i["description"].lower()]
        assert len(guide_items) == 1
        assert guide_items[0]["profile"] == "angle_2x2x0.25"

    def test_top_hung_beam_sizes_by_weight(self):
        """Light gate gets HSS 4x4, heavy gate gets HSS 6x4."""
        # Light gate (12 ft × 6 ft) should get 4x4
        result_light = self._calculate({
            "clear_width": "12",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung only)",
        })
        beam = [i for i in result_light["items"]
                if "overhead" in i["description"].lower()][0]
        assert beam["profile"] == "hss_4x4_0.25"


# ---------------------------------------------------------------------------
# Fence section generation
# ---------------------------------------------------------------------------

class TestFenceSectionGeneration:
    """Verify adjacent fence material generation."""

    def _calculate(self, fields):
        from backend.calculators.cantilever_gate import CantileverGateCalculator
        calc = CantileverGateCalculator()
        return calc.calculate(fields)

    def test_no_fence_by_default(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
        })
        fence_items = [i for i in result["items"] if "fence" in i["description"].lower()]
        assert len(fence_items) == 0

    def test_fence_one_side(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on one side only",
            "fence_side_1_length": "20",
            "fence_side_2_length": "0",
            "infill_type": "Pickets (vertical bars)",
        })
        fence_items = [i for i in result["items"] if "fence" in i["description"].lower()]
        assert len(fence_items) >= 2  # At least posts + rails + pickets
        # Should have Side 1 items, no Side 2
        side_1 = [i for i in fence_items if "Side 1" in i["description"]]
        side_2 = [i for i in fence_items if "Side 2" in i["description"]]
        assert len(side_1) >= 2
        assert len(side_2) == 0

    def test_fence_both_sides(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "20",
            "fence_side_2_length": "15",
            "infill_type": "Pickets (vertical bars)",
        })
        fence_items = [i for i in result["items"] if "fence" in i["description"].lower()]
        side_1 = [i for i in fence_items if "Side 1" in i["description"]]
        side_2 = [i for i in fence_items if "Side 2" in i["description"]]
        assert len(side_1) >= 2
        assert len(side_2) >= 2

    def test_fence_posts_with_explicit_count(self):
        """When fence_post_count is provided, use it instead of estimating."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on one side only",
            "fence_side_1_length": "24",
            "fence_side_2_length": "0",
            "fence_post_count": "4",
            "infill_type": "Pickets (vertical bars)",
        })
        fence_post_items = [i for i in result["items"]
                            if "fence post" in i["description"].lower()
                            and "concrete" not in i["description"].lower()]
        assert len(fence_post_items) == 1
        # All 4 posts go to the single side
        assert fence_post_items[0]["quantity"] == 4

    def test_fence_posts_estimated_when_no_count(self):
        """When fence_post_count is not provided, estimate from spacing."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on one side only",
            "fence_side_1_length": "24",
            "fence_side_2_length": "0",
            "infill_type": "Pickets (vertical bars)",
        })
        fence_post_items = [i for i in result["items"]
                            if "fence post" in i["description"].lower()
                            and "concrete" not in i["description"].lower()]
        assert len(fence_post_items) == 1
        # 24 ft / 6 ft default spacing = 4 posts
        assert fence_post_items[0]["quantity"] == 4

    def test_fence_assumptions_added(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on one side only",
            "fence_side_1_length": "20",
            "fence_side_2_length": "0",
            "infill_type": "Pickets (vertical bars)",
        })
        assert any("adjacent fence" in a.lower() or "fence side" in a.lower()
                    for a in result["assumptions"])

    def test_fence_with_expanded_metal(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on one side only",
            "fence_side_1_length": "20",
            "fence_side_2_length": "0",
            "infill_type": "Expanded metal",
        })
        fence_infill = [i for i in result["items"]
                        if "fence infill" in i["description"].lower()
                        or ("fence" in i["description"].lower() and "expanded" in i["description"].lower())]
        assert len(fence_infill) >= 1


# ---------------------------------------------------------------------------
# AI cut list context enrichment
# ---------------------------------------------------------------------------

class TestAICutListContext:
    """Verify field context blocks are built for the AI prompt."""

    def _get_generator(self):
        from backend.calculators.ai_cut_list import AICutListGenerator
        return AICutListGenerator()

    def test_top_hung_context(self):
        gen = self._get_generator()
        ctx = gen._build_field_context("cantilever_gate", {
            "bottom_guide": "No bottom guide (top-hung only)",
        })
        assert "top-hung" in ctx.lower() or "no bottom guide" in ctx.lower()
        assert "do not include" in ctx.lower()

    def test_embedded_track_context(self):
        gen = self._get_generator()
        ctx = gen._build_field_context("cantilever_gate", {
            "bottom_guide": "Embedded track (flush with ground)",
        })
        assert "embedded" in ctx.lower()
        assert "channel" in ctx.lower() or "C4" in ctx

    def test_surface_mount_context(self):
        gen = self._get_generator()
        ctx = gen._build_field_context("cantilever_gate", {
            "bottom_guide": "Surface mount guide roller",
        })
        assert "surface mount" in ctx.lower()
        assert "angle" in ctx.lower()

    def test_fence_context_included(self):
        gen = self._get_generator()
        ctx = gen._build_field_context("cantilever_gate", {
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "20",
            "fence_side_2_length": "15",
            "fence_post_count": "6",
            "fence_infill_match": "Yes — match the gate exactly",
        })
        assert "fence" in ctx.lower()
        assert "20" in ctx
        assert "15" in ctx

    def test_no_context_for_other_job_types(self):
        gen = self._get_generator()
        ctx = gen._build_field_context("furniture_table", {
            "width": "48",
            "length": "72",
        })
        assert ctx == ""

    def test_no_context_when_no_special_fields(self):
        gen = self._get_generator()
        ctx = gen._build_field_context("cantilever_gate", {
            "clear_width": "12",
            "height": "6",
        })
        # No bottom_guide or adjacent_fence → no context
        assert ctx == ""


# ---------------------------------------------------------------------------
# Material profiles
# ---------------------------------------------------------------------------

class TestMaterialProfiles:
    """Verify new HSS profiles are available."""

    def test_hss_4x4_price(self):
        from backend.calculators.material_lookup import MaterialLookup
        m = MaterialLookup()
        price = m.get_price_per_foot("hss_4x4_0.25")
        assert price > 0

    def test_hss_6x4_price(self):
        from backend.calculators.material_lookup import MaterialLookup
        m = MaterialLookup()
        price = m.get_price_per_foot("hss_6x4_0.25")
        assert price > 0

    def test_hss_extract_shape(self):
        from backend.calculators.material_lookup import MaterialLookup
        assert MaterialLookup._extract_shape("hss_4x4_0.25") == "hss"
        assert MaterialLookup._extract_shape("hss_6x4_0.25") == "hss"

    def test_hss_profile_description(self):
        from backend.calculators.material_lookup import MaterialLookup
        desc = MaterialLookup._profile_to_description("hss_4x4_0.25")
        assert "HSS" in desc
        assert "4x4" in desc

    def test_hss_in_ai_profiles(self):
        """HSS profiles should appear in AI cut list prompt for cantilever_gate."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        profiles = gen._get_profiles_for_job_type("cantilever_gate")
        assert "hss" in profiles.lower()
        assert "hss_4x4_0.25" in profiles


# ---------------------------------------------------------------------------
# Hardware pipeline (Prompt 21 fixes)
# ---------------------------------------------------------------------------

class TestHardwarePipeline:
    """Verify hardware is built BEFORE AI check with correct quantities."""

    def _calculate(self, fields):
        from backend.calculators.cantilever_gate import CantileverGateCalculator
        calc = CantileverGateCalculator()
        return calc.calculate(fields)

    def test_roller_carriage_qty_is_two(self):
        """Roller carriages should always be qty=2 (one per rear post)."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
        })
        carriage_items = [h for h in result["hardware"]
                          if "carriage" in h["description"].lower()
                          or "roller" in h["description"].lower()]
        assert len(carriage_items) == 1
        assert carriage_items[0]["quantity"] == 2

    def test_latch_in_hardware(self):
        """Latch should appear in hardware list."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "latch_lock": "Gravity latch",
        })
        latch_items = [h for h in result["hardware"]
                       if "latch" in h["description"].lower()]
        assert len(latch_items) == 1
        assert latch_items[0]["quantity"] == 1

    def test_no_latch_when_none(self):
        """No latch hardware when user selects 'None'."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "latch_lock": "None",
        })
        latch_items = [h for h in result["hardware"]
                       if "latch" in h["description"].lower()]
        assert len(latch_items) == 0

    def test_motor_in_hardware(self):
        """Motor should appear in hardware when has_motor=Yes."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "has_motor": "Yes",
            "motor_brand": "LiftMaster LA412 (industry standard)",
        })
        motor_items = [h for h in result["hardware"]
                       if "operator" in h["description"].lower()
                       or "motor" in h["description"].lower()]
        assert len(motor_items) == 1

    def test_gate_stop_in_hardware(self):
        """Gate stop/bumper should always be in hardware."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
        })
        stop_items = [h for h in result["hardware"]
                      if "stop" in h["description"].lower()
                      or "bumper" in h["description"].lower()]
        assert len(stop_items) == 1
        assert stop_items[0]["quantity"] == 2

    def test_top_hung_carriage_description(self):
        """Top-hung should produce 'Top-mount roller carriage' description."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung only)",
        })
        carriage_items = [h for h in result["hardware"]
                          if "carriage" in h["description"].lower()
                          or "roller" in h["description"].lower()]
        assert len(carriage_items) == 1
        assert "top-mount" in carriage_items[0]["description"].lower()

    def test_standard_carriage_description(self):
        """Standard (non-top-hung) should have regular roller carriage description."""
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
        })
        carriage_items = [h for h in result["hardware"]
                          if "carriage" in h["description"].lower()
                          or "roller" in h["description"].lower()]
        assert len(carriage_items) == 1
        assert "top-mount" not in carriage_items[0]["description"].lower()
