"""
Stage 5 — Pricing Engine.

Combines all upstream pipeline outputs into a PricedQuote.
Pure math — no AI. Quantity × price, hours × rate, subtotal × markup.

Input: MaterialList + LaborEstimate + FinishingSection + hardware pricing
Output: PricedQuote (per CLAUDE.md contract)
"""

from datetime import datetime

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

        # --- Price hardware ---
        raw_hardware = material_list.get("hardware", [])
        priced_hardware = self.hardware_sourcer.price_hardware_list(raw_hardware)

        # --- Estimate consumables ---
        weld_inches = material_list.get("weld_linear_inches", 0)
        total_sq_ft = material_list.get("total_sq_ft", 0)
        finish_type = fields.get("finish", "raw")
        consumables = self.hardware_sourcer.estimate_consumables(
            weld_inches, total_sq_ft, finish_type,
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

        return {
            "quote_id": None,  # Set when Quote record is created
            "user_id": user.get("id"),
            "job_type": job_type,
            "client_name": user.get("shop_name"),
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
                "Labor hours estimated by AI (Gemini 2.0 Flash) with domain guidance."
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
