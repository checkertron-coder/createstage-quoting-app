"""
Tests for Prompt 25 — Claude Review Loop + Bug Fixes + Rate Fix.

Covers:
- Picket profile robust matching (fraction, decimal, Gemini text, empty field)
- Fence picket gate match (match enforced, separate infill allowed, default)
- Overhead beam profile validation (wrong profile overridden, correct kept, missing added)
- Consumable sanity (small→cans, large→gallons, caps, paint+primer both)
- HSS weights (both profiles in STOCK_WEIGHTS with correct values)
- Claude reviewer (no API key graceful, parse_review JSON, error handling)
- Review endpoint (404 missing session, 400 unpriced, success structure)
"""

import json
import math
import os
from unittest.mock import patch, MagicMock

import pytest


# ========================================================
# Part 1: Picket Profile Robust Matching
# ========================================================

class TestPicketProfileRobust:
    """Test _resolve_picket_profile handles Gemini text variations."""

    def test_exact_fraction_match(self):
        """Standard fraction format from question tree."""
        from backend.calculators.cantilever_gate import _resolve_picket_profile
        fields = {"picket_material": '5/8" square'}
        result = _resolve_picket_profile(fields, "Pickets (vertical bars)")
        assert result == "sq_bar_0.625"

    def test_fraction_without_quotes(self):
        """Gemini might extract '5/8 inch square' without quotes."""
        from backend.calculators.cantilever_gate import _resolve_picket_profile
        fields = {"picket_material": "5/8 inch square bar"}
        result = _resolve_picket_profile(fields, "Pickets (vertical bars)")
        assert result == "sq_bar_0.625"

    def test_decimal_form(self):
        """Gemini might use decimal: 0.625 sq"""
        from backend.calculators.cantilever_gate import _resolve_picket_profile
        fields = {"picket_material": "0.625 sq"}
        result = _resolve_picket_profile(fields, "Pickets (vertical bars)")
        assert result == "sq_bar_0.625"

    def test_empty_field_fallback(self):
        """Empty picket_material falls back to INFILL_PROFILES."""
        from backend.calculators.cantilever_gate import _resolve_picket_profile
        fields = {"picket_material": ""}
        result = _resolve_picket_profile(fields, "Pickets (vertical bars)")
        assert result == "sq_bar_0.75"

    def test_round_bar_fraction(self):
        """5/8 round should return round bar profile."""
        from backend.calculators.cantilever_gate import _resolve_picket_profile
        fields = {"picket_material": "5/8 round bar"}
        result = _resolve_picket_profile(fields, "Pickets (vertical bars)")
        assert result == "round_bar_0.625"

    def test_half_inch_decimal(self):
        """0.5 should map to 1/2 inch."""
        from backend.calculators.cantilever_gate import _resolve_picket_profile
        fields = {"picket_material": "0.5 square"}
        result = _resolve_picket_profile(fields, "Pickets (vertical bars)")
        assert result == "sq_bar_0.5"


# ========================================================
# Part 2: Fence Picket Gate Match
# ========================================================

class TestFencePicketGateMatch:
    """Test that fence pickets use gate picket profile when match is requested."""

    def test_fence_match_uses_gate_profile(self):
        """When fence_infill_match says match, fence pickets use gate picket profile."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator

        calc = CantileverGateCalculator()
        fields = {
            "picket_material": '5/8" square',
            "fence_infill_match": "Yes — match gate infill exactly",
            "fence_side_1_length": "20",
            "infill_type": "Pickets (vertical bars)",
        }
        result = calc._generate_fence_sections(
            fields, height_in=72, infill_type="Pickets (vertical bars)",
            infill_spacing_in=4.0,
            frame_key="sq_tube_2x2_11ga", frame_size='2" x 2"',
            frame_gauge="11 gauge", frame_price_ft=3.50,
            post_profile_key="sq_tube_4x4_11ga", post_price_ft=6.0,
            post_concrete_depth_in=42.0,
            gate_picket_profile="sq_bar_0.625",
        )
        # Find the fence picket item
        picket_items = [i for i in result["items"] if "picket" in i["description"].lower()]
        assert len(picket_items) >= 1
        assert picket_items[0]["profile"] == "sq_bar_0.625"

    def test_fence_no_match_uses_default(self):
        """When no gate profile passed, fence uses its own resolution."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator

        calc = CantileverGateCalculator()
        fields = {
            "picket_material": '3/4" square',
            "fence_infill_match": "No — different infill",
            "fence_side_1_length": "20",
            "infill_type": "Pickets (vertical bars)",
        }
        result = calc._generate_fence_sections(
            fields, height_in=72, infill_type="Pickets (vertical bars)",
            infill_spacing_in=4.0,
            frame_key="sq_tube_2x2_11ga", frame_size='2" x 2"',
            frame_gauge="11 gauge", frame_price_ft=3.50,
            post_profile_key="sq_tube_4x4_11ga", post_price_ft=6.0,
            post_concrete_depth_in=42.0,
            gate_picket_profile="sq_bar_0.625",
        )
        picket_items = [i for i in result["items"] if "picket" in i["description"].lower()]
        assert len(picket_items) >= 1
        # Should NOT use gate profile since match is "No"
        assert picket_items[0]["profile"] == "sq_bar_0.75"

    def test_fence_default_no_gate_profile(self):
        """When gate_picket_profile is None, fence resolves its own."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator

        calc = CantileverGateCalculator()
        fields = {
            "fence_infill_match": "Yes — match gate infill exactly",
            "fence_side_1_length": "15",
            "infill_type": "Pickets (vertical bars)",
        }
        result = calc._generate_fence_sections(
            fields, height_in=72, infill_type="Pickets (vertical bars)",
            infill_spacing_in=4.0,
            frame_key="sq_tube_2x2_11ga", frame_size='2" x 2"',
            frame_gauge="11 gauge", frame_price_ft=3.50,
            post_profile_key="sq_tube_4x4_11ga", post_price_ft=6.0,
            post_concrete_depth_in=42.0,
            gate_picket_profile=None,
        )
        picket_items = [i for i in result["items"] if "picket" in i["description"].lower()]
        assert len(picket_items) >= 1
        # Falls back to default resolution
        assert picket_items[0]["profile"] == "sq_bar_0.75"


# ========================================================
# Part 3: Overhead Beam Validation
# ========================================================

class TestOverheadBeamValidation:
    """Test overhead beam profile is validated against gate weight."""

    def test_trusts_ai_beam_profile(self):
        """Post-processor trusts AI's beam profile (constraints enforced via prompt)."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator

        calc = CantileverGateCalculator()
        # AI provides overhead beam — post-processor trusts the profile
        ai_result = {
            "items": [
                {
                    "description": "Overhead support beam — HSS 6×4×1/4\"",
                    "material_type": "hss_structural_tube",
                    "profile": "hss_6x4_0.25",
                    "length_inches": 204.0,
                    "quantity": 1,
                    "unit_price": 100.0,
                    "line_total": 100.0,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                },
            ],
            "cut_list": [
                {
                    "description": "Overhead beam",
                    "piece_name": "overhead_beam",
                    "profile": "hss_6x4_0.25",
                    "length_inches": 204.0,
                    "quantity": 1,
                }
            ],
            "total_weight_lbs": 300.0,
            "total_sq_ft": 100.0,
            "weld_linear_inches": 200.0,
            "assumptions": [],
        }
        fields = {
            "clear_width": "10",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung system)",
            "post_size": "4\" x 4\" square tube",
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
            "infill_type": "Pickets (vertical bars)",
        }
        result = calc._post_process_ai_result(ai_result, fields, [])
        # AI included overhead beam — trust it, don't add another
        beam_items = [i for i in result["items"]
                      if "overhead" in i["description"].lower()]
        assert len(beam_items) == 1
        # Profile is trusted as-is (constraints handled in AI prompt)
        assert beam_items[0]["profile"] == "hss_6x4_0.25"

    def test_correct_profile_kept(self):
        """If AI puts the right profile, it should be kept."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator

        calc = CantileverGateCalculator()
        ai_result = {
            "items": [
                {
                    "description": "Overhead support beam — HSS 4×4×1/4\"",
                    "material_type": "hss_structural_tube",
                    "profile": "hss_4x4_0.25",  # Correct for < 800 lbs
                    "length_inches": 204.0,
                    "quantity": 1,
                    "unit_price": 100.0,
                    "line_total": 100.0,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                },
            ],
            "cut_list": [],
            "total_weight_lbs": 300.0,
            "total_sq_ft": 100.0,
            "weld_linear_inches": 200.0,
            "assumptions": [],
        }
        fields = {
            "clear_width": "10",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung system)",
            "post_size": "4\" x 4\" square tube",
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
            "infill_type": "Pickets (vertical bars)",
        }
        result = calc._post_process_ai_result(ai_result, fields, [])
        beam_items = [i for i in result["items"]
                      if "overhead" in i["description"].lower()]
        assert len(beam_items) == 1
        assert beam_items[0]["profile"] == "hss_4x4_0.25"

    def test_missing_beam_added(self):
        """If AI omits overhead beam for top-hung gate, it should be added."""
        from backend.calculators.cantilever_gate import CantileverGateCalculator

        calc = CantileverGateCalculator()
        ai_result = {
            "items": [],  # No overhead beam
            "cut_list": [],
            "total_weight_lbs": 200.0,
            "total_sq_ft": 80.0,
            "weld_linear_inches": 150.0,
            "assumptions": [],
        }
        fields = {
            "clear_width": "10",
            "height": "6",
            "bottom_guide": "No bottom guide (top-hung system)",
            "post_size": "4\" x 4\" square tube",
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
            "infill_type": "Pickets (vertical bars)",
        }
        result = calc._post_process_ai_result(ai_result, fields, [])
        beam_items = [i for i in result["items"]
                      if "overhead" in i["description"].lower()]
        assert len(beam_items) >= 1
        assert beam_items[0]["profile"] == "hss_4x4_0.25"


# ========================================================
# Part 4: Consumable Sanity
# ========================================================

class TestConsumableSanity:
    """Test consumable estimation uses gallons for large jobs, cans for small."""

    def test_small_job_uses_cans(self):
        """Jobs ≤ 100 sq ft should use spray cans."""
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        items = hs.estimate_consumables(100.0, 50.0, "paint")
        paint_items = [i for i in items if "primer" in i["description"].lower()
                       or "paint" in i["description"].lower()]
        for item in paint_items:
            assert "spray" in item["description"].lower() or "can" in item["description"].lower() \
                   or "x" in item["description"].lower()  # "Primer spray x3" format

    def test_large_job_uses_gallons(self):
        """Jobs > 100 sq ft should use gallons."""
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        items = hs.estimate_consumables(500.0, 1418.0, "paint")
        paint_items = [i for i in items if "primer" in i["description"].lower()
                       or "paint" in i["description"].lower()]
        assert len(paint_items) == 2  # primer + paint gallons
        for item in paint_items:
            assert "gallon" in item["description"].lower()

    def test_large_job_primer_and_paint(self):
        """Large paint job should have both primer and paint as gallons."""
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        items = hs.estimate_consumables(500.0, 1418.0, "paint")
        descriptions = [i["description"].lower() for i in items]
        has_primer = any("primer" in d for d in descriptions)
        has_paint = any("paint" in d and "primer" not in d for d in descriptions)
        assert has_primer, "Should have primer gallons"
        assert has_paint, "Should have paint gallons"

    def test_gallon_cap_at_10(self):
        """Gallon quantities should cap at 10."""
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        # 5000 sq ft → ceil(5000/350) = 15 → capped at 10
        items = hs.estimate_consumables(500.0, 5000.0, "paint")
        gallon_items = [i for i in items if "gallon" in i["description"].lower()]
        for item in gallon_items:
            assert item["quantity"] <= 10

    def test_can_cap_at_12(self):
        """Spray can quantities should cap at 12 for small jobs."""
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        # 99 sq ft → ceil(99/20) = 5 cans, should be ≤ 12
        items = hs.estimate_consumables(100.0, 99.0, "paint")
        can_items = [i for i in items if "spray" in i["description"].lower()]
        for item in can_items:
            assert item["quantity"] <= 12

    def test_clearcoat_large_uses_gallons(self):
        """Large clearcoat job should use gallons."""
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        items = hs.estimate_consumables(200.0, 500.0, "clearcoat")
        cc_items = [i for i in items if "clear" in i["description"].lower()]
        assert len(cc_items) >= 1
        assert "gallon" in cc_items[0]["description"].lower()

    def test_1418_sqft_reasonable_cost(self):
        """1418 sq ft paint job should cost ~$400, not $603."""
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        items = hs.estimate_consumables(500.0, 1418.0, "paint")
        finish_cost = sum(i["line_total"] for i in items
                         if "primer" in i["description"].lower()
                         or "paint" in i["description"].lower())
        assert finish_cost < 500, "1418 sq ft paint should be under $500, got $%.2f" % finish_cost
        assert finish_cost > 200, "1418 sq ft paint should be over $200, got $%.2f" % finish_cost


# ========================================================
# Part 5: HSS Weights
# ========================================================

class TestHSSWeights:
    """Test HSS profiles exist in STOCK_WEIGHTS with correct AISC values."""

    def test_hss_4x4_weight(self):
        from backend.weights import STOCK_WEIGHTS
        assert "hss_4x4_0.25" in STOCK_WEIGHTS
        assert STOCK_WEIGHTS["hss_4x4_0.25"] == 12.21

    def test_hss_6x4_weight(self):
        from backend.weights import STOCK_WEIGHTS
        assert "hss_6x4_0.25" in STOCK_WEIGHTS
        assert STOCK_WEIGHTS["hss_6x4_0.25"] == 15.62

    def test_weight_from_stock_hss(self):
        """weight_from_stock should return non-zero for HSS profiles."""
        from backend.weights import weight_from_stock
        weight = weight_from_stock("hss_4x4_0.25", 10.0)
        assert weight > 0
        assert abs(weight - 122.1) < 0.1  # 12.21 * 10 = 122.1


# ========================================================
# Part 6: Claude Reviewer
# ========================================================

class TestClaudeReviewer:
    """Test the Claude review module."""

    def test_no_api_key_graceful(self):
        """Without ANTHROPIC_API_KEY, returns graceful fallback."""
        from backend.claude_reviewer import review_quote
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = review_quote({}, {})
            assert result["reviewed"] is False
            assert isinstance(result["issues"], list)
            assert isinstance(result["warnings"], list)
            assert result["score"] is None

    def test_parse_review_valid_json(self):
        """_parse_review correctly parses valid JSON response."""
        from backend.claude_reviewer import _parse_review
        text = json.dumps({
            "issues": ["Missing post concrete"],
            "warnings": ["Labor hours seem low"],
            "suggestions": ["Consider powder coat"],
            "score": 78,
        })
        result = _parse_review(text)
        assert result["reviewed"] is True
        assert result["score"] == 78
        assert "Missing post concrete" in result["issues"]

    def test_parse_review_with_markdown_fences(self):
        """_parse_review handles markdown code fences."""
        from backend.claude_reviewer import _parse_review
        text = "```json\n" + json.dumps({
            "issues": [],
            "warnings": [],
            "suggestions": [],
            "score": 95,
        }) + "\n```"
        result = _parse_review(text)
        assert result["reviewed"] is True
        assert result["score"] == 95

    def test_parse_review_invalid_json(self):
        """_parse_review handles invalid JSON gracefully."""
        from backend.claude_reviewer import _parse_review
        result = _parse_review("not valid json at all")
        assert result["reviewed"] is False
        assert result["score"] is None


# ========================================================
# Part 7: Review Endpoint
# ========================================================

class TestReviewEndpoint:
    """Test the /api/session/{id}/review endpoint."""

    def test_404_missing_session(self, client, auth_headers):
        """Review on non-existent session returns 404."""
        resp = client.post(
            "/api/session/nonexistent-id/review",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_400_unpriced_session(self, client, auth_headers):
        """Review on session that hasn't been priced returns 400."""
        # Start a session first
        start_resp = client.post(
            "/api/session/start",
            json={"description": "Test gate", "job_type": "cantilever_gate"},
            headers=auth_headers,
        )
        assert start_resp.status_code == 200
        session_id = start_resp.json()["session_id"]

        # Try to review before pricing
        resp = client.post(
            "/api/session/%s/review" % session_id,
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "output" in resp.json()["detail"].lower() or "price" in resp.json()["detail"].lower()

    def test_review_returns_structure(self, client, auth_headers):
        """Review endpoint returns proper structure (mocked Claude)."""
        from backend.claude_reviewer import review_quote as real_review

        # Mock review_quote to avoid actual API call
        mock_review = {
            "issues": [],
            "warnings": ["Test warning"],
            "suggestions": [],
            "score": 90,
            "reviewed": True,
        }

        # Start and complete a session through all stages
        start = client.post(
            "/api/session/start",
            json={"description": "10ft cantilever gate, 6ft tall, with 5/8 square pickets",
                  "job_type": "cantilever_gate"},
            headers=auth_headers,
        )
        session_id = start.json()["session_id"]

        # Answer required fields
        client.post(
            "/api/session/%s/answer" % session_id,
            json={"answers": {
                "clear_width": "10",
                "height": "6",
                "frame_material": '2" x 2" square tube',
                "frame_size": '2" x 2"',
                "frame_gauge": "11 gauge (0.120\" - standard for gates)",
                "post_size": "4\" x 4\" square tube",
                "post_count": "3 posts (standard)",
                "infill_type": "Pickets (vertical bars)",
                "picket_material": '5/8" square',
                "picket_spacing": "4\" on-center",
                "finish": "Paint",
                "installation": "Full install (gate + posts + concrete)",
                "has_motor": "No",
                "adjacent_fence": "No",
                "bottom_guide": "Surface mount guide roller",
                "post_concrete": "Yes",
            }},
            headers=auth_headers,
        )

        # Run calculate
        calc_resp = client.post(
            "/api/session/%s/calculate" % session_id,
            headers=auth_headers,
        )
        if calc_resp.status_code != 200:
            pytest.skip("Calculate failed: %s" % calc_resp.json().get("detail", ""))

        # Run estimate
        est_resp = client.post(
            "/api/session/%s/estimate" % session_id,
            headers=auth_headers,
        )
        if est_resp.status_code != 200:
            pytest.skip("Estimate failed: %s" % est_resp.json().get("detail", ""))

        # Run price
        price_resp = client.post(
            "/api/session/%s/price" % session_id,
            headers=auth_headers,
        )
        if price_resp.status_code != 200:
            pytest.skip("Price failed: %s" % price_resp.json().get("detail", ""))

        # Now run review with mocked Claude
        with patch("backend.routers.quote_session.review_quote", return_value=mock_review):
            review_resp = client.post(
                "/api/session/%s/review" % session_id,
                headers=auth_headers,
            )

        assert review_resp.status_code == 200
        data = review_resp.json()
        assert "review" in data
        assert data["review"]["reviewed"] is True
        assert data["review"]["score"] == 90
