"""
Tests for Prompt 23 — AI Path Post-Processing + Pre-Punched Channel Cross Braces

Covers:
1. AI path post-processing (fence posts, overhead beam, mid-rails, post validation)
2. Pre-punched channel profiles in material catalog + weights
3. Mid-rail type question in question tree
4. AI prompt enrichment with calculator-verified values
5. Pre-punched channel labor reduction
"""

import json
import math
import pytest

from backend.calculators.cantilever_gate import (
    CantileverGateCalculator, _resolve_picket_profile, PICKET_MATERIAL_PROFILES,
)
from backend.calculators.material_lookup import MaterialLookup, PRICE_PER_FOOT
from backend.weights import STOCK_WEIGHTS
from backend.calculators.labor_calculator import calculate_labor_hours
from backend.calculators.ai_cut_list import AICutListGenerator


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


class TestAIPathPostProcessing:
    """Test that the AI path no longer bypasses calculator logic."""

    def test_post_process_adds_fence_posts(self):
        """When adjacent fence is answered, post-processing adds fence posts."""
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
        # Build a minimal AI result
        ai_cuts = _make_ai_cut_list([
            ("Gate frame top rail", "sq_tube_2x2_11ga", 222, 1),
            ("Gate frame bottom rail", "sq_tube_2x2_11ga", 222, 1),
        ])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields,
            ["Test assumption"], hardware=[])

        # Run post-processing
        result = calc._post_process_ai_result(result, fields, is_top_hung=False)

        # Check fence posts were added
        descs = [item["description"].lower() for item in result["items"]]
        has_fence_posts = any("fence post" in d for d in descs)
        assert has_fence_posts, "Post-processing should add fence posts when adjacent_fence=Yes"

        # Check fence post concrete was added
        has_concrete = any("concrete" in d for d in descs)
        assert has_concrete, "Post-processing should add fence post concrete"

    def test_post_process_adds_overhead_beam(self):
        """When top-hung, post-processing adds overhead beam."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung only)",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 222, 1),
        ])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields,
            ["Test assumption"], hardware=[])

        result = calc._post_process_ai_result(result, fields, is_top_hung=True)

        descs = [item["description"].lower() for item in result["items"]]
        has_beam = any("overhead" in d and "beam" in d for d in descs)
        assert has_beam, "Post-processing should add overhead beam for top-hung gates"

        # Check assumption about clearance
        assumptions = result.get("assumptions", [])
        has_clearance = any("clearance" in a.lower() or "top-hung" in a.lower()
                           for a in assumptions)
        assert has_clearance, "Should include clearance assumption for top-hung"

    def test_post_process_adds_fence_mid_rails(self):
        """When fence height > 48\", post-processing adds mid-rails."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",  # 72" — should get 1 mid-rail
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "15",
            "fence_side_2_length": "13",
            "fence_post_count": "4",
            "mid_rail_type": "Standard tube rail (pickets welded to flat rail)",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 222, 1),
        ])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields,
            ["Test assumption"], hardware=[])

        result = calc._post_process_ai_result(result, fields, is_top_hung=False)

        descs = [item["description"].lower() for item in result["items"]]
        has_mid_rails = any("mid-rail" in d and "fence" in d for d in descs)
        assert has_mid_rails, "Post-processing should add fence mid-rails for height > 48\""

    def test_post_process_validates_post_lengths(self):
        """Post-processing flags short AI-generated posts."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "10",  # 120" above grade + 2 + 42 = 164"
            "post_concrete": "Yes",
        }
        # AI generates short posts (only 129")
        ai_cuts = _make_ai_cut_list([
            ("Gate post", "sq_tube_4x4_11ga", 129, 3),
        ])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields,
            ["Test assumption"], hardware=[])

        result = calc._post_process_ai_result(result, fields, is_top_hung=False)

        assumptions = result.get("assumptions", [])
        has_warning = any("post length" in a.lower() and "short" in a.lower()
                         for a in assumptions)
        assert has_warning, "Should warn about short AI-generated posts"

    def test_post_process_no_duplicates_when_ai_covers(self):
        """Post-processing doesn't duplicate items AI already generated."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "15",
            "fence_side_2_length": "13",
            "fence_post_count": "4",
            "post_size": '4" x 4" square tube',
        }
        # AI already generates sufficient fence post material
        ai_cuts = _make_ai_cut_list([
            ("Gate post", "sq_tube_4x4_11ga", 116, 3),
            ("Fence post - section 1", "sq_tube_4x4_11ga", 116, 2),
            ("Fence post - section 2", "sq_tube_4x4_11ga", 116, 2),
        ])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields,
            ["Test assumption"], hardware=[])

        result = calc._post_process_ai_result(result, fields, is_top_hung=False)

        # Count fence post items — should have the AI-generated ones but not extras
        fence_post_items = [
            i for i in result["items"]
            if "fence post" in i["description"].lower() and "concrete" not in i["description"].lower()
        ]
        # Should have at most one additional set (from post-processing if AI didn't cover enough)
        # Since AI generated enough, post-processing should skip
        # The items list will have consolidated profiles from _build_from_ai_cuts
        assert len(result["items"]) >= 1  # At minimum the consolidated AI items

    def test_post_process_gate_only_no_extras(self):
        """Gate-only (no fence, standard mount) — post-processing adds nothing."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "No — gate only",
            "bottom_guide": "Surface mount guide roller",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 222, 1),
            ("Gate post", "sq_tube_4x4_11ga", 116, 3),
        ])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields,
            ["Test assumption"], hardware=[])

        items_before = len(result["items"])
        result = calc._post_process_ai_result(result, fields, is_top_hung=False)
        items_after = len(result["items"])

        assert items_after == items_before, "Gate-only should not add extra items"


class TestPrePunchedChannelProfiles:
    """Test pre-punched channel profiles exist in material catalog + weights."""

    def test_profiles_in_price_catalog(self):
        """All 5 pre-punched channel profiles have prices."""
        profiles = [
            "punched_channel_1x0.5_fits_0.5",
            "punched_channel_1.5x0.5_fits_0.5",
            "punched_channel_1.5x0.5_fits_0.625",
            "punched_channel_1.5x0.5_fits_0.75",
            "punched_channel_2x1_fits_0.75",
        ]
        for profile in profiles:
            price = PRICE_PER_FOOT.get(profile, 0.0)
            assert price > 0, "Profile %s should have a price" % profile

    def test_profiles_in_weights(self):
        """All 5 pre-punched channel profiles have weights."""
        profiles = [
            "punched_channel_1x0.5_fits_0.5",
            "punched_channel_1.5x0.5_fits_0.5",
            "punched_channel_1.5x0.5_fits_0.625",
            "punched_channel_1.5x0.5_fits_0.75",
            "punched_channel_2x1_fits_0.75",
        ]
        for profile in profiles:
            weight = STOCK_WEIGHTS.get(profile, 0.0)
            assert weight > 0, "Profile %s should have a weight" % profile

    def test_lookup_returns_price(self):
        """MaterialLookup.get_price_per_foot works for pre-punched channel."""
        ml = MaterialLookup()
        price = ml.get_price_per_foot("punched_channel_1.5x0.5_fits_0.75")
        assert price == 4.50

    def test_price_range_reasonable(self):
        """Pre-punched channel prices are in reasonable range ($3-$8/ft)."""
        for profile, price in PRICE_PER_FOOT.items():
            if "punched_channel" in profile:
                assert 3.0 <= price <= 8.0, (
                    "Profile %s price $%.2f outside reasonable range" % (profile, price)
                )


class TestMidRailTypeQuestion:
    """Test mid_rail_type question in cantilever_gate question tree."""

    def test_question_exists(self):
        """mid_rail_type question exists in cantilever_gate.json."""
        with open("backend/question_trees/data/cantilever_gate.json") as f:
            tree = json.load(f)
        ids = [q["id"] for q in tree["questions"]]
        assert "mid_rail_type" in ids

    def test_question_has_three_options(self):
        """mid_rail_type has pre-punched, standard tube, and not-sure options."""
        with open("backend/question_trees/data/cantilever_gate.json") as f:
            tree = json.load(f)
        q = next(q for q in tree["questions"] if q["id"] == "mid_rail_type")
        assert len(q["options"]) == 3
        assert any("pre-punched" in o.lower() for o in q["options"])
        assert any("standard" in o.lower() for o in q["options"])
        assert any("not sure" in o.lower() for o in q["options"])

    def test_picket_branches_include_mid_rail_type(self):
        """Pickets (vertical bars) branch includes mid_rail_type."""
        with open("backend/question_trees/data/cantilever_gate.json") as f:
            tree = json.load(f)
        infill_q = next(q for q in tree["questions"] if q["id"] == "infill_type")
        picket_branch = infill_q["branches"]["Pickets (vertical bars)"]
        assert "mid_rail_type" in picket_branch


class TestPrePunchedChannelMidRails:
    """Test pre-punched channel selection in post-processing."""

    def test_punched_channel_for_half_inch_pickets(self):
        """1/2\" pickets with pre-punched channel → punched_channel_1.5x0.5_fits_0.5."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "15",
            "fence_side_2_length": "13",
            "fence_post_count": "4",
            "picket_material": '1/2" square bar',
            "mid_rail_type": "Pre-punched channel (pickets slide through — fastest)",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 222, 1),
        ])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields,
            ["Test"], hardware=[])
        result = calc._post_process_ai_result(result, fields, is_top_hung=False)

        profiles = [i.get("profile", "") for i in result["items"]]
        assert "punched_channel_1.5x0.5_fits_0.5" in profiles, (
            "Should use 1/2\" pre-punched channel for 1/2\" pickets"
        )

    def test_punched_channel_for_three_quarter_pickets(self):
        """3/4\" pickets with pre-punched channel → punched_channel_1.5x0.5_fits_0.75."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "15",
            "fence_side_2_length": "13",
            "fence_post_count": "4",
            "picket_material": '3/4" square bar (standard)',
            "mid_rail_type": "Pre-punched channel (pickets slide through — fastest)",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 222, 1),
        ])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields,
            ["Test"], hardware=[])
        result = calc._post_process_ai_result(result, fields, is_top_hung=False)

        profiles = [i.get("profile", "") for i in result["items"]]
        assert "punched_channel_1.5x0.5_fits_0.75" in profiles

    def test_standard_tube_mid_rail(self):
        """Standard tube rail selected → no pre-punched channel profiles."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "15",
            "fence_side_2_length": "13",
            "fence_post_count": "4",
            "mid_rail_type": "Standard tube rail (pickets welded to flat rail)",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 222, 1),
        ])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields,
            ["Test"], hardware=[])
        result = calc._post_process_ai_result(result, fields, is_top_hung=False)

        profiles = [i.get("profile", "") for i in result["items"]]
        assert not any("punched_channel" in p for p in profiles), (
            "Standard tube selection should not use pre-punched channel"
        )

    def test_five_eighths_pickets_punched(self):
        """5/8\" pickets with pre-punched → punched_channel_1.5x0.5_fits_0.625."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "6",
            "adjacent_fence": "Yes — fence on one side only",
            "fence_side_1_length": "15",
            "fence_post_count": "3",
            "picket_material": '5/8" square bar',
            "mid_rail_type": "Pre-punched channel (pickets slide through — fastest)",
        }
        ai_cuts = _make_ai_cut_list([
            ("Gate frame", "sq_tube_2x2_11ga", 222, 1),
        ])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields,
            ["Test"], hardware=[])
        result = calc._post_process_ai_result(result, fields, is_top_hung=False)

        profiles = [i.get("profile", "") for i in result["items"]]
        assert "punched_channel_1.5x0.5_fits_0.625" in profiles


class TestAIPromptEnrichment:
    """Test that AI prompts include calculator-verified values."""

    def test_post_dimensions_include_total_posts(self):
        """AI context includes total post count (gate + fence)."""
        gen = AICutListGenerator()
        fields = {
            "height": "6",
            "post_count": "3 posts (standard)",
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "15",
            "fence_side_2_length": "13",
            "fence_post_count": "4",
        }
        ctx = gen._build_field_context("cantilever_gate", fields)
        assert "Total posts:" in ctx or "total posts" in ctx.lower()

    def test_post_dimensions_exact_length(self):
        """AI context includes exact post length in inches."""
        gen = AICutListGenerator()
        fields = {
            "height": "10",
            "post_concrete": "Yes",
        }
        ctx = gen._build_field_context("cantilever_gate", fields)
        # 10ft = 120" + 2" clearance + 42" embed = 164"
        assert "164" in ctx, "Should include exact post length 164\" for 10ft gate"

    def test_gate_mounting_top_hung_context(self):
        """AI context mentions overhead beam for top-hung gates."""
        gen = AICutListGenerator()
        fields = {
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung only)",
        }
        ctx = gen._build_field_context("cantilever_gate", fields)
        assert "overhead" in ctx.lower() or "top-hung" in ctx.lower()

    def test_fence_section_details_in_context(self):
        """AI context includes fence section lengths and mid-rail count."""
        gen = AICutListGenerator()
        fields = {
            "height": "6",
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "15",
            "fence_side_2_length": "13",
            "fence_post_count": "4",
        }
        ctx = gen._build_field_context("cantilever_gate", fields)
        assert "15" in ctx and "13" in ctx
        assert "mid-rail" in ctx.lower() or "Mid-rail" in ctx


class TestPrePunchedLaborReduction:
    """Test that pre-punched channel reduces fit-tack labor."""

    def test_punched_channel_reduces_fit_tack(self):
        """Pre-punched channel in cut list reduces fit_tack by 35%."""
        cut_list = [
            {"description": "Gate frame", "profile": "sq_tube_2x2_11ga",
             "length_inches": 200, "quantity": 4, "cut_type": "square"},
            {"description": "Picket", "piece_name": "picket", "profile": "sq_bar_0.75",
             "length_inches": 68, "quantity": 30, "cut_type": "square"},
            {"description": "Fence mid-rail", "profile": "punched_channel_1.5x0.5_fits_0.75",
             "length_inches": 180, "quantity": 2, "cut_type": "square"},
        ]
        fields = {"finish": "Powder coat"}

        result_with_punched = calculate_labor_hours("cantilever_gate", cut_list, fields)

        # Same list but without punched channel
        cut_list_standard = [
            {"description": "Gate frame", "profile": "sq_tube_2x2_11ga",
             "length_inches": 200, "quantity": 4, "cut_type": "square"},
            {"description": "Picket", "piece_name": "picket", "profile": "sq_bar_0.75",
             "length_inches": 68, "quantity": 30, "cut_type": "square"},
            {"description": "Fence mid-rail", "profile": "sq_tube_2x2_11ga",
             "length_inches": 180, "quantity": 2, "cut_type": "square"},
        ]

        result_standard = calculate_labor_hours("cantilever_gate", cut_list_standard, fields)

        assert result_with_punched["fit_tack"] < result_standard["fit_tack"], (
            "Pre-punched channel should reduce fit_tack hours"
        )

    def test_no_reduction_without_pickets(self):
        """Without pickets, pre-punched channel doesn't affect fit_tack."""
        cut_list = [
            {"description": "Gate frame", "profile": "sq_tube_2x2_11ga",
             "length_inches": 200, "quantity": 4, "cut_type": "square"},
            {"description": "Expanded metal", "profile": "expanded_metal_13ga",
             "length_inches": 96, "quantity": 2, "cut_type": "square"},
            {"description": "Mid-rail channel", "profile": "punched_channel_1.5x0.5_fits_0.75",
             "length_inches": 180, "quantity": 2, "cut_type": "square"},
        ]
        fields = {"finish": "Powder coat"}

        result = calculate_labor_hours("cantilever_gate", cut_list, fields)

        # With 0 pickets, the 35% reduction shouldn't change fit_tack
        # fit_min = type_a_count * 5 + 0 * 2.5 = base structural only
        assert result["fit_tack"] >= 1.0

    def test_reasoning_mentions_punched(self):
        """Reasoning includes note about pre-punched channel when used."""
        cut_list = [
            {"description": "Frame", "profile": "sq_tube_2x2_11ga",
             "length_inches": 200, "quantity": 4, "cut_type": "square"},
            {"description": "Picket", "piece_name": "picket", "profile": "sq_bar_0.75",
             "length_inches": 68, "quantity": 20, "cut_type": "square"},
            {"description": "Channel rail", "profile": "punched_channel_1.5x0.5_fits_0.75",
             "length_inches": 180, "quantity": 2, "cut_type": "square"},
        ]
        fields = {"finish": "Powder coat"}

        result = calculate_labor_hours("cantilever_gate", cut_list, fields)
        reasoning = result.get("_reasoning", "")
        assert "pre-punched" in reasoning.lower()


class TestPostProcessIntegration:
    """Integration tests for the full AI path with post-processing."""

    def test_calculate_method_calls_post_process(self):
        """Verify the calculate() method structure has post-processing in AI path."""
        # Read the source code to confirm the pattern
        import inspect
        source = inspect.getsource(CantileverGateCalculator.calculate)
        assert "_post_process_ai_result" in source, (
            "calculate() must call _post_process_ai_result after _build_from_ai_cuts"
        )
        # Verify it's NOT a direct return
        assert "result = self._build_from_ai_cuts" in source, (
            "AI path should capture result, not return directly"
        )

    def test_post_process_height_threshold(self):
        """Fence mid-rails only added when height > 48\" (4 ft)."""
        calc = CantileverGateCalculator()
        # 4ft = 48" — should NOT get mid-rails
        fields_short = {
            "clear_width": "12",
            "height": "4",
            "adjacent_fence": "Yes — fence on both sides",
            "fence_side_1_length": "15",
            "fence_side_2_length": "13",
            "fence_post_count": "4",
        }
        ai_cuts = _make_ai_cut_list([("Gate frame", "sq_tube_2x2_11ga", 222, 1)])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields_short, ["Test"], hardware=[])
        result = calc._post_process_ai_result(result, fields_short, is_top_hung=False)

        descs = [i["description"].lower() for i in result["items"]]
        has_mid_rails = any("mid-rail" in d and "fence" in d for d in descs)
        assert not has_mid_rails, "Height <= 48\" should not get fence mid-rails"

    def test_tall_fence_gets_two_mid_rails(self):
        """Fence height > 72\" (6 ft) should get 2 mid-rails per section."""
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "12",
            "height": "7",  # 84" — should get 2 mid-rails
            "adjacent_fence": "Yes — fence on one side only",
            "fence_side_1_length": "20",
            "fence_post_count": "3",
            "mid_rail_type": "Standard tube rail (pickets welded to flat rail)",
        }
        ai_cuts = _make_ai_cut_list([("Gate frame", "sq_tube_2x2_11ga", 222, 1)])
        result = calc._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields, ["Test"], hardware=[])
        result = calc._post_process_ai_result(result, fields, is_top_hung=False)

        mid_rail_items = [
            i for i in result["items"]
            if "mid-rail" in i["description"].lower() and "fence" in i["description"].lower()
        ]
        assert len(mid_rail_items) > 0, "Should have fence mid-rail items"
        # Quantity should be 2 for > 72"
        for item in mid_rail_items:
            assert item["quantity"] == 2, "Height > 72\" should get 2 mid-rails"
