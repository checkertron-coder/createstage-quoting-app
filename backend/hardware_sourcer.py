"""
Hardware Sourcer — prices hardware items and estimates consumables.

For each hardware item, produces 3 pricing options:
1. McMaster-Carr (catalog price — most expensive, most reliable)
2. Amazon (often cheaper, variable availability)
3. Third option (Grainger, Gate Depot, specialty supplier)

Also estimates consumable costs (welding wire, grinding discs, shielding gas)
from weld_linear_inches and total_sq_ft.

v2: Uses hardcoded catalog with realistic pricing.
Phase 3: McMaster-Carr eProcurement API + web search for live prices.
"""

import math
import urllib.parse

from .calculators.material_lookup import HARDWARE_CATALOG


# --- Upgraded hardware pricing catalog ---
# Prices reflect Feb 2026 catalog/street prices for the Chicago area.
# McMaster part numbers are real where known.

HARDWARE_PRICES = {
    # Gate hinges
    "heavy_duty_weld_hinge_pair": {
        "category": "hinge",
        "options": [
            {"supplier": "McMaster-Carr", "price": 145.00, "part_number": "1573A63",
             "url": "https://www.mcmaster.com/1573A63", "lead_days": 3},
            {"supplier": "Amazon", "price": 89.99, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 125.00, "part_number": "5RRN2",
             "url": "", "lead_days": 2},
        ],
    },
    "standard_weld_hinge_pair": {
        "category": "hinge",
        "options": [
            {"supplier": "McMaster-Carr", "price": 72.00, "part_number": "1573A52",
             "url": "https://www.mcmaster.com/1573A52", "lead_days": 3},
            {"supplier": "Amazon", "price": 45.99, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 62.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "ball_bearing_hinge_pair": {
        "category": "hinge",
        "options": [
            {"supplier": "McMaster-Carr", "price": 165.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 120.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 155.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "spring_hinge_pair": {
        "category": "hinge",
        "options": [
            {"supplier": "McMaster-Carr", "price": 78.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 55.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 72.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    # Latches
    "gravity_latch": {
        "category": "latch",
        "options": [
            {"supplier": "McMaster-Carr", "price": 48.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 28.99, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 38.50, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "magnetic_latch": {
        "category": "latch",
        "options": [
            {"supplier": "McMaster-Carr", "price": 65.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 42.99, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 55.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "keyed_deadbolt": {
        "category": "latch",
        "options": [
            {"supplier": "McMaster-Carr", "price": 89.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 55.99, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 72.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "pool_code_latch": {
        "category": "latch",
        "options": [
            {"supplier": "McMaster-Carr", "price": 95.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 72.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 88.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "electric_strike": {
        "category": "latch",
        "options": [
            {"supplier": "McMaster-Carr", "price": 135.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 95.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 125.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    # Gate operators — McMaster doesn't sell these
    "liftmaster_la412": {
        "category": "operator",
        "options": [
            {"supplier": "LiftMaster Dealer", "price": 1350.00, "part_number": "LA412",
             "url": "", "lead_days": 5},
            {"supplier": "Amazon", "price": 1450.00, "part_number": "LA412",
             "url": "", "lead_days": 7},
            {"supplier": "Gate Depot", "price": 1249.00, "part_number": "LA412",
             "url": "", "lead_days": 4},
        ],
    },
    "us_automatic_patriot": {
        "category": "operator",
        "options": [
            {"supplier": "US Automatic Dealer", "price": 950.00, "part_number": "Patriot",
             "url": "", "lead_days": 5},
            {"supplier": "Amazon", "price": 975.00, "part_number": None,
             "url": "", "lead_days": 7},
            {"supplier": "Gate Depot", "price": 899.00, "part_number": None,
             "url": "", "lead_days": 4},
        ],
    },
    "liftmaster_rsw12u": {
        "category": "operator",
        "options": [
            {"supplier": "LiftMaster Dealer", "price": 1100.00, "part_number": "RSW12U",
             "url": "", "lead_days": 5},
            {"supplier": "Amazon", "price": 1200.00, "part_number": None,
             "url": "", "lead_days": 7},
            {"supplier": "Gate Depot", "price": 1050.00, "part_number": "RSW12U",
             "url": "", "lead_days": 4},
        ],
    },
    "liftmaster_csw24u": {
        "category": "operator",
        "options": [
            {"supplier": "LiftMaster Dealer", "price": 1800.00, "part_number": "CSW24U",
             "url": "", "lead_days": 5},
            {"supplier": "Amazon", "price": 1950.00, "part_number": None,
             "url": "", "lead_days": 7},
            {"supplier": "Gate Depot", "price": 1750.00, "part_number": "CSW24U",
             "url": "", "lead_days": 4},
        ],
    },
    # Roller carriages
    "roller_carriage_standard": {
        "category": "roller_carriage",
        "options": [
            {"supplier": "McMaster-Carr", "price": 225.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 165.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 195.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "roller_carriage_heavy": {
        "category": "roller_carriage",
        "options": [
            {"supplier": "McMaster-Carr", "price": 385.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 275.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 340.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    # Gate stops
    "gate_stop": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 18.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 12.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 16.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    # Railing hardware
    "surface_mount_flange": {
        "category": "railing_mount",
        "options": [
            {"supplier": "McMaster-Carr", "price": 22.50, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 14.99, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 18.75, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "cable_tensioner": {
        "category": "railing_hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 28.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 18.99, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "CableRail", "price": 24.00, "part_number": None,
             "url": "", "lead_days": 7},
        ],
    },
    "cable_end_fitting": {
        "category": "railing_hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 12.50, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 8.99, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "CableRail", "price": 10.50, "part_number": None,
             "url": "", "lead_days": 7},
        ],
    },
    # Auto-close / center stop
    "hydraulic_closer": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 195.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 150.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 185.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "cane_bolt": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 38.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 25.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 35.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "surface_drop_rod": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 48.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 35.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 45.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
    "flush_bolt": {
        "category": "hardware",
        "options": [
            {"supplier": "McMaster-Carr", "price": 58.00, "part_number": None,
             "url": "", "lead_days": 3},
            {"supplier": "Amazon", "price": 42.00, "part_number": None,
             "url": "", "lead_days": 5},
            {"supplier": "Grainger", "price": 55.00, "part_number": None,
             "url": "", "lead_days": 2},
        ],
    },
}

# --- Consumables ---
# Estimated per job from weld_linear_inches and total_sq_ft
CONSUMABLES = {
    "welding_wire_er70s6": {
        "description": "ER70S-6 welding wire",
        "price_per_lb": 3.50,
        "usage_per_100_weld_inches": 0.5,  # lbs per 100 weld inches
    },
    "grinding_disc_4.5": {
        "description": "4.5\" grinding disc",
        "price_each": 4.50,
        "usage_per_100_weld_inches": 1.0,  # discs per 100 weld inches
    },
    "flap_disc_4.5": {
        "description": "4.5\" flap disc",
        "price_each": 6.50,
        "usage_per_100_weld_inches": 0.5,
    },
    "shielding_gas_75_25": {
        "description": "75/25 Ar/CO2 shielding gas",
        "price_per_cu_ft": 0.08,
        "usage_cu_ft_per_weld_hour": 25.0,  # cu ft/hr at ~10 in/hr welding
    },
    "clearcoat_spray": {
        "description": "Clear coat spray",
        "price_per_can": 12.50,
        "coverage_sq_ft": 25.0,
    },
    "primer_spray": {
        "description": "Primer spray",
        "price_per_can": 8.50,
        "coverage_sq_ft": 20.0,
    },
}


class HardwareSourcer:
    """
    Prices hardware items and estimates consumables.

    For v2, uses the hardcoded catalog above.
    Future: database-backed prices, McMaster eProcurement API, web search.
    """

    def price_hardware_list(self, hardware_items: list, quantity_multiplier: int = 1) -> list:
        """
        Takes hardware items from MaterialList and returns them with full pricing.

        Args:
            hardware_items: list of HardwareItem dicts from Stage 3
            quantity_multiplier: for batch jobs (e.g., 10 identical gates)

        Returns:
            list of HardwareItem dicts with upgraded pricing options
        """
        priced = []
        for item in hardware_items:
            upgraded = dict(item)
            desc = item.get("description", "").lower()

            # Try to match to a catalog key
            matched_key = self._match_catalog_key(desc, item)
            if matched_key and matched_key in HARDWARE_PRICES:
                upgraded["options"] = [dict(o) for o in HARDWARE_PRICES[matched_key]["options"]]
            else:
                # Deep-copy options so we don't mutate originals
                upgraded["options"] = [dict(o) for o in upgraded.get("options", [])]

            # Fill empty URLs with McMaster search links
            self._fill_missing_urls(upgraded)

            if quantity_multiplier > 1:
                upgraded["quantity"] = item.get("quantity", 1) * quantity_multiplier

            priced.append(upgraded)

        return priced

    @staticmethod
    def _fill_missing_urls(item: dict):
        """Fill empty URL fields with McMaster search URLs based on item description."""
        desc = item.get("description", "hardware")
        for option in item.get("options", []):
            if option.get("url"):
                continue
            supplier = option.get("supplier", "").lower()
            if "mcmaster" in supplier:
                search_term = urllib.parse.quote_plus(desc)
                option["url"] = "https://www.mcmaster.com/%s" % search_term
            elif "amazon" in supplier:
                search_term = urllib.parse.quote_plus(desc)
                option["url"] = "https://www.amazon.com/s?k=%s" % search_term
            elif "grainger" in supplier:
                search_term = urllib.parse.quote_plus(desc)
                option["url"] = "https://www.grainger.com/search?searchQuery=%s" % search_term
            elif "gate depot" in supplier:
                search_term = urllib.parse.quote_plus(desc)
                option["url"] = "https://www.gatedepot.com/search?q=%s" % search_term

    def estimate_consumables(self, weld_linear_inches: float, total_sq_ft: float,
                             finish_type: str = "raw") -> list:
        """
        Estimate consumable costs from weld inches and square footage.
        Returns list of consumable line items.
        """
        items = []
        weld_hundreds = weld_linear_inches / 100.0

        # Welding wire
        wire = CONSUMABLES["welding_wire_er70s6"]
        wire_lbs = math.ceil(weld_hundreds * wire["usage_per_100_weld_inches"])
        if wire_lbs > 0:
            items.append({
                "description": f"{wire['description']} ({wire_lbs} lbs)",
                "quantity": wire_lbs,
                "unit_price": wire["price_per_lb"],
                "line_total": round(wire_lbs * wire["price_per_lb"], 2),
                "category": "consumable",
            })

        # Grinding discs
        grind = CONSUMABLES["grinding_disc_4.5"]
        disc_count = math.ceil(weld_hundreds * grind["usage_per_100_weld_inches"])
        if disc_count > 0:
            items.append({
                "description": f"{grind['description']} x{disc_count}",
                "quantity": disc_count,
                "unit_price": grind["price_each"],
                "line_total": round(disc_count * grind["price_each"], 2),
                "category": "consumable",
            })

        # Flap discs
        flap = CONSUMABLES["flap_disc_4.5"]
        flap_count = math.ceil(weld_hundreds * flap["usage_per_100_weld_inches"])
        if flap_count > 0:
            items.append({
                "description": f"{flap['description']} x{flap_count}",
                "quantity": flap_count,
                "unit_price": flap["price_each"],
                "line_total": round(flap_count * flap["price_each"], 2),
                "category": "consumable",
            })

        # Shielding gas
        gas = CONSUMABLES["shielding_gas_75_25"]
        weld_hours = weld_linear_inches / 10.0  # ~10 in/hr
        gas_cu_ft = math.ceil(weld_hours * gas["usage_cu_ft_per_weld_hour"])
        if gas_cu_ft > 0:
            items.append({
                "description": f"{gas['description']} ({gas_cu_ft} cu ft)",
                "quantity": gas_cu_ft,
                "unit_price": gas["price_per_cu_ft"],
                "line_total": round(gas_cu_ft * gas["price_per_cu_ft"], 2),
                "category": "consumable",
            })

        # Finish consumables
        finish = str(finish_type).lower()
        if "clear" in finish:
            cc = CONSUMABLES["clearcoat_spray"]
            cans = math.ceil(total_sq_ft / cc["coverage_sq_ft"])
            if cans > 0:
                items.append({
                    "description": f"{cc['description']} x{cans}",
                    "quantity": cans,
                    "unit_price": cc["price_per_can"],
                    "line_total": round(cans * cc["price_per_can"], 2),
                    "category": "consumable",
                })
        elif "paint" in finish and "powder" not in finish:
            pr = CONSUMABLES["primer_spray"]
            primer_cans = math.ceil(total_sq_ft / pr["coverage_sq_ft"])
            if primer_cans > 0:
                items.append({
                    "description": f"{pr['description']} x{primer_cans}",
                    "quantity": primer_cans,
                    "unit_price": pr["price_per_can"],
                    "line_total": round(primer_cans * pr["price_per_can"], 2),
                    "category": "consumable",
                })

        return items

    def get_pricing_options(self, item_key: str) -> list:
        """
        Returns 3 PricingOption dicts for a hardware item.
        Priority: upgraded catalog → Session 3 stubs → generic estimate.
        """
        if item_key in HARDWARE_PRICES:
            options = [dict(o) for o in HARDWARE_PRICES[item_key]["options"]]
        elif item_key in HARDWARE_CATALOG:
            options = [dict(o) for o in HARDWARE_CATALOG[item_key]["options"]]
        else:
            search_term = urllib.parse.quote_plus(item_key.replace("_", " "))
            options = [
                {"supplier": "McMaster-Carr", "price": 50.00, "part_number": None,
                 "url": "https://www.mcmaster.com/%s" % search_term, "lead_days": 3},
            ]

        # Fill missing URLs
        desc = item_key.replace("_", " ")
        for option in options:
            if not option.get("url"):
                supplier = option.get("supplier", "").lower()
                search = urllib.parse.quote_plus(desc)
                if "mcmaster" in supplier:
                    option["url"] = "https://www.mcmaster.com/%s" % search
                elif "amazon" in supplier:
                    option["url"] = "https://www.amazon.com/s?k=%s" % search
                elif "grainger" in supplier:
                    option["url"] = "https://www.grainger.com/search?searchQuery=%s" % search

        return options

    def suggest_bulk_discount(self, total_hardware_cost: float) -> dict:
        """
        If total hardware cost > $500, suggest bulk ordering.
        If total hardware cost > $2000, suggest direct supplier contact.
        """
        if total_hardware_cost > 2000:
            return {
                "suggestion": (
                    f"Hardware total is ${total_hardware_cost:,.2f} — "
                    f"contact suppliers directly for bulk pricing. "
                    f"Potential savings: 10-20%."
                ),
                "threshold": "high",
            }
        if total_hardware_cost > 500:
            return {
                "suggestion": (
                    f"Hardware total is ${total_hardware_cost:,.2f} — "
                    f"consider consolidating orders for volume discounts. "
                    f"Potential savings: 5-10%."
                ),
                "threshold": "medium",
            }
        return {}

    def flag_mcmaster_only(self, hardware_items: list) -> list:
        """
        Returns list of items where McMaster-Carr is the ONLY source with a price.
        These are candidates for manual sourcing to find cheaper alternatives.
        """
        flagged = []
        for item in hardware_items:
            options = item.get("options", [])
            priced_options = [o for o in options if o.get("price") is not None]
            if len(priced_options) == 1 and priced_options[0].get("supplier") == "McMaster-Carr":
                flagged.append(item.get("description", "Unknown item"))
        return flagged

    def select_cheapest_option(self, hardware_item: dict) -> tuple:
        """
        Returns (price, supplier_name) for the cheapest available option.
        If no valid price found, returns (0.0, "NO PRICE FOUND").
        """
        options = hardware_item.get("options", [])
        valid = [
            (o["price"], o.get("supplier", "Unknown"))
            for o in options
            if o.get("price") is not None
        ]
        if not valid:
            return (0.0, "NO PRICE FOUND")
        return min(valid, key=lambda x: x[0])

    def _match_catalog_key(self, description: str, item: dict) -> str:
        """Match a hardware item description to a catalog key."""
        desc = description.lower()

        # Gate operators
        if "la412" in desc or ("liftmaster" in desc and "operator" in desc):
            return "liftmaster_la412"
        if "patriot" in desc or "us automatic" in desc:
            return "us_automatic_patriot"
        if "rsw12u" in desc:
            return "liftmaster_rsw12u"
        if "csw24u" in desc:
            return "liftmaster_csw24u"

        # Roller carriages
        if "roller" in desc and "carriage" in desc:
            if "heavy" in desc:
                return "roller_carriage_heavy"
            return "roller_carriage_standard"

        # Hinges
        if "hinge" in desc:
            if "spring" in desc:
                return "spring_hinge_pair"
            if "ball bearing" in desc:
                return "ball_bearing_hinge_pair"
            if "heavy" in desc:
                return "heavy_duty_weld_hinge_pair"
            return "standard_weld_hinge_pair"

        # Latches
        if "gravity" in desc and "latch" in desc:
            return "gravity_latch"
        if "magnetic" in desc and "latch" in desc:
            return "magnetic_latch"
        if "deadbolt" in desc or "keyed" in desc:
            return "keyed_deadbolt"
        if "pool" in desc and "latch" in desc:
            return "pool_code_latch"
        if "electric" in desc and "strike" in desc:
            return "electric_strike"

        # Auto-close
        if "hydraulic" in desc and "closer" in desc:
            return "hydraulic_closer"

        # Center stop hardware
        if "cane bolt" in desc:
            return "cane_bolt"
        if "drop rod" in desc:
            return "surface_drop_rod"
        if "flush bolt" in desc:
            return "flush_bolt"

        # Gate stops
        if "stop" in desc or "bumper" in desc:
            return "gate_stop"

        # Railing
        if "flange" in desc or "surface mount" in desc:
            return "surface_mount_flange"
        if "tensioner" in desc:
            return "cable_tensioner"
        if "end fitting" in desc:
            return "cable_end_fitting"

        return ""
