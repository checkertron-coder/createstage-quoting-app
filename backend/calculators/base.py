"""
Abstract base class for all job-type calculators.

Input: QuoteParams.fields dict (from Stage 2)
Output: MaterialList dict (per CLAUDE.md contract)
"""

import logging
import math
from abc import ABC, abstractmethod

from ..weights import weight_from_stock, weight_from_dimensions, STOCK_WEIGHTS

logger = logging.getLogger(__name__)


class BaseCalculator(ABC):
    """All job-type calculators inherit from this."""

    # Waste factors — override per calculator if needed
    WASTE_TUBE = 0.05       # 5% waste on tubing
    WASTE_FLAT = 0.10       # 10% waste on flat stock
    WASTE_SHEET = 0.15      # 15% waste on sheet/plate
    WASTE_HARDWARE = 0.00   # 0% waste on hardware

    @abstractmethod
    def calculate(self, fields: dict) -> dict:
        """
        Takes the answered fields from Stage 2.
        Returns a MaterialList dict matching CLAUDE.md contract.
        """
        pass

    # --- Helper methods for all calculators ---

    def apply_waste(self, quantity: float, waste_factor: float) -> int:
        """Apply waste factor to a quantity. Always round UP to next whole unit."""
        return math.ceil(quantity * (1 + waste_factor))

    def linear_feet_to_pieces(self, total_length_ft: float, stock_length_ft: float = 20.0) -> int:
        """
        Calculate number of stock pieces needed.
        Standard stock lengths: 20' for tube/bar, 10' for some flat bar, 4'x8' for sheet.
        Always rounds up — you can't buy half a stick.
        """
        return math.ceil(total_length_ft / stock_length_ft)

    def sq_ft_from_dimensions(self, width_in: float, height_in: float) -> float:
        """Calculate square footage from dimensions in inches."""
        return (width_in * height_in) / 144.0

    def perimeter_inches(self, width_in: float, height_in: float) -> float:
        """Frame perimeter in inches."""
        return 2.0 * (width_in + height_in)

    def weld_inches_for_joints(self, num_joints: int, avg_weld_length_in: float = 3.0) -> float:
        """Estimate total weld linear inches from joint count."""
        return num_joints * avg_weld_length_in

    def parse_feet(self, value, default: float = 0.0) -> float:
        """Parse a feet value from user input. Handles strings like '10', '10.5', etc."""
        if value is None:
            return default
        try:
            return float(str(value).strip().rstrip("'").rstrip("ft").strip())
        except (ValueError, TypeError):
            return default

    def parse_inches(self, value, default: float = 0.0) -> float:
        """Parse an inches value from user input."""
        if value is None:
            return default
        try:
            return float(str(value).strip().rstrip('"').rstrip("in").strip())
        except (ValueError, TypeError):
            return default

    def parse_int(self, value, default: int = 0) -> int:
        """Parse an integer from user input."""
        if value is None:
            return default
        try:
            return int(float(str(value).strip()))
        except (ValueError, TypeError):
            return default

    def parse_number(self, value, default: float = 0.0) -> float:
        """Parse a numeric value from user input."""
        if value is None:
            return default
        try:
            return float(str(value).strip())
        except (ValueError, TypeError):
            return default

    def feet_to_inches(self, feet: float) -> float:
        """Convert feet to inches."""
        return feet * 12.0

    def inches_to_feet(self, inches: float) -> float:
        """Convert inches to feet."""
        return inches / 12.0

    def get_weight_per_ft(self, stock_key: str) -> float:
        """Look up weight per foot from weights.py STOCK_WEIGHTS table."""
        return STOCK_WEIGHTS.get(stock_key, 0.0)

    def get_weight_lbs(self, stock_key: str, length_ft: float) -> float:
        """Calculate weight using weights.py."""
        return weight_from_stock(stock_key, length_ft)

    def get_plate_weight_lbs(self, length_in: float, width_in: float, thickness_in: float,
                             material_type: str = "mild_steel") -> float:
        """Calculate plate/sheet weight using weights.py."""
        return weight_from_dimensions(length_in, width_in, thickness_in, material_type)

    def make_material_item(self, description: str, material_type: str, profile: str,
                           length_inches: float, quantity: int, unit_price: float,
                           cut_type: str = "square", waste_factor: float = 0.0) -> dict:
        """Build a MaterialItem dict matching the CLAUDE.md contract."""
        line_total = round(unit_price * quantity, 2)
        return {
            "description": description,
            "material_type": material_type,
            "profile": profile,
            "length_inches": round(length_inches, 2),
            "quantity": quantity,
            "unit_price": round(unit_price, 2),
            "line_total": line_total,
            "cut_type": cut_type,
            "waste_factor": waste_factor,
        }

    def make_hardware_item(self, description: str, quantity: int,
                           options: list) -> dict:
        """Build a HardwareItem dict matching the CLAUDE.md contract."""
        return {
            "description": description,
            "quantity": quantity,
            "options": options,
        }

    def make_pricing_option(self, supplier: str, price: float, url: str = "",
                            part_number: str = None, lead_days: int = None) -> dict:
        """Build a PricingOption dict matching the CLAUDE.md contract."""
        return {
            "supplier": supplier,
            "price": round(price, 2),
            "url": url,
            "part_number": part_number,
            "lead_days": lead_days,
        }

    def make_material_list(self, job_type: str, items: list, hardware: list,
                           total_weight_lbs: float, total_sq_ft: float,
                           weld_linear_inches: float,
                           assumptions: list = None) -> dict:
        """Build the MaterialList output dict matching the CLAUDE.md contract."""
        return {
            "job_type": job_type,
            "items": items,
            "hardware": hardware,
            "total_weight_lbs": round(total_weight_lbs, 1),
            "total_sq_ft": round(total_sq_ft, 1),
            "weld_linear_inches": round(weld_linear_inches, 1),
            "assumptions": assumptions or [],
        }

    # --- AI cut list integration (default implementations) ---

    def _has_description(self, fields: dict) -> bool:
        """
        Check if the user provided a meaningful design description.
        Returns True if combined description + notes exceeds 10 words.
        """
        description = str(fields.get("description", "") or "")
        notes = str(fields.get("notes", "") or "")
        photo_obs = str(fields.get("photo_observations", "") or "")
        combined = (description + " " + notes + " " + photo_obs).strip()
        print(f"BASE_HAS_DESC DEBUG: combined = '{combined[:100]}', word_count = {len(combined.split())}")
        return len(combined.split()) > 10

    def _try_ai_cut_list(self, job_type: str, fields: dict):
        """
        Try to generate an AI cut list from the user's description.
        Returns list of cut dicts or None on failure.
        """
        try:
            from .ai_cut_list import AICutListGenerator
            generator = AICutListGenerator()
            return generator.generate_cut_list(job_type, fields)
        except Exception as e:
            logger.warning("AI cut list failed for %s: %s", job_type, e)
            return None

    def _build_from_ai_cuts(self, job_type: str, ai_cuts: list,
                            fields: dict, assumptions: list,
                            hardware: list = None) -> dict:
        """
        Build a MaterialList from AI-generated cut items.
        Default implementation — subclasses can override for job-specific hardware.
        """
        from .material_lookup import MaterialLookup
        _lookup = MaterialLookup()

        items = []
        total_weight = 0.0
        total_weld_inches = 0.0

        for cut in ai_cuts:
            profile = cut.get("profile", "sq_tube_1.5x1.5_11ga")
            length_in = cut.get("length_inches", 12.0)
            quantity = cut.get("quantity", 1)
            price_ft = _lookup.get_price_per_foot(profile)
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
            total_weld_inches += quantity * 6  # Estimate 6" weld per piece

        # Estimate surface area from items
        total_length_ft = sum(
            self.inches_to_feet(c.get("length_inches", 12.0)) * c.get("quantity", 1)
            for c in ai_cuts
        )
        total_sq_ft = total_length_ft * 0.5  # Rough: 6" average width

        assumptions.append("Cut list generated by AI from project description.")

        return self.make_material_list(
            job_type=job_type,
            items=items,
            hardware=hardware or [],
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )
