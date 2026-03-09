"""
Stage 5 — Pricing Engine.

Combines all upstream pipeline outputs into a PricedQuote.
Pure math — no AI. Quantity × price, hours × rate, subtotal × markup.

Input: MaterialList + LaborEstimate + FinishingSection + hardware pricing
Output: PricedQuote (per CLAUDE.md contract)
"""

from datetime import datetime

from .claude_client import get_model_name
from .hardware_sourcer import HardwareSourcer


class PricingEngine:
    """
    Stage 5 of the pipeline.
    Assembles the final PricedQuote from all upstream outputs.
    """

    MARKUP_OPTIONS = [0, 5, 10, 15, 20, 25, 30]
    BULK_MATERIAL_THRESHOLD = 5000.00

    def __init__(self):
        self.hardware_sourcer = HardwareSourcer()

    def build_priced_quote(self, session_data: dict, user: dict) -> dict:
        """
        Assembles the final PricedQuote from all pipeline outputs.

        Args:
            session_data: {
                "session_id": str,
                "job_type": str,
                "fields": dict,          # answered fields from Stage 2
                "material_list": dict,    # MaterialList from Stage 3
                "labor_estimate": dict,   # LaborEstimate from Stage 4
                "finishing": dict,        # FinishingSection from Stage 4
            }
            user: dict with user profile fields (shop_name, markup_default, etc.)

        Returns:
            PricedQuote dict matching CLAUDE.md contract
        """
        material_list = session_data.get("material_list", {})
        labor_estimate = session_data.get("labor_estimate", {})
        finishing = session_data.get("finishing", {})
        fields = session_data.get("fields", {})
        job_type = session_data.get("job_type", "custom_fab")
        job_description = fields.get("description", "")

        # --- Price hardware ---
        raw_hardware = material_list.get("hardware", [])
        priced_hardware = self.hardware_sourcer.price_hardware_list(raw_hardware)

        # --- Estimate consumables ---
        weld_inches = material_list.get("weld_linear_inches", 0)
        total_sq_ft = material_list.get("total_sq_ft", 0)
        finish_type = fields.get("finish", "raw")

        # Detect material type from description for correct consumables
        desc_lower = str(job_description).lower()
        if any(k in desc_lower for k in ("aluminum", "6061", "5052")):
            detected_material = "aluminum_6061"
        elif any(k in desc_lower for k in ("stainless", "304", "316")):
            detected_material = "stainless_304"
        else:
            detected_material = "mild_steel"

        consumables = self.hardware_sourcer.estimate_consumables(
            weld_inches, total_sq_ft, finish_type,
            material_type=detected_material,
        )

        # --- Calculate subtotals ---
        materials = material_list.get("items", [])
        labor_processes = labor_estimate.get("processes", [])

        material_subtotal = self._calculate_material_subtotal(materials)
        hardware_subtotal = self._calculate_hardware_subtotal(priced_hardware)
        consumable_subtotal = self._calculate_consumable_subtotal(consumables)
        labor_subtotal = self._calculate_labor_subtotal(labor_processes)
        finishing_subtotal = self._calculate_finishing_subtotal(finishing)

        subtotal = round(
            material_subtotal + hardware_subtotal + consumable_subtotal +
            labor_subtotal + finishing_subtotal,
            2,
        )

        # --- Markup options ---
        markup_default = user.get("markup_default", 15)
        markup_options = self._build_markup_options(subtotal)

        # --- Assumptions and exclusions ---
        assumptions = self._build_assumptions(session_data, consumables)
        exclusions = self._build_exclusions(session_data)

        # --- Bulk discount note ---
        bulk_note = self._check_bulk_discount(material_subtotal)
        if bulk_note:
            assumptions.append(bulk_note)

        # --- Hardware sourcing notes ---
        hw_bulk = self.hardware_sourcer.suggest_bulk_discount(hardware_subtotal)
        if hw_bulk:
            assumptions.append(hw_bulk["suggestion"])

        mcmaster_only = self.hardware_sourcer.flag_mcmaster_only(priced_hardware)
        if mcmaster_only:
            assumptions.append(
                f"McMaster-Carr only source for: {', '.join(mcmaster_only)}. "
                f"Consider sourcing alternatives for cost savings."
            )

        # --- Enrich materials with stock length info ---
        try:
            from .knowledge.materials import get_stock_length
            for item in materials:
                profile = item.get("profile", "")
                mat_type = item.get("material_type", "")
                # Skip non-steel materials (concrete, etc.) from stock order
                if mat_type in ("concrete", "other") or profile.startswith("concrete"):
                    continue
                sl = get_stock_length(profile)
                if sl is not None:
                    item["stock_length_ft"] = sl
        except Exception:
            pass  # non-critical enrichment

        # --- Optional AI sections ---
        detailed_cut_list = session_data.get("detailed_cut_list", [])
        build_instructions = session_data.get("build_instructions", [])

        result = {
            "quote_id": None,  # Set when Quote record is created
            "user_id": user.get("id"),
            "job_type": job_type,
            "client_name": user.get("shop_name"),
            "job_description": job_description,
            "materials": materials,
            "hardware": priced_hardware,
            "consumables": consumables,
            "labor": labor_processes,
            "finishing": finishing,
            "material_subtotal": material_subtotal,
            "hardware_subtotal": hardware_subtotal,
            "consumable_subtotal": consumable_subtotal,
            "labor_subtotal": labor_subtotal,
            "finishing_subtotal": finishing_subtotal,
            "subtotal": subtotal,
            "markup_options": markup_options,
            "selected_markup_pct": markup_default,
            "total": markup_options.get(str(markup_default), subtotal),
            "created_at": datetime.utcnow().isoformat(),
            "assumptions": assumptions,
            "exclusions": exclusions,
        }

        if detailed_cut_list:
            result["detailed_cut_list"] = detailed_cut_list
        if build_instructions:
            result["build_instructions"] = build_instructions

        # Materials summary — aggregated by profile for steel ordering
        result["materials_summary"] = self._aggregate_materials(materials)

        return result

    def _calculate_material_subtotal(self, materials: list) -> float:
        """Sum of all material line_total values."""
        return round(sum(item.get("line_total", 0) for item in materials), 2)

    def _calculate_hardware_subtotal(self, hardware: list) -> float:
        """
        Sum of hardware costs using the cheapest option for each item.
        """
        total = 0.0
        for item in hardware:
            price, _ = self.hardware_sourcer.select_cheapest_option(item)
            qty = item.get("quantity", 1)
            total += price * qty
        return round(total, 2)

    def _calculate_consumable_subtotal(self, consumables: list) -> float:
        """Sum of consumable line_total values."""
        return round(sum(c.get("line_total", 0) for c in consumables), 2)

    def _calculate_labor_subtotal(self, labor_processes: list) -> float:
        """Sum of hours × rate for each process."""
        return round(
            sum(p.get("hours", 0) * p.get("rate", 0) for p in labor_processes),
            2,
        )

    def _calculate_finishing_subtotal(self, finishing: dict) -> float:
        """finishing.total — already computed by FinishingBuilder."""
        return round(finishing.get("total", 0), 2)

    def _build_markup_options(self, subtotal: float) -> dict:
        """
        Returns: {"0": subtotal, "5": subtotal*1.05, ..., "30": subtotal*1.30}
        """
        return {
            str(pct): round(subtotal * (1 + pct / 100.0), 2)
            for pct in self.MARKUP_OPTIONS
        }

    def _build_assumptions(self, session_data: dict, consumables: list) -> list:
        """
        Collect all assumptions from the pipeline.
        """
        assumptions = []

        # Material price source
        assumptions.append(
            "Material prices based on market averages (Feb 2026) — "
            "update with supplier quotes for accuracy."
        )

        # Labor estimation method
        labor = session_data.get("labor_estimate", {})
        processes = labor.get("processes", [])
        if processes and "rule-based" in str(processes[0].get("notes", "")).lower():
            assumptions.append(
                "Labor hours estimated by rule-based fallback — "
                "AI estimator was unavailable. Consider re-running when available."
            )
        else:
            assumptions.append(
                "Labor hours estimated by AI (%s via %s) with domain guidance."
                % (get_model_name("deep"), "Claude")
            )

        # Hardware pricing source
        assumptions.append(
            "Hardware prices from catalog data — verify availability "
            "and current pricing before ordering."
        )

        # Consumables
        if consumables:
            consumable_total = sum(c.get("line_total", 0) for c in consumables)
            assumptions.append(
                f"Consumables estimated at ${consumable_total:.2f} based on "
                f"weld volume and finish area."
            )

        # Material list assumptions (from Stage 3)
        material_list = session_data.get("material_list", {})
        for a in material_list.get("assumptions", []):
            if a not in assumptions:
                assumptions.append(a)

        # Flagged estimate
        if labor.get("flagged"):
            assumptions.append(f"FLAGGED: {labor.get('flag_reason', 'Variance detected')}")

        return assumptions

    def _build_exclusions(self, session_data: dict) -> list:
        """
        Standard exclusions plus job-specific ones.
        """
        exclusions = [
            "Permit fees and engineering review",
            "Demolition or removal of existing work (unless explicitly included)",
        ]

        fields = session_data.get("fields", {})
        job_type = session_data.get("job_type", "")

        # Gate-specific exclusions
        if "gate" in job_type:
            exclusions.append("Concrete work beyond post holes")
            has_motor = "yes" in str(fields.get("has_motor", "")).lower()
            if has_motor:
                exclusions.append(
                    "Electrical wiring for gate operator "
                    "(we mount the operator; electrician handles wiring)"
                )

        # Install exclusions
        install = str(fields.get("installation", fields.get("install_included", ""))).lower()
        if "install" in install:
            exclusions.append("Touch-up after other trades complete their work")

        # Railing / stair exclusions
        if "railing" in job_type or "stair" in job_type:
            exclusions.append("Concrete or structural modifications to mount surfaces")

        # Repair exclusions
        if "repair" in job_type:
            exclusions.append("Additional damage discovered during disassembly")
            exclusions.append("Matching existing finish — exact color match not guaranteed")

        return exclusions

    def _check_bulk_discount(self, material_subtotal: float) -> str:
        """
        If material cost > $5,000: return suggestion string.
        """
        if material_subtotal > self.BULK_MATERIAL_THRESHOLD:
            return (
                f"Material cost exceeds ${self.BULK_MATERIAL_THRESHOLD:,.0f} "
                f"(${material_subtotal:,.2f}) — recommend negotiating bulk rate "
                f"with supplier for potential 5-15% savings."
            )
        return ""

    def _aggregate_materials(self, materials: list) -> list:
        """
        Group materials by profile for steel ordering summary.

        Returns list of dicts with: profile, description, total_length_ft,
        stock_length_ft, sticks_needed, remainder_ft, weight_lbs, total_cost,
        piece_count, is_area_sold.
        Concrete items tracked separately with is_concrete flag.
        """
        import math
        try:
            from .knowledge.materials import get_stock_length
        except Exception:
            return []
        try:
            from .weights import STOCK_WEIGHTS
        except Exception:
            STOCK_WEIGHTS = {}

        groups = {}  # type: dict
        concrete_items = []  # type: list
        for item in materials:
            profile = item.get("profile", "")
            mat_type = item.get("material_type", "")
            line_total = item.get("line_total", 0)
            qty = int(item.get("quantity", 1))
            length_in = item.get("length_inches", 0)

            # Concrete tracked separately
            if mat_type in ("concrete", "other") or profile.startswith("concrete"):
                concrete_items.append(item)
                continue

            stock_ft = get_stock_length(profile)
            is_area_sold = stock_ft is None  # sheet/plate

            if profile not in groups:
                groups[profile] = {
                    "profile": profile,
                    "description": item.get("description", profile),
                    "total_length_ft": 0.0,
                    "piece_count": 0,
                    "total_cost": 0.0,
                    "stock_length_ft": stock_ft or 0,
                    "is_area_sold": is_area_sold,
                }
            groups[profile]["total_length_ft"] += (length_in * qty) / 12.0
            groups[profile]["piece_count"] += qty
            groups[profile]["total_cost"] += line_total

        result = []
        for profile, info in sorted(groups.items()):
            total_ft = round(info["total_length_ft"], 1)
            stock_ft = info["stock_length_ft"]

            if not info["is_area_sold"] and stock_ft > 0:
                sticks = int(math.ceil(total_ft / stock_ft))
                remainder = round(sticks * stock_ft - total_ft, 1)
            else:
                sticks = 0
                remainder = 0

            # Weight lookup — try exact key, then prefix match
            weight_per_ft = STOCK_WEIGHTS.get(profile, 0)
            if weight_per_ft == 0:
                for key, val in STOCK_WEIGHTS.items():
                    if profile.startswith(key) or key.startswith(profile.split("_")[0] + "_" + profile.split("_")[1] if "_" in profile else profile):
                        weight_per_ft = val
                        break
            weight_lbs = round(weight_per_ft * total_ft, 1) if weight_per_ft > 0 else 0

            result.append({
                "profile": profile,
                "description": info["description"],
                "total_length_ft": total_ft,
                "piece_count": info["piece_count"],
                "stock_length_ft": stock_ft,
                "sticks_needed": sticks,
                "remainder_ft": remainder,
                "weight_lbs": weight_lbs,
                "total_cost": round(info["total_cost"], 2),
                "is_area_sold": info["is_area_sold"],
            })

        # Add concrete as separate entry
        if concrete_items:
            total_qty = sum(int(c.get("quantity", 1)) for c in concrete_items)
            total_cost = sum(c.get("line_total", 0) for c in concrete_items)
            result.append({
                "profile": "concrete",
                "description": concrete_items[0].get("description", "Concrete"),
                "total_length_ft": 0,
                "piece_count": total_qty,
                "stock_length_ft": 0,
                "sticks_needed": 0,
                "remainder_ft": 0,
                "weight_lbs": round(total_qty * 80, 1),  # 80lb bags
                "total_cost": round(total_cost, 2),
                "is_area_sold": False,
                "is_concrete": True,
            })

        return result

    def recalculate_with_markup(self, priced_quote: dict, markup_pct: int) -> dict:
        """
        Recalculate total with a new markup percentage.
        Returns updated priced_quote dict.
        """
        subtotal = priced_quote.get("subtotal", 0)
        new_total = round(subtotal * (1 + markup_pct / 100.0), 2)
        priced_quote["selected_markup_pct"] = markup_pct
        priced_quote["total"] = new_total
        return priced_quote
