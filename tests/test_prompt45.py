"""
Tests for Prompt 45 — "The Finish Line"

Covers:
- Fix A: _normalize_finish_type() check order — brushed before raw
- Fix B+C: Finish field extraction bypass — no fuzzy matching for finish
- Fix D: Frontend _recalcTotals() includes shop_stock_subtotal (structural only)
"""

import pytest

from backend.finishing import FinishingBuilder


# ---------------------------------------------------------------------------
# Fix A: _normalize_finish_type() check order
# ---------------------------------------------------------------------------

class TestFinishNormalizeOrder:
    """Brushed/polished/mirror must match BEFORE the raw block."""

    def test_brushed_no_coating(self):
        """'Brushed stainless (no coating)' → brushed, NOT raw."""
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("Brushed stainless (no coating)") == "brushed"

    def test_brushed_plain(self):
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("Brushed finish") == "brushed"

    def test_satin_no_coating(self):
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("Satin (no coating)") == "brushed"

    def test_polished_mirror(self):
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("Mirror polish") == "brushed"

    def test_raw_still_works(self):
        """Plain raw inputs still normalize to raw."""
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("Raw steel") == "raw"
        assert fb._normalize_finish_type("No finish") == "raw"
        assert fb._normalize_finish_type("Mill finish") == "raw"
        assert fb._normalize_finish_type("Not sure — recommend based on use") == "raw"

    def test_clearcoat_before_raw(self):
        """Clear coat must match clearcoat, not be dropped."""
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("Clear coat") == "clearcoat"
        assert fb._normalize_finish_type("Permalac clear") == "clearcoat"

    def test_powder_coat_unchanged(self):
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("Powder coat (most common)") == "powder_coat"

    def test_paint_unchanged(self):
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("Paint (primer + topcoat)") == "paint"


# ---------------------------------------------------------------------------
# Fix B+C: Finish field extraction bypass
# ---------------------------------------------------------------------------

class TestFinishExtractionBypass:
    """Finish field must NOT go through fuzzy _match_option()."""

    def test_clear_coat_not_matched_to_powder(self):
        """'clear coat' must NOT fuzzy-match to 'Powder coat (most common)'."""
        from backend.question_trees.engine import _normalize_extracted_fields

        questions = [
            {
                "id": "finish",
                "type": "choice",
                "options": [
                    "Raw steel (no finish)",
                    "Clear coat / lacquer",
                    "Paint (primer + topcoat)",
                    "Powder coat (most common)",
                ],
            }
        ]
        extracted = {"finish": "clear coat"}
        result = _normalize_extracted_fields(extracted, questions)
        # Should keep raw value "clear coat", which _normalize_finish_type
        # will correctly map to "clearcoat"
        assert "finish" in result
        val = result["finish"].lower()
        assert "powder" not in val, "clear coat must NOT match powder coat"

    def test_finish_field_preserves_raw_value(self):
        """Finish field keeps the extracted value verbatim."""
        from backend.question_trees.engine import _normalize_extracted_fields

        questions = [
            {
                "id": "finish",
                "type": "choice",
                "options": ["Raw", "Paint", "Powder coat"],
            }
        ]
        extracted = {"finish": "brushed stainless no coating"}
        result = _normalize_extracted_fields(extracted, questions)
        assert result["finish"] == "brushed stainless no coating"

    def test_non_finish_fields_still_fuzzy_match(self):
        """Other choice fields still go through _match_option()."""
        from backend.question_trees.engine import _normalize_extracted_fields

        questions = [
            {
                "id": "material",
                "type": "choice",
                "options": ["Mild steel", "Stainless 304", "Aluminum 6061"],
            }
        ]
        extracted = {"material": "mild steel"}
        result = _normalize_extracted_fields(extracted, questions)
        assert result["material"] == "Mild steel"  # case-normalized


# ---------------------------------------------------------------------------
# Fix A end-to-end: FinishingBuilder.build() with brushed input
# ---------------------------------------------------------------------------

class TestBrushedEndToEnd:
    """Brushed finish must produce method='brushed' through full build()."""

    def test_brushed_no_coating_build(self):
        fb = FinishingBuilder()
        result = fb.build("Brushed stainless (no coating)", 50.0, [])
        assert result["method"] == "brushed"
        assert result["materials_cost"] == 0.0
        assert result["outsource_cost"] == 0.0

    def test_clear_coat_build(self):
        fb = FinishingBuilder()
        result = fb.build("Clear coat", 50.0, [])
        assert result["method"] == "clearcoat"
        assert result["materials_cost"] > 0


# ---------------------------------------------------------------------------
# Fix D: shop_stock_subtotal in pricing engine subtotal
# ---------------------------------------------------------------------------

class TestShopStockInSubtotal:
    """PricingEngine subtotal must include shop_stock_subtotal."""

    def test_subtotal_includes_shop_stock(self):
        from backend.pricing_engine import PricingEngine

        pe = PricingEngine()
        session_data = {
            "session_id": "test-45-shopstock",
            "job_type": "cantilever_gate",
            "fields": {
                "description": "Steel cantilever gate 20ft",
                "finish": "raw",
            },
            "material_list": {
                "items": [],
                "hardware": [],
                "weld_linear_inches": 500,
                "total_sq_ft": 100,
                "assumptions": [],
            },
            "labor_estimate": {"processes": [], "total_hours": 0},
            "finishing": {"method": "raw", "total": 0},
        }
        user = {"id": 1, "shop_name": "Test Shop", "markup_default": 0}
        result = pe.build_priced_quote(session_data, user)

        # Subtotal must equal sum of all parts including shop_stock
        expected = (
            result.get("material_subtotal", 0) +
            result.get("hardware_subtotal", 0) +
            result.get("consumable_subtotal", 0) +
            result.get("shop_stock_subtotal", 0) +
            result.get("labor_subtotal", 0) +
            result.get("finishing_subtotal", 0)
        )
        assert abs(result["subtotal"] - expected) < 0.02, \
            "subtotal should be sum of all parts incl. shop_stock_subtotal"
