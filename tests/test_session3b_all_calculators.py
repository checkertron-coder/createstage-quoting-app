"""
Session 3B acceptance tests — complete calculator coverage for all 25 job types.

Tests:
1-20.  One test per new calculator (20 tests)
21-23. Registry tests (3 tests)
24-26. Detection keyword tests (3 tests)
27-29. Question tree tests (3 tests)
30.    V2_JOB_TYPES sync test (1 test)
31-32. Custom_fab fallback tests (2 tests)
33.    Product firetable BOM test (1 test)
34-35. Output contract tests for new calculators (2 tests)
"""

from backend.calculators.registry import get_calculator, has_calculator, list_calculators
from backend.calculators.custom_fab import CustomFabCalculator
from backend.calculators.ornamental_fence import OrnamentalFenceCalculator
from backend.calculators.complete_stair import CompleteStairCalculator
from backend.calculators.spiral_stair import SpiralStairCalculator
from backend.calculators.window_security_grate import WindowSecurityGrateCalculator
from backend.calculators.balcony_railing import BalconyRailingCalculator
from backend.calculators.bollard import BollardCalculator
from backend.calculators.furniture_table import FurnitureTableCalculator
from backend.calculators.utility_enclosure import UtilityEnclosureCalculator
from backend.calculators.repair_structural import RepairStructuralCalculator
from backend.calculators.offroad_bumper import OffroadBumperCalculator
from backend.calculators.rock_slider import RockSliderCalculator
from backend.calculators.roll_cage import RollCageCalculator
from backend.calculators.exhaust_custom import ExhaustCustomCalculator
from backend.calculators.trailer_fab import TrailerFabCalculator
from backend.calculators.structural_frame import StructuralFrameCalculator
from backend.calculators.furniture_other import FurnitureOtherCalculator
from backend.calculators.sign_frame import SignFrameCalculator
from backend.calculators.led_sign_custom import LedSignCustomCalculator
from backend.calculators.product_firetable import ProductFiretableCalculator
from backend.question_trees.engine import QuestionTreeEngine, detect_job_type, DETECTION_KEYWORDS
from backend.models import V2_JOB_TYPES


# ============================================================
# Helper: verify standard MaterialList output
# ============================================================

def _assert_valid_material_list(result, job_type_label):
    """Verify result matches MaterialList contract."""
    assert "items" in result, "%s missing items" % job_type_label
    assert "hardware" in result, "%s missing hardware" % job_type_label
    assert "total_weight_lbs" in result, "%s missing total_weight_lbs" % job_type_label
    assert "total_sq_ft" in result, "%s missing total_sq_ft" % job_type_label
    assert "weld_linear_inches" in result, "%s missing weld_linear_inches" % job_type_label
    assert "assumptions" in result, "%s missing assumptions" % job_type_label

    assert isinstance(result["items"], list)
    assert len(result["items"]) > 0, "%s has empty items list" % job_type_label
    assert result["total_weight_lbs"] > 0, "%s has zero weight" % job_type_label
    assert result["total_sq_ft"] >= 0, "%s has negative sq_ft" % job_type_label
    assert result["weld_linear_inches"] >= 0, "%s has negative weld_inches" % job_type_label
    assert len(result["assumptions"]) > 0, "%s has no assumptions" % job_type_label

    # Verify MaterialItem schema
    for item in result["items"]:
        assert "description" in item
        assert "material_type" in item
        assert "profile" in item
        assert "quantity" in item
        assert isinstance(item["quantity"], int), \
            "quantity must be int in %s, got %s" % (job_type_label, type(item["quantity"]))
        assert "unit_price" in item
        assert "line_total" in item


# ============================================================
# 1-20: One test per new calculator
# ============================================================

def test_ornamental_fence_calculator():
    calc = OrnamentalFenceCalculator()
    result = calc.calculate({
        "total_footage": "50",
        "fence_height": "6",
        "panel_width": "6",
        "picket_spacing": "4\" on-center",
    })
    _assert_valid_material_list(result, "ornamental_fence")
    assert any("post" in i["description"].lower() for i in result["items"])
    assert any("picket" in i["description"].lower() for i in result["items"])


def test_complete_stair_calculator():
    calc = CompleteStairCalculator()
    result = calc.calculate({
        "total_rise": "10",
        "stair_width": "3",
        "rise_per_step": "7.5",
        "run_per_step": "10",
    })
    _assert_valid_material_list(result, "complete_stair")
    assert any("stringer" in i["description"].lower() for i in result["items"])
    assert any("tread" in i["description"].lower() for i in result["items"])


def test_spiral_stair_calculator():
    calc = SpiralStairCalculator()
    result = calc.calculate({
        "total_rise": "10",
        "diameter": "5",
        "rise_per_step": "7.5",
    })
    _assert_valid_material_list(result, "spiral_stair")
    assert any("center column" in i["description"].lower() or "column" in i["description"].lower()
               for i in result["items"])
    assert any("tread" in i["description"].lower() for i in result["items"])


def test_window_security_grate_calculator():
    calc = WindowSecurityGrateCalculator()
    result = calc.calculate({
        "window_width": "3",
        "window_height": "4",
        "window_count": "4",
    })
    _assert_valid_material_list(result, "window_security_grate")
    assert any("frame" in i["description"].lower() for i in result["items"])
    assert any("bar" in i["description"].lower() for i in result["items"])


def test_balcony_railing_calculator():
    calc = BalconyRailingCalculator()
    result = calc.calculate({
        "linear_footage": "12",
        "railing_height": "42\"",
        "top_rail_profile": "1-1/2\" round tube (ADA graspable)",
        "infill_style": "Vertical square bar (traditional)",
        "post_mount_type": "Surface mount flange",
        "post_spacing": "6 ft on-center (standard)",
        "transitions": "0",
        "finish": "Powder coat",
    })
    _assert_valid_material_list(result, "balcony_railing")
    assert any("post" in i["description"].lower() for i in result["items"])


def test_bollard_calculator():
    calc = BollardCalculator()
    result = calc.calculate({
        "bollard_count": "6",
        "pipe_size": "6\" schedule 40 (standard — most common)",
        "bollard_height": "36\" (standard)",
        "fixed_or_removable": "Fixed — set in concrete (permanent)",
        "finish": "Powder coat (most durable)",
    })
    _assert_valid_material_list(result, "bollard")
    assert any("pipe" in i["description"].lower() for i in result["items"])
    assert any("cap" in i["description"].lower() for i in result["items"])


def test_furniture_table_calculator():
    calc = FurnitureTableCalculator()
    result = calc.calculate({
        "table_length": "60",
        "table_width": "30",
        "table_height": "30",
        "quantity": "2",
    })
    _assert_valid_material_list(result, "furniture_table")
    assert any("leg" in i["description"].lower() for i in result["items"])
    assert any("frame" in i["description"].lower() or "support" in i["description"].lower()
               for i in result["items"])


def test_utility_enclosure_calculator():
    calc = UtilityEnclosureCalculator()
    result = calc.calculate({
        "width": "24",
        "height": "36",
        "depth": "12",
        "quantity": "1",
        "has_door": "Yes",
    })
    _assert_valid_material_list(result, "utility_enclosure")
    assert any("panel" in i["description"].lower() for i in result["items"])


def test_repair_structural_calculator():
    calc = RepairStructuralCalculator()
    result = calc.calculate({
        "repair_type": "Trailer frame repair",
        "damage_dimensions": "3 feet",
    })
    _assert_valid_material_list(result, "repair_structural")
    assert any("replacement" in i["description"].lower() for i in result["items"])


def test_offroad_bumper_calculator():
    calc = OffroadBumperCalculator()
    result = calc.calculate({
        "vehicle_make_model": "2020 Toyota Tacoma",
        "bumper_position": "Front bumper",
        "material_thickness": "1/4\" (standard — most common)",
        "winch_mount": "Yes — standard winch plate",
        "d_ring_mounts": "Yes — pair of 3/4\" D-ring mounts",
        "finish": "Powder coat (most durable)",
    })
    _assert_valid_material_list(result, "offroad_bumper")
    assert any("bumper" in i["description"].lower() or "plate" in i["description"].lower()
               for i in result["items"])


def test_rock_slider_calculator():
    calc = RockSliderCalculator()
    result = calc.calculate({
        "vehicle_make_model": "2021 Toyota 4Runner",
        "slider_style": "Weld-on (strongest — welded to frame)",
        "material_thickness": "1.75\" OD × 0.120\" wall DOM (standard)",
        "kick_out": "Yes — angled kick-out (easier entry/exit)",
        "finish": "Powder coat (most durable)",
    })
    _assert_valid_material_list(result, "rock_slider")
    assert any("rail" in i["description"].lower() for i in result["items"])
    assert any("bracket" in i["description"].lower() or "mount" in i["description"].lower()
               for i in result["items"])


def test_roll_cage_calculator():
    calc = RollCageCalculator()
    result = calc.calculate({
        "vehicle_type": "Truck / SUV (off-road / prerunner)",
        "cage_style": "6-point cage (4-point + door bars)",
        "tube_size": "1.75\" × 0.120\" wall DOM (most common — street/trail)",
        "finish": "Powder coat (most durable)",
    })
    _assert_valid_material_list(result, "roll_cage")
    assert any("cage" in i["description"].lower() or "tubing" in i["description"].lower()
               for i in result["items"])


def test_exhaust_custom_calculator():
    calc = ExhaustCustomCalculator()
    result = calc.calculate({
        "vehicle_make_model": "2019 Ford Mustang GT",
        "exhaust_type": "Cat-back exhaust (catalytic converter back)",
        "pipe_diameter": "3\" (V8 / performance)",
        "material": "304 stainless steel (premium — long-lasting)",
        "finish": "High-temp ceramic coat (most durable for exhaust)",
    })
    _assert_valid_material_list(result, "exhaust_custom")
    assert any("pipe" in i["description"].lower() or "exhaust" in i["description"].lower()
               for i in result["items"])
    assert any("bend" in i["description"].lower() for i in result["items"])
    assert len(result["hardware"]) >= 1  # Flanges/clamps


def test_trailer_fab_calculator():
    calc = TrailerFabCalculator()
    result = calc.calculate({
        "trailer_type": "Flatbed / utility trailer",
        "length": "16",
        "width": "6.5' (standard utility)",
        "axle_count": "Tandem axle (up to 7,000 lb capacity)",
        "deck_type": "Expanded metal deck",
        "finish": "Powder coat (most durable)",
    })
    _assert_valid_material_list(result, "trailer_fab")
    assert any("frame" in i["description"].lower() or "rail" in i["description"].lower()
               for i in result["items"])
    assert any("cross" in i["description"].lower() for i in result["items"])
    assert len(result["hardware"]) >= 2  # Coupler, chains, jack


def test_structural_frame_calculator():
    calc = StructuralFrameCalculator()
    result = calc.calculate({
        "frame_type": "Mezzanine / platform",
        "span": "20",
        "height": "10",
        "depth": "12",
        "material": "Wide flange / I-beam (most common for structural)",
    })
    _assert_valid_material_list(result, "structural_frame")
    assert any("beam" in i["description"].lower() for i in result["items"])
    assert any("column" in i["description"].lower() for i in result["items"])


def test_furniture_other_calculator():
    calc = FurnitureOtherCalculator()
    result = calc.calculate({
        "item_type": "Shelving / storage rack",
        "material": "Mild steel (most common / cheapest)",
        "approximate_size": "48\" × 18\" × 72\"",
        "quantity": "2",
        "finish": "Powder coat",
    })
    _assert_valid_material_list(result, "furniture_other")


def test_sign_frame_calculator():
    calc = SignFrameCalculator()
    result = calc.calculate({
        "sign_type": "Post-mount sign frame (street/parking lot)",
        "sign_dimensions": "4 ft × 3 ft",
        "mounting_method": "Bolt-through (sign bolts to frame)",
        "material": "Mild steel (paint or powder coat)",
        "finish": "Powder coat",
    })
    _assert_valid_material_list(result, "sign_frame")
    assert any("frame" in i["description"].lower() for i in result["items"])
    assert any("post" in i["description"].lower() for i in result["items"])


def test_led_sign_custom_calculator():
    calc = LedSignCustomCalculator()
    result = calc.calculate({
        "sign_type": "Channel letters (individual 3D letters)",
        "dimensions": "8 ft × 2 ft",
        "letter_height": "18",
        "letter_count": "8",
        "material": "Aluminum (standard for sign fabrication)",
    })
    _assert_valid_material_list(result, "led_sign_custom")
    assert any("letter" in i["description"].lower() or "return" in i["description"].lower()
               for i in result["items"])


def test_product_firetable_calculator():
    calc = ProductFiretableCalculator()
    result = calc.calculate({
        "configuration": "FireTable Pro System (base + basin + stand)",
        "fuel_type": "Propane (most common — portable)",
        "dimensions": "Standard (24\" × 34\")",
        "material": "304 stainless steel (standard FireTable Pro)",
        "finish": "Brushed stainless (standard for FireTable Pro)",
    })
    _assert_valid_material_list(result, "product_firetable")


def test_custom_fab_calculator():
    calc = CustomFabCalculator()
    result = calc.calculate({
        "description": "Custom steel bracket for mounting equipment",
        "material": "Mild steel (most common / cheapest)",
        "approximate_size": "4 ft × 2 ft × 3 ft",
        "quantity": "1",
    })
    _assert_valid_material_list(result, "custom_fab")


# ============================================================
# 21-23: Registry tests
# ============================================================

def test_registry_has_all_25_types():
    """Registry should have all 25 job types."""
    calcs = list_calculators()
    assert len(calcs) == 25, "Expected 25 calculators, got %d: %s" % (len(calcs), calcs)
    for job_type in V2_JOB_TYPES:
        assert job_type in calcs, "%s not in calculator registry" % job_type


def test_registry_fallback_to_custom_fab():
    """Unknown job types should fallback to CustomFabCalculator instead of raising."""
    calc = get_calculator("totally_unknown_type")
    assert isinstance(calc, CustomFabCalculator)
    # Should not raise
    result = calc.calculate({"approximate_size": "2 ft × 1 ft", "quantity": "1"})
    assert len(result["items"]) > 0


def test_registry_list_returns_25():
    """list_calculators() returns all 25 entries."""
    assert len(list_calculators()) == 25


# ============================================================
# 24-26: Detection keyword tests
# ============================================================

def test_keyword_match_returns_correct_type():
    """Multi-word keyword match returns correct job_type with high confidence."""
    result = detect_job_type("I need a cantilever sliding gate for my driveway")
    assert result["job_type"] == "cantilever_gate"
    # Should have reasonable confidence
    assert result["confidence"] >= 0.6

    result2 = detect_job_type("Need a custom roll cage for my Jeep Wrangler")
    assert result2["job_type"] == "roll_cage"


def test_multiword_keyword_matching():
    """Multi-word keywords like 'spiral stair' are matched correctly."""
    result = detect_job_type("Building a spiral staircase in my loft")
    assert result["job_type"] == "spiral_stair"

    result2 = detect_job_type("Need security bars for 4 windows")
    assert result2["job_type"] == "window_security_grate"


def test_unknown_description_defaults():
    """Completely unknown description returns custom_fab (no API key in tests)."""
    result = detect_job_type("I need something completely indescribable and unusual")
    # Without Gemini API key, keyword fallback or custom_fab
    assert result["job_type"] in V2_JOB_TYPES


# ============================================================
# 27-29: Question tree tests
# ============================================================

def test_all_25_types_have_question_trees():
    """Every job type in V2_JOB_TYPES must have a JSON question tree file."""
    engine = QuestionTreeEngine()
    available = engine.list_available_trees()
    for job_type in V2_JOB_TYPES:
        assert job_type in available, \
            "Missing question tree for %s. Available: %s" % (job_type, available)


def test_new_trees_load_without_error():
    """All 10 new question trees load and parse correctly."""
    engine = QuestionTreeEngine()
    new_types = [
        "offroad_bumper", "rock_slider", "roll_cage", "exhaust_custom",
        "trailer_fab", "structural_frame", "furniture_other",
        "sign_frame", "led_sign_custom", "product_firetable",
    ]
    for job_type in new_types:
        tree = engine.load_tree(job_type)
        assert tree["job_type"] == job_type
        assert "questions" in tree
        assert len(tree["questions"]) >= 3
        assert "required_fields" in tree
        assert len(tree["required_fields"]) >= 2


def test_required_fields_exist_in_questions():
    """Every required_field must have a corresponding question."""
    engine = QuestionTreeEngine()
    for job_type in V2_JOB_TYPES:
        tree = engine.load_tree(job_type)
        question_ids = {q["id"] for q in tree.get("questions", [])}
        for field in tree.get("required_fields", []):
            assert field in question_ids, \
                "Required field '%s' not found in questions for %s" % (field, job_type)


# ============================================================
# 30: V2_JOB_TYPES sync test
# ============================================================

def test_v2_job_types_match_registry_and_trees():
    """V2_JOB_TYPES, calculator registry, and question trees must all be in sync."""
    engine = QuestionTreeEngine()
    available_trees = set(engine.list_available_trees())
    registered_calcs = set(list_calculators())

    assert len(V2_JOB_TYPES) == 25, "V2_JOB_TYPES should have 25 types"

    for job_type in V2_JOB_TYPES:
        assert job_type in registered_calcs, \
            "%s in V2_JOB_TYPES but not in calculator registry" % job_type
        assert job_type in available_trees, \
            "%s in V2_JOB_TYPES but no question tree file" % job_type


# ============================================================
# 31-32: Custom_fab fallback tests
# ============================================================

def test_custom_fab_handles_minimal_fields():
    """CustomFabCalculator works with only approximate_size."""
    calc = CustomFabCalculator()
    result = calc.calculate({"approximate_size": "2 ft square"})
    assert len(result["items"]) > 0
    assert result["total_weight_lbs"] > 0


def test_custom_fab_handles_empty_fields():
    """CustomFabCalculator handles completely empty fields without crash."""
    calc = CustomFabCalculator()
    result = calc.calculate({})
    assert len(result["items"]) > 0
    assert result["total_weight_lbs"] > 0
    assert len(result["assumptions"]) >= 2


# ============================================================
# 33: Product firetable BOM test
# ============================================================

def test_firetable_loads_bom():
    """FireTable calculator loads BOM data from firetable_pro_bom.json."""
    calc = ProductFiretableCalculator()
    result = calc.calculate({
        "configuration": "FireTable Pro System (base + basin + stand)",
        "fuel_type": "Propane",
        "dimensions": "Standard (24\" × 34\")",
        "material": "304 stainless steel",
        "finish": "Brushed stainless",
    })
    assert len(result["items"]) >= 5, \
        "FireTable BOM should have multiple material items"
    assert result["total_weight_lbs"] > 100, \
        "FireTable should weigh > 100 lbs"
    assert any("bom" in a.lower() or "osorio" in a.lower() or "supplier" in a.lower()
               for a in result["assumptions"]), \
        "Should reference BOM/supplier in assumptions"


# ============================================================
# 34-35: Output contract tests for all new calculators
# ============================================================

def _all_new_calculators_with_fields():
    """Returns (calculator, fields) for each of the 20 new calculator types."""
    return [
        (OrnamentalFenceCalculator(), {"total_footage": "30", "fence_height": "5"}),
        (CompleteStairCalculator(), {"total_rise": "9", "stair_width": "3"}),
        (SpiralStairCalculator(), {"total_rise": "10", "diameter": "5"}),
        (WindowSecurityGrateCalculator(), {"window_width": "3", "window_height": "4", "window_count": "2"}),
        (BalconyRailingCalculator(), {"linear_footage": "10", "railing_height": "42\"",
                                      "infill_style": "Vertical square bar",
                                      "post_mount_type": "Surface mount flange",
                                      "post_spacing": "6 ft on-center"}),
        (BollardCalculator(), {"bollard_count": "4", "pipe_size": "6\" schedule 40",
                                "bollard_height": "36\"", "fixed_or_removable": "Fixed"}),
        (FurnitureTableCalculator(), {"table_length": "48", "table_width": "24", "table_height": "30"}),
        (UtilityEnclosureCalculator(), {"width": "24", "height": "36", "depth": "12"}),
        (RepairStructuralCalculator(), {"repair_type": "General structural repair"}),
        (OffroadBumperCalculator(), {"bumper_position": "Front bumper",
                                     "material_thickness": "1/4\""}),
        (RockSliderCalculator(), {"vehicle_make_model": "2020 Tacoma",
                                   "material_thickness": "1.75\" OD"}),
        (RollCageCalculator(), {"vehicle_type": "UTV", "cage_style": "4-point cage (main hoop + down tubes)",
                                 "tube_size": "1.75\""}),
        (ExhaustCustomCalculator(), {"exhaust_type": "Cat-back exhaust (catalytic converter back)",
                                      "pipe_diameter": "2.5\"", "material": "Mild steel"}),
        (TrailerFabCalculator(), {"length": "12", "width": "6'", "axle_count": "Single axle"}),
        (StructuralFrameCalculator(), {"frame_type": "Portal frame (beam + columns)",
                                        "span": "15", "height": "10"}),
        (FurnitureOtherCalculator(), {"item_type": "Shelving / storage rack",
                                       "approximate_size": "48 × 18 × 72", "quantity": "1"}),
        (SignFrameCalculator(), {"sign_type": "Wall-mount bracket", "sign_dimensions": "3 ft × 2 ft",
                                  "material": "Mild steel"}),
        (LedSignCustomCalculator(), {"sign_type": "Cabinet / box sign", "dimensions": "6 ft × 3 ft",
                                      "letter_height": "12"}),
        (ProductFiretableCalculator(), {"configuration": "FireTable Pro System",
                                         "dimensions": "Standard (24\" × 34\")",
                                         "material": "304 stainless steel"}),
        (CustomFabCalculator(), {"approximate_size": "3 ft × 2 ft × 1 ft", "quantity": "3"}),
    ]


def test_all_new_calculators_output_schema():
    """Every new calculator output matches MaterialList schema."""
    required_keys = {"job_type", "items", "hardware", "total_weight_lbs",
                     "total_sq_ft", "weld_linear_inches", "assumptions"}

    for calc, fields in _all_new_calculators_with_fields():
        result = calc.calculate(fields)
        for key in required_keys:
            assert key in result, \
                "%s output missing '%s'" % (type(calc).__name__, key)

        assert isinstance(result["items"], list)
        assert isinstance(result["hardware"], list)
        assert isinstance(result["assumptions"], list)
        assert isinstance(result["total_weight_lbs"], (int, float))
        assert isinstance(result["total_sq_ft"], (int, float))
        assert isinstance(result["weld_linear_inches"], (int, float))


def test_all_new_calculators_have_positive_output():
    """Every new calculator produces positive weight and non-empty items."""
    for calc, fields in _all_new_calculators_with_fields():
        result = calc.calculate(fields)
        assert result["total_weight_lbs"] > 0, \
            "%s produced zero weight" % type(calc).__name__
        assert len(result["items"]) > 0, \
            "%s produced empty items list" % type(calc).__name__
        assert len(result["assumptions"]) > 0, \
            "%s produced no assumptions" % type(calc).__name__
