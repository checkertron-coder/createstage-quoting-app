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

# FALLBACK PRICES — Real Chicago-area pricing
# Source: Osorio Metals Supply + D. Wexler & Sons quotes (2024-2025)
# Buffer: +10% over Osorio baseline for market fluctuation
# Last updated: March 2026
PRICE_PER_FOOT = {
    # Square tube — Osorio + 10%
    "sq_tube_1x1_11ga": 1.27,      # Osorio $1.15/ft (Jan 2025)
    "sq_tube_1x1_14ga": 0.95,      # Estimated from 11ga ratio
    "sq_tube_1x1_16ga": 0.80,      # Estimated
    "sq_tube_1.25x1.25_11ga": 1.51, # Osorio $1.37/ft (Jan 2025)
    "sq_tube_1.5x1.5_11ga": 1.74,  # Osorio $1.58/ft (Oct 2024)
    "sq_tube_1.5x1.5_14ga": 1.22,  # Osorio $1.11/ft (Jan 2025)
    "sq_tube_1.5x1.5_16ga": 1.00,  # Estimated
    "sq_tube_1.75x1.75_11ga": 2.64, # Osorio $2.40/ft (Jan 2025)
    "sq_tube_2x2_11ga": 2.75,      # Osorio $2.49-2.88/ft (2024) +10%
    "sq_tube_2x2_14ga": 1.67,      # Osorio $1.52/ft (receipt)
    "sq_tube_2x2_16ga": 1.40,      # Estimated from 14ga ratio
    "sq_tube_2.5x2.5_11ga": 3.86,  # Osorio $3.51/ft (Nov 2023) +10%
    "sq_tube_3x3_11ga": 5.61,      # Osorio $5.10/ft (Feb 2025) +10%
    "sq_tube_3x3_7ga": 8.25,       # Osorio $7.50/ft (Feb 2025, 1/4" wall) +10%
    "sq_tube_4x4_11ga": 4.95,      # Extrapolated: ~5.41 lb/ft × $0.83/lb (Osorio avg)
    "sq_tube_6x6_7ga": 14.96,      # Osorio $13.60/ft (Jun 2024) +10%
    # Rectangular tube
    "rect_tube_2x4_11ga": 3.76,    # Wexler $3.42/ft (Jun 2024) +10%
    "rect_tube_2x3_11ga": 3.10,    # Estimated between 2x2 and 2x4
    "rect_tube_2x1_11ga": 2.00,    # Estimated
    # Round tube
    "round_tube_1.5_11ga": 5.07,   # Wexler $4.61/ft DOM (Jan 2025) +10%
    "round_tube_1.5_14ga": 3.85,   # Estimated
    "round_tube_1.25_14ga": 3.30,  # Estimated
    "round_tube_2_11ga": 6.05,     # Estimated
    # Square bar / pickets — extrapolated from tube $/lb ratios
    "sq_bar_0.5": 0.75,            # 0.85 lb/ft × $0.90/lb
    "sq_bar_0.625": 1.10,          # 1.33 lb/ft × $0.90/lb
    "sq_bar_0.75": 1.55,           # 1.91 lb/ft × $0.90/lb
    "sq_bar_1.0": 2.75,            # 3.40 lb/ft × $0.90/lb
    # Round bar
    "round_bar_0.5": 0.70,         # 0.67 lb/ft × $0.95/lb
    "round_bar_0.625": 1.00,       # 1.04 lb/ft × $0.95/lb
    "round_bar_0.75": 1.40,        # 1.50 lb/ft × $0.95/lb
    # Flat bar — Osorio + 10%
    "flat_bar_1x0.125": 0.90,      # Estimated
    "flat_bar_1x0.25": 1.41,       # Osorio $1.28/ft (Jan 2025) +10%
    "flat_bar_1.5x0.25": 1.66,     # Osorio $1.51/ft (Jan 2025) +10%
    "flat_bar_1x0.1875": 1.10,     # Estimated
    "flat_bar_0.75x0.25": 1.10,    # Estimated
    "flat_bar_2x0.25": 2.80,       # Estimated
    "flat_bar_3x0.25": 4.57,       # Osorio $4.15/ft (Nov 2023) +10%
    # Angle iron — Osorio + 10%
    "angle_1.5x1.5x0.125": 1.06,   # Osorio $0.96/ft (receipt) +10%
    "angle_2x2x0.125": 1.42,       # Osorio $1.29/ft (receipt) +10%
    "angle_2x2x0.1875": 2.02,      # Osorio $1.84/ft (Jan 2025) +10%
    "angle_2x2x0.25": 2.50,        # Estimated from 3/16" ratio
    "angle_3x3x0.1875": 2.61,      # Osorio $2.37/ft (Feb 2025) +10%
    # Channel
    "channel_6x8.2": 8.20,         # No supplier data — keep estimate
    "channel_4x5.4": 5.40,         # No supplier data — keep estimate
    # Pre-punched channel (fence mid-rails)
    "punched_channel_1x0.5_fits_0.5": 3.85,       # Estimated + 10%
    "punched_channel_1.5x0.5_fits_0.5": 4.95,     # Estimated + 10%
    "punched_channel_1.5x0.5_fits_0.625": 4.95,   # Estimated + 10%
    "punched_channel_1.5x0.5_fits_0.75": 4.95,    # Estimated + 10%
    "punched_channel_2x1_fits_0.75": 8.25,         # Estimated + 10%
    # Pipe (posts)
    "pipe_4_sch40": 6.60,          # No Osorio data — estimated + 10%
    "pipe_6_sch40": 13.20,         # No Osorio data — estimated + 10%
    "pipe_3.5_sch40": 5.50,
    "pipe_3_sch40": 4.40,
    # HSS (structural tube)
    "hss_4x4_0.25": 8.25,          # Extrapolated from 3×3×1/4 ($7.50) + size premium
    "hss_6x4_0.25": 12.00,         # No supplier data — keep estimate
    # Aluminum tube — 6061-T6, ~2-3x steel
    "al_sq_tube_1x1_0.125": 3.20,          # 1" sq tube, 1/8" wall
    "al_sq_tube_1.5x1.5_0.125": 4.50,      # 1.5" sq tube, 1/8" wall
    "al_sq_tube_2x2_0.125": 6.00,          # 2" sq tube, 1/8" wall
    "al_rect_tube_1x2_0.125": 4.80,        # 1x2 rect tube, 1/8" wall
    # Aluminum angle — 6061-T6
    "al_angle_1.5x1.5x0.125": 2.80,        # 1.5" angle, 1/8" leg
    "al_angle_2x2x0.125": 3.60,            # 2" angle, 1/8" leg
    # Aluminum flat bar — 6061-T6
    "al_flat_bar_1x0.125": 1.80,            # 1" wide, 1/8" thick
    "al_flat_bar_1.5x0.125": 2.40,          # 1.5" wide, 1/8" thick
    "al_flat_bar_2x0.25": 5.20,             # 2" wide, 1/4" thick
    # Aluminum round tube — 6061-T6
    "al_round_tube_1.5_0.125": 4.20,        # 1.5" OD, 1/8" wall
}

# Prices per square foot
PRICE_PER_SQFT = {
    "expanded_metal_13ga": 1.40,    # ~$45/sheet for 4x8
    "expanded_metal_16ga": 1.10,
    "expanded_metal_10ga": 1.90,
    "sheet_11ga": 2.65,             # ~$85/sheet for 4x8
    "sheet_14ga": 2.03,             # ~$65/sheet for 4x8
    "sheet_16ga": 1.56,             # ~$50/sheet for 4x8
    # Steel plate — A36 hot-rolled, priced per sqft from 4'x8' sheets
    # Source: Chicago-area service centers (2025-2026), mid-range + 10% buffer
    "plate_0.1875": 6.50,           # 3/16" plate — 7.65 lbs/sqft × $0.85/lb
    "plate_0.25": 9.00,             # 1/4" plate — 10.2 lbs/sqft × $0.88/lb (~$288/sheet)
    "plate_0.375": 11.50,           # 3/8" plate — 15.3 lbs/sqft × $0.75/lb (~$368/sheet)
    "plate_0.5": 14.50,             # 1/2" plate — 20.4 lbs/sqft × $0.71/lb (~$464/sheet)
    "plate_0.75": 21.00,            # 3/4" plate — 30.6 lbs/sqft × $0.69/lb (~$672/sheet)
    "plate_1.0": 27.50,             # 1" plate — 40.8 lbs/sqft × $0.67/lb (~$880/sheet)
    # Aluminum sheet — 5052-H32 / 6061-T6, standard 4'x8' or 4'x10'
    "al_sheet_0.040": 4.50,         # 0.040" (~18ga equiv)
    "al_sheet_0.063": 5.80,         # 0.063" (~16ga equiv)
    "al_sheet_0.080": 7.00,         # 0.080" (~14ga equiv)
    "al_sheet_0.125": 10.50,        # 1/8" sheet
    "al_sheet_0.190": 15.00,        # 3/16" plate
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
    # Anchor bolts
    "anchor_bolt_set": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 18.00, "url": "", "part_number": None, "lead_days": 3},
            {"supplier": "Amazon", "price": 12.00, "url": "", "part_number": None, "lead_days": 5},
            {"supplier": "Grainger", "price": 20.00, "url": "", "part_number": None, "lead_days": 2},
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

    def get_alternatives(self, profile):
        """
        Returns all profiles of the same shape family, sorted by price.
        Excludes the input profile itself.

        Returns: list of {"profile": str, "price": float, "description": str}
        """
        shape = self._extract_shape(profile)
        if not shape:
            return []

        alternatives = []
        # Scan all known profiles in PRICE_PER_FOOT + seeded
        all_profiles = set(PRICE_PER_FOOT.keys())
        all_profiles.update(_SEEDED_PRICES.keys())

        for p in all_profiles:
            if p == profile:
                continue
            if self._extract_shape(p) == shape:
                price = self.get_price_per_foot(p)
                if price > 0:
                    alternatives.append({
                        "profile": p,
                        "price": price,
                        "description": self._profile_to_description(p),
                    })

        alternatives.sort(key=lambda x: x["price"])
        return alternatives

    @staticmethod
    def _extract_shape(profile):
        """
        Extract the shape family from a profile key.
        e.g. 'sq_tube_2x2_11ga' -> 'sq_tube'
             'flat_bar_1x0.25' -> 'flat_bar'
             'round_tube_1.5_14ga' -> 'round_tube'
             'pipe_4_sch40' -> 'pipe'
        """
        if not profile:
            return ""
        # Known multi-word shape prefixes (order matters — longest first)
        prefixes = [
            "al_sq_tube", "al_rect_tube", "al_round_tube",
            "al_flat_bar", "al_angle", "al_sheet",
            "sq_tube", "rect_tube", "round_tube",
            "sq_bar", "round_bar", "flat_bar",
            "dom_tube", "angle", "channel", "pipe", "hss",
        ]
        for prefix in prefixes:
            if profile.startswith(prefix + "_") or profile == prefix:
                return prefix
        # Fallback: first segment before underscore
        parts = profile.split("_")
        return parts[0] if parts else ""

    @staticmethod
    def _profile_to_description(profile):
        """
        Convert a profile key to a human-readable description.
        e.g. 'sq_tube_2x2_11ga' -> '2x2 Square Tube 11ga'
             'flat_bar_1x0.25' -> '1x0.25 Flat Bar'
        """
        if not profile:
            return ""
        shape_names = {
            "al_sq_tube": "Aluminum Square Tube",
            "al_rect_tube": "Aluminum Rectangular Tube",
            "al_round_tube": "Aluminum Round Tube",
            "al_flat_bar": "Aluminum Flat Bar",
            "al_angle": "Aluminum Angle",
            "al_sheet": "Aluminum Sheet",
            "sq_tube": "Square Tube",
            "rect_tube": "Rectangular Tube",
            "round_tube": "Round Tube",
            "sq_bar": "Square Bar",
            "round_bar": "Round Bar",
            "flat_bar": "Flat Bar",
            "dom_tube": "DOM Tube",
            "angle": "Angle Iron",
            "channel": "Channel",
            "pipe": "Pipe",
            "hss": "HSS",
        }
        prefixes = [
            "al_sq_tube", "al_rect_tube", "al_round_tube",
            "al_flat_bar", "al_angle", "al_sheet",
            "sq_tube", "rect_tube", "round_tube",
            "sq_bar", "round_bar", "flat_bar",
            "dom_tube", "angle", "channel", "pipe", "hss",
        ]
        for prefix in prefixes:
            if profile.startswith(prefix + "_"):
                suffix = profile[len(prefix) + 1:]
                shape_label = shape_names.get(prefix, prefix.replace("_", " ").title())
                return "%s %s" % (suffix.replace("_", " "), shape_label)
        return profile.replace("_", " ").title()

    @staticmethod
    def has_seeded_prices() -> bool:
        """Returns True if seeded prices are loaded."""
        return len(_SEEDED_PRICES) > 0

    @staticmethod
    def seeded_price_count() -> int:
        """Returns the number of seeded profile prices loaded."""
        return len(_SEEDED_PRICES)
