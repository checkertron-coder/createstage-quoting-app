"""
Rock slider / rocker guard calculator.

Main rail (DOM tube) + mount brackets (plate + tube).
Always sold as a pair (qty 2).
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class RockSliderCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
            "Rock sliders are always quoted as a pair (driver + passenger side).",
        ]

        # Parse inputs
        tube_str = fields.get("material_thickness",
                              "1.75\" OD × 0.120\" wall DOM (standard)")
        tube_profile, tube_od = self._parse_tube(tube_str)
        has_kick_out = "yes" in str(fields.get("kick_out", "No")).lower()
        has_top_plate = "plate" in str(fields.get("top_plate", "")).lower() or \
                        "diamond" in str(fields.get("top_plate", "")).lower()

        # Main rail length — typical cab-length ~60" for trucks, 70" for crew cabs
        rail_length_in = 60.0  # Default for standard cab
        vehicle = str(fields.get("vehicle_make_model", "")).lower()
        if "crew" in vehicle or "4-door" in vehicle or "4 door" in vehicle:
            rail_length_in = 72.0
        elif "short" in vehicle or "2-door" in vehicle or "2 door" in vehicle:
            rail_length_in = 48.0

        # 1. Main rails (DOM tube — pair)
        tube_price_ft = lookup.get_price_per_foot(tube_profile)
        if tube_price_ft == 0.0:
            tube_price_ft = 5.50  # Fallback for DOM
            assumptions.append("DOM tube price estimated at $5.50/ft.")

        total_rail_in = rail_length_in * 2  # Pair
        if has_kick_out:
            total_rail_in += 24 * 2  # ~12" kick-out each side × 2
        total_rail_ft = self.inches_to_feet(total_rail_in)
        rail_weight = self.get_weight_lbs(tube_profile, total_rail_ft)
        if rail_weight == 0.0:
            rail_weight = total_rail_ft * 3.5  # ~3.5 lb/ft estimate for 1.75" DOM

        items.append(self.make_material_item(
            description="Main rails — %s × 2 (%.0f\" each%s)" % (
                tube_profile, rail_length_in,
                " + kick-out" if has_kick_out else ""),
            material_type="dom_tubing",
            profile=tube_profile,
            length_inches=total_rail_in / 2,  # Per side
            quantity=self.apply_waste(2, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(total_rail_in / 2) * tube_price_ft, 2),
            cut_type="cope" if has_kick_out else "square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += rail_weight

        # 2. Mount brackets (4-6 per side, plate + tube gussets)
        brackets_per_side = 4
        if rail_length_in > 60:
            brackets_per_side = 5
        total_brackets = brackets_per_side * 2

        bracket_profile = "sq_tube_1.5x1.5_11ga"
        bracket_length_in = 8.0  # Typical mount bracket height
        bracket_price_ft = lookup.get_price_per_foot(bracket_profile)
        bracket_total_ft = self.inches_to_feet(bracket_length_in) * total_brackets
        bracket_weight = self.get_weight_lbs(bracket_profile, bracket_total_ft)

        items.append(self.make_material_item(
            description="Mount brackets — 1-1/2\" sq tube × %d (%d per side)" % (
                total_brackets, brackets_per_side),
            material_type="square_tubing",
            profile=bracket_profile,
            length_inches=bracket_length_in,
            quantity=self.apply_waste(total_brackets, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(bracket_length_in) * bracket_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += bracket_weight

        # Gusset plates
        gusset_count = total_brackets
        gusset_weight = self.get_plate_weight_lbs(4, 4, 0.1875) * gusset_count  # 3/16" gussets

        items.append(self.make_material_item(
            description="Gusset plates — 3/16\" × 4\" × 4\" × %d" % gusset_count,
            material_type="plate",
            profile="sheet_14ga",
            length_inches=4.0,
            quantity=gusset_count,
            unit_price=round(gusset_weight * 0.50 / max(gusset_count, 1), 2),
            cut_type="square",
            waste_factor=self.WASTE_SHEET,
        ))
        total_weight += gusset_weight

        # 3. Top plate (if applicable)
        if has_top_plate:
            plate_length_in = rail_length_in
            plate_width_in = 6.0  # Typical step width
            plate_sqft = self.sq_ft_from_dimensions(plate_length_in, plate_width_in) * 2
            plate_weight = self.get_plate_weight_lbs(plate_length_in, plate_width_in, 0.1196) * 2

            items.append(self.make_material_item(
                description="Top step plate — 11ga × %.0f\" × %.0f\" × 2 (pair)" % (
                    plate_length_in, plate_width_in),
                material_type="plate",
                profile="sheet_11ga",
                length_inches=plate_length_in,
                quantity=2,
                unit_price=round(plate_sqft / 2 * 2.65, 2),  # $2.65/sqft for 11ga
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += plate_weight
            total_sq_ft += plate_sqft

        # Weld totals
        total_weld_inches = total_brackets * 12  # Bracket-to-frame welds
        total_weld_inches += rail_length_in * 2 * 0.3  # Rail seams
        total_weld_inches += gusset_count * 8  # Gusset welds

        # Surface area
        circumference = math.pi * tube_od
        total_sq_ft += self.inches_to_feet(circumference) * self.inches_to_feet(total_rail_in)

        assumptions.append(
            "Rail length: %.0f\" per side based on vehicle type. %d mount brackets per side." % (
                rail_length_in, brackets_per_side))

        return self.make_material_list(
            job_type="rock_slider",
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
        if "1.5" in s:
            return ("round_tube_1.5_11ga", 1.5)
        return ("round_tube_2_11ga", 1.75)  # Default 1.75" → use 2" as closest
