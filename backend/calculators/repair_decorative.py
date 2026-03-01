"""
Decorative/ornamental iron repair material calculator.

Fundamentally different from new fabrication calculators.
Repairs are photo-first and estimate-driven — no standard geometry.
This calculator produces conservative estimates with explicit assumptions.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()

# Material profile defaults by item type
ITEM_MATERIAL_PROFILES = {
    "Gate (swing or sliding)": "sq_tube_2x2_11ga",
    "Fence section": "sq_bar_0.75",
    "Railing (stair or flat)": "sq_tube_1.5x1.5_11ga",
    "Balcony railing or guard": "sq_tube_1.5x1.5_11ga",
    "Window grate/bars": "sq_bar_0.75",
    "Decorative panel or screen": "flat_bar_1x0.25",
}


class RepairDecorativeCalculator(BaseCalculator):

    SCOPE_CREEP_BUFFER = 0.25  # 25% buffer when surrounding damage flagged

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
            "Repair estimates are approximate — actual scope may change upon inspection.",
        ]

        # Try AI cut list for complex repairs with description
        ai_cuts = self._try_ai_cut_list(fields)
        if ai_cuts is not None:
            return self._build_from_ai_cuts(ai_cuts, fields, assumptions)

        # --- Parse inputs ---
        repair_types = fields.get("repair_type", "Broken weld (piece detached)")
        if isinstance(repair_types, str):
            repair_types = [repair_types]

        item_type = fields.get("item_type", "Railing (stair or flat)")
        material_type_str = fields.get("material_type", "Mild steel / carbon steel")
        damage_dims = fields.get("damage_dimensions", "")
        is_structural = fields.get("is_structural", "Cosmetic")
        finish_match = fields.get("finish_match", "")
        surrounding_damage = fields.get("surrounding_damage", "No")
        can_remove = fields.get("can_remove", "Can be removed — bring to shop")
        finish = fields.get("finish", "Match existing")

        # Parse damage dimensions — rough estimate
        damage_length_in, damage_width_in = self._parse_damage_dims(damage_dims)

        # Determine material profile
        profile_key = ITEM_MATERIAL_PROFILES.get(item_type, "sq_tube_1.5x1.5_11ga")
        price_per_ft = lookup.get_price_per_foot(profile_key)

        # Scope creep flag
        has_scope_creep = (
            "Yes" in str(surrounding_damage) or
            "widespread" in str(surrounding_damage).lower() or
            "additional" in str(surrounding_damage).lower()
        )

        # --- Calculate based on repair type ---
        for repair in repair_types:
            repair_lower = repair.lower()

            if "broken weld" in repair_lower or "broken" in repair_lower:
                # Broken weld: no new material, just weld repair
                weld_in = max(damage_length_in * 0.5, 6.0)  # At least 6" of weld
                total_weld_inches += weld_in
                assumptions.append(f"Broken weld repair: ~{weld_in:.0f}\" of reweld, no new material.")

            elif "bent" in repair_lower or "deformed" in repair_lower:
                # Bent section: may need replacement piece
                piece_length_in = max(damage_length_in, 12.0)
                piece_length_ft = self.inches_to_feet(piece_length_in)
                piece_weight = self.get_weight_lbs(profile_key, piece_length_ft)

                items.append(self.make_material_item(
                    description=f"Replacement section — {profile_key} ({piece_length_ft:.1f} ft, bent member)",
                    material_type=self._material_type_from_str(material_type_str),
                    profile=profile_key,
                    length_inches=piece_length_in,
                    quantity=1,
                    unit_price=round(piece_length_ft * price_per_ft, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_TUBE,
                ))
                total_weight += piece_weight
                total_weld_inches += self.weld_inches_for_joints(2, 4.0)  # Cut + reweld 2 joints
                assumptions.append(f"Bent section: {piece_length_ft:.1f} ft replacement piece estimated. May be straightened instead if feasible.")

            elif "rust" in repair_lower or "corrosion" in repair_lower:
                # Rust-through: replacement section + connecting material
                patch_length_in = max(damage_length_in, 6.0)
                patch_width_in = max(damage_width_in, 4.0)
                patch_area_sqft = self.sq_ft_from_dimensions(patch_length_in, patch_width_in)

                # Replacement section of the same profile
                piece_length_in = patch_length_in + 4  # Extra 2" each side for overlap
                piece_length_ft = self.inches_to_feet(piece_length_in)
                piece_weight = self.get_weight_lbs(profile_key, piece_length_ft)

                items.append(self.make_material_item(
                    description=f"Rust repair section — {profile_key} ({piece_length_ft:.1f} ft, includes overlap)",
                    material_type=self._material_type_from_str(material_type_str),
                    profile=profile_key,
                    length_inches=piece_length_in,
                    quantity=1,
                    unit_price=round(piece_length_ft * price_per_ft, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_TUBE,
                ))
                total_weight += piece_weight
                total_weld_inches += self.weld_inches_for_joints(2, piece_length_in * 0.3)
                total_sq_ft += patch_area_sqft
                assumptions.append(f"Rust-through: {piece_length_ft:.1f} ft section replacement. Surrounding metal condition may require larger patch.")

            elif "missing" in repair_lower:
                # Missing piece: full replacement from dimensions
                piece_length_in = max(damage_length_in, 12.0)
                piece_length_ft = self.inches_to_feet(piece_length_in)
                piece_weight = self.get_weight_lbs(profile_key, piece_length_ft)

                items.append(self.make_material_item(
                    description=f"Replacement piece — {profile_key} ({piece_length_ft:.1f} ft)",
                    material_type=self._material_type_from_str(material_type_str),
                    profile=profile_key,
                    length_inches=piece_length_in,
                    quantity=1,
                    unit_price=round(piece_length_ft * price_per_ft, 2),
                    cut_type="cope" if "scroll" in item_type.lower() else "square",
                    waste_factor=self.WASTE_TUBE,
                ))
                total_weight += piece_weight
                total_weld_inches += self.weld_inches_for_joints(2, 4.0)
                assumptions.append(f"Missing piece: {piece_length_ft:.1f} ft replacement. Design match accuracy depends on photo reference.")

                # Matching required?
                matching = fields.get("matching_required", "")
                if "exactly" in str(matching).lower():
                    assumptions.append("Exact design match required — may require custom forming/forging. Labor estimate will be higher.")

            elif "crack" in repair_lower or "split" in repair_lower:
                # Crack repair: weld + possible reinforcement
                weld_in = max(damage_length_in, 6.0)
                total_weld_inches += weld_in

                # Add reinforcement plate for structural cracks
                if "Structural" in is_structural or "structural" in is_structural.lower():
                    reinf_length_in = damage_length_in + 4
                    reinf_width_in = 3.0  # 3" wide reinforcement plate
                    reinf_weight = self.get_plate_weight_lbs(reinf_length_in, reinf_width_in, 0.25)
                    reinf_price = lookup.get_price_per_foot("flat_bar_1.5x0.25")

                    items.append(self.make_material_item(
                        description=f"Reinforcement plate — 1/4\" × 3\" × {reinf_length_in:.0f}\"",
                        material_type="flat_bar",
                        profile="flat_bar_1.5x0.25",
                        length_inches=reinf_length_in,
                        quantity=1,
                        unit_price=round(self.inches_to_feet(reinf_length_in) * reinf_price, 2),
                        cut_type="square",
                        waste_factor=self.WASTE_FLAT,
                    ))
                    total_weight += reinf_weight
                    total_weld_inches += reinf_length_in * 2  # Both sides of plate

                assumptions.append(f"Crack/split repair: {weld_in:.0f}\" weld repair" +
                                   (" + reinforcement plate." if "Structural" in is_structural else "."))

            elif "loose" in repair_lower or "wobbly" in repair_lower:
                # Loose posts/anchors: reweld or rebolt
                total_weld_inches += 12.0  # Typical reweld at base
                assumptions.append("Loose anchor repair: reweld at base connection. May require redrilling if anchor bolts are failed.")

        # --- Apply scope creep buffer ---
        if has_scope_creep:
            buffer_pct = int(self.SCOPE_CREEP_BUFFER * 100)
            for item in items:
                original_qty = item["quantity"]
                item["quantity"] = self.apply_waste(original_qty, self.SCOPE_CREEP_BUFFER)
            total_weight *= (1 + self.SCOPE_CREEP_BUFFER)
            total_weld_inches *= (1 + self.SCOPE_CREEP_BUFFER)
            assumptions.append(
                f"Adjacent material condition may require additional work — "
                f"{buffer_pct}% material buffer applied. Site assessment recommended."
            )

        # --- Finishing ---
        if "refinish entire" in str(finish).lower() or "Powder coat" in str(finish):
            # Estimate entire piece area
            est_area = max(total_sq_ft, self.sq_ft_from_dimensions(damage_length_in * 3, damage_width_in * 3))
            total_sq_ft = est_area
            assumptions.append("Finish area estimated for full refinish of the affected piece.")
        elif "match" in str(finish).lower():
            total_sq_ft = max(total_sq_ft, self.sq_ft_from_dimensions(damage_length_in * 1.5, damage_width_in * 1.5))
            assumptions.append("Spot-matching finish — blending may show, full refinish recommended for best results.")
        else:
            total_sq_ft = max(total_sq_ft, 1.0)

        # --- On-site vs shop ---
        if "in place" in str(can_remove).lower() or "on-site" in str(can_remove).lower():
            assumptions.append("On-site repair — on-site labor rate applies. Access constraints may increase time.")

        return self.make_material_list(
            job_type="repair_decorative",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    # --- AI integration ---

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
            return generator.generate_cut_list("repair_decorative", fields)
        except Exception:
            return None

    def _build_from_ai_cuts(self, ai_cuts, fields, assumptions):
        """Build MaterialList from AI-generated cut list."""
        items = []
        total_weight = 0.0
        total_weld_inches = 0.0
        total_sq_ft = 0.0

        for cut in ai_cuts:
            profile = cut.get("profile", "sq_tube_1.5x1.5_11ga")
            length_in = cut.get("length_inches", 12.0)
            quantity = cut.get("quantity", 1)
            price_ft = lookup.get_price_per_foot(profile)
            if price_ft == 0.0:
                price_ft = 2.50
            length_ft = self.inches_to_feet(length_in)
            weight = self.get_weight_lbs(profile, length_ft * quantity)
            if weight == 0.0:
                weight = length_ft * quantity * 2.0

            items.append(self.make_material_item(
                description=cut.get("description", "Repair piece"),
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
            total_sq_ft += self.sq_ft_from_dimensions(length_in, 4)

        total_sq_ft = max(total_sq_ft, 2.0)
        assumptions.append("Repair cut list generated by AI from damage description.")

        return self.make_material_list(
            job_type="repair_decorative",
            items=items,
            hardware=[],
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    # --- Private helpers ---

    def _parse_damage_dims(self, dims_str: str) -> tuple:
        """Parse damage dimensions from free-text input. Returns (length_in, width_in)."""
        if not dims_str:
            return (12.0, 4.0)  # Default: 1 ft × 4" estimated

        s = str(dims_str).lower()
        length = 12.0
        width = 4.0

        # Try to extract numbers
        import re
        numbers = re.findall(r'(\d+\.?\d*)', s)
        if len(numbers) >= 2:
            length = float(numbers[0])
            width = float(numbers[1])
        elif len(numbers) == 1:
            length = float(numbers[0])

        # Check units — convert feet to inches if needed
        if "ft" in s or "feet" in s or "foot" in s:
            length *= 12
            if width < 12:  # Width probably stayed in inches
                pass

        return (max(length, 1.0), max(width, 1.0))

    def _material_type_from_str(self, mat_str: str) -> str:
        """Map material description to MaterialType value."""
        m = str(mat_str).lower()
        if "stainless" in m:
            return "stainless_304"
        if "aluminum" in m:
            return "aluminum_6061"
        if "wrought" in m:
            return "mild_steel"  # Treat old wrought iron as mild steel for pricing
        return "mild_steel"
