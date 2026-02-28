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
        Main entry point.

        Args:
            material_list: MaterialList from Stage 3
            quote_params: QuoteParams from Stage 2 (has job_type, fields, notes)
            user_rates: {"rate_inshop": float, "rate_onsite": float} from user profile

        Returns:
            LaborEstimate dict matching CLAUDE.md contract
        """
        is_onsite = self._is_onsite_job(quote_params)

        # Try Gemini first, fall back to rule-based
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("No GEMINI_API_KEY — using rule-based fallback for labor estimate")
            return self._fallback_estimate(material_list, quote_params, user_rates)

        try:
            prompt = self._build_prompt(material_list, quote_params)
            response_text = self._call_gemini(prompt)
            estimate = self._parse_response(response_text, user_rates, is_onsite)
            return estimate
        except Exception as e:
            logger.warning(f"Gemini labor estimation failed: {e} — using fallback")
            return self._fallback_estimate(material_list, quote_params, user_rates)

    def _build_prompt(self, material_list: dict, quote_params: dict) -> str:
        """
        Build the Gemini prompt. Provides structured context and demands
        structured JSON output with per-process hour breakdowns.
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
                     "panel_config", "stair_angle", "num_risers"]:
            if key in fields:
                dimensions_summary.append(f"  - {key}: {fields[key]}")

        # Material descriptions
        material_lines = []
        for item in items[:15]:  # Cap at 15 to keep prompt reasonable
            material_lines.append(
                f"  - {item.get('description', 'unknown')} "
                f"(qty: {item.get('quantity', 1)}, cut: {item.get('cut_type', 'square')})"
            )

        # Hardware descriptions
        hardware_lines = []
        for h in hardware:
            hardware_lines.append(f"  - {h.get('description', 'unknown')} (qty: {h.get('quantity', 1)})")

        # Finish type
        finish = fields.get("finish", "raw")
        install = fields.get("installation", fields.get("install_included", "No"))
        is_install = "install" in str(install).lower() or "yes" in str(install).lower()

        # Is this on-site work?
        is_onsite = self._is_onsite_job(quote_params)

        prompt = f"""You are an expert metal fabrication labor estimator with 20+ years of shop experience.

TASK: Estimate labor hours per process for a {job_type} fabrication job.

JOB SUMMARY:
  Job type: {job_type}
  Total material pieces: {piece_count}
  Total weight: {total_weight:.1f} lbs
  Total weld linear inches: {weld_inches:.1f}
  Total surface area (for finishing): {total_sq_ft:.1f} sq ft
  Hardware items to install: {hardware_count}
  Finish type: {finish}
  Installation included: {"Yes" if is_install else "No"}
  On-site work (entire job): {"Yes" if is_onsite else "No"}

KEY DIMENSIONS:
{chr(10).join(dimensions_summary) if dimensions_summary else "  (none specified)"}

MATERIAL LIST:
{chr(10).join(material_lines) if material_lines else "  (no materials)"}

HARDWARE:
{chr(10).join(hardware_lines) if hardware_lines else "  (no hardware)"}

DOMAIN GUIDANCE — use these rules of thumb:
  - layout_setup: 0.5-2.0 hours depending on job complexity. Simple railing = 0.5, complex gate with motor = 1.5-2.0.
  - cut_prep: ~3-5 minutes per cut for tube, longer for thick material or miter cuts. Scale with piece count.
  - fit_tack: Most variable process. Simple frame = 1-2 hrs, complex assembly with multiple pieces = 4-8 hrs.
  - full_weld: Roughly 8-15 linear inches per hour for MIG on mild steel. Slower for TIG, thick material, or overhead/vertical position.
  - grind_clean: ~30-50% of weld time for standard finish. More for mirror/polish finish. Less for raw.
  - finish_prep: 0.5-1.0 hr for paint/clear coat prep (sanding, degreasing). 0 for raw steel.
  - clearcoat: ~0.5 hr per 50 sq ft. 0 if not clear coat finish.
  - paint: ~0.75 hr per 50 sq ft (primer + topcoat). 0 if not paint finish.
  - hardware_install: ~15-30 min per simple item (latch, hinge). 1-2 hrs for motor/operator install.
  - site_install: Highly variable. 2-4 hrs for railing, 4-8 hrs for gate with concrete, 6-12 hrs for stairs. 0 if no installation.
  - final_inspection: 0.25-0.5 hrs always. Includes function test, touch-up, client walkthrough.

REASONABLENESS CHECK:
  - Typical residential cantilever gate with motor and install: 16-28 total hours.
  - 40 linear feet of railing with install: 12-20 total hours.
  - Stair railing (12 ft) with install: 10-16 total hours.
  - Decorative repair (weld + refinish): 2-6 total hours.
  If your estimate is significantly outside these ranges, include a note explaining why.

CRITICAL RULES:
  1. Return hours for ALL 11 processes listed below. Use 0.0 if not applicable.
  2. Do NOT return a total. Do NOT sum the hours. The system computes the total.
  3. Include a brief "notes" string for each process explaining your reasoning.
  4. If finish is "raw", set clearcoat=0, paint=0, finish_prep=0.
  5. If finish is "powder_coat" or "galvanized", set clearcoat=0, paint=0 (outsourced, handled separately).
  6. If no installation, set site_install=0.

Return ONLY valid JSON in this exact format:
{{
    "layout_setup": {{"hours": 1.5, "notes": "reason"}},
    "cut_prep": {{"hours": 2.0, "notes": "reason"}},
    "fit_tack": {{"hours": 3.0, "notes": "reason"}},
    "full_weld": {{"hours": 4.0, "notes": "reason"}},
    "grind_clean": {{"hours": 1.5, "notes": "reason"}},
    "finish_prep": {{"hours": 1.0, "notes": "reason"}},
    "clearcoat": {{"hours": 0.0, "notes": "reason"}},
    "paint": {{"hours": 0.0, "notes": "reason"}},
    "hardware_install": {{"hours": 2.0, "notes": "reason"}},
    "site_install": {{"hours": 6.0, "notes": "reason"}},
    "final_inspection": {{"hours": 0.5, "notes": "reason"}}
}}"""
        return prompt

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
