"""
Complete stair calculator — stringers, treads, risers, landing.

Uses rise/run geometry to determine stringer length and tread count.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class CompleteStairCalculator(BaseCalculator):

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
            ai_cuts = self._try_ai_cut_list("complete_stair", fields)
            if ai_cuts is not None:
                return self._build_from_ai_cuts("complete_stair", ai_cuts, fields, assumptions)

        # Parse inputs
        total_rise_ft = self.parse_feet(fields.get("total_rise",
                                                    fields.get("height")), default=10.0)
        total_rise_in = self.feet_to_inches(total_rise_ft)

        rise_per_step_in = self.parse_inches(fields.get("rise_per_step"), default=7.5)
        run_per_step_in = self.parse_inches(fields.get("run_per_step",
                                                        fields.get("tread_depth")), default=10.0)

        stair_width_in = self.parse_inches(
            fields.get("stair_width"),
            default=self.feet_to_inches(self.parse_feet(fields.get("width"), default=3.0))
        )
        if stair_width_in < 12:
            stair_width_in = self.feet_to_inches(stair_width_in)  # Likely given in feet

        num_risers = self.parse_int(fields.get("num_risers"), default=0)
        if num_risers == 0:
            num_risers = max(math.ceil(total_rise_in / rise_per_step_in), 1)

        num_treads = num_risers  # Treads = risers (top tread is landing)
        has_landing = "yes" in str(fields.get("has_landing", "No")).lower()

        # Stringer geometry
        total_run_in = num_risers * run_per_step_in
        stringer_length_in = math.sqrt(total_rise_in ** 2 + total_run_in ** 2)
        stringer_length_ft = self.inches_to_feet(stringer_length_in)

        # 1. Stringers (2x channel or tube)
        stringer_profile = "channel_6x8.2"
        stringer_price_ft = lookup.get_price_per_foot(stringer_profile)
        stringer_count = 2
        if stair_width_in > 48:
            stringer_count = 3  # Center stringer for wide stairs
            assumptions.append("Stair width > 48\" — center stringer added.")

        stringer_total_ft = stringer_length_ft * stringer_count
        stringer_weight = self.get_weight_lbs(stringer_profile, stringer_total_ft)

        items.append(self.make_material_item(
            description="Stringers — C6×8.2 channel × %d (%.1f ft each)" % (
                stringer_count, stringer_length_ft),
            material_type="channel",
            profile=stringer_profile,
            length_inches=stringer_length_in,
            quantity=self.apply_waste(stringer_count, self.WASTE_TUBE),
            unit_price=round(stringer_length_ft * stringer_price_ft, 2),
            cut_type="miter_45",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += stringer_weight

        # 2. Treads (checker plate or grating)
        tread_profile = "sheet_11ga"
        tread_price_sqft = lookup.get_price_per_sqft(tread_profile)
        if tread_price_sqft == 0.0:
            tread_price_sqft = 2.65
        tread_area_sqft = self.sq_ft_from_dimensions(stair_width_in, run_per_step_in)
        total_tread_sqft = tread_area_sqft * num_treads
        tread_sheets = self.apply_waste(math.ceil(total_tread_sqft / 32.0), self.WASTE_SHEET)
        tread_weight = self.get_plate_weight_lbs(stair_width_in, run_per_step_in, 0.1196) * num_treads

        items.append(self.make_material_item(
            description="Treads — 11ga checker plate × %d (%.0f\" × %.0f\" each)" % (
                num_treads, stair_width_in, run_per_step_in),
            material_type="plate",
            profile=tread_profile,
            length_inches=stair_width_in,
            quantity=tread_sheets,
            unit_price=round(total_tread_sqft * tread_price_sqft / max(tread_sheets, 1), 2),
            cut_type="square",
            waste_factor=self.WASTE_SHEET,
        ))
        total_weight += tread_weight

        # 3. Tread support angles (clip angles under each tread, welded to stringer)
        angle_profile = "angle_2x2x0.1875"
        angle_price_ft = lookup.get_price_per_foot(angle_profile)
        angle_length_in = stair_width_in
        angle_total_ft = self.inches_to_feet(angle_length_in) * num_treads * 2  # 2 per tread
        angle_weight = self.get_weight_lbs(angle_profile, angle_total_ft)

        items.append(self.make_material_item(
            description="Tread support angles — 2\"×2\"×3/16\" × %d pairs" % num_treads,
            material_type="angle_iron",
            profile=angle_profile,
            length_inches=angle_length_in,
            quantity=self.apply_waste(num_treads * 2, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(angle_length_in) * angle_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += angle_weight

        # 4. Landing platform (if applicable)
        if has_landing:
            landing_width_in = stair_width_in
            landing_depth_in = max(stair_width_in, 36.0)  # Minimum 3 ft
            landing_area_sqft = self.sq_ft_from_dimensions(landing_width_in, landing_depth_in)

            # Landing frame
            landing_frame_profile = "sq_tube_2x2_11ga"
            landing_frame_in = self.perimeter_inches(landing_width_in, landing_depth_in)
            landing_frame_ft = self.inches_to_feet(landing_frame_in)
            landing_frame_price = lookup.get_price_per_foot(landing_frame_profile)
            landing_frame_weight = self.get_weight_lbs(landing_frame_profile, landing_frame_ft)

            items.append(self.make_material_item(
                description="Landing frame — 2\" sq tube 11ga (%.0f\" × %.0f\")" % (
                    landing_width_in, landing_depth_in),
                material_type="square_tubing",
                profile=landing_frame_profile,
                length_inches=landing_frame_in,
                quantity=self.linear_feet_to_pieces(landing_frame_ft),
                unit_price=round(landing_frame_ft * landing_frame_price, 2),
                cut_type="miter_45",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += landing_frame_weight
            total_sq_ft += landing_area_sqft

        # Weld: tread supports to stringers + tread to angles
        total_weld_inches = self.weld_inches_for_joints(num_treads * stringer_count * 2, 3.0)
        total_weld_inches += self.weld_inches_for_joints(num_treads * 2, stair_width_in * 0.2)

        # Surface area
        total_sq_ft += total_tread_sqft + stringer_length_ft * 2 * stringer_count

        assumptions.append(
            "%d risers at %.1f\" rise × %.1f\" run. Stringer length: %.1f ft." % (
                num_risers, rise_per_step_in, run_per_step_in, stringer_length_ft))
        assumptions.append("Stair width: %.0f\"." % stair_width_in)

        return self.make_material_list(
            job_type="complete_stair",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )
