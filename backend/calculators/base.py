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

    def _apply_hardware_fallback(self, job_type, fields, hardware):
        """
        If hardware list is empty, try the hardware mapper for common items.
        Calculators that already populate hardware (swing_gate, cantilever_gate)
        pass non-empty lists so this never runs for them.
        """
        if hardware:
            return hardware
        try:
            from .hardware_mapper import map_hardware
            mapped = map_hardware(job_type, fields)
            return mapped if mapped else []
        except Exception as e:
            logger.warning("Hardware mapper fallback failed: %s", e)
            return []

    def make_material_list(self, job_type: str, items: list, hardware: list,
                           total_weight_lbs: float, total_sq_ft: float,
                           weld_linear_inches: float,
                           assumptions: list = None,
                           cut_list: list = None,
                           fields: dict = None) -> dict:
        """Build the MaterialList output dict matching the CLAUDE.md contract."""
        # Apply hardware fallback if hardware list is empty and fields provided
        if not hardware and fields is not None:
            hardware = self._apply_hardware_fallback(job_type, fields, hardware)
        result = {
            "job_type": job_type,
            "items": items,
            "hardware": hardware,
            "total_weight_lbs": round(total_weight_lbs, 1),
            "total_sq_ft": round(total_sq_ft, 1),
            "weld_linear_inches": round(weld_linear_inches, 1),
            "assumptions": assumptions or [],
        }
        if cut_list is not None:
            result["cut_list"] = cut_list
        return result

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

        Items are consolidated by profile — each profile appears once with total
        footage (what you buy from the supplier). The raw per-piece cut list is
        preserved separately as cut_list for the detailed cut list section.
        """
        from .material_lookup import MaterialLookup
        _lookup = MaterialLookup()

        total_weight = 0.0
        total_weld_inches = 0.0

        # Build per-piece cut list and aggregate footage by profile
        cut_list_items = []
        profile_totals = {}  # profile -> {total_ft, material_type, price_ft}

        for cut in ai_cuts:
            profile = cut.get("profile", "sq_tube_1.5x1.5_11ga")
            length_in = cut.get("length_inches", 12.0)
            quantity = cut.get("quantity", 1)
            length_ft = self.inches_to_feet(length_in)
            piece_total_ft = length_ft * quantity

            # Per-piece entry for the cut list
            cut_entry = {
                "description": cut.get("description", "Cut piece"),
                "piece_name": cut.get("piece_name", ""),
                "group": cut.get("group", "general"),
                "material_type": cut.get("material_type", "mild_steel"),
                "profile": profile,
                "length_inches": length_in,
                "quantity": quantity,
                "cut_type": cut.get("cut_type", "square"),
                "cut_angle": cut.get("cut_angle", 90.0),
                "weld_process": cut.get("weld_process", "mig"),
                "weld_type": cut.get("weld_type", "fillet"),
                "notes": cut.get("notes", ""),
            }
            # Sheet/plate fields — pass through from Opus
            if cut.get("width_inches"):
                cut_entry["width_inches"] = cut["width_inches"]
            if cut.get("sheet_stock_size"):
                cut_entry["sheet_stock_size"] = cut["sheet_stock_size"]
            if cut.get("sheets_needed"):
                cut_entry["sheets_needed"] = cut["sheets_needed"]
            if cut.get("seaming_required"):
                cut_entry["seaming_required"] = cut["seaming_required"]
            cut_list_items.append(cut_entry)

            # Accumulate footage by profile
            is_sheet = "sheet" in profile.lower() or "plate" in profile.lower()
            if profile not in profile_totals:
                if is_sheet:
                    price_ft = _lookup.get_price_per_sqft(profile)
                else:
                    price_ft = _lookup.get_price_per_foot(profile)
                if price_ft == 0.0:
                    price_ft = 3.50
                profile_totals[profile] = {
                    "total_ft": 0.0,
                    "material_type": cut.get("material_type", "mild_steel"),
                    "price_ft": price_ft,
                    "is_sheet": is_sheet,
                    "sheet_stock_size": None,
                    "sheets_needed": 0,
                    "seaming_required": False,
                }
            profile_totals[profile]["total_ft"] += piece_total_ft

            # Accumulate sheet data from Opus — keep the LARGEST sheet size
            if is_sheet:
                new_size = cut.get("sheet_stock_size")
                if new_size:
                    existing = profile_totals[profile]["sheet_stock_size"]
                    if not existing or (new_size[0] * new_size[1]) > (existing[0] * existing[1]):
                        profile_totals[profile]["sheet_stock_size"] = new_size
                profile_totals[profile]["sheets_needed"] += cut.get("sheets_needed", 0) * quantity
                if cut.get("seaming_required"):
                    profile_totals[profile]["seaming_required"] = True

            total_weld_inches += quantity * 6  # Estimate 6" weld per piece

        # Build consolidated material items (what you buy from the supplier)
        items = []
        for profile, info in profile_totals.items():
            raw_ft = info["total_ft"]
            is_sheet = info.get("is_sheet", False)

            if is_sheet and info["sheets_needed"] > 0:
                # Sheet pricing: use Opus's sheet count × sheet area × price/sqft
                stock = info["sheet_stock_size"]
                if stock:
                    sheet_sqft = (stock[0] * stock[1]) / 144.0
                else:
                    sheet_sqft = 32.0  # fallback 4x8
                line_total = round(info["sheets_needed"] * sheet_sqft * info["price_ft"], 2)
                wasted_ft = raw_ft  # no separate waste for sheets
                waste_factor = 0.0
            else:
                wasted_ft = round(raw_ft * (1 + self.WASTE_TUBE), 1)
                line_total = round(wasted_ft * info["price_ft"], 2)
                waste_factor = self.WASTE_TUBE

            weight = self.get_weight_lbs(profile, wasted_ft)
            if weight == 0.0:
                weight = wasted_ft * 2.0
            total_weight += weight

            mat_item = self.make_material_item(
                description="%s — %.1f ft" % (profile, wasted_ft),
                material_type=info["material_type"],
                profile=profile,
                length_inches=round(wasted_ft * 12, 2),
                quantity=1,
                unit_price=line_total,
                cut_type="square",
                waste_factor=waste_factor,
            )
            # Attach sheet metadata for downstream (pricing_engine, PDF)
            if is_sheet:
                if info["sheet_stock_size"]:
                    mat_item["sheet_stock_size"] = info["sheet_stock_size"]
                if info["sheets_needed"] > 0:
                    mat_item["sheets_needed"] = info["sheets_needed"]
                if info["seaming_required"]:
                    mat_item["seaming_required"] = True
            items.append(mat_item)

        # Estimate surface area
        total_length_ft = sum(info["total_ft"] for info in profile_totals.values())
        total_sq_ft = total_length_ft * 0.5  # Rough: 6" average width

        # --- Laser cutting detection for sheet items ---
        description = str(fields.get("description", "") or "").lower()
        all_fields_text = " ".join(str(v) for v in fields.values()).lower()
        is_aluminum = any(k in all_fields_text for k in ("aluminum", "6061", "5052"))
        needs_laser = is_aluminum or "laser" in description or "cnc" in description

        if needs_laser:
            # Sum perimeter from sheet items using actual geometry
            sheet_perim_inches = 0.0
            for cut in ai_cuts:
                prof = cut.get("profile", "")
                if "sheet" in prof or "plate" in prof:
                    length_in = cut.get("length_inches", 0)
                    width_in = cut.get("width_inches", 0)
                    qty = cut.get("quantity", 1)
                    if width_in > 0:
                        # Real perimeter from Opus dimensions
                        sheet_perim_inches += 2 * (length_in + width_in) * qty
                    else:
                        # Fallback: assume square-ish piece
                        sheet_perim_inches += length_in * qty * 4

            if sheet_perim_inches > 0:
                laser_cost = max(round(sheet_perim_inches * 0.15, 2), 75.00)
                laser_online = round(laser_cost * 1.20, 2)
                if hardware is None:
                    hardware = []
                hardware.append(self.make_hardware_item(
                    description="Laser cutting service — %.0f\" perimeter" % sheet_perim_inches,
                    quantity=1,
                    options=[
                        self.make_pricing_option("Local laser shop", laser_cost),
                        self.make_pricing_option("SendCutSend", laser_online),
                    ],
                ))
                assumptions.append(
                    "Laser cutting estimated at $%.2f for %.0f\" of sheet perimeter."
                    % (laser_cost, sheet_perim_inches)
                )

        assumptions.append("Cut list generated by AI from project description.")
        assumptions.append(
            "Materials consolidated by profile — total footage includes %.0f%% waste factor."
            % (self.WASTE_TUBE * 100)
        )

        return self.make_material_list(
            job_type=job_type,
            items=items,
            hardware=hardware or [],
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
            cut_list=cut_list_items,
            fields=fields,
        )
