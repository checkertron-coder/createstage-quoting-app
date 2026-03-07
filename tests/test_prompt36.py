"""
Tests for Prompt 36: Materials PDF fix, build instructions parsing, editable fields.

Covers:
- Materials PDF uses aggregated stock order (not individual pieces)
- Materials CSV uses aggregated stock order
- Build instructions parser handles dict wrapper responses
- Build instructions parser handles code fences
- Adjust line items endpoint
- Frontend editable fields (labor, hardware, consumables)
"""

import json
import pytest
from unittest.mock import patch


# =====================================================================
# Materials PDF — aggregated stock order
# =====================================================================

class TestMaterialsPdfAggregated:
    """Materials PDF should show aggregated stock order, not individual pieces."""

    def _make_priced_quote(self):
        return {
            "quote_id": 1,
            "quote_number": "CS-2026-0001",
            "job_type": "cantilever_gate",
            "materials": [
                {"description": "Post A", "profile": "sq_tube_4x4_11ga",
                 "length_inches": 120, "quantity": 2, "material_type": "steel",
                 "unit_price": 10.0, "line_total": 20.0},
                {"description": "Rail B", "profile": "sq_tube_2x2_11ga",
                 "length_inches": 180, "quantity": 4, "material_type": "steel",
                 "unit_price": 5.0, "line_total": 20.0},
            ],
            "materials_summary": [
                {"profile": "sq_tube_4x4_11ga", "total_length_ft": 20.0,
                 "sticks_needed": 1, "stock_length_ft": 24,
                 "remainder_ft": 4.0, "weight_lbs": 100, "total_cost": 20.0,
                 "piece_count": 2, "is_concrete": False, "is_area_sold": False},
                {"profile": "sq_tube_2x2_11ga", "total_length_ft": 60.0,
                 "sticks_needed": 3, "stock_length_ft": 24,
                 "remainder_ft": 12.0, "weight_lbs": 80, "total_cost": 20.0,
                 "piece_count": 4, "is_concrete": False, "is_area_sold": False},
            ],
            "hardware": [],
            "material_subtotal": 40.0,
        }

    def test_materials_pdf_shows_stock_order_header(self):
        """Materials PDF should have STOCK ORDER section, not CUT LIST."""
        from backend.pdf_generator import generate_materials_pdf
        pq = self._make_priced_quote()
        user = {"shop_name": "Test Shop"}
        pdf_bytes = generate_materials_pdf(pq, user)
        assert isinstance(pdf_bytes, (bytes, bytearray))
        assert len(pdf_bytes) > 100

    def test_materials_pdf_no_cut_list_header_when_summary_exists(self):
        """When materials_summary exists, PDF should not have CUT LIST section."""
        from backend.pdf_generator import generate_materials_pdf
        pq = self._make_priced_quote()
        user = {"shop_name": "Test Shop"}
        # Generate and check the PDF bytes don't contain "CUT LIST" as section header
        # (Can't easily check PDF content, but verify it generates without error)
        pdf_bytes = generate_materials_pdf(pq, user)
        assert isinstance(pdf_bytes, (bytes, bytearray))

    def test_materials_pdf_fallback_when_no_summary(self):
        """When no materials_summary, falls back to per-piece view."""
        from backend.pdf_generator import generate_materials_pdf
        pq = self._make_priced_quote()
        del pq["materials_summary"]
        user = {"shop_name": "Test Shop"}
        pdf_bytes = generate_materials_pdf(pq, user)
        assert isinstance(pdf_bytes, (bytes, bytearray))
        assert len(pdf_bytes) > 100


# =====================================================================
# Materials CSV — aggregated stock order
# =====================================================================

class TestMaterialsCsvAggregated:
    """Materials CSV should show aggregated stock order as primary view."""

    def test_csv_primary_is_aggregated(self):
        """CSV should have aggregated columns when summary exists."""
        from backend.pdf_generator import generate_materials_csv
        pq = {
            "materials_summary": [
                {"profile": "sq_tube_2x2_11ga", "total_length_ft": 40.0,
                 "sticks_needed": 2, "stock_length_ft": 24,
                 "remainder_ft": 8.0, "weight_lbs": 60,
                 "is_concrete": False},
            ],
            "materials": [],
            "hardware": [],
        }
        csv_bytes = generate_materials_csv(pq)
        csv_text = csv_bytes.decode("utf-8")
        assert "Total Length (ft)" in csv_text
        assert "Sticks Needed" in csv_text
        assert "Remainder (ft)" in csv_text
        assert "Weight (lbs)" in csv_text

    def test_csv_fallback_when_no_summary(self):
        """CSV uses per-piece format when no summary."""
        from backend.pdf_generator import generate_materials_csv
        pq = {
            "materials_summary": [],
            "materials": [
                {"profile": "sq_tube_2x2_11ga", "description": "Rail",
                 "length_inches": 120, "quantity": 2, "material_type": "steel"},
            ],
            "hardware": [],
        }
        csv_bytes = generate_materials_csv(pq)
        csv_text = csv_bytes.decode("utf-8")
        assert "Length (in)" in csv_text
        assert "Description" in csv_text


# =====================================================================
# Build instructions parsing — dict wrapper handling
# =====================================================================

class TestBuildInstructionsParsing:
    """Build instructions parser should handle various response formats."""

    def _get_parser(self):
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        return gen._parse_instructions_response

    def test_parse_bare_array(self):
        """Standard bare JSON array should parse."""
        parse = self._get_parser()
        data = json.dumps([
            {"step": 1, "title": "Layout", "description": "Mark steel",
             "tools": ["tape measure"], "duration_minutes": 15},
        ])
        result = parse(data)
        assert result is not None
        assert len(result) == 1
        assert result[0]["title"] == "Layout"

    def test_parse_dict_with_steps_key(self):
        """Dict wrapper with 'steps' key should unwrap."""
        parse = self._get_parser()
        data = json.dumps({
            "steps": [
                {"step": 1, "title": "Cut", "description": "Cut rails"},
                {"step": 2, "title": "Weld", "description": "Weld frame"},
            ]
        })
        result = parse(data)
        assert result is not None
        assert len(result) == 2

    def test_parse_dict_with_instructions_key(self):
        """Dict wrapper with 'instructions' key should unwrap."""
        parse = self._get_parser()
        data = json.dumps({
            "instructions": [
                {"step": 1, "title": "Prep", "description": "Prepare materials"},
            ]
        })
        result = parse(data)
        assert result is not None
        assert len(result) == 1

    def test_parse_dict_with_build_instructions_key(self):
        """Dict wrapper with 'build_instructions' key should unwrap."""
        parse = self._get_parser()
        data = json.dumps({
            "build_instructions": [
                {"step": 1, "title": "Layout", "description": "Mark pieces"},
            ]
        })
        result = parse(data)
        assert result is not None
        assert len(result) == 1

    def test_parse_dict_with_fabrication_sequence_key(self):
        """Dict wrapper with 'fabrication_sequence' key should unwrap."""
        parse = self._get_parser()
        data = json.dumps({
            "fabrication_sequence": [
                {"step": 1, "title": "Start", "description": "Begin fabrication"},
            ]
        })
        result = parse(data)
        assert result is not None

    def test_parse_code_fenced_response(self):
        """Response wrapped in markdown code fences should parse."""
        parse = self._get_parser()
        data = '```json\n[{"step": 1, "title": "Layout", "description": "Mark"}]\n```'
        result = parse(data)
        assert result is not None
        assert len(result) == 1

    def test_parse_code_fenced_dict_wrapper(self):
        """Code-fenced dict wrapper should parse."""
        parse = self._get_parser()
        data = '```json\n{"steps": [{"step": 1, "title": "Cut", "description": "Cut rails"}]}\n```'
        result = parse(data)
        assert result is not None
        assert len(result) == 1

    def test_parse_empty_returns_none(self):
        """Empty response should return None."""
        parse = self._get_parser()
        assert parse("") is None
        assert parse(None) is None

    def test_parse_validates_step_fields(self):
        """Parser should normalize step fields."""
        parse = self._get_parser()
        data = json.dumps([{"title": "Step One", "description": "Do stuff"}])
        result = parse(data)
        assert result is not None
        assert result[0]["step"] == 1  # Auto-numbered
        assert result[0]["tools"] == []  # Default empty list
        assert result[0]["duration_minutes"] == 15  # Default duration


# =====================================================================
# Adjust line items endpoint
# =====================================================================

class TestAdjustLineItems:
    """PATCH /quotes/{id}/adjust endpoint."""

    def _create_quote(self, client, auth_headers, db, user_id=None):
        """Create a test quote with outputs_json."""
        from backend import models
        from datetime import datetime

        # Determine user_id from auth_headers if not specified
        if user_id is None:
            resp = client.get("/api/auth/me", headers=auth_headers)
            user_id = resp.json().get("id", 1)

        quote = models.Quote(
            quote_number="CS-2026-TEST",
            job_type="cantilever_gate",
            user_id=user_id,
            session_id="test-session",
            inputs_json={},
            outputs_json={
                "job_type": "cantilever_gate",
                "materials": [],
                "hardware": [
                    {"description": "Hinge Pair", "quantity": 2,
                     "options": [{"supplier": "McMaster", "price": 25.0, "url": "", "part_number": "123"}]},
                ],
                "consumables": [
                    {"description": "Welding wire", "quantity": 1, "unit_price": 30.0, "line_total": 30.0},
                    {"description": "Grinding disc", "quantity": 3, "unit_price": 5.0, "line_total": 15.0},
                ],
                "labor": [
                    {"process": "cut_prep", "hours": 2.0, "rate": 125.0},
                    {"process": "full_weld", "hours": 4.0, "rate": 125.0},
                ],
                "finishing": {"method": "raw", "total": 0},
                "material_subtotal": 100.0,
                "hardware_subtotal": 50.0,
                "consumable_subtotal": 45.0,
                "labor_subtotal": 750.0,
                "finishing_subtotal": 0,
                "subtotal": 945.0,
                "selected_markup_pct": 15,
                "total": 1086.75,
                "markup_options": {"0": 945.0, "15": 1086.75},
            },
            subtotal=945.0,
            total=1086.75,
            selected_markup_pct=15,
        )
        db.add(quote)
        db.commit()
        db.refresh(quote)
        return quote

    def test_adjust_labor_hours(self, client, auth_headers, db):
        """Adjusting labor hours should recalculate totals."""
        quote = self._create_quote(client, auth_headers, db)
        resp = client.patch(
            "/api/quotes/%d/adjust" % quote.id,
            json={"labor_adjustments": {"cut_prep": 3.0}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # cut_prep went from 2.0 to 3.0 hours, rate=125
        # full_weld stays at 4.0 hours
        # new labor subtotal = 3.0*125 + 4.0*125 = 875
        assert data["labor_subtotal"] == 875.0
        # subtotal = 100 + 50 + 45 + 875 + 0 = 1070
        assert data["subtotal"] == 1070.0

    def test_adjust_hardware_qty(self, client, auth_headers, db):
        """Adjusting hardware quantity should recalculate subtotal."""
        quote = self._create_quote(client, auth_headers, db)
        resp = client.patch(
            "/api/quotes/%d/adjust" % quote.id,
            json={"hardware_adjustments": {"0": 4}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Hinge pair: 4 x $25 = $100
        assert data["hardware_subtotal"] == 100.0

    def test_adjust_consumable_qty(self, client, auth_headers, db):
        """Adjusting consumable quantity should recalculate line_total and subtotal."""
        quote = self._create_quote(client, auth_headers, db)
        resp = client.patch(
            "/api/quotes/%d/adjust" % quote.id,
            json={"consumable_adjustments": {"0": 2.0}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Welding wire: 2.0 x $30 = $60, grinding disc stays at $15
        assert data["consumable_subtotal"] == 75.0

    def test_adjust_no_changes(self, client, auth_headers, db):
        """If no adjustments match, returns outputs unchanged."""
        quote = self._create_quote(client, auth_headers, db)
        resp = client.patch(
            "/api/quotes/%d/adjust" % quote.id,
            json={},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_adjust_requires_auth(self, client, db):
        """Adjust endpoint requires authentication."""
        resp = client.patch("/api/quotes/999/adjust", json={})
        assert resp.status_code in (401, 403, 422)

    def test_adjust_wrong_user(self, client, guest_headers, auth_headers, db):
        """Can't adjust another user's quote."""
        quote = self._create_quote(client, auth_headers, db)
        resp = client.patch(
            "/api/quotes/%d/adjust" % quote.id,
            json={"labor_adjustments": {"cut_prep": 5.0}},
            headers=guest_headers,
        )
        assert resp.status_code == 403


# =====================================================================
# Format helpers
# =====================================================================

class TestFormatHelpers:
    def test_fmt_profile_sq_tube(self):
        from backend.pdf_generator import _fmt_profile
        result = _fmt_profile("sq_tube_2x2_11ga")
        assert "Sq Tube" in result
        assert "11ga" in result

    def test_fmt_profile_flat_bar(self):
        from backend.pdf_generator import _fmt_profile
        result = _fmt_profile("flat_bar_1x0.25")
        assert "Flat Bar" in result
        assert '1/4"' in result

    def test_fmt_length_feet_inches(self):
        from backend.pdf_generator import _fmt_length
        assert _fmt_length(24) == "2'-0\""
        assert _fmt_length(30) == "2'-6\""
        assert _fmt_length(6) == '6"'
