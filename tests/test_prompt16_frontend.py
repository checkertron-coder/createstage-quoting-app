"""
Tests for Prompt 16 — Frontend: Full Quote View + Hourly Rate Input + Missing Spec Prompts.

Verifies:
- Stock length lookup works for all profile shapes
- Pricing engine enriches materials with stock_length_ft
- Question tree gauge/wall thickness questions exist
- Question tree branching is valid (no broken depends_on)
"""

import json
from pathlib import Path

import pytest

from backend.knowledge.materials import (
    PROFILES,
    STOCK_LENGTHS,
    get_stock_length,
)
from backend.pricing_engine import PricingEngine


# ---------------------------------------------------------------------------
# Stock length tests
# ---------------------------------------------------------------------------

class TestStockLengths:

    def test_stock_lengths_has_all_shapes(self):
        """Every shape that appears in PROFILES has a STOCK_LENGTHS entry."""
        shapes_in_profiles = set(p["shape"] for p in PROFILES.values())
        for shape in shapes_in_profiles:
            assert shape in STOCK_LENGTHS, \
                "Shape '%s' found in PROFILES but not in STOCK_LENGTHS" % shape

    def test_stock_lengths_reasonable(self):
        """Stock lengths are either None (area-sold) or 18-26 feet."""
        for shape, length in STOCK_LENGTHS.items():
            if length is not None:
                assert 18 <= length <= 26, \
                    "%s stock length %s is outside reasonable range" % (shape, length)

    def test_get_stock_length_known_profile(self):
        """get_stock_length returns correct length for known profiles."""
        length = get_stock_length("sq_tube_2x2_11ga")
        assert length == 24  # square tube = 24ft

    def test_get_stock_length_unknown_profile(self):
        """get_stock_length returns 20 (default) for unknown profiles."""
        length = get_stock_length("totally_fake_profile_xyz")
        assert length == 20

    def test_get_stock_length_sheet_returns_none(self):
        """Sheet/plate profiles return None (sold by area)."""
        length = get_stock_length("sheet_16ga")
        assert length is None


# ---------------------------------------------------------------------------
# Pricing engine enrichment tests
# ---------------------------------------------------------------------------

class TestPricingEngineEnrichment:

    def test_materials_get_stock_length_ft(self):
        """Pricing engine adds stock_length_ft to material items."""
        pe = PricingEngine()
        session_data = {
            "session_id": "test-123",
            "job_type": "custom_fab",
            "fields": {},
            "material_list": {
                "items": [
                    {
                        "description": "2x2 sq tube",
                        "profile": "sq_tube_2x2_11ga",
                        "length_inches": 48,
                        "quantity": 4,
                        "unit_price": 3.50,
                        "line_total": 56.00,
                        "material_type": "tube_steel",
                        "cut_type": "square",
                        "waste_factor": 0.1,
                    },
                ],
                "hardware": [],
                "weld_linear_inches": 0,
                "total_sq_ft": 0,
                "assumptions": [],
            },
            "labor_estimate": {
                "processes": [
                    {"process": "cut_prep", "hours": 1.0, "rate": 125, "notes": ""},
                ],
                "total_hours": 1.0,
            },
            "finishing": {
                "method": "raw",
                "area_sq_ft": 0,
                "hours": 0,
                "materials_cost": 0,
                "outsource_cost": 0,
                "total": 0,
            },
        }
        user = {"id": 1, "shop_name": "Test", "markup_default": 15,
                "rate_inshop": 125, "rate_onsite": 145}

        result = pe.build_priced_quote(session_data, user)
        mat = result["materials"][0]
        assert "stock_length_ft" in mat
        assert mat["stock_length_ft"] == 24


# ---------------------------------------------------------------------------
# Question tree gauge/clarification tests
# ---------------------------------------------------------------------------

TREES_DIR = Path(__file__).resolve().parent.parent / "backend" / "question_trees" / "data"


class TestQuestionTreeClarification:

    def _load_tree(self, name):
        path = TREES_DIR / (name + ".json")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_furniture_table_has_tube_wall_thickness(self):
        """furniture_table tree has tube_wall_thickness question."""
        tree = self._load_tree("furniture_table")
        qids = [q["id"] for q in tree["questions"]]
        assert "tube_wall_thickness" in qids

    def test_custom_fab_has_material_gauge(self):
        """custom_fab tree has material_profile and material_gauge questions."""
        tree = self._load_tree("custom_fab")
        qids = [q["id"] for q in tree["questions"]]
        assert "material_profile" in qids
        assert "material_gauge" in qids

    def test_straight_railing_has_post_gauge(self):
        """straight_railing tree has post_gauge question."""
        tree = self._load_tree("straight_railing")
        qids = [q["id"] for q in tree["questions"]]
        assert "post_gauge" in qids

    def test_branches_reference_existing_questions(self):
        """All branch targets in question trees reference existing question IDs."""
        for tree_file in TREES_DIR.glob("*.json"):
            tree = json.loads(tree_file.read_text(encoding="utf-8"))
            qids = set(q["id"] for q in tree["questions"])
            for q in tree["questions"]:
                branches = q.get("branches")
                if not branches:
                    continue
                for option, targets in branches.items():
                    for target in targets:
                        assert target in qids, \
                            "%s: branch '%s' -> '%s' references unknown question ID" % (
                                tree_file.name, option, target
                            )

    def test_depends_on_references_existing_questions(self):
        """All depends_on fields reference existing question IDs."""
        for tree_file in TREES_DIR.glob("*.json"):
            tree = json.loads(tree_file.read_text(encoding="utf-8"))
            qids = set(q["id"] for q in tree["questions"])
            for q in tree["questions"]:
                dep = q.get("depends_on")
                if dep:
                    assert dep in qids, \
                        "%s: question '%s' depends_on unknown '%s'" % (
                            tree_file.name, q["id"], dep
                        )
