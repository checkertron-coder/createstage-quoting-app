"""
Furniture table calculator.

Legs (tube) + individual frame rails + stretchers + top support.
Parametric by table dimensions. Supports AI cut list for custom designs.

Dimension parser handles formats like "20 x 20 x 32" (L x W x H in inches).
"""

import re

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class FurnitureTableCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # Try AI cut list when description exists
        print(f"FURNITURE_TABLE DEBUG: _has_description = {self._has_description(fields)}")
        print(f"FURNITURE_TABLE DEBUG: description field = {str(fields.get('description', 'MISSING'))[:100]}")
        if self._has_description(fields):
            ai_result = self._try_ai_cut_list("furniture_table", fields)
            if ai_result is not None:
                return self._build_from_ai_cuts("furniture_table", ai_result, fields, assumptions)

        return self._template_calculate(fields, assumptions)

    def _template_calculate(self, fields: dict, assumptions: list) -> dict:
        """Template-based calculation when AI is unavailable."""
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0

        # Parse dimensions — handles "20 x 20 x 32" format
        dims = self._parse_table_dimensions(fields)
        table_length_in = dims["length"]
        table_width_in = dims["width"]
        table_height_in = dims["height"]

        quantity = self.parse_int(fields.get("quantity"), default=1)
        if quantity < 1:
            quantity = 1

        leg_style = fields.get("leg_style", "Straight legs")
        leg_profile = "sq_tube_2x2_11ga"
        frame_profile = "sq_tube_1.5x1.5_11ga"

        if "round" in str(leg_style).lower() or "hairpin" in str(leg_style).lower():
            leg_profile = "round_tube_1.5_14ga"

        leg_price_ft = lookup.get_price_per_foot(leg_profile)
        frame_price_ft = lookup.get_price_per_foot(frame_profile)

        # 1. Legs — 4 per table
        leg_count = 4 * quantity
        leg_length_in = table_height_in
        leg_total_ft = self.inches_to_feet(leg_length_in) * leg_count
        leg_weight = self.get_weight_lbs(leg_profile, leg_total_ft)

        items.append(self.make_material_item(
            description="Table legs — %s × %d (%.0f\" each)" % (
                leg_profile, leg_count, leg_length_in),
            material_type="square_tubing",
            profile=leg_profile,
            length_inches=leg_length_in,
            quantity=self.apply_waste(leg_count, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(leg_length_in) * leg_price_ft, 2),
            cut_type="miter_45",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += leg_weight

        # 2. Top frame — individual rails (2 long + 2 short per table)
        long_rail_count = 2 * quantity
        short_rail_count = 2 * quantity
        long_rail_in = table_length_in
        short_rail_in = table_width_in

        # Long rails
        long_rail_total_ft = self.inches_to_feet(long_rail_in) * long_rail_count
        long_rail_weight = self.get_weight_lbs(frame_profile, long_rail_total_ft)

        items.append(self.make_material_item(
            description="Top frame long rails — %s × %d (%.0f\" each)" % (
                frame_profile, long_rail_count, long_rail_in),
            material_type="square_tubing",
            profile=frame_profile,
            length_inches=long_rail_in,
            quantity=self.apply_waste(long_rail_count, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(long_rail_in) * frame_price_ft, 2),
            cut_type="miter_45",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += long_rail_weight

        # Short rails
        short_rail_total_ft = self.inches_to_feet(short_rail_in) * short_rail_count
        short_rail_weight = self.get_weight_lbs(frame_profile, short_rail_total_ft)

        items.append(self.make_material_item(
            description="Top frame short rails — %s × %d (%.0f\" each)" % (
                frame_profile, short_rail_count, short_rail_in),
            material_type="square_tubing",
            profile=frame_profile,
            length_inches=short_rail_in,
            quantity=self.apply_waste(short_rail_count, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(short_rail_in) * frame_price_ft, 2),
            cut_type="miter_45",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += short_rail_weight

        # 3. Center stretcher (1 per table, long direction)
        stretcher_count = 1 * quantity
        center_stretcher_in = table_length_in - 4  # Inset from frame
        center_ft = self.inches_to_feet(center_stretcher_in) * stretcher_count
        center_weight = self.get_weight_lbs(frame_profile, center_ft)

        items.append(self.make_material_item(
            description="Center stretcher — %s × %d (%.0f\" each)" % (
                frame_profile, stretcher_count, center_stretcher_in),
            material_type="square_tubing",
            profile=frame_profile,
            length_inches=center_stretcher_in,
            quantity=self.apply_waste(stretcher_count, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(center_stretcher_in) * frame_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += center_weight

        # 4. Bottom stretchers (H-frame between legs, 2 per table)
        bottom_count = 2 * quantity
        bottom_length_in = table_length_in - 4  # Inset from legs
        bottom_total_ft = self.inches_to_feet(bottom_length_in) * bottom_count
        bottom_weight = self.get_weight_lbs(frame_profile, bottom_total_ft)

        items.append(self.make_material_item(
            description="Bottom stretchers — %s × %d (%.0f\" each)" % (
                frame_profile, bottom_count, bottom_length_in),
            material_type="square_tubing",
            profile=frame_profile,
            length_inches=bottom_length_in,
            quantity=self.apply_waste(bottom_count, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(bottom_length_in) * frame_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += bottom_weight

        # Leveling feet hardware
        hardware.append(self.make_hardware_item(
            description="Adjustable leveling feet",
            quantity=4 * quantity,
            options=[
                {"supplier": "McMaster-Carr", "price": 5.00, "url": "", "part_number": None, "lead_days": 3},
                {"supplier": "Amazon", "price": 3.50, "url": "", "part_number": None, "lead_days": 5},
                {"supplier": "Grainger", "price": 6.00, "url": "", "part_number": None, "lead_days": 2},
            ],
        ))

        # Weld totals
        total_weld_inches = leg_count * 8  # Leg-to-frame welds (4 sides x 2")
        total_weld_inches += bottom_count * 4  # Bottom stretcher welds
        total_weld_inches += stretcher_count * 4  # Center stretcher welds
        total_weld_inches += (long_rail_count + short_rail_count) * 6  # Frame corner welds

        # Surface area
        total_sq_ft = self.sq_ft_from_dimensions(table_length_in, table_width_in) * quantity

        assumptions.append(
            "Table: %.0f\" x %.0f\" x %.0f\" height x %d unit(s). "
            "Top material (wood, stone, glass) NOT included — steel frame only." % (
                table_length_in, table_width_in, table_height_in, quantity))

        return self.make_material_list(
            job_type="furniture_table",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _parse_table_dimensions(self, fields: dict) -> dict:
        """
        Parse table dimensions from fields. Handles multiple formats:
        - Individual fields: table_length, table_width, table_height / height
        - Combined format: approximate_size or dimensions = "20 x 20 x 32"
        - Defaults: 60" x 30" x 30"
        """
        # Try combined dimension string first (e.g., "20 x 20 x 32")
        for dim_key in ("approximate_size", "dimensions", "size"):
            dim_str = fields.get(dim_key, "")
            if dim_str:
                parsed = self._parse_dimension_string(str(dim_str))
                if parsed:
                    return parsed

        # Fall back to individual fields
        table_length_in = self.parse_inches(
            fields.get("table_length"),
            default=self.feet_to_inches(self.parse_feet(
                fields.get("table_length", fields.get("length")), default=5.0))
        )
        if table_length_in < 12:
            table_length_in = self.feet_to_inches(table_length_in)

        table_width_in = self.parse_inches(
            fields.get("table_width"),
            default=self.feet_to_inches(self.parse_feet(
                fields.get("table_width", fields.get("width")), default=2.5))
        )
        if table_width_in < 12:
            table_width_in = self.feet_to_inches(table_width_in)

        table_height_in = self.parse_inches(
            fields.get("table_height", fields.get("height")), default=30.0)
        if table_height_in < 12:
            table_height_in *= 12

        return {
            "length": table_length_in,
            "width": table_width_in,
            "height": table_height_in,
        }

    def _parse_dimension_string(self, dim_str: str):
        """
        Parse "L x W x H" dimension string.
        Handles formats like: "20 x 20 x 32", "20x20x32", "20 x 20 x 32"
        Returns dict or None if can't parse.
        """
        # Normalize separators
        s = dim_str.replace("\u00d7", "x").replace("X", "x").replace("by", "x")
        nums = re.findall(r'(\d+\.?\d*)', s)

        if len(nums) >= 3:
            vals = [float(n) for n in nums[:3]]
            # If values are small (< 12), probably feet — convert
            is_feet = "ft" in dim_str.lower() or "'" in dim_str
            if is_feet:
                vals = [v * 12 for v in vals]
            return {
                "length": max(vals[0], 6.0),
                "width": max(vals[1], 6.0),
                "height": max(vals[2], 6.0),
            }
        elif len(nums) == 2:
            vals = [float(n) for n in nums[:2]]
            is_feet = "ft" in dim_str.lower() or "'" in dim_str
            if is_feet:
                vals = [v * 12 for v in vals]
            return {
                "length": max(vals[0], 6.0),
                "width": max(vals[1], 6.0),
                "height": 30.0,
            }
        return None
