"""
AI-assisted cut list generator for custom/complex jobs.

Uses Gemini to interpret freeform designs into detailed cut lists.
Called by ALL 25 calculators when a user provides a design description.
The AI thinks through design first, then generates precise cut lists.

Fallback: if Gemini fails or returns invalid JSON, the calling calculator
uses its own template-based output. Never crashes.
"""

import json
import logging
import os
import re
import urllib.request
import urllib.error
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Valid cut types
VALID_CUT_TYPES = ("square", "miter_45", "miter_22.5", "cope", "notch", "compound")

# Valid weld processes
VALID_WELD_PROCESSES = ("mig", "tig", "stick", "none")

# Valid weld types
VALID_WELD_TYPES = (
    "butt", "fillet", "lap", "plug", "tack_only",
    "full_penetration", "skip", "none",
)


class AICutListGenerator:
    """
    Generates detailed cut lists by sending structured job info to Gemini.

    Usage:
        generator = AICutListGenerator()
        cuts = generator.generate_cut_list("furniture_table", fields)
        if cuts:
            # Use AI-generated cut list
        else:
            # Fall back to template calculator
    """

    def generate_cut_list(self, job_type: str, fields: dict) -> Optional[List[Dict]]:
        """
        Generate an AI-assisted cut list from job fields.

        Args:
            job_type: The job type string (e.g. "furniture_table")
            fields: Answered fields from Stage 2

        Returns:
            List of cut item dicts matching expanded MaterialItem schema, or None.
            Each dict has: description, material_type, profile, length_inches,
            quantity, cut_type, cut_angle, weld_process, weld_type, group, notes.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.info("No GEMINI_API_KEY — skipping AI cut list")
            return None

        try:
            prompt = self._build_prompt(job_type, fields)
            response_text = self._call_gemini(prompt)
            cuts = self._parse_response(response_text)
            if cuts and len(cuts) > 0:
                return cuts
            logger.warning("AI cut list returned empty — falling back to template")
            return None
        except Exception as e:
            logger.warning("AI cut list generation failed: %s — falling back to template", e)
            return None

    def generate_build_instructions(self, job_type: str, fields: dict,
                                     cut_list: List[Dict]) -> Optional[List[Dict]]:
        """
        Generate fabrication sequence / build instructions.

        Args:
            job_type: The job type string
            fields: Answered fields from Stage 2
            cut_list: The material items list (from calculator output)

        Returns:
            List of step dicts [{step, title, description, tools, duration_minutes,
            weld_process, safety_notes}], or None on failure.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.info("No GEMINI_API_KEY — skipping build instructions")
            return None

        try:
            prompt = self._build_instructions_prompt(job_type, fields, cut_list)
            response_text = self._call_gemini(prompt)
            steps = self._parse_instructions_response(response_text)
            if steps and len(steps) > 0:
                return steps
            logger.warning("AI build instructions returned empty — skipping")
            return None
        except Exception as e:
            logger.warning("AI build instructions failed: %s — skipping", e)
            return None

    def _build_prompt(self, job_type: str, fields: dict) -> str:
        """
        Build the Gemini prompt for cut list generation.

        The prompt instructs the AI to:
        1. Think through the design (structure, geometry, patterns)
        2. Calculate pattern geometry (spacing, counts, repetitions)
        3. Determine weld process per joint (MIG vs TIG)
        4. Generate a precise cut list with expanded schema
        """
        # Summarize fields — skip internal keys
        field_lines = []
        for key, val in fields.items():
            if key.startswith("_"):
                continue
            if val is not None and str(val).strip():
                field_lines.append("  - %s: %s" % (key, val))

        fields_text = "\n".join(field_lines) if field_lines else "  (no fields provided)"

        # Detect material and finish requirements for weld process guidance
        all_fields_text = " ".join(str(v) for v in fields.values()).lower()

        # TIG indicators
        tig_indicators = [
            "ground smooth", "blended", "furniture finish", "show quality",
            "visible welds", "tig", "glass top", "grind flush", "grind smooth",
            "seamless", "showroom", "polished", "mirror finish",
            "stainless", "aluminum", "chrome", "brushed finish",
        ]
        needs_tig = any(ind in all_fields_text for ind in tig_indicators)

        # Stainless detection
        is_stainless = "stainless" in all_fields_text or "304" in all_fields_text or "316" in all_fields_text
        is_aluminum = "aluminum" in all_fields_text or "6061" in all_fields_text

        # Build weld process guidance
        weld_guidance = self._build_weld_guidance(needs_tig, is_stainless, is_aluminum)

        prompt = """You are an expert metal fabricator with 25+ years of shop experience.
You are generating a DETAILED cut list for a fabrication project.

IMPORTANT: Think through this design BEFORE listing pieces.

JOB TYPE: %s

USER-PROVIDED INFORMATION:
%s

=== STEP 1: DESIGN ANALYSIS ===
Before listing any pieces, think through:
- What is the overall structure? (frame, enclosure, decorative, structural)
- What are the critical dimensions and how do pieces connect?
- Are there any repeating patterns? (pickets, panels, cross-members)
- What joints are visible vs hidden? (visible = better cuts, TIG welds)
- What is the load path? (structural members need to be sized appropriately)

=== STEP 2: PATTERN GEOMETRY ===
If there are repeating elements (pickets, slats, bars, cross-members):
- Calculate: count = (available_space / spacing) + 1
- Each repeating piece gets its OWN line item with correct quantity
- Do NOT lump different pieces into one line

=== STEP 3: WELD PROCESS DETERMINATION ===
For each joint, determine the weld process:
%s

=== STEP 4: GENERATE CUT LIST ===

AVAILABLE PROFILES (use ONLY these):
  Square tube: sq_tube_1x1_14ga, sq_tube_1.5x1.5_11ga, sq_tube_2x2_11ga, sq_tube_2x2_14ga, sq_tube_3x3_11ga, sq_tube_4x4_11ga
  Rectangular tube: rect_tube_2x3_11ga, rect_tube_2x4_11ga
  Round tube: round_tube_1.5_14ga, round_tube_2_11ga
  Flat bar: flat_bar_1x0.25, flat_bar_1.5x0.25, flat_bar_2x0.25, flat_bar_3x0.25
  Angle: angle_1.5x1.5x0.125, angle_2x2x0.1875, angle_2x2x0.25
  Square bar: sq_bar_0.5, sq_bar_0.625, sq_bar_0.75
  Round bar: round_bar_0.5, round_bar_0.625
  Channel: channel_4x5.4, channel_6x8.2
  Pipe: pipe_3_sch40, pipe_4_sch40, pipe_6_sch40
  Sheet/plate: sheet_11ga, sheet_14ga, sheet_16ga, plate_0.25, plate_0.375, plate_0.5
  DOM tube: dom_tube_1.75x0.120

MATERIAL TYPES: square_tubing, round_tubing, flat_bar, angle_iron, channel, pipe, plate, mild_steel, stainless_304, aluminum_6061, dom_tubing

CUT TYPES: square, miter_45, miter_22.5, cope, notch, compound

RULES:
1. Every piece must have a SPECIFIC length in inches — no "TBD" or "varies".
2. Group related pieces (e.g., all frame members in "frame" group, all pickets in "infill" group).
3. List each UNIQUE piece separately with its quantity — don't combine different pieces.
4. For tables/furniture: 4 legs (not 5), list each rail separately (2 long + 2 short).
5. Include connection plates, gussets, and brackets — these are real pieces that get cut.
6. Use miter_45 for visible frame corners. Use cope for tube-to-tube T-joints.
7. Be practical — use sizes a real fab shop would stock and cut.
8. Include piece_name for what the part IS (e.g., "leg", "top_rail", "picket").

Return ONLY valid JSON — an array of objects:
[
    {
        "description": "Table leg - 2x2 sq tube",
        "piece_name": "leg",
        "group": "frame",
        "material_type": "square_tubing",
        "profile": "sq_tube_2x2_11ga",
        "length_inches": 30.0,
        "quantity": 4,
        "cut_type": "miter_45",
        "cut_angle": 45.0,
        "weld_process": "tig",
        "weld_type": "fillet",
        "notes": "4 legs at 30 inches for 30-inch table height. Miter bottom for leveling feet."
    }
]""" % (job_type, fields_text, weld_guidance)

        return prompt

    def _build_weld_guidance(self, needs_tig, is_stainless, is_aluminum):
        """Build weld process guidance section for the prompt."""
        lines = []

        if needs_tig or is_stainless or is_aluminum:
            lines.append("THIS PROJECT REQUIRES TIG WELDING. Reasons:")
            if is_stainless:
                lines.append("  - Stainless steel material — TIG required for corrosion resistance")
            if is_aluminum:
                lines.append("  - Aluminum material — TIG (or specialized MIG) required")
            if needs_tig and not is_stainless and not is_aluminum:
                lines.append("  - Finish quality requires ground/blended welds — TIG produces cleaner joints")
            lines.append("")
            lines.append("Use weld_process: \"tig\" for ALL visible joints.")
            lines.append("Use weld_process: \"mig\" for hidden structural joints only.")
        else:
            lines.append("Standard mild steel project — default to MIG welding.")
            lines.append("Use weld_process: \"mig\" for most joints.")
            lines.append("Use weld_process: \"tig\" only if a specific joint needs show-quality finish.")

        lines.append("")
        lines.append("Weld types to use:")
        lines.append("  - \"fillet\" — most common, T-joints and lap joints")
        lines.append("  - \"butt\" — end-to-end joints (frame corners with miters)")
        lines.append("  - \"full_penetration\" — structural connections requiring full strength")
        lines.append("  - \"tack_only\" — temporary or removable connections")
        lines.append("  - \"plug\" — sheet to tube/frame connections")

        return "\n".join(lines)

    def _build_instructions_prompt(self, job_type: str, fields: dict,
                                    cut_list: List[Dict]) -> str:
        """Build the Gemini prompt for fabrication sequence."""
        # Summarize fields (skip internal keys)
        field_lines = []
        for key, val in fields.items():
            if key.startswith("_"):
                continue
            if val is not None and str(val).strip():
                field_lines.append("  - %s: %s" % (key, val))
        fields_text = "\n".join(field_lines) if field_lines else "  (none)"

        # Summarize cut list with weld info
        cut_lines = []
        for item in cut_list[:25]:
            desc = item.get("description", "piece")
            qty = item.get("quantity", 1)
            length = item.get("length_inches", 0)
            weld = item.get("cut_type", "square")
            cut_lines.append('  - %s (qty %d, %.0f", cut: %s)' % (desc, qty, length, weld))
        cuts_text = "\n".join(cut_lines) if cut_lines else "  (no items)"

        # Detect weld process from cut list
        weld_processes = set()
        for item in cut_list:
            wp = item.get("weld_process", "")
            if wp:
                weld_processes.add(wp)

        weld_note = ""
        if "tig" in weld_processes:
            weld_note = "\nNOTE: This project includes TIG welding. Steps involving TIG should specify appropriate gas (argon), filler rod, and amperage range."

        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        prompt = """You are an expert metal fabricator creating step-by-step build instructions.
A journeyman fabricator should be able to follow these instructions and build this project.

JOB TYPE: %s

PROJECT DETAILS:
%s

CUT LIST:
%s
%s
TASK: Generate a practical fabrication sequence — the exact steps a fabricator follows
to build this project from raw material to finished product.

RULES:
1. Steps in logical build order: layout/mark → cut → deburr → fit/tack → weld → grind → finish
2. Each step must be SPECIFIC and ACTIONABLE — not generic. Reference actual pieces from the cut list.
3. Include the correct tools for each step (chop saw, band saw, TIG welder, MIG welder, angle grinder, etc.).
4. Specify weld process (MIG vs TIG) for each welding step.
5. Estimate realistic duration in minutes for each step.
6. Include safety notes where relevant (PPE, ventilation for galvanized, etc.).
7. 8-15 steps is typical. Group related operations but don't skip important steps.
8. Include quality checks: square check after tacking, level check, fit check before welding.

Return ONLY valid JSON — an array of step objects:
[
    {
        "step": 1,
        "title": "Layout & Mark All Pieces",
        "description": "Transfer cut list dimensions to raw stock using tape measure and soapstone. Mark miter angles on frame pieces using speed square. Number each piece for assembly reference.",
        "tools": ["tape measure", "soapstone", "speed square", "sharpie"],
        "duration_minutes": 25,
        "weld_process": null,
        "safety_notes": "Wear gloves when handling raw steel — sharp edges and mill scale."
    }
]""" % (job_type, fields_text, cuts_text, weld_note)

        return prompt

    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API. Raises on failure."""
        api_key = os.getenv("GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "%s:generateContent?key=%s" % (model, api_key)
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

    def _parse_response(self, response_text: str) -> Optional[List[Dict]]:
        """Parse Gemini response into cut list items with expanded schema."""
        try:
            # Try direct JSON parse
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON array from markdown code block
            match = re.search(r'\[[\s\S]*\]', response_text)
            if not match:
                logger.warning("Could not find JSON array in AI response")
                return None
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Failed to parse extracted JSON from AI response")
                return None

        if not isinstance(data, list):
            logger.warning("AI response is not a list")
            return None

        # Validate and normalize each item
        validated = []
        for item in data:
            if not isinstance(item, dict):
                continue

            # Parse cut_type — normalize variants
            cut_type = str(item.get("cut_type", "square")).lower().strip()
            if cut_type not in VALID_CUT_TYPES:
                # Try to match common variants
                if "miter" in cut_type and "22" in cut_type:
                    cut_type = "miter_22.5"
                elif "miter" in cut_type or "45" in cut_type:
                    cut_type = "miter_45"
                elif "cope" in cut_type:
                    cut_type = "cope"
                elif "notch" in cut_type:
                    cut_type = "notch"
                else:
                    cut_type = "square"

            # Parse weld_process
            weld_process = str(item.get("weld_process", "mig")).lower().strip()
            if weld_process not in VALID_WELD_PROCESSES:
                weld_process = "mig"

            # Parse weld_type
            weld_type = str(item.get("weld_type", "fillet")).lower().strip()
            if weld_type not in VALID_WELD_TYPES:
                weld_type = "fillet"

            cut = {
                "description": str(item.get("description", "Cut piece")),
                "piece_name": str(item.get("piece_name", "")),
                "group": str(item.get("group", "general")),
                "material_type": str(item.get("material_type", "mild_steel")),
                "profile": str(item.get("profile", "sq_tube_1.5x1.5_11ga")),
                "length_inches": float(item.get("length_inches", 12.0)),
                "quantity": int(item.get("quantity", 1)),
                "cut_type": cut_type,
                "cut_angle": float(item.get("cut_angle", 90.0)),
                "weld_process": weld_process,
                "weld_type": weld_type,
                "notes": str(item.get("notes", "")),
            }

            # Sanity checks
            if cut["length_inches"] <= 0:
                cut["length_inches"] = 12.0
            if cut["quantity"] <= 0:
                cut["quantity"] = 1
            if cut["cut_angle"] <= 0 or cut["cut_angle"] > 90:
                cut["cut_angle"] = 90.0 if cut["cut_type"] == "square" else 45.0

            validated.append(cut)

        return validated if validated else None

    def _parse_instructions_response(self, response_text: str) -> Optional[List[Dict]]:
        """Parse Gemini response into build instruction steps."""
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            match = re.search(r'\[[\s\S]*\]', response_text)
            if not match:
                return None
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None

        if not isinstance(data, list):
            return None

        validated = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            step = {
                "step": int(item.get("step", i + 1)),
                "title": str(item.get("title", "Step %d" % (i + 1))),
                "description": str(item.get("description", "")),
                "tools": item.get("tools", []),
                "duration_minutes": int(item.get("duration_minutes", 15)),
                "weld_process": item.get("weld_process"),
                "safety_notes": str(item.get("safety_notes", "")),
            }
            if not isinstance(step["tools"], list):
                step["tools"] = [str(step["tools"])]
            validated.append(step)

        return validated if validated else None
