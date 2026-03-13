"""
Tests for Prompt 46 — "Trust Opus on Sheets"

Covers:
- AI cut list prompt includes sheet fields (width_inches, sheet_stock_size, sheets_needed)
- _parse_response reads and validates new sheet fields
- _build_from_ai_cuts passes through sheet data and calculates deterministic laser perimeter
- _aggregate_materials uses Opus's sheet data instead of guessing
- PDF _fmt_sheet_dims reads real sheet sizes
- Non-sheet materials unchanged
"""

import pytest

from backend.calculators.ai_cut_list import AICutListGenerator
from backend.calculators.base import BaseCalculator
from backend.pdf_generator import _fmt_sheet_dims


# ---------------------------------------------------------------------------
# Minimal calculator for testing _build_from_ai_cuts
# ---------------------------------------------------------------------------

class _DummyCalculator(BaseCalculator):
    def calculate(self, fields):
        return {}


# ---------------------------------------------------------------------------
# AI cut list prompt — sheet fields in schema
# ---------------------------------------------------------------------------

class TestPromptSheetFields:
    def test_prompt_includes_width_inches(self):
        gen = AICutListGenerator()
        prompt = gen._build_prompt("led_sign_custom", {
            "description": "Aluminum LED sign cabinet 138x28",
            "material": "aluminum 6061",
        })
        assert "width_inches" in prompt

    def test_prompt_includes_sheet_stock_size(self):
        gen = AICutListGenerator()
        prompt = gen._build_prompt("led_sign_custom", {
            "description": "Aluminum sign",
            "material": "aluminum 6061",
        })
        assert "sheet_stock_size" in prompt

    def test_prompt_includes_sheets_needed(self):
        gen = AICutListGenerator()
        prompt = gen._build_prompt("led_sign_custom", {
            "description": "Aluminum sign",
            "material": "aluminum 6061",
        })
        assert "sheets_needed" in prompt

    def test_prompt_includes_standard_sizes(self):
        gen = AICutListGenerator()
        prompt = gen._build_prompt("led_sign_custom", {
            "description": "Aluminum sign",
        })
        assert "[48,96]" in prompt or "[48, 96]" in prompt


# ---------------------------------------------------------------------------
# _parse_response — sheet field parsing
# ---------------------------------------------------------------------------

class TestParseSheetFields:
    def test_parse_width_inches(self):
        gen = AICutListGenerator()
        response = '''[{
            "description": "Back panel",
            "piece_name": "back_panel",
            "group": "cabinet",
            "material_type": "aluminum_6061",
            "profile": "al_sheet_0.063",
            "length_inches": 138.0,
            "width_inches": 28.0,
            "quantity": 1,
            "cut_type": "square",
            "weld_process": "tig",
            "weld_type": "butt",
            "sheet_stock_size": [48, 144],
            "sheets_needed": 1
        }]'''
        result = gen._parse_response(response)
        assert result is not None
        assert result[0]["width_inches"] == 28.0
        assert result[0]["sheet_stock_size"] == [48, 144]
        assert result[0]["sheets_needed"] == 1

    def test_parse_invalid_stock_size_rejected(self):
        gen = AICutListGenerator()
        response = '''[{
            "description": "Panel",
            "profile": "al_sheet_0.063",
            "length_inches": 48.0,
            "width_inches": 24.0,
            "quantity": 1,
            "sheet_stock_size": [36, 72]
        }]'''
        result = gen._parse_response(response)
        assert result is not None
        # Invalid stock size should be set to None
        assert result[0]["sheet_stock_size"] is None

    def test_parse_seaming_required(self):
        gen = AICutListGenerator()
        response = '''[{
            "description": "Large panel",
            "profile": "al_sheet_0.125",
            "length_inches": 160.0,
            "width_inches": 48.0,
            "quantity": 1,
            "sheet_stock_size": [60, 144],
            "sheets_needed": 1,
            "seaming_required": true
        }]'''
        result = gen._parse_response(response)
        assert result is not None
        assert result[0]["seaming_required"] is True

    def test_parse_non_sheet_no_width(self):
        """Non-sheet items get width_inches=0 and no sheet data."""
        gen = AICutListGenerator()
        response = '''[{
            "description": "Frame rail",
            "profile": "sq_tube_2x2_11ga",
            "length_inches": 96.0,
            "quantity": 4
        }]'''
        result = gen._parse_response(response)
        assert result is not None
        assert result[0]["width_inches"] == 0.0
        assert result[0]["sheet_stock_size"] is None
        assert result[0]["sheets_needed"] == 0

    def test_parse_valid_stock_sizes(self):
        """All 5 standard stock sizes are accepted."""
        gen = AICutListGenerator()
        for size in ([48, 96], [48, 120], [48, 144], [60, 120], [60, 144]):
            response = '''[{
                "description": "Panel",
                "profile": "sheet_14ga",
                "length_inches": 48.0,
                "width_inches": 24.0,
                "quantity": 1,
                "sheet_stock_size": %s,
                "sheets_needed": 1
            }]''' % size
            result = gen._parse_response(response)
            assert result is not None
            assert result[0]["sheet_stock_size"] == size, \
                "Stock size %s should be accepted" % size


# ---------------------------------------------------------------------------
# _build_from_ai_cuts — sheet pass-through + laser perimeter
# ---------------------------------------------------------------------------

class TestBuildFromAiCutsSheets:
    def test_sheet_data_on_material_item(self):
        """Sheet metadata flows through to material items."""
        calc = _DummyCalculator()
        ai_cuts = [{
            "profile": "al_sheet_0.063",
            "length_inches": 138.0,
            "width_inches": 28.0,
            "quantity": 1,
            "material_type": "aluminum_6061",
            "sheet_stock_size": [48, 144],
            "sheets_needed": 1,
        }]
        fields = {"description": "LED sign", "material": "aluminum 6061"}
        result = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])
        items = result["items"]
        sheet_item = [i for i in items if "sheet" in i["profile"]]
        assert len(sheet_item) == 1
        assert sheet_item[0].get("sheet_stock_size") == [48, 144]
        assert sheet_item[0].get("sheets_needed") == 1

    def test_no_auto_laser_injection(self):
        """No auto-laser injection — if Opus didn't include laser, don't add it."""
        calc = _DummyCalculator()
        ai_cuts = [{
            "profile": "al_sheet_0.063",
            "length_inches": 138.0,
            "width_inches": 28.0,
            "quantity": 1,
            "material_type": "aluminum_6061",
            "sheet_stock_size": [48, 144],
            "sheets_needed": 1,
        }]
        fields = {"description": "Aluminum LED sign", "material": "aluminum 6061"}
        result = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])
        hw_descs = [h["description"].lower() for h in result.get("hardware", [])]
        laser_items = [d for d in hw_descs if "laser" in d]
        assert len(laser_items) == 0, \
            "No auto-laser injection — Opus provides laser if needed"

    def test_non_sheet_items_unchanged(self):
        """Tube items don't get sheet metadata."""
        calc = _DummyCalculator()
        ai_cuts = [{
            "profile": "sq_tube_2x2_11ga",
            "length_inches": 96.0,
            "quantity": 4,
            "material_type": "mild_steel",
        }]
        fields = {"description": "Steel gate frame"}
        result = calc._build_from_ai_cuts("cantilever_gate", ai_cuts, fields, [])
        items = result["items"]
        assert len(items) == 1
        assert "sheet_stock_size" not in items[0]
        assert "sheets_needed" not in items[0]

    def test_sheet_pricing_uses_sqft(self):
        """Sheet items use price_per_sqft, not price_per_foot."""
        calc = _DummyCalculator()
        ai_cuts = [{
            "profile": "al_sheet_0.063",
            "length_inches": 48.0,
            "width_inches": 24.0,
            "quantity": 1,
            "material_type": "aluminum_6061",
            "sheet_stock_size": [48, 96],
            "sheets_needed": 1,
        }]
        fields = {"description": "Small sign panel"}
        result = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])
        items = result["items"]
        sheet_item = [i for i in items if "sheet" in i["profile"]]
        assert len(sheet_item) == 1
        # 1 sheet × (48*96/144) sqft × $5.80/sqft = 1 × 32 × 5.80 = $185.60
        assert sheet_item[0]["unit_price"] > 100, \
            "Sheet should be priced by sqft, not $3.50/ft fallback"


# ---------------------------------------------------------------------------
# _aggregate_materials — sheet data from Opus
# ---------------------------------------------------------------------------

class TestAggregateSheets:
    def test_aggregate_reads_sheet_fields(self):
        """Aggregation picks up sheet_stock_size and sheets_needed."""
        from backend.pricing_engine import PricingEngine
        pe = PricingEngine()
        materials = [{
            "profile": "al_sheet_0.063",
            "description": "al_sheet_0.063 — 11.5 ft",
            "material_type": "aluminum_6061",
            "length_inches": 138.0,
            "quantity": 1,
            "unit_price": 185.60,
            "line_total": 185.60,
            "sheet_stock_size": [48, 144],
            "sheets_needed": 1,
        }]
        summary = pe._aggregate_materials(materials)
        sheet = [s for s in summary if "sheet" in s["profile"]]
        assert len(sheet) == 1
        assert sheet[0].get("sheet_size") == [48, 144]
        assert sheet[0].get("sheets_needed") == 1
        # stock_length_ft should be sheet length / 12
        assert sheet[0]["stock_length_ft"] == 12.0

    def test_aggregate_no_sheet_fields_fallback(self):
        """Legacy items without sheet fields still calculate sheets needed."""
        from backend.pricing_engine import PricingEngine
        pe = PricingEngine()
        materials = [{
            "profile": "al_sheet_0.063",
            "description": "al_sheet_0.063 — 11.5 ft",
            "material_type": "aluminum_6061",
            "length_inches": 138.0,
            "quantity": 1,
            "unit_price": 40.0,
            "line_total": 40.0,
        }]
        summary = pe._aggregate_materials(materials)
        sheet = [s for s in summary if "sheet" in s["profile"]]
        assert len(sheet) == 1
        # No Opus sheet data — fallback calculates sheets needed (>= 1)
        assert sheet[0]["sticks_needed"] >= 1
        assert sheet[0].get("sheets_needed", 0) >= 1

    def test_tube_materials_unchanged(self):
        """Tube aggregation unaffected by sheet changes."""
        from backend.pricing_engine import PricingEngine
        pe = PricingEngine()
        materials = [{
            "profile": "sq_tube_2x2_11ga",
            "description": "sq_tube_2x2_11ga — 33.6 ft",
            "material_type": "mild_steel",
            "length_inches": 403.2,
            "quantity": 1,
            "unit_price": 100.0,
            "line_total": 100.0,
        }]
        summary = pe._aggregate_materials(materials)
        tube = [s for s in summary if "sq_tube" in s["profile"]]
        assert len(tube) == 1
        assert tube[0]["sticks_needed"] > 0
        assert tube[0]["stock_length_ft"] == 24  # 24' stock


# ---------------------------------------------------------------------------
# PDF — _fmt_sheet_dims
# ---------------------------------------------------------------------------

class TestFmtSheetDims:
    def test_real_sheet_size(self):
        """Opus sheet_size renders as W'xH'."""
        ms = {"sheet_size": [48, 144], "stock_length_ft": 12}
        result = _fmt_sheet_dims(ms)
        assert "4'" in result
        assert "12'" in result

    def test_seaming_flag(self):
        ms = {"sheet_size": [60, 144], "seaming_required": True}
        result = _fmt_sheet_dims(ms)
        assert "SEAM" in result

    def test_legacy_fallback(self):
        """Without sheet_size, falls back to stock_length_ft guess."""
        ms = {"stock_length_ft": 10}
        result = _fmt_sheet_dims(ms)
        assert "4'x10'" in result

    def test_legacy_8ft(self):
        ms = {"stock_length_ft": 8}
        result = _fmt_sheet_dims(ms)
        assert "4'x8'" in result


# ---------------------------------------------------------------------------
# End-to-end: sheet data flows from cut → aggregate → display
# ---------------------------------------------------------------------------

class TestSheetEndToEnd:
    def test_full_pipeline_sheet_data(self):
        """Sheet data from ai_cuts flows through to materials_summary."""
        from backend.pricing_engine import PricingEngine
        calc = _DummyCalculator()
        ai_cuts = [{
            "profile": "al_sheet_0.063",
            "length_inches": 138.0,
            "width_inches": 28.0,
            "quantity": 1,
            "material_type": "aluminum_6061",
            "sheet_stock_size": [48, 144],
            "sheets_needed": 1,
        }, {
            "profile": "al_sq_tube_1x1_0.125",
            "length_inches": 24.0,
            "quantity": 8,
            "material_type": "aluminum_6061",
        }]
        fields = {"description": "LED sign", "material": "aluminum 6061"}
        mat_list = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])

        pe = PricingEngine()
        summary = pe._aggregate_materials(mat_list["items"])

        sheet_rows = [s for s in summary if "sheet" in s["profile"]]
        tube_rows = [s for s in summary if "tube" in s["profile"]]

        assert len(sheet_rows) == 1
        assert sheet_rows[0].get("sheet_size") == [48, 144]
        assert sheet_rows[0].get("sheets_needed") == 1
        assert sheet_rows[0]["stock_length_ft"] == 12.0

        # Tube should be normal aggregation
        assert len(tube_rows) == 1
        assert "sheet_size" not in tube_rows[0]
