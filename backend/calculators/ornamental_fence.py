"""
Ornamental fence material calculator.

Panel-based: total footage / panel width = panel count.
Each panel has top rail, bottom rail, and pickets.
Posts between panels.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class OrnamentalFenceCalculator(BaseCalculator):

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
            ai_cuts = self._try_ai_cut_list("ornamental_fence", fields)
            if ai_cuts is not None:
                return self._build_from_ai_cuts("ornamental_fence", ai_cuts, fields, assumptions)

        # Parse inputs
        total_footage = self.parse_feet(fields.get("total_footage",
                                                    fields.get("linear_footage")), default=50.0)
        height_ft = self.parse_feet(fields.get("fence_height",
                                                fields.get("height")), default=6.0)
        height_in = self.feet_to_inches(height_ft)

        panel_width_ft = self.parse_feet(fields.get("panel_width"), default=6.0)
        panel_width_in = self.feet_to_inches(panel_width_ft)

        picket_spacing_in = 4.0  # Code compliant default
        spacing_str = fields.get("picket_spacing", "")
        if "3.5" in str(spacing_str) or "3-1/2" in str(spacing_str):
            picket_spacing_in = 3.5
        elif "5" in str(spacing_str):
            picket_spacing_in = 5.0

        picket_profile = fields.get("picket_style", "")
        if "round" in str(picket_profile).lower():
            picket_key = "round_bar_0.625"
            picket_mat = "flat_bar"
        elif "flat" in str(picket_profile).lower():
            picket_key = "flat_bar_1x0.25"
            picket_mat = "flat_bar"
        else:
            picket_key = "sq_bar_0.75"
            picket_mat = "square_tubing"

        rail_profile = "sq_tube_1.5x1.5_11ga"
        post_profile = "sq_tube_2x2_11ga"

        # Calculations
        panel_count = math.ceil(total_footage / panel_width_ft)
        post_count = panel_count + 1

        # 1. Posts
        post_embed_in = 36.0  # 3 ft embed
        post_length_in = height_in + post_embed_in + 2  # +2" above fence
        post_total_ft = self.inches_to_feet(post_length_in) * post_count
        post_price_ft = lookup.get_price_per_foot(post_profile)
        post_weight = self.get_weight_lbs(post_profile, post_total_ft)

        items.append(self.make_material_item(
            description="Posts — 2\" sq tube 11ga × %d (%.1f ft each, includes %d\" embed)" % (
                post_count, self.inches_to_feet(post_length_in), int(post_embed_in)),
            material_type="square_tubing",
            profile=post_profile,
            length_inches=post_length_in,
            quantity=self.apply_waste(post_count, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(post_length_in) * post_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += post_weight

        # 2. Top and bottom rails (per panel)
        rail_price_ft = lookup.get_price_per_foot(rail_profile)
        total_rail_in = panel_width_in * panel_count * 2  # top + bottom per panel
        total_rail_ft = self.inches_to_feet(total_rail_in)
        rail_weight = self.get_weight_lbs(rail_profile, total_rail_ft)

        items.append(self.make_material_item(
            description="Top + bottom rails — 1-1/2\" sq tube 11ga × %d panels (%.1f ft total)" % (
                panel_count, total_rail_ft),
            material_type="square_tubing",
            profile=rail_profile,
            length_inches=total_rail_in,
            quantity=self.linear_feet_to_pieces(total_rail_ft),
            unit_price=round(total_rail_ft * rail_price_ft / max(self.linear_feet_to_pieces(total_rail_ft), 1), 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += rail_weight

        # 3. Pickets
        pickets_per_panel = math.ceil(panel_width_in / picket_spacing_in) + 1
        total_pickets = pickets_per_panel * panel_count
        picket_length_in = height_in - 4  # Between rails
        picket_total_ft = self.inches_to_feet(picket_length_in) * total_pickets
        picket_price_ft = lookup.get_price_per_foot(picket_key)
        picket_weight = self.get_weight_lbs(picket_key, picket_total_ft)

        items.append(self.make_material_item(
            description="Pickets — %s at %.0f\" OC × %d total (%d per panel × %d panels)" % (
                picket_key, picket_spacing_in, total_pickets, pickets_per_panel, panel_count),
            material_type=picket_mat,
            profile=picket_key,
            length_inches=picket_length_in,
            quantity=self.apply_waste(total_pickets, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(picket_length_in) * picket_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += picket_weight

        # Weld: 2 tack welds per picket (top + bottom) + rail-to-post welds
        total_weld_inches = self.weld_inches_for_joints(total_pickets * 2, 1.5)
        total_weld_inches += self.weld_inches_for_joints(panel_count * 4, 3.0)  # Rail-to-post

        # Surface area (both sides)
        total_sq_ft = total_footage * height_ft * 2

        assumptions.append(
            "%d panels at %.0f ft each, %d pickets per panel at %.0f\" OC." % (
                panel_count, panel_width_ft, pickets_per_panel, picket_spacing_in))
        assumptions.append("Post embed depth: %.0f\" (concrete not included in material list)." % post_embed_in)

        return self.make_material_list(
            job_type="ornamental_fence",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )
