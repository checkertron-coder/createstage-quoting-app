"""
Straight railing material calculator.

Input: linear footage, height, baluster style/spacing, post type/spacing, finish.
Output: MaterialList with posts, top rail, bottom rail, balusters, hardware.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()

# Top rail profile mapping
TOP_RAIL_PROFILES = {
    "1-1/2\" round tube (ADA graspable)": ("round_tube_1.5_14ga", "dom_tubing"),
    "1-1/4\" round tube (ADA graspable)": ("round_tube_1.25_14ga", "dom_tubing"),
    "Square tube 1-1/2\"": ("sq_tube_1.5x1.5_14ga", "square_tubing"),
    "Square tube 2\"": ("sq_tube_2x2_14ga", "square_tubing"),
    "Flat bar cap (1-1/2\" x 1/4\")": ("flat_bar_1.5x0.25", "flat_bar"),
    "Flat bar cap (2\" x 1/4\")": ("flat_bar_2x0.25", "flat_bar"),
}

# Baluster/infill profile mapping
BALUSTER_PROFILES = {
    "Vertical square bar (traditional)": ("sq_bar_0.75", "square_tubing"),
    "Vertical square bar": ("sq_bar_0.75", "square_tubing"),
    "Vertical round bar": ("round_bar_0.625", "flat_bar"),
    "Horizontal bars": ("sq_bar_0.75", "square_tubing"),
    "Flat bar (contemporary)": ("flat_bar_1x0.25", "flat_bar"),
    "Flat bar": ("flat_bar_1x0.25", "flat_bar"),
}

# Post profiles — railing posts are smaller than gate posts
POST_PROFILES = {
    "sq_tube_1.5x1.5_11ga": "sq_tube_1.5x1.5_11ga",
    "sq_tube_2x2_11ga": "sq_tube_2x2_11ga",
}


class StraightRailingCalculator(BaseCalculator):

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
        linear_footage = self.parse_feet(fields.get("linear_footage"), default=20.0)
        linear_inches = self.feet_to_inches(linear_footage)

        railing_height_str = fields.get("railing_height", "42\"")
        height_in = self._parse_height(railing_height_str, fields.get("custom_height"))

        top_rail_str = fields.get("top_rail_profile", "1-1/2\" round tube (ADA graspable)")
        infill_style = fields.get("infill_style", "Vertical square bar (traditional)")

        baluster_spacing_in = self._parse_spacing(
            fields.get("baluster_spacing",
                       fields.get("horizontal_bar_spacing", "4\" max clear (code compliant — standard)")))

        post_spacing_ft = self._parse_post_spacing(fields.get("post_spacing", "6 ft on-center (standard)"))
        post_mount = fields.get("post_mount_type", "Surface mount flange")

        num_transitions = self.parse_int(fields.get("transitions"), default=0)

        finish = fields.get("finish", "Powder coat")

        # --- 1. Posts ---
        post_profile = "sq_tube_1.5x1.5_11ga"
        post_price_ft = lookup.get_price_per_foot(post_profile)

        # Post count: one per spacing interval + 1, plus extra for transitions
        post_count = math.floor(linear_footage / post_spacing_ft) + 1 + num_transitions

        # Post length depends on mount type
        if "Surface" in post_mount or "surface" in post_mount:
            post_length_in = height_in  # Flange mounts on top
            needs_flanges = True
        elif "Core" in post_mount or "core" in post_mount:
            post_length_in = height_in + 5  # 5" embed for core drill
            needs_flanges = False
        elif "Side" in post_mount or "side" in post_mount:
            post_length_in = height_in  # Side-mount bracket, no extra length
            needs_flanges = True  # Side-mount uses flanges too
        elif "Embedded" in post_mount:
            post_length_in = height_in + 6  # 6" embed in concrete
            needs_flanges = False
        else:
            post_length_in = height_in
            needs_flanges = True

        post_total_ft = self.inches_to_feet(post_length_in) * post_count
        post_weight = self.get_weight_lbs(post_profile, post_total_ft)

        items.append(self.make_material_item(
            description=f"Posts — 1-1/2\" sq tube 11ga × {post_count} ({self.inches_to_feet(post_length_in):.1f} ft each)",
            material_type="square_tubing",
            profile=post_profile,
            length_inches=post_length_in,
            quantity=self.apply_waste(post_count, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(post_length_in) * post_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += post_weight
        total_weld_inches += self.weld_inches_for_joints(post_count * 2, 3.0)  # Post-to-rail welds

        # Post flanges (hardware)
        if needs_flanges:
            hardware.append(self.make_hardware_item(
                description=f"Surface mount flange — {post_mount}",
                quantity=post_count,
                options=lookup.get_hardware_options("surface_mount_flange"),
            ))

        # --- 2. Top rail ---
        top_rail_key, top_rail_mat = self._lookup_top_rail(top_rail_str)
        top_rail_price_ft = lookup.get_price_per_foot(top_rail_key)
        # Add 6" per transition for miter joint waste
        top_rail_total_in = linear_inches + (num_transitions * 6)
        top_rail_total_ft = self.inches_to_feet(top_rail_total_in)
        top_rail_weight = self.get_weight_lbs(top_rail_key, top_rail_total_ft)

        items.append(self.make_material_item(
            description=f"Top rail — {top_rail_str} ({top_rail_total_ft:.1f} ft)",
            material_type=top_rail_mat,
            profile=top_rail_key,
            length_inches=top_rail_total_in,
            quantity=self.linear_feet_to_pieces(top_rail_total_ft),
            unit_price=round(top_rail_total_ft * top_rail_price_ft / max(self.linear_feet_to_pieces(top_rail_total_ft), 1), 2),
            cut_type="miter_45" if num_transitions > 0 else "square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += top_rail_weight

        # --- 3. Bottom rail (same profile as top rail) ---
        bottom_rail_in = top_rail_total_in
        bottom_rail_ft = top_rail_total_ft
        bottom_rail_weight = self.get_weight_lbs(top_rail_key, bottom_rail_ft)

        items.append(self.make_material_item(
            description=f"Bottom rail — {top_rail_str} ({bottom_rail_ft:.1f} ft)",
            material_type=top_rail_mat,
            profile=top_rail_key,
            length_inches=bottom_rail_in,
            quantity=self.linear_feet_to_pieces(bottom_rail_ft),
            unit_price=round(bottom_rail_ft * top_rail_price_ft / max(self.linear_feet_to_pieces(bottom_rail_ft), 1), 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += bottom_rail_weight

        # --- 4. Balusters / infill ---
        if "Cable" in infill_style:
            # Cable infill — horizontal runs
            cable_spacing_in = 3.0  # Code: 3" max spacing for cable
            cable_count = math.ceil((height_in - 4) / cable_spacing_in) + 1  # Between top and bottom rail
            cable_length_ft = linear_footage  # Each cable runs the full length

            # Number of cable sections (between posts)
            section_count = post_count - 1
            total_cable_ft = cable_count * cable_length_ft

            assumptions.append(f"Cable infill: {cable_count} cables at 3\" spacing, {total_cable_ft:.0f} total linear feet.")

            # Tensioners: 1 per cable per section
            tensioner_count = cable_count * section_count
            hardware.append(self.make_hardware_item(
                description=f"Cable tensioner — {tensioner_count} total ({cable_count} cables × {section_count} sections)",
                quantity=tensioner_count,
                options=lookup.get_hardware_options("cable_tensioner"),
            ))
            # End fittings: 2 per cable (or 1 per cable per post through-hole)
            end_fitting_count = cable_count * 2
            hardware.append(self.make_hardware_item(
                description=f"Cable end fitting × {end_fitting_count}",
                quantity=end_fitting_count,
                options=lookup.get_hardware_options("cable_end_fitting"),
            ))

        elif "Glass" in infill_style:
            # Glass panels — we fabricate steel frame/clamps; glass sourced separately
            section_count = post_count - 1
            panel_width_in = (linear_inches / section_count) - 2 if section_count > 0 else linear_inches
            panel_height_in = height_in - 6  # Minus rail heights
            assumptions.append(f"Glass panels: {section_count} panels approx. {panel_width_in:.0f}\" × {panel_height_in:.0f}\". Glass sourced separately — not included in this quote.")

        elif "None" not in infill_style and "open" not in infill_style.lower():
            # Standard balusters (vertical or horizontal)
            is_horizontal = "Horizontal" in infill_style
            baluster_profile_key, baluster_mat = self._lookup_baluster(infill_style)
            baluster_price_ft = lookup.get_price_per_foot(baluster_profile_key)

            if is_horizontal:
                # Horizontal bars: count from height / spacing, each bar = full section width
                bar_count = math.ceil((height_in - 4) / baluster_spacing_in) + 1
                bar_length_in = linear_inches  # Full run length
                bar_total_ft = self.inches_to_feet(bar_length_in) * bar_count
                label = f"Horizontal bars at {baluster_spacing_in}\" OC × {bar_count}"
                baluster_count = bar_count
                baluster_length_in = bar_length_in
            else:
                # Vertical balusters: count from width / spacing
                baluster_count = math.ceil(linear_inches / baluster_spacing_in) + 1
                baluster_length_in = height_in - 4  # Minus top and bottom rail
                bar_total_ft = self.inches_to_feet(baluster_length_in) * baluster_count
                label = f"Balusters — {infill_style} at {baluster_spacing_in}\" OC × {baluster_count}"

            baluster_weight = self.get_weight_lbs(baluster_profile_key, bar_total_ft)
            waste = self.WASTE_FLAT if "flat" in baluster_mat else self.WASTE_TUBE

            items.append(self.make_material_item(
                description=label,
                material_type=baluster_mat,
                profile=baluster_profile_key,
                length_inches=baluster_length_in,
                quantity=self.apply_waste(baluster_count, waste),
                unit_price=round(self.inches_to_feet(baluster_length_in) * baluster_price_ft, 2),
                cut_type="square",
                waste_factor=waste,
            ))
            total_weight += baluster_weight
            # Weld: top and bottom tack per baluster
            total_weld_inches += self.weld_inches_for_joints(baluster_count * 2, 1.5)

        # --- 5. End caps / returns ---
        if num_transitions > 0:
            assumptions.append(f"{num_transitions} transitions/corners — miter joints add waste and labor.")

        # --- 6. Surface area for finishing ---
        total_sq_ft = linear_footage * self.inches_to_feet(height_in)

        return self.make_material_list(
            job_type="straight_railing",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    # --- Private helpers ---

    def _parse_height(self, height_str: str, custom: str = None) -> float:
        """Parse railing height from answer string to inches."""
        if custom:
            return self.parse_inches(custom, default=42.0)
        h = str(height_str)
        if "36" in h:
            return 36.0
        if "42" in h:
            return 42.0
        if "48" in h:
            return 48.0
        if "34" in h:
            return 34.0
        return 42.0

    def _parse_spacing(self, spacing_str: str) -> float:
        if not spacing_str:
            return 4.0
        s = str(spacing_str)
        if "3-1/2" in s or "3.5" in s:
            return 3.5
        if "3" in s and "13" not in s:
            return 3.0
        if "5" in s:
            return 5.0
        if "6" in s:
            return 6.0
        return 4.0

    def _parse_post_spacing(self, spacing_str: str) -> float:
        """Parse post spacing from answer string to feet."""
        s = str(spacing_str)
        if "4" in s and "14" not in s:
            return 4.0
        if "5" in s and "15" not in s:
            return 5.0
        if "8" in s:
            return 8.0
        return 6.0  # Default

    def _lookup_top_rail(self, rail_str: str) -> tuple:
        """Returns (profile_key, material_type)."""
        if rail_str in TOP_RAIL_PROFILES:
            return TOP_RAIL_PROFILES[rail_str]
        # Fuzzy match
        for key, val in TOP_RAIL_PROFILES.items():
            if key.split("(")[0].strip() in rail_str or rail_str in key:
                return val
        return ("sq_tube_1.5x1.5_14ga", "square_tubing")

    def _lookup_baluster(self, style_str: str) -> tuple:
        """Returns (profile_key, material_type)."""
        if style_str in BALUSTER_PROFILES:
            return BALUSTER_PROFILES[style_str]
        for key, val in BALUSTER_PROFILES.items():
            if key in style_str or style_str in key:
                return val
        return ("sq_bar_0.75", "square_tubing")
