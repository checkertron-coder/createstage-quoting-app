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

# Profile groups — each line is a category of available profiles
_PROFILE_GROUPS = {
    "sq_tube": "  Square tube: sq_tube_1x1_14ga, sq_tube_1.5x1.5_11ga, sq_tube_2x2_11ga, sq_tube_2x2_14ga, sq_tube_3x3_11ga, sq_tube_4x4_11ga",
    "rect_tube": "  Rectangular tube: rect_tube_2x3_11ga, rect_tube_2x4_11ga",
    "round_tube": "  Round tube: round_tube_1.5_14ga, round_tube_2_11ga",
    "flat_bar": "  Flat bar: flat_bar_1x0.125, flat_bar_1x0.1875, flat_bar_1x0.25, flat_bar_1.5x0.25, flat_bar_2x0.25, flat_bar_3x0.25",
    "angle": "  Angle: angle_1.5x1.5x0.125, angle_2x2x0.1875, angle_2x2x0.25",
    "sq_bar": "  Square bar: sq_bar_0.5, sq_bar_0.625, sq_bar_0.75",
    "round_bar": "  Round bar: round_bar_0.5, round_bar_0.625",
    "channel": "  Channel: channel_4x5.4, channel_6x8.2",
    "pipe": "  Pipe: pipe_3_sch40, pipe_4_sch40, pipe_6_sch40",
    "sheet_plate": "  Sheet/plate: sheet_11ga, sheet_14ga, sheet_16ga, plate_0.25, plate_0.375, plate_0.5",
    "dom_tube": "  DOM tube: dom_tube_1.75x0.120",
}

# Which profile groups each job type needs
_JOB_TYPE_PROFILES = {
    "cantilever_gate": ["sq_tube", "rect_tube", "flat_bar", "angle", "sq_bar", "pipe", "sheet_plate"],
    "swing_gate": ["sq_tube", "rect_tube", "flat_bar", "angle", "sq_bar", "pipe", "sheet_plate"],
    "straight_railing": ["sq_tube", "round_tube", "flat_bar", "sq_bar", "round_bar", "pipe"],
    "stair_railing": ["sq_tube", "round_tube", "flat_bar", "sq_bar", "round_bar", "pipe"],
    "balcony_railing": ["sq_tube", "round_tube", "flat_bar", "sq_bar", "round_bar", "pipe", "sheet_plate"],
    "ornamental_fence": ["sq_tube", "flat_bar", "sq_bar", "round_bar", "pipe"],
    "complete_stair": ["channel", "sq_tube", "angle", "sheet_plate", "round_tube", "pipe"],
    "spiral_stair": ["pipe", "round_tube", "sq_tube", "sheet_plate", "flat_bar"],
    "window_security_grate": ["sq_tube", "sq_bar", "flat_bar", "angle"],
    "furniture_table": ["sq_tube", "flat_bar", "round_bar", "round_tube", "sheet_plate"],
    "furniture_other": ["sq_tube", "flat_bar", "round_bar", "round_tube", "sheet_plate", "angle"],
    "utility_enclosure": ["sq_tube", "angle", "sheet_plate"],
    "bollard": ["pipe", "sheet_plate"],
    "repair_decorative": ["sq_tube", "flat_bar", "sq_bar", "round_bar", "round_tube", "sheet_plate"],
    "repair_structural": ["sq_tube", "rect_tube", "channel", "flat_bar", "angle", "sheet_plate"],
    "offroad_bumper": ["sq_tube", "rect_tube", "dom_tube", "sheet_plate", "round_tube"],
    "rock_slider": ["sq_tube", "rect_tube", "dom_tube", "sheet_plate"],
    "roll_cage": ["round_tube", "dom_tube", "sq_tube", "sheet_plate"],
    "exhaust_custom": ["round_tube", "pipe"],
    "trailer_fab": ["channel", "rect_tube", "sq_tube", "angle", "sheet_plate"],
    "structural_frame": ["channel", "sq_tube", "rect_tube", "angle", "sheet_plate", "pipe"],
    "sign_frame": ["sq_tube", "flat_bar", "angle", "sheet_plate"],
    "led_sign_custom": ["sq_tube", "flat_bar", "angle", "sheet_plate"],
    "product_firetable": ["sq_tube", "flat_bar", "sheet_plate"],
}

# All groups — used for custom_fab and unknown job types
_ALL_PROFILE_GROUPS = list(_PROFILE_GROUPS.keys())


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
            cutlist_model = os.getenv("GEMINI_CUTLIST_MODEL", "gemini-2.5-flash")
            response_text = self._call_gemini(prompt, model=cutlist_model)
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

        profiles_text = self._get_profiles_for_job_type(job_type)

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
%s
  NOTE on flat bar naming: width x thickness. flat_bar_1x0.125 = 1" wide x 1/8" thick (your "1x1/8" flat bar)

MATERIAL TYPES: square_tubing, round_tubing, flat_bar, angle_iron, channel, pipe, plate, mild_steel, stainless_304, aluminum_6061, dom_tubing

CUT TYPES: square, miter_45, miter_22.5, cope, notch, compound

CRITICAL RULES FOR CUSTOM FEATURES:
- If the description mentions a PATTERN (pyramid, grid, cross-hatch, inlay, layers, concentric squares), you MUST calculate and include ALL pieces for that pattern in the cut list.
- NEVER describe a custom feature only in notes — it must appear as real line items with quantities and lengths.
- Before generating ANY repeating pattern, work out the geometry step by step in the "notes" field of the FIRST item in that pattern group: what is the available space, what is the step interval, how many iterations fit, and what is each piece's length. Show the math.
- A square has exactly 4 sides. The quantity for any square layer is ALWAYS 4. Not 5, not 3 — exactly 4.
- Each piece in a single square layer must have the SAME length (all 4 sides of a square are equal).
- For pyramid/concentric patterns: calculate each layer separately. Start with the outermost square, step inward by the specified spacing, repeat until no more full squares fit. Each layer = 4 pieces.
- Example: 20" inside frame, 1/4" spacing per side. Layer 1: 4 pcs at 19.5". Layer 2: 4 pcs at 19.0". Layer 3: 4 pcs at 18.5". Continue until pieces are too small to be practical (< 3").
- Do NOT invent structural pieces (tabs, supports, connectors, spacers) that were not mentioned in the description. Only include pieces the user asked for.

RULES:
1. Every piece must have a SPECIFIC length in inches — no "TBD" or "varies".
2. Group related pieces (e.g., all frame members in "frame" group, all pickets in "infill" group).
3. List each UNIQUE piece separately with its quantity — don't combine different pieces.
4. For tables/furniture: exactly 4 legs per table (not 5). List each rail separately (2 long + 2 short).
5. Only include connection plates, gussets, and brackets if the user mentioned them or if they are structurally required for the design described.
6. Use miter_45 for visible frame corners. Use cope for tube-to-tube T-joints.
7. Be practical — use sizes a real fab shop would stock and cut.
8. Include piece_name for what the part IS (e.g., "leg", "top_rail", "picket").
9. Quantity means the number of IDENTICAL pieces to cut. Waste factor is handled separately — do not inflate quantity to account for waste.

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
]""" % (job_type, fields_text, weld_guidance, profiles_text)

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

    def _get_profiles_for_job_type(self, job_type: str) -> str:
        """Return only the profile lines relevant to a job type."""
        groups = _JOB_TYPE_PROFILES.get(job_type, _ALL_PROFILE_GROUPS)
        lines = []
        for group in groups:
            line = _PROFILE_GROUPS.get(group)
            if line:
                lines.append(line)
        return "\n".join(lines) if lines else "\n".join(
            _PROFILE_GROUPS[g] for g in _ALL_PROFILE_GROUPS
        )

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

        # Detect finish type to determine mill scale removal and build sequence
        all_fields_lower = " ".join(str(v) for v in fields.values()).lower()
        bare_metal_keywords = [
            "clear_coat", "clear coat", "clearcoat",
            "raw", "waxed", "raw_steel", "raw steel",
            "brushed", "brushed_steel", "brushed steel",
            "patina", "chemical_patina",
        ]
        coating_keywords = [
            "powder_coat", "powder coat", "powdercoat",
            "paint", "painted",
            "galvanized", "galvanize",
        ]
        has_coating = any(k in all_fields_lower for k in coating_keywords)
        needs_mill_scale_removal = (
            not has_coating
            and any(k in all_fields_lower for k in bare_metal_keywords)
        )

        if needs_mill_scale_removal:
            build_sequence = """
BUILD SEQUENCE (bare metal finish — mill scale removal AFTER welding):
This project has a bare metal finish (clear coat, brushed, raw, or patina). Mill scale must be removed for proper adhesion and appearance. Do this AFTER all welding is complete.
1. Layout and mark all pieces
2. Cut all pieces
3. Fit, tack, and weld main structural frame (MIG)
4. Grind frame welds smooth
5. Attach decorative/thin elements (TIG) using physical spacers where needed
6. Grind and blend all remaining welds
7. Mill scale removal on the completed assembly (vinegar bath, acid wash, flap disc grind, or needle scaler — use what you have available)
8. Wire brush, clean, and dry immediately after mill scale removal
9. Final finish (clear coat, wax, brushed finish, patina treatment, etc.)
Do NOT place mill scale removal before welding — it goes AFTER all welding and grinding is done.
"""
        else:
            build_sequence = """
BUILD SEQUENCE (paint/powder coat/galvanized finish — NO mill scale removal):
This project will be painted, powder coated, or galvanized. Mill scale removal is NOT needed. Do NOT include vinegar bath, acid wash, or mill scale removal steps.
1. Layout and mark all pieces
2. Cut all pieces
3. Degrease and scuff all pieces
4. Build and fully weld main structural frame (MIG)
5. Grind welds to required finish level
6. Attach decorative elements (TIG)
7. Surface prep for coating (sand, degrease, wipe down)
8. Paint or send out for powder coat / galvanizing
"""

        prompt = """You are an expert metal fabricator creating step-by-step build instructions.
A journeyman fabricator should be able to follow these instructions and build this project.

JOB TYPE: %s

PROJECT DETAILS:
%s

CUT LIST:
%s
%s%s
TASK: Generate a practical fabrication sequence — the exact steps a fabricator follows
to build this project from raw material to finished product.
Follow the BUILD SEQUENCE above as the template for step order.

RULES:
1. Follow the BUILD SEQUENCE order above. Do not rearrange steps or add mill scale removal if the sequence says to skip it.
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
]""" % (job_type, fields_text, cuts_text, weld_note, build_sequence)

        return prompt

    def _call_gemini(self, prompt: str, model: Optional[str] = None) -> str:
        """Call Gemini API. Raises on failure."""
        api_key = os.getenv("GEMINI_API_KEY")
        if model is None:
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

        with urllib.request.urlopen(req, timeout=180) as response:
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
