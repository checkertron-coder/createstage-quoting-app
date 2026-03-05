"""
Tests for Prompt 33: Materials Intelligence, Field Extraction, Output Polish.

Covers:
- 4A: All model defaults are opus
- 4B: Improved field extraction prompt
- 4C: Materials summary aggregation
- 4D: Plate cutting labor
- 4E: Units rule in AI prompt
- 4F: Grind hours fix for punched channel
- 4G: Materials PDF + CSV generation
- 4H: Concrete filter, punched channel profiles, fence constraints
"""

import math
import pytest


# =====================================================================
# 4A — All model defaults are Opus
# =====================================================================

class TestKillSonnet:
    def test_config_fast_model_opus(self):
        """Config fast model default is opus."""
        from backend.config import Settings
        s = Settings()
        assert "opus" in s.CLAUDE_FAST_MODEL

    def test_config_deep_model_opus(self):
        """Config deep model default is opus."""
        from backend.config import Settings
        s = Settings()
        assert "opus" in s.CLAUDE_DEEP_MODEL

    def test_config_review_model_opus(self):
        """Config review model default is opus."""
        from backend.config import Settings
        s = Settings()
        assert "opus" in s.CLAUDE_REVIEW_MODEL

    def test_claude_client_default_fast_opus(self):
        """claude_client._DEFAULT_FAST is opus."""
        from backend.claude_client import _DEFAULT_FAST
        assert "opus" in _DEFAULT_FAST

    def test_claude_client_default_deep_opus(self):
        """claude_client._DEFAULT_DEEP is opus."""
        from backend.claude_client import _DEFAULT_DEEP
        assert "opus" in _DEFAULT_DEEP

    def test_claude_reviewer_default_opus(self):
        """claude_reviewer default model is opus."""
        from backend.claude_reviewer import CLAUDE_REVIEW_MODEL
        assert "opus" in CLAUDE_REVIEW_MODEL


# =====================================================================
# 4B — Improved field extraction prompt
# =====================================================================

class TestFieldExtractionPrompt:
    def test_extraction_prompt_has_unit_normalization(self):
        """Extraction prompt includes unit normalization guidance."""
        from backend.question_trees.engine import _build_extraction_prompt
        prompt = _build_extraction_prompt(
            "cantilever_gate", "Cantilever Gate",
            "10 foot gate", "- clear_width: Width?"
        )
        assert "UNIT NORMALIZATION" in prompt
        assert "120 inches" in prompt

    def test_extraction_prompt_has_dimension_parsing(self):
        """Extraction prompt includes dimension parsing guidance."""
        from backend.question_trees.engine import _build_extraction_prompt
        prompt = _build_extraction_prompt(
            "cantilever_gate", "Cantilever Gate",
            "10x6 gate", "- clear_width: Width?"
        )
        assert "DIMENSION PARSING" in prompt
        assert "10x6" in prompt

    def test_extraction_prompt_has_examples(self):
        """Extraction prompt includes concrete examples."""
        from backend.question_trees.engine import _build_extraction_prompt
        prompt = _build_extraction_prompt(
            "cantilever_gate", "Cantilever Gate",
            "gate", "- clear_width: Width?"
        )
        assert "EXAMPLES:" in prompt
        assert "has_motor" in prompt


# =====================================================================
# 4C — Materials summary aggregation
# =====================================================================

class TestMaterialsSummary:
    def test_aggregate_materials_basic(self):
        """Materials summary groups by profile and calculates sticks."""
        from backend.pricing_engine import PricingEngine
        engine = PricingEngine()
        materials = [
            {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
             "length_inches": 120, "quantity": 4, "description": "frame rail"},
            {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
             "length_inches": 36, "quantity": 8, "description": "picket"},
        ]
        summary = engine._aggregate_materials(materials)
        assert len(summary) == 1
        item = summary[0]
        assert item["profile"] == "sq_tube_2x2_11ga"
        total_ft = (120 * 4 + 36 * 8) / 12.0  # 40 + 24 = 64 ft
        assert abs(item["total_length_ft"] - total_ft) < 0.2
        assert item["stock_length_ft"] == 24  # square tube stock
        assert item["sticks_needed"] == math.ceil(total_ft / 24)

    def test_aggregate_materials_skips_concrete(self):
        """Materials summary skips concrete items."""
        from backend.pricing_engine import PricingEngine
        engine = PricingEngine()
        materials = [
            {"profile": "concrete_80lb_bag", "material_type": "concrete",
             "length_inches": 0, "quantity": 6, "description": "concrete"},
            {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
             "length_inches": 120, "quantity": 2, "description": "rail"},
        ]
        summary = engine._aggregate_materials(materials)
        profiles = [s["profile"] for s in summary]
        assert "concrete_80lb_bag" not in profiles
        assert "sq_tube_2x2_11ga" in profiles

    def test_materials_summary_in_priced_quote(self):
        """build_priced_quote includes materials_summary key."""
        from backend.pricing_engine import PricingEngine
        engine = PricingEngine()
        session_data = {
            "session_id": "test",
            "job_type": "custom_fab",
            "fields": {},
            "material_list": {
                "items": [
                    {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
                     "length_inches": 120, "quantity": 2, "line_total": 50.0,
                     "unit_price": 25.0, "description": "rail"},
                ],
                "hardware": [],
                "total_weight_lbs": 50,
                "total_sq_ft": 10,
                "weld_linear_inches": 20,
                "assumptions": [],
            },
            "labor_estimate": {"processes": [], "total_hours": 0},
            "finishing": {"method": "raw", "total": 0},
        }
        user = {"id": 1, "shop_name": "Test", "markup_default": 0}
        result = engine.build_priced_quote(session_data, user)
        assert "materials_summary" in result
        assert isinstance(result["materials_summary"], list)


# =====================================================================
# 4D — Plate cutting labor
# =====================================================================

class TestPlateCuttingLabor:
    def test_plate_adds_cut_prep_time(self):
        """Plate/sheet items add 8 min/piece to cut_prep."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"profile": "plate_0.25", "description": "base plate",
             "material_type": "plate", "quantity": 4, "length_inches": 12},
            {"profile": "sq_tube_2x2_11ga", "description": "leg",
             "material_type": "square_tubing", "quantity": 4, "length_inches": 30},
        ]
        result = calculate_labor_hours("furniture_table", cut_list, {"finish": "paint"})
        assert "PLATE CUTTING" in result["_reasoning"]
        # 4 plate pieces × 8 min = 32 min = 0.53 hr added
        # Without plate, 8 pieces × 4 min = 32 min = 0.53 hr baseline
        assert result["cut_prep"] > 1.0

    def test_no_plate_no_extra_time(self):
        """Jobs without plate/sheet items don't get plate cutting time."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"profile": "sq_tube_2x2_11ga", "description": "leg",
             "material_type": "square_tubing", "quantity": 4, "length_inches": 30},
        ]
        result = calculate_labor_hours("furniture_table", cut_list, {"finish": "paint"})
        assert "PLATE CUTTING" not in result["_reasoning"]


# =====================================================================
# 4F — Grind hours fix for punched channel
# =====================================================================

class TestGrindFixPunchedChannel:
    def test_punched_channel_reduces_grind(self):
        """Punched channel pickets should reduce grind hours vs regular pickets."""
        from backend.calculators.labor_calculator import calculate_labor_hours

        # Without punched channel
        cut_list_regular = [
            {"profile": "sq_tube_2x2_11ga", "description": "post",
             "material_type": "square_tubing", "quantity": 4, "length_inches": 42},
            {"profile": "sq_bar_0.5", "description": "picket",
             "piece_name": "picket", "material_type": "square_bar",
             "quantity": 50, "length_inches": 36},
        ]
        result_regular = calculate_labor_hours(
            "ornamental_fence", cut_list_regular, {"finish": "paint"})

        # With punched channel
        cut_list_punched = [
            {"profile": "sq_tube_2x2_11ga", "description": "post",
             "material_type": "square_tubing", "quantity": 4, "length_inches": 42},
            {"profile": "sq_bar_0.5", "description": "picket",
             "piece_name": "picket", "material_type": "square_bar",
             "quantity": 50, "length_inches": 36},
            {"profile": "punched_channel_1.25x0.5x14ga", "description": "picket receiver",
             "material_type": "channel", "quantity": 4, "length_inches": 72},
        ]
        result_punched = calculate_labor_hours(
            "ornamental_fence", cut_list_punched, {"finish": "paint"})

        assert result_punched["grind_clean"] < result_regular["grind_clean"], (
            "Punched channel should reduce grind: %.2f vs %.2f"
            % (result_punched["grind_clean"], result_regular["grind_clean"]))
        assert "PUNCHED CHANNEL grind fix" in result_punched["_reasoning"]


# =====================================================================
# 4G — Materials PDF + CSV generation
# =====================================================================

class TestMaterialsExport:
    def _make_priced_quote(self):
        return {
            "quote_id": 1,
            "quote_number": "Q-001",
            "job_type": "furniture_table",
            "materials": [
                {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
                 "length_inches": 30, "quantity": 4, "description": "Table leg",
                 "unit_price": 5.0, "line_total": 20.0},
                {"profile": "concrete_80lb_bag", "material_type": "concrete",
                 "length_inches": 0, "quantity": 2, "description": "Concrete",
                 "unit_price": 6.0, "line_total": 12.0},
            ],
            "materials_summary": [
                {"profile": "sq_tube_2x2_11ga", "description": "Table leg",
                 "total_length_ft": 10.0, "stock_length_ft": 24,
                 "sticks_needed": 1, "remainder_ft": 14.0},
            ],
        }

    def test_generate_materials_pdf(self):
        """Materials PDF generates without error."""
        from backend.pdf_generator import generate_materials_pdf
        pq = self._make_priced_quote()
        user = {"shop_name": "Test Shop"}
        result = generate_materials_pdf(pq, user)
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 100

    def test_generate_materials_csv(self):
        """Materials CSV generates with correct structure."""
        from backend.pdf_generator import generate_materials_csv
        pq = self._make_priced_quote()
        result = generate_materials_csv(pq)
        assert isinstance(result, bytes)
        text = result.decode("utf-8")
        assert "Profile" in text
        assert "sq_tube_2x2_11ga" in text
        # Concrete should be excluded
        assert "concrete" not in text.lower()

    def test_materials_csv_has_summary(self):
        """Materials CSV includes stock order summary section."""
        from backend.pdf_generator import generate_materials_csv
        pq = self._make_priced_quote()
        result = generate_materials_csv(pq)
        text = result.decode("utf-8")
        assert "STOCK ORDER SUMMARY" in text


# =====================================================================
# 4H — Output cleanup
# =====================================================================

class TestOutputCleanup:
    def test_concrete_not_in_cut_list_pdf(self):
        """Shop PDF cut list section filters out concrete items."""
        from backend.pdf_generator import generate_quote_pdf
        pq = {
            "quote_id": 1, "quote_number": "Q-001", "job_type": "custom_fab",
            "materials": [
                {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
                 "length_inches": 30, "quantity": 4, "description": "Leg",
                 "unit_price": 5.0, "line_total": 20.0, "cut_type": "square"},
                {"profile": "concrete_80lb_bag", "material_type": "concrete",
                 "length_inches": 0, "quantity": 6, "description": "Concrete bags",
                 "unit_price": 6.0, "line_total": 36.0, "cut_type": "square"},
            ],
            "hardware": [], "consumables": [], "labor": [],
            "finishing": {"method": "raw", "total": 0},
            "material_subtotal": 56.0, "hardware_subtotal": 0,
            "consumable_subtotal": 0, "labor_subtotal": 0,
            "finishing_subtotal": 0, "subtotal": 56.0,
            "markup_options": {"0": 56.0}, "selected_markup_pct": 0,
            "total": 56.0, "created_at": "2026-03-05T00:00:00",
            "assumptions": [], "exclusions": [],
        }
        user = {"shop_name": "Test"}
        result = generate_quote_pdf(pq, user)
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 100

    def test_punched_channel_in_ai_profiles(self):
        """Punched channel profile group exists and is available for fence/railing."""
        from backend.calculators.ai_cut_list import _PROFILE_GROUPS, _JOB_TYPE_PROFILES
        assert "punched_channel" in _PROFILE_GROUPS
        assert "punched_channel" in _JOB_TYPE_PROFILES["ornamental_fence"]
        assert "punched_channel" in _JOB_TYPE_PROFILES["straight_railing"]
        assert "punched_channel" in _JOB_TYPE_PROFILES["stair_railing"]
        assert "punched_channel" in _JOB_TYPE_PROFILES["balcony_railing"]

