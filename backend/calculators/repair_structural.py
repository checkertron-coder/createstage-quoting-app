"""
Structural repair calculator.

Similar to repair_decorative but routes by repair_type
(trailer, chassis, beam, general structural).
Conservative estimates with explicit assumptions.
"""

import re

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class RepairStructuralCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
            "Structural repair estimates are conservative — actual scope may change upon inspection.",
        ]

        # Try AI cut list for complex structural repairs
        ai_cuts = self._try_ai_cut_list(fields)
        if ai_cuts is not None:
            return self._build_from_ai_cuts(ai_cuts, fields, assumptions)

        # Parse inputs
        repair_type = fields.get("repair_type", fields.get("description", "General structural repair"))
        repair_lower = str(repair_type).lower()

        damage_length_in = 24.0  # Default 2 ft
        damage_dims = fields.get("damage_dimensions", fields.get("approximate_size", ""))
        if damage_dims:
            nums = re.findall(r'(\d+\.?\d*)', str(damage_dims))
            if nums:
                val = float(nums[0])
                if "ft" in str(damage_dims).lower() or "feet" in str(damage_dims).lower():
                    val *= 12
                damage_length_in = max(val, 6.0)

        # Route by repair type
        if "trailer" in repair_lower:
            profile = "channel_4x5.4"
            mat_type = "channel"
            section_length_in = max(damage_length_in, 24.0)
            assumptions.append("Trailer frame repair — channel section replacement estimated.")
        elif "chassis" in repair_lower:
            profile = "rect_tube_2x4_11ga"
            mat_type = "square_tubing"
            section_length_in = max(damage_length_in, 36.0)
            assumptions.append("Chassis repair — rectangular tube section replacement estimated.")
        elif "beam" in repair_lower or "column" in repair_lower:
            profile = "channel_6x8.2"
            mat_type = "channel"
            section_length_in = max(damage_length_in, 48.0)
            assumptions.append("Structural beam/column repair — channel section replacement estimated.")
        else:
            profile = "sq_tube_2x2_11ga"
            mat_type = "square_tubing"
            section_length_in = max(damage_length_in, 18.0)
            assumptions.append("General structural repair — tube section replacement estimated.")

        price_ft = lookup.get_price_per_foot(profile)
        section_ft = self.inches_to_feet(section_length_in)

        # 1. Replacement section
        section_weight = self.get_weight_lbs(profile, section_ft)
        items.append(self.make_material_item(
            description="Replacement section — %s (%.1f ft)" % (profile, section_ft),
            material_type=mat_type,
            profile=profile,
            length_inches=section_length_in,
            quantity=1,
            unit_price=round(section_ft * price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += section_weight
        total_weld_inches += section_length_in * 0.5  # Weld along seams

        # 2. Reinforcement / splice plates
        splice_length_in = min(section_length_in * 0.5, 12.0)
        splice_count = 2
        splice_profile = "flat_bar_2x0.25"
        splice_price_ft = lookup.get_price_per_foot(splice_profile)
        splice_weight = self.get_weight_lbs(splice_profile, self.inches_to_feet(splice_length_in) * splice_count)

        items.append(self.make_material_item(
            description="Splice plates — %s × %d (%.0f\" each)" % (
                splice_profile, splice_count, splice_length_in),
            material_type="flat_bar",
            profile=splice_profile,
            length_inches=splice_length_in,
            quantity=splice_count,
            unit_price=round(self.inches_to_feet(splice_length_in) * splice_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_FLAT,
        ))
        total_weight += splice_weight
        total_weld_inches += splice_length_in * 2 * splice_count  # Both sides of each plate

        # 3. Gusset plates if significant repair
        if section_length_in > 24:
            gusset_count = 4
            gusset_weight = self.get_plate_weight_lbs(6, 6, 0.25) * gusset_count

            items.append(self.make_material_item(
                description="Gusset reinforcement plates — 1/4\" × 6\" × 6\" × %d" % gusset_count,
                material_type="plate",
                profile="plate_0.25",
                length_inches=6.0,
                quantity=gusset_count,
                unit_price=round(gusset_weight * 0.50 / max(gusset_count, 1), 2),
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += gusset_weight
            total_weld_inches += gusset_count * 12

        # Surface area
        total_sq_ft = max(self.sq_ft_from_dimensions(section_length_in, 8), 1.0)

        assumptions.append(
            "Repair section: %.0f\" of %s. Splice plates at each end. "
            "Site inspection recommended to confirm scope." % (section_length_in, profile))

        return self.make_material_list(
            job_type="repair_structural",
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
            return generator.generate_cut_list("repair_structural", fields)
        except Exception:
            return None

    def _build_from_ai_cuts(self, ai_cuts, fields, assumptions):
        """Build MaterialList from AI-generated cut list."""
        items = []
        total_weight = 0.0
        total_weld_inches = 0.0

        for cut in ai_cuts:
            profile = cut.get("profile", "sq_tube_2x2_11ga")
            length_in = cut.get("length_inches", 12.0)
            quantity = cut.get("quantity", 1)
            price_ft = lookup.get_price_per_foot(profile)
            if price_ft == 0.0:
                price_ft = 3.50
            length_ft = self.inches_to_feet(length_in)
            weight = self.get_weight_lbs(profile, length_ft * quantity)
            if weight == 0.0:
                weight = length_ft * quantity * 2.5

            items.append(self.make_material_item(
                description=cut.get("description", "Repair section"),
                material_type=cut.get("material_type", "mild_steel"),
                profile=profile,
                length_inches=length_in,
                quantity=self.apply_waste(quantity, self.WASTE_TUBE),
                unit_price=round(length_ft * price_ft, 2),
                cut_type=cut.get("cut_type", "square"),
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += weight
            total_weld_inches += quantity * 8

        damage_dims = fields.get("damage_dimensions", fields.get("approximate_size", ""))
        nums = re.findall(r'(\d+\.?\d*)', str(damage_dims))
        section_len = float(nums[0]) if nums else 24.0
        total_sq_ft = max(self.sq_ft_from_dimensions(section_len, 8), 1.0)

        assumptions.append("Structural repair cut list generated by AI from damage description.")

        return self.make_material_list(
            job_type="repair_structural",
            items=items,
            hardware=[],
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )
