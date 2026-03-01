"""
Off-road bumper calculator.

Plate cuts for main body + tube for structure + mounts.
Parametric by bumper_position (front/rear).
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class OffroadBumperCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # Try AI cut list for custom/complex designs
        if self._has_description(fields):
            ai_cuts = self._try_ai_cut_list("offroad_bumper", fields)
            if ai_cuts is not None:
                return self._build_from_ai_cuts("offroad_bumper", ai_cuts, fields, assumptions)

        # Parse inputs
        position = fields.get("bumper_position", "Front bumper")
        is_front = "front" in str(position).lower()
        is_both = "both" in str(position).lower()
        bumper_count = 2 if is_both else 1

        thickness_str = fields.get("material_thickness", "1/4\" (standard — most common)")
        plate_thickness_in = self._parse_thickness(thickness_str)
        plate_profile = self._thickness_to_profile(plate_thickness_in)

        has_winch = "yes" in str(fields.get("winch_mount", "No")).lower()
        has_d_rings = "yes" in str(fields.get("d_ring_mounts", "No")).lower()

        style = fields.get("bumper_style", "Full-width plate bumper (maximum protection)")
        is_stubby = "stubby" in str(style).lower() or "mid-width" in str(style).lower()
        is_tube = "tube" in str(style).lower() or "pre-runner" in str(style).lower()

        for bumper_num in range(bumper_count):
            label = "Front" if (is_front or (is_both and bumper_num == 0)) else "Rear"

            # Base dimensions by style
            if is_stubby:
                width_in = 48.0
                height_in = 14.0
            elif is_tube:
                width_in = 60.0
                height_in = 12.0
            else:
                width_in = 60.0
                height_in = 16.0

            # 1. Main plate panels
            plate_sqft = self.sq_ft_from_dimensions(width_in, height_in)
            plate_weight = self.get_plate_weight_lbs(width_in, height_in, plate_thickness_in)
            plate_price_sqft = lookup.get_price_per_sqft("sheet_11ga")
            if plate_price_sqft == 0.0:
                plate_price_sqft = 2.65
            # Adjust price for thickness
            price_multiplier = plate_thickness_in / 0.1196  # Relative to 11ga
            adjusted_price = plate_price_sqft * price_multiplier

            if not is_tube:
                items.append(self.make_material_item(
                    description="%s bumper main plate — %.3f\" × %.0f\" × %.0f\"" % (
                        label, plate_thickness_in, width_in, height_in),
                    material_type="plate",
                    profile=plate_profile,
                    length_inches=width_in,
                    quantity=1,
                    unit_price=round(plate_sqft * adjusted_price, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_SHEET,
                ))
                total_weight += plate_weight

                # Side wings / return panels (2 per bumper)
                wing_width_in = 12.0
                wing_height_in = height_in
                wing_weight = self.get_plate_weight_lbs(wing_width_in, wing_height_in, plate_thickness_in)
                wing_sqft = self.sq_ft_from_dimensions(wing_width_in, wing_height_in)

                items.append(self.make_material_item(
                    description="%s bumper side returns — %.3f\" plate × 2" % (label, plate_thickness_in),
                    material_type="plate",
                    profile=plate_profile,
                    length_inches=wing_width_in,
                    quantity=2,
                    unit_price=round(wing_sqft * adjusted_price, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_SHEET,
                ))
                total_weight += wing_weight * 2

            # 2. Structural tubing / push bar
            tube_profile = "round_tube_2_11ga"
            tube_price_ft = lookup.get_price_per_foot(tube_profile)

            if is_tube or is_front:
                # Push bar / tube structure
                tube_length_in = width_in + 24  # Wrap-around
                tube_length_ft = self.inches_to_feet(tube_length_in)
                tube_weight = self.get_weight_lbs(tube_profile, tube_length_ft)

                items.append(self.make_material_item(
                    description="%s bumper tube structure — 2\" round tube (%.1f ft)" % (
                        label, tube_length_ft),
                    material_type="dom_tubing",
                    profile=tube_profile,
                    length_inches=tube_length_in,
                    quantity=self.linear_feet_to_pieces(tube_length_ft),
                    unit_price=round(tube_length_ft * tube_price_ft, 2),
                    cut_type="cope",
                    waste_factor=self.WASTE_TUBE,
                ))
                total_weight += tube_weight

            # 3. Frame mount brackets (plate)
            bracket_count = 4
            bracket_weight = self.get_plate_weight_lbs(8, 6, plate_thickness_in) * bracket_count

            items.append(self.make_material_item(
                description="%s bumper frame mount brackets × %d" % (label, bracket_count),
                material_type="plate",
                profile=plate_profile,
                length_inches=8.0,
                quantity=bracket_count,
                unit_price=round(bracket_weight * 0.50 / bracket_count, 2),
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += bracket_weight

            # 4. Winch mount plate (front only)
            if has_winch and (is_front or bumper_num == 0):
                winch_plate_weight = self.get_plate_weight_lbs(10, 4.5, 0.375)  # 3/8" winch plate
                items.append(self.make_material_item(
                    description="Winch mount plate — 3/8\" × 10\" × 4.5\"",
                    material_type="plate",
                    profile="plate_0.375",
                    length_inches=10.0,
                    quantity=1,
                    unit_price=round(winch_plate_weight * 0.50, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_SHEET,
                ))
                total_weight += winch_plate_weight
                assumptions.append("Winch plate: 3/8\" × 10\" × 4.5\" with standard bolt pattern.")

            # 5. D-ring mounts
            if has_d_rings:
                d_ring_weight = self.get_plate_weight_lbs(6, 4, 0.375) * 2
                items.append(self.make_material_item(
                    description="%s D-ring / shackle mount plates × 2" % label,
                    material_type="plate",
                    profile="plate_0.375",
                    length_inches=6.0,
                    quantity=2,
                    unit_price=round(d_ring_weight * 0.50 / 2, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_SHEET,
                ))
                total_weight += d_ring_weight
                # D-ring hardware
                hardware.append(self.make_hardware_item(
                    description="3/4\" D-ring shackle",
                    quantity=2,
                    options=[
                        {"supplier": "Amazon", "price": 25.00, "url": "", "part_number": None, "lead_days": 5},
                        {"supplier": "McMaster-Carr", "price": 32.00, "url": "", "part_number": None, "lead_days": 3},
                        {"supplier": "Grainger", "price": 35.00, "url": "", "part_number": None, "lead_days": 2},
                    ],
                ))

            # Weld inches for this bumper
            total_weld_inches += width_in * 2  # Top and bottom seams
            total_weld_inches += height_in * 4  # Side returns
            total_weld_inches += bracket_count * 12  # Bracket welds

            # Surface area
            total_sq_ft += plate_sqft * 2 + self.sq_ft_from_dimensions(wing_width_in, wing_height_in) * 4 if not is_tube else plate_sqft

        assumptions.append(
            "%s bumper, %s style, %.3f\" plate." % (
                "Front + Rear" if is_both else ("Front" if is_front else "Rear"),
                "stubby" if is_stubby else ("tube" if is_tube else "full-width"),
                plate_thickness_in))

        return self.make_material_list(
            job_type="offroad_bumper",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _parse_thickness(self, s):
        s = str(s)
        if "3/16" in s:
            return 0.1875
        if "3/8" in s:
            return 0.375
        return 0.25  # Default 1/4"

    def _thickness_to_profile(self, thickness):
        if thickness <= 0.19:
            return "sheet_14ga"
        if thickness >= 0.35:
            return "sheet_11ga"
        return "sheet_11ga"
