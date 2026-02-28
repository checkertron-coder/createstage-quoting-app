"""
Furniture table calculator.

Legs (tube) + stretchers + top support frame.
Parametric by table dimensions.
"""

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class FurnitureTableCalculator(BaseCalculator):

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
            table_height_in *= 12  # Probably in feet

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

        # 1. Legs (4 per table)
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

        # 2. Top support frame (perimeter + 1 center stretcher)
        frame_perim_in = self.perimeter_inches(table_length_in, table_width_in)
        center_stretcher_in = table_length_in  # Long direction
        total_frame_in = (frame_perim_in + center_stretcher_in) * quantity
        total_frame_ft = self.inches_to_feet(total_frame_in)
        frame_weight = self.get_weight_lbs(frame_profile, total_frame_ft)

        items.append(self.make_material_item(
            description="Top support frame — %s (perimeter + center stretcher × %d)" % (
                frame_profile, quantity),
            material_type="square_tubing",
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

        # 3. Bottom stretchers (H-frame between legs)
        stretcher_count = 2 * quantity  # 2 per table (long direction)
        stretcher_length_in = table_length_in - 4  # Inset from legs
        stretcher_total_ft = self.inches_to_feet(stretcher_length_in) * stretcher_count
        stretcher_weight = self.get_weight_lbs(frame_profile, stretcher_total_ft)

        items.append(self.make_material_item(
            description="Bottom stretchers — %s × %d (%.0f\" each)" % (
                frame_profile, stretcher_count, stretcher_length_in),
            material_type="square_tubing",
            profile=frame_profile,
            length_inches=stretcher_length_in,
            quantity=self.apply_waste(stretcher_count, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(stretcher_length_in) * frame_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += stretcher_weight

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
        total_weld_inches = leg_count * 8  # Leg-to-frame welds (4 sides × 2")
        total_weld_inches += stretcher_count * 4  # Stretcher welds
        total_weld_inches += quantity * frame_perim_in * 0.1  # Frame corner welds

        # Surface area
        total_sq_ft = self.sq_ft_from_dimensions(table_length_in, table_width_in) * quantity

        assumptions.append(
            "Table: %.0f\" × %.0f\" × %.0f\" height × %d unit(s). "
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
