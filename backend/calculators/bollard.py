"""
Bollard calculator.

Pipe length = height + embed_depth. Cap plate. Base plate if surface-mount.
Multiply by count.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class BollardCalculator(BaseCalculator):

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
        bollard_count = self.parse_int(fields.get("bollard_count",
                                                   fields.get("quantity")), default=1)
        if bollard_count < 1:
            bollard_count = 1

        height_in = self._parse_height(fields.get("bollard_height", "36\" (standard)"))
        pipe_profile = self._parse_pipe(fields.get("pipe_size", "6\" schedule 40 (standard — most common)"))

        fixed_or_removable = fields.get("fixed_or_removable", "Fixed — set in concrete (permanent)")
        is_surface_mount = "surface" in str(fixed_or_removable).lower()
        is_removable = "removable" in str(fixed_or_removable).lower()

        cap_style = fields.get("cap_style", "Flat plate cap (welded on)")
        concrete_fill = "yes" in str(fields.get("concrete_fill", "No")).lower()

        # Embed depth
        if is_surface_mount:
            embed_in = 0.0
        elif is_removable:
            embed_in = height_in * 0.5  # Sleeve depth
        else:
            embed_in = max(height_in * 0.5, 24.0)  # At least 24" or 50% of height

        # 1. Pipe
        pipe_price_ft = lookup.get_price_per_foot(pipe_profile)
        pipe_length_in = height_in + embed_in
        pipe_length_ft = self.inches_to_feet(pipe_length_in)
        pipe_total_ft = pipe_length_ft * bollard_count
        pipe_weight = self.get_weight_lbs(pipe_profile, pipe_total_ft)

        items.append(self.make_material_item(
            description="Bollard pipe — %s × %d (%.1f ft each, %.0f\" above grade + %.0f\" embed)" % (
                pipe_profile, bollard_count, pipe_length_ft, height_in, embed_in),
            material_type="mild_steel",
            profile=pipe_profile,
            length_inches=pipe_length_in,
            quantity=self.apply_waste(bollard_count, self.WASTE_TUBE),
            unit_price=round(pipe_length_ft * pipe_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += pipe_weight

        # 2. Cap plates
        if "open" not in str(cap_style).lower():
            pipe_diameter_in = self._pipe_diameter(pipe_profile)
            cap_size_in = pipe_diameter_in + 1  # 1/2" overhang all around
            cap_thickness_in = 0.25
            cap_weight_each = self.get_plate_weight_lbs(cap_size_in, cap_size_in, cap_thickness_in)

            items.append(self.make_material_item(
                description="Cap plates — 1/4\" plate × %d (%.0f\" × %.0f\")" % (
                    bollard_count, cap_size_in, cap_size_in),
                material_type="plate",
                profile="plate_0.25",
                length_inches=cap_size_in,
                quantity=bollard_count,
                unit_price=round(cap_weight_each * 0.50, 2),  # ~$0.50/lb for plate
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += cap_weight_each * bollard_count
            total_weld_inches += math.pi * pipe_diameter_in * bollard_count  # Weld cap circumference

        # 3. Base plates (if surface mount)
        if is_surface_mount:
            base_size_str = fields.get("base_plate_size", "10\" x 10\" (standard for 6\" pipe)")
            base_size_in = self._parse_base_plate_size(base_size_str)
            base_thickness_in = 0.5
            base_weight_each = self.get_plate_weight_lbs(base_size_in, base_size_in, base_thickness_in)

            items.append(self.make_material_item(
                description="Base plates — 1/2\" plate × %d (%.0f\" × %.0f\")" % (
                    bollard_count, base_size_in, base_size_in),
                material_type="plate",
                profile="plate_0.5",
                length_inches=base_size_in,
                quantity=bollard_count,
                unit_price=round(base_weight_each * 0.50, 2),
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += base_weight_each * bollard_count
            total_weld_inches += math.pi * self._pipe_diameter(pipe_profile) * bollard_count
            assumptions.append("Surface mount — 4 anchor bolts per base plate (not included).")

        # 4. Removable sleeve
        if is_removable:
            sleeve_diameter = self._pipe_diameter(pipe_profile) + 0.5  # Clearance
            sleeve_profile = self._next_pipe_size(pipe_profile)
            sleeve_price_ft = lookup.get_price_per_foot(sleeve_profile)
            sleeve_length_in = embed_in + 2  # Flush or slightly above grade
            sleeve_length_ft = self.inches_to_feet(sleeve_length_in)
            sleeve_weight = self.get_weight_lbs(sleeve_profile, sleeve_length_ft * bollard_count)

            items.append(self.make_material_item(
                description="Receiver sleeves — %s × %d (%.1f ft each)" % (
                    sleeve_profile, bollard_count, sleeve_length_ft),
                material_type="mild_steel",
                profile=sleeve_profile,
                length_inches=sleeve_length_in,
                quantity=self.apply_waste(bollard_count, self.WASTE_TUBE),
                unit_price=round(sleeve_length_ft * sleeve_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += sleeve_weight
            assumptions.append("Removable bollards include receiver sleeves set in concrete.")

        # Surface area (cylindrical)
        pipe_diameter_in = self._pipe_diameter(pipe_profile)
        circumference_ft = self.inches_to_feet(math.pi * pipe_diameter_in)
        total_sq_ft = circumference_ft * self.inches_to_feet(height_in) * bollard_count

        assumptions.append(
            "%d bollards, %s, %.0f\" height above grade." % (bollard_count, pipe_profile, height_in))
        if concrete_fill:
            assumptions.append("Concrete-filled for impact resistance.")

        return self.make_material_list(
            job_type="bollard",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _parse_height(self, height_str):
        s = str(height_str)
        if "30" in s:
            return 30.0
        if "42" in s:
            return 42.0
        if "48" in s:
            return 48.0
        return 36.0

    def _parse_pipe(self, pipe_str):
        s = str(pipe_str)
        if "4\"" in s or "4 " in s:
            return "pipe_4_sch40"
        if "8\"" in s or "8 " in s:
            return "pipe_6_sch40"  # Use 6" as proxy
        return "pipe_6_sch40"

    def _pipe_diameter(self, profile):
        if "4" in profile:
            return 4.5  # OD of 4" Sch 40
        if "6" in profile:
            return 6.625
        if "3.5" in profile:
            return 4.0
        if "3" in profile:
            return 3.5
        return 6.625

    def _next_pipe_size(self, profile):
        """Return the next larger pipe for use as a sleeve."""
        if "pipe_4" in profile:
            return "pipe_6_sch40"
        return "pipe_6_sch40"

    def _parse_base_plate_size(self, size_str):
        s = str(size_str)
        if "8\"" in s or "8 " in s:
            return 8.0
        if "12" in s:
            return 12.0
        return 10.0
