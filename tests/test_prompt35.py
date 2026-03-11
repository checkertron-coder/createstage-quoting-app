"""
Tests for Prompt 35: Field Extraction Fix.

Covers:
- AC-1: Assertive extraction prompt (no >90% confidence language)
- AC-2: Post-extraction normalization (_normalize_extracted_fields, _match_option)
- AC-3: Logging wired into extraction path
- Branching regression: normalized values must trigger correct branches
"""

import pytest


# =====================================================================
# AC-1 — Extraction prompt is assertive
# =====================================================================

class TestExtractionPromptAssertive:
    def test_no_90_confidence_language(self):
        """Prompt must NOT contain >90% confidence hedging."""
        from backend.question_trees.engine import _build_extraction_prompt
        prompt = _build_extraction_prompt(
            "cantilever_gate", "Cantilever Gate",
            "10 foot gate", "- clear_width: Width?",
        )
        assert ">90%" not in prompt
        assert "90% confident" not in prompt

    def test_prompt_demands_exact_option_strings(self):
        """Prompt must instruct to return EXACT option strings."""
        from backend.question_trees.engine import _build_extraction_prompt
        prompt = _build_extraction_prompt(
            "cantilever_gate", "Cantilever Gate",
            "gate with motor", "- has_motor: Motor? Options: Yes, No",
        )
        assert "EXACT option string" in prompt

    def test_prompt_has_aggressive_extraction_language(self):
        """Prompt should say to be aggressive / extract everything stated."""
        from backend.question_trees.engine import _build_extraction_prompt
        prompt = _build_extraction_prompt(
            "cantilever_gate", "Cantilever Gate",
            "gate", "- clear_width: Width?",
        )
        assert "AGGRESSIVE" in prompt or "EXTRACT every" in prompt

    def test_prompt_has_choice_field_examples(self):
        """Prompt includes examples mapping customer words to exact options."""
        from backend.question_trees.engine import _build_extraction_prompt
        prompt = _build_extraction_prompt(
            "cantilever_gate", "Cantilever Gate",
            "gate", "- finish: Finish?",
        )
        assert "Paint (in-house)" in prompt
        assert "Pickets (vertical bars)" in prompt


# =====================================================================
# AC-2 — Normalization (_match_option and _normalize_extracted_fields)
# =====================================================================

class TestMatchOption:
    def test_exact_match(self):
        """Exact string returns as-is."""
        from backend.question_trees.engine import _match_option
        options = ["Yes", "No — manual operation", "Not sure — show me options"]
        assert _match_option("Yes", options) == "Yes"

    def test_case_insensitive_match(self):
        """Case-insensitive 'yes' -> 'Yes'."""
        from backend.question_trees.engine import _match_option
        options = ["Yes", "No — manual operation"]
        assert _match_option("yes", options) == "Yes"

    def test_substring_match_single(self):
        """'paint' matches 'Paint (in-house)' when only one option contains it."""
        from backend.question_trees.engine import _match_option
        options = [
            "Powder coat (most durable, outsourced)",
            "Paint (in-house)",
            "Clear coat (shows steel grain)",
            "Galvanized (hot-dip)",
            "Raw steel (no finish)",
        ]
        assert _match_option("paint", options) == "Paint (in-house)"

    def test_substring_match_powder_coat(self):
        """'powder coat' matches 'Powder coat (most durable, outsourced)'."""
        from backend.question_trees.engine import _match_option
        options = [
            "Powder coat (most durable, outsourced)",
            "Paint (in-house)",
            "Clear coat (shows steel grain)",
        ]
        assert _match_option("powder coat", options) == "Powder coat (most durable, outsourced)"

    def test_substring_match_pickets(self):
        """'pickets' matches 'Pickets (vertical bars)'."""
        from backend.question_trees.engine import _match_option
        options = [
            "Pickets (vertical bars)",
            "Flat bar vertical",
            "Expanded metal",
        ]
        assert _match_option("pickets", options) == "Pickets (vertical bars)"

    def test_no_match_returns_none(self):
        """Completely unrelated value returns None."""
        from backend.question_trees.engine import _match_option
        options = ["Yes", "No — manual operation"]
        assert _match_option("banana", options) is None

    def test_word_overlap_match(self):
        """'full installation' matches option containing those words."""
        from backend.question_trees.engine import _match_option
        options = [
            "Full installation (gate + posts + concrete)",
            "Gate install only (posts already set)",
            "Shop pickup (no installation)",
        ]
        result = _match_option("full installation", options)
        assert result == "Full installation (gate + posts + concrete)"

    def test_pickup_match(self):
        """'pickup' matches 'Shop pickup (no installation)'."""
        from backend.question_trees.engine import _match_option
        options = [
            "Full installation (gate + posts + concrete)",
            "Gate install only (posts already set)",
            "Shop pickup (no installation)",
            "Delivery only (no installation)",
        ]
        result = _match_option("pickup", options)
        assert result == "Shop pickup (no installation)"


class TestNormalizeExtractedFields:
    def _get_cantilever_questions(self):
        from backend.question_trees.engine import QuestionTreeEngine
        engine = QuestionTreeEngine()
        tree = engine.load_tree("cantilever_gate")
        return tree["questions"]

    def test_measurement_passes_through(self):
        """Measurement values are not normalized."""
        from backend.question_trees.engine import _normalize_extracted_fields
        questions = self._get_cantilever_questions()
        extracted = {"clear_width": "10", "height": "6"}
        result = _normalize_extracted_fields(extracted, questions)
        assert result["clear_width"] == "10"
        assert result["height"] == "6"

    def test_choice_normalized_to_exact(self):
        """Choice value 'yes' normalized to exact option 'Yes'."""
        from backend.question_trees.engine import _normalize_extracted_fields
        questions = self._get_cantilever_questions()
        extracted = {"has_motor": "yes"}
        result = _normalize_extracted_fields(extracted, questions)
        assert result["has_motor"] == "Yes"

    def test_choice_paint_normalized(self):
        """'paint' kept as-is for finish (bypass fuzzy match)."""
        from backend.question_trees.engine import _normalize_extracted_fields
        questions = self._get_cantilever_questions()
        extracted = {"finish": "paint"}
        result = _normalize_extracted_fields(extracted, questions)
        # P45: finish fields bypass fuzzy matching — raw value preserved.
        # _normalize_finish_type() handles "paint" → "paint" downstream.
        assert result["finish"] == "paint"

    def test_choice_powder_coat_normalized(self):
        """'powder coat' kept as-is for finish (bypass fuzzy match)."""
        from backend.question_trees.engine import _normalize_extracted_fields
        questions = self._get_cantilever_questions()
        extracted = {"finish": "powder coat"}
        result = _normalize_extracted_fields(extracted, questions)
        # P45: finish fields bypass fuzzy matching — raw value preserved.
        # _normalize_finish_type() handles "powder coat" → "powder_coat" downstream.
        assert result["finish"] == "powder coat"

    def test_unknown_field_dropped(self):
        """Field not in question tree is dropped."""
        from backend.question_trees.engine import _normalize_extracted_fields
        questions = self._get_cantilever_questions()
        extracted = {"nonexistent_field": "value"}
        result = _normalize_extracted_fields(extracted, questions)
        assert "nonexistent_field" not in result

    def test_unmatched_choice_dropped(self):
        """Choice value with no match is dropped entirely."""
        from backend.question_trees.engine import _normalize_extracted_fields
        questions = self._get_cantilever_questions()
        extracted = {"has_motor": "banana"}
        result = _normalize_extracted_fields(extracted, questions)
        # "banana" has no word overlap with any option in has_motor
        # Options: ["Yes", "No — manual operation", "Not sure — show me options"]
        # Actually "banana" might match via word overlap... let's check
        # No, "banana" won't match any word in those options
        assert "has_motor" not in result

    def test_multiple_fields_normalized(self):
        """Multiple fields all get normalized correctly."""
        from backend.question_trees.engine import _normalize_extracted_fields
        questions = self._get_cantilever_questions()
        extracted = {
            "clear_width": "12",
            "height": "6",
            "has_motor": "Yes",
            "finish": "paint",
            "installation": "full installation",
            "infill_type": "pickets",
        }
        result = _normalize_extracted_fields(extracted, questions)
        assert result["clear_width"] == "12"
        assert result["height"] == "6"
        assert result["has_motor"] == "Yes"
        assert result["finish"] == "paint"  # P45: finish bypasses fuzzy match
        assert "installation" in result  # should match Full installation option
        assert result["infill_type"] == "Pickets (vertical bars)"


# =====================================================================
# Branching regression — normalized values trigger correct branches
# =====================================================================

class TestBranchingRegression:
    def test_normalized_has_motor_triggers_branch(self):
        """has_motor='Yes' (after normalization) should activate motor_brand."""
        from backend.question_trees.engine import QuestionTreeEngine
        engine = QuestionTreeEngine()
        answered = {"has_motor": "Yes"}
        next_qs = engine.get_next_questions("cantilever_gate", answered)
        next_ids = [q["id"] for q in next_qs]
        assert "motor_brand" in next_ids

    def test_normalized_infill_triggers_picket_branch(self):
        """infill_type='Pickets (vertical bars)' activates picket sub-questions."""
        from backend.question_trees.engine import QuestionTreeEngine
        engine = QuestionTreeEngine()
        answered = {"infill_type": "Pickets (vertical bars)"}
        next_qs = engine.get_next_questions("cantilever_gate", answered)
        next_ids = [q["id"] for q in next_qs]
        assert "picket_material" in next_ids
        assert "picket_spacing" in next_ids

    def test_normalized_finish_triggers_paint_branch(self):
        """finish='Paint (in-house)' activates paint_color sub-question."""
        from backend.question_trees.engine import QuestionTreeEngine
        engine = QuestionTreeEngine()
        answered = {"finish": "Paint (in-house)"}
        next_qs = engine.get_next_questions("cantilever_gate", answered)
        next_ids = [q["id"] for q in next_qs]
        assert "paint_color" in next_ids

    def test_raw_paint_would_fail_branch(self):
        """Verifies that un-normalized 'paint' does NOT trigger branch."""
        from backend.question_trees.engine import QuestionTreeEngine
        engine = QuestionTreeEngine()
        # "paint" is NOT an exact option — branches won't fire
        answered = {"finish": "paint"}
        next_qs = engine.get_next_questions("cantilever_gate", answered)
        next_ids = [q["id"] for q in next_qs]
        # paint_color should NOT appear because "paint" != "Paint (in-house)"
        assert "paint_color" not in next_ids


# =====================================================================
# AC-3 — Logging is wired in
# =====================================================================

class TestExtractionLogging:
    def test_logger_exists_in_module(self):
        """engine module has a logger configured."""
        from backend.question_trees import engine
        assert hasattr(engine, "logger")
        assert engine.logger.name == "backend.question_trees.engine"
