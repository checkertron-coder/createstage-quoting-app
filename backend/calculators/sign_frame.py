"""
Sign frame / bracket calculator.

Frame tube + mounting brackets. Varies by sign_type.
"""

import re
import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class SignFrameCalculator(BaseCalculator):

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
            ai_cuts = self._try_ai_cut_list("sign_frame", fields)
            if ai_cuts is not None:
                return self._build_from_ai_cuts("sign_frame", ai_cuts, fields, assumptions)

        # Parse inputs
        sign_type = fields.get("sign_type", "Post-mount sign frame (street/parking lot)")
        sign_dims = fields.get("sign_dimensions", "4 ft × 3 ft")
        sign_width_in, sign_height_in = self._parse_dims(sign_dims)

        mounting = fields.get("mounting_method", "Bolt-through (sign bolts to frame)")
        material = fields.get("material", "Mild steel (paint or powder coat)")

        frame_profile = "sq_tube_1.5x1.5_11ga"
        if "aluminum" in str(material).lower():
            frame_profile = "sq_tube_1.5x1.5_14ga"
        frame_price_ft = lookup.get_price_per_foot(frame_profile)

        # 1. Sign frame (perimeter)
        frame_perim_in = self.perimeter_inches(sign_width_in, sign_height_in)
        frame_ft = self.inches_to_feet(frame_perim_in)
        frame_weight = self.get_weight_lbs(frame_profile, frame_ft)

        items.append(self.make_material_item(
            description="Sign frame — %s (%.0f\" × %.0f\" perimeter)" % (
                frame_profile, sign_width_in, sign_height_in),
            material_type="square_tubing",
            profile=frame_profile,
            length_inches=frame_perim_in,
            quantity=self.linear_feet_to_pieces(frame_ft),
            unit_price=round(frame_ft * frame_price_ft / max(
                self.linear_feet_to_pieces(frame_ft), 1), 2),
            cut_type="miter_45",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += frame_weight
        total_weld_inches += 4 * 3.0  # 4 corner welds

        # 2. Internal cross members
        cross_count = 1 if sign_width_in <= 48 else 2
        cross_length_in = sign_height_in
        cross_ft = self.inches_to_feet(cross_length_in) * cross_count
        cross_weight = self.get_weight_lbs(frame_profile, cross_ft)

        items.append(self.make_material_item(
            description="Frame cross members — %s × %d" % (frame_profile, cross_count),
            material_type="square_tubing",
            profile=frame_profile,
            length_inches=cross_length_in,
            quantity=cross_count,
            unit_price=round(self.inches_to_feet(cross_length_in) * frame_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += cross_weight
        total_weld_inches += cross_count * 2 * 3.0

        # 3. Support structure by sign type
        if "post" in str(sign_type).lower():
            # Posts
            post_height_ft = self.parse_feet(fields.get("height_above_grade"), default=8.0)
            post_profile = "pipe_3_sch40"
            post_price_ft = lookup.get_price_per_foot(post_profile)
            post_count = 1 if sign_width_in <= 48 else 2
            post_length_in = self.feet_to_inches(post_height_ft) + 36  # +36" embed
            post_total_ft = self.inches_to_feet(post_length_in) * post_count
            post_weight = self.get_weight_lbs(post_profile, post_total_ft)

            items.append(self.make_material_item(
                description="Sign post — %s × %d (%.1f ft each, includes embed)" % (
                    post_profile, post_count, self.inches_to_feet(post_length_in)),
                material_type="mild_steel",
                profile=post_profile,
                length_inches=post_length_in,
                quantity=post_count,
                unit_price=round(self.inches_to_feet(post_length_in) * post_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += post_weight
            total_weld_inches += post_count * sign_height_in * 0.2  # Frame-to-post welds

        elif "wall" in str(sign_type).lower() or "bracket" in str(sign_type).lower() or "hanging" in str(sign_type).lower():
            # Wall mount brackets
            bracket_profile = "flat_bar_1.5x0.25"
            bracket_price_ft = lookup.get_price_per_foot(bracket_profile)
            bracket_count = 2 if sign_width_in <= 48 else 3
            bracket_length_in = 18.0  # Projection from wall

            bracket_ft = self.inches_to_feet(bracket_length_in) * bracket_count
            bracket_weight = self.get_weight_lbs(bracket_profile, bracket_ft)

            items.append(self.make_material_item(
                description="Wall mount brackets — %s × %d (%.0f\" projection)" % (
                    bracket_profile, bracket_count, bracket_length_in),
                material_type="flat_bar",
                profile=bracket_profile,
                length_inches=bracket_length_in,
                quantity=bracket_count,
                unit_price=round(self.inches_to_feet(bracket_length_in) * bracket_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_FLAT,
            ))
            total_weight += bracket_weight

        elif "monument" in str(sign_type).lower():
            # Monument base frame
            base_profile = "sq_tube_2x2_11ga"
            base_price_ft = lookup.get_price_per_foot(base_profile)
            base_width_in = sign_width_in + 12
            base_height_in = 12.0  # Base height
            base_perim_in = self.perimeter_inches(base_width_in, base_height_in)
            base_ft = self.inches_to_feet(base_perim_in)
            base_weight = self.get_weight_lbs(base_profile, base_ft)

            items.append(self.make_material_item(
                description="Monument base frame — %s (%.0f\" × %.0f\")" % (
                    base_profile, base_width_in, base_height_in),
                material_type="square_tubing",
                profile=base_profile,
                length_inches=base_perim_in,
                quantity=self.linear_feet_to_pieces(base_ft),
                unit_price=round(base_ft * base_price_ft, 2),
                cut_type="miter_45",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += base_weight

        # Surface area
        total_sq_ft = self.sq_ft_from_dimensions(sign_width_in, sign_height_in)

        assumptions.append(
            "Sign frame: %.0f\" × %.0f\", %s." % (
                sign_width_in, sign_height_in, sign_type.split("(")[0].strip()))
        assumptions.append("Sign panel material NOT included — frame and mounting structure only.")

        return self.make_material_list(
            job_type="sign_frame",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _parse_dims(self, dims_str):
        nums = re.findall(r'(\d+\.?\d*)', str(dims_str))
        is_feet = "ft" in str(dims_str).lower() or "'" in str(dims_str)

        if len(nums) >= 2:
            w, h = float(nums[0]), float(nums[1])
            if is_feet:
                w *= 12
                h *= 12
            return (max(w, 6.0), max(h, 6.0))
        elif len(nums) == 1:
            v = float(nums[0])
            if is_feet:
                v *= 12
            return (max(v, 6.0), max(v * 0.75, 6.0))
        return (48.0, 36.0)
