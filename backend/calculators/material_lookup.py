"""
Material price lookup with fallback chain:
1. Seeded prices from data/seeded_prices.json (real supplier quotes)
2. DEFAULT_PRICES from this file (market averages)

Run `python data/seed_from_invoices.py` to generate seeded_prices.json
from raw invoice data in data/raw/.

All prices are per linear foot unless otherwise noted.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# --- Seeded prices (loaded from data/seeded_prices.json if it exists) ---
_SEEDED_PRICES = {}
_seeded_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "seeded_prices.json"
)
try:
    with open(_seeded_path) as _f:
        _SEEDED_PRICES = json.load(_f)
    logger.info("Loaded %d seeded material prices from %s", len(_SEEDED_PRICES), _seeded_path)
except (FileNotFoundError, json.JSONDecodeError):
    pass  # No seeded prices — use defaults

# FALLBACK PRICES — used when no seeded price exists for a profile
# Source: market averages as of Feb 2026
PRICE_PER_FOOT = {
    # Square tube
    "sq_tube_2x2_11ga": 3.50,
    "sq_tube_2x2_14ga": 2.75,
    "sq_tube_2x2_16ga": 2.25,
    "sq_tube_1.5x1.5_11ga": 2.75,
    "sq_tube_1.5x1.5_14ga": 2.25,
    "sq_tube_1.5x1.5_16ga": 1.85,
    "sq_tube_1x1_11ga": 1.75,
    "sq_tube_1x1_14ga": 1.50,
    "sq_tube_1x1_16ga": 1.25,
    "sq_tube_2.5x2.5_11ga": 4.50,
    "sq_tube_3x3_11ga": 5.50,
    "sq_tube_4x4_11ga": 7.50,
    # Rectangular tube
    "rect_tube_2x4_11ga": 5.50,
    "rect_tube_2x3_11ga": 4.50,
    "rect_tube_2x1_11ga": 2.50,
    # Round tube
    "round_tube_1.5_11ga": 4.65,   # DOM
    "round_tube_1.5_14ga": 3.50,
    "round_tube_1.25_14ga": 3.00,
    "round_tube_2_11ga": 5.50,
    # Square bar / pickets
    "sq_bar_0.75": 1.50,
    "sq_bar_0.625": 1.10,
    "sq_bar_0.5": 0.85,
    "sq_bar_1.0": 2.25,
    # Round bar
    "round_bar_0.5": 0.85,
    "round_bar_0.625": 1.10,
    "round_bar_0.75": 1.50,
    # Flat bar
    "flat_bar_1x0.25": 1.75,
    "flat_bar_1.5x0.25": 2.50,
    "flat_bar_1x0.1875": 1.40,
    "flat_bar_0.75x0.25": 1.35,
    "flat_bar_2x0.25": 3.40,
    # Angle iron
    "angle_1.5x1.5x0.125": 1.60,
    "angle_2x2x0.1875": 2.80,
    "angle_2x2x0.25": 3.50,
    # Channel
    "channel_6x8.2": 8.20,
    "channel_4x5.4": 5.40,
    # Pipe (posts)
    "pipe_4_sch40": 6.00,
    "pipe_6_sch40": 12.00,
    "pipe_3.5_sch40": 5.00,
    "pipe_3_sch40": 4.00,
}

# Prices per square foot
PRICE_PER_SQFT = {
    "expanded_metal_13ga": 1.40,    # ~$45/sheet for 4x8
    "expanded_metal_16ga": 1.10,
    "expanded_metal_10ga": 1.90,
    "sheet_11ga": 2.65,             # ~$85/sheet for 4x8
    "sheet_14ga": 2.03,             # ~$65/sheet for 4x8
    "sheet_16ga": 1.56,             # ~$50/sheet for 4x8
}

# Per-unit prices for misc items
PRICE_PER_UNIT = {
    "concrete_per_cuyd": 175.00,
    "post_cap_4x4": 8.00,
    "post_cap_6x6": 12.00,
}


# Hardware price stubs — Session 5 replaces with real sourcing
# These match the HardwareItem + PricingOption schema from CLAUDE.md
HARDWARE_CATALOG = {
    # Hinges
    "heavy_duty_weld_hinge_pair": {
        "category": "hinge",
        "options": [
            {"supplier": "McMaster-Carr", "price": 125.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 95.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 140.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "standard_weld_hinge_pair": {
        "category": "hinge",
        "options": [
            {"supplier": "McMaster-Carr", "price": 60.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 45.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 65.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "ball_bearing_hinge_pair": {
        "category": "hinge",
        "options": [
            {"supplier": "McMaster-Carr", "price": 150.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 120.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 165.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    # Latches
    "gravity_latch": {
        "category": "latch",
        "options": [
            {"supplier": "McMaster-Carr", "price": 35.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 28.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 40.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "magnetic_latch": {
        "category": "latch",
        "options": [
            {"supplier": "McMaster-Carr", "price": 50.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 38.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 55.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "keyed_deadbolt": {
        "category": "latch",
        "options": [
            {"supplier": "McMaster-Carr", "price": 65.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 50.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 75.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "pool_code_latch": {
        "category": "latch",
        "options": [
            {"supplier": "McMaster-Carr", "price": 85.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 70.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 90.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "electric_strike": {
        "category": "latch",
        "options": [
            {"supplier": "McMaster-Carr", "price": 120.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 95.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 135.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    # Gate operators
    "liftmaster_la412": {
        "category": "operator",
        "options": [
            {"supplier": "LiftMaster Dealer", "price": 1350.00, "url": "", "part_number": "LA412", "lead_days": 5},
            {"supplier": "Amazon", "price": 1450.00, "url": "", "part_number": None, "lead_days": 7},
            {"supplier": "Gate Depot", "price": 1295.00, "url": "", "part_number": "LA412", "lead_days": 4},
        ],
    },
    "us_automatic_patriot": {
        "category": "operator",
        "options": [
            {"supplier": "US Automatic Dealer", "price": 950.00, "url": "", "part_number": "Patriot", "lead_days": 5},
            {"supplier": "Amazon", "price": 1050.00, "url": "", "part_number": None, "lead_days": 7},
            {"supplier": "Gate Depot", "price": 895.00, "url": "", "part_number": None, "lead_days": 4},
        ],
    },
    "liftmaster_rsw12u": {
        "category": "operator",
        "options": [
            {"supplier": "LiftMaster Dealer", "price": 1100.00, "url": "", "part_number": "RSW12U", "lead_days": 5},
            {"supplier": "Amazon", "price": 1200.00, "url": "", "part_number": None, "lead_days": 7},
            {"supplier": "Gate Depot", "price": 1050.00, "url": "", "part_number": "RSW12U", "lead_days": 4},
        ],
    },
    "liftmaster_csw24u": {
        "category": "operator",
        "options": [
            {"supplier": "LiftMaster Dealer", "price": 1800.00, "url": "", "part_number": "CSW24U", "lead_days": 5},
            {"supplier": "Amazon", "price": 1950.00, "url": "", "part_number": None, "lead_days": 7},
            {"supplier": "Gate Depot", "price": 1750.00, "url": "", "part_number": "CSW24U", "lead_days": 4},
        ],
    },
    # Roller carriages (cantilever)
    "roller_carriage_standard": {
        "category": "roller_carriage",
        "options": [
            {"supplier": "McMaster-Carr", "price": 195.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 165.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 220.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "roller_carriage_heavy": {
        "category": "roller_carriage",
        "options": [
            {"supplier": "McMaster-Carr", "price": 325.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 280.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 370.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    # Gate stops/bumpers
    "gate_stop": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 15.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 12.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 18.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    # Railing hardware
    "surface_mount_flange": {
        "category": "railing_mount",
        "options": [
            {"supplier": "McMaster-Carr", "price": 18.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 14.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 22.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "cable_tensioner": {
        "category": "railing_hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 22.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 18.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "CableRail", "price": 25.00, "url": "", "part_number": None, "lead_days": 7},
        ],
    },
    "cable_end_fitting": {
        "category": "railing_hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 8.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 6.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "CableRail", "price": 10.00, "url": "", "part_number": None, "lead_days": 7},
        ],
    },
    # Auto-close
    "spring_hinge_pair": {
        "category": "hinge",
        "options": [
            {"supplier": "McMaster-Carr", "price": 75.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 55.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 80.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "hydraulic_closer": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 185.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 150.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 200.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    # Cane bolt / drop rod
    "cane_bolt": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 35.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 25.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 40.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "surface_drop_rod": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 45.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 35.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 50.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
    "flush_bolt": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 55.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 42.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 60.00, "url": "", "part_number": None, "lead_days": 2},
        ],
    },
}


class MaterialLookup:
    """
    Looks up material prices.
    Priority: 1) Seeded prices from data/seeded_prices.json (real supplier quotes)
              2) DEFAULT PRICES in this file (market averages)

    This class wraps the lookup so calculators don't need to know the source.
    """

    def get_price_per_foot(self, profile: str) -> float:
        """
        Returns price per linear foot for tube/bar profiles.
        Checks seeded prices first, falls back to hardcoded defaults.
        Falls back to 0.0 if profile not found anywhere.
        """
        seeded = _SEEDED_PRICES.get(profile)
        if seeded:
            return seeded["price_per_foot"]
        return PRICE_PER_FOOT.get(profile, 0.0)

    def get_price_with_source(self, profile: str) -> tuple:
        """
        Returns (price, source_label) for a profile.
        source_label is the supplier name (e.g. "Osorio", "Wexler")
        or "market_average" if using hardcoded defaults.
        """
        seeded = _SEEDED_PRICES.get(profile)
        if seeded:
            return (seeded["price_per_foot"], seeded.get("supplier", "seeded"))
        price = PRICE_PER_FOOT.get(profile, 0.0)
        return (price, "market_average")

    def get_price_per_sqft(self, sheet_type: str) -> float:
        """
        Returns price per square foot for sheet/plate.
        Falls back to 0.0 if not found.
        """
        return PRICE_PER_SQFT.get(sheet_type, 0.0)

    def get_unit_price(self, item_key: str) -> float:
        """Returns per-unit price for misc items (concrete, post caps, etc.)."""
        return PRICE_PER_UNIT.get(item_key, 0.0)

    def get_hardware_options(self, hardware_key: str) -> list:
        """
        Returns list of PricingOption dicts for a hardware item.
        """
        entry = HARDWARE_CATALOG.get(hardware_key)
        if not entry:
            return [
                {"supplier": "Estimated", "price": 50.00, "url": "",
                 "part_number": None, "lead_days": None},
            ]
        return entry["options"]

    def get_hardware_category(self, hardware_key: str) -> str:
        """Returns the category for a hardware key."""
        entry = HARDWARE_CATALOG.get(hardware_key)
        return entry["category"] if entry else "hardware"

    @staticmethod
    def has_seeded_prices() -> bool:
        """Returns True if seeded prices are loaded."""
        return len(_SEEDED_PRICES) > 0

    @staticmethod
    def seeded_price_count() -> int:
        """Returns the number of seeded profile prices loaded."""
        return len(_SEEDED_PRICES)
