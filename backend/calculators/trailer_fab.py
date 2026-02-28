"""
Custom trailer calculator.

Frame rails (channel) + cross members + tongue + axle mounts + deck.
Length-driven calculations.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class TrailerFabCalculator(BaseCalculator):

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
        length_ft = self.parse_feet(fields.get("length"), default=16.0)
        width_str = fields.get("width", "6.5' (standard utility)")
        width_ft = self._parse_width(width_str)
        length_in = self.feet_to_inches(length_ft)
        width_in = self.feet_to_inches(width_ft)

        axle_str = fields.get("axle_count", "Single axle (up to 3,500 lb capacity)")
        axle_count = self._parse_axle_count(axle_str)

        deck_type = fields.get("deck_type", "Expanded metal deck")
        trailer_type = fields.get("trailer_type", "Flatbed / utility trailer")

        # Frame profile — channel iron for main rails
        main_rail_profile = "channel_6x8.2"
        cross_member_profile = "channel_4x5.4"
        tongue_profile = "channel_6x8.2"

        main_rail_price = lookup.get_price_per_foot(main_rail_profile)
        cross_price = lookup.get_price_per_foot(cross_member_profile)

        # 1. Main frame rails (2× trailer length + tongue)
        tongue_length_ft = 4.0  # Standard 4 ft tongue
        rail_length_ft = length_ft + tongue_length_ft
        total_rail_ft = rail_length_ft * 2
        rail_weight = self.get_weight_lbs(main_rail_profile, total_rail_ft)

        items.append(self.make_material_item(
            description="Main frame rails — C6×8.2 channel × 2 (%.1f ft each, includes tongue)" % rail_length_ft,
            material_type="channel",
            profile=main_rail_profile,
            length_inches=self.feet_to_inches(rail_length_ft),
            quantity=self.apply_waste(2, self.WASTE_TUBE),
            unit_price=round(rail_length_ft * main_rail_price, 2),
            cut_type="miter_45",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += rail_weight

        # 2. Cross members (every 16" on center)
        cross_spacing_in = 16.0
        cross_count = math.ceil(length_in / cross_spacing_in) + 1
        cross_length_in = width_in
        cross_total_ft = self.inches_to_feet(cross_length_in) * cross_count
        cross_weight = self.get_weight_lbs(cross_member_profile, cross_total_ft)

        items.append(self.make_material_item(
            description="Cross members — C4×5.4 channel × %d at 16\" OC (%.1f ft each)" % (
                cross_count, self.inches_to_feet(cross_length_in)),
            material_type="channel",
            profile=cross_member_profile,
            length_inches=cross_length_in,
            quantity=self.apply_waste(cross_count, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(cross_length_in) * cross_price, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += cross_weight

        # 3. Tongue assembly (A-frame from 2× channel converging to coupler)
        tongue_weight = self.get_weight_lbs(tongue_profile, tongue_length_ft * 2)

        items.append(self.make_material_item(
            description="Tongue assembly — C6×8.2 A-frame (%.0f ft)" % tongue_length_ft,
            material_type="channel",
            profile=tongue_profile,
            length_inches=self.feet_to_inches(tongue_length_ft),
            quantity=2,
            unit_price=round(tongue_length_ft * main_rail_price, 2),
            cut_type="miter_45",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += tongue_weight

        # 4. Axle mounting crossmembers (heavier — one per axle)
        axle_mount_profile = "sq_tube_3x3_11ga"
        axle_mount_price = lookup.get_price_per_foot(axle_mount_profile)
        axle_mount_length_in = width_in + 12  # Extra for spring hangers
        axle_mount_ft = self.inches_to_feet(axle_mount_length_in) * axle_count
        axle_mount_weight = self.get_weight_lbs(axle_mount_profile, axle_mount_ft)

        items.append(self.make_material_item(
            description="Axle mount crossmembers — 3\" sq tube 11ga × %d" % axle_count,
            material_type="square_tubing",
            profile=axle_mount_profile,
            length_inches=axle_mount_length_in,
            quantity=self.apply_waste(axle_count, self.WASTE_TUBE),
            unit_price=round(self.inches_to_feet(axle_mount_length_in) * axle_mount_price, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += axle_mount_weight

        # 5. Deck material
        deck_sqft = self.sq_ft_from_dimensions(length_in, width_in)
        if "expanded" in str(deck_type).lower():
            deck_profile = "expanded_metal_13ga"
            deck_price_sqft = lookup.get_price_per_sqft(deck_profile)
            if deck_price_sqft == 0.0:
                deck_price_sqft = 1.40
            deck_sheets = self.apply_waste(math.ceil(deck_sqft / 32.0), self.WASTE_SHEET)
            deck_weight = self.get_plate_weight_lbs(length_in, width_in, 0.075)

            items.append(self.make_material_item(
                description="Deck — expanded metal 13ga (%.0f sq ft)" % deck_sqft,
                material_type="plate",
                profile=deck_profile,
                length_inches=length_in,
                quantity=deck_sheets,
                unit_price=round(deck_sqft * deck_price_sqft / max(deck_sheets, 1), 2),
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += deck_weight
        elif "diamond" in str(deck_type).lower():
            deck_profile = "sheet_11ga"
            deck_price_sqft = lookup.get_price_per_sqft(deck_profile)
            if deck_price_sqft == 0.0:
                deck_price_sqft = 2.65
            deck_sheets = self.apply_waste(math.ceil(deck_sqft / 32.0), self.WASTE_SHEET)
            deck_weight = self.get_plate_weight_lbs(length_in, width_in, 0.1196)

            items.append(self.make_material_item(
                description="Deck — 11ga diamond plate (%.0f sq ft)" % deck_sqft,
                material_type="plate",
                profile=deck_profile,
                length_inches=length_in,
                quantity=deck_sheets,
                unit_price=round(deck_sqft * deck_price_sqft / max(deck_sheets, 1), 2),
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += deck_weight
        else:
            assumptions.append("Deck type: %s — deck material not included or by others." % deck_type)

        # 6. Hardware
        # Coupler
        hardware.append(self.make_hardware_item(
            description="Trailer coupler (2\" ball for single axle, 2-5/16\" for tandem+)",
            quantity=1,
            options=[
                {"supplier": "Amazon", "price": 55.00, "url": "", "part_number": None, "lead_days": 5},
                {"supplier": "McMaster-Carr", "price": 65.00, "url": "", "part_number": None, "lead_days": 3},
                {"supplier": "Grainger", "price": 70.00, "url": "", "part_number": None, "lead_days": 2},
            ],
        ))
        # Safety chains
        hardware.append(self.make_hardware_item(
            description="Safety chain set (pair)",
            quantity=1,
            options=[
                {"supplier": "Amazon", "price": 25.00, "url": "", "part_number": None, "lead_days": 5},
                {"supplier": "McMaster-Carr", "price": 30.00, "url": "", "part_number": None, "lead_days": 3},
                {"supplier": "Grainger", "price": 35.00, "url": "", "part_number": None, "lead_days": 2},
            ],
        ))
        # Jack
        hardware.append(self.make_hardware_item(
            description="Trailer tongue jack",
            quantity=1,
            options=[
                {"supplier": "Amazon", "price": 45.00, "url": "", "part_number": None, "lead_days": 5},
                {"supplier": "McMaster-Carr", "price": 55.00, "url": "", "part_number": None, "lead_days": 3},
                {"supplier": "Grainger", "price": 60.00, "url": "", "part_number": None, "lead_days": 2},
            ],
        ))

        # Weld totals
        total_weld_inches = cross_count * width_in * 0.2  # Cross member welds
        total_weld_inches += length_in * 2 * 0.1  # Rail welds
        total_weld_inches += axle_count * 24  # Axle mount welds

        # Surface area
        total_sq_ft = deck_sqft + (length_ft + tongue_length_ft) * 2 * 0.5  # Rails visible area

        assumptions.append(
            "%.0f ft × %.0f ft trailer, %d axle(s), %d cross members at 16\" OC." % (
                length_ft, width_ft, axle_count, cross_count))
        assumptions.append("Axles, springs, wheels/tires, wiring, and fenders NOT included in material list.")

        return self.make_material_list(
            job_type="trailer_fab",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _parse_width(self, width_str):
        s = str(width_str)
        if "5'" in s or "5 " in s:
            return 5.0
        if "6'" in s and "6.5" not in s:
            return 6.0
        if "7'" in s or "7 " in s:
            return 7.0
        if "8'" in s and "8.5" not in s:
            return 8.0
        if "8.5" in s:
            return 8.5
        return 6.5

    def _parse_axle_count(self, axle_str):
        s = str(axle_str).lower()
        if "single" in s:
            return 1
        if "triple" in s:
            return 3
        return 2
