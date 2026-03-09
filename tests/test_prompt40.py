"""
Tests for Prompt 40 — 'Don't Skip the Good Questions'.

AC-1: Frontend question priority (JS logic — tested via session start API)
AC-2: Aluminum profiles in VALID_PROFILES validation whitelist
AC-3: Finish extraction catches "clear coat" variants from descriptions
AC-4: Solved by AC-1 (frontend fix is sufficient)
"""

import pytest


# ── AC-2: Profile coverage — every catalog key in VALID_PROFILES ─────────


class TestProfileCoverage:
    """Every profile in the pricing catalog must be in VALID_PROFILES."""

    def test_all_price_per_foot_keys_in_valid_profiles(self):
        """Every PRICE_PER_FOOT key exists in VALID_PROFILES."""
        from backend.calculators.material_lookup import PRICE_PER_FOOT
        from backend.knowledge.validation import VALID_PROFILES

        missing = set(PRICE_PER_FOOT.keys()) - VALID_PROFILES
        assert not missing, (
            "PRICE_PER_FOOT keys missing from VALID_PROFILES: %s" % sorted(missing)
        )

    def test_all_price_per_sqft_keys_in_valid_profiles(self):
        """Every PRICE_PER_SQFT key exists in VALID_PROFILES."""
        from backend.calculators.material_lookup import PRICE_PER_SQFT
        from backend.knowledge.validation import VALID_PROFILES

        missing = set(PRICE_PER_SQFT.keys()) - VALID_PROFILES
        assert not missing, (
            "PRICE_PER_SQFT keys missing from VALID_PROFILES: %s" % sorted(missing)
        )

    def test_aluminum_profiles_in_valid_profiles(self):
        """All 15 aluminum profile keys are whitelisted."""
        from backend.knowledge.validation import VALID_PROFILES

        al_profiles = [
            "al_sq_tube_1x1_0.125", "al_sq_tube_1.5x1.5_0.125",
            "al_sq_tube_2x2_0.125", "al_rect_tube_1x2_0.125",
            "al_angle_1.5x1.5x0.125", "al_angle_2x2x0.125",
            "al_flat_bar_1x0.125", "al_flat_bar_1.5x0.125",
            "al_flat_bar_2x0.25", "al_round_tube_1.5_0.125",
            "al_sheet_0.040", "al_sheet_0.063", "al_sheet_0.080",
            "al_sheet_0.125", "al_sheet_0.190",
        ]
        for profile in al_profiles:
            assert profile in VALID_PROFILES, (
                "Aluminum profile %r missing from VALID_PROFILES" % profile
            )


# ── AC-3: Finish extraction ─────────────────────────────────────────────


class TestFinishExtraction:
    """Finish normalization catches clear coat variants."""

    def test_clearcoat_recognized(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("clearcoat") == "clearcoat"

    def test_clear_coat_space_recognized(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("clear coat") == "clearcoat"

    def test_clear_coated_recognized(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("clear coated") == "clearcoat"

    def test_permalac_recognized(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("permalac") == "clearcoat"

    def test_lacquer_recognized(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("lacquer") == "clearcoat"

    def test_wax_recognized(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("wax") == "clearcoat"

    def test_extraction_prompt_has_finish_rule(self):
        """The extraction prompt includes finish mapping guidance."""
        from backend.question_trees.engine import _build_extraction_prompt
        field_desc = 'finish: Finish? (choice) Options: ["Raw", "Paint", "Clear coat"]'
        prompt = _build_extraction_prompt(
            "led_sign_custom", "LED Sign Custom",
            "Clear coated aluminum channel letters", field_desc,
        )
        assert "FINISH FIELD" in prompt
        assert "clear coat" in prompt.lower()


# ── AC-1: Question priority via API ──────────────────────────────────────


class TestQuestionPriority:
    """Session start returns next_questions — frontend must show them."""

    def test_session_start_returns_questions(self, client, guest_headers):
        """Starting a session returns next_questions for the job type."""
        resp = client.post("/api/session/start", json={
            "description": "Steel swing gate 10 ft wide 6 ft tall with paint finish",
            "job_type": "swing_gate",
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        questions = data.get("next_questions", [])
        # A swing gate always has questions (width, height, material, etc.)
        assert len(questions) > 0, "Expected questions for swing_gate"

    def test_led_sign_returns_questions(self, client, guest_headers):
        """LED sign with electronics keywords should get questions."""
        resp = client.post("/api/session/start", json={
            "description": "LED channel letter sign for restaurant facade",
            "job_type": "led_sign_custom",
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        questions = data.get("next_questions", [])
        assert len(questions) > 0, "Expected questions for led_sign_custom"


# ── No regressions ───────────────────────────────────────────────────────


class TestNoRegressions:
    """Existing behaviors still work after P40 changes."""

    def test_validation_still_catches_invalid_profile(self):
        """A totally invalid profile is still not in VALID_PROFILES."""
        from backend.knowledge.validation import VALID_PROFILES
        assert "nonexistent_profile_xyz" not in VALID_PROFILES

    def test_finishing_paint_still_works(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("paint") == "paint"

    def test_finishing_powder_coat_still_works(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("powder coat") == "powder_coat"

    def test_finishing_raw_still_works(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("raw") == "raw"

    def test_finishing_galvanized_still_works(self):
        from backend.finishing import FinishingBuilder
        fb = FinishingBuilder()
        assert fb._normalize_finish_type("hot-dip galvanized") == "galvanized"
