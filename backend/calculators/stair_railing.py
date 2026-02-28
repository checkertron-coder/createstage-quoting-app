"""
Stair railing material calculator.

Extends straight railing with stair geometry:
- Rake angle increases railing length vs. horizontal run
- Post heights vary along the rake
- Landing extensions are calculated as straight railing sections
"""

import math

from .base import BaseCalculator
from .straight_railing import StraightRailingCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()

# Standard stair angles in degrees
STAIR_ANGLES = {
    "Standard residential (about 35-37 degrees)": 36.0,
    "Steep (38-42 degrees)": 40.0,
    "Shallow (under 35 degrees)": 30.0,
}


class StairRailingCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # --- Parse inputs ---
        linear_footage = self.parse_feet(fields.get("linear_footage"), default=12.0)

        railing_height_str = fields.get("railing_height", "34\"")
        height_in = self._parse_height(railing_height_str)

        stair_angle_str = fields.get("stair_angle", "Standard residential (about 35-37 degrees)")
        stair_rise = self.parse_inches(fields.get("stair_rise"))
        stair_run = self.parse_inches(fields.get("stair_run"))
        num_risers = self.parse_int(fields.get("num_risers"), default=14)

        # Calculate angle from rise/run if provided
        if stair_rise > 0 and stair_run > 0:
            angle_deg = math.degrees(math.atan(stair_rise / stair_run))
            assumptions.append(f"Stair angle calculated from rise/run: {stair_rise}\" / {stair_run}\" = {angle_deg:.1f}°")
        elif "provide" in stair_angle_str.lower():
            angle_deg = 36.0  # Default if they said they'd provide but didn't
            assumptions.append("Stair angle defaulted to 36° — rise/run not provided.")
        else:
            angle_deg = STAIR_ANGLES.get(stair_angle_str, 36.0)

        angle_rad = math.radians(angle_deg)

        # Landing extensions
        landing_ext = fields.get("landing_extension", "No")
        top_landing_ft = self.parse_feet(fields.get("landing_length_top"), default=0.0)
        bottom_landing_ft = self.parse_feet(fields.get("landing_length_bottom"), default=0.0)
        if "top" in str(landing_ext).lower() or "both" in str(landing_ext).lower():
            if top_landing_ft == 0:
                top_landing_ft = 1.0  # ADA minimum 12"
        if "bottom" in str(landing_ext).lower() or "both" in str(landing_ext).lower():
            if bottom_landing_ft == 0:
                bottom_landing_ft = 1.0

        # Wall handrail
        wall_handrail = fields.get("wall_handrail", "No")
        needs_wall_rail = "Yes" in str(wall_handrail) or "both" in str(wall_handrail).lower()

        # --- Stair railing geometry ---
        # The railing along the stair slope is longer than the horizontal run
        # linear_footage from the question tree is measured along the slope
        stair_railing_ft = linear_footage
        rake_adjusted_ft = stair_railing_ft  # Already slope distance

        # If linear footage seems like horizontal distance, adjust:
        # We trust the user input as slope measurement per question tree hint

        total_railing_ft = stair_railing_ft + top_landing_ft + bottom_landing_ft

        assumptions.append(f"Stair angle: {angle_deg:.1f}°, {num_risers} risers.")
        if top_landing_ft > 0 or bottom_landing_ft > 0:
            assumptions.append(f"Landing extensions: top {top_landing_ft:.1f} ft, bottom {bottom_landing_ft:.1f} ft.")

        # --- Use StraightRailingCalculator for the material math ---
        # Build modified fields for the straight railing calculator
        straight_fields = dict(fields)
        straight_fields["linear_footage"] = str(total_railing_ft)
        # Keep same height, profiles, spacing, finish

        straight_calc = StraightRailingCalculator()
        straight_result = straight_calc.calculate(straight_fields)

        # Start with straight railing results
        items = straight_result["items"]
        hardware = straight_result["hardware"]
        total_weight = straight_result["total_weight_lbs"]
        total_sq_ft = straight_result["total_sq_ft"]
        total_weld_inches = straight_result["weld_linear_inches"]

        # --- Add stair-specific adjustments ---

        # Rake angle adds labor complexity (noted in assumptions, affects Stage 4)
        assumptions.append(f"Stair rake angle adds fabrication complexity vs. flat railing — all rail/baluster cuts are angled.")

        # Baluster cuts: if plumb (vertical), all same length; if raked, each is different
        baluster_orientation = fields.get("baluster_orientation", "Plumb (vertical — most common)")
        if "Raked" in baluster_orientation or "raked" in baluster_orientation:
            assumptions.append("Raked balusters: each cut to different length along stair angle — adds labor.")

        # Wall handrail (opposite side)
        if needs_wall_rail:
            wall_rail_profile = "round_tube_1.5_14ga"
            wall_rail_price = lookup.get_price_per_foot(wall_rail_profile)
            wall_rail_ft = total_railing_ft
            wall_rail_weight = self.get_weight_lbs(wall_rail_profile, wall_rail_ft)

            items.append(self.make_material_item(
                description=f"Wall-mount handrail — 1-1/2\" round tube ({wall_rail_ft:.1f} ft)",
                material_type="dom_tubing",
                profile=wall_rail_profile,
                length_inches=self.feet_to_inches(wall_rail_ft),
                quantity=self.linear_feet_to_pieces(wall_rail_ft),
                unit_price=round(wall_rail_ft * wall_rail_price / max(self.linear_feet_to_pieces(wall_rail_ft), 1), 2),
                cut_type="miter_45",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += wall_rail_weight

            # Wall brackets: one every 4 ft
            bracket_count = math.ceil(wall_rail_ft / 4.0) + 1
            hardware.append(self.make_hardware_item(
                description=f"Wall handrail bracket × {bracket_count}",
                quantity=bracket_count,
                options=lookup.get_hardware_options("surface_mount_flange"),
            ))

        # Merge assumptions
        combined_assumptions = assumptions + [
            a for a in straight_result.get("assumptions", [])
            if a not in assumptions
        ]

        return self.make_material_list(
            job_type="stair_railing",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=combined_assumptions,
        )

    def _parse_height(self, height_str: str) -> float:
        """Parse railing height from answer string to inches."""
        h = str(height_str)
        if "34" in h:
            return 34.0
        if "36" in h:
            return 36.0
        if "42" in h:
            return 42.0
        if "48" in h:
            return 48.0
        return 34.0
