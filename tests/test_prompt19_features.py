"""
Tests for Prompt 19 — Job Description Display, Hardware Pipeline, Inline Material Swap.

20 tests covering:
- Job description in PricedQuote and PDF
- Hardware mapper from question tree fields
- Material alternatives and swap endpoints
- Helper methods
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# 1. Job Description in PricedQuote
# ============================================================

class TestJobDescription:
    """Job description flows from fields to PricedQuote and PDF."""

    def test_job_description_in_priced_quote(self):
        """PricingEngine includes job_description from fields."""
        from backend.pricing_engine import PricingEngine

        engine = PricingEngine()
        session_data = {
            "job_type": "custom_fab",
            "fields": {"description": "Build a custom steel shelf unit 48x72 inches"},
            "material_list": {"items": [], "hardware": [], "weld_linear_inches": 0, "total_sq_ft": 0},
            "labor_estimate": {"processes": []},
            "finishing": {"method": "raw", "total": 0},
        }
        user = {"id": 1, "shop_name": "Test Shop", "markup_default": 15}
        result = engine.build_priced_quote(session_data, user)
        assert result["job_description"] == "Build a custom steel shelf unit 48x72 inches"

    def test_empty_description_handled(self):
        """PricedQuote handles empty description gracefully."""
        from backend.pricing_engine import PricingEngine

        engine = PricingEngine()
        session_data = {
            "job_type": "custom_fab",
            "fields": {},
            "material_list": {"items": [], "hardware": [], "weld_linear_inches": 0, "total_sq_ft": 0},
            "labor_estimate": {"processes": []},
            "finishing": {"method": "raw", "total": 0},
        }
        user = {"id": 1, "shop_name": "Test Shop", "markup_default": 15}
        result = engine.build_priced_quote(session_data, user)
        assert result["job_description"] == ""

    def test_job_description_in_pdf(self):
        """PDF includes job description section when present."""
        from backend.pdf_generator import generate_quote_pdf

        priced_quote = {
            "quote_id": 1,
            "quote_number": "CS-2026-0001",
            "job_type": "straight_railing",
            "job_description": "30 feet of straight railing with picket infill, powder coat black",
            "client_name": "Test Client",
            "materials": [],
            "hardware": [],
            "consumables": [],
            "labor": [],
            "finishing": {"method": "raw", "total": 0},
            "material_subtotal": 0,
            "hardware_subtotal": 0,
            "consumable_subtotal": 0,
            "labor_subtotal": 0,
            "finishing_subtotal": 0,
            "subtotal": 0,
            "markup_options": {"0": 0},
            "selected_markup_pct": 0,
            "total": 0,
            "created_at": "2026-03-01T00:00:00",
            "assumptions": [],
            "exclusions": [],
        }
        user_profile = {"shop_name": "Test Shop"}
        result = generate_quote_pdf(priced_quote, user_profile)
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 500  # Non-trivial PDF


# ============================================================
# 2. Hardware Mapper
# ============================================================

class TestHardwareMapper:
    """Hardware mapper produces correct hardware for various job types."""

    def test_straight_railing_gets_flange(self):
        """Straight railing always gets surface mount flanges."""
        from backend.calculators.hardware_mapper import map_hardware

        hw = map_hardware("straight_railing", {"linear_footage": "20"})
        assert len(hw) >= 1
        descriptions = [h["description"].lower() for h in hw]
        assert any("surface" in d and "mount" in d for d in descriptions)

    def test_swing_gate_maps_hinge(self):
        """Swing gate maps hinge_type field to hinge hardware."""
        from backend.calculators.hardware_mapper import map_hardware

        hw = map_hardware("swing_gate", {
            "hinge_type": "Heavy duty",
            "latch_type": "Gravity",
        })
        descriptions = [h["description"].lower() for h in hw]
        assert any("hinge" in d for d in descriptions)
        assert any("latch" in d or "gravity" in d for d in descriptions)
        # Also has gate_stop from _always
        assert any("gate" in d and "stop" in d for d in descriptions)

    def test_empty_fields_returns_always_items(self):
        """Empty fields still returns _always items."""
        from backend.calculators.hardware_mapper import map_hardware

        hw = map_hardware("cantilever_gate", {})
        assert len(hw) >= 2  # roller_carriage + gate_stop

    def test_unknown_job_type_returns_empty(self):
        """Unknown job type returns empty list."""
        from backend.calculators.hardware_mapper import map_hardware

        hw = map_hardware("nonexistent_type", {"foo": "bar"})
        assert hw == []

    def test_mapper_import_works(self):
        """hardware_mapper is importable from calculators."""
        from backend.calculators.hardware_mapper import map_hardware, HARDWARE_MAP
        assert callable(map_hardware)
        assert "swing_gate" in HARDWARE_MAP

    def test_hardware_fallback_in_make_material_list(self):
        """make_material_list applies hardware fallback when hardware=[] and fields provided."""
        from backend.calculators.straight_railing import StraightRailingCalculator

        calc = StraightRailingCalculator()
        fields = {"linear_footage": "20", "railing_height": "42"}
        result = calc.make_material_list(
            job_type="straight_railing",
            items=[],
            hardware=[],
            total_weight_lbs=0,
            total_sq_ft=0,
            weld_linear_inches=0,
            fields=fields,
        )
        # Should have hardware from mapper (surface_mount_flange)
        assert len(result["hardware"]) >= 1

    def test_bollard_surface_mount_gets_anchors(self):
        """Bollard with surface mount gets anchor bolt set."""
        from backend.calculators.hardware_mapper import map_hardware

        hw = map_hardware("bollard", {"mount_type": "Surface mount"})
        descriptions = [h["description"].lower() for h in hw]
        assert any("anchor" in d for d in descriptions)


# ============================================================
# 3. Material Alternatives
# ============================================================

class TestMaterialAlternatives:
    """Material alternatives returns same-shape profiles."""

    def test_get_alternatives_returns_same_shape(self):
        """get_alternatives returns only profiles in the same shape family."""
        from backend.calculators.material_lookup import MaterialLookup

        lookup = MaterialLookup()
        alts = lookup.get_alternatives("sq_tube_2x2_11ga")
        assert len(alts) >= 2  # There are multiple sq_tube profiles
        for a in alts:
            assert a["profile"].startswith("sq_tube_")
            assert a["profile"] != "sq_tube_2x2_11ga"

    def test_get_alternatives_excludes_self(self):
        """The current profile is not in the alternatives list."""
        from backend.calculators.material_lookup import MaterialLookup

        lookup = MaterialLookup()
        alts = lookup.get_alternatives("sq_tube_2x2_11ga")
        profiles = [a["profile"] for a in alts]
        assert "sq_tube_2x2_11ga" not in profiles

    def test_get_alternatives_sorted_by_price(self):
        """Alternatives are sorted by price ascending."""
        from backend.calculators.material_lookup import MaterialLookup

        lookup = MaterialLookup()
        alts = lookup.get_alternatives("sq_tube_2x2_11ga")
        prices = [a["price"] for a in alts]
        assert prices == sorted(prices)


# ============================================================
# 4. Helper Methods
# ============================================================

class TestHelperMethods:
    """Tests for _extract_shape and _profile_to_description."""

    def test_extract_shape_sq_tube(self):
        """_extract_shape handles sq_tube correctly."""
        from backend.calculators.material_lookup import MaterialLookup

        assert MaterialLookup._extract_shape("sq_tube_2x2_11ga") == "sq_tube"

    def test_extract_shape_flat_bar(self):
        """_extract_shape handles flat_bar correctly."""
        from backend.calculators.material_lookup import MaterialLookup

        assert MaterialLookup._extract_shape("flat_bar_1x0.25") == "flat_bar"

    def test_extract_shape_pipe(self):
        """_extract_shape handles pipe correctly."""
        from backend.calculators.material_lookup import MaterialLookup

        assert MaterialLookup._extract_shape("pipe_4_sch40") == "pipe"

    def test_profile_to_description(self):
        """_profile_to_description generates readable text."""
        from backend.calculators.material_lookup import MaterialLookup

        desc = MaterialLookup._profile_to_description("sq_tube_2x2_11ga")
        assert "Square Tube" in desc
        assert "2x2" in desc


# ============================================================
# 5. Swap Endpoint (integration)
# ============================================================

class TestSwapEndpoint:
    """Swap material endpoint tests via API."""

    def test_swap_material_endpoint_exists(self, client, auth_headers):
        """POST /quotes/{id}/swap-material returns 404 for missing quote (not 405)."""
        resp = client.post("/api/quotes/99999/swap-material",
                           json={"item_index": 0, "new_profile": "sq_tube_1x1_14ga"},
                           headers=auth_headers)
        assert resp.status_code == 404

    def test_material_alternatives_endpoint_exists(self, client, auth_headers):
        """GET /quotes/{id}/material-alternatives returns 404 for missing quote."""
        resp = client.get("/api/quotes/99999/material-alternatives",
                          headers=auth_headers)
        assert resp.status_code == 404

    def test_anchor_bolt_set_in_catalog(self):
        """anchor_bolt_set is in the HARDWARE_CATALOG."""
        from backend.calculators.material_lookup import HARDWARE_CATALOG

        assert "anchor_bolt_set" in HARDWARE_CATALOG
        options = HARDWARE_CATALOG["anchor_bolt_set"]["options"]
        assert len(options) == 3
        prices = [o["price"] for o in options]
        assert min(prices) >= 10
        assert max(prices) <= 25
