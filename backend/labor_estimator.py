"""
Stage 4 — AI-powered labor estimation engine.

Input: MaterialList (from Stage 3) + QuoteParams (from Stage 2) + user rates
Output: LaborEstimate (per CLAUDE.md contract)

Uses Gemini 2.0 Flash to estimate hours per process.
AI receives structured data, returns structured JSON.
Total hours are COMPUTED by summing process hours — never AI-provided.

Graceful fallback: if Gemini is unavailable, uses rule-based estimation.
The app NEVER fails because the AI is down.
"""

import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# The 11 labor processes — every estimate must address each one
LABOR_PROCESSES = [
    "layout_setup",
    "cut_prep",
    "fit_tack",
    "full_weld",
    "grind_clean",
    "finish_prep",
    "clearcoat",
    "paint",
    "hardware_install",
    "site_install",
    "final_inspection",
]


class LaborEstimator:
    """
    Stage 4 of the pipeline.

    Input: MaterialList (from Stage 3) + QuoteParams (from Stage 2)
    Output: LaborEstimate (per CLAUDE.md contract)

    The AI NEVER returns a single total hours number. It ALWAYS returns
    per-process breakdown. The total is computed by summing in Python.
    """

    def estimate(self, material_list: dict, quote_params: dict, user_rates: dict) -> dict:
        """
        Main entry point — deterministic labor calculation from cut list.

        No AI involved. Hours are calculated from cut list analysis using
        shop time standards from FAB_KNOWLEDGE.md.

        Args:
            material_list: MaterialList from Stage 3
            quote_params: QuoteParams from Stage 2 (has job_type, fields, notes)
            user_rates: {"rate_inshop": float, "rate_onsite": float} from user profile

        Returns:
            LaborEstimate dict matching CLAUDE.md contract (11 processes)
        """
        from .calculators.labor_calculator import calculate_labor_hours

        is_onsite = self._is_onsite_job(quote_params)
        fields = quote_params.get("fields", {})
        job_type = quote_params.get("job_type", "custom_fab")
        finish = str(fields.get("finish", "raw")).lower()

        # Prefer per-piece cut list; fall back to consolidated items
        cut_list = material_list.get("cut_list", material_list.get("items", []))

        # --- Deterministic core calculation (8 keys) ---
        labor_hours = calculate_labor_hours(job_type, cut_list, fields)

        # --- Map coating_application → clearcoat / paint ---
        coating = labor_hours["coating_application"]
        if "clear" in finish:
            clearcoat_hrs = coating
            paint_hrs = 0.0
        elif "paint" in finish and "powder" not in finish:
            clearcoat_hrs = 0.0
            paint_hrs = coating
        else:
            clearcoat_hrs = 0.0
            paint_hrs = 0.0

        # --- Hardware install (deterministic rule-based) ---
        hardware = material_list.get("hardware", [])
        hardware_count = sum(h.get("quantity", 1) for h in hardware)
        hardware_install = max(0.0, hardware_count * 0.4)  # ~25 min/item
        for h in hardware:
            desc = str(h.get("description", "")).lower()
            if "operator" in desc or "motor" in desc:
                hardware_install += 1.5

        # --- Site install (deterministic rule-based) ---
        install_str = str(fields.get("installation",
                          fields.get("install_included", "no"))).lower()
        is_install = "install" in install_str or "yes" in install_str
        site_install = 0.0
        if is_install:
            weight = material_list.get("total_weight_lbs", 0)
            if weight < 200:
                site_install = 3.0
            elif weight < 500:
                site_install = 5.0
            elif weight < 1000:
                site_install = 7.0
            else:
                site_install = 10.0
            if ("concrete" in str(fields.get("post_concrete", "")).lower()
                    or "full installation" in install_str):
                site_install += 2.0

        # --- Assemble 11-process list ---
        hours_map = {
            "layout_setup": labor_hours["layout_setup"],
            "cut_prep": labor_hours["cut_prep"],
            "fit_tack": labor_hours["fit_tack"],
            "full_weld": labor_hours["full_weld"],
            "grind_clean": labor_hours["grind_clean"],
            "finish_prep": labor_hours["finish_prep"],
            "clearcoat": clearcoat_hrs,
            "paint": paint_hrs,
            "hardware_install": round(hardware_install, 2),
            "site_install": round(site_install, 2),
            "final_inspection": labor_hours["final_inspection"],
        }

        note = "Deterministic — calculated from cut list and shop standards"
        processes = []
        for process_name in LABOR_PROCESSES:
            hours = round(max(hours_map.get(process_name, 0.0), 0.0), 2)
            rate = self._get_rate_for_process(process_name, is_onsite, user_rates)
            processes.append({
                "process": process_name,
                "hours": hours,
                "rate": rate,
                "notes": note,
            })

        total_hours = round(sum(p["hours"] for p in processes), 2)

        return {
            "processes": processes,
            "total_hours": total_hours,
            "flagged": False,
            "flag_reason": None,
        }

    def _build_prompt(self, material_list: dict, quote_params: dict) -> str:
        """
        Build the Gemini prompt. Provides structured context and demands
        structured JSON output with per-process hour breakdowns.

        Includes weld process reasoning — TIG vs MIG determination affects
        labor hours significantly (TIG is 2.5-3.5x slower than MIG).
        """
        fields = quote_params.get("fields", {})
        job_type = quote_params.get("job_type", "custom_fab")
        items = material_list.get("items", [])
        hardware = material_list.get("hardware", [])

        # Summarize materials
        piece_count = sum(item.get("quantity", 1) for item in items)
        total_weight = material_list.get("total_weight_lbs", 0)
        weld_inches = material_list.get("weld_linear_inches", 0)
        total_sq_ft = material_list.get("total_sq_ft", 0)
        hardware_count = sum(h.get("quantity", 1) for h in hardware)

        # Key dimensions
        dimensions_summary = []
        for key in ["clear_width", "height", "linear_footage", "railing_height",
                     "panel_config", "stair_angle", "num_risers", "description"]:
            if key in fields:
                val = fields[key]
                # Truncate long descriptions
                val_str = str(val)
                if len(val_str) > 200:
                    val_str = val_str[:200] + "..."
                dimensions_summary.append("  - %s: %s" % (key, val_str))

        # Material descriptions with weld process info
        material_lines = []
        for item in items[:20]:
            desc = item.get("description", "unknown")
            qty = item.get("quantity", 1)
            cut = item.get("cut_type", "square")
            weld_proc = item.get("weld_process", "")
            weld_info = " [%s]" % weld_proc.upper() if weld_proc else ""
            material_lines.append(
                "  - %s (qty: %d, cut: %s)%s" % (desc, qty, cut, weld_info)
            )

        # Hardware descriptions
        hardware_lines = []
        for h in hardware:
            hardware_lines.append("  - %s (qty: %d)" % (
                h.get("description", "unknown"), h.get("quantity", 1)))

        # Finish type
        finish = fields.get("finish", "raw")
        install = fields.get("installation", fields.get("install_included", "No"))
        is_install = "install" in str(install).lower() or "yes" in str(install).lower()

        # Detect weld process from material list items (set by AI cut list)
        has_tig_items = any(
            item.get("weld_process", "").lower() == "tig" for item in items
        )

        # Also detect TIG from field values
        all_fields_text = " ".join(str(v) for v in fields.values()).lower()
        tig_indicators = [
            "ground smooth", "blended", "furniture finish", "show quality",
            "visible welds", "tig", "glass top", "grind flush", "grind smooth",
            "seamless", "showroom", "polished", "mirror finish",
            "stainless", "aluminum", "chrome", "brushed finish",
        ]
        needs_tig = has_tig_items or any(ind in all_fields_text for ind in tig_indicators)

        # Stainless / aluminum detection
        is_stainless = "stainless" in all_fields_text or "304" in all_fields_text
        is_aluminum = "aluminum" in all_fields_text or "6061" in all_fields_text

        # Build weld process section
        weld_section = self._build_weld_process_section(
            needs_tig, is_stainless, is_aluminum, weld_inches)

        # Is this on-site work?
        is_onsite = self._is_onsite_job(quote_params)

        prompt = """You are an expert metal fabrication labor estimator with 20+ years of shop experience.

TASK: Estimate labor hours per process for a %s fabrication job.

JOB SUMMARY:
  Job type: %s
  Total material pieces: %d
  Total weight: %.1f lbs
  Total weld linear inches: %.1f
  Total surface area (for finishing): %.1f sq ft
  Hardware items to install: %d
  Finish type: %s
  Installation included: %s
  On-site work (entire job): %s

KEY DIMENSIONS AND DESCRIPTION:
%s

MATERIAL LIST:
%s

HARDWARE:
%s

=== WELD PROCESS DETERMINATION ===
%s

=== LABOR ESTIMATION GUIDANCE ===

PROCESS-BY-PROCESS RULES OF THUMB:

1. layout_setup (0.5-2.0 hrs):
   - Simple railing/fence = 0.5 hr
   - Complex gate/stair = 1.0-1.5 hrs
   - Custom furniture with patterns = 1.5-2.0 hrs
   - Includes: reading drawings, measuring, marking, squaring table

2. cut_prep:
   - Square cuts: ~3 min per cut (chop saw)
   - Miter cuts: ~5 min per cut (requires angle setup)
   - Cope cuts: ~8-10 min per cut (requires notcher or hand work)
   - Compound cuts: ~10-15 min per cut
   - Scale with piece count: %d pieces total

3. fit_tack (MOST VARIABLE — think carefully):
   - Simple rectangular frame = 1-2 hrs
   - Complex assembly (gate with infill) = 3-5 hrs
   - Pattern work (repeating pickets/slats) = add 2-3 min per piece
   - Furniture with precision fits = 4-8 hrs
   - Stair with multiple treads = 4-8 hrs

4. full_weld:
   - MIG on mild steel: 8-15 linear inches per hour
   - TIG on mild steel: 4-8 linear inches per hour (2-3x slower)
   - TIG on stainless: 3-6 linear inches per hour (add back-purge time)
   - Overhead/vertical position: reduce rate by 30-40%%
   - Total weld inches for this job: %.1f

5. grind_clean:
   - Standard (MIG, painted finish): 30-40%% of weld time
   - Ground smooth (TIG visible): 75-100%% of weld time
   - Blended/seamless joints: 100-150%% of weld time
   - Raw steel (no finish): 20-30%% of weld time (just cleanup)

6. finish_prep: 0.5-1.0 hr for paint prep. 0 for raw. 0.25 for powder coat prep (outsourced).
7. clearcoat: ~0.5 hr per 50 sq ft. 0 if not clearcoat.
8. paint: ~0.75 hr per 50 sq ft (primer + topcoat). 0 if not paint.
9. hardware_install: ~15-30 min per simple item. 1-2 hrs for motor/operator.
10. site_install: 2-4 hrs railing, 4-8 hrs gate w/ concrete, 6-12 hrs stairs. 0 if no install.
11. final_inspection: 0.25-0.5 hrs always.

REASONABLENESS CHECK:
  - Cantilever gate with motor + install: 16-28 total hours
  - 40 LF railing with install: 12-20 total hours
  - Stair railing 12 ft with install: 10-16 total hours
  - Custom table (TIG, ground smooth): 12-20 total hours
  - Decorative repair: 2-6 total hours
  If your estimate is significantly outside these ranges, explain why.

CRITICAL RULES:
  1. Return hours for ALL 11 processes. Use 0.0 if not applicable.
  2. Do NOT return a total. The system computes the total.
  3. Include a brief "notes" for each process explaining your reasoning.
  4. If finish is "raw": clearcoat=0, paint=0, finish_prep=0.
  5. If finish is "powder_coat" or "galvanized": clearcoat=0, paint=0 (outsourced).
  6. If no installation: site_install=0.

Return ONLY valid JSON:
{
    "layout_setup": {"hours": 1.5, "notes": "reason"},
    "cut_prep": {"hours": 2.0, "notes": "reason"},
    "fit_tack": {"hours": 3.0, "notes": "reason"},
    "full_weld": {"hours": 4.0, "notes": "reason"},
    "grind_clean": {"hours": 1.5, "notes": "reason"},
    "finish_prep": {"hours": 1.0, "notes": "reason"},
    "clearcoat": {"hours": 0.0, "notes": "reason"},
    "paint": {"hours": 0.0, "notes": "reason"},
    "hardware_install": {"hours": 2.0, "notes": "reason"},
    "site_install": {"hours": 6.0, "notes": "reason"},
    "final_inspection": {"hours": 0.5, "notes": "reason"}
}""" % (
            job_type, job_type,
            piece_count, total_weight, weld_inches, total_sq_ft,
            hardware_count, finish,
            "Yes" if is_install else "No",
            "Yes" if is_onsite else "No",
            "\n".join(dimensions_summary) if dimensions_summary else "  (none specified)",
            "\n".join(material_lines) if material_lines else "  (no materials)",
            "\n".join(hardware_lines) if hardware_lines else "  (no hardware)",
            weld_section,
            piece_count, weld_inches,
        )
        return prompt

    def _build_weld_process_section(self, needs_tig, is_stainless, is_aluminum, weld_inches):
        """Build weld process reasoning section for labor prompt."""
        lines = []

        if needs_tig:
            lines.append("** THIS JOB REQUIRES TIG WELDING **")
            lines.append("")
            if is_stainless:
                lines.append("Material: STAINLESS STEEL")
                lines.append("  - TIG required — MIG on stainless produces poor corrosion resistance")
                lines.append("  - Back-purge required on closed joints (adds 20-30%% to weld time)")
                lines.append("  - Stainless labor multiplier: 1.3x on ALL processes (harder to work with)")
                lines.append("  - Post-weld passivation needed (add to finish_prep)")
            elif is_aluminum:
                lines.append("Material: ALUMINUM")
                lines.append("  - TIG or pulse-MIG required — standard MIG won't work")
                lines.append("  - Aluminum labor multiplier: 1.2x (different technique, more setup)")
                lines.append("  - Requires AC TIG with argon gas, 4043 or 5356 filler")
            else:
                lines.append("Material: MILD STEEL with TIG finish requirements")
                lines.append("  - Visible joints need TIG for clean appearance")
                lines.append("  - Hidden structural joints can use MIG (faster)")
                lines.append("  - Ground/blended welds add significant grind_clean time")

            lines.append("")
            lines.append("TIG WELDING RATE: 4-8 linear inches per hour (vs 8-15 for MIG)")
            lines.append("GRIND TIME: 75-100%% of weld time for ground smooth finish")
            lines.append("Estimated weld inches: %.0f → at TIG rate: %.1f-%.1f welding hours" % (
                weld_inches, weld_inches / 8.0, weld_inches / 4.0))
        else:
            lines.append("Standard mild steel — MIG welding (default)")
            lines.append("MIG WELDING RATE: 8-15 linear inches per hour")
            lines.append("Estimated weld inches: %.0f → at MIG rate: %.1f-%.1f welding hours" % (
                weld_inches, weld_inches / 15.0, weld_inches / 8.0))

        return "\n".join(lines)

    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API. Raises on failure (caller handles fallback)."""
        api_key = os.getenv("GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=90) as response:
            result = json.loads(response.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return text

    def _parse_response(self, response_text: str, user_rates: dict, is_onsite: bool) -> dict:
        """
        Parse Gemini JSON response into LaborEstimate.
        Validates all 11 processes are present.
        Computes total_hours by summing — never trusts AI total.
        Applies correct rate (inshop vs onsite) per process.
        """
        parsed = json.loads(response_text)

        # If AI returned a wrapped object, try to unwrap
        if isinstance(parsed, dict) and len(parsed) == 1:
            key = list(parsed.keys())[0]
            if isinstance(parsed[key], dict) and "layout_setup" in parsed[key]:
                parsed = parsed[key]

        processes = []
        for process_name in LABOR_PROCESSES:
            entry = parsed.get(process_name, {})
            if isinstance(entry, dict):
                hours = float(entry.get("hours", 0.0))
                notes = str(entry.get("notes", ""))
            else:
                # AI returned just a number
                hours = float(entry) if entry else 0.0
                notes = ""

            hours = max(hours, 0.0)  # Never negative
            rate = self._get_rate_for_process(process_name, is_onsite, user_rates)

            processes.append({
                "process": process_name,
                "hours": round(hours, 2),
                "rate": rate,
                "notes": notes,
            })

        # Compute total by summing — NEVER trust AI total
        total_hours = round(sum(p["hours"] for p in processes), 2)

        return {
            "processes": processes,
            "total_hours": total_hours,
            "flagged": False,
            "flag_reason": None,
        }

    def _fallback_estimate(self, material_list: dict, quote_params: dict, user_rates: dict) -> dict:
        """
        Rule-based fallback when Gemini is unavailable.
        Based on material quantities and industry rules of thumb.
        Conservative (slightly high rather than low).
        """
        items = material_list.get("items", [])
        hardware = material_list.get("hardware", [])
        weld_inches = material_list.get("weld_linear_inches", 0)
        sq_ft = material_list.get("total_sq_ft", 0)
        piece_count = sum(item.get("quantity", 1) for item in items)
        hardware_count = sum(h.get("quantity", 1) for h in hardware)

        fields = quote_params.get("fields", {})
        finish = str(fields.get("finish", "raw")).lower()
        install = str(fields.get("installation", fields.get("install_included", "no"))).lower()
        is_install = "install" in install or "yes" in install
        is_onsite = self._is_onsite_job(quote_params)

        # Rules of thumb (conservative)
        layout_setup = max(0.5, min(2.0, piece_count * 0.05 + 0.5))
        cut_prep = max(0.25, piece_count * 0.08)           # ~5 min per piece
        fit_tack = max(0.5, piece_count * 0.12)             # ~7 min per piece
        full_weld = max(0.25, weld_inches / 10.0)           # ~10 inches/hr average
        grind_clean = max(0.25, full_weld * 0.4)            # 40% of weld time
        finish_prep = 0.0
        clearcoat_hrs = 0.0
        paint_hrs = 0.0

        if "clear" in finish:
            finish_prep = max(0.5, sq_ft / 100.0)
            clearcoat_hrs = max(0.25, sq_ft / 50.0 * 0.5)
        elif "paint" in finish and "powder" not in finish:
            finish_prep = max(0.5, sq_ft / 80.0)
            paint_hrs = max(0.25, sq_ft / 50.0 * 0.75)
        elif "powder" in finish:
            finish_prep = max(0.25, sq_ft / 100.0)  # Prep for outsourced powder coat
            # Powder coat itself is outsourced — 0 in-house hours
        elif "galv" in finish:
            # Galvanizing is outsourced — no in-house finish work
            pass
        elif "raw" not in finish:
            # Unknown finish — assume paint
            finish_prep = max(0.5, sq_ft / 80.0)
            paint_hrs = max(0.25, sq_ft / 50.0 * 0.75)

        hardware_install = max(0.0, hardware_count * 0.4)   # ~25 min per item average
        # Check for motor (adds significant install time)
        for h in hardware:
            desc = str(h.get("description", "")).lower()
            if "operator" in desc or "motor" in desc:
                hardware_install += 1.5  # Motor install adds ~1.5 hrs

        site_install = 0.0
        if is_install:
            # Base on weight as a complexity proxy
            weight = material_list.get("total_weight_lbs", 0)
            if weight < 200:
                site_install = 3.0
            elif weight < 500:
                site_install = 5.0
            elif weight < 1000:
                site_install = 7.0
            else:
                site_install = 10.0
            # Concrete posts add time
            if "concrete" in str(fields.get("post_concrete", "")).lower() or \
               "full installation" in install:
                site_install += 2.0

        final_inspection = 0.5  # Always at least 0.5 hrs

        fallback_note = "Rule-based estimate — AI unavailable"

        hours_map = {
            "layout_setup": (layout_setup, f"{fallback_note}. {piece_count} pieces, complexity-scaled."),
            "cut_prep": (cut_prep, f"{fallback_note}. {piece_count} pieces at ~5 min each."),
            "fit_tack": (fit_tack, f"{fallback_note}. {piece_count} pieces at ~7 min each."),
            "full_weld": (full_weld, f"{fallback_note}. {weld_inches:.0f} linear inches at ~10 in/hr."),
            "grind_clean": (grind_clean, f"{fallback_note}. 40% of weld time."),
            "finish_prep": (finish_prep, f"{fallback_note}. Finish: {finish}."),
            "clearcoat": (clearcoat_hrs, f"{fallback_note}. {sq_ft:.0f} sq ft."),
            "paint": (paint_hrs, f"{fallback_note}. {sq_ft:.0f} sq ft."),
            "hardware_install": (hardware_install, f"{fallback_note}. {hardware_count} items."),
            "site_install": (site_install, f"{fallback_note}. {'Included' if is_install else 'Not included'}."),
            "final_inspection": (final_inspection, f"{fallback_note}. Standard walkthrough and touch-up."),
        }

        processes = []
        for process_name in LABOR_PROCESSES:
            hours, notes = hours_map[process_name]
            hours = round(max(hours, 0.0), 2)
            rate = self._get_rate_for_process(process_name, is_onsite, user_rates)
            processes.append({
                "process": process_name,
                "hours": hours,
                "rate": rate,
                "notes": notes,
            })

        total_hours = round(sum(p["hours"] for p in processes), 2)

        return {
            "processes": processes,
            "total_hours": total_hours,
            "flagged": False,
            "flag_reason": None,
        }

    def _get_rate_for_process(self, process: str, is_onsite: bool, user_rates: dict) -> float:
        """
        Apply correct rate per process.
        - Most processes use rate_inshop
        - site_install uses rate_onsite
        - If entire job is on-site (repair, mobile welding), ALL processes use rate_onsite
        """
        if is_onsite:
            return user_rates.get("rate_onsite", 145.00)
        if process == "site_install":
            return user_rates.get("rate_onsite", 145.00)
        return user_rates.get("rate_inshop", 125.00)

    def _is_onsite_job(self, quote_params: dict) -> bool:
        """Determine if the entire job is on-site (repairs done in place)."""
        fields = quote_params.get("fields", {})
        job_type = quote_params.get("job_type", "")

        # Repair jobs that can't be removed are on-site
        can_remove = str(fields.get("can_remove", "")).lower()
        if "in place" in can_remove or "on-site" in can_remove:
            return True

        # repair_structural with field work
        if job_type == "repair_structural":
            location = str(fields.get("repair_location", "")).lower()
            if "field" in location or "on-site" in location:
                return True

        return False
