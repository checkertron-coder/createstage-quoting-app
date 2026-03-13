"""
Stage 5 — Pricing Engine.

Combines all upstream pipeline outputs into a PricedQuote.
Pure math — no AI. Quantity × price, hours × rate, subtotal × markup.

Input: MaterialList + LaborEstimate + FinishingSection + hardware pricing
Output: PricedQuote (per CLAUDE.md contract)
"""

import logging
from datetime import datetime

from .claude_client import get_model_name
from .finishing import FinishingBuilder
from .hardware_sourcer import HardwareSourcer

logger = logging.getLogger(__name__)


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
        upstream_finishing = session_data.get("finishing", {})
        fields = session_data.get("fields", {})
        job_type = session_data.get("job_type", "custom_fab")
        job_description = fields.get("description", "")

        labor_processes = labor_estimate.get("processes", [])
        total_sq_ft = material_list.get("total_sq_ft", 0)
        clear_coat_type = fields.get("clear_coat_type", "")
        finishing_builder = FinishingBuilder()

        # --- Check for _opus_* keys (full package path) ---
        opus_hardware = material_list.get("_opus_hardware")
        opus_consumables = material_list.get("_opus_consumables")
        opus_labor = material_list.get("_opus_labor_hours")
        opus_finishing_method = material_list.get("_opus_finishing_method")

        if opus_hardware is not None:
            # Full package path — trust Opus's output directly
            priced_hardware = list(opus_hardware)

            # Trust Opus's consumable prices — just ensure line_total math
            consumables = []
            for item in list(opus_consumables or []):
                item = dict(item)  # don't mutate original
                qty = max(int(item.get("quantity", 1) or 1), 1)
                unit_price = float(item.get("unit_price", 0) or 0)
                item["line_total"] = round(qty * unit_price, 2)
                consumables.append(item)

            # Build finishing from Opus's method recommendation
            finish_method = opus_finishing_method or "raw"
            finishing = finishing_builder.build(
                finish_type=finish_method,
                total_sq_ft=total_sq_ft,
                labor_processes=labor_processes,
                clear_coat_type=clear_coat_type,
            )

            # Use Opus labor hours if available (multiply by user's shop rate)
            if opus_labor:
                labor_processes = self._build_labor_from_opus(
                    opus_labor, labor_processes, user,
                )
        else:
            # Legacy path — rebuild finishing from fields (no Opus to trust)
            finish_field = fields.get("finish", fields.get("finish_type", ""))
            if not finish_field:
                desc_lower = str(job_description).lower()
                if "powder" in desc_lower and "coat" in desc_lower:
                    finish_field = "powder_coat"
                elif "clear coat" in desc_lower or "clearcoat" in desc_lower:
                    finish_field = "clearcoat"
                elif "paint" in desc_lower and "powder" not in desc_lower:
                    finish_field = "paint"
                elif "galvaniz" in desc_lower:
                    finish_field = "galvanized"
                elif "anodiz" in desc_lower:
                    finish_field = "anodized"
                elif "patina" in desc_lower or "blacken" in desc_lower:
                    finish_field = "patina"
                elif "brush" in desc_lower or "polish" in desc_lower:
                    finish_field = "brushed"
                else:
                    finish_field = "raw"

            finishing = finishing_builder.build(
                finish_type=finish_field,
                total_sq_ft=total_sq_ft,
                labor_processes=labor_processes,
                clear_coat_type=clear_coat_type,
            )

            # --- Price hardware ---
            raw_hardware = material_list.get("hardware", [])
            priced_hardware = self.hardware_sourcer.price_hardware_list(raw_hardware)

            # --- Electronics / specialty hardware ---
            electronics = self.hardware_sourcer.estimate_electronics(job_description)
            if electronics:
                priced_hardware.extend(electronics)

            # --- Estimate consumables ---
            weld_inches = material_list.get("weld_linear_inches", 0)
            total_sq_ft = material_list.get("total_sq_ft", 0)
            finish_type = finish_field

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

            # --- Opus BOM estimation (AI-driven hardware + consumables) ---
            try:
                opus_bom = self.hardware_sourcer.opus_estimate_bom(
                    job_description,
                    material_list.get("items", []),
                    detected_material,
                    job_type,
                )
                if opus_bom:
                    if opus_bom.get("hardware"):
                        priced_hardware.extend(opus_bom["hardware"])
                    if opus_bom.get("consumables"):
                        consumables = opus_bom["consumables"]
            except Exception:
                pass

        # --- BOM validation: orphan check against build instructions ---
        build_instructions = session_data.get("build_instructions", [])
        if build_instructions and priced_hardware:
            from .bom_validator import validate_bom_against_build
            bom_result = validate_bom_against_build(priced_hardware, build_instructions)
            priced_hardware = bom_result["kept"]
            orphaned_hw = bom_result["orphaned"]
            orphan_reasons = bom_result["orphan_reasons"]
        else:
            orphaned_hw = []
            orphan_reasons = []

        # --- Dedup + tiering ---
        priced_hardware = self._dedup_hardware(priced_hardware)
        tier_result = self._tier_items(priced_hardware, consumables)
        priced_hardware = tier_result["hardware"]
        consumables = tier_result["consumables"]
        shop_stock = tier_result["shop_stock"]

        # --- Calculate subtotals ---
        materials = material_list.get("items", [])
        if not opus_labor:
            labor_processes = labor_estimate.get("processes", [])

        material_subtotal = self._calculate_material_subtotal(materials)
        hardware_subtotal = self._calculate_hardware_subtotal(priced_hardware)
        consumable_subtotal = self._calculate_consumable_subtotal(consumables)
        labor_subtotal = self._calculate_labor_subtotal(labor_processes)
        finishing_subtotal = self._calculate_finishing_subtotal(finishing)
        shop_stock_subtotal = self._calculate_shop_stock_subtotal(shop_stock)

        subtotal = round(
            material_subtotal + hardware_subtotal + consumable_subtotal +
            labor_subtotal + finishing_subtotal + shop_stock_subtotal,
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
            "shop_stock": shop_stock,
            "labor": labor_processes,
            "finishing": finishing,
            "material_subtotal": material_subtotal,
            "hardware_subtotal": hardware_subtotal,
            "consumable_subtotal": consumable_subtotal,
            "shop_stock_subtotal": shop_stock_subtotal,
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

        # Orphaned hardware from BOM validation
        if orphaned_hw:
            result["orphaned_hardware"] = orphaned_hw
            validation_warnings = result.get("validation_warnings", [])
            validation_warnings.append(
                "%d hardware item(s) removed — no matching fabrication step: %s"
                % (len(orphaned_hw), ", ".join(
                    o.get("description", "?") for o in orphaned_hw
                ))
            )
            result["validation_warnings"] = validation_warnings

        # Materials summary — aggregated by profile for steel ordering
        result["materials_summary"] = self._aggregate_materials(
            materials, detailed_cut_list
        )

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

    def _build_labor_from_opus(self, opus_labor, existing_processes, user):
        """Convert Opus labor_hours dict to LaborProcess list."""
        rate_inshop = user.get("rate_inshop", 125.00)
        rate_onsite = user.get("rate_onsite", 145.00)
        processes = []
        for process_name, entry in opus_labor.items():
            if isinstance(entry, dict):
                h = round(float(entry.get("hours", 0)), 2)
            else:
                h = round(float(entry or 0), 2)
            if h <= 0:
                continue
            rate = rate_onsite if process_name == "site_install" else rate_inshop
            processes.append({
                "process": process_name,
                "hours": h,
                "rate": rate,
                "notes": "Opus full package estimate",
            })
        return processes if processes else existing_processes

    # Fallback prices for common consumables when Opus returns $0
    _CONSUMABLE_FALLBACK_PRICES = {
        "welding wire": 3.50,
        "er70s": 3.50,
        "er4043": 18.00,
        "er5356": 18.00,
        "er308": 22.00,
        "grinding disc": 4.50,
        "flap disc": 6.50,
        "cut-off disc": 3.50,
        "cutoff disc": 3.50,
        "shielding gas": 15.00,
        "argon": 15.00,
        "75/25": 12.00,
        "primer": 8.50,
        "clear coat": 12.50,
        "clearcoat": 12.50,
        "paint": 14.00,
        "sandpaper": 5.00,
        "anti-spatter": 9.00,
        "soapstone": 3.00,
        "marking": 3.00,
        "masking tape": 6.00,
        "wire brush": 8.00,
        "wire wheel": 12.00,
        "acetone": 8.00,
        "degreaser": 10.00,
    }

    def _validate_consumable_prices(self, consumables):
        # type: (list) -> list
        """
        Ensure all consumable items have non-zero prices.
        If Opus returned unit_price=0, look up a fallback price.
        Always recalculates line_total from quantity * unit_price.
        """
        for item in consumables:
            unit_price = float(item.get("unit_price", 0) or 0)
            qty = max(int(item.get("quantity", 1) or 1), 1)

            if unit_price <= 0:
                # Try to match description against known consumables
                desc = str(item.get("description", "")).lower()
                matched_price = None
                for keyword, price in self._CONSUMABLE_FALLBACK_PRICES.items():
                    if keyword in desc:
                        matched_price = price
                        break
                if matched_price:
                    unit_price = matched_price
                else:
                    # Last resort — minimum $5.00 per consumable item
                    unit_price = 5.00

                item["unit_price"] = round(unit_price, 2)

            item["line_total"] = round(qty * unit_price, 2)

        return consumables

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

        # Opus assumptions from full package
        for a in material_list.get("_opus_assumptions", []):
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

        # Opus exclusions from full package — pass through unmodified
        material_list = session_data.get("material_list", {})
        for e in material_list.get("_opus_exclusions", []):
            if e not in exclusions:
                exclusions.append(e)

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

    @staticmethod
    def _bin_pack_sticks(piece_lengths_ft, stock_ft):
        """First-fit decreasing bin packing — how many sticks to order."""
        import math
        if not piece_lengths_ft or stock_ft <= 0:
            total = sum(piece_lengths_ft) if piece_lengths_ft else 0
            return int(math.ceil(total / stock_ft)) if stock_ft > 0 else 0
        sorted_pieces = sorted(piece_lengths_ft, reverse=True)
        bins = []  # remaining space in each bin (stick)
        for piece in sorted_pieces:
            if piece > stock_ft:
                # Piece longer than stock — needs its own stick (will splice)
                bins.append(0)
                continue
            placed = False
            for i, remaining in enumerate(bins):
                if remaining >= piece:
                    bins[i] -= piece
                    placed = True
                    break
            if not placed:
                bins.append(stock_ft - piece)
        return len(bins)

    def _aggregate_materials(self, materials, cut_list=None):
        """
        Group materials by profile for steel ordering summary.

        Returns list of dicts with: profile, description, total_length_ft,
        stock_length_ft, sticks_needed, remainder_ft, weight_lbs, total_cost,
        is_area_sold.
        Concrete items tracked separately with is_concrete flag.

        Uses cut_list (detailed_cut_list) when available to:
        - Bin-pack pieces into sticks for accurate stick count
        - Calculate plate/sheet area from piece dimensions for sheet count
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

        # --- Build per-profile piece data from cut list ---
        # piece_lengths[profile] = [length_ft, length_ft, ...]  (one per piece)
        # piece_areas[profile] = total area in sq inches (for plate/sheet)
        profile_piece_lengths = {}  # type: dict
        profile_piece_areas = {}    # type: dict
        if cut_list:
            for piece in (cut_list or []):
                profile = piece.get("profile", "")
                length_in = piece.get("length_inches", 0)
                width_in = piece.get("width_inches", 0)
                qty = int(piece.get("quantity", 1))
                if not profile:
                    continue
                if profile not in profile_piece_lengths:
                    profile_piece_lengths[profile] = []
                    profile_piece_areas[profile] = 0.0
                for _ in range(qty):
                    profile_piece_lengths[profile].append(length_in / 12.0)
                # Accumulate plate/sheet area
                if width_in > 0:
                    profile_piece_areas[profile] += length_in * width_in * qty

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
            # Also try stripped key for al_/ss_ prefixed profiles
            if stock_ft == 20 and (profile.startswith("al_") or profile.startswith("ss_")):
                stock_ft = get_stock_length(profile[3:] if profile.startswith("al_") else profile[3:])
            # Detect area-sold: get_stock_length returns None for sheet/plate,
            # or infer from profile name if lookup missed
            is_area_sold = stock_ft is None or "sheet" in profile or "plate" in profile

            if profile not in groups:
                groups[profile] = {
                    "profile": profile,
                    "description": item.get("description", profile),
                    "total_length_ft": 0.0,
                    "total_cost": 0.0,
                    "stock_length_ft": stock_ft or 0,
                    "is_area_sold": is_area_sold,
                    # Sheet fields from Opus (accumulated across items)
                    "sheet_stock_size": None,
                    "sheets_needed": 0,
                    "seaming_required": False,
                }
            groups[profile]["total_length_ft"] += (length_in * qty) / 12.0
            groups[profile]["total_cost"] += line_total

            # Accumulate sheet data from material items (set by _build_from_ai_cuts)
            # Take the LARGEST sheet size needed (not the last one seen)
            if is_area_sold:
                new_size = item.get("sheet_stock_size")
                if new_size:
                    existing = groups[profile]["sheet_stock_size"]
                    if not existing or (new_size[0] * new_size[1]) > (existing[0] * existing[1]):
                        groups[profile]["sheet_stock_size"] = new_size
                groups[profile]["sheets_needed"] += item.get("sheets_needed", 0)
                if item.get("seaming_required"):
                    groups[profile]["seaming_required"] = True

        result = []
        for profile, info in sorted(groups.items()):
            total_ft = round(info["total_length_ft"], 1)
            stock_ft = info["stock_length_ft"]

            # Sheet items: use Opus's sheet data if available
            sheet_size = info.get("sheet_stock_size")
            sheets_needed = info.get("sheets_needed", 0)
            seaming = info.get("seaming_required", False)

            if info["is_area_sold"]:
                # Default sheet size if Opus didn't specify
                if not sheet_size:
                    sheet_size = [48, 96]  # standard 4'x8'
                sheet_area_sqin = sheet_size[0] * sheet_size[1]

                if sheets_needed > 0:
                    # Opus told us the sheet count — use it
                    sticks = sheets_needed
                elif profile in profile_piece_areas and profile_piece_areas[profile] > 0:
                    # Calculate sheets from actual piece areas (cut list)
                    sheets_needed = max(1, int(math.ceil(
                        profile_piece_areas[profile] / sheet_area_sqin
                    )))
                    sticks = sheets_needed
                else:
                    # Fallback: estimate from total linear ft
                    # Assume average 12" width for plate pieces
                    est_area = total_ft * 12 * 12  # total_ft * 12in width * 12in/ft
                    sheets_needed = max(1, int(math.ceil(est_area / sheet_area_sqin)))
                    sticks = sheets_needed

                stock_ft = sheet_size[1] / 12.0
                remainder = 0
                # Unused sheet area (sqft) for fabricator visibility
                actual_area = profile_piece_areas.get(profile, 0)
                ordered_area = sticks * sheet_area_sqin
                if actual_area > 0 and ordered_area > actual_area:
                    remainder_sqft = round((ordered_area - actual_area) / 144.0, 1)
                else:
                    remainder_sqft = 0
            elif stock_ft > 0:
                # Use bin-packing if we have individual piece lengths
                if profile in profile_piece_lengths:
                    sticks = self._bin_pack_sticks(
                        profile_piece_lengths[profile], stock_ft
                    )
                else:
                    sticks = int(math.ceil(total_ft / stock_ft))
                remainder = round(sticks * stock_ft - total_ft, 1)
            else:
                sticks = 0
                remainder = 0

            # --- Weight calculation ---
            # For area-sold (plate/sheet): weight = sheets × sheet_sqft × lb/sqft
            # For linear stock: weight = total_ft × lb/ft
            weight_lbs = 0

            if info["is_area_sold"]:
                # Plate/sheet weight = weight of the stock being ordered
                try:
                    import re as _re
                    from .knowledge.materials import PROFILES
                    lookup_key = profile[3:] if profile.startswith("al_") else profile
                    mat_data = PROFILES.get(lookup_key, {})
                    w_per_sqft = mat_data.get("weight_per_foot", 0)
                    # Dynamic fallback: compute from thickness if PROFILES miss
                    if w_per_sqft <= 0 and ("sheet" in lookup_key or "plate" in lookup_key):
                        m = _re.search(r'[\._](\d+\.?\d*)', lookup_key)
                        if m:
                            thickness = float(m.group(1))
                            if thickness < 1:  # sane guard: 0.040-0.500
                                # Steel weight: thickness × 144 sqin/sqft × 0.2836 lb/in³
                                w_per_sqft = round(thickness * 144 * 0.2836, 2)
                    if w_per_sqft > 0:
                        if profile.startswith("al_"):
                            w_per_sqft = round(w_per_sqft * 0.344, 2)
                        sheet_sqft = (sheet_size[0] * sheet_size[1]) / 144.0
                        weight_lbs = round(sheets_needed * sheet_sqft * w_per_sqft, 1)
                except Exception:
                    pass
            else:
                # Linear stock weight
                weight_per_ft = STOCK_WEIGHTS.get(profile, 0)
                if weight_per_ft == 0:
                    for key, val in STOCK_WEIGHTS.items():
                        if profile.startswith(key) or key.startswith(
                            profile.split("_")[0] + "_" + profile.split("_")[1]
                            if "_" in profile else profile
                        ):
                            weight_per_ft = val
                            break
                # Aluminum fallback: strip al_ prefix and scale by 0.344
                if weight_per_ft == 0 and profile.startswith("al_"):
                    steel_key = profile[3:]
                    steel_weight = STOCK_WEIGHTS.get(steel_key, 0)
                    if steel_weight == 0:
                        for key, val in STOCK_WEIGHTS.items():
                            if steel_key.startswith(key):
                                steel_weight = val
                                break
                    if steel_weight > 0:
                        weight_per_ft = round(steel_weight * 0.344, 2)
                if weight_per_ft > 0:
                    # Weight of stock ordered = sticks × stock_length × lb/ft
                    weight_lbs = round(sticks * stock_ft * weight_per_ft, 1) if sticks > 0 else round(weight_per_ft * total_ft, 1)

            entry = {
                "profile": profile,
                "description": info["description"],
                "total_length_ft": total_ft,
                "stock_length_ft": stock_ft,
                "sticks_needed": sticks,
                "remainder_ft": remainder,
                "weight_lbs": weight_lbs,
                "total_cost": round(info["total_cost"], 2),
                "is_area_sold": info["is_area_sold"],
            }
            # Attach sheet metadata for PDF display
            if sheet_size and info["is_area_sold"]:
                entry["sheet_size"] = sheet_size
                if remainder_sqft > 0:
                    entry["remainder_sqft"] = remainder_sqft
            if sheets_needed > 0:
                entry["sheets_needed"] = sheets_needed
            if seaming:
                entry["seaming_required"] = True
            result.append(entry)

        # Add concrete as separate entry
        if concrete_items:
            total_qty = sum(int(c.get("quantity", 1)) for c in concrete_items)
            total_cost = sum(c.get("line_total", 0) for c in concrete_items)
            result.append({
                "profile": "concrete",
                "description": "Concrete - %d x 80lb bags" % total_qty,
                "total_length_ft": 0,
                "stock_length_ft": 0,
                "sticks_needed": total_qty,
                "remainder_ft": 0,
                "weight_lbs": round(total_qty * 80, 1),  # 80lb bags
                "total_cost": round(total_cost, 2),
                "is_area_sold": False,
                "is_concrete": True,
            })

        return result

    # --- Shop stock keywords for tiering ---
    _SHOP_STOCK_KEYWORDS = (
        "wire", "disc", "gas", "tape", "sandpaper", "solvent",
        "primer", "spray", "welding", "grinding", "flap",
        "shielding", "clear coat", "clearcoat", "denatured",
        "alcohol", "acetone", "spool",
    )

    def _dedup_hardware(self, hardware_list):
        # type: (list) -> list
        """
        Deduplicate hardware items by normalized description.

        If duplicates found, keep the one with most pricing options; sum quantities.
        """
        if not hardware_list:
            return []

        import re
        groups = {}  # type: dict
        for item in hardware_list:
            desc = str(item.get("description", ""))
            # Normalize: lowercase, strip adjectives/qty words
            norm = re.sub(r'[^a-z0-9\s]', '', desc.lower()).strip()
            norm = re.sub(r'\b(heavy|duty|standard|estimated|est|qty|pack|of)\b', '', norm).strip()
            norm = re.sub(r'\s+', ' ', norm)

            if norm in groups:
                existing = groups[norm]
                # Sum quantities
                existing["quantity"] = existing.get("quantity", 1) + item.get("quantity", 1)
                # Keep the one with more pricing options
                if len(item.get("options", [])) > len(existing.get("options", [])):
                    qty = existing["quantity"]
                    groups[norm] = dict(item)
                    groups[norm]["quantity"] = qty
            else:
                groups[norm] = dict(item)

        result = list(groups.values())
        if len(result) < len(hardware_list):
            logger.info("Deduped hardware: %d -> %d items", len(hardware_list), len(result))
        return result

    def _tier_items(self, hardware, consumables):
        # type: (list, list) -> dict
        """
        Separate items into tiers:
        - Tier 1 (hardware): Project-specific items stay in hardware list
        - Tier 2 (shop_stock): Consumables/supplies every fab shop has

        Consumables from the consumables list that match shop stock keywords
        are moved to shop_stock with allocation_pct.

        Returns: {"hardware": [...], "consumables": [...], "shop_stock": [...]}
        """
        shop_stock = []

        # Move consumables that are shop stock items
        remaining_consumables = []
        for item in (consumables or []):
            desc = str(item.get("description", "")).lower()
            cat = str(item.get("category", "")).lower()
            if cat == "consumable" or any(kw in desc for kw in self._SHOP_STOCK_KEYWORDS):
                stock_item = dict(item)
                stock_item["allocation_pct"] = 100  # full allocation for this job
                shop_stock.append(stock_item)
            else:
                remaining_consumables.append(item)

        # Hardware items that look like consumables -> shop stock
        remaining_hw = []
        for item in (hardware or []):
            desc = str(item.get("description", "")).lower()
            if any(kw in desc for kw in self._SHOP_STOCK_KEYWORDS):
                # Convert to shop stock format
                price, _ = self.hardware_sourcer.select_cheapest_option(item)
                qty = item.get("quantity", 1)
                stock_item = {
                    "description": item.get("description", ""),
                    "quantity": qty,
                    "unit_price": price,
                    "line_total": round(price * qty, 2),
                    "allocation_pct": 100,
                    "category": "consumable",
                }
                shop_stock.append(stock_item)
            else:
                remaining_hw.append(item)

        return {
            "hardware": remaining_hw,
            "consumables": remaining_consumables,
            "shop_stock": shop_stock,
        }

    def _calculate_shop_stock_subtotal(self, shop_stock):
        # type: (list) -> float
        """Sum of allocated shop stock costs."""
        if not shop_stock:
            return 0.0
        return round(
            sum(
                round(
                    s.get("line_total", 0) * s.get("allocation_pct", 100) / 100, 2
                )
                for s in shop_stock
            ),
            2,
        )

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
