"""
FireTable product calculator — BOM-based.

Loads material list from data/raw/firetable_pro_bom.json.
Known product with known materials and pricing.
"""

import json
import os

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()

# Load FireTable BOM
_BOM_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "raw", "firetable_pro_bom.json"
)
_FIRETABLE_BOM = None
try:
    with open(_BOM_PATH) as _f:
        _FIRETABLE_BOM = json.load(_f)
except (FileNotFoundError, json.JSONDecodeError):
    pass


class ProductFiretableCalculator(BaseCalculator):

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
            ai_cuts = self._try_ai_cut_list("product_firetable", fields)
            if ai_cuts is not None:
                return self._build_from_ai_cuts("product_firetable", ai_cuts, fields, assumptions)

        configuration = fields.get("configuration",
                                    "FireTable Pro System (base + basin + stand)")
        quantity = self.parse_int(fields.get("quantity"), default=1)
        if quantity < 1:
            quantity = 1

        is_custom = "custom" in str(configuration).lower()
        is_base_only = "base only" in str(configuration).lower()

        if _FIRETABLE_BOM and not is_custom:
            # Use BOM data
            bom_materials = _FIRETABLE_BOM.get("materials", [])

            for mat in bom_materials:
                qty = mat.get("qty", 1)
                if is_base_only:
                    # Skip some items for base-only config
                    if "grill" in mat.get("desc", "").lower():
                        continue

                unit_price = mat.get("unit_price", 0)
                desc = mat.get("desc", "Unknown material")

                items.append(self.make_material_item(
                    description=desc,
                    material_type=mat.get("material", "mild_steel"),
                    profile="firetable_bom",
                    length_inches=0,
                    quantity=qty * quantity,
                    unit_price=round(unit_price, 2),
                    cut_type="square",
                    waste_factor=0.0,
                ))
                total_weight += unit_price * 0.5  # Rough weight estimate from price

            bom_totals = _FIRETABLE_BOM.get("totals", {})
            total_weight = bom_totals.get("weight_lbs", total_weight) * quantity

            assumptions.append(
                "FireTable Pro BOM loaded from supplier quote (Osorio Metals). "
                "Prices are actual supplier quotes.")
            if quantity > 1:
                assumptions.append("Quantity: %d units. Material costs scale linearly." % quantity)

        else:
            # Custom or BOM not available — estimate
            # Stainless steel sheet and tube for fire table
            ss_sheet_sqft = 32.0  # ~1 sheet of 4'×8' stainless
            ss_sheet_price = 464.40  # From BOM
            ss_sheet_weight = 80.0  # Approximate

            items.append(self.make_material_item(
                description="304 stainless sheet 11ga (basin + panels)",
                material_type="stainless_304",
                profile="ss_304_sheet",
                length_inches=96,
                quantity=quantity,
                unit_price=ss_sheet_price,
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += ss_sheet_weight * quantity

            # Frame tube
            frame_profile = "sq_tube_1.5x1.5_14ga"
            frame_price_ft = lookup.get_price_per_foot(frame_profile)
            frame_ft = 20.0  # ~20 ft of tube per table
            frame_weight = self.get_weight_lbs(frame_profile, frame_ft)

            items.append(self.make_material_item(
                description="Frame tubing — 1-1/2\" sq tube 14ga (stand + supports)",
                material_type="square_tubing",
                profile=frame_profile,
                length_inches=self.feet_to_inches(frame_ft),
                quantity=quantity,
                unit_price=round(frame_ft * frame_price_ft, 2),
                cut_type="miter_45",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += frame_weight * quantity

            # Plate for basin
            plate_weight = self.get_plate_weight_lbs(34, 24, 0.75)  # 3/4" basin plate
            items.append(self.make_material_item(
                description="HR Plate 3/4\" × 24\" × 34\" (basin base)",
                material_type="plate",
                profile="plate_0.75",
                length_inches=34,
                quantity=quantity,
                unit_price=212.41,  # From BOM
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += plate_weight * quantity

            assumptions.append("Custom FireTable — estimated from standard Pro BOM with adjustments.")

        # Accessories
        accessories = fields.get("accessories", [])
        if isinstance(accessories, str):
            accessories = [accessories]

        retail = {}
        if _FIRETABLE_BOM:
            retail = _FIRETABLE_BOM.get("retail_prices", {})

        for acc in accessories:
            if "lid" in str(acc).lower() and "Lid" not in str(acc):
                acc = "FireTable Lid"
            if "caster" in str(acc).lower():
                hardware.append(self.make_hardware_item(
                    description="Locking Casters (set of 4)",
                    quantity=quantity,
                    options=[{"supplier": "Direct", "price": retail.get("Locking Casters", 100.00),
                              "url": "", "part_number": None, "lead_days": 5}],
                ))
            elif "hanger" in str(acc).lower():
                hardware.append(self.make_hardware_item(
                    description="Hanger Bracket",
                    quantity=quantity,
                    options=[{"supplier": "Direct", "price": retail.get("Hanger Bracket", 75.00),
                              "url": "", "part_number": None, "lead_days": 5}],
                ))
            elif "suspension" in str(acc).lower():
                hardware.append(self.make_hardware_item(
                    description="FireTable Suspension System",
                    quantity=quantity,
                    options=[{"supplier": "Direct", "price": retail.get(
                        "FireTable Suspension System_from", 1045.00),
                              "url": "", "part_number": None, "lead_days": 10}],
                ))

        # Surface area (approximate for a fire table)
        total_sq_ft = 20.0 * quantity  # ~20 sqft of finish area per unit

        # Weld inches
        total_weld_inches = 120.0 * quantity  # Significant TIG welding for stainless

        assumptions.append("Fuel system (burner, gas connections, ignition) NOT included — sourced separately.")

        return self.make_material_list(
            job_type="product_firetable",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )
