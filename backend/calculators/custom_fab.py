"""
Custom fabrication calculator — universal fallback.

This calculator NEVER fails. It handles any job type by estimating
material needs from approximate dimensions and quantity.
Used as the fallback when no dedicated calculator exists.

Supports AI cut list generation for better estimates when a description
is provided. Falls back to template-based estimation silently.
"""

import re

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class CustomFabCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
            "Custom fabrication estimate — actual material needs may vary significantly. "
            "This estimate is based on approximate dimensions only.",
        ]

        # Try AI cut list — custom_fab always tries AI when description exists
        ai_cuts = self._try_ai_cut_list(fields)
        if ai_cuts is not None:
            return self._build_from_ai_cuts(ai_cuts, fields, assumptions)

        # Parse inputs with generous defaults
        quantity = self.parse_int(fields.get("quantity"), default=1)
        if quantity < 1:
            quantity = 1

        # Parse approximate size
        size_str = fields.get("approximate_size", "")
        length_in, width_in, height_in = self._parse_size(size_str)

        # Material selection
        material_str = fields.get("material", "Mild steel (most common / cheapest)")
        profile, mat_type = self._select_profile(material_str)
        price_per_ft = lookup.get_price_per_foot(profile)
        if price_per_ft == 0.0:
            price_per_ft = 3.50  # Safe fallback
            assumptions.append("Profile price not found — using $3.50/ft default.")

        # Estimate frame perimeter as primary material
        perimeter_in = 2 * (length_in + width_in) + 4 * height_in
        perimeter_ft = self.inches_to_feet(perimeter_in)
        frame_weight = self.get_weight_lbs(profile, perimeter_ft)
        if frame_weight == 0.0:
            # Fallback weight estimate: ~2 lbs/ft for typical tube
            frame_weight = perimeter_ft * 2.0

        per_unit_cost = round(perimeter_ft * price_per_ft, 2)

        items.append(self.make_material_item(
            description="Estimated frame/structural material — %s (%.1f ft per unit)" % (profile, perimeter_ft),
            material_type=mat_type,
            profile=profile,
            length_inches=perimeter_in,
            quantity=self.apply_waste(quantity, self.WASTE_TUBE),
            unit_price=per_unit_cost,
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += frame_weight * quantity

        # Estimate cross members / internal bracing
        internal_in = (length_in + width_in) * 0.5
        internal_ft = self.inches_to_feet(internal_in)
        internal_weight = self.get_weight_lbs(profile, internal_ft)
        if internal_weight == 0.0:
            internal_weight = internal_ft * 2.0

        items.append(self.make_material_item(
            description="Estimated internal bracing — %s (%.1f ft per unit)" % (profile, internal_ft),
            material_type=mat_type,
            profile=profile,
            length_inches=internal_in,
            quantity=self.apply_waste(quantity, self.WASTE_TUBE),
            unit_price=round(internal_ft * price_per_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += internal_weight * quantity

        # Surface area
        total_sq_ft = self.sq_ft_from_dimensions(length_in, width_in) * 2 * quantity

        # Weld estimate
        total_weld_inches = perimeter_in * 0.3 * quantity

        assumptions.append(
            "Estimated from approximate size: %.0f\" x %.0f\" x %.0f\". "
            "Quantity: %d." % (length_in, width_in, height_in, quantity)
        )

        return self.make_material_list(
            job_type=fields.get("_job_type", "custom_fab"),
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _try_ai_cut_list(self, fields):
        """Try AI cut list. Custom fab always tries when there's a description."""
        description = fields.get("description", "")
        notes = fields.get("notes", "")
        if not description and not notes:
            return None

        try:
            from .ai_cut_list import AICutListGenerator
            generator = AICutListGenerator()
            return generator.generate_cut_list(
                fields.get("_job_type", "custom_fab"), fields)
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
                price_ft = 3.50
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

        # Surface area from approximate size
        size_str = fields.get("approximate_size", "")
        length_in, width_in, _ = self._parse_size(size_str)
        total_sq_ft = self.sq_ft_from_dimensions(length_in, width_in) * 2

        assumptions.append("Cut list generated by AI from project description.")

        return self.make_material_list(
            job_type=fields.get("_job_type", "custom_fab"),
            items=items,
            hardware=[],
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _parse_size(self, size_str):
        """Parse approximate size from free text. Returns (length_in, width_in, height_in)."""
        if not size_str:
            return (24.0, 12.0, 12.0)  # Default 2' x 1' x 1'

        s = str(size_str).lower()
        numbers = re.findall(r'(\d+\.?\d*)', s)

        # Convert to inches
        is_feet = "ft" in s or "feet" in s or "foot" in s or "'" in s

        if len(numbers) >= 3:
            vals = [float(n) for n in numbers[:3]]
            if is_feet:
                vals = [v * 12 for v in vals]
            return (max(vals[0], 1.0), max(vals[1], 1.0), max(vals[2], 1.0))
        elif len(numbers) >= 2:
            vals = [float(n) for n in numbers[:2]]
            if is_feet:
                vals = [v * 12 for v in vals]
            return (max(vals[0], 1.0), max(vals[1], 1.0), max(vals[0] * 0.5, 6.0))
        elif len(numbers) == 1:
            val = float(numbers[0])
            if is_feet:
                val *= 12
            return (max(val, 1.0), max(val * 0.5, 1.0), max(val * 0.5, 6.0))

        return (24.0, 12.0, 12.0)

    def _select_profile(self, material_str):
        """Map material description to profile key and material type."""
        m = str(material_str).lower()
        if "stainless" in m:
            return ("sq_tube_1.5x1.5_11ga", "stainless_304")
        if "aluminum" in m:
            return ("sq_tube_1.5x1.5_11ga", "aluminum_6061")
        return ("sq_tube_1.5x1.5_11ga", "mild_steel")
