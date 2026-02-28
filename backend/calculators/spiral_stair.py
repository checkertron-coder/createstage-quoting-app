"""
Spiral stair calculator — center column, pie-shaped treads, handrail.

Tread count = total_rise / rise_per_step.
Handrail is approximately circumference × number of turns.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class SpiralStairCalculator(BaseCalculator):

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
        total_rise_ft = self.parse_feet(fields.get("total_rise",
                                                    fields.get("height")), default=10.0)
        total_rise_in = self.feet_to_inches(total_rise_ft)

        diameter_in = self.parse_inches(
            fields.get("diameter"),
            default=self.feet_to_inches(self.parse_feet(fields.get("diameter"), default=5.0))
        )
        if diameter_in < 24:
            diameter_in = self.feet_to_inches(diameter_in)  # Likely given in feet

        rise_per_step_in = self.parse_inches(fields.get("rise_per_step"), default=7.5)
        rotation_degrees = self.parse_number(fields.get("rotation_per_step"), default=30.0)

        num_treads = max(math.ceil(total_rise_in / rise_per_step_in), 1)

        # 1. Center column (pipe)
        column_profile = "pipe_4_sch40"
        column_length_in = total_rise_in + 42  # Extend above for handrail connection
        column_length_ft = self.inches_to_feet(column_length_in)
        column_price_ft = lookup.get_price_per_foot(column_profile)
        column_weight = self.get_weight_lbs(column_profile, column_length_ft)

        items.append(self.make_material_item(
            description="Center column — 4\" pipe Sch 40 (%.1f ft)" % column_length_ft,
            material_type="mild_steel",
            profile=column_profile,
            length_inches=column_length_in,
            quantity=self.linear_feet_to_pieces(column_length_ft),
            unit_price=round(column_length_ft * column_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += column_weight

        # 2. Treads (pie-shaped plates)
        tread_radius_in = (diameter_in / 2) - 2  # Minus column radius clearance
        tread_arc_angle = rotation_degrees * math.pi / 180
        tread_area_sqin = 0.5 * tread_radius_in ** 2 * tread_arc_angle
        tread_area_sqft = tread_area_sqin / 144.0
        total_tread_sqft = tread_area_sqft * num_treads

        tread_profile = "sheet_11ga"
        tread_price_sqft = lookup.get_price_per_sqft(tread_profile)
        if tread_price_sqft == 0.0:
            tread_price_sqft = 2.65
        tread_sheets = self.apply_waste(math.ceil(total_tread_sqft / 32.0), self.WASTE_SHEET)
        tread_weight = self.get_plate_weight_lbs(
            tread_radius_in, tread_radius_in * 0.5, 0.1196) * num_treads

        items.append(self.make_material_item(
            description="Treads — 11ga plate × %d pie-shaped (%.0f\" radius)" % (
                num_treads, tread_radius_in),
            material_type="plate",
            profile=tread_profile,
            length_inches=tread_radius_in,
            quantity=tread_sheets,
            unit_price=round(total_tread_sqft * tread_price_sqft / max(tread_sheets, 1), 2),
            cut_type="notch",
            waste_factor=self.WASTE_SHEET,
        ))
        total_weight += tread_weight

        # 3. Tread support arms (tube from column to tread edge)
        arm_profile = "sq_tube_1.5x1.5_11ga"
        arm_length_in = tread_radius_in
        arm_price_ft = lookup.get_price_per_foot(arm_profile)
        arm_total_ft = self.inches_to_feet(arm_length_in) * num_treads
        arm_weight = self.get_weight_lbs(arm_profile, arm_total_ft)

        items.append(self.make_material_item(
            description="Tread support arms — 1-1/2\" sq tube × %d (%.0f\" each)" % (
                num_treads, arm_length_in),
            material_type="square_tubing",
            profile=arm_profile,
            length_inches=arm_length_in,
            quantity=self.apply_waste(num_treads, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(arm_length_in) * arm_price_ft, 2),
            cut_type="cope",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += arm_weight

        # 4. Handrail (bent tube — spiral path)
        total_rotation_deg = rotation_degrees * num_treads
        num_turns = total_rotation_deg / 360.0
        circumference_in = math.pi * diameter_in
        handrail_length_in = math.sqrt(
            (circumference_in * num_turns) ** 2 + total_rise_in ** 2
        )
        handrail_length_ft = self.inches_to_feet(handrail_length_in)
        handrail_profile = "round_tube_1.5_14ga"
        handrail_price_ft = lookup.get_price_per_foot(handrail_profile)
        handrail_weight = self.get_weight_lbs(handrail_profile, handrail_length_ft)

        items.append(self.make_material_item(
            description="Handrail — 1-1/2\" round tube (%.1f ft spiral path)" % handrail_length_ft,
            material_type="dom_tubing",
            profile=handrail_profile,
            length_inches=handrail_length_in,
            quantity=self.linear_feet_to_pieces(handrail_length_ft),
            unit_price=round(handrail_length_ft * handrail_price_ft / max(
                self.linear_feet_to_pieces(handrail_length_ft), 1), 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += handrail_weight

        # 5. Balusters (between treads, on outer edge)
        baluster_profile = "sq_bar_0.625"
        baluster_length_in = rise_per_step_in + 6  # Between tread levels
        balusters_per_tread = 3  # Typical
        total_balusters = balusters_per_tread * num_treads
        baluster_price_ft = lookup.get_price_per_foot(baluster_profile)
        baluster_total_ft = self.inches_to_feet(baluster_length_in) * total_balusters
        baluster_weight = self.get_weight_lbs(baluster_profile, baluster_total_ft)

        items.append(self.make_material_item(
            description="Balusters — 5/8\" sq bar × %d (%d per tread)" % (
                total_balusters, balusters_per_tread),
            material_type="square_tubing",
            profile=baluster_profile,
            length_inches=baluster_length_in,
            quantity=self.apply_waste(total_balusters, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(baluster_length_in) * baluster_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += baluster_weight

        # Weld totals
        total_weld_inches = self.weld_inches_for_joints(num_treads * 4, 3.0)  # Arms to column
        total_weld_inches += self.weld_inches_for_joints(total_balusters * 2, 1.5)

        # Surface area
        total_sq_ft = total_tread_sqft + handrail_length_ft * 0.5

        assumptions.append(
            "%d treads at %.1f\" rise, %.0f\" diameter. %.1f turns total." % (
                num_treads, rise_per_step_in, diameter_in, num_turns))
        assumptions.append("Handrail is rolled/bent tube — requires roll bending.")

        return self.make_material_list(
            job_type="spiral_stair",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )
