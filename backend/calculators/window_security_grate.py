"""
Window security grate calculator.

Frame perimeter + vertical/horizontal bars.
Batch multiplication for multiple windows.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class WindowSecurityGrateCalculator(BaseCalculator):

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
            ai_cuts = self._try_ai_cut_list("window_security_grate", fields)
            if ai_cuts is not None:
                return self._build_from_ai_cuts("window_security_grate", ai_cuts, fields, assumptions)

        # Parse inputs
        window_width_in = self.parse_inches(
            fields.get("window_width"),
            default=self.feet_to_inches(self.parse_feet(fields.get("window_width"), default=3.0))
        )
        if window_width_in < 12:
            window_width_in = self.feet_to_inches(window_width_in)

        window_height_in = self.parse_inches(
            fields.get("window_height"),
            default=self.feet_to_inches(self.parse_feet(fields.get("window_height"), default=4.0))
        )
        if window_height_in < 12:
            window_height_in = self.feet_to_inches(window_height_in)

        window_count = self.parse_int(fields.get("window_count",
                                                  fields.get("quantity")), default=1)
        if window_count < 1:
            window_count = 1

        bar_spacing_in = self.parse_inches(fields.get("bar_spacing"), default=4.0)
        has_crossbars = "yes" in str(fields.get("horizontal_bars",
                                                 fields.get("crossbars", "No"))).lower()

        fixed_or_hinged = fields.get("fixed_or_hinged", "Fixed")

        # Profiles
        frame_profile = "angle_1.5x1.5x0.125"
        bar_profile = "sq_bar_0.75"

        frame_price_ft = lookup.get_price_per_foot(frame_profile)
        bar_price_ft = lookup.get_price_per_foot(bar_profile)

        # 1. Frame (angle iron perimeter per window)
        frame_perimeter_in = self.perimeter_inches(window_width_in, window_height_in)
        frame_total_in = frame_perimeter_in * window_count
        frame_total_ft = self.inches_to_feet(frame_total_in)
        frame_weight = self.get_weight_lbs(frame_profile, frame_total_ft)

        items.append(self.make_material_item(
            description="Frame — 1-1/2\" × 1-1/2\" × 1/8\" angle × %d windows (%.0f\" perimeter each)" % (
                window_count, frame_perimeter_in),
            material_type="angle_iron",
            profile=frame_profile,
            length_inches=frame_perimeter_in,
            quantity=self.apply_waste(window_count * 4, self.WASTE_TUBE),  # 4 pieces per frame
            unit_price=round(self.inches_to_feet(frame_perimeter_in) * frame_price_ft / 4, 2),
            cut_type="miter_45",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += frame_weight

        # 2. Vertical bars
        num_vertical_bars = math.ceil(window_width_in / bar_spacing_in) - 1
        if num_vertical_bars < 1:
            num_vertical_bars = 1
        total_vert_bars = num_vertical_bars * window_count
        vert_bar_length_in = window_height_in - 1  # Slightly shorter than frame
        vert_total_ft = self.inches_to_feet(vert_bar_length_in) * total_vert_bars
        vert_weight = self.get_weight_lbs(bar_profile, vert_total_ft)

        items.append(self.make_material_item(
            description="Vertical bars — 3/4\" sq bar × %d per window × %d windows" % (
                num_vertical_bars, window_count),
            material_type="square_tubing",
            profile=bar_profile,
            length_inches=vert_bar_length_in,
            quantity=self.apply_waste(total_vert_bars, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(vert_bar_length_in) * bar_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += vert_weight
        total_weld_inches += self.weld_inches_for_joints(total_vert_bars * 2, 1.5)

        # 3. Horizontal crossbars (if applicable)
        if has_crossbars:
            num_horiz_bars = math.ceil(window_height_in / bar_spacing_in) - 1
            if num_horiz_bars < 1:
                num_horiz_bars = 1
            total_horiz_bars = num_horiz_bars * window_count
            horiz_bar_length_in = window_width_in - 1
            horiz_total_ft = self.inches_to_feet(horiz_bar_length_in) * total_horiz_bars
            horiz_weight = self.get_weight_lbs(bar_profile, horiz_total_ft)

            items.append(self.make_material_item(
                description="Horizontal crossbars — 3/4\" sq bar × %d per window × %d windows" % (
                    num_horiz_bars, window_count),
                material_type="square_tubing",
                profile=bar_profile,
                length_inches=horiz_bar_length_in,
                quantity=self.apply_waste(total_horiz_bars, self.WASTE_TUBE),
                unit_price=round(self.inches_to_feet(horiz_bar_length_in) * bar_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += horiz_weight
            total_weld_inches += self.weld_inches_for_joints(total_horiz_bars * 2, 1.5)

        # 4. Hinges (if hinged)
        if "hinged" in str(fixed_or_hinged).lower() or "swing" in str(fixed_or_hinged).lower():
            hardware.append(self.make_hardware_item(
                description="Security grate hinges (pair per window)",
                quantity=window_count,
                options=lookup.get_hardware_options("standard_weld_hinge_pair"),
            ))
            # Padlock hasp
            hardware.append(self.make_hardware_item(
                description="Padlock hasp / latch",
                quantity=window_count,
                options=lookup.get_hardware_options("gravity_latch"),
            ))

        # Frame welds (corners)
        total_weld_inches += self.weld_inches_for_joints(window_count * 4, 2.0)

        # Surface area
        total_sq_ft = self.sq_ft_from_dimensions(window_width_in, window_height_in) * window_count

        assumptions.append(
            "%d window(s), %.0f\" × %.0f\" each. %d vertical bars at %.0f\" spacing." % (
                window_count, window_width_in, window_height_in, num_vertical_bars, bar_spacing_in))
        if has_crossbars:
            assumptions.append("Crossbar pattern included.")
        if "hinged" in str(fixed_or_hinged).lower():
            assumptions.append("Hinged grates include hinges and padlock hasp.")

        return self.make_material_list(
            job_type="window_security_grate",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )
