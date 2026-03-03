"""
Tests for Prompt 20 — Compound Jobs, Top-Mount Cantilever, Bottom Guide Logic.

Tests:
- Question tree: fence questions added to cantilever_gate.json
- Bottom guide: conditional logic (surface mount / embedded / top-hung)
- Fence sections: material generation for adjacent fence
- AI cut list: field context enrichment
- Material profiles: HSS profiles added
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

    def test_fence_post_spacing_exists(self, tree):
        ids = [q["id"] for q in tree["questions"]]
        assert "fence_post_spacing" in ids

    def test_fence_infill_match_exists(self, tree):
        ids = [q["id"] for q in tree["questions"]]
        assert "fence_infill_match" in ids

    def test_fence_questions_depend_on_adjacent_fence(self, tree):
        fence_qs = [q for q in tree["questions"]
                    if q["id"] in ("fence_side_1_length", "fence_side_2_length",
                                   "fence_post_spacing", "fence_infill_match")]
        for q in fence_qs:
            assert q["depends_on"] == "adjacent_fence", (
                "%s should depend on adjacent_fence" % q["id"])

    def test_adjacent_fence_branches(self, tree):
        q = next(q for q in tree["questions"] if q["id"] == "adjacent_fence")
        assert q["branches"] is not None
        yes_key = "Yes — fence on one or both sides"
        assert yes_key in q["branches"]
        branch_ids = q["branches"][yes_key]
        assert "fence_side_1_length" in branch_ids
        assert "fence_side_2_length" in branch_ids

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

    def test_top_hung_no_guide(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung only)",
        })
        guide_items = [i for i in result["items"]
                       if "guide" in i["description"].lower()
                       and ("bottom" in i["description"].lower() or "embedded" in i["description"].lower())]
        assert len(guide_items) == 0
        # Check assumption note
        assert any("top-hung" in a.lower() or "no bottom guide" in a.lower()
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
            "adjacent_fence": "Yes — fence on one or both sides",
            "fence_side_1_length": "20",
            "fence_side_2_length": "0",
            "fence_post_spacing": "6 ft on-center (standard residential)",
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
            "adjacent_fence": "Yes — fence on one or both sides",
            "fence_side_1_length": "20",
            "fence_side_2_length": "15",
            "fence_post_spacing": "6 ft on-center (standard residential)",
            "infill_type": "Pickets (vertical bars)",
        })
        fence_items = [i for i in result["items"] if "fence" in i["description"].lower()]
        side_1 = [i for i in fence_items if "Side 1" in i["description"]]
        side_2 = [i for i in fence_items if "Side 2" in i["description"]]
        assert len(side_1) >= 2
        assert len(side_2) >= 2

    def test_fence_posts_at_correct_spacing(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on one or both sides",
            "fence_side_1_length": "24",
            "fence_side_2_length": "0",
            "fence_post_spacing": "8 ft on-center (common commercial)",
            "infill_type": "Pickets (vertical bars)",
        })
        fence_post_items = [i for i in result["items"]
                            if "fence post" in i["description"].lower()
                            and "concrete" not in i["description"].lower()]
        assert len(fence_post_items) == 1
        # 24 ft / 8 ft spacing = 3 posts
        assert fence_post_items[0]["quantity"] == 3

    def test_fence_assumptions_added(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on one or both sides",
            "fence_side_1_length": "20",
            "fence_side_2_length": "0",
            "infill_type": "Pickets (vertical bars)",
        })
        assert any("adjacent fence" in a.lower() for a in result["assumptions"])

    def test_fence_with_expanded_metal(self):
        result = self._calculate({
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on one or both sides",
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
            "adjacent_fence": "Yes — fence on one or both sides",
            "fence_side_1_length": "20",
            "fence_side_2_length": "15",
            "fence_post_spacing": "6 ft on-center",
            "fence_infill_match": "Yes — match gate infill exactly",
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
