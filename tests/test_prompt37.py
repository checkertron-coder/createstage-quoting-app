"""
Tests for Prompt 37: Trust Opus — Remove Bad Rules, Fix Grind Bug, Fix Finish Detection.

Covers:
- Aluminum jobs never get vinegar bath / mill scale removal in build instructions
- Grind hours for sign/panel jobs use surface-area formula (not per-joint furniture grind)
- Finishing section correctly labels clear coat
- Mild steel + clear coat still gets mill scale removal (vinegar bath correct)
- Standard painted/powder coat jobs are unaffected
"""

import json
import pytest


# =====================================================================
# Fix 1: Aluminum jobs — no vinegar bath in build instructions prompt
# =====================================================================

class TestAluminumNoVinegarBath:
    """Aluminum jobs should never get vinegar bath / mill scale instructions."""

    def test_aluminum_led_sign_no_mill_scale(self):
        """Aluminum LED sign with clear coat → FINISH CONTEXT should not require mill scale removal."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        fields = {
            "description": "Two channel letter signs, aluminum, clear coat finish",
            "finish": "clear coat",
            "material": "aluminum 6061",
        }
        cut_list = [
            {"description": "Sign panel", "quantity": 2, "length_inches": 128,
             "cut_type": "square", "profile": "sheet_11ga"},
        ]
        prompt = gen._build_instructions_prompt("led_sign_custom", fields, cut_list)
        # FINISH CONTEXT should say no mill scale removal needed
        assert "no mill scale removal needed" in prompt.lower()
        # RULES should not instruct vinegar bath as step 1
        assert 'step 1 is always "submerge' not in prompt.lower()
        # FINISH CONTEXT should NOT say "requires mill scale removal"
        assert "requires mill scale removal" not in prompt.lower()

    def test_aluminum_6061_suppresses_mill_scale(self):
        """6061 alloy reference suppresses mill scale in FINISH CONTEXT."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        fields = {
            "description": "Custom sign frame, 6061 aluminum, brushed finish",
            "finish": "brushed",
        }
        cut_list = [{"description": "Frame", "quantity": 4, "length_inches": 48,
                     "cut_type": "square", "profile": "sq_tube_2x2_11ga"}]
        prompt = gen._build_instructions_prompt("sign_frame", fields, cut_list)
        assert "no mill scale removal needed" in prompt.lower()
        assert 'step 1 is always "submerge' not in prompt.lower()

    def test_aluminum_5052_suppresses_mill_scale(self):
        """5052 alloy reference suppresses mill scale in FINISH CONTEXT."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        fields = {
            "description": "Sheet metal enclosure, 5052 aluminum",
            "finish": "raw",
        }
        cut_list = [{"description": "Panel", "quantity": 6, "length_inches": 24,
                     "cut_type": "square", "profile": "sheet_14ga"}]
        prompt = gen._build_instructions_prompt("utility_enclosure", fields, cut_list)
        assert "no mill scale removal needed" in prompt.lower()
        assert 'step 1 is always "submerge' not in prompt.lower()


# =====================================================================
# Fix 1b: Mild steel + clear coat — vinegar bath SHOULD survive
# =====================================================================

class TestMildSteelClearCoatStillGetsVinegarBath:
    """Mild steel with clear coat/raw finish should still get mill scale removal."""

    def test_mild_steel_clear_coat_gets_vinegar_bath(self):
        """Mild steel ornamental fence + clear coat → vinegar bath IS correct."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        fields = {
            "description": "Ornamental flat bar fence, mild steel, clear coat finish",
            "finish": "clear coat",
        }
        cut_list = [
            {"description": "Top rail", "quantity": 4, "length_inches": 96,
             "cut_type": "square", "profile": "sq_tube_2x2_11ga"},
            {"description": "Flat bar picket", "quantity": 40, "length_inches": 42,
             "cut_type": "square", "profile": "flat_bar_1x0.125"},
        ]
        prompt = gen._build_instructions_prompt("ornamental_fence", fields, cut_list)
        # Mild steel + bare metal finish = vinegar bath is correct
        assert "vinegar bath" in prompt.lower() or "mill scale" in prompt.lower()

    def test_mild_steel_raw_finish_gets_vinegar_bath(self):
        """Mild steel table + raw finish → vinegar bath in prompt."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        fields = {
            "description": "Steel dining table, raw steel finish with wax",
            "finish": "raw",
        }
        cut_list = [
            {"description": "Leg", "quantity": 4, "length_inches": 30,
             "cut_type": "miter_45", "profile": "sq_tube_2x2_11ga"},
        ]
        prompt = gen._build_instructions_prompt("furniture_table", fields, cut_list)
        assert "vinegar bath" in prompt.lower() or "mill scale" in prompt.lower()


# =====================================================================
# Fix 2: Grind hours for sign/panel jobs
# =====================================================================

class TestSignPanelGrindHours:
    """Sign/panel jobs should use surface-area grind formula, not per-joint."""

    def _make_led_sign_cut_list(self):
        """Simulate a two-sign LED project with ~50 pieces."""
        cuts = []
        # Sheet panels (signs)
        cuts.append({"description": "Sign face panel", "quantity": 2,
                     "profile": "sheet_11ga", "length_inches": 128,
                     "cut_type": "square", "weld_process": "tig"})
        cuts.append({"description": "Sign back panel", "quantity": 2,
                     "profile": "sheet_14ga", "length_inches": 128,
                     "cut_type": "square", "weld_process": "mig"})
        cuts.append({"description": "Side return panel", "quantity": 8,
                     "profile": "sheet_14ga", "length_inches": 38,
                     "cut_type": "square", "weld_process": "mig"})
        # Structural frame
        for i in range(5):
            cuts.append({"description": "Frame rail %d" % (i+1), "quantity": 4,
                         "profile": "sq_tube_1x1_14ga", "length_inches": 128,
                         "cut_type": "square", "weld_process": "mig"})
        cuts.append({"description": "Frame cross brace", "quantity": 12,
                     "profile": "sq_tube_1x1_14ga", "length_inches": 38,
                     "cut_type": "square", "weld_process": "mig"})
        return cuts

    def test_led_sign_grind_under_12_hours(self):
        """Two-sign LED project grind should be 6-12 hours, not 33+."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cuts = self._make_led_sign_cut_list()
        fields = {
            "description": "Two channel letter signs, aluminum, clear coat",
            "finish": "clear coat",
            "material": "aluminum",
        }
        result = calculate_labor_hours("led_sign_custom", cuts, fields)
        grind = result["grind_clean"]
        assert grind <= 12.0, "Grind hours %.1f exceeds 12 hour cap for sign job" % grind
        assert grind >= 1.0, "Grind hours %.1f too low for sign job" % grind

    def test_led_sign_custom_uses_panel_grind(self):
        """led_sign_custom job type triggers panel grind path."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cuts = [
            {"description": "Sign panel", "quantity": 2, "profile": "sheet_14ga",
             "length_inches": 72, "cut_type": "square", "weld_process": "mig"},
            {"description": "Frame rail", "quantity": 4, "profile": "sq_tube_1.5x1.5_11ga",
             "length_inches": 72, "cut_type": "miter_45", "weld_process": "mig"},
        ]
        fields = {"finish": "paint", "description": "Custom LED sign"}
        result = calculate_labor_hours("led_sign_custom", cuts, fields)
        assert "panel/sign" in result["_reasoning"]

    def test_sheet_dominant_job_uses_panel_grind(self):
        """Custom fab with >40% sheet pieces triggers panel grind."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cuts = [
            {"description": "Side panel", "quantity": 4, "profile": "sheet_14ga",
             "length_inches": 48, "cut_type": "square", "weld_process": "mig"},
            {"description": "Frame", "quantity": 2, "profile": "sq_tube_1x1_14ga",
             "length_inches": 48, "cut_type": "square", "weld_process": "mig"},
        ]
        # 4 sheet pieces out of 6 total = 67% > 40%
        fields = {"finish": "paint", "description": "Custom enclosure"}
        result = calculate_labor_hours("custom_fab", cuts, fields)
        assert "panel/sign" in result["_reasoning"]

    def test_aluminum_reduces_grind_time(self):
        """Aluminum material applies 0.7x multiplier to grind."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cuts = [
            {"description": "Panel", "quantity": 4, "profile": "sheet_11ga",
             "length_inches": 72, "cut_type": "square", "weld_process": "tig"},
            {"description": "Frame", "quantity": 4, "profile": "sq_tube_1x1_14ga",
             "length_inches": 72, "cut_type": "square", "weld_process": "mig"},
        ]
        steel_result = calculate_labor_hours(
            "led_sign_custom", cuts, {"finish": "paint", "description": "steel sign"})
        alum_result = calculate_labor_hours(
            "led_sign_custom", cuts, {"finish": "paint", "description": "aluminum sign"})
        assert alum_result["grind_clean"] < steel_result["grind_clean"]

    def test_aluminum_no_mill_scale_in_labor(self):
        """Aluminum job should not add 90 min mill scale in labor calc."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cuts = [
            {"description": "Panel", "quantity": 4, "profile": "sheet_11ga",
             "length_inches": 72, "cut_type": "square", "weld_process": "tig"},
        ]
        fields = {"finish": "clear coat", "description": "aluminum sign", "material": "6061"}
        result = calculate_labor_hours("led_sign_custom", cuts, fields)
        assert "mill scale" not in result["_reasoning"]


# =====================================================================
# Fix 2b: Standard jobs unaffected
# =====================================================================

class TestStandardJobsUnaffected:
    """Painted gate, outdoor railing — grind behavior unchanged."""

    def test_painted_gate_uses_outdoor_cleanup(self):
        """Powder coat cantilever gate → outdoor cleanup grind path."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cuts = [
            {"description": "Frame rail", "quantity": 4, "profile": "sq_tube_2x2_11ga",
             "length_inches": 120, "cut_type": "miter_45", "weld_process": "mig"},
            {"description": "Picket", "quantity": 30, "profile": "sq_bar_0.625",
             "length_inches": 70, "cut_type": "square", "weld_process": "mig"},
        ]
        fields = {"finish": "powder coat", "description": "Cantilever gate"}
        result = calculate_labor_hours("cantilever_gate", cuts, fields)
        assert "outdoor cleanup" in result["_reasoning"]

    def test_furniture_table_uses_full_grind(self):
        """Indoor furniture table → full grind path (not panel)."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cuts = [
            {"description": "Leg", "quantity": 4, "profile": "sq_tube_2x2_11ga",
             "length_inches": 30, "cut_type": "miter_45", "weld_process": "tig"},
            {"description": "Stretcher", "quantity": 2, "profile": "sq_tube_1.5x1.5_11ga",
             "length_inches": 48, "cut_type": "square", "weld_process": "tig"},
        ]
        fields = {"finish": "clear coat", "description": "Steel dining table"}
        result = calculate_labor_hours("furniture_table", cuts, fields)
        assert "indoor full grind" in result["_reasoning"]


# =====================================================================
# Fix 3: Finish label in PDF
# =====================================================================

class TestFinishDisplayName:
    """Finishing method display names should be clean and correct."""

    def test_clearcoat_display(self):
        from backend.pdf_generator import _finish_display_name
        assert _finish_display_name("clearcoat") == "Clear Coat"

    def test_clear_coat_display(self):
        from backend.pdf_generator import _finish_display_name
        assert _finish_display_name("clear_coat") == "Clear Coat"

    def test_powder_coat_display(self):
        from backend.pdf_generator import _finish_display_name
        assert _finish_display_name("powder_coat") == "Powder Coat"

    def test_paint_display(self):
        from backend.pdf_generator import _finish_display_name
        assert _finish_display_name("paint") == "Paint"

    def test_galvanized_display(self):
        from backend.pdf_generator import _finish_display_name
        assert _finish_display_name("galvanized") == "Galvanized"

    def test_raw_display(self):
        from backend.pdf_generator import _finish_display_name
        assert _finish_display_name("raw") == "Raw Steel"

    def test_unknown_falls_back_to_title(self):
        from backend.pdf_generator import _finish_display_name
        assert _finish_display_name("custom_patina") == "Custom Patina"


# =====================================================================
# Fix 3b: FinishingBuilder urethane detection
# =====================================================================

class TestFinishingBuilderUrethane:
    """2k urethane and automotive clear → clearcoat method."""

    def test_urethane_maps_to_clearcoat(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("2k urethane") == "clearcoat"

    def test_automotive_clear_maps_to_clearcoat(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("automotive clear") == "clearcoat"

    def test_standard_clear_coat_still_works(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("clear coat") == "clearcoat"
        assert fb._normalize_finish_type("Clear coat (in-house)") == "clearcoat"
