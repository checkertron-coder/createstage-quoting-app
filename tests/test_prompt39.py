"""
Tests for Prompt 39 — 'Let Opus Drive'.

AC-1: Opus labor estimation with deterministic fallback
AC-2: Finish label default → "raw" (not "paint")
AC-3: Real sheet dimensions in LED sign calculator
AC-4: Seaming detection when face > 120"
AC-5: Electronics keyword detection for dynamic questions
AC-6: No regressions — existing tests must pass
"""

import json
import math
from unittest.mock import patch, MagicMock

import pytest


# ── AC-1: Opus labor estimation ──────────────────────────────────────────


class TestOpusLaborEstimation:
    """Opus AI estimation with deterministic fallback."""

    def _sample_cut_list(self):
        return [
            {"description": "Frame leg", "profile": "sq_tube_2x2_11ga",
             "length_inches": 30, "quantity": 4, "cut_type": "square",
             "group": "frame", "weld_process": "mig"},
            {"description": "Top rail", "profile": "sq_tube_2x2_11ga",
             "length_inches": 48, "quantity": 2, "cut_type": "square",
             "group": "frame", "weld_process": "mig"},
        ]

    def _sample_fields(self):
        return {
            "finish": "raw",
            "description": "Steel table frame",
        }

    def test_fallback_when_no_api_key(self):
        """Without ANTHROPIC_API_KEY, falls back to deterministic."""
        from backend.calculators.labor_calculator import calculate_labor_hours

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = calculate_labor_hours(
                "furniture_table", self._sample_cut_list(), self._sample_fields()
            )
        # Should get deterministic result
        assert "layout_setup" in result
        assert "full_weld" in result
        assert result["_reasoning"]  # Has reasoning string

    def test_fallback_on_empty_cut_list(self):
        """Empty cut list → uses deterministic defaults."""
        from backend.calculators.labor_calculator import calculate_labor_hours

        result = calculate_labor_hours("custom_fab", [], {"finish": "raw"})
        assert result["layout_setup"] == 1.5
        assert result["full_weld"] == 1.0

    @patch("backend.claude_client.call_deep")
    @patch("backend.claude_client.is_configured", return_value=True)
    def test_opus_success(self, mock_conf, mock_call):
        """Opus returns valid JSON → used directly."""
        from backend.calculators.labor_calculator import calculate_labor_hours

        mock_call.return_value = json.dumps({
            "layout_setup": 1.5,
            "cut_prep": 2.0,
            "fit_tack": 3.0,
            "full_weld": 4.0,
            "grind_clean": 1.5,
            "finish_prep": 0.5,
            "coating_application": 0.0,
            "final_inspection": 0.5,
            "reasoning": "Steel table frame — 6 structural pieces",
        })

        result = calculate_labor_hours(
            "furniture_table", self._sample_cut_list(), self._sample_fields()
        )
        assert result["full_weld"] == 4.0
        assert result["fit_tack"] == 3.0
        assert "Opus AI" in result["_reasoning"]

    @patch("backend.claude_client.call_deep")
    @patch("backend.claude_client.is_configured", return_value=True)
    def test_opus_failure_falls_back(self, mock_conf, mock_call):
        """Opus returns None → falls back to deterministic."""
        from backend.calculators.labor_calculator import calculate_labor_hours

        mock_call.return_value = None

        result = calculate_labor_hours(
            "furniture_table", self._sample_cut_list(), self._sample_fields()
        )
        # Should still work — deterministic fallback
        assert "layout_setup" in result
        assert result["full_weld"] > 0

    @patch("backend.claude_client.call_deep")
    @patch("backend.claude_client.is_configured", return_value=True)
    def test_opus_garbage_json_falls_back(self, mock_conf, mock_call):
        """Opus returns invalid JSON → falls back to deterministic."""
        from backend.calculators.labor_calculator import calculate_labor_hours

        mock_call.return_value = "not valid json {{"

        result = calculate_labor_hours(
            "furniture_table", self._sample_cut_list(), self._sample_fields()
        )
        assert "layout_setup" in result
        assert result["full_weld"] > 0

    @patch("backend.claude_client.call_deep")
    @patch("backend.claude_client.is_configured", return_value=True)
    def test_opus_out_of_range_rejected(self, mock_conf, mock_call):
        """Opus returns unreasonable total → rejected, fallback used."""
        from backend.calculators.labor_calculator import calculate_labor_hours

        # Total < 1 hour
        mock_call.return_value = json.dumps({
            "layout_setup": 0.0, "cut_prep": 0.0, "fit_tack": 0.0,
            "full_weld": 0.0, "grind_clean": 0.0, "finish_prep": 0.0,
            "coating_application": 0.0, "final_inspection": 0.0,
        })

        result = calculate_labor_hours(
            "furniture_table", self._sample_cut_list(), self._sample_fields()
        )
        # Should have used fallback since total was 0
        assert result["full_weld"] > 0

    @patch("backend.claude_client.call_deep")
    @patch("backend.claude_client.is_configured", return_value=True)
    def test_opus_includes_fab_knowledge(self, mock_conf, mock_call):
        """Opus prompt includes FAB_KNOWLEDGE context."""
        from backend.calculators.labor_calculator import _opus_estimate_labor

        mock_call.return_value = json.dumps({
            "layout_setup": 1.5, "cut_prep": 2.0, "fit_tack": 3.0,
            "full_weld": 4.0, "grind_clean": 1.5, "finish_prep": 0.5,
            "coating_application": 0.0, "final_inspection": 0.5,
            "reasoning": "Test",
        })

        _opus_estimate_labor("furniture_table", self._sample_cut_list(), self._sample_fields())

        # Verify the prompt contains domain knowledge
        prompt_arg = mock_call.call_args[0][0]
        assert "DOMAIN KNOWLEDGE" in prompt_arg
        assert "furniture_table" in prompt_arg

    def test_function_signature_unchanged(self):
        """calculate_labor_hours still has the same signature."""
        from backend.calculators.labor_calculator import calculate_labor_hours
        import inspect

        sig = inspect.signature(calculate_labor_hours)
        params = list(sig.parameters.keys())
        assert params == ["job_type", "cut_list", "fields"]


# ── AC-2: Finish label defaults ──────────────────────────────────────────


class TestFinishDefaults:
    """Finish normalization defaults to 'raw' not 'paint'."""

    def test_empty_string_returns_raw(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("") == "raw"

    def test_unknown_string_returns_raw(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("something_unknown") == "raw"

    def test_none_returns_raw(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type(None) == "raw"

    def test_bare_returns_raw(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("bare metal") == "raw"

    def test_permalac_returns_clearcoat(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("permalac") == "clearcoat"

    def test_lacquer_returns_clearcoat(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("lacquer finish") == "clearcoat"

    def test_wax_returns_clearcoat(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("wax") == "clearcoat"

    def test_paint_still_works(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("paint") == "paint"

    def test_powder_coat_still_works(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("powder coat") == "powder_coat"

    def test_galvanized_still_works(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("hot-dip galvanized") == "galvanized"

    def test_raw_still_works(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("raw") == "raw"


# ── AC-3: Real sheet dimensions ──────────────────────────────────────────


class TestRealSheetDimensions:
    """LED sign calculator uses real sheet sizes instead of abstract counts."""

    def test_sheets_needed_small_area(self):
        from backend.calculators.led_sign_custom import _sheets_needed
        count, label = _sheets_needed(10.0)  # 10 sqft
        assert count == 1
        assert "4'" in label  # Should be a standard sheet label

    def test_sheets_needed_large_area(self):
        from backend.calculators.led_sign_custom import _sheets_needed
        # 100 sqft requires multiple 4'x8' (32 sqft) sheets
        count, label = _sheets_needed(100.0)
        assert count >= 3  # At least 3 sheets for 100 sqft

    def test_sheets_needed_exact_one_sheet(self):
        from backend.calculators.led_sign_custom import _sheets_needed
        count, label = _sheets_needed(30.0)  # Just under one 4'x8' (32 sqft)
        assert count == 1

    def test_sheet_label_in_material_description(self):
        """Template calculation includes sheet size label in item description."""
        from backend.calculators.led_sign_custom import LedSignCustomCalculator
        calc = LedSignCustomCalculator()
        result = calc.calculate({
            "sign_type": "Channel letters (individual 3D letters)",
            "dimensions": "8 ft x 2 ft",
            "letter_height": "18",
            "letter_count": "8",
            "material": "Steel",
        })
        # At least one item should have a sheet size label
        descriptions = [item["description"] for item in result["items"]]
        has_sheet_label = any(
            "4'" in d or "5'" in d for d in descriptions
        )
        assert has_sheet_label, "No sheet size label found in descriptions: %s" % descriptions


# ── AC-4: Seaming detection ──────────────────────────────────────────────


class TestSeamingDetection:
    """When face exceeds 120\" stock sheet width, seaming is detected."""

    def test_cabinet_seaming_detected(self):
        """Cabinet sign wider than 120\" triggers seaming assumption."""
        from backend.calculators.led_sign_custom import LedSignCustomCalculator
        calc = LedSignCustomCalculator()
        result = calc.calculate({
            "sign_type": "Cabinet/box sign",
            "dimensions": "180 x 48",  # 15 ft wide — exceeds 120"
            "letter_height": "18",
            "letter_count": "8",
            "material": "Aluminum (standard for sign fabrication)",
        })
        assumptions = result.get("assumptions", [])
        has_seam = any("seam" in a.lower() for a in assumptions)
        assert has_seam, "No seaming assumption for 180\" wide cabinet: %s" % assumptions

    def test_no_seaming_for_small_cabinet(self):
        """Cabinet sign under 120\" does NOT trigger seaming."""
        from backend.calculators.led_sign_custom import LedSignCustomCalculator
        calc = LedSignCustomCalculator()
        result = calc.calculate({
            "sign_type": "Cabinet/box sign",
            "dimensions": "96 x 48",  # 8 ft — under 120"
            "letter_height": "18",
            "letter_count": "8",
            "material": "Aluminum",
        })
        assumptions = result.get("assumptions", [])
        has_seam = any("seam" in a.lower() for a in assumptions)
        assert not has_seam, "Unexpected seaming for 96\" wide cabinet"

    def test_seaming_adds_weld_inches(self):
        """Seaming adds weld inches for the seam joints."""
        from backend.calculators.led_sign_custom import LedSignCustomCalculator
        calc = LedSignCustomCalculator()

        small = calc.calculate({
            "sign_type": "Cabinet/box sign",
            "dimensions": "96 x 48",
            "material": "Steel",
        })
        large = calc.calculate({
            "sign_type": "Cabinet/box sign",
            "dimensions": "180 x 48",
            "material": "Steel",
        })
        # Large should have more weld inches due to seaming
        assert large["weld_linear_inches"] > small["weld_linear_inches"]


# ── AC-5: Electronics keyword detection ──────────────────────────────────


class TestElectronicsKeywordDetection:
    """LED/electronics keywords inject an electronics question."""

    def test_led_keyword_injects_question(self, client, guest_headers):
        """Description with 'LED' triggers electronics question."""
        resp = client.post("/api/session/start", json={
            "description": "LED illuminated channel letter sign for storefront",
            "job_type": "led_sign_custom",
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        questions = data.get("next_questions", [])
        q_ids = [q.get("id", "") for q in questions]
        has_electronics = any("electron" in qid or "power" in qid
                              or "voltage" in qid or "led" in qid
                              for qid in q_ids)
        assert has_electronics, "No electronics question for LED description. IDs: %s" % q_ids

    def test_neon_keyword_injects_question(self, client, guest_headers):
        """Description with 'neon' triggers electronics question."""
        resp = client.post("/api/session/start", json={
            "description": "Custom neon-style sign with RGB controller",
            "job_type": "led_sign_custom",
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        questions = data.get("next_questions", [])
        q_ids = [q.get("id", "") for q in questions]
        has_electronics = any("electron" in qid or "power" in qid
                              or "voltage" in qid or "led" in qid
                              for qid in q_ids)
        assert has_electronics, "No electronics question for neon description. IDs: %s" % q_ids

    def test_no_electronics_for_steel_gate(self, client, guest_headers):
        """Non-LED description does NOT inject electronics question."""
        resp = client.post("/api/session/start", json={
            "description": "Steel swing gate 12 ft wide 6 ft tall",
            "job_type": "swing_gate",
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        questions = data.get("next_questions", [])
        q_ids = [q.get("id", "") for q in questions]
        has_electronics = "_ai_electronics_spec" in q_ids
        assert not has_electronics, "Unexpected electronics question for gate"


# ── AC-6: No regressions — existing pipeline still works ─────────────────


class TestNoRegressions:
    """Key pipeline behaviors remain intact."""

    def test_cantilever_gate_still_calculates(self):
        """Cantilever gate calculator still works."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator
        calc = CantileverGateCalculator()
        result = calc.calculate({
            "clear_width": "16",
            "height": "6",
            "frame_material": "Square tube 2x2 11ga",
            "infill_type": "Picket",
            "picket_spacing": "4",
            "finish": "paint",
        })
        assert len(result["items"]) > 0
        assert result["total_weight_lbs"] > 0

    def test_labor_estimator_uses_calculator(self):
        """LaborEstimator still calls calculate_labor_hours properly."""
        from backend.labor_estimator import LaborEstimator

        estimator = LaborEstimator()
        material_list = {
            "items": [
                {"description": "test", "profile": "sq_tube_2x2_11ga",
                 "length_inches": 48, "quantity": 4, "line_total": 50.0},
            ],
            "hardware": [],
            "weld_linear_inches": 100,
            "total_sq_ft": 20,
            "total_weight_lbs": 100,
        }
        quote_params = {
            "job_type": "custom_fab",
            "fields": {"finish": "raw", "description": "test"},
        }
        user_rates = {"rate_inshop": 125.0, "rate_onsite": 145.0}

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = estimator.estimate(material_list, quote_params, user_rates)

        assert "processes" in result
        assert result["total_hours"] > 0
        process_names = [p["process"] for p in result["processes"]]
        assert "full_weld" in process_names

    def test_finishing_builder_raw(self):
        """FinishingBuilder returns raw correctly."""
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        result = fb.build("raw", 50.0, [])
        assert result["method"] == "raw"
        assert result["total"] == 0.0

    def test_finishing_builder_paint(self):
        """FinishingBuilder still handles paint."""
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        result = fb.build("paint", 50.0, [
            {"process": "finish_prep", "hours": 1.0},
            {"process": "paint", "hours": 1.5},
        ])
        assert result["method"] == "paint"
        assert result["materials_cost"] > 0
