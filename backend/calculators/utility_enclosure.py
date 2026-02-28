"""
Utility enclosure / equipment box calculator.

Box = panels (4 sides + top + bottom or door). Sheet metal construction.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class UtilityEnclosureCalculator(BaseCalculator):

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
        width_in = self.parse_inches(
            fields.get("width"),
            default=self.feet_to_inches(self.parse_feet(fields.get("width"), default=2.0))
        )
        if width_in < 6:
            width_in = self.feet_to_inches(width_in)

        height_in = self.parse_inches(
            fields.get("height"),
            default=self.feet_to_inches(self.parse_feet(fields.get("height"), default=3.0))
        )
        if height_in < 6:
            height_in = self.feet_to_inches(height_in)

        depth_in = self.parse_inches(
            fields.get("depth"),
            default=self.feet_to_inches(self.parse_feet(fields.get("depth"), default=1.0))
        )
        if depth_in < 4:
            depth_in = self.feet_to_inches(depth_in)

        quantity = self.parse_int(fields.get("quantity"), default=1)
        if quantity < 1:
            quantity = 1

        gauge = fields.get("gauge", "14 gauge")
        sheet_profile = "sheet_14ga"
        sheet_thickness_in = 0.0747
        if "11" in str(gauge):
            sheet_profile = "sheet_11ga"
            sheet_thickness_in = 0.1196
        elif "16" in str(gauge):
            sheet_profile = "sheet_16ga"
            sheet_thickness_in = 0.0598

        sheet_price_sqft = lookup.get_price_per_sqft(sheet_profile)
        if sheet_price_sqft == 0.0:
            sheet_price_sqft = 2.03  # 14ga default

        has_door = "yes" in str(fields.get("has_door", "Yes")).lower() or \
                   "door" in str(fields.get("door_type", "")).lower()

        # Calculate panel areas
        # Front + back
        front_back_sqft = self.sq_ft_from_dimensions(width_in, height_in) * 2
        # Sides
        side_sqft = self.sq_ft_from_dimensions(depth_in, height_in) * 2
        # Top + bottom
        top_bottom_sqft = self.sq_ft_from_dimensions(width_in, depth_in) * 2

        total_panel_sqft = (front_back_sqft + side_sqft + top_bottom_sqft) * quantity

        # Sheet count (4'×8' = 32 sqft per sheet)
        sheet_count = self.apply_waste(math.ceil(total_panel_sqft / 32.0), self.WASTE_SHEET)

        # Weight
        panel_weight = 0.0
        for w, h, count, label in [
            (width_in, height_in, 2, "front/back"),
            (depth_in, height_in, 2, "sides"),
            (width_in, depth_in, 2, "top/bottom"),
        ]:
            pw = self.get_plate_weight_lbs(w, h, sheet_thickness_in) * count * quantity
            panel_weight += pw

        items.append(self.make_material_item(
            description="Enclosure panels — %s (%.0f sq ft total — %d units)" % (
                sheet_profile, total_panel_sqft, quantity),
            material_type="plate",
            profile=sheet_profile,
            length_inches=max(width_in, height_in),
            quantity=sheet_count,
            unit_price=round(total_panel_sqft * sheet_price_sqft / max(sheet_count, 1), 2),
            cut_type="square",
            waste_factor=self.WASTE_SHEET,
        ))
        total_weight += panel_weight

        # Frame (angle iron internal frame for rigidity)
        frame_profile = "angle_1.5x1.5x0.125"
        frame_price_ft = lookup.get_price_per_foot(frame_profile)

        # 12 edges of the box
        edge_total_in = (4 * width_in + 4 * height_in + 4 * depth_in) * quantity
        edge_total_ft = self.inches_to_feet(edge_total_in)
        edge_weight = self.get_weight_lbs(frame_profile, edge_total_ft)

        items.append(self.make_material_item(
            description="Internal frame — 1-1/2\" angle × %d (12 edges per box × %d)" % (
                12 * quantity, quantity),
            material_type="angle_iron",
            profile=frame_profile,
            length_inches=edge_total_in / max(12 * quantity, 1),
            quantity=self.apply_waste(12 * quantity, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(edge_total_in / max(12 * quantity, 1)) * frame_price_ft, 2),
            cut_type="miter_45",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += edge_weight

        # Door hardware
        if has_door:
            hardware.append(self.make_hardware_item(
                description="Enclosure hinges (pair per unit)",
                quantity=quantity,
                options=lookup.get_hardware_options("standard_weld_hinge_pair"),
            ))
            hardware.append(self.make_hardware_item(
                description="Enclosure latch / handle",
                quantity=quantity,
                options=lookup.get_hardware_options("gravity_latch"),
            ))
            assumptions.append("Hinged door on front panel. Padlock hasp if security needed.")

        # Weld totals
        total_weld_inches = edge_total_in * 0.25  # ~25% of edges welded
        total_weld_inches += quantity * self.perimeter_inches(width_in, height_in)  # Panel seams

        # Surface area
        total_sq_ft = total_panel_sqft

        assumptions.append(
            "Enclosure: %.0f\" × %.0f\" × %.0f\" (%s), %d unit(s)." % (
                width_in, height_in, depth_in, sheet_profile, quantity))

        return self.make_material_list(
            job_type="utility_enclosure",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )
