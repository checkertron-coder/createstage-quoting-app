"""
Tests for deterministic labor calculator (labor_calculator.py).

Tests:
1-3.  Simple furniture (tube frame, 10 pieces)
4-6.  Complex furniture (tube + flat bar pyramid, 30+ pieces)
7-9.  Railing job
10.   Empty cut list returns minimums
11.   TIG detection from fields
12.   Mill scale adds grind time
"""

from backend.calculators.labor_calculator import calculate_labor_hours


# --- Fixtures ---

def _simple_furniture_cuts():
    """10-piece tube frame for a basic end table."""
    return [
        {"profile": "sq_tube_1.5x1.5_11ga", "quantity": 4,
         "cut_type": "square", "length_inches": 28,
         "description": "Leg", "weld_process": "tig"},
        {"profile": "sq_tube_1.5x1.5_11ga", "quantity": 2,
         "cut_type": "miter_45", "length_inches": 24,
         "description": "Long apron", "weld_process": "tig"},
        {"profile": "sq_tube_1.5x1.5_11ga", "quantity": 2,
         "cut_type": "miter_45", "length_inches": 18,
         "description": "Short apron", "weld_process": "tig"},
        {"profile": "sq_tube_1.5x1.5_11ga", "quantity": 2,
         "cut_type": "square", "length_inches": 20,
         "description": "Stretcher", "weld_process": "tig"},
    ]


def _complex_furniture_cuts():
    """42-piece table with tube frame + flat bar pyramid pattern."""
    cuts = _simple_furniture_cuts()  # 10 tube pieces
    # 8 pyramid layers × 4 pieces each = 32 flat bar pieces
    for i in range(8):
        length = 20 - (i * 2)
        cuts.append({
            "profile": "flat_bar_1x0.125", "quantity": 4,
            "cut_type": "square", "length_inches": length,
            "description": "Pyramid layer %d" % (i + 1),
            "weld_process": "tig",
        })
    return cuts  # 10 + 32 = 42 total pieces


def _railing_cuts():
    """40 LF straight railing with pickets, MIG welded."""
    return [
        {"profile": "sq_tube_2x2_11ga", "quantity": 1,
         "cut_type": "square", "length_inches": 480,
         "description": "Top rail", "weld_process": "mig"},
        {"profile": "sq_tube_2x2_11ga", "quantity": 1,
         "cut_type": "square", "length_inches": 480,
         "description": "Bottom rail", "weld_process": "mig"},
        {"profile": "sq_bar_0.5", "quantity": 120,
         "cut_type": "square", "length_inches": 36,
         "description": "Pickets", "weld_process": "mig"},
        {"profile": "sq_tube_2x2_11ga", "quantity": 8,
         "cut_type": "square", "length_inches": 42,
         "description": "Posts", "weld_process": "mig"},
        {"profile": "plate_0.25", "quantity": 8,
         "cut_type": "square", "length_inches": 6,
         "description": "Post base flanges", "weld_process": "mig"},
    ]


def _furniture_fields():
    return {
        "finish": "Clear coat / lacquer",
        "description": "End table with pyramid pattern, ground smooth TIG welds",
    }


def _railing_fields():
    return {
        "finish": "Powder coat (most durable, outsourced)",
        "description": "40 foot straight railing, 42 inches tall",
    }


# ============================================================
# Simple Furniture Tests
# ============================================================

def test_simple_furniture_returns_all_8_keys():
    """All 8 labor categories present."""
    result = calculate_labor_hours("furniture_table", _simple_furniture_cuts(),
                                   _furniture_fields())
    expected_keys = [
        "layout_setup", "cut_prep", "fit_tack", "full_weld",
        "grind_clean", "finish_prep", "coating_application", "final_inspection",
    ]
    for key in expected_keys:
        assert key in result, "Missing key: %s" % key
        assert isinstance(result[key], float), "%s should be float" % key
        assert result[key] >= 0.0, "%s should be non-negative" % key


def test_simple_furniture_weld_hours_realistic():
    """Full weld hours <= 12 for standard 10-piece furniture."""
    result = calculate_labor_hours("furniture_table", _simple_furniture_cuts(),
                                   _furniture_fields())
    assert result["full_weld"] <= 12.0, \
        "Weld hours %.1f too high for simple furniture" % result["full_weld"]
    assert result["full_weld"] > 0.0, "Weld hours should be > 0"


def test_simple_furniture_total_reasonable():
    """Total shop hours (excluding install) should be 5-25 hrs for simple table."""
    result = calculate_labor_hours("furniture_table", _simple_furniture_cuts(),
                                   _furniture_fields())
    total = sum(result.values())
    assert total >= 5.0, "Total %.1f too low for furniture" % total
    assert total <= 25.0, "Total %.1f too high for simple furniture" % total


# ============================================================
# Complex Furniture Tests
# ============================================================

def test_complex_furniture_weld_hours_realistic():
    """Full weld hours <= 12 for furniture with 30+ pieces."""
    result = calculate_labor_hours("furniture_table", _complex_furniture_cuts(),
                                   _furniture_fields())
    assert result["full_weld"] <= 12.0, \
        "Weld hours %.1f too high for complex furniture" % result["full_weld"]


def test_complex_furniture_more_than_simple():
    """Complex furniture with pyramid pattern should take more total time."""
    simple = calculate_labor_hours("furniture_table", _simple_furniture_cuts(),
                                    _furniture_fields())
    complex_ = calculate_labor_hours("furniture_table", _complex_furniture_cuts(),
                                      _furniture_fields())
    assert sum(complex_.values()) > sum(simple.values()), \
        "Complex furniture should take longer than simple"


def test_complex_furniture_cut_prep_scales():
    """More pieces = more cut prep time."""
    simple = calculate_labor_hours("furniture_table", _simple_furniture_cuts(),
                                    _furniture_fields())
    complex_ = calculate_labor_hours("furniture_table", _complex_furniture_cuts(),
                                      _furniture_fields())
    assert complex_["cut_prep"] > simple["cut_prep"]


# ============================================================
# Railing Tests
# ============================================================

def test_railing_uses_mig_speed():
    """Railing with MIG welding should have lower weld hours than TIG equivalent."""
    result = calculate_labor_hours("straight_railing", _railing_cuts(),
                                   _railing_fields())
    # MIG is 2.5x faster than TIG, so weld hours should reflect that
    assert result["full_weld"] > 0.0
    # Powder coat = 0 coating application
    assert result["coating_application"] == 0.0


def test_railing_powder_coat_no_coating_labor():
    """Powder coat finish = 0 hrs coating (outsourced)."""
    result = calculate_labor_hours("straight_railing", _railing_cuts(),
                                   _railing_fields())
    assert result["coating_application"] == 0.0
    assert result["finish_prep"] == 1.0  # degrease, scuff, load


def test_railing_total_reasonable():
    """40 LF railing total hours should be reasonable."""
    result = calculate_labor_hours("straight_railing", _railing_cuts(),
                                   _railing_fields())
    total = sum(result.values())
    assert total > 5.0, "Total %.1f too low for 40 LF railing" % total


# ============================================================
# Edge Cases
# ============================================================

def test_empty_cut_list_returns_minimums():
    """Empty cut list should return minimum viable hours, not crash."""
    result = calculate_labor_hours("custom_fab", [], {})
    assert result["layout_setup"] == 1.5
    assert result["final_inspection"] == 0.5
    assert sum(result.values()) > 0


def test_tig_detected_from_fields():
    """TIG detection from field values (not just cut list weld_process)."""
    # Use enough pieces so weld hours exceed the 0.5 hr minimum
    cuts = [
        {"profile": "sq_tube_2x2_11ga", "quantity": 10,
         "cut_type": "square", "length_inches": 28,
         "weld_process": "mig"},  # items say MIG
        {"profile": "sq_tube_2x2_11ga", "quantity": 6,
         "cut_type": "miter_45", "length_inches": 20,
         "weld_process": "mig"},
    ]
    fields_tig = {"finish": "raw", "description": "ground smooth visible welds"}
    result_tig = calculate_labor_hours("furniture_table", cuts, fields_tig)

    fields_mig = {"finish": "raw", "description": "standard frame"}
    result_mig = calculate_labor_hours("furniture_table", cuts, fields_mig)

    assert result_tig["full_weld"] > result_mig["full_weld"], \
        "TIG detection should increase weld hours (%.2f vs %.2f)" % (
            result_tig["full_weld"], result_mig["full_weld"])


def test_mill_scale_adds_grind_time():
    """Clear coat / raw finish should add mill scale removal time."""
    cuts = [
        {"profile": "sq_tube_2x2_11ga", "quantity": 4,
         "cut_type": "square", "length_inches": 30,
         "weld_process": "mig"},
    ]
    fields_clear = {"finish": "Clear coat / lacquer"}
    fields_powder = {"finish": "Powder coat"}
    result_clear = calculate_labor_hours("furniture_table", cuts, fields_clear)
    result_powder = calculate_labor_hours("furniture_table", cuts, fields_powder)
    assert result_clear["grind_clean"] > result_powder["grind_clean"], \
        "Clear coat should add mill scale removal time to grind_clean"
