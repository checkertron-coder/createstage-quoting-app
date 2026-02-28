"""
Roll cage / roll bar calculator.

Main hoop + down tubes + cross braces. Tube profile varies by cage_style.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()

# Tube footage estimates by cage style
CAGE_TUBE_FOOTAGE = {
    "Roll bar only (behind seats — minimal)": 12,
    "4-point cage (main hoop + down tubes)": 25,
    "6-point cage (4-point + door bars)": 40,
    "Full cage (multi-point, A-pillar to rear)": 65,
    "Custom — describe your needs": 45,
}


class RollCageCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # Parse inputs
        cage_style = fields.get("cage_style", "4-point cage (main hoop + down tubes)")
        tube_str = fields.get("tube_size",
                              "1.75\" × 0.120\" wall DOM (most common — street/trail)")
        tube_profile, tube_od = self._parse_tube(tube_str)

        vehicle_type = fields.get("vehicle_type", "Truck / SUV (off-road / prerunner)")
        door_str = fields.get("door_count", "2-door")
        has_gussets = "no" not in str(fields.get("gussets", "Yes")).lower()

        # Total tube footage for this cage style
        base_footage = CAGE_TUBE_FOOTAGE.get(cage_style, 40)

        # Adjust for vehicle type
        if "utv" in str(vehicle_type).lower() or "buggy" in str(vehicle_type).lower():
            base_footage = int(base_footage * 0.7)
        elif "4-door" in str(door_str).lower():
            base_footage = int(base_footage * 1.25)

        tube_total_ft = float(base_footage)

        # 1. Main cage tubing
        tube_price_ft = lookup.get_price_per_foot(tube_profile)
        if tube_price_ft == 0.0:
            tube_price_ft = 5.50
            assumptions.append("DOM tube price estimated at $5.50/ft.")

        tube_weight = self.get_weight_lbs(tube_profile, tube_total_ft)
        if tube_weight == 0.0:
            tube_weight = tube_total_ft * 3.0  # ~3 lb/ft estimate

        items.append(self.make_material_item(
            description="Cage tubing — %s (%.0f ft total — %s)" % (
                tube_profile, tube_total_ft, cage_style.split("(")[0].strip()),
            material_type="dom_tubing",
            profile=tube_profile,
            length_inches=self.feet_to_inches(tube_total_ft),
            quantity=self.linear_feet_to_pieces(tube_total_ft),
            unit_price=round(tube_total_ft * tube_price_ft / max(
                self.linear_feet_to_pieces(tube_total_ft), 1), 2),
            cut_type="cope",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += tube_weight

        # 2. Foot plates / mounting plates
        plate_count = self._foot_plate_count(cage_style)
        plate_weight = self.get_plate_weight_lbs(6, 6, 0.25) * plate_count

        items.append(self.make_material_item(
            description="Cage foot / mounting plates — 1/4\" × 6\" × 6\" × %d" % plate_count,
            material_type="plate",
            profile="plate_0.25",
            length_inches=6.0,
            quantity=plate_count,
            unit_price=round(plate_weight * 0.50 / max(plate_count, 1), 2),
            cut_type="square",
            waste_factor=self.WASTE_SHEET,
        ))
        total_weight += plate_weight

        # 3. Gussets
        if has_gussets:
            gusset_count = plate_count * 2  # 2 gussets per joint
            gusset_weight = self.get_plate_weight_lbs(3, 3, 0.1875) * gusset_count

            items.append(self.make_material_item(
                description="Gusset plates — 3/16\" × 3\" × 3\" × %d" % gusset_count,
                material_type="plate",
                profile="sheet_14ga",
                length_inches=3.0,
                quantity=gusset_count,
                unit_price=round(gusset_weight * 0.50 / max(gusset_count, 1), 2),
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += gusset_weight
            total_weld_inches += gusset_count * 6  # 6" weld per gusset

        # Weld totals (cage joints — heavily welded)
        joint_count = self._joint_count(cage_style)
        total_weld_inches += joint_count * math.pi * tube_od  # Full circumference weld per joint

        # Surface area (cylindrical tube surface)
        circumference_ft = self.inches_to_feet(math.pi * tube_od)
        total_sq_ft = circumference_ft * tube_total_ft

        assumptions.append(
            "%s — estimated %.0f ft of %.1f\" DOM tube. %d joints." % (
                cage_style.split("(")[0].strip(), tube_total_ft, tube_od, joint_count))
        if "chromoly" in str(tube_str).lower() or "4130" in str(tube_str).lower():
            assumptions.append("4130 chromoly requires TIG welding and post-weld normalization. "
                               "Do NOT powder coat 4130 — heat can weaken the material.")

        return self.make_material_list(
            job_type="roll_cage",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _parse_tube(self, tube_str):
        s = str(tube_str).lower()
        if "2\"" in s or "2 " in s:
            return ("round_tube_2_11ga", 2.0)
        if "1.625" in s:
            return ("round_tube_1.5_11ga", 1.625)
        if "1.5\"" in s or "1.5 " in s:
            return ("round_tube_1.5_11ga", 1.5)
        return ("round_tube_2_11ga", 1.75)

    def _foot_plate_count(self, cage_style):
        s = str(cage_style).lower()
        if "roll bar" in s:
            return 2
        if "4-point" in s:
            return 4
        if "6-point" in s:
            return 6
        if "full" in s:
            return 8
        return 4

    def _joint_count(self, cage_style):
        s = str(cage_style).lower()
        if "roll bar" in s:
            return 4
        if "4-point" in s:
            return 8
        if "6-point" in s:
            return 14
        if "full" in s:
            return 22
        return 10
