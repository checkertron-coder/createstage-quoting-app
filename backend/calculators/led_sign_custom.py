"""
Custom LED / illuminated sign calculator.

Channel letter / cabinet estimate. Routes by sign_type.
Uses BaseCalculator AI methods — logging, price fallbacks, consistent behavior.
"""

import re
import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class LedSignCustomCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # Try AI cut list when description exists
        if self._has_description(fields):
            ai_result = self._try_ai_cut_list("led_sign_custom", fields)
            if ai_result is not None:
                return self._build_from_ai_cuts("led_sign_custom", ai_result, fields, assumptions)

        return self._template_calculate(fields, assumptions)

    def _template_calculate(self, fields: dict, assumptions: list) -> dict:
        """Template-based calculation when AI is unavailable."""
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0

        # Parse inputs
        sign_type = fields.get("sign_type", "Channel letters (individual 3D letters)")
        dims_str = fields.get("dimensions", "8 ft x 2 ft")
        letter_height_str = fields.get("letter_height", "18")
        letter_count = self.parse_int(fields.get("letter_count"), default=8)
        material_str = fields.get("material", "Aluminum (standard for sign fabrication)")

        overall_width_in, overall_height_in = self._parse_dims(dims_str)
        letter_height_in = self._parse_letter_height(letter_height_str)

        is_aluminum = "aluminum" in str(material_str).lower()
        is_stainless = "stainless" in str(material_str).lower()

        if "channel" in str(sign_type).lower() or "halo" in str(sign_type).lower():
            # Channel letters — individual 3D fabricated letters
            avg_letter_width_in = letter_height_in * 0.6
            return_depth_in = 5.0

            return_profile = "flat_bar_1x0.25" if not is_aluminum else "flat_bar_1x0.1875"
            return_price_ft = lookup.get_price_per_foot(return_profile)

            avg_perim_in = 2 * (letter_height_in + avg_letter_width_in)
            total_return_in = avg_perim_in * letter_count
            total_return_ft = self.inches_to_feet(total_return_in)
            return_weight = self.get_weight_lbs(return_profile, total_return_ft)

            items.append(self.make_material_item(
                description="Channel letter returns — %s x %d letters (%.0f\" avg perimeter)" % (
                    return_profile, letter_count, avg_perim_in),
                material_type="flat_bar" if not is_aluminum else "aluminum_6061",
                profile=return_profile,
                length_inches=avg_perim_in,
                quantity=self.apply_waste(letter_count, self.WASTE_FLAT),
                unit_price=round(self.inches_to_feet(avg_perim_in) * return_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_FLAT,
            ))
            total_weight += return_weight

            face_area_sqin = letter_height_in * avg_letter_width_in * letter_count
            face_area_sqft = face_area_sqin / 144.0 * 2
            sheet_profile = "sheet_16ga"
            sheet_price_sqft = lookup.get_price_per_sqft(sheet_profile)
            if sheet_price_sqft == 0.0:
                sheet_price_sqft = 1.56
            if is_aluminum:
                sheet_price_sqft *= 1.5
            if is_stainless:
                sheet_price_sqft *= 3.0

            sheet_count = self.apply_waste(math.ceil(face_area_sqft / 32.0), self.WASTE_SHEET)
            face_weight = face_area_sqft * 1.5

            items.append(self.make_material_item(
                description="Letter faces + backs — %s %s (%.1f sq ft total)" % (
                    "aluminum" if is_aluminum else ("stainless" if is_stainless else "steel"),
                    sheet_profile, face_area_sqft),
                material_type="aluminum_6061" if is_aluminum else (
                    "stainless_304" if is_stainless else "plate"),
                profile=sheet_profile,
                length_inches=letter_height_in,
                quantity=sheet_count,
                unit_price=round(face_area_sqft * sheet_price_sqft / max(sheet_count, 1), 2),
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += face_weight

            total_weld_inches = total_return_in * 0.3
            total_sq_ft = face_area_sqft

            assumptions.append(
                "%d channel letters at %.0f\" height, %.0f\" deep returns. "
                "LED modules and power supplies NOT included." % (
                    letter_count, letter_height_in, return_depth_in))

        elif "cabinet" in str(sign_type).lower() or "box" in str(sign_type).lower() or \
             "light box" in str(sign_type).lower():
            cabinet_depth_in = 6.0

            front_sqft = self.sq_ft_from_dimensions(overall_width_in, overall_height_in)
            side_sqft = self.sq_ft_from_dimensions(cabinet_depth_in, overall_height_in) * 2
            top_bottom_sqft = self.sq_ft_from_dimensions(overall_width_in, cabinet_depth_in) * 2
            back_sqft = front_sqft
            total_sheet_sqft = side_sqft + top_bottom_sqft + back_sqft

            sheet_profile = "sheet_16ga"
            sheet_price_sqft = lookup.get_price_per_sqft(sheet_profile)
            if sheet_price_sqft == 0.0:
                sheet_price_sqft = 1.56
            if is_aluminum:
                sheet_price_sqft *= 1.5

            sheet_count = self.apply_waste(math.ceil(total_sheet_sqft / 32.0), self.WASTE_SHEET)
            cabinet_weight = total_sheet_sqft * 1.5

            items.append(self.make_material_item(
                description="Cabinet box — %s (%.0f\" x %.0f\" x %.0f\" deep)" % (
                    sheet_profile, overall_width_in, overall_height_in, cabinet_depth_in),
                material_type="aluminum_6061" if is_aluminum else "plate",
                profile=sheet_profile,
                length_inches=overall_width_in,
                quantity=sheet_count,
                unit_price=round(total_sheet_sqft * sheet_price_sqft / max(sheet_count, 1), 2),
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += cabinet_weight

            frame_profile = "angle_1.5x1.5x0.125"
            frame_price_ft = lookup.get_price_per_foot(frame_profile)
            frame_in = self.perimeter_inches(overall_width_in, overall_height_in) * 2
            frame_ft = self.inches_to_feet(frame_in)
            frame_weight = self.get_weight_lbs(frame_profile, frame_ft)

            items.append(self.make_material_item(
                description="Internal frame — 1-1/2\" angle (front + back perimeter)",
                material_type="angle_iron",
                profile=frame_profile,
                length_inches=frame_in,
                quantity=self.linear_feet_to_pieces(frame_ft),
                unit_price=round(frame_ft * frame_price_ft / max(
                    self.linear_feet_to_pieces(frame_ft), 1), 2),
                cut_type="miter_45",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += frame_weight

            total_weld_inches = frame_in * 0.2
            total_sq_ft = total_sheet_sqft + front_sqft

            assumptions.append(
                "Cabinet sign: %.0f\" x %.0f\" x %.0f\" deep. "
                "Front face panel (acrylic/polycarbonate) and LED modules NOT included." % (
                    overall_width_in, overall_height_in, cabinet_depth_in))

        else:
            frame_profile = "sq_tube_1.5x1.5_11ga"
            frame_price_ft = lookup.get_price_per_foot(frame_profile)
            frame_in = self.perimeter_inches(overall_width_in, overall_height_in) + overall_height_in
            frame_ft = self.inches_to_feet(frame_in)
            frame_weight = self.get_weight_lbs(frame_profile, frame_ft)

            items.append(self.make_material_item(
                description="Sign frame — %s (%.0f\" x %.0f\")" % (
                    frame_profile, overall_width_in, overall_height_in),
                material_type="square_tubing",
                profile=frame_profile,
                length_inches=frame_in,
                quantity=self.linear_feet_to_pieces(frame_ft),
                unit_price=round(frame_ft * frame_price_ft / max(
                    self.linear_feet_to_pieces(frame_ft), 1), 2),
                cut_type="miter_45",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += frame_weight
            total_weld_inches = 4 * 3.0
            total_sq_ft = self.sq_ft_from_dimensions(overall_width_in, overall_height_in)
            assumptions.append("Custom LED sign frame — %.0f\" x %.0f\"." % (
                overall_width_in, overall_height_in))

        # Raceway (if building-mounted)
        if "raceway" in str(fields.get("mounting_location", "")).lower() or \
           "facade" in str(fields.get("mounting_location", "")).lower():
            raceway_profile = "sq_tube_2x2_11ga"
            raceway_price_ft = lookup.get_price_per_foot(raceway_profile)
            raceway_length_in = overall_width_in + 12
            raceway_ft = self.inches_to_feet(raceway_length_in)
            raceway_weight = self.get_weight_lbs(raceway_profile, raceway_ft)

            items.append(self.make_material_item(
                description="Mounting raceway — %s (%.1f ft)" % (raceway_profile, raceway_ft),
                material_type="square_tubing",
                profile=raceway_profile,
                length_inches=raceway_length_in,
                quantity=1,
                unit_price=round(raceway_ft * raceway_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += raceway_weight

        assumptions.append("LED modules, power supplies, and wiring NOT included in material estimate.")

        return self.make_material_list(
            job_type="led_sign_custom",
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
        return (96.0, 24.0)

    def _parse_letter_height(self, s):
        nums = re.findall(r'(\d+\.?\d*)', str(s))
        if nums:
            return max(float(nums[0]), 4.0)
        return 18.0
