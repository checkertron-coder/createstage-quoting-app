"""
Custom exhaust calculator.

Pipe runs + bends + flanges + hardware (gaskets, clamps).
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()

# Typical pipe footage by exhaust type
EXHAUST_FOOTAGE = {
    "Full custom exhaust (headers/manifold back)": 18,
    "Cat-back exhaust (catalytic converter back)": 10,
    "Downpipe / turbo piping only": 4,
    "Header fabrication only": 6,
    "Repair / patch existing exhaust": 3,
}


class ExhaustCustomCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # Try AI cut list for custom/complex designs
        if self._has_description(fields):
            ai_cuts = self._try_ai_cut_list("exhaust_custom", fields)
            if ai_cuts is not None:
                return self._build_from_ai_cuts("exhaust_custom", ai_cuts, fields, assumptions)

        # Parse inputs
        exhaust_type = fields.get("exhaust_type", "Cat-back exhaust (catalytic converter back)")
        pipe_diameter_str = fields.get("pipe_diameter", "2.5\" (V6 / small V8)")
        material_str = fields.get("material", "Mild steel (cheapest — will rust eventually)")

        pipe_od_in = self._parse_diameter(pipe_diameter_str)
        is_dual = "dual" in str(pipe_diameter_str).lower()
        is_stainless = "stainless" in str(material_str).lower()

        # Pipe footage
        base_footage = EXHAUST_FOOTAGE.get(exhaust_type, 10)
        if is_dual:
            base_footage = int(base_footage * 1.8)
        pipe_total_ft = float(base_footage)

        # Select profile (use closest available)
        pipe_profile = self._select_pipe_profile(pipe_od_in)
        pipe_price_ft = lookup.get_price_per_foot(pipe_profile)
        if pipe_price_ft == 0.0:
            pipe_price_ft = 4.50
            assumptions.append("Exhaust pipe price estimated at $4.50/ft.")
        if is_stainless:
            pipe_price_ft *= 2.5  # Stainless premium
            assumptions.append("304 stainless adds ~2.5× material cost over mild steel.")

        # 1. Straight pipe sections
        pipe_weight = pipe_total_ft * self._weight_per_ft(pipe_od_in)

        items.append(self.make_material_item(
            description="Exhaust pipe — %.2f\" OD %s (%.0f ft%s)" % (
                pipe_od_in,
                "304 SS" if is_stainless else "mild steel",
                pipe_total_ft,
                " dual" if is_dual else ""),
            material_type="stainless_304" if is_stainless else "mild_steel",
            profile=pipe_profile,
            length_inches=self.feet_to_inches(pipe_total_ft),
            quantity=self.linear_feet_to_pieces(pipe_total_ft),
            unit_price=round(pipe_total_ft * pipe_price_ft / max(
                self.linear_feet_to_pieces(pipe_total_ft), 1), 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += pipe_weight

        # 2. Mandrel bends
        bend_count = self._bend_count(exhaust_type, is_dual)
        bend_price_each = 18.00 if not is_stainless else 45.00
        bend_weight = self._weight_per_ft(pipe_od_in) * 1.5 * bend_count  # ~1.5 ft per bend

        items.append(self.make_material_item(
            description="Mandrel bends — %.2f\" %s × %d" % (
                pipe_od_in,
                "304 SS" if is_stainless else "mild steel",
                bend_count),
            material_type="stainless_304" if is_stainless else "mild_steel",
            profile=pipe_profile,
            length_inches=18.0,  # ~18" per bend
            quantity=bend_count,
            unit_price=bend_price_each,
            cut_type="square",
            waste_factor=0.0,
        ))
        total_weight += bend_weight

        # 3. Flanges / V-band clamps
        flange_count = 2 if not is_dual else 4
        hardware.append(self.make_hardware_item(
            description="Exhaust flange / V-band clamp",
            quantity=flange_count,
            options=[
                {"supplier": "Amazon", "price": 22.00, "url": "", "part_number": None, "lead_days": 5},
                {"supplier": "McMaster-Carr", "price": 28.00, "url": "", "part_number": None, "lead_days": 3},
                {"supplier": "Grainger", "price": 32.00, "url": "", "part_number": None, "lead_days": 2},
            ],
        ))

        # 4. Hangers / clamps
        hanger_count = max(int(pipe_total_ft / 3), 2)
        hardware.append(self.make_hardware_item(
            description="Exhaust hanger / rubber mount",
            quantity=hanger_count,
            options=[
                {"supplier": "Amazon", "price": 8.00, "url": "", "part_number": None, "lead_days": 5},
                {"supplier": "McMaster-Carr", "price": 12.00, "url": "", "part_number": None, "lead_days": 3},
                {"supplier": "Grainger", "price": 14.00, "url": "", "part_number": None, "lead_days": 2},
            ],
        ))

        # Weld totals
        total_weld_inches = bend_count * math.pi * pipe_od_in  # Each bend-to-straight joint
        total_weld_inches += flange_count * math.pi * pipe_od_in  # Flange welds

        # Surface area (cylindrical)
        circumference_ft = self.inches_to_feet(math.pi * pipe_od_in)
        total_sq_ft = circumference_ft * pipe_total_ft

        assumptions.append(
            "%s — %.0f ft of %.2f\" pipe, %d bends." % (
                exhaust_type.split("(")[0].strip(), pipe_total_ft, pipe_od_in, bend_count))

        return self.make_material_list(
            job_type="exhaust_custom",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _parse_diameter(self, s):
        s = str(s)
        if "2\"" in s and "2.5" not in s and "2.25" not in s:
            return 2.0
        if "2.25" in s:
            return 2.25
        if "2.5" in s:
            return 2.5
        if "3\"" in s and "3.5" not in s:
            return 3.0
        if "3.5" in s:
            return 3.5
        if "4\"" in s or "4 " in s:
            return 4.0
        return 2.5

    def _select_pipe_profile(self, od):
        if od <= 1.5:
            return "round_tube_1.5_14ga"
        if od <= 2.0:
            return "round_tube_2_11ga"
        return "round_tube_2_11ga"  # Closest available

    def _weight_per_ft(self, od):
        """Approximate weight per foot for exhaust pipe by OD."""
        weights = {2.0: 1.5, 2.25: 1.8, 2.5: 2.1, 3.0: 2.8, 3.5: 3.4, 4.0: 4.0}
        return weights.get(od, 2.5)

    def _bend_count(self, exhaust_type, is_dual):
        counts = {
            "Full custom exhaust (headers/manifold back)": 8,
            "Cat-back exhaust (catalytic converter back)": 5,
            "Downpipe / turbo piping only": 3,
            "Header fabrication only": 4,
            "Repair / patch existing exhaust": 1,
        }
        count = counts.get(exhaust_type, 4)
        if is_dual:
            count = int(count * 1.6)
        return count
