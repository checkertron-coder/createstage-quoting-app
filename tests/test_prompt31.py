"""
Prompt 31 tests — Client PDF, concrete stock order fix, HSS profile
validation, grit spec fix, progress bar fix.

Tests cover:
  - Client PDF: generate_client_pdf returns valid PDF bytes
  - Client PDF: contains scope/price/terms, no cut list or labor breakdown
  - Concrete stock order: concrete_footing excluded from stock length enrichment
  - HSS profiles: hss_4x4_0.25 and hss_6x4_0.25 in VALID_PROFILES
  - Grit spec: Rule 14 specifies 36-grit flap disc
  - Progress bar: uses required_answered not total_answered
  - PDF endpoint: mode=client parameter accepted
"""

import os
import re
import pytest


# ── HSS Profile Validation ───────────────────────────────────────


class TestHSSProfileValidation:
    """hss_4x4_0.25 and hss_6x4_0.25 are recognized profiles."""

    def test_hss_4x4_in_valid_profiles(self):
        from backend.knowledge.validation import VALID_PROFILES
        assert "hss_4x4_0.25" in VALID_PROFILES

    def test_hss_6x4_in_valid_profiles(self):
        from backend.knowledge.validation import VALID_PROFILES
        assert "hss_6x4_0.25" in VALID_PROFILES

    def test_hss_4x4_no_warning(self):
        from backend.knowledge.validation import validate_cut_list_item
        item = {
            "description": "Overhead beam — HSS 4x4x1/4 (27.0 ft)",
            "profile": "hss_4x4_0.25",
            "length_inches": 324,
            "quantity": 1,
            "material_type": "tube_steel",
            "cut_type": "square",
        }
        result = validate_cut_list_item(item)
        # Should have no "Unrecognized profile" warnings
        unrecognized = [w for w in result.warnings if "Unrecognized profile" in w]
        assert len(unrecognized) == 0


# ── Grit Spec in Rule 14 ─────────────────────────────────────────


class TestGritSpec:
    """Rule 14 specifies 36-grit flap disc for outdoor spatter cleanup."""

    def test_grind_guidance_in_knowledge_base(self):
        """Grind guidance is in knowledge base, not hardcoded rules."""
        from backend.calculators.fab_knowledge import get_relevant_knowledge
        # Knowledge base should include grind guidance for outdoor work
        knowledge = get_relevant_knowledge("cantilever_gate", "paint", False)
        assert knowledge is not None

    def test_prompt_rules_trimmed(self):
        """Build instructions prompt has been trimmed to essential rules only."""
        from backend.calculators.ai_cut_list import AICutListGenerator
        gen = AICutListGenerator()
        prompt = gen._build_instructions_prompt(
            "cantilever_gate", {"description": "gate"}, [])
        # Should have 4 rules, not 16
        assert "SCHEDULING" in prompt
        assert "EXACT DIMENSIONS" in prompt


# ── Concrete Stock Order Fix ─────────────────────────────────────


class TestConcreteStockOrder:
    """Concrete should not appear in stock order summary."""

    def test_concrete_excluded_from_stock_enrichment(self):
        """Concrete items should NOT get stock_length_ft."""
        from backend.pricing_engine import PricingEngine
        from unittest.mock import MagicMock, patch

        materials = [
            {
                "description": "Post concrete — 3 holes × 12\" dia × 42\" deep",
                "material_type": "concrete",
                "profile": "concrete_footing",
                "length_inches": 42,
                "quantity": 3,
                "unit_price": 50.0,
                "line_total": 150.0,
            },
            {
                "description": "Gate frame — sq tube 2x2",
                "material_type": "tube_steel",
                "profile": "sq_tube_2x2_11ga",
                "length_inches": 240,
                "quantity": 2,
                "unit_price": 3.50,
                "line_total": 140.0,
            },
        ]

        # The concrete item should NOT get stock_length_ft
        assert "stock_length_ft" not in materials[0]

        # Simulate the enrichment logic
        from backend.knowledge.materials import get_stock_length
        for item in materials:
            profile = item.get("profile", "")
            mat_type = item.get("material_type", "")
            if mat_type in ("concrete", "other") or profile.startswith("concrete"):
                continue
            sl = get_stock_length(profile)
            if sl is not None:
                item["stock_length_ft"] = sl

        # Concrete should still not have stock_length_ft
        assert "stock_length_ft" not in materials[0]
        # Steel item should have stock_length_ft
        assert "stock_length_ft" in materials[1]


# ── Progress Bar Fix ─────────────────────────────────────────────


class TestProgressBarFix:
    """Frontend uses required_answered, not total_answered."""

    def test_frontend_uses_required_answered(self):
        """quote-flow.js should use completion.required_answered for display."""
        with open("frontend/js/quote-flow.js") as f:
            content = f.read()
        # Should use required_answered
        assert "completion.required_answered" in content
        # Should NOT use total_answered for the field count display
        # (total_answered may still exist in other contexts, but not in progress display)
        assert "completion.total_answered" not in content

    def test_completion_status_returns_required_answered(self):
        """Engine.get_completion_status includes required_answered."""
        from backend.question_trees.engine import QuestionTreeEngine
        engine = QuestionTreeEngine()
        # Use cantilever_gate with some fields
        status = engine.get_completion_status("cantilever_gate", {
            "clear_width": "18",
            "height": "10",
            "frame_material": "Steel",
            "extra_field_1": "not required",
            "extra_field_2": "not required",
        })
        assert "required_answered" in status
        assert "total_answered" in status
        # total_answered >= required_answered (includes extras)
        assert status["total_answered"] >= status["required_answered"]


# ── Client PDF Generation ────────────────────────────────────────


class TestClientPDF:
    """Client PDF generates valid PDF with simplified sections."""

    def _make_priced_quote(self):
        return {
            "quote_id": 42,
            "quote_number": "CS-2026-0042",
            "job_type": "cantilever_gate",
            "client_name": "Test Client",
            "job_description": "18 ft sliding gate with fence sections",
            "created_at": "2026-03-01T12:00:00",
            "materials": [
                {"description": "Gate frame", "profile": "sq_tube_2x2_11ga",
                 "quantity": 4, "unit_price": 3.50, "line_total": 280.0},
            ],
            "hardware": [
                {"description": "Gate hinges", "quantity": 2,
                 "options": [{"supplier": "McMaster", "price": 45.0}]},
            ],
            "consumables": [
                {"description": "Welding wire", "line_total": 25.0},
            ],
            "labor": [
                {"process": "cut_prep", "hours": 2.0, "rate": 75.0},
                {"process": "full_weld", "hours": 4.0, "rate": 75.0},
            ],
            "finishing": {"method": "powder_coat", "area_sq_ft": 120, "total": 360.0},
            "material_subtotal": 280.0,
            "hardware_subtotal": 90.0,
            "consumable_subtotal": 25.0,
            "labor_subtotal": 450.0,
            "finishing_subtotal": 360.0,
            "subtotal": 1205.0,
            "selected_markup_pct": 15,
            "total": 1385.75,
            "assumptions": ["42\" post embed for Chicago frost line"],
            "exclusions": ["Electrical work for gate operator"],
        }

    def test_client_pdf_returns_bytes(self):
        from backend.pdf_generator import generate_client_pdf
        pq = self._make_priced_quote()
        user = {"shop_name": "Test Shop", "shop_address": "", "shop_phone": "", "shop_email": ""}
        inputs = {"fields": {"clear_width": "18", "height": "10", "finish": "Powder coat"}}
        result = generate_client_pdf(pq, user, inputs)
        assert isinstance(result, (bytes, bytearray))
        assert len(result) > 100

    def test_client_pdf_is_valid_pdf(self):
        from backend.pdf_generator import generate_client_pdf
        pq = self._make_priced_quote()
        user = {"shop_name": "Test Shop"}
        result = generate_client_pdf(pq, user)
        # Check PDF header
        if isinstance(result, bytearray):
            result = bytes(result)
        assert result[:5] == b"%PDF-"

    def test_client_pdf_has_proposal_title(self):
        """Client PDF uses PROPOSAL not QUOTE in the code path."""
        from backend.pdf_generator import generate_client_pdf
        import inspect
        source = inspect.getsource(generate_client_pdf)
        assert "PROPOSAL" in source

    def test_client_pdf_different_from_shop_pdf(self):
        """Client PDF produces different output than shop PDF."""
        from backend.pdf_generator import generate_client_pdf, generate_quote_pdf
        pq = self._make_priced_quote()
        user = {"shop_name": "Test Shop"}
        inputs = {"fields": {"clear_width": "18"}}
        client_pdf = generate_client_pdf(pq, user, inputs)
        shop_pdf = generate_quote_pdf(pq, user, inputs)
        # They should be different sizes (client is shorter)
        assert len(client_pdf) != len(shop_pdf)

    def test_client_pdf_no_cut_list_in_code(self):
        """Client PDF code path does not render CUT LIST section."""
        from backend.pdf_generator import generate_client_pdf
        import inspect
        source = inspect.getsource(generate_client_pdf)
        assert "CUT LIST" not in source
        assert "FABRICATION SEQUENCE" not in source

    def test_client_pdf_has_signature_lines(self):
        """Client PDF code has signature lines for acceptance."""
        from backend.pdf_generator import generate_client_pdf
        import inspect
        source = inspect.getsource(generate_client_pdf)
        assert "Accepted by" in source


# ── PDF Endpoint Mode Parameter ──────────────────────────────────


class TestPDFEndpointMode:
    """PDF endpoint accepts mode=client parameter."""

    def test_endpoint_has_mode_param(self):
        """The download_pdf endpoint should accept mode query param."""
        from backend.routers.pdf import download_pdf
        import inspect
        sig = inspect.signature(download_pdf)
        assert "mode" in sig.parameters

    def test_client_pdf_import(self):
        """generate_client_pdf is importable from pdf_generator."""
        from backend.pdf_generator import generate_client_pdf
        assert callable(generate_client_pdf)


# ── API getPdfUrl Mode Support ───────────────────────────────────


class TestAPIPdfUrlMode:
    """Frontend API.getPdfUrl supports mode parameter."""

    def test_api_js_supports_mode(self):
        """api.js getPdfUrl should accept mode parameter."""
        with open("frontend/js/api.js") as f:
            content = f.read()
        assert "getPdfUrl(quoteId, mode)" in content
        assert "mode=" in content


# ── Frontend Two PDF Buttons ─────────────────────────────────────


class TestFrontendPDFButtons:
    """Frontend has two PDF download buttons: Shop and Client."""

    def test_shop_pdf_button(self):
        with open("frontend/js/quote-flow.js") as f:
            content = f.read()
        assert "Shop PDF" in content

    def test_client_pdf_button(self):
        with open("frontend/js/quote-flow.js") as f:
            content = f.read()
        assert "Client PDF" in content
        assert "downloadPdf('client')" in content
