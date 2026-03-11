"""
Tests for Prompt 34: Labor Reality Check & Shop PDF Materials.

Covers:
- AC-1: Batch cutting reduces cut_prep dramatically for identical pieces
- AC-2: Outdoor painted grind uses flat cleanup, indoor keeps per-joint
- AC-3: Materials aggregation includes weight, cost, plates, concrete
"""

import math
import pytest


# =====================================================================
# AC-1 — Batch cutting logic
# =====================================================================

class TestBatchCutting:
    def _large_outdoor_cut_list(self):
        """Simulate CS-2026-0044 style: 127 pickets + structural frame."""
        items = [
            # Frame members — all different lengths
            {"profile": "sq_tube_2x2_11ga", "description": "top rail",
             "material_type": "square_tubing", "quantity": 2, "length_inches": 216,
             "cut_type": "miter_45"},
            {"profile": "sq_tube_2x2_11ga", "description": "bottom rail",
             "material_type": "square_tubing", "quantity": 2, "length_inches": 216,
             "cut_type": "square"},
            {"profile": "sq_tube_2x2_11ga", "description": "stile",
             "material_type": "square_tubing", "quantity": 4, "length_inches": 70,
             "cut_type": "square"},
            {"profile": "sq_tube_2x2_11ga", "description": "mid rail",
             "material_type": "square_tubing", "quantity": 2, "length_inches": 108,
             "cut_type": "square"},
            {"profile": "sq_tube_4x4_11ga", "description": "post",
             "material_type": "square_tubing", "quantity": 3, "length_inches": 126,
             "cut_type": "square"},
            # 127 identical pickets — THIS is what should batch
            {"profile": "sq_bar_0.5", "description": "picket",
             "piece_name": "picket", "material_type": "square_bar",
             "quantity": 127, "length_inches": 70, "cut_type": "square"},
        ]
        return items

    def test_batch_cutting_reduces_cut_prep(self):
        """127 identical pickets should batch — cut_prep drops dramatically."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = self._large_outdoor_cut_list()
        result = calculate_labor_hours("cantilever_gate", cut_list, {"finish": "paint"})
        # Old formula: 140 pieces x 4 min = 560 min = 9.3 hrs
        # Batch formula: ~6 batches, 127 pickets batch = 4 + 126*0.5 = 67 min
        # Total ~130 min = ~2.2 hrs
        assert result["cut_prep"] < 4.0, (
            "Batch cutting should bring cut_prep under 4 hrs, got %.2f" % result["cut_prep"])
        assert "CUT BATCH" in result["_reasoning"]

    def test_batch_cutting_different_pieces_still_get_setup(self):
        """Different pieces each get their own setup time."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"profile": "sq_tube_2x2_11ga", "description": "piece A",
             "material_type": "square_tubing", "quantity": 1, "length_inches": 30,
             "cut_type": "square"},
            {"profile": "sq_tube_2x2_11ga", "description": "piece B",
             "material_type": "square_tubing", "quantity": 1, "length_inches": 48,
             "cut_type": "square"},
            {"profile": "sq_tube_2x2_11ga", "description": "piece C",
             "material_type": "square_tubing", "quantity": 1, "length_inches": 60,
             "cut_type": "miter_45"},
        ]
        result = calculate_labor_hours("furniture_table", cut_list, {"finish": "paint"})
        # 3 different batches: 4 + 4 + 6 = 14 min = 0.23 hr
        assert result["cut_prep"] >= 0.2

    def test_miter_batch_takes_longer(self):
        """Miter cuts get more setup and feed time than square cuts."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        # Need enough pieces to exceed the 1.0 hr floor
        sq_list = [
            {"profile": "sq_tube_2x2_11ga", "description": "rail",
             "material_type": "square_tubing", "quantity": 100,
             "length_inches": 48, "cut_type": "square"},
        ]
        miter_list = [
            {"profile": "sq_tube_2x2_11ga", "description": "rail",
             "material_type": "square_tubing", "quantity": 100,
             "length_inches": 48, "cut_type": "miter_45"},
        ]
        sq_result = calculate_labor_hours("custom_fab", sq_list, {"finish": "paint"})
        miter_result = calculate_labor_hours("custom_fab", miter_list, {"finish": "paint"})
        assert miter_result["cut_prep"] > sq_result["cut_prep"]

    def test_single_piece_still_gets_setup(self):
        """A single piece still gets full setup time."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"profile": "sq_tube_2x2_11ga", "description": "one piece",
             "material_type": "square_tubing", "quantity": 1,
             "length_inches": 48, "cut_type": "square"},
        ]
        result = calculate_labor_hours("custom_fab", cut_list, {"finish": "paint"})
        # 1 batch of 1 piece: 4 min setup = 0.07 hr, but min is 1.0
        assert result["cut_prep"] >= 1.0


# =====================================================================
# AC-2 — Outdoor grind = cleanup pass, indoor = per-joint
# =====================================================================

class TestOutdoorGrindCleanup:
    def test_outdoor_painted_uses_cleanup_formula(self):
        """Outdoor painted job uses flat cleanup, not per-joint grind."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        # 140+ piece outdoor gate with paint finish
        cut_list = [
            {"profile": "sq_tube_2x2_11ga", "description": "rail",
             "material_type": "square_tubing", "quantity": 10,
             "length_inches": 100, "cut_type": "miter_45"},
            {"profile": "sq_bar_0.5", "description": "picket",
             "piece_name": "picket", "material_type": "square_bar",
             "quantity": 127, "length_inches": 70, "cut_type": "square"},
        ]
        result = calculate_labor_hours("cantilever_gate", cut_list, {"finish": "paint"})
        # Old per-joint: (10*2)*2 + (127*2)*1 + 15 = 40 + 254 + 15 = 309 min = 5.15 hr
        # New cleanup: 30 + 10*1 + 127*0.3 + 10*2 = 30 + 10 + 38.1 + 20 = 98.1 min = 1.6 hr
        assert result["grind_clean"] < 3.0, (
            "Outdoor painted grind should be under 3 hrs, got %.2f" % result["grind_clean"])
        assert "outdoor cleanup" in result["_reasoning"]

    def test_indoor_furniture_uses_per_joint_grind(self):
        """Indoor furniture keeps per-joint grind formula."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"profile": "sq_tube_2x2_11ga", "description": "leg",
             "material_type": "square_tubing", "quantity": 4,
             "length_inches": 30, "cut_type": "square"},
            {"profile": "sq_tube_2x2_11ga", "description": "rail",
             "material_type": "square_tubing", "quantity": 4,
             "length_inches": 48, "cut_type": "miter_45"},
        ]
        result = calculate_labor_hours("furniture_table", cut_list, {"finish": "clearcoat"})
        assert "indoor full grind" in result["_reasoning"]

    def test_outdoor_raw_finish_uses_per_joint(self):
        """Outdoor with raw/bare metal finish still uses per-joint (needs real grinding)."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"profile": "sq_tube_2x2_11ga", "description": "rail",
             "material_type": "square_tubing", "quantity": 4,
             "length_inches": 100, "cut_type": "square"},
        ]
        result = calculate_labor_hours("cantilever_gate", cut_list, {"finish": "raw"})
        # Raw finish on outdoor = no coating, uses indoor formula
        assert "indoor full grind" in result["_reasoning"]

    def test_outdoor_painted_vs_indoor_grind_difference(self):
        """Same cut list: outdoor painted should have much less grind than indoor bare metal."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"profile": "sq_tube_2x2_11ga", "description": "frame",
             "material_type": "square_tubing", "quantity": 8,
             "length_inches": 48, "cut_type": "square"},
            {"profile": "sq_bar_0.5", "description": "picket",
             "piece_name": "picket", "material_type": "square_bar",
             "quantity": 50, "length_inches": 36, "cut_type": "square"},
        ]
        outdoor = calculate_labor_hours("ornamental_fence", cut_list, {"finish": "paint"})
        indoor = calculate_labor_hours("furniture_table", cut_list, {"finish": "clearcoat"})
        assert outdoor["grind_clean"] < indoor["grind_clean"], (
            "Outdoor painted %.2f should be less than indoor %.2f"
            % (outdoor["grind_clean"], indoor["grind_clean"]))


# =====================================================================
# AC-3 — Materials aggregation with weight, cost, concrete
# =====================================================================

class TestMaterialsAggregation:
    def test_aggregate_includes_weight(self):
        """Aggregated materials include weight_lbs from STOCK_WEIGHTS.
        Weight is based on stock ordered (sticks × stock_length × lb/ft),
        not just material used, so a distributor sees the ordering weight."""
        from backend.pricing_engine import PricingEngine
        engine = PricingEngine()
        materials = [
            {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
             "length_inches": 120, "quantity": 4, "description": "rail",
             "unit_price": 10.0, "line_total": 40.0},
        ]
        summary = engine._aggregate_materials(materials)
        steel = [s for s in summary if not s.get("is_concrete")]
        assert len(steel) == 1
        assert steel[0]["weight_lbs"] > 0
        # sq_tube_2x2_11ga is 1.951 lb/ft, 40 ft needs 2 sticks @ 24ft = 48ft
        # Weight of stock ordered: 2 × 24 × 1.951 = 93.6 lbs
        assert abs(steel[0]["weight_lbs"] - 93.6) < 2.0

    def test_aggregate_includes_total_cost(self):
        """Aggregated materials include total_cost summed from line_totals."""
        from backend.pricing_engine import PricingEngine
        engine = PricingEngine()
        materials = [
            {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
             "length_inches": 120, "quantity": 2, "description": "rail A",
             "unit_price": 10.0, "line_total": 20.0},
            {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
             "length_inches": 48, "quantity": 4, "description": "rail B",
             "unit_price": 5.0, "line_total": 20.0},
        ]
        summary = engine._aggregate_materials(materials)
        steel = [s for s in summary if s["profile"] == "sq_tube_2x2_11ga"]
        assert len(steel) == 1
        assert steel[0]["total_cost"] == 40.0  # 20 + 20

    def test_aggregate_cost_equals_subtotal(self):
        """Sum of all aggregated costs must equal material subtotal exactly."""
        from backend.pricing_engine import PricingEngine
        engine = PricingEngine()
        materials = [
            {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
             "length_inches": 120, "quantity": 4, "description": "rail",
             "unit_price": 10.0, "line_total": 40.0},
            {"profile": "sq_bar_0.5", "material_type": "square_bar",
             "length_inches": 36, "quantity": 50, "description": "picket",
             "unit_price": 1.5, "line_total": 75.0},
            {"profile": "concrete_80lb_bag", "material_type": "concrete",
             "length_inches": 0, "quantity": 6, "description": "concrete",
             "unit_price": 6.0, "line_total": 36.0},
        ]
        summary = engine._aggregate_materials(materials)
        agg_total = sum(s.get("total_cost", 0) for s in summary)
        material_subtotal = sum(m.get("line_total", 0) for m in materials)
        assert abs(agg_total - material_subtotal) < 0.01, (
            "Aggregated total %.2f != material subtotal %.2f" % (agg_total, material_subtotal))

    def test_plates_show_piece_count(self):
        """Plates/sheets are area-sold — show piece_count and sheets_needed."""
        from backend.pricing_engine import PricingEngine
        engine = PricingEngine()
        materials = [
            {"profile": "plate_0.25", "material_type": "plate",
             "length_inches": 12, "quantity": 4, "description": "base plate",
             "unit_price": 5.0, "line_total": 20.0},
        ]
        summary = engine._aggregate_materials(materials)
        plate = [s for s in summary if "plate" in s["profile"]]
        assert len(plate) == 1
        assert plate[0]["is_area_sold"] is True
        assert plate[0]["piece_count"] == 4
        # Plates now calculate sheets_needed (at least 1 sheet to order)
        assert plate[0]["sticks_needed"] >= 1
        assert plate[0].get("sheets_needed", 0) >= 1

    def test_concrete_separate_entry(self):
        """Concrete gets its own summary entry with is_concrete flag."""
        from backend.pricing_engine import PricingEngine
        engine = PricingEngine()
        materials = [
            {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
             "length_inches": 120, "quantity": 2, "description": "rail",
             "unit_price": 10.0, "line_total": 20.0},
            {"profile": "concrete_80lb_bag", "material_type": "concrete",
             "length_inches": 0, "quantity": 6, "description": "concrete",
             "unit_price": 6.0, "line_total": 36.0},
        ]
        summary = engine._aggregate_materials(materials)
        concrete = [s for s in summary if s.get("is_concrete")]
        assert len(concrete) == 1
        assert concrete[0]["piece_count"] == 6
        assert concrete[0]["total_cost"] == 36.0
        assert concrete[0]["weight_lbs"] == 480.0  # 6 × 80 lbs

    def test_shop_pdf_renders_with_aggregated_materials(self):
        """Shop PDF generates without error using aggregated materials."""
        from backend.pdf_generator import generate_quote_pdf
        pq = {
            "quote_id": 1, "quote_number": "Q-001", "job_type": "cantilever_gate",
            "materials": [
                {"profile": "sq_tube_2x2_11ga", "material_type": "square_tubing",
                 "length_inches": 120, "quantity": 4, "description": "Frame rail",
                 "unit_price": 10.0, "line_total": 40.0, "cut_type": "square"},
                {"profile": "sq_bar_0.5", "material_type": "square_bar",
                 "length_inches": 36, "quantity": 50, "description": "Picket",
                 "unit_price": 1.5, "line_total": 75.0, "cut_type": "square"},
                {"profile": "concrete_80lb_bag", "material_type": "concrete",
                 "length_inches": 0, "quantity": 6, "description": "Concrete",
                 "unit_price": 6.0, "line_total": 36.0, "cut_type": "square"},
            ],
            "materials_summary": [
                {"profile": "sq_tube_2x2_11ga", "description": "Frame rail",
                 "total_length_ft": 40.0, "piece_count": 4, "stock_length_ft": 24,
                 "sticks_needed": 2, "remainder_ft": 8.0, "weight_lbs": 78.0,
                 "total_cost": 40.0, "is_area_sold": False},
                {"profile": "sq_bar_0.5", "description": "Picket",
                 "total_length_ft": 150.0, "piece_count": 50, "stock_length_ft": 20,
                 "sticks_needed": 8, "remainder_ft": 10.0, "weight_lbs": 127.5,
                 "total_cost": 75.0, "is_area_sold": False},
                {"profile": "concrete", "description": "Concrete",
                 "total_length_ft": 0, "piece_count": 6, "stock_length_ft": 0,
                 "sticks_needed": 0, "remainder_ft": 0, "weight_lbs": 480.0,
                 "total_cost": 36.0, "is_area_sold": False, "is_concrete": True},
            ],
            "hardware": [], "consumables": [], "labor": [],
            "finishing": {"method": "paint", "total": 0},
            "material_subtotal": 151.0, "hardware_subtotal": 0,
            "consumable_subtotal": 0, "labor_subtotal": 0,
            "finishing_subtotal": 0, "subtotal": 151.0,
            "markup_options": {"0": 151.0}, "selected_markup_pct": 0,
            "total": 151.0, "created_at": "2026-03-05T00:00:00",
            "assumptions": [], "exclusions": [],
        }
        user = {"shop_name": "Test"}
        result = generate_quote_pdf(pq, user)
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 100


# =====================================================================
# Regression: existing behavior still works
# =====================================================================

class TestRegressions:
    def test_empty_cut_list_defaults(self):
        """Empty cut list still returns valid defaults."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        result = calculate_labor_hours("custom_fab", [], {})
        assert result["cut_prep"] == 1.0
        assert result["grind_clean"] == 0.5

    def test_plate_cutting_still_works(self):
        """Plate cutting labor from Prompt 33 still applies."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"profile": "plate_0.25", "description": "base plate",
             "material_type": "plate", "quantity": 4, "length_inches": 12},
        ]
        result = calculate_labor_hours("furniture_table", cut_list, {"finish": "paint"})
        assert "PLATE CUTTING" in result["_reasoning"]

    def test_punched_channel_grind_fix_still_works(self):
        """Punched channel grind fix from Prompt 33 still fires."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        cut_list = [
            {"profile": "sq_tube_2x2_11ga", "description": "post",
             "material_type": "square_tubing", "quantity": 4, "length_inches": 42},
            {"profile": "sq_bar_0.5", "description": "picket",
             "piece_name": "picket", "material_type": "square_bar",
             "quantity": 50, "length_inches": 36},
            {"profile": "punched_channel_1.25x0.5x14ga", "description": "receiver",
             "material_type": "channel", "quantity": 4, "length_inches": 72},
        ]
        # Use paint finish so outdoor cleanup fires, but punched channel fix should still apply
        result = calculate_labor_hours("ornamental_fence", cut_list, {"finish": "paint"})
        assert "PUNCHED CHANNEL" in result["_reasoning"]
