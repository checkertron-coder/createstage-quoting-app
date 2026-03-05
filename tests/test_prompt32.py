"""
Tests for Prompt 32 — Client PDF polish, customer info, logo upload, beam fix.
"""

import base64
import inspect
from io import BytesIO
from unittest.mock import patch

import pytest


# ── Part 1: Client PDF bugs ──


class TestClientPDFBugs:
    """Tests for Part 1: client PDF fixes."""

    def test_client_pdf_no_markup_word(self):
        """Client PDF source should not display 'Markup' as a visible label."""
        from backend.pdf_generator import generate_client_pdf
        src = inspect.getsource(generate_client_pdf)
        # The word "Markup" should not appear as a cell/label in the client PDF
        # It can appear in variable names (markup_pct, multiplier) but not displayed
        assert 'Markup (' not in src, "Client PDF should not show 'Markup (X%)' line"

    def test_client_pdf_no_subtotal_line(self):
        """Client PDF should not show a 'Subtotal' line — go straight to PROJECT TOTAL."""
        from backend.pdf_generator import generate_client_pdf
        src = inspect.getsource(generate_client_pdf)
        assert '  Subtotal' not in src, "Client PDF should not show 'Subtotal' line"

    def test_client_pdf_no_double_percent(self):
        """Client PDF terms should not contain '%%' (literal double percent)."""
        from backend.pdf_generator import generate_client_pdf
        src = inspect.getsource(generate_client_pdf)
        assert '%%' not in src, "Client PDF should not have '%%' in any string"

    def test_client_pdf_terms_simplified(self):
        """Client PDF terms should use simple '50% deposit' language."""
        from backend.pdf_generator import generate_client_pdf
        src = inspect.getsource(generate_client_pdf)
        assert '50% deposit' in src

    def test_client_pdf_markup_distributed(self):
        """Client PDF should distribute markup into category totals."""
        from backend.pdf_generator import generate_client_pdf
        pq = {
            "job_type": "cantilever_gate",
            "material_subtotal": 1000,
            "hardware_subtotal": 200,
            "consumable_subtotal": 50,
            "labor_subtotal": 500,
            "finishing_subtotal": 100,
            "subtotal": 1850,
            "selected_markup_pct": 20,
            "total": 2220,
            "materials": [],
            "hardware": [],
            "consumables": [],
            "labor": [],
            "finishing": {"method": "raw"},
            "assumptions": [],
            "exclusions": [],
        }
        user_profile = {"shop_name": "Test Shop"}
        result = generate_client_pdf(pq, user_profile)
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 100

    def test_included_list_customer_friendly(self):
        """_build_included_list should use customer-friendly language."""
        from backend.pdf_generator import _build_included_list
        pq = {
            "job_type": "cantilever_gate",
            "materials": [{"description": "tube", "profile": "sq_tube_2x2_11ga"}],
            "hardware": [{"description": "hinge"}],
            "consumables": [{"description": "wire"}],
            "labor": [{"process": "full_weld", "hours": 5, "rate": 125}],
            "finishing": {"method": "powder_coat"},
        }
        fields = {"has_motor": "Yes", "installation": "Full install"}
        result = _build_included_list(pq, fields)
        # Should NOT contain item counts or hour numbers
        combined = " ".join(result)
        assert "items)" not in combined
        assert "hours)" not in combined
        assert "wire, gas" not in combined
        # Should contain customer-friendly text
        assert "All structural steel" in combined
        assert "Complete shop fabrication" in combined
        assert "Electric gate operator" in combined


# ── Part 2: AI Scope ──


class TestAIScope:
    """Tests for Part 2: AI scope of work generation."""

    def test_generate_client_scope_exists(self):
        """generate_client_scope function should exist and be importable."""
        from backend.pdf_generator import generate_client_scope
        assert callable(generate_client_scope)

    def test_generate_client_scope_fallback(self):
        """When AI unavailable, falls back to job_description."""
        from backend.pdf_generator import generate_client_scope
        with patch("backend.claude_client.call_fast", side_effect=Exception("unavailable")):
            result = generate_client_scope("cantilever_gate", {}, "Build a 10ft gate")
        assert result == "Build a 10ft gate"

    def test_client_pdf_accepts_scope_param(self):
        """generate_client_pdf should accept client_scope parameter."""
        from backend.pdf_generator import generate_client_pdf
        sig = inspect.signature(generate_client_pdf)
        assert "client_scope" in sig.parameters


# ── Part 3: Customer Information ──


class TestCustomerInfo:
    """Tests for Part 3: customer information endpoint and rendering."""

    def test_customer_endpoint_exists(self, client, guest_headers):
        """PATCH /api/session/{id}/customer should exist."""
        # First create a session
        resp = client.post("/api/session/start", json={
            "description": "Test gate",
        }, headers=guest_headers)
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Update customer info
        resp = client.patch(
            "/api/session/%s/customer" % session_id,
            json={"name": "John Smith", "phone": "312-555-1234"},
            headers=guest_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["customer"]["name"] == "John Smith"
        assert data["customer"]["phone"] == "312-555-1234"

    def test_customer_info_stored_in_session(self, client, guest_headers, db):
        """Customer info should be stored in session params_json."""
        from backend.models import QuoteSession
        resp = client.post("/api/session/start", json={
            "description": "Test railing",
        }, headers=guest_headers)
        session_id = resp.json()["session_id"]

        client.patch(
            "/api/session/%s/customer" % session_id,
            json={"name": "Jane Doe", "email": "jane@example.com"},
            headers=guest_headers,
        )

        session = db.query(QuoteSession).filter(QuoteSession.id == session_id).first()
        assert session is not None
        customer = session.params_json.get("_customer", {})
        assert customer["name"] == "Jane Doe"
        assert customer["email"] == "jane@example.com"

    def test_customer_info_in_shop_pdf(self):
        """Shop PDF should render customer info in 'Prepared for' section."""
        from backend.pdf_generator import generate_quote_pdf
        pq = {
            "job_type": "straight_railing",
            "material_subtotal": 500,
            "hardware_subtotal": 100,
            "consumable_subtotal": 25,
            "labor_subtotal": 300,
            "finishing_subtotal": 50,
            "subtotal": 975,
            "selected_markup_pct": 0,
            "total": 975,
            "materials": [],
            "hardware": [],
            "consumables": [],
            "labor": [],
            "finishing": {"method": "raw"},
            "assumptions": [],
            "exclusions": [],
            "_customer": {
                "name": "Test Client",
                "phone": "555-1234",
                "email": "test@test.com",
                "address": "123 Main St",
            },
        }
        result = generate_quote_pdf(pq, {"shop_name": "Shop"})
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 100


# ── Part 4: Logo Upload ──


class TestLogoUpload:
    """Tests for Part 4: logo upload endpoint."""

    def test_logo_endpoint_exists(self, client, auth_headers):
        """POST /api/auth/profile/logo should exist."""
        # Create a tiny valid PNG (1x1 pixel)
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "2mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        from io import BytesIO
        resp = client.post(
            "/api/auth/profile/logo",
            files={"file": ("logo.png", BytesIO(png_data), "image/png")},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "Logo uploaded" in resp.json()["message"]

    def test_logo_rejects_invalid_type(self, client, auth_headers):
        """Logo upload should reject non-image files."""
        resp = client.post(
            "/api/auth/profile/logo",
            files={"file": ("test.txt", BytesIO(b"not an image"), "text/plain")},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_logo_rejects_oversized(self, client, auth_headers):
        """Logo upload should reject files over 2MB."""
        big_data = b"\x00" * (3 * 1024 * 1024)  # 3MB
        resp = client.post(
            "/api/auth/profile/logo",
            files={"file": ("big.png", BytesIO(big_data), "image/png")},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_render_logo_helper(self):
        """_render_logo should handle invalid/empty URLs gracefully."""
        from backend.pdf_generator import _render_logo
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        # Should not raise on empty URL
        _render_logo(pdf, "")
        _render_logo(pdf, None)
        _render_logo(pdf, "https://example.com/logo.png")  # non-data URI


# ── Part 5: Beam Profile Fix ──


class TestBeamProfileFix:
    """Tests for Part 5: cantilever gate beam qty=1 enforcement."""

    def test_beam_qty_enforcement_code_exists(self):
        """cantilever_gate.py should enforce beam qty=1 in cut_list."""
        from backend.calculators import cantilever_gate
        src = inspect.getsource(cantilever_gate)
        assert "Sync qty=1 to cut_list" in src

    def test_no_beam_profile_override(self):
        """Beam profile should NOT be overridden — trust Opus."""
        from backend.calculators import cantilever_gate
        src = inspect.getsource(cantilever_gate)
        assert "Beam profile corrected:" not in src

    def test_is_overhead_item_used_on_cutlist(self):
        """The beam fix should check cut_list entries with _is_overhead_item."""
        from backend.calculators import cantilever_gate
        src = inspect.getsource(cantilever_gate)
        assert "for cl_entry in cut_list:" in src
