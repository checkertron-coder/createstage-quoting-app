"""
Tests for Prompt 22 — Fab Knowledge Corrections + Picket Options + Cross Braces + Labor Calibration

Covers:
- Picket material options in question trees and calculators
- Fence mid-rails for tall fence sections
- Outdoor grind calibration (reduced for outdoor job types)
- Fit & tack picket positioning time
- Paint hours (sqft-based formula)
- Banned terms (file → flap disc)
- Bar weights in STOCK_WEIGHTS
- Post dimensions in AI context
"""

import json
import math

import pytest


# ---- Picket options ----

class TestPicketOptions:
    """Tests for picket_material question tree updates and calculator resolution."""

    def test_cantilever_gate_has_picket_material(self):
        """cantilever_gate.json has picket_material question, not picket_style."""
        with open("backend/question_trees/data/cantilever_gate.json") as f:
            tree = json.load(f)
        ids = [q["id"] for q in tree["questions"]]
        assert "picket_material" in ids, "picket_material missing from cantilever_gate tree"
        assert "picket_style" not in ids, "picket_style should be removed"

    def test_cantilever_gate_has_picket_top(self):
        """cantilever_gate.json has picket_top question."""
        with open("backend/question_trees/data/cantilever_gate.json") as f:
            tree = json.load(f)
        ids = [q["id"] for q in tree["questions"]]
        assert "picket_top" in ids, "picket_top missing from cantilever_gate tree"

    def test_swing_gate_has_picket_material(self):
        """swing_gate.json has picket_material question, not picket_style."""
        with open("backend/question_trees/data/swing_gate.json") as f:
            tree = json.load(f)
        ids = [q["id"] for q in tree["questions"]]
        assert "picket_material" in ids, "picket_material missing from swing_gate tree"
        assert "picket_style" not in ids, "picket_style should be removed"

    def test_resolve_picket_profile_sq_bar(self):
        """_resolve_picket_profile maps square bar picket_material to correct profile."""
        from backend.calculators.cantilever_gate import _resolve_picket_profile
        fields = {"picket_material": '1/2" square bar'}
        assert _resolve_picket_profile(fields, "Pickets (vertical bars)") == "sq_bar_0.5"

        fields = {"picket_material": '1" square bar (heavy duty)'}
        assert _resolve_picket_profile(fields, "Pickets (vertical bars)") == "sq_bar_1.0"

    def test_resolve_picket_profile_round_bar(self):
        """_resolve_picket_profile maps round bar picket_material to correct profile."""
        from backend.calculators.cantilever_gate import _resolve_picket_profile
        fields = {"picket_material": '5/8" round bar'}
        assert _resolve_picket_profile(fields, "Pickets (vertical bars)") == "round_bar_0.625"

        fields = {"picket_material": '3/4" round bar'}
        assert _resolve_picket_profile(fields, "Pickets (vertical bars)") == "round_bar_0.75"

    def test_resolve_picket_profile_fallback(self):
        """_resolve_picket_profile falls back to INFILL_PROFILES when no picket_material."""
        from backend.calculators.cantilever_gate import _resolve_picket_profile
        fields = {}  # No picket_material
        assert _resolve_picket_profile(fields, "Pickets (vertical bars)") == "sq_bar_0.75"

    def test_ornamental_fence_picket_material(self):
        """ornamental_fence.json has expanded picket_material options (7 options)."""
        with open("backend/question_trees/data/ornamental_fence.json") as f:
            tree = json.load(f)
        picket_q = next(q for q in tree["questions"] if q["id"] == "picket_material")
        assert len(picket_q["options"]) == 7, "Expected 7 picket material options"
        # Should include 1/2" square bar (new)
        assert any('1/2" square' in opt for opt in picket_q["options"])

    def test_ornamental_fence_has_picket_top(self):
        """ornamental_fence.json has picket_top question."""
        with open("backend/question_trees/data/ornamental_fence.json") as f:
            tree = json.load(f)
        ids = [q["id"] for q in tree["questions"]]
        assert "picket_top" in ids, "picket_top missing from ornamental_fence tree"


# ---- Mid-rails ----

class TestFenceMidRails:
    """Tests for mid-rail addition in fence sections."""

    def test_fence_no_mid_rails_48in(self):
        """Fence <=48\" height gets 0 mid-rails."""
        from backend.calculators.ornamental_fence import OrnamentalFenceCalculator
        calc = OrnamentalFenceCalculator()
        result = calc.calculate({
            "linear_footage": "20",
            "height": "4",  # 48 inches
            "picket_spacing": "4\" on-center",
            "finish": "Powder coat",
        })
        mid_rail_items = [i for i in result["items"] if "mid-rail" in i["description"].lower()]
        assert len(mid_rail_items) == 0, "No mid-rails for 48\" fence"

    def test_fence_one_mid_rail_60in(self):
        """Fence 48-72\" height gets 1 mid-rail."""
        from backend.calculators.ornamental_fence import OrnamentalFenceCalculator
        calc = OrnamentalFenceCalculator()
        result = calc.calculate({
            "linear_footage": "20",
            "height": "5",  # 60 inches
            "picket_spacing": "4\" on-center",
            "finish": "Powder coat",
        })
        mid_rail_items = [i for i in result["items"] if "mid-rail" in i["description"].lower()]
        assert len(mid_rail_items) == 1, "Expected 1 mid-rail item for 60\" fence"
        assert any("1 mid-rail" in a for a in result["assumptions"]), \
            "Assumptions should mention 1 mid-rail"

    def test_fence_two_mid_rails_84in(self):
        """Fence >72\" height gets 2 mid-rails."""
        from backend.calculators.ornamental_fence import OrnamentalFenceCalculator
        calc = OrnamentalFenceCalculator()
        result = calc.calculate({
            "linear_footage": "20",
            "height": "7",  # 84 inches
            "picket_spacing": "4\" on-center",
            "finish": "Powder coat",
        })
        mid_rail_items = [i for i in result["items"] if "mid-rail" in i["description"].lower()]
        assert len(mid_rail_items) == 1, "Expected 1 mid-rail line item for 84\" fence"
        assert any("2 mid-rail" in a for a in result["assumptions"]), \
            "Assumptions should mention 2 mid-rails"


# ---- Grind calibration ----

class TestGrindCalibration:
    """Tests for outdoor vs indoor grind calibration."""

    def test_outdoor_grind_less_than_indoor(self):
        """Outdoor gate grind hours should be less than indoor furniture."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"description": "Gate frame", "profile": "sq_tube_2x2_11ga",
             "quantity": 5, "cut_type": "miter_45"},
        ]
        outdoor = calculate_labor_hours("cantilever_gate", cut_list, {"finish": "paint"})
        indoor = calculate_labor_hours("furniture_table", cut_list, {"finish": "paint"})
        assert outdoor["grind_clean"] < indoor["grind_clean"], \
            "Outdoor grind (%.2f) should be less than indoor (%.2f)" % (
                outdoor["grind_clean"], indoor["grind_clean"])

    def test_outdoor_gate_grind_reasonable(self):
        """A typical gate shouldn't exceed 4 hrs of grind time."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"description": "Gate frame top", "profile": "sq_tube_2x2_11ga",
             "quantity": 2, "cut_type": "miter_45"},
            {"description": "Gate frame vertical", "profile": "sq_tube_2x2_11ga",
             "quantity": 3, "cut_type": "miter_45"},
            {"description": "Pickets", "profile": "sq_bar_0.75",
             "quantity": 30, "cut_type": "square", "piece_name": "picket"},
        ]
        result = calculate_labor_hours("cantilever_gate", cut_list, {"finish": "powder coat"})
        assert result["grind_clean"] < 4.0, \
            "Outdoor gate grind %.2f hrs should be < 4 hrs" % result["grind_clean"]

    def test_indoor_furniture_grind_unchanged(self):
        """Indoor furniture grind should still use 6 min/joint for TYPE A."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"description": "Table leg", "profile": "sq_tube_2x2_11ga",
             "quantity": 4, "cut_type": "square"},
        ]
        result = calculate_labor_hours("furniture_table", cut_list, {"finish": "clear coat"})
        # 4 legs × 2 joints = 8 TYPE A joints × 6 min = 48 min + 30 clean = 78 min
        # Plus 90 min mill scale = 168 min = 2.8 hrs
        assert result["grind_clean"] > 1.0, \
            "Indoor grind should be substantial: %.2f" % result["grind_clean"]
        assert "indoor full grind" in result["_reasoning"]


# ---- Fit & Tack ----

class TestFitTack:
    """Tests for picket positioning time in fit & tack."""

    def test_pickets_add_positioning_time(self):
        """Cut list with pickets should have higher fit_tack than without."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        base = [
            {"description": "Gate frame", "profile": "sq_tube_2x2_11ga",
             "quantity": 4, "cut_type": "square"},
        ]
        with_pickets = base + [
            {"description": "Pickets", "profile": "sq_bar_0.75",
             "quantity": 20, "cut_type": "square", "piece_name": "picket"},
        ]
        result_no = calculate_labor_hours("cantilever_gate", base, {"finish": "paint"})
        result_yes = calculate_labor_hours("cantilever_gate", with_pickets, {"finish": "paint"})
        assert result_yes["fit_tack"] > result_no["fit_tack"], \
            "Pickets should add positioning time: with=%.2f, without=%.2f" % (
                result_yes["fit_tack"], result_no["fit_tack"])

    def test_no_pickets_unchanged(self):
        """Cut list without pickets should not add positioning time."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"description": "Frame piece", "profile": "sq_tube_2x2_11ga",
             "quantity": 4, "cut_type": "square"},
        ]
        result = calculate_labor_hours("furniture_table", cut_list, {"finish": "paint"})
        # 4 TYPE A × 5 min = 20 min = 0.33 hr, minimum 1.0
        assert result["fit_tack"] == 1.0, \
            "No pickets — fit_tack should be minimum 1.0, got %.2f" % result["fit_tack"]


# ---- Paint hours ----

class TestPaintHours:
    """Tests for sqft-based paint coating_application formula."""

    def test_paint_uses_sqft_formula(self):
        """Paint coating_application should use sqft-based formula, minimum 2.0 hrs."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"description": "Gate frame", "profile": "sq_tube_2x2_11ga",
             "length_inches": 120, "quantity": 4, "cut_type": "square"},
        ]
        result = calculate_labor_hours("cantilever_gate", cut_list, {"finish": "paint"})
        assert result["coating_application"] >= 2.0, \
            "Paint should be minimum 2.0 hrs, got %.2f" % result["coating_application"]

    def test_paint_min_2hrs(self):
        """Even small jobs should have minimum 2.0 hrs for paint."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"description": "Small bracket", "profile": "flat_bar_1x0.25",
             "length_inches": 12, "quantity": 2, "cut_type": "square"},
        ]
        result = calculate_labor_hours("custom_fab", cut_list, {"finish": "paint"})
        assert result["coating_application"] >= 2.0, \
            "Paint should be minimum 2.0 hrs, got %.2f" % result["coating_application"]


# ---- Banned terms ----

class TestBannedTerms:
    """Tests for banned terms in AI cut list prompts."""

    def test_hand_file_banned(self):
        """'hand file' should be in BANNED_TERM_REPLACEMENTS."""
        from backend.calculators.ai_cut_list import BANNED_TERM_REPLACEMENTS
        assert "hand file" in BANNED_TERM_REPLACEMENTS
        assert "flap disc" in BANNED_TERM_REPLACEMENTS["hand file"].lower()

    def test_mill_scale_in_rules(self):
        """Build instructions prompt should include mill scale rule."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        prompt = gen._build_instructions_prompt(
            "cantilever_gate",
            {"description": "10ft gate", "finish": "paint"},
            [{"description": "frame", "quantity": 1, "length_inches": 120, "cut_type": "square"}],
        )
        assert "MILL SCALE" in prompt or "mill scale" in prompt


# ---- Weights ----

class TestBarWeights:
    """Tests for bar weight constants in STOCK_WEIGHTS."""

    def test_sq_bar_in_stock_weights(self):
        """Square bar profiles should be in STOCK_WEIGHTS."""
        from backend.weights import STOCK_WEIGHTS
        assert "sq_bar_0.75" in STOCK_WEIGHTS
        assert STOCK_WEIGHTS["sq_bar_0.75"] > 0
        assert "sq_bar_0.5" in STOCK_WEIGHTS
        assert "sq_bar_1.0" in STOCK_WEIGHTS

    def test_round_bar_in_stock_weights(self):
        """Round bar profiles should be in STOCK_WEIGHTS."""
        from backend.weights import STOCK_WEIGHTS
        assert "round_bar_0.625" in STOCK_WEIGHTS
        assert STOCK_WEIGHTS["round_bar_0.625"] > 0
        assert "round_bar_0.5" in STOCK_WEIGHTS
        assert "round_bar_0.75" in STOCK_WEIGHTS


# ---- Post dimensions ----

class TestPostDimensions:
    """Tests for post dimensions in AI context."""

    def test_post_dims_in_context(self):
        """AI context should include computed post dimensions for cantilever gate."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        prompt = gen._build_prompt("cantilever_gate", {
            "description": "10ft sliding gate with pickets",
            "height": "6",
            "clear_width": "10",
            "post_concrete": "Yes",
        })
        assert "POST DIMENSIONS" in prompt

    def test_post_length_for_10ft_gate(self):
        """10ft gate with 6ft height: post = 74in above + 42in embed = 116in."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        prompt = gen._build_prompt("cantilever_gate", {
            "description": "10ft sliding gate",
            "height": "6",
            "clear_width": "10",
            "post_concrete": "Yes",
        })
        # 6ft = 72in, +2 above grade = 74in, +42 embed = 116in
        assert "116" in prompt, "Post total should be 116in (74+42)"

    def test_field_welding_context(self):
        """Installation jobs should include field welding context."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        prompt = gen._build_prompt("cantilever_gate", {
            "description": "10ft gate",
            "height": "6",
            "installation": "Full installation (gate + posts + concrete)",
        })
        assert "FIELD WELDING" in prompt
        assert "Stick" in prompt or "SMAW" in prompt
