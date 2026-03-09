"""
Prompt 38 — Aluminum Awareness tests.

Tests aluminum catalog entries, AI prompt injection, consumable material selection,
laser cutting detection, and steel gate regression.
"""

import pytest

from backend.calculators.material_lookup import (
    MaterialLookup, PRICE_PER_FOOT, PRICE_PER_SQFT,
)
from backend.calculators.ai_cut_list import (
    AICutListGenerator, _PROFILE_GROUPS, _JOB_TYPE_PROFILES,
)
from backend.calculators.base import BaseCalculator
from backend.hardware_sourcer import HardwareSourcer


# ---------------------------------------------------------------------------
# Aluminum catalog
# ---------------------------------------------------------------------------

class TestAluminumCatalog:
    def test_aluminum_profiles_exist(self):
        """al_sq_tube, al_sheet entries have prices > 0."""
        ml = MaterialLookup()
        assert ml.get_price_per_foot("al_sq_tube_1x1_0.125") > 0
        assert ml.get_price_per_foot("al_sq_tube_2x2_0.125") > 0
        assert ml.get_price_per_foot("al_flat_bar_1x0.125") > 0
        assert ml.get_price_per_foot("al_angle_2x2x0.125") > 0
        assert ml.get_price_per_foot("al_round_tube_1.5_0.125") > 0
        assert ml.get_price_per_sqft("al_sheet_0.125") > 0
        assert ml.get_price_per_sqft("al_sheet_0.040") > 0

    def test_extract_shape_aluminum(self):
        """_extract_shape handles al_ prefixed profiles."""
        assert MaterialLookup._extract_shape("al_sq_tube_1x1_0.125") == "al_sq_tube"
        assert MaterialLookup._extract_shape("al_flat_bar_2x0.25") == "al_flat_bar"
        assert MaterialLookup._extract_shape("al_sheet_0.125") == "al_sheet"
        assert MaterialLookup._extract_shape("al_angle_1.5x1.5x0.125") == "al_angle"
        assert MaterialLookup._extract_shape("al_round_tube_1.5_0.125") == "al_round_tube"

    def test_steel_profiles_unchanged(self):
        """Steel profiles still work correctly after aluminum additions."""
        ml = MaterialLookup()
        assert ml.get_price_per_foot("sq_tube_2x2_11ga") > 0
        assert MaterialLookup._extract_shape("sq_tube_2x2_11ga") == "sq_tube"
        assert MaterialLookup._extract_shape("flat_bar_1x0.25") == "flat_bar"


# ---------------------------------------------------------------------------
# AI cut list prompt — aluminum context
# ---------------------------------------------------------------------------

class TestAluminumPrompt:
    def test_aluminum_profiles_in_prompt(self):
        """_get_profiles_for_job_type('led_sign_custom') includes al groups."""
        gen = AICutListGenerator()
        profiles = gen._get_profiles_for_job_type("led_sign_custom")
        assert "al_sq_tube" in profiles
        assert "al_sheet" in profiles
        assert "al_flat_bar" in profiles

    def test_material_context_in_prompt(self):
        """Aluminum fields inject MATERIAL CONTEXT block into prompt."""
        gen = AICutListGenerator()
        fields = {
            "description": "Aluminum channel letter sign",
            "material": "aluminum 6061",
        }
        prompt = gen._build_prompt("led_sign_custom", fields)
        assert "MATERIAL CONTEXT" in prompt
        assert "al_*" in prompt or "al_sq_tube" in prompt

    def test_no_material_context_for_steel(self):
        """Steel jobs should NOT have MATERIAL CONTEXT block."""
        gen = AICutListGenerator()
        fields = {
            "description": "Steel cantilever gate 10 ft",
            "material": "mild steel",
        }
        prompt = gen._build_prompt("cantilever_gate", fields)
        assert "MATERIAL CONTEXT" not in prompt


# ---------------------------------------------------------------------------
# Consumables — material-aware
# ---------------------------------------------------------------------------

class TestConsumablesMaterialAware:
    def test_consumables_aluminum_wire(self):
        """material_type='aluminum_6061' produces ER4043 wire."""
        hs = HardwareSourcer()
        items = hs.estimate_consumables(500, 200, "raw", material_type="aluminum_6061")
        wire_items = [i for i in items if "4043" in i["description"] or "ER4043" in i["description"]]
        assert len(wire_items) > 0, "Expected ER4043 wire for aluminum"

    def test_consumables_aluminum_gas(self):
        """material_type='aluminum_6061' produces 100% Argon gas."""
        hs = HardwareSourcer()
        items = hs.estimate_consumables(500, 200, "raw", material_type="aluminum_6061")
        gas_items = [i for i in items if "Argon" in i["description"] and "75/25" not in i["description"]]
        assert len(gas_items) > 0, "Expected 100% Argon for aluminum"

    def test_consumables_steel_unchanged(self):
        """No material_type (default) still produces ER70S-6 wire."""
        hs = HardwareSourcer()
        items = hs.estimate_consumables(500, 200, "raw")
        wire_items = [i for i in items if "ER70S-6" in i["description"]]
        assert len(wire_items) > 0, "Expected ER70S-6 wire for steel"
        gas_items = [i for i in items if "75/25" in i["description"]]
        assert len(gas_items) > 0, "Expected 75/25 Ar/CO2 for steel"


# ---------------------------------------------------------------------------
# Laser cutting
# ---------------------------------------------------------------------------

class _DummyCalculator(BaseCalculator):
    """Minimal calculator for testing _build_from_ai_cuts."""
    def calculate(self, fields):
        return {}


class TestLaserCutting:
    def test_laser_cutting_added_for_aluminum(self):
        """Aluminum + sheet items → hardware includes laser cutting."""
        calc = _DummyCalculator()
        ai_cuts = [
            {"profile": "al_sheet_0.125", "length_inches": 48.0,
             "quantity": 2, "material_type": "aluminum_6061"},
            {"profile": "al_sq_tube_1x1_0.125", "length_inches": 24.0,
             "quantity": 4, "material_type": "aluminum_6061"},
        ]
        fields = {"description": "Aluminum sign cabinet", "material": "aluminum 6061"}
        result = calc._build_from_ai_cuts("led_sign_custom", ai_cuts, fields, [])
        hw_descs = [h["description"].lower() for h in result.get("hardware", [])]
        assert any("laser" in d for d in hw_descs), \
            "Expected laser cutting hardware for aluminum sheet items"

    def test_laser_cutting_not_for_steel(self):
        """Steel sheet items (no aluminum/laser keyword) → no laser cutting."""
        calc = _DummyCalculator()
        ai_cuts = [
            {"profile": "sheet_14ga", "length_inches": 48.0,
             "quantity": 2, "material_type": "mild_steel"},
            {"profile": "sq_tube_2x2_11ga", "length_inches": 36.0,
             "quantity": 4, "material_type": "mild_steel"},
        ]
        fields = {"description": "Steel utility enclosure", "material": "mild steel"}
        result = calc._build_from_ai_cuts("utility_enclosure", ai_cuts, fields, [])
        hw_descs = [h["description"].lower() for h in result.get("hardware", [])]
        assert not any("laser" in d for d in hw_descs), \
            "Steel sheet should NOT get laser cutting hardware"


# ---------------------------------------------------------------------------
# Pricing engine — material type passthrough
# ---------------------------------------------------------------------------

class TestPricingMaterialType:
    def test_pricing_passes_material_type(self):
        """Aluminum description → consumables have ER4043 wire."""
        from backend.pricing_engine import PricingEngine

        engine = PricingEngine()
        session_data = {
            "job_type": "led_sign_custom",
            "fields": {
                "description": "Aluminum channel letter sign 6061",
                "finish": "raw",
            },
            "material_list": {
                "items": [],
                "hardware": [],
                "weld_linear_inches": 300,
                "total_sq_ft": 50,
                "assumptions": [],
            },
            "labor_estimate": {"processes": [], "total_hours": 0},
            "finishing": {"method": "raw", "total": 0},
        }
        user = {"id": 1, "shop_name": "Test Shop", "markup_default": 15}
        result = engine.build_priced_quote(session_data, user)
        wire_descs = [c["description"] for c in result.get("consumables", [])]
        assert any("4043" in d or "ER4043" in d for d in wire_descs), \
            "Expected ER4043 wire in consumables for aluminum job"
