"""
Tests for Prompt 28: Simplified post-processor (trust AI, add only missing items),
enforced dimensions, Rule 14 expansion, surface prep solvent, bid upload UI.
"""

import os
import math

import pytest


# =====================================================================
# 1. Post detection — _is_post_item and _is_overhead_item helpers
# =====================================================================

class TestDetectionHelpers:
    def test_is_post_item_detects_various_post_descriptions(self):
        from backend.calculators.cantilever_gate import _is_post_item

        positive_cases = [
            {"description": "Gate post — 4\" pipe (10.5 ft)"},
            {"description": "Hinge post — sq tube 4x4"},
            {"description": "Latch post (terminal)"},
            {"description": "Strike post — 4\" pipe Sch 40"},
            {"description": "Terminal post for fence"},
        ]
        for item in positive_cases:
            assert _is_post_item(item), "Should detect: %s" % item["description"]

    def test_is_post_item_rejects_non_post_items(self):
        from backend.calculators.cantilever_gate import _is_post_item

        negative_cases = [
            {"description": "HSS 4x4 frame rail"},
            {"description": "Gate frame top rail"},
            {"description": "Overhead support beam"},
            {"description": "Picket — sq bar 3/4\""},
        ]
        for item in negative_cases:
            assert not _is_post_item(item), "Should not detect: %s" % item["description"]

    def test_is_overhead_item_detects_beams(self):
        from backend.calculators.cantilever_gate import _is_overhead_item

        positive = [
            {"description": "HSS 4x4x1/4 structural tube — overhead track (27.0 ft)"},
            {"description": "Overhead support beam — HSS 4x4x1/4"},
            {"description": "Header beam for gate"},
            {"description": "Track beam spanning posts"},
        ]
        for item in positive:
            assert _is_overhead_item(item), "Should detect: %s" % item["description"]


# =====================================================================
# 2. Simplified post-processor — trusts AI, adds only missing items
# =====================================================================

class TestSimplifiedPostProcessor:
    def _make_calc_and_fields(self):
        from backend.calculators.cantilever_gate import CantileverGateCalculator
        calc = CantileverGateCalculator()
        fields = {
            "clear_width": "18",
            "height": "6",
            "frame_size": '2" x 2"',
            "frame_gauge": "11 gauge",
            "post_size": '4" round pipe Sch 40',
            "post_count": "3 posts (standard)",
            "post_concrete": "Yes",
            "infill_type": "Pickets (vertical bars)",
            "bottom_guide": "No bottom guide (top-hung)",
            "adjacent_fence": "No",
            "finish": "Powder coat",
        }
        return calc, fields

    def test_does_not_add_posts_when_ai_included_them(self):
        """When AI includes posts, post-processor trusts them — no duplicates."""
        calc, fields = self._make_calc_and_fields()

        ai_items = [
            {
                "description": "Gate post — 4\" pipe Sch 40 (10.5 ft)",
                "material_type": "pipe",
                "profile": "pipe_4_sch40",
                "length_inches": 126.0,
                "quantity": 3,
                "unit_price": 50.0,
                "cut_type": "square",
                "waste_factor": 0.0,
                "line_total": 150.0,
            },
        ]
        ai_result = {
            "job_type": "cantilever_gate",
            "items": list(ai_items),
            "cut_list": [],
            "hardware": [],
            "total_weight_lbs": 500.0,
            "total_sq_ft": 200.0,
            "weld_linear_inches": 300.0,
            "assumptions": [],
        }

        result = calc._post_process_ai_result(ai_result, fields, [])

        post_items = [
            i for i in result["items"]
            if "post" in i.get("description", "").lower()
            and "concrete" not in i.get("description", "").lower()
            and "fence" not in i.get("description", "").lower()
        ]
        # Should be exactly the AI's posts, no extras added
        assert len(post_items) == 1
        assert post_items[0]["quantity"] == 3

    def test_adds_posts_when_ai_omitted_them(self):
        """When AI omits posts entirely, post-processor adds them."""
        calc, fields = self._make_calc_and_fields()

        ai_result = {
            "job_type": "cantilever_gate",
            "items": [
                {
                    "description": "Gate frame top rail",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_2x2_11ga",
                    "length_inches": 324.0,
                    "quantity": 1,
                    "unit_price": 100.0,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                    "line_total": 100.0,
                },
            ],
            "cut_list": [],
            "hardware": [],
            "total_weight_lbs": 200.0,
            "total_sq_ft": 100.0,
            "weld_linear_inches": 200.0,
            "assumptions": [],
        }

        result = calc._post_process_ai_result(ai_result, fields, [])

        post_items = [
            i for i in result["items"]
            if "post" in i.get("description", "").lower()
            and "concrete" not in i.get("description", "").lower()
        ]
        assert len(post_items) >= 1, "Should have added posts when AI omitted them"

    def test_does_not_add_overhead_when_ai_included_it(self):
        """When AI includes overhead beam, post-processor trusts it."""
        calc, fields = self._make_calc_and_fields()

        ai_result = {
            "job_type": "cantilever_gate",
            "items": [
                {
                    "description": "Overhead support beam — HSS 4x4 (27 ft)",
                    "material_type": "hss_structural_tube",
                    "profile": "hss_4x4_0.25",
                    "length_inches": 324.0,
                    "quantity": 1,
                    "unit_price": 200.0,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                    "line_total": 200.0,
                },
                {
                    "description": "Gate post — 4\" pipe (10.5 ft)",
                    "material_type": "pipe",
                    "profile": "pipe_4_sch40",
                    "length_inches": 126.0,
                    "quantity": 3,
                    "unit_price": 50.0,
                    "cut_type": "square",
                    "waste_factor": 0.0,
                    "line_total": 150.0,
                },
            ],
            "cut_list": [],
            "hardware": [],
            "total_weight_lbs": 500.0,
            "total_sq_ft": 200.0,
            "weld_linear_inches": 300.0,
            "assumptions": [],
        }

        result = calc._post_process_ai_result(ai_result, fields, [])

        overhead_items = [
            i for i in result["items"]
            if "overhead" in i.get("description", "").lower()
            or "support beam" in i.get("description", "").lower()
        ]
        # AI had 1, post-processor should NOT add another
        assert len(overhead_items) == 1, (
            "Should trust AI's overhead beam, got %d" % len(overhead_items))

    def test_trusts_ai_fence_items(self):
        """When AI includes fence items, post-processor trusts them entirely."""
        calc, fields = self._make_calc_and_fields()
        fields["adjacent_fence"] = "Yes — one side"
        fields["fence_side_1_length"] = "30"

        ai_result = {
            "job_type": "cantilever_gate",
            "items": [
                {
                    "description": "Gate post — pipe 4\" (10.5 ft)",
                    "material_type": "pipe",
                    "profile": "pipe_4_sch40",
                    "length_inches": 126.0,
                    "quantity": 3,
                    "unit_price": 50.0,
                    "cut_type": "square",
                    "waste_factor": 0.0,
                    "line_total": 150.0,
                },
                {
                    "description": "Fence line post — pipe 4\" (9.7 ft)",
                    "material_type": "pipe",
                    "profile": "pipe_4_sch40",
                    "length_inches": 116.0,
                    "quantity": 5,
                    "unit_price": 45.0,
                    "cut_type": "square",
                    "waste_factor": 0.0,
                    "line_total": 225.0,
                },
                {
                    "description": "Fence top rail — sq tube 2x2",
                    "material_type": "square_tubing",
                    "profile": "sq_tube_2x2_11ga",
                    "length_inches": 360.0,
                    "quantity": 1,
                    "unit_price": 80.0,
                    "cut_type": "square",
                    "waste_factor": 0.05,
                    "line_total": 80.0,
                },
                {
                    "description": "Fence pickets — sq bar 3/4\" × 55 pcs",
                    "material_type": "square_tubing",
                    "profile": "sq_bar_0.75",
                    "length_inches": 70.0,
                    "quantity": 55,
                    "unit_price": 5.0,
                    "cut_type": "square",
                    "waste_factor": 0.03,
                    "line_total": 275.0,
                },
            ],
            "cut_list": [],
            "hardware": [],
            "total_weight_lbs": 800.0,
            "total_sq_ft": 400.0,
            "weld_linear_inches": 500.0,
            "assumptions": [],
        }

        result = calc._post_process_ai_result(ai_result, fields, [])

        # AI included fence items, post-processor should NOT generate more
        fence_items = [
            i for i in result["items"]
            if "fence" in i.get("description", "").lower()
        ]
        # Should only have the 3 AI fence items, not a full regenerated set
        assert len(fence_items) == 3, (
            "Should trust AI fence items, got %d: %s"
            % (len(fence_items), [i["description"] for i in fence_items]))


# =====================================================================
# 3. Enforced dimensions — appears in prompt
# =====================================================================

class TestEnforcedDimensions:
    def test_enforced_dims_in_prompt(self):
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        enforced = {
            "opening_width": "18 ft",
            "gate_length": "27.0 ft (opening x 1.5)",
            "post_embed_depth": "42 inches (Chicago frost line)",
        }
        prompt = gen._build_instructions_prompt(
            "cantilever_gate", {"description": "test gate"}, [],
            enforced_dimensions=enforced)

        assert "ENFORCED DIMENSIONS" in prompt
        assert "18 ft" in prompt
        assert "27.0 ft" in prompt
        assert "42 inches" in prompt

    def test_no_enforced_dims_when_none(self):
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        prompt = gen._build_instructions_prompt(
            "cantilever_gate", {"description": "test gate"}, [],
            enforced_dimensions=None)

        assert "ENFORCED DIMENSIONS" not in prompt


# =====================================================================
# 4. Rule 14 expansion — progressive gritting ban
# =====================================================================

class TestRule14:
    def test_rule14_contains_progressive_gritting_ban(self):
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        prompt = gen._build_instructions_prompt(
            "cantilever_gate", {"description": "test gate"}, [])

        assert "progressive" in prompt.lower()
        assert "single pass" in prompt.lower()


# =====================================================================
# 5. Surface prep solvent
# =====================================================================

class TestSurfacePrepSolvent:
    def test_solvent_present_for_painted_jobs(self):
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        items = hs.estimate_consumables(500.0, 200.0, "paint")
        solvent = [i for i in items if "solvent" in i["description"].lower()]
        assert len(solvent) == 1
        assert solvent[0]["line_total"] > 0

    def test_solvent_absent_for_raw_finish(self):
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        items = hs.estimate_consumables(500.0, 200.0, "raw")
        solvent = [i for i in items if "solvent" in i["description"].lower()]
        assert len(solvent) == 0

    def test_solvent_present_for_powder_coat(self):
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        items = hs.estimate_consumables(300.0, 100.0, "powder_coat")
        solvent = [i for i in items if "solvent" in i["description"].lower()]
        assert len(solvent) == 1

    def test_solvent_quart_for_small_jobs(self):
        from backend.hardware_sourcer import HardwareSourcer
        hs = HardwareSourcer()
        items = hs.estimate_consumables(100.0, 30.0, "clearcoat")
        solvent = [i for i in items if "solvent" in i["description"].lower()]
        assert len(solvent) == 1
        assert "qt" in solvent[0]["description"].lower()
        assert solvent[0]["unit_price"] == 8.50


# =====================================================================
# 6. Frontend bid upload
# =====================================================================

class TestBidUploadFrontend:
    def test_bid_upload_js_exists(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "frontend", "js", "bid-upload.js")
        assert os.path.exists(path)
        with open(path, "r") as f:
            content = f.read()
        assert "initBidUpload" in content

    def test_app_html_has_bid_view(self):
        """Bid upload view is in app.html (P53 moved app from index.html to app.html)."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "frontend", "app.html")
        with open(path, "r") as f:
            content = f.read()
        assert "view-bid" in content
        assert "bid-upload.js" in content
        assert "Upload Bid" in content


# =====================================================================
# 7. Post profile key injection into AI prompt context
# =====================================================================

class TestPostProfileKeyInjection:
    def test_post_profile_in_field_context(self):
        from backend.calculators.ai_cut_list import AICutListGenerator

        gen = AICutListGenerator()
        fields = {
            "clear_width": "18",
            "height": "6",
            "post_concrete": "Yes",
            "post_count": "3",
            "_post_profile_key": "pipe_4_sch40",
        }
        context = gen._build_field_context("cantilever_gate", fields)
        assert "pipe_4_sch40" in context
