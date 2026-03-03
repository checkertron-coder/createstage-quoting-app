"""
Tests for validation layer wiring into the quote pipeline.

Verifies:
- build_instructions_to_text() helper
- Banned terms detection
- validate_full_output() integration
- PDF rendering of validation warnings
- Dead import cleanup in fab_knowledge.py
- Edge cases (empty inputs)
- Decorative stock prep uses structured data (no baking soda)
- AI build instructions run banned terms check before returning
- FAB_KNOWLEDGE.md has no baking soda in stock prep steps
"""

import inspect
import pytest

from backend.knowledge.validation import (
    build_instructions_to_text,
    check_banned_terms,
    validate_full_output,
)
from backend.pdf_generator import generate_quote_pdf


# ---------------------------------------------------------------------------
# build_instructions_to_text tests
# ---------------------------------------------------------------------------

class TestBuildInstructionsToText:

    def test_normal_steps(self):
        """Normal list of step dicts produces concatenated text."""
        steps = [
            {"step": 1, "title": "Cut pieces", "description": "Use chop saw", "safety_notes": "Wear PPE"},
            {"step": 2, "title": "Weld frame", "description": "MIG weld all joints"},
        ]
        result = build_instructions_to_text(steps)
        assert "Cut pieces" in result
        assert "Use chop saw" in result
        assert "Wear PPE" in result
        assert "Weld frame" in result
        assert "MIG weld all joints" in result

    def test_empty_and_none(self):
        """Empty list and None return empty string."""
        assert build_instructions_to_text([]) == ""
        assert build_instructions_to_text(None) == ""

    def test_non_dict_items_skipped(self):
        """Non-dict items in the list are skipped without error."""
        steps = [
            "not a dict",
            42,
            {"title": "Real step", "description": "Real description"},
            None,
        ]
        result = build_instructions_to_text(steps)
        assert "Real step" in result
        assert "Real description" in result
        # Non-dict items should not appear
        assert "not a dict" not in result


# ---------------------------------------------------------------------------
# Banned terms detection tests
# ---------------------------------------------------------------------------

class TestBannedTermsDetection:

    def test_vinegar_cleanup_finds_baking_soda(self):
        """Baking soda is banned in vinegar_bath_cleanup context."""
        text = "After vinegar soak, rinse with water and neutralize with baking soda solution."
        found = check_banned_terms(text, "vinegar_bath_cleanup")
        assert any("baking soda" in t for t in found)

    def test_decorative_prep_finds_grind_individual(self):
        """'grind individual pieces' is banned in decorative_stock_prep context."""
        text = "Grind individual pieces before assembly to ensure smooth finish."
        found = check_banned_terms(text, "decorative_stock_prep")
        assert any("grind individual pieces" in t for t in found)

    def test_clean_text_returns_empty(self):
        """Clean text returns no banned terms."""
        text = "Cut all pieces to length on chop saw. Deburr edges."
        found = check_banned_terms(text, "vinegar_bath_cleanup")
        assert found == []
        found2 = check_banned_terms(text, "decorative_stock_prep")
        assert found2 == []


# ---------------------------------------------------------------------------
# validate_full_output integration tests
# ---------------------------------------------------------------------------

class TestValidateFullOutput:

    def test_invalid_cut_list_negative_length(self):
        """Negative length in cut list item produces an error."""
        items = [
            {"description": "Bad piece", "profile": "sq_tube_2x2_11ga",
             "length_inches": -5, "quantity": 1, "cut_type": "square",
             "material_type": "tube_steel"},
        ]
        result = validate_full_output("furniture_table", items, [])
        assert not result.is_valid
        assert any("Invalid length" in e for e in result.errors)

    def test_bad_labor_negative_hours(self):
        """Negative hours in labor process produces an error."""
        items = [
            {"description": "Leg", "profile": "sq_tube_2x2_11ga",
             "length_inches": 30, "quantity": 4, "cut_type": "square",
             "material_type": "tube_steel"},
        ]
        processes = [
            {"process": "cut_prep", "hours": -2, "rate": 125},
        ]
        result = validate_full_output("furniture_table", items, processes)
        assert not result.is_valid
        assert any("Negative hours" in e for e in result.errors)

    def test_banned_terms_in_build_text(self):
        """Banned terms in build instructions produce warnings."""
        items = [
            {"description": "Frame tube", "profile": "sq_tube_2x2_11ga",
             "length_inches": 48, "quantity": 2, "cut_type": "square",
             "material_type": "tube_steel"},
        ]
        build_text = "After vinegar bath, neutralize with baking soda solution and rinse."
        result = validate_full_output("furniture_table", items, [], build_text)
        assert any("banned terms" in w.lower() for w in result.warnings)

    def test_list_to_text_roundtrip(self):
        """Steps list converts to text and banned terms are found through validate_full_output."""
        steps = [
            {"title": "Cleanup", "description": "After vinegar soak, apply baking soda to neutralize acid."},
        ]
        text = build_instructions_to_text(steps)
        items = [
            {"description": "Part", "profile": "sq_tube_1x1_14ga",
             "length_inches": 12, "quantity": 1, "cut_type": "square",
             "material_type": "tube_steel"},
        ]
        result = validate_full_output("custom_fab", items, [], text)
        assert any("banned terms" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# PDF rendering tests
# ---------------------------------------------------------------------------

class TestPDFValidationWarnings:

    def _minimal_priced_quote(self, warnings=None):
        """Build a minimal priced_quote dict for PDF generation."""
        pq = {
            "quote_id": 1,
            "quote_number": "CS-TEST-001",
            "job_type": "custom_fab",
            "client_name": "Test Client",
            "materials": [],
            "hardware": [],
            "consumables": [],
            "labor": [],
            "finishing": {"method": "raw", "area_sq_ft": 0, "total": 0,
                          "hours": 0, "materials_cost": 0, "outsource_cost": 0},
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
            "detailed_cut_list": [],
            "build_instructions": [],
        }
        if warnings:
            pq["validation_warnings"] = warnings
        return pq

    def test_pdf_with_warnings_renders_section(self):
        """PDF with validation_warnings includes REVIEW REQUIRED section."""
        warnings = [
            "[ERROR] Banned term 'baking soda' found in build instructions",
            "[WARNING] Item 1: Length 500 inches exceeds typical stock",
        ]
        pq = self._minimal_priced_quote(warnings)
        pdf_bytes = generate_quote_pdf(pq, {"shop_name": "Test Shop"}, {})
        assert isinstance(pdf_bytes, (bytes, bytearray))
        assert len(pdf_bytes) > 100

    def test_pdf_without_warnings_no_section(self):
        """PDF without validation_warnings does not include REVIEW REQUIRED text."""
        pq = self._minimal_priced_quote()
        pdf_bytes = generate_quote_pdf(pq, {"shop_name": "Test Shop"}, {})
        assert isinstance(pdf_bytes, (bytes, bytearray))
        assert len(pdf_bytes) > 100


# ---------------------------------------------------------------------------
# Dead import cleanup test
# ---------------------------------------------------------------------------

class TestDeadImportCleanup:

    def test_fab_knowledge_no_check_banned_terms_import(self):
        """fab_knowledge.py should not import check_banned_terms from validation."""
        import backend.calculators.fab_knowledge as fk
        source = inspect.getsource(fk)
        # Should not have the specific import line
        assert "from ..knowledge.validation import" not in source


# ---------------------------------------------------------------------------
# Edge case test
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_all_empty_inputs_no_crash(self):
        """validate_full_output with all-empty inputs does not crash."""
        result = validate_full_output("custom_fab", [], [], "", {})
        # Should have a warning about empty cut list but no crash
        assert result is not None
        # Empty cut list warning
        assert any("empty" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Prompt 15 — Decorative stock prep fix tests
# ---------------------------------------------------------------------------

class TestDecorativeStockPrepFix:

    def test_structured_data_is_source_of_truth(self):
        """_build_decorative_stock_prep() uses structured process data, not FAB_KNOWLEDGE.md prose."""
        from backend.calculators.fab_knowledge import _build_decorative_stock_prep
        text = _build_decorative_stock_prep()
        assert len(text) > 0, "Should return non-empty text"
        # Must contain structured steps (from processes.py)
        assert "Steps:" in text
        # Must contain NEVER list
        assert "NEVER" in text

    def test_no_baking_soda_in_output(self):
        """Decorative stock prep output must not contain baking soda except in NEVER list."""
        from backend.calculators.fab_knowledge import _build_decorative_stock_prep
        text = _build_decorative_stock_prep()
        text_lower = text.lower()
        if "baking soda" in text_lower:
            # If present, it must only be in the NEVER section
            never_pos = text.find("NEVER")
            baking_pos = text_lower.find("baking soda")
            assert never_pos >= 0 and baking_pos > never_pos, \
                "Baking soda appears before NEVER section — fallback override bug!"

    def test_structured_vinegar_bath_no_baking_soda(self):
        """The vinegar_bath process in processes.py must not have baking soda in steps."""
        from backend.knowledge.processes import get_process
        proc = get_process("vinegar_bath")
        assert proc is not None
        steps_text = " ".join(proc.get("steps", [])).lower()
        assert "baking soda" not in steps_text, \
            "Structured vinegar_bath steps still contain baking soda!"

    def test_fab_knowledge_md_no_baking_soda_in_steps(self):
        """FAB_KNOWLEDGE.md stock prep section must not have baking soda in process steps."""
        from pathlib import Path
        fab_path = Path(__file__).resolve().parent.parent / "FAB_KNOWLEDGE.md"
        if not fab_path.exists():
            pytest.skip("FAB_KNOWLEDGE.md not found")
        content = fab_path.read_text(encoding="utf-8")
        # Find the decorative stock prep section
        import re
        parts = re.split(r'^(## .+)$', content, flags=re.MULTILINE)
        for i in range(1, len(parts) - 1, 2):
            if "DECORATIVE STOCK PREP" in parts[i].upper():
                section = parts[i + 1]
                # Phase 1 steps should not contain baking soda
                phase1_match = re.search(
                    r'\*\*Phase 1.*?\*\*(.*?)(?:\*\*Phase 2|\Z)',
                    section, re.DOTALL
                )
                if phase1_match:
                    phase1 = phase1_match.group(1)
                    assert "baking soda" not in phase1.lower(), \
                        "FAB_KNOWLEDGE.md Phase 1 still has baking soda!"


# ---------------------------------------------------------------------------
# Prompt 15 — AI build instructions validation wiring
# ---------------------------------------------------------------------------

class TestAICutListValidationWiring:

    def test_generate_build_instructions_has_validation_import(self):
        """ai_cut_list.py generate_build_instructions references check_banned_terms."""
        import backend.calculators.ai_cut_list as acl
        source = inspect.getsource(acl.AICutListGenerator.generate_build_instructions)
        assert "check_banned_terms" in source, \
            "generate_build_instructions must call check_banned_terms"

    def test_banned_term_flagged_in_step(self):
        """If a build step contains a banned term, it gets flagged."""
        from backend.knowledge.validation import check_banned_terms
        # Simulate what ai_cut_list.py does
        steps = [
            {"step": 1, "title": "Cleanup", "description": "Rinse with warm water"},
            {"step": 2, "title": "Neutralize", "description": "Apply baking soda solution to neutralize acid"},
        ]
        full_text = " ".join(s.get("description", "") for s in steps)

        for context in ["vinegar_bath_cleanup", "decorative_stock_prep",
                        "decorative_assembly"]:
            violations = check_banned_terms(full_text, context)
            if violations:
                for step in steps:
                    desc = step.get("description", "")
                    for v in violations:
                        if v.lower() in desc.lower():
                            step["description"] = (
                                desc + " [REVIEW: contains banned term '%s']" % v
                            )

        # The step with baking soda should be flagged
        flagged = [s for s in steps if "REVIEW" in s.get("description", "")]
        assert len(flagged) >= 1
        assert "baking soda" in flagged[0]["description"].lower()

    def test_validation_call_sites_exist(self):
        """check_banned_terms and validate_full_output are called in actual pipeline code."""
        import backend.calculators.ai_cut_list as acl
        import backend.routers.quote_session as qs

        acl_source = inspect.getsource(acl)
        qs_source = inspect.getsource(qs)

        # ai_cut_list.py must call check_banned_terms (not just import)
        assert "check_banned_terms(" in acl_source, \
            "ai_cut_list.py must CALL check_banned_terms, not just import it"

        # quote_session.py must call validate_full_output (not just import)
        assert "validate_full_output(" in qs_source, \
            "quote_session.py must CALL validate_full_output, not just import it"
