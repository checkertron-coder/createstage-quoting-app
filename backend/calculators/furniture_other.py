"""
Custom furniture / fixtures calculator.

Generic furniture items — routes by item_type (shelf, bracket, rack, etc.).
"""

import re

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class FurnitureOtherCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # Try AI cut list for custom designs
        ai_cuts = self._try_ai_cut_list(fields)
        if ai_cuts is not None:
            return self._build_from_ai_cuts(ai_cuts, fields, assumptions)

        # Parse inputs
        item_type = fields.get("item_type", "Shelving / storage rack")
        material_str = fields.get("material", "Mild steel (most common / cheapest)")
        size_str = fields.get("approximate_size", "48\" × 18\" × 72\"")
        quantity = self.parse_int(fields.get("quantity"), default=1)
        if quantity < 1:
            quantity = 1

        length_in, width_in, height_in = self._parse_size(size_str)

        # Material profile selection
        if "stainless" in str(material_str).lower():
            frame_profile = "sq_tube_1.5x1.5_11ga"
            mat_type = "stainless_304"
        elif "aluminum" in str(material_str).lower():
            frame_profile = "sq_tube_1.5x1.5_14ga"
            mat_type = "aluminum_6061"
        else:
            frame_profile = "sq_tube_1.5x1.5_11ga"
            mat_type = "mild_steel"

        frame_price_ft = lookup.get_price_per_foot(frame_profile)

        # Route by item type
        item_lower = str(item_type).lower()

        if "shelf" in item_lower or "rack" in item_lower:
            # Shelving: uprights + shelf frames + cross braces
            upright_count = 4 * quantity
            shelf_count = max(int(height_in / 18), 2) * quantity  # Shelf every ~18"
            cross_brace_count = 2 * quantity

            # Uprights
            upright_total_ft = self.inches_to_feet(height_in) * upright_count
            upright_weight = self.get_weight_lbs(frame_profile, upright_total_ft)

            items.append(self.make_material_item(
                description="Uprights — %s × %d (%.0f\" each)" % (
                    frame_profile, upright_count, height_in),
                material_type=mat_type,
                profile=frame_profile,
                length_inches=height_in,
                quantity=self.apply_waste(upright_count, self.WASTE_TUBE),
                unit_price=round(self.inches_to_feet(height_in) * frame_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += upright_weight

            # Shelf frames (perimeter per shelf)
            shelf_perim_in = self.perimeter_inches(length_in, width_in)
            shelf_total_ft = self.inches_to_feet(shelf_perim_in) * shelf_count
            shelf_weight = self.get_weight_lbs(frame_profile, shelf_total_ft)

            items.append(self.make_material_item(
                description="Shelf frames — %s × %d shelves" % (frame_profile, shelf_count),
                material_type=mat_type,
                profile=frame_profile,
                length_inches=shelf_perim_in,
                quantity=self.apply_waste(shelf_count, self.WASTE_TUBE),
                unit_price=round(self.inches_to_feet(shelf_perim_in) * frame_price_ft, 2),
                cut_type="miter_45",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += shelf_weight

            total_weld_inches = (upright_count * shelf_count * 2 +
                                 shelf_count * 4) * 2.0
            assumptions.append(
                "Shelving: %d uprights, %d shelves at ~18\" spacing." % (
                    upright_count, shelf_count))

        elif "bracket" in item_lower or "mount" in item_lower:
            # Brackets: flat bar or angle
            bracket_profile = "flat_bar_1.5x0.25"
            bracket_price_ft = lookup.get_price_per_foot(bracket_profile)
            bracket_length_in = max(length_in, 8.0)
            bracket_total_ft = self.inches_to_feet(bracket_length_in) * quantity * 2
            bracket_weight = self.get_weight_lbs(bracket_profile, bracket_total_ft)

            items.append(self.make_material_item(
                description="Brackets — %s × %d (%.0f\" each, 2 per unit)" % (
                    bracket_profile, quantity * 2, bracket_length_in),
                material_type="flat_bar",
                profile=bracket_profile,
                length_inches=bracket_length_in,
                quantity=self.apply_waste(quantity * 2, self.WASTE_FLAT),
                unit_price=round(self.inches_to_feet(bracket_length_in) * bracket_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_FLAT,
            ))
            total_weight += bracket_weight
            total_weld_inches = quantity * 2 * 6
            assumptions.append("Brackets: 2 per unit, %.0f\" each." % bracket_length_in)

        else:
            # Generic furniture frame
            frame_perim_in = self.perimeter_inches(length_in, width_in) + 4 * height_in
            internal_in = (length_in + width_in) * 0.5
            total_frame_in = (frame_perim_in + internal_in) * quantity
            total_frame_ft = self.inches_to_feet(total_frame_in)
            frame_weight = self.get_weight_lbs(frame_profile, total_frame_ft)

            items.append(self.make_material_item(
                description="Frame material — %s (%.1f ft per unit × %d)" % (
                    frame_profile, self.inches_to_feet(frame_perim_in + internal_in), quantity),
                material_type=mat_type,
                profile=frame_profile,
                length_inches=total_frame_in / max(quantity, 1),
                quantity=self.apply_waste(
                    self.linear_feet_to_pieces(total_frame_ft), self.WASTE_TUBE),
                unit_price=round(total_frame_ft * frame_price_ft / max(
                    self.linear_feet_to_pieces(total_frame_ft), 1), 2),
                cut_type="miter_45",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += frame_weight
            total_weld_inches = quantity * 12 * 3.0
            assumptions.append("Generic furniture frame estimated from overall dimensions.")

        # Surface area
        total_sq_ft = self.sq_ft_from_dimensions(length_in, width_in) * quantity

        assumptions.append(
            "%s: %.0f\" × %.0f\" × %.0f\", %d unit(s)." % (
                item_type.split("/")[0].strip() if "/" in item_type else item_type.split("(")[0].strip(),
                length_in, width_in, height_in, quantity))

        return self.make_material_list(
            job_type="furniture_other",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _try_ai_cut_list(self, fields):
        """Try AI cut list when any description text exists."""
        description = fields.get("description", "")
        notes = fields.get("notes", "")
        combined = (str(description) + " " + str(notes)).strip()
        if not combined:
            return None
        try:
            from .ai_cut_list import AICutListGenerator
            generator = AICutListGenerator()
            return generator.generate_cut_list("furniture_other", fields)
        except Exception:
            return None

    def _build_from_ai_cuts(self, ai_cuts, fields, assumptions):
        """Build MaterialList from AI-generated cut list."""
        items = []
        total_weight = 0.0
        total_weld_inches = 0.0

        for cut in ai_cuts:
            profile = cut.get("profile", "sq_tube_1.5x1.5_11ga")
            length_in = cut.get("length_inches", 12.0)
            quantity = cut.get("quantity", 1)
            price_ft = lookup.get_price_per_foot(profile)
            if price_ft == 0.0:
                price_ft = 2.75
            length_ft = self.inches_to_feet(length_in)
            weight = self.get_weight_lbs(profile, length_ft * quantity)
            if weight == 0.0:
                weight = length_ft * quantity * 2.0

            items.append(self.make_material_item(
                description=cut.get("description", "Cut piece"),
                material_type=cut.get("material_type", "mild_steel"),
                profile=profile,
                length_inches=length_in,
                quantity=self.apply_waste(quantity, self.WASTE_TUBE),
                unit_price=round(length_ft * price_ft, 2),
                cut_type=cut.get("cut_type", "square"),
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += weight
            total_weld_inches += quantity * 6

        size_str = fields.get("approximate_size", "")
        length_in, width_in, _ = self._parse_size(size_str)
        total_sq_ft = self.sq_ft_from_dimensions(length_in, width_in)
        assumptions.append("Cut list generated by AI from custom design description.")

        return self.make_material_list(
            job_type="furniture_other",
            items=items,
            hardware=[],
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _parse_size(self, size_str):
        if not size_str:
            return (48.0, 18.0, 36.0)
        s = str(size_str).lower()
        numbers = re.findall(r'(\d+\.?\d*)', s)
        is_feet = "ft" in s or "feet" in s or "'" in s

        if len(numbers) >= 3:
            vals = [float(n) for n in numbers[:3]]
            if is_feet:
                vals = [v * 12 for v in vals]
            return (max(vals[0], 1.0), max(vals[1], 1.0), max(vals[2], 1.0))
        elif len(numbers) >= 2:
            vals = [float(n) for n in numbers[:2]]
            if is_feet:
                vals = [v * 12 for v in vals]
            return (max(vals[0], 1.0), max(vals[1], 1.0), 36.0)
        elif len(numbers) == 1:
            val = float(numbers[0])
            if is_feet:
                val *= 12
            return (max(val, 1.0), max(val * 0.5, 1.0), 36.0)
        return (48.0, 18.0, 36.0)
