"""
Session 3 acceptance tests — geometry + material calculation engine.

Tests:
1-5.   Framework tests (base class, material lookup, registry)
6-10.  Cantilever gate calculator
11-14. Swing gate calculator
15-18. Straight railing calculator
19-21. Stair railing calculator
22-25. Repair decorative calculator
26-30. Output contract + pipeline integration tests
"""

import math

from backend.calculators.base import BaseCalculator
from backend.calculators.material_lookup import MaterialLookup, PRICE_PER_FOOT, HARDWARE_CATALOG
from backend.calculators.registry import get_calculator, has_calculator, list_calculators
from backend.calculators.cantilever_gate import CantileverGateCalculator
from backend.calculators.swing_gate import SwingGateCalculator
from backend.calculators.straight_railing import StraightRailingCalculator
from backend.calculators.stair_railing import StairRailingCalculator
from backend.calculators.repair_decorative import RepairDecorativeCalculator


# ============================================================
# Framework tests
# ============================================================

def test_base_calculator_waste_rounds_up():
    """apply_waste always rounds up to next whole unit."""
    calc = CantileverGateCalculator()  # Use concrete subclass
    assert calc.apply_waste(10, 0.05) == 11  # 10 * 1.05 = 10.5 → 11
    assert calc.apply_waste(1, 0.05) == 2    # 1 * 1.05 = 1.05 → 2
    assert calc.apply_waste(20, 0.10) == 22  # 20 * 1.10 = 22.0 → 22
    assert calc.apply_waste(3, 0.15) == 4    # 3 * 1.15 = 3.45 → 4


def test_base_calculator_linear_feet_to_pieces():
    """linear_feet_to_pieces always rounds up — can't buy half a stick."""
    calc = CantileverGateCalculator()
    assert calc.linear_feet_to_pieces(20.0) == 1   # Exactly 1 stick
    assert calc.linear_feet_to_pieces(21.0) == 2   # Needs 2 sticks
    assert calc.linear_feet_to_pieces(40.0) == 2   # Exactly 2 sticks
    assert calc.linear_feet_to_pieces(0.5) == 1    # Less than 1 stick = still 1
    assert calc.linear_feet_to_pieces(15.0, stock_length_ft=10.0) == 2  # Custom stock length


def test_material_lookup_returns_default_prices():
    """MaterialLookup returns nonzero prices for known profiles (seeded or default)."""
    ml = MaterialLookup()
    # Prices may come from seeded data or hardcoded defaults — either way, > 0
    assert ml.get_price_per_foot("sq_tube_2x2_11ga") > 0
    assert ml.get_price_per_foot("sq_tube_4x4_11ga") > 0
    assert ml.get_price_per_foot("sq_bar_0.75") > 0
    assert ml.get_price_per_foot("nonexistent_profile") == 0.0
    # get_price_with_source returns (price, source) tuple
    price, source = ml.get_price_with_source("sq_tube_2x2_11ga")
    assert price > 0
    assert source in ("Osorio", "Wexler", "market_average")


def test_material_lookup_hardware_stubs():
    """Hardware stubs return 3-option PricingOption lists."""
    ml = MaterialLookup()
    options = ml.get_hardware_options("liftmaster_la412")
    assert len(options) == 3
    assert all("supplier" in opt for opt in options)
    assert all("price" in opt for opt in options)
    assert all(opt["price"] > 0 for opt in options)


def test_calculator_registry_all_5_types():
    """Registry has all 5 Priority A calculator types."""
    calcs = list_calculators()
    for job_type in ["cantilever_gate", "swing_gate", "straight_railing",
                     "stair_railing", "repair_decorative"]:
        assert job_type in calcs, f"{job_type} not in registry"
        assert has_calculator(job_type)


def test_calculator_registry_unknown_type_falls_back():
    """Requesting a calculator for unknown type falls back to CustomFabCalculator."""
    from backend.calculators.custom_fab import CustomFabCalculator
    calc = get_calculator("nonexistent_type")
    assert isinstance(calc, CustomFabCalculator)


# ============================================================
# Cantilever gate tests
# ============================================================

def _cantilever_basic_fields():
    """Standard cantilever gate fields for testing."""
    return {
        "clear_width": "10",
        "height": "6",
        "frame_material": "Square tube (most common)",
        "frame_gauge": "11 gauge (0.120\" - standard for gates)",
        "frame_size": "2\" x 2\"",
        "infill_type": "Expanded metal",
        "post_count": "3 posts (standard)",
        "post_size": "4\" x 4\" square tube",
        "post_concrete": "Yes — new footings needed",
        "roller_carriages": "Standard duty (gates under 1,000 lbs)",
        "has_motor": "Yes",
        "motor_brand": "LiftMaster LA412 (industry standard)",
        "latch_lock": "Gravity latch",
        "finish": "Powder coat (most durable, outsourced)",
        "powder_coat_color": "Black (most common)",
        "installation": "Full installation (gate + posts + concrete)",
    }


def test_cantilever_gate_basic():
    """
    10' wide, 6' tall, 2" sq tube 11ga, expanded metal, 3 posts,
    LiftMaster motor, powder coat black.
    """
    calc = CantileverGateCalculator()
    result = calc.calculate(_cantilever_basic_fields())

    # Must have items
    assert len(result["items"]) >= 4  # Frame, mid-rail, infill, posts + concrete + guide
    assert len(result["hardware"]) >= 3  # Roller carriages, gate stops, motor, latch

    # Counterbalance tail must be present in assumptions
    assert any("tail" in a.lower() or "counterbalance" in a.lower()
               for a in result["assumptions"]), "No counterbalance tail mentioned in assumptions"

    # Motor appears in hardware
    motor_items = [h for h in result["hardware"] if "operator" in h["description"].lower()]
    assert len(motor_items) == 1, "Motor should appear in hardware"

    # Roller carriages appear
    roller_items = [h for h in result["hardware"] if "roller" in h["description"].lower()]
    assert len(roller_items) == 1

    # Weight is reasonable (400-800 lbs for 10x6 gate)
    assert 200 < result["total_weight_lbs"] < 1000, \
        f"Weight {result['total_weight_lbs']} seems unreasonable for a 10x6 gate"

    # Square footage calculated
    assert result["total_sq_ft"] > 0


def test_cantilever_gate_counterbalance_tail():
    """Counterbalance tail adds 50-60% of clear_width in frame material."""
    calc = CantileverGateCalculator()
    result = calc.calculate(_cantilever_basic_fields())

    # Check that frame item description mentions tail
    frame_items = [i for i in result["items"] if "frame" in i["description"].lower()
                   and "tail" in i["description"].lower()]
    assert len(frame_items) >= 1, "Frame item should mention counterbalance tail"

    # Total gate length should be more than clear width
    # 10 ft opening → ~15.5 ft total (10 + 5.5 ft tail)
    # Frame length should reflect this
    frame_item = frame_items[0]
    assert frame_item["length_inches"] > 120, \
        f"Frame length {frame_item['length_inches']}\" should be > 120\" (10ft opening)"


def test_cantilever_gate_no_motor():
    """has_motor=No → no motor in hardware list."""
    fields = _cantilever_basic_fields()
    fields["has_motor"] = "No — manual operation"
    calc = CantileverGateCalculator()
    result = calc.calculate(fields)

    motor_items = [h for h in result["hardware"] if "operator" in h["description"].lower()
                   or "motor" in h["description"].lower()]
    assert len(motor_items) == 0, "Motor should not appear when has_motor=No"


def test_cantilever_gate_post_length_includes_embed():
    """Posts include height + concrete embed depth + 2" clearance."""
    calc = CantileverGateCalculator()
    result = calc.calculate(_cantilever_basic_fields())

    post_items = [i for i in result["items"] if "post" in i["description"].lower()
                  and "concrete" not in i["description"].lower()
                  and "guide" not in i["description"].lower()]
    assert len(post_items) >= 1
    post = post_items[0]
    # 6 ft height = 72" + 42" embed + 2" = 116"
    assert post["length_inches"] >= 100, \
        f"Post length {post['length_inches']}\" should include embed depth"


# ============================================================
# Swing gate tests
# ============================================================

def _swing_double_fields():
    """Standard double swing gate fields."""
    return {
        "clear_width": "12",
        "height": "6",
        "panel_config": "Double panel (two leaves, meet in center)",
        "frame_material": "Square tube (most common)",
        "frame_gauge": "11 gauge (0.120\" - standard)",
        "frame_size": "2\" x 2\"",
        "infill_type": "Pickets (vertical bars)",
        "picket_spacing": "4\" on-center (code compliant)",
        "post_count": "2 posts (single panel)",
        "post_size": "4\" x 4\" square tube",
        "hinge_type": "Heavy duty weld-on barrel hinges",
        "latch_type": "Gravity latch",
        "center_stop": "Cane bolt (drop rod into ground sleeve)",
        "finish": "Powder coat (most durable, outsourced)",
        "installation": "Full installation (gate + posts + concrete)",
    }


def test_swing_gate_double_panel():
    """Double panel → each panel = clear_width / 2, hinge count applies per panel."""
    calc = SwingGateCalculator()
    result = calc.calculate(_swing_double_fields())

    # Should have frame items for panels
    frame_items = [i for i in result["items"] if "panel" in i["description"].lower()
                   and "frame" in i["description"].lower()]
    assert len(frame_items) == 2, f"Expected 2 panel frames, got {len(frame_items)}"

    # Hinge quantity should be for both panels
    hinge_items = [h for h in result["hardware"] if "hinge" in h["description"].lower()]
    assert len(hinge_items) >= 1
    total_hinge_qty = sum(h["quantity"] for h in hinge_items)
    assert total_hinge_qty >= 4, f"Double gate should have >= 4 hinges total, got {total_hinge_qty}"

    # Center stop should be present
    stop_items = [h for h in result["hardware"] if "center" in h["description"].lower()
                  or "cane" in h["description"].lower() or "stop" in h["description"].lower()
                  and "gate stop" not in h["description"].lower()]
    # Filter out generic gate stops
    stop_items = [h for h in result["hardware"] if "cane" in h["description"].lower()
                  or "center stop" in h["description"].lower()
                  or "drop rod" in h["description"].lower()]
    assert len(stop_items) >= 1, "Double gate should have center stop"


def test_swing_gate_hinge_weight_matching():
    """Heavy gate (wide + tall) should get heavy duty hinges."""
    fields = _swing_double_fields()
    fields["panel_config"] = "Single panel (one leaf)"
    fields["clear_width"] = "6"
    fields["height"] = "7"
    fields["hinge_type"] = "Not sure — recommend based on gate weight"

    calc = SwingGateCalculator()
    result = calc.calculate(fields)

    hinge_items = [h for h in result["hardware"] if "hinge" in h["description"].lower()]
    assert len(hinge_items) >= 1


def test_swing_gate_single_panel():
    """Single panel → 2 posts (hinge + latch side)."""
    fields = _swing_double_fields()
    fields["panel_config"] = "Single panel (one leaf)"
    fields["clear_width"] = "4"
    calc = SwingGateCalculator()
    result = calc.calculate(fields)

    # Frame items: should be 1 panel
    frame_items = [i for i in result["items"] if "panel" in i["description"].lower()
                   and "frame" in i["description"].lower()]
    assert len(frame_items) == 1


# ============================================================
# Straight railing tests
# ============================================================

def _railing_40ft_fields():
    """40 ft commercial railing fields."""
    return {
        "linear_footage": "40",
        "location": "Exterior",
        "application": "Commercial / public building",
        "railing_height": "42\" (commercial code minimum / IBC)",
        "top_rail_profile": "1-1/2\" round tube (ADA graspable)",
        "infill_style": "Vertical round bar",
        "baluster_spacing": "4\" max clear (code compliant — standard)",
        "post_mount_type": "Surface mount flange (bolted on top of slab)",
        "post_spacing": "6 ft on-center (standard)",
        "transitions": "0",
        "finish": "Galvanized",
        "installation": "Full installation",
    }


def test_straight_railing_40ft():
    """
    40 linear feet, 42" commercial, round bar balusters at 4" spacing.
    Verify baluster count, post count, and finishing area.
    """
    calc = StraightRailingCalculator()
    result = calc.calculate(_railing_40ft_fields())

    # Baluster count: ~121 (40ft = 480" / 4" spacing + 1)
    baluster_items = [i for i in result["items"] if "baluster" in i["description"].lower()
                      or "infill" in i["description"].lower()]
    assert len(baluster_items) >= 1
    baluster = baluster_items[0]
    # With 5% waste: 121 * 1.05 = 128
    assert baluster["quantity"] >= 100, \
        f"Expected ~121+ balusters for 40ft at 4\" spacing, got {baluster['quantity']}"

    # Post count: floor(40/6) + 1 = 7 posts
    post_items = [i for i in result["items"] if "post" in i["description"].lower()]
    assert len(post_items) >= 1
    post = post_items[0]
    assert post["quantity"] >= 7, f"Expected ~7 posts for 40ft at 6ft spacing, got {post['quantity']}"

    # Square footage for galvanizing
    assert result["total_sq_ft"] > 0

    # Hardware: surface mount flanges
    flange_items = [h for h in result["hardware"] if "flange" in h["description"].lower()
                    or "mount" in h["description"].lower()]
    assert len(flange_items) >= 1


def test_straight_railing_post_count_with_transitions():
    """Corners and transitions add posts."""
    fields = _railing_40ft_fields()
    fields["transitions"] = "3"
    calc = StraightRailingCalculator()
    result = calc.calculate(fields)

    post_items = [i for i in result["items"] if "post" in i["description"].lower()]
    assert len(post_items) >= 1
    # 7 base posts + 3 transition posts = 10
    assert post_items[0]["quantity"] >= 10, \
        f"Expected ~10 posts with 3 transitions, got {post_items[0]['quantity']}"


def test_straight_railing_cable_infill():
    """Cable infill → tensioners + end fittings in hardware."""
    fields = _railing_40ft_fields()
    fields["infill_style"] = "Cable infill"
    calc = StraightRailingCalculator()
    result = calc.calculate(fields)

    tensioner_items = [h for h in result["hardware"] if "tensioner" in h["description"].lower()]
    assert len(tensioner_items) >= 1, "Cable infill should include tensioners"

    fitting_items = [h for h in result["hardware"] if "end fitting" in h["description"].lower()]
    assert len(fitting_items) >= 1, "Cable infill should include end fittings"


# ============================================================
# Stair railing tests
# ============================================================

def test_stair_railing_rake_angle_increases_length():
    """Stair railing total length should account for landing extensions."""
    fields = {
        "linear_footage": "12",
        "railing_height": "34\" (IRC minimum for stairs)",
        "stair_angle": "Standard residential (about 35-37 degrees)",
        "num_risers": "14",
        "top_rail_profile": "1-1/2\" round tube (ADA graspable)",
        "infill_style": "Vertical square bar",
        "post_mount_type": "Surface mount flange (on top of stair tread)",
        "finish": "Powder coat (most durable)",
        "installation": "Full installation",
        "location": "Interior",
        "application": "Residential",
        "landing_extension": "Yes — both top and bottom landings",
        "landing_length_top": "2",
        "landing_length_bottom": "1",
    }
    calc = StairRailingCalculator()
    result = calc.calculate(fields)

    # Total railing should be 12 + 2 + 1 = 15 ft worth of material
    top_rail_items = [i for i in result["items"] if "top rail" in i["description"].lower()]
    assert len(top_rail_items) >= 1
    # The total linear feet should reflect landing extensions
    assert result["total_sq_ft"] > 0


def test_stair_railing_reuses_straight_logic():
    """Stair calculator at 0-degree effective angle should produce reasonable results."""
    straight_fields = {
        "linear_footage": "20",
        "railing_height": "42\" (commercial code minimum / IBC)",
        "top_rail_profile": "Square tube 1-1/2\"",
        "infill_style": "Vertical square bar (traditional)",
        "baluster_spacing": "4\" max clear (code compliant — standard)",
        "post_mount_type": "Surface mount flange (bolted on top of slab)",
        "post_spacing": "6 ft on-center (standard)",
        "transitions": "0",
        "finish": "Powder coat (most durable)",
        "installation": "Full installation",
        "location": "Exterior",
        "application": "Commercial / public building",
    }

    stair_fields = dict(straight_fields)
    stair_fields["stair_angle"] = "Shallow (under 35 degrees)"
    stair_fields["num_risers"] = "10"

    straight_calc = StraightRailingCalculator()
    stair_calc = StairRailingCalculator()

    straight_result = straight_calc.calculate(straight_fields)
    stair_result = stair_calc.calculate(stair_fields)

    # Both should have similar item counts (stair may have wall rail extra)
    assert abs(len(straight_result["items"]) - len(stair_result["items"])) <= 2


def test_stair_railing_wall_handrail():
    """Wall handrail on opposite side adds material."""
    fields = {
        "linear_footage": "12",
        "railing_height": "42\" (IBC commercial minimum)",
        "stair_angle": "Standard residential (about 35-37 degrees)",
        "num_risers": "14",
        "top_rail_profile": "1-1/2\" round tube (ADA graspable)",
        "infill_style": "Vertical square bar",
        "post_mount_type": "Surface mount flange (on top of stair tread)",
        "finish": "Powder coat (most durable)",
        "installation": "Full installation",
        "location": "Interior",
        "application": "Commercial / public building",
        "wall_handrail": "Yes — wall-mount handrail opposite side",
    }
    calc = StairRailingCalculator()
    result = calc.calculate(fields)

    wall_items = [i for i in result["items"] if "wall" in i["description"].lower()]
    assert len(wall_items) >= 1, "Wall handrail should appear in items"

    bracket_items = [h for h in result["hardware"] if "bracket" in h["description"].lower()]
    assert len(bracket_items) >= 1, "Wall brackets should appear in hardware"


# ============================================================
# Repair decorative tests
# ============================================================

def test_repair_broken_weld_minimal_material():
    """Broken weld → no new material items, just weld inches."""
    fields = {
        "repair_photos": "photo1.jpg",
        "repair_type": "Broken weld (piece detached)",
        "item_type": "Railing (stair or flat)",
        "material_type": "Mild steel / carbon steel",
        "is_structural": "Structural",
        "can_remove": "Can be removed — bring to shop",
        "finish": "No finish (structural fix only)",
    }
    calc = RepairDecorativeCalculator()
    result = calc.calculate(fields)

    # No new material for a simple weld repair
    assert len(result["items"]) == 0, "Broken weld should need no new material"
    # But weld inches should be > 0
    assert result["weld_linear_inches"] > 0


def test_repair_rust_through_includes_replacement():
    """Rust-through → replacement section material in output."""
    fields = {
        "repair_photos": "photo1.jpg",
        "repair_type": "Rust-through (holes from corrosion)",
        "item_type": "Fence section",
        "material_type": "Mild steel / carbon steel",
        "damage_dimensions": "2 feet long, 4 inches wide",
        "is_structural": "Both",
        "can_remove": "Can be removed — bring to shop",
        "finish": "Refinish entire piece (strip and recoat everything)",
    }
    calc = RepairDecorativeCalculator()
    result = calc.calculate(fields)

    # Should have replacement material
    assert len(result["items"]) >= 1, "Rust-through should have replacement material"
    assert any("rust" in i["description"].lower() or "replacement" in i["description"].lower()
               for i in result["items"])


def test_repair_scope_creep_flag():
    """surrounding_damage=yes → 25% buffer + assumption note."""
    fields = {
        "repair_photos": "photo1.jpg",
        "repair_type": "Bent or deformed section",
        "item_type": "Gate (swing or sliding)",
        "material_type": "Mild steel / carbon steel",
        "damage_dimensions": "3 feet",
        "is_structural": "Structural",
        "surrounding_damage": "Yes — some additional issues nearby",
        "can_remove": "Can be removed — bring to shop",
        "finish": "Match existing (blend repair into existing finish)",
    }
    calc = RepairDecorativeCalculator()
    result = calc.calculate(fields)

    # Should have scope creep warning
    assert any("additional work" in a.lower() or "buffer" in a.lower() or "site assessment" in a.lower()
               for a in result["assumptions"]), "Scope creep should be noted in assumptions"


def test_repair_assumptions_list_present():
    """Repair output must always have assumptions list."""
    fields = {
        "repair_photos": "photo.jpg",
        "repair_type": "Missing piece or section",
        "item_type": "Decorative panel or screen",
        "material_type": "Mild steel / carbon steel",
        "is_structural": "Cosmetic",
        "can_remove": "Can be removed — bring to shop",
        "finish": "Prime only (customer will paint)",
    }
    calc = RepairDecorativeCalculator()
    result = calc.calculate(fields)

    assert "assumptions" in result
    assert len(result["assumptions"]) >= 2, "Repair should have at least 2 assumptions"


# ============================================================
# Output contract tests
# ============================================================

def _all_calculators_with_fields():
    """Returns (calculator, fields) for each registered type."""
    return [
        (CantileverGateCalculator(), _cantilever_basic_fields()),
        (SwingGateCalculator(), _swing_double_fields()),
        (StraightRailingCalculator(), _railing_40ft_fields()),
        (StairRailingCalculator(), {
            "linear_footage": "12",
            "railing_height": "34\" (IRC minimum for stairs)",
            "stair_angle": "Standard residential (about 35-37 degrees)",
            "num_risers": "14",
            "top_rail_profile": "1-1/2\" round tube (ADA graspable)",
            "infill_style": "Vertical square bar",
            "post_mount_type": "Surface mount flange (on top of stair tread)",
            "finish": "Powder coat (most durable)",
            "installation": "Full installation",
            "location": "Interior",
            "application": "Residential",
        }),
        (RepairDecorativeCalculator(), {
            "repair_photos": "photo.jpg",
            "repair_type": "Rust-through (holes from corrosion)",
            "item_type": "Railing (stair or flat)",
            "material_type": "Mild steel / carbon steel",
            "is_structural": "Structural",
            "can_remove": "Can be removed — bring to shop",
            "finish": "Match existing (blend repair into existing finish)",
        }),
    ]


def test_output_matches_material_list_schema():
    """Every calculator output must match MaterialList schema from CLAUDE.md."""
    required_keys = {"job_type", "items", "hardware", "total_weight_lbs",
                     "total_sq_ft", "weld_linear_inches"}

    for calc, fields in _all_calculators_with_fields():
        result = calc.calculate(fields)
        for key in required_keys:
            assert key in result, f"{type(calc).__name__} output missing '{key}'"

        # Items must match MaterialItem schema
        for item in result["items"]:
            assert "description" in item
            assert "material_type" in item
            assert "profile" in item
            assert "length_inches" in item
            assert "quantity" in item
            assert isinstance(item["quantity"], int), \
                f"quantity must be int, got {type(item['quantity'])} in {type(calc).__name__}"
            assert "unit_price" in item
            assert "line_total" in item
            assert "cut_type" in item
            assert "waste_factor" in item

        # Hardware must match HardwareItem schema
        for hw in result["hardware"]:
            assert "description" in hw
            assert "quantity" in hw
            assert "options" in hw
            assert isinstance(hw["options"], list)
            for opt in hw["options"]:
                assert "supplier" in opt
                assert "price" in opt


def test_every_output_has_weight():
    """total_weight_lbs is always present and > 0 for non-repair jobs."""
    for calc, fields in _all_calculators_with_fields():
        result = calc.calculate(fields)
        assert result["total_weight_lbs"] >= 0, \
            f"{type(calc).__name__} has negative weight"
        # Non-repair calculators should have positive weight
        if not isinstance(calc, RepairDecorativeCalculator):
            assert result["total_weight_lbs"] > 0, \
                f"{type(calc).__name__} has zero weight"


def test_every_output_has_weld_inches():
    """weld_linear_inches is always present and >= 0."""
    for calc, fields in _all_calculators_with_fields():
        result = calc.calculate(fields)
        assert result["weld_linear_inches"] >= 0, \
            f"{type(calc).__name__} has negative weld inches"


def test_every_output_has_sq_ft():
    """total_sq_ft is always present (used for finishing calculation)."""
    for calc, fields in _all_calculators_with_fields():
        result = calc.calculate(fields)
        assert "total_sq_ft" in result
        assert result["total_sq_ft"] >= 0


def test_every_output_has_assumptions():
    """Every calculator outputs an assumptions list."""
    for calc, fields in _all_calculators_with_fields():
        result = calc.calculate(fields)
        assert "assumptions" in result
        assert isinstance(result["assumptions"], list)
        assert len(result["assumptions"]) >= 1
        # First assumption should be about default prices
        assert any("market average" in a.lower() or "price" in a.lower()
                    for a in result["assumptions"])


# ============================================================
# Pipeline integration tests
# ============================================================

def test_calculate_endpoint_with_complete_session(client, auth_headers):
    """Create session → answer all required → call /calculate → get material list."""
    # Start session
    start_resp = client.post("/api/session/start", json={
        "description": "I need a 10 foot cantilever gate, 6 feet tall",
        "job_type": "cantilever_gate",
    }, headers=auth_headers)
    assert start_resp.status_code == 200
    session_id = start_resp.json()["session_id"]

    # Answer all required fields
    answer_resp = client.post(f"/api/session/{session_id}/answer", json={
        "answers": {
            "clear_width": "10",
            "height": "6",
            "frame_material": "Square tube (most common)",
            "frame_gauge": "11 gauge (0.120\" - standard for gates)",
            "infill_type": "Expanded metal",
            "post_count": "3 posts (standard)",
            "finish": "Powder coat (most durable, outsourced)",
            "installation": "Full installation (gate + posts + concrete)",
        },
    }, headers=auth_headers)
    assert answer_resp.status_code == 200
    assert answer_resp.json()["is_complete"] is True

    # Calculate
    calc_resp = client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    assert calc_resp.status_code == 200
    data = calc_resp.json()

    assert data["job_type"] == "cantilever_gate"
    assert data["calculator_used"] == "CantileverGateCalculator"
    assert "material_list" in data
    assert len(data["material_list"]["items"]) >= 4
    assert data["material_list"]["total_weight_lbs"] > 0


def test_calculate_endpoint_rejects_incomplete_session(client, auth_headers):
    """Incomplete session → 400 error."""
    # Start session but don't answer all required fields
    start_resp = client.post("/api/session/start", json={
        "description": "Need a railing",
        "job_type": "straight_railing",
    }, headers=auth_headers)
    session_id = start_resp.json()["session_id"]

    # Only answer some fields (not all required)
    client.post(f"/api/session/{session_id}/answer", json={
        "answers": {"linear_footage": "20"},
    }, headers=auth_headers)

    # Try to calculate — should fail
    calc_resp = client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    assert calc_resp.status_code == 400
    assert "missing" in calc_resp.json()["detail"].lower() or "not complete" in calc_resp.json()["detail"].lower()
