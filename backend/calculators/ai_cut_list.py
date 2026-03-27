"""
AI-assisted cut list generator for custom/complex jobs.

Uses Claude API to interpret freeform designs into detailed cut lists.
Called by ALL 25 calculators when a user provides a design description.
The AI thinks through design first, then generates precise cut lists.

Fallback: if Claude fails or returns invalid JSON, the calling calculator
uses its own template-based output. Never crashes.
"""

import json
import logging
import re
from typing import Optional, List, Dict

from ..claude_client import call_fast, is_configured

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BANNED TERM REPLACEMENTS — customer-facing text must use correct shop terms
# ---------------------------------------------------------------------------
# Maps banned phrases to their correct replacements. Applied to build
# instruction steps before returning to the caller.

BANNED_TERM_REPLACEMENTS = {
    # Vinegar bath cleanup — SHOP: CreateStage
    "baking soda": "dish soap",
    "neutralize with baking soda": "scrub with dish soap and red scotch-brite pad",
    "baking soda solution": "dish soap and warm water",
    "compressed air": "clean towel",
    "blow dry": "towel dry",
    "wire brush": "red scotch-brite pad",
    "chemical neutralizer": "dish soap",
    "neutralizing agent": "dish soap",
    # Decorative stock prep grind spec — 40 grit IS the finish
    "80 grit then 120 grit": "40-grit flap disc (this IS the finish)",
    "80-grit followed by 120-grit": "40-grit flap disc (this IS the finish)",
    "120 grit for final finish": "40-grit flap disc for final finish",
    "progressive grit sequence": "single-pass 40-grit flap disc",
    # Decorative assembly — sequential, not dry-fit
    "dry fit entire pattern": "assemble sequentially — measure, position, weld each piece",
    "dry-fit entire pattern": "assemble sequentially — measure, position, weld each piece",
    "dry fit all pieces": "assemble one piece at a time",
    "lay out all pieces first": "assemble sequentially from outside in",
    "position all pieces before welding": "position and weld one piece at a time",
    "pre-position entire assembly": "assemble sequentially — one piece at a time",
    # Leveler installation — never drill into hollow tube
    "drill into tube": "weld in threaded bung",
    "drill into the tube": "weld in threaded bung",
    "drill through tube wall": "weld in threaded bung",
    "drill and tap tube wall": "weld in threaded bung",
    "tap directly into tube": "weld in threaded bung",
    "self-tapping screw into tube": "weld in threaded bung and thread leveling foot",
    # Additional drill/tap patterns for leveler feet
    "drill a pilot hole": "weld a threaded bung",
    "drill and tap": "weld in a threaded bung and tap",
    "drill a hole in the bottom": "weld a threaded bung into the bottom",
    "drill a hole into the bottom": "weld a threaded bung into the bottom",
    "tap a thread into the bottom": "weld a threaded bung into the bottom",
    "drill press, hand drill, tap set, cutting fluid": "MIG welder, threaded bungs",
    # Filing — always use flap disc or die grinder
    "file the edges": "deburr with flap disc",
    "use a file": "use a flap disc",
    "hand file": "flap disc or die grinder",
    "file smooth": "grind smooth with flap disc",
    # Pre-paint cleaning — product is surface prep solvent, not degreaser
    "degreaser wipe-down": "surface prep solvent wipe-down",
    "degreaser wipe": "surface prep solvent wipe",
    "degreaser spray": "surface prep solvent",
    "clean with degreaser": "wipe with surface prep solvent and clean rags",
    "degreaser": "surface prep solvent",
}

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
    "hss": "  HSS (structural tube): hss_4x4_0.25, hss_6x4_0.25",
    "punched_channel": "  Punched channel: punched_channel_1.25x0.5x14ga, punched_channel_1.5x0.75x14ga",
    # Aluminum profiles
    "al_sq_tube": "  Aluminum square tube: al_sq_tube_1x1_0.125, al_sq_tube_1.5x1.5_0.125, al_sq_tube_2x2_0.125",
    "al_rect_tube": "  Aluminum rectangular tube: al_rect_tube_1x2_0.125",
    "al_flat_bar": "  Aluminum flat bar: al_flat_bar_1x0.125, al_flat_bar_1.5x0.125, al_flat_bar_2x0.25",
    "al_angle": "  Aluminum angle: al_angle_1.5x1.5x0.125, al_angle_2x2x0.125",
    "al_round_tube": "  Aluminum round tube: al_round_tube_1.5_0.125",
    "al_sheet": "  Aluminum sheet: al_sheet_0.040, al_sheet_0.063, al_sheet_0.080, al_sheet_0.125, al_sheet_0.190",
}

# Which profile groups each job type needs
_JOB_TYPE_PROFILES = {
    "cantilever_gate": ["sq_tube", "rect_tube", "flat_bar", "angle", "sq_bar", "pipe", "sheet_plate", "hss"],
    "swing_gate": ["sq_tube", "rect_tube", "flat_bar", "angle", "sq_bar", "pipe", "sheet_plate"],
    "straight_railing": ["sq_tube", "round_tube", "flat_bar", "sq_bar", "round_bar", "pipe", "punched_channel"],
    "stair_railing": ["sq_tube", "round_tube", "flat_bar", "sq_bar", "round_bar", "pipe", "punched_channel"],
    "balcony_railing": ["sq_tube", "round_tube", "flat_bar", "sq_bar", "round_bar", "pipe", "sheet_plate", "punched_channel"],
    "ornamental_fence": ["sq_tube", "flat_bar", "sq_bar", "round_bar", "pipe", "punched_channel"],
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
    "sign_frame": ["sq_tube", "flat_bar", "angle", "sheet_plate", "al_sq_tube", "al_flat_bar", "al_angle", "al_sheet"],
    "led_sign_custom": ["sq_tube", "flat_bar", "angle", "sheet_plate", "al_sq_tube", "al_flat_bar", "al_angle", "al_sheet", "al_rect_tube"],
    "product_firetable": ["sq_tube", "flat_bar", "sheet_plate"],
}

# All groups — used for custom_fab and unknown job types
_ALL_PROFILE_GROUPS = list(_PROFILE_GROUPS.keys())


def _strip_banned_terms_from_steps(steps):
    # type: (List[Dict]) -> None
    """
    Replace banned terms in build instruction steps with correct shop terms.

    Modifies steps in-place. Handles description, safety_notes, and tools fields.
    Case-insensitive matching, preserves original casing in surrounding text.
    Sorts replacements longest-first to prevent partial matches
    (e.g., "baking soda solution" must match before "baking soda").
    """
    # Sort by length of banned term (longest first) to prevent partial matches
    sorted_replacements = sorted(
        BANNED_TERM_REPLACEMENTS.items(),
        key=lambda x: len(x[0]),
        reverse=True
    )

    for step in steps:
        for field_name in ("description", "safety_notes"):
            text = step.get(field_name, "")
            if not text:
                continue
            for banned, replacement in sorted_replacements:
                pattern = re.compile(re.escape(banned), re.IGNORECASE)
                text = pattern.sub(replacement, text)
            step[field_name] = text

        # Clean tools list/string
        tools = step.get("tools", "")
        if isinstance(tools, list):
            cleaned_tools = []
            for tool in tools:
                tool_str = str(tool)
                for banned, replacement in sorted_replacements:
                    pattern = re.compile(re.escape(banned), re.IGNORECASE)
                    tool_str = pattern.sub(replacement, tool_str)
                cleaned_tools.append(tool_str)
            step["tools"] = cleaned_tools
        elif isinstance(tools, str):
            for banned, replacement in sorted_replacements:
                pattern = re.compile(re.escape(banned), re.IGNORECASE)
                tools = pattern.sub(replacement, tools)
            step["tools"] = tools


def _build_geometry_summary(cut_list):
    # type: (List[Dict]) -> str
    """
    Build a geometry summary from the cut list for the build instructions prompt.

    Groups items by their 'group' field, lists piece counts and unique lengths,
    and detects uniform step patterns (concentric/pyramid layers).
    Adds HARD CONSTRAINT for decorative layer counts.

    Returns a GEOMETRY SUMMARY block string, or empty string if no groups found.
    """
    if not cut_list:
        return ""

    groups = {}  # type: Dict[str, List[Dict]]
    for item in cut_list:
        group = item.get("group", "general")
        if group not in groups:
            groups[group] = []
        groups[group].append(item)

    if not groups:
        return ""

    # Count decorative layers and spacers from cut list
    layer_count = 0
    spacer_count = 0
    for item in cut_list:
        desc_lower = item.get("description", "").lower()
        group_lower = item.get("group", "").lower()
        qty = item.get("quantity", 1)
        is_decorative = (
            "layer" in desc_lower or "decorative" in desc_lower
            or "pattern" in group_lower or "decorative" in group_lower
        )
        if is_decorative and "spacer" not in desc_lower:
            layer_count += 1  # each unique line item = 1 layer
        if "spacer" in desc_lower:
            spacer_count += qty

    lines = ["GEOMETRY SUMMARY (from cut list — use these dimensions in build steps):"]

    for group_name, items in sorted(groups.items()):
        total_pieces = sum(i.get("quantity", 1) for i in items)
        lengths = sorted(set(i.get("length_inches", 0) for i in items))
        profiles = sorted(set(i.get("profile", "") for i in items))

        lines.append("  %s: %d pieces, profiles: %s" % (
            group_name, total_pieces, ", ".join(profiles) if profiles else "mixed"))
        if len(lengths) > 1:
            length_strs = ["%.1f\"" % l for l in lengths]
            lines.append("    lengths: %s" % ", ".join(length_strs))

            # Detect uniform step pattern
            if len(lengths) >= 3:
                diffs = [round(lengths[i+1] - lengths[i], 2) for i in range(len(lengths) - 1)]
                if len(set(diffs)) == 1:
                    lines.append("    uniform step: %.1f\" increment (%d layers)" % (
                        abs(diffs[0]), len(lengths)))
        elif len(lengths) == 1:
            lines.append("    all pieces: %.1f\"" % lengths[0])

    # Add hard constraint for decorative layers
    if layer_count > 0:
        lines.append("")
        lines.append("HARD CONSTRAINT: The build sequence MUST install exactly %d decorative layers." % layer_count)
        lines.append("Each layer MUST use the EXACT dimensions from the cut list above.")
        lines.append("Do NOT consolidate layers. Do NOT skip layers. Do NOT change dimensions.")
        if layer_count > 5:
            lines.append("If the cut list says %d layers, the build sequence must reference all %d layers." % (
                layer_count, layer_count))
    if spacer_count > 0:
        lines.append("Spacers: %d total spacer pieces in the cut list." % spacer_count)

    return "\n".join(lines)


class AICutListGenerator:
    """
    Generates detailed cut lists by sending structured job info to Claude API.

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
        if not is_configured():
            logger.info("No AI provider configured — skipping AI cut list")
            return None

        try:
            prompt = self._build_prompt(job_type, fields)
            response_text = self._call_ai(prompt)
            cuts = self._parse_response(response_text)
            if cuts and len(cuts) > 0:
                return cuts
            logger.warning("AI cut list returned empty — falling back to template")
            return None
        except Exception as e:
            logger.warning("AI cut list generation failed: %s — falling back to template", e)
            return None

    def generate_build_instructions(self, job_type: str, fields: dict,
                                     cut_list: List[Dict],
                                     enforced_dimensions: Optional[Dict] = None) -> Optional[List[Dict]]:
        """
        Generate fabrication sequence / build instructions.

        Args:
            job_type: The job type string
            fields: Answered fields from Stage 2
            cut_list: The material items list (from calculator output)
            enforced_dimensions: Optional dict of dimension name → value that
                must appear verbatim in the build instructions prompt.

        Returns:
            List of step dicts [{step, title, description, tools, duration_minutes,
            weld_process, safety_notes}], or None on failure.
        """
        if not is_configured():
            logger.info("No AI provider configured — skipping build instructions")
            return None

        try:
            prompt = self._build_instructions_prompt(
                job_type, fields, cut_list,
                enforced_dimensions=enforced_dimensions)
            logger.info("BUILD INSTRUCTIONS: calling AI with prompt length=%d", len(prompt))
            response_text = self._call_ai(prompt)
            logger.info("BUILD INSTRUCTIONS: AI returned %d chars",
                        len(response_text) if response_text else 0)
            steps = self._parse_instructions_response(response_text)
            if steps and len(steps) > 0:
                return steps
            logger.warning("AI build instructions returned empty — skipping")
            return None
        except Exception as e:
            logger.warning("AI build instructions failed: %s — skipping", e, exc_info=True)
            return None

    def _build_prompt(self, job_type: str, fields: dict) -> str:
        """Build the AI prompt for cut list generation."""
        # Summarize fields — skip internal keys
        field_lines = []
        for key, val in fields.items():
            if key.startswith("_") and not key.startswith("_ai_"):
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

        # Material type detection — uses question tree field first, falls back to description
        material_constraint, is_aluminum, is_stainless = self._detect_material_constraint(fields)
        # Legacy fallback for jobs without material_type field
        if not material_constraint and not is_aluminum and not is_stainless:
            if "stainless" in all_fields_text or "304" in all_fields_text or "316" in all_fields_text:
                is_stainless = True
            if "aluminum" in all_fields_text or "6061" in all_fields_text:
                is_aluminum = True

        # Build weld process guidance
        weld_guidance = self._build_weld_guidance(needs_tig, is_stainless, is_aluminum)

        # Gauge / thickness constraint
        gauge_constraint = self._detect_gauge_constraint(fields)

        profiles_text = self._get_profiles_for_job_type(job_type)

        # Filter profiles based on material selection
        if is_aluminum and material_constraint:
            # User explicitly chose aluminum — ONLY aluminum profiles
            al_groups = ["al_sq_tube", "al_rect_tube", "al_flat_bar",
                         "al_angle", "al_round_tube", "al_sheet"]
            al_lines = []
            for ag in al_groups:
                line = _PROFILE_GROUPS.get(ag)
                if line:
                    al_lines.append(line)
            profiles_text = "\n".join(al_lines)
        elif is_aluminum:
            # Detected from description — add aluminum but keep steel (legacy behavior)
            al_groups = ["al_sq_tube", "al_rect_tube", "al_flat_bar",
                         "al_angle", "al_round_tube", "al_sheet"]
            for ag in al_groups:
                line = _PROFILE_GROUPS.get(ag)
                if line and line not in profiles_text:
                    profiles_text += "\n" + line
        elif material_constraint and not is_stainless:
            # User explicitly chose carbon steel — strip any aluminum profiles
            profile_lines = profiles_text.split("\n")
            profiles_text = "\n".join(l for l in profile_lines if "Aluminum" not in l)

        # Inject relevant fabrication knowledge
        finish_type = str(fields.get("finish", fields.get("finish_type", "")) or "")
        description = str(fields.get("description", "") or "")
        has_stainless = is_stainless
        from .fab_knowledge import get_relevant_knowledge
        knowledge_snippet = get_relevant_knowledge(
            job_type, finish_type, has_stainless, description=description)
        knowledge_block = ""
        if knowledge_snippet:
            knowledge_block = """
SHOP KNOWLEDGE BASE (use this to inform your output):
%s
---
""" % knowledge_snippet

        # Shop equipment context (injected via _shop_context field)
        shop_context_block = str(fields.get("_shop_context", "") or "")

        # Build structured context blocks for compound/complex jobs
        context_blocks = self._build_field_context(job_type, fields)

        # Material context — from explicit selection or legacy detection
        material_context = material_constraint
        if not material_context and is_aluminum:
            material_context = """
MATERIAL CONTEXT — ALUMINUM:
This project uses ALUMINUM, not steel. You MUST:
1. Use al_* profile keys (e.g., al_sq_tube_2x2_0.125, al_sheet_0.125) — NOT steel keys.
2. Set material_type to "aluminum_6061" for all items.
3. For sheet/panel coverage, specify al_sheet_* profiles with area dimensions in notes.
4. Weld process: use "tig" for all joints (aluminum requires TIG or specialized pulsed MIG).
5. Do NOT use steel profiles (sq_tube_*, flat_bar_*, etc.) for aluminum projects.
"""

        prompt = """You are an expert metal fabricator generating a cut list for a fabrication project.

JOB TYPE: %s
%s%s%s
PROJECT INFO:
%s
%s
WELD PROCESS GUIDANCE:
%s
%s
AVAILABLE PROFILES (use ONLY these):
%s
  NOTE on flat bar naming: width x thickness. flat_bar_1x0.125 = 1" wide x 1/8" thick (your "1x1/8" flat bar)

MATERIAL TYPES: square_tubing, round_tubing, flat_bar, angle_iron, channel, pipe, plate, mild_steel, stainless_304, aluminum_6061, dom_tubing

CUT TYPES: square, miter_45, miter_22.5, cope, notch, compound

RULES:
1. Every piece must have a SPECIFIC length in inches — no "TBD" or "varies".
2. Group related pieces (e.g., all frame members in "frame" group, all pickets in "infill" group).
3. List each UNIQUE piece separately with its quantity — don't combine different pieces.
4. Only include connection plates, gussets, and brackets if the user mentioned them or if they are structurally required.
5. Be practical — use sizes a real fab shop would stock and cut.
6. Include piece_name for what the part IS (e.g., "leg", "top_rail", "picket").
7. Each line = one cuttable piece, max 240 inches. Use quantity for identical pieces.

SHEET/PLATE RULES:
For any sheet or plate item (profile contains "sheet" or "plate"), you MUST also include:
- "width_inches": the WIDTH of the piece (length_inches is the longer dimension)
- "sheet_stock_size": [W, H] — the standard stock sheet to order. Options: [48,96], [48,120], [48,144], [60,120], [60,144]
  Pick the SMALLEST standard sheet where BOTH piece dimensions fit (piece can be rotated).
  If NO standard sheet fits, use [60,144] and set "seaming_required": true
- "sheets_needed": how many stock sheets this line item requires (usually 1 per piece, but if cutting multiple small pieces from one sheet, group them)

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
    },
    {
        "description": "Sign cabinet back panel - al sheet",
        "piece_name": "back_panel",
        "group": "cabinet",
        "material_type": "aluminum_6061",
        "profile": "al_sheet_0.063",
        "length_inches": 138.0,
        "width_inches": 28.0,
        "quantity": 1,
        "cut_type": "square",
        "cut_angle": 90.0,
        "weld_process": "tig",
        "weld_type": "butt",
        "sheet_stock_size": [48, 144],
        "sheets_needed": 1,
        "notes": "Back panel 138x28, fits on 4'x12' sheet."
    }
]""" % (job_type, knowledge_block, shop_context_block, material_context, fields_text,
        context_blocks, weld_guidance, gauge_constraint, profiles_text)

        return prompt

    def _build_field_context(self, job_type, fields):
        # type: (str, dict) -> str
        """
        Build structured context blocks from fields for compound/complex jobs.

        Provides explicit guidance to the AI about compound elements like
        adjacent fence sections, bottom guide types, mounting styles, etc.
        so cuts are generated for the ENTIRE job, not just the primary element.
        """
        blocks = []

        # --- Cantilever gate compound job context ---
        if job_type == "cantilever_gate":
            # Bottom guide context
            bottom_guide = str(fields.get("bottom_guide", ""))
            if "No bottom guide" in bottom_guide or "top-hung" in bottom_guide.lower():
                blocks.append(
                    "BOTTOM GUIDE: None — this is a top-hung (cantilever-only) gate. "
                    "Do NOT include any bottom guide rail or embedded track in the cut list."
                )
            elif "Embedded" in bottom_guide:
                blocks.append(
                    "BOTTOM GUIDE: Embedded track (flush with ground). "
                    "Include a C4x5.4 channel as the embedded guide rail, "
                    "length = gate total length + 24\" approach."
                )
            elif bottom_guide:
                blocks.append(
                    "BOTTOM GUIDE: Surface mount guide roller. "
                    "Include a 2\"x2\"x1/4\" angle iron guide rail, "
                    "length = gate total length + 24\" approach."
                )

            # Gate length constraint
            clear_width_str = fields.get("clear_width", "")
            if clear_width_str:
                try:
                    cw_ft = float(str(clear_width_str).split()[0])
                    gate_total_ft = cw_ft * 1.5
                    tail_ft = gate_total_ft - cw_ft
                    blocks.append(
                        "GATE PANEL LENGTH (HARD CONSTRAINT — DO NOT CHANGE):\n"
                        "  Total gate panel = %.1f ft (%.0f\")\n"
                        "  Gate face (opening) = %.1f ft (%.0f\")\n"
                        "  Counterbalance tail = %.1f ft (%.0f\")\n"
                        "  Formula: opening × 1.5. The 'available space' field is the MAXIMUM, "
                        "not the required tail length. Never make the tail longer than 50%% of the opening."
                        % (gate_total_ft, gate_total_ft * 12,
                           cw_ft, cw_ft * 12,
                           tail_ft, tail_ft * 12)
                    )
                except (ValueError, IndexError):
                    pass

            # Gate height constraint — prevent confusion with fence lengths
            height_str = fields.get("height", fields.get("clear_height", ""))
            if height_str:
                try:
                    h_ft = float(str(height_str).split()[0])
                    h_in = h_ft * 12
                    blocks.append(
                        "GATE HEIGHT (HARD CONSTRAINT — DO NOT CHANGE):\n"
                        "  Gate height = %.1f ft (%.0f\")\n"
                        "  This is the HEIGHT of the gate and fence, NOT a length measurement.\n"
                        "  Do NOT confuse fence section lengths (e.g. 15 ft, 13 ft) with gate height.\n"
                        "  Picket length = height minus 2\" (for ground clearance).\n"
                        "  Vertical stile length = height minus rail widths."
                        % (h_ft, h_in)
                    )
                except (ValueError, IndexError):
                    pass

            # Picket material constraint
            infill_type = fields.get("infill_type", "")
            if "Picket" in str(infill_type):
                from .cantilever_gate import _resolve_picket_profile
                profile = _resolve_picket_profile(fields, infill_type)
                spacing = fields.get("picket_spacing", "4\" on-center")
                blocks.append(
                    "PICKET MATERIAL (HARD CONSTRAINT — DO NOT CHANGE):\n"
                    "  Profile: %s\n"
                    "  Spacing: %s\n"
                    "  Use EXACTLY this profile for all pickets. Do NOT substitute "
                    "square tube, round tube, or any other material for pickets."
                    % (profile, spacing)
                )

            # Overhead beam constraint
            bottom_guide_check = str(fields.get("bottom_guide", ""))
            if "No bottom guide" in bottom_guide_check or "top-hung" in bottom_guide_check.lower():
                blocks.append(
                    "OVERHEAD BEAM (HARD CONSTRAINT):\n"
                    "  Quantity: 1 (ONE beam spanning between the two rear carriage posts)\n"
                    "  Profile: hss_4x4_0.25 for gates under 800 lbs, hss_6x4_0.25 for heavier\n"
                    "  Length: gate panel length + 24\" (12\" overhang each side)\n"
                    "  Do NOT use qty 2. It is ONE continuous beam."
                )

            # Post dimensions context — calculator-verified values
            height_str = fields.get("height", fields.get("clear_height", ""))
            post_concrete = fields.get("post_concrete", "Yes")
            if height_str:
                try:
                    h_ft = float(str(height_str).split()[0])
                    h_in = h_ft * 12
                    above_grade_in = h_in + 2  # 2" clearance above gate
                    embed_in = 42.0 if "No" not in str(post_concrete) else 0.0
                    total_in = above_grade_in + embed_in
                    gate_post_count = 3  # default
                    post_count_str = str(fields.get("post_count", "3"))
                    if "2" in post_count_str:
                        gate_post_count = 2
                    elif "4" in post_count_str:
                        gate_post_count = 4

                    # Include post profile key if injected by calculator
                    post_profile_hint = ""
                    injected_profile = fields.get("_post_profile_key", "")
                    if injected_profile:
                        post_profile_hint = (
                            "  Post profile key (use this exact value): %s\n"
                            % injected_profile
                        )

                    post_block = (
                        "POST DIMENSIONS (calculator-verified — use EXACTLY):\n"
                        "%s"
                        "  Above grade: %.0fin + %.0fin embed = %.0fin total (%.1f ft)\n"
                        "  Gate posts: %d\n"
                        % (post_profile_hint,
                           above_grade_in, embed_in, total_in, total_in / 12.0,
                           gate_post_count)
                    )

                    # Calculate fence posts if applicable
                    adjacent = str(fields.get("adjacent_fence", ""))
                    if "Yes" in adjacent:
                        import math
                        fence_post_count = 0
                        try:
                            fence_post_count = int(float(str(fields.get("fence_post_count", "0")).strip()))
                        except (ValueError, TypeError):
                            pass
                        if fence_post_count == 0:
                            s1 = float(str(fields.get("fence_side_1_length", "0")).strip() or "0")
                            s2 = float(str(fields.get("fence_side_2_length", "0")).strip() or "0")
                            if s1 > 0:
                                fence_post_count += max(1, round(s1 / 7))
                            if s2 > 0 and "both" in adjacent.lower():
                                fence_post_count += max(1, round(s2 / 7))
                        post_block += "  Fence posts: %d\n" % fence_post_count
                        post_block += "  Total posts: %d\n" % (gate_post_count + fence_post_count)
                    post_block += (
                        "  All posts must be cut to EXACTLY %.0f inches (%.1f ft). "
                        "Do NOT calculate your own post length."
                        % (total_in, total_in / 12.0)
                    )
                    blocks.append(post_block)
                except (ValueError, IndexError):
                    pass

            # Gate mounting context
            bottom_guide = str(fields.get("bottom_guide", ""))
            if "No bottom guide" in bottom_guide or "top-hung" in bottom_guide.lower():
                blocks.append(
                    "GATE MOUNTING: Top-hung (overhead beam required, no bottom guide). "
                    "Include overhead HSS beam in cut list."
                )
            elif bottom_guide:
                blocks.append(
                    "GATE MOUNTING: Standard (bottom guide rail)."
                )

            # Adjacent fence context with enriched details
            adjacent = str(fields.get("adjacent_fence", ""))
            if "Yes" in adjacent:
                side_1 = fields.get("fence_side_1_length", "0")
                side_2 = fields.get("fence_side_2_length", "0")
                spacing = fields.get("fence_post_spacing", "6 ft")
                match = fields.get("fence_infill_match", "match")

                mid_rail_count = 0
                if height_str:
                    try:
                        h_in = float(str(height_str).split()[0]) * 12
                        if h_in > 72:
                            mid_rail_count = 2
                        elif h_in > 48:
                            mid_rail_count = 1
                    except (ValueError, IndexError):
                        pass

                fence_block = (
                    "ADJACENT FENCE SECTIONS (compound job — include in cut list):\n"
                    "  Side 1 length: %s ft\n"
                    "  Side 2 length: %s ft\n"
                    "  Post spacing: %s\n"
                    "  Infill: %s\n"
                    "  Mid-rails per section: %d\n"
                    "  The fence uses the same height and frame material as the gate.\n"
                    "  Fence posts are SAME profile and length as gate posts.\n"
                    "  Each fence section needs: top rail, bottom rail, %d mid-rail(s), "
                    "vertical pickets at spacing OC.\n"
                    "  Include fence rails, fence pickets/infill, "
                    "and fence posts in the cut list. Gate post is shared — do not duplicate."
                    % (side_1, side_2, spacing, match, mid_rail_count, mid_rail_count)
                )
                blocks.append(fence_block)

        # --- Field welding context ---
        installation = str(fields.get("installation", ""))
        if "install" in installation.lower() and "no" not in installation.lower():
            blocks.append(
                "FIELD WELDING (HARD CONSTRAINT):\n"
                "  ALL site/field welds = Stick (SMAW, E7018) or self-shielded flux core (FCAW-S).\n"
                "  NEVER specify MIG (GMAW) or TIG (GTAW) for outdoor field work.\n"
                "  Wind disperses shielding gas — cannot maintain gas coverage outdoors.\n"
                "  MIG/TIG is for SHOP FABRICATION ONLY.\n"
                "  In the fab sequence, any step done on-site must specify stick or flux core."
            )

        # --- Customer-specified profiles (universal — all job types) ---
        picket_key = fields.get("_picket_profile_key", "")
        picket_material_text = fields.get("picket_material", "")
        if picket_key:
            blocks.append(
                "PICKET/BAR PROFILE (customer-specified — use EXACTLY):\n"
                "  Profile key: %s\n"
                "  Customer chose: %s\n"
                "  Use this profile for ALL pickets/bars. "
                "Do NOT substitute round for square or vice versa."
                % (picket_key, picket_material_text or picket_key)
            )

        gauge_val = fields.get("_frame_gauge_value", "")
        if gauge_val:
            blocks.append(
                "FRAME GAUGE (customer-specified): %s — use this for all frame members."
                % gauge_val
            )

        # --- Generic compound context for any job type ---
        # Pass through any fields that indicate compound elements
        for key in ("additional_sections", "extension_length", "return_wall_length"):
            val = fields.get(key)
            if val and str(val).strip() and str(val).strip() != "0":
                blocks.append(
                    "ADDITIONAL ELEMENT — %s: %s. Include this in the cut list." % (
                        key.replace("_", " "), val)
                )

        if not blocks:
            return ""
        return "\nSTRUCTURED CONTEXT:\n" + "\n".join("- " + b for b in blocks) + "\n"

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

    # Field names that indicate user-specified gauge/thickness
    _GAUGE_FIELD_NAMES = (
        "material_gauge", "frame_gauge", "material_thickness",
        "tube_wall_thickness", "top_thickness", "gauge", "thickness",
        "expanded_metal_gauge", "sheet_thickness",
    )

    # Common gauge descriptions → decimal inches
    _GAUGE_MAP = {
        "7 gauge": ".187", "7ga": ".187",
        "10 gauge": ".134", "10ga": ".134",
        "11 gauge": ".120", "11ga": ".120",
        "12 gauge": ".105", "12ga": ".105",
        "14 gauge": ".075", "14ga": ".075",
        "16 gauge": ".063", "16ga": ".063",
        "18 gauge": ".048", "18ga": ".048",
        "20 gauge": ".036", "20ga": ".036",
    }

    def _detect_gauge_constraint(self, fields):
        # type: (dict) -> str
        """
        Scan fields and description for user-specified gauge/thickness.
        Returns a HARD CONSTRAINT block if found, empty string otherwise.
        """
        gauge_value = None

        # Check explicit gauge/thickness fields
        for field_name in self._GAUGE_FIELD_NAMES:
            val = fields.get(field_name)
            if val and str(val).strip():
                gauge_value = str(val).strip()
                break

        # If no explicit field, scan description for gauge patterns
        if not gauge_value:
            desc = str(fields.get("description", "") or "").lower()
            # Match decimal thickness like .125, 0.125, .063
            m = re.search(r"(?:^|[\s(])(\.\d{2,3})(?:[\"\s']|[\s-]?(?:inch|thick|gauge|aluminum|steel|sheet|plate))", desc)
            if m:
                gauge_value = m.group(1)
            else:
                # Match fraction like 1/8", 3/16", 1/4"
                m = re.search(r'(\d/\d{1,2})\s*["\']?\s*(?:thick|sheet|plate|aluminum|steel)?', desc)
                if m:
                    frac = m.group(1)
                    # Convert common fractions
                    frac_map = {"1/8": ".125", "3/16": ".1875", "1/4": ".250",
                                "1/16": ".063", "3/8": ".375", "1/2": ".500"}
                    gauge_value = frac_map.get(frac, frac + '"')
                else:
                    # Match named gauges like "11 gauge", "14ga"
                    for name, decimal in self._GAUGE_MAP.items():
                        if name in desc:
                            gauge_value = "%s (%s\")" % (name, decimal)
                            break

        if not gauge_value:
            return ""

        return (
            "\nMATERIAL GAUGE (HARD CONSTRAINT — DO NOT OVERRIDE):\n"
            "User specified: %s.\n"
            "ALL materials (tube, bar, angle, sheet, plate, channel) MUST match this gauge/thickness.\n"
            "Do NOT mix thicknesses — every structural and decorative piece uses the user's specified gauge.\n"
            "Do NOT substitute a different thickness to save weight or for any other reason.\n"
            % gauge_value
        )

    def _detect_material_constraint(self, fields):
        # type: (dict) -> tuple
        """
        Detect user-selected material type from fields.
        Returns (constraint_text, is_aluminum, is_stainless).

        When the user explicitly selects a material type via the question tree,
        this produces a HARD CONSTRAINT and signals which profile set to use.
        """
        material_type = str(fields.get("material_type", "") or "").lower().strip()
        stainless_grade = str(fields.get("stainless_grade", "") or "").lower().strip()
        aluminum_alloy = str(fields.get("aluminum_alloy", "") or "").lower().strip()
        desc = str(fields.get("description", "") or "").lower()

        # Explicit field takes priority
        if "aluminum" in material_type:
            alloy_note = ""
            if "6061" in aluminum_alloy:
                alloy_note = " (6061-T6)"
            elif "5052" in aluminum_alloy:
                alloy_note = " (5052)"
            constraint = (
                "\nMATERIAL TYPE (HARD CONSTRAINT — DO NOT MIX MATERIALS):\n"
                "User specified: ALUMINUM%s.\n"
                "ALL components MUST be aluminum. Use ONLY al_* profile keys.\n"
                "Set material_type to \"aluminum_6061\" for all items.\n"
                "Weld process: \"tig\" for all joints (aluminum requires TIG).\n"
                "Do NOT use any steel profiles (sq_tube_*, flat_bar_*, etc.).\n"
                "Do NOT mix steel and aluminum — they cannot be welded together.\n"
                % alloy_note
            )
            return constraint, True, False

        if "stainless" in material_type:
            grade_note = "304"
            if "316" in stainless_grade:
                grade_note = "316"
            constraint = (
                "\nMATERIAL TYPE (HARD CONSTRAINT — DO NOT MIX MATERIALS):\n"
                "User specified: STAINLESS STEEL (%s).\n"
                "ALL components MUST be stainless steel.\n"
                "Set material_type to \"stainless_%s\" for all items.\n"
                "Weld process: \"tig\" for all joints (stainless requires TIG with proper shielding).\n"
                "Use standard steel profile keys (sq_tube_*, flat_bar_*, etc.) but note stainless material_type.\n"
                "Do NOT mix carbon steel and stainless steel.\n"
                % (grade_note, grade_note)
            )
            return constraint, False, True

        if "carbon" in material_type or "steel" in material_type:
            constraint = (
                "\nMATERIAL TYPE (HARD CONSTRAINT — DO NOT MIX MATERIALS):\n"
                "User specified: CARBON STEEL.\n"
                "ALL components MUST be carbon steel (mild steel).\n"
                "Set material_type to \"mild_steel\" for all items.\n"
                "Do NOT use aluminum profiles (al_*). Do NOT mix aluminum and steel.\n"
                "Weld process: \"mig\" for standard joints, \"stick\" for field/site work.\n"
            )
            return constraint, False, False

        # No explicit field — fall back to description-based detection
        if "aluminum" in desc or "6061" in desc:
            return "", True, False
        if "stainless" in desc or "304" in desc or "316" in desc:
            return "", False, True

        # Default: no constraint (steel assumed by profile list)
        return "", False, False

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
                                    cut_list: List[Dict],
                                    enforced_dimensions: Optional[Dict] = None) -> str:
        """Build the AI prompt for fabrication sequence."""
        # Summarize fields (skip internal keys)
        field_lines = []
        for key, val in fields.items():
            if key.startswith("_") and not key.startswith("_ai_"):
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
            length_str = ('%.2f"' % length if length < 1 else
                         '%d"' % int(length) if length == int(length) else
                         '%.1f"' % length) if length else '0"'
            cut_lines.append('  - %s (qty %d, %s, cut: %s)' % (desc, qty, length_str, weld))
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

        # Force TIG for decorative elements
        all_fields_lower = " ".join(str(v) for v in fields.values()).lower()
        decorative_keywords = ["decorative", "flat bar", "ornamental", "pattern",
                               "layered", "woven", "pyramid", "concentric"]
        has_decorative = any(k in all_fields_lower for k in decorative_keywords)
        if has_decorative:
            weld_note += (
                "\nCRITICAL: All decorative flat bar welding MUST use TIG (GTAW), "
                "not MIG. The flat bar is 1/8\" thick with pre-finished surfaces — "
                "MIG would cause burn-through, excess spatter, and damage the finish. "
                "Use MIG only for the structural square tube frame."
            )

        # Detect finish type for mill scale hint
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

        # Aluminum has no mill scale — oxide layer is handled differently.
        # Do NOT inject vinegar bath or mill scale removal for aluminum.
        is_aluminum = any(k in all_fields_lower for k in ("aluminum", "6061", "5052"))
        if is_aluminum:
            needs_mill_scale_removal = False

        # Inject relevant fabrication knowledge (includes reasoning principles)
        finish_type = str(fields.get("finish", fields.get("finish_type", "")) or "")
        description = str(fields.get("description", "") or "")
        is_stainless = "stainless" in all_fields_lower or "304" in all_fields_lower or "316" in all_fields_lower
        from .fab_knowledge import get_relevant_knowledge
        knowledge_snippet = get_relevant_knowledge(
            job_type, finish_type, is_stainless, description=description)
        knowledge_block = ""
        if knowledge_snippet:
            knowledge_block = """
SHOP KNOWLEDGE BASE (use this to inform your output):
%s
---
""" % knowledge_snippet

        # Finish context — hints, not rigid templates
        if needs_mill_scale_removal:
            finish_context = """
FINISH CONTEXT:
This job requires mill scale removal (bare metal finish: clear coat, raw, brushed, or patina).

CRITICAL SCHEDULING RULE: The vinegar bath takes 12-24 hours and is UNATTENDED.
- Step 1 MUST be: Submerge flat bar/decorative stock in vinegar bath (this takes 30 seconds of labor).
- Steps 2-N: Do ALL frame/structural work while the vinegar bath runs overnight.
- After frame work is done: Pull stock from bath, rinse with warm water, scrub with dish soap and red scotch-brite pad, dry with clean towel, then heavy grind with 40-grit flap disc.
- NEVER schedule the vinegar bath AFTER frame work. That wastes an entire day.

Apply Principles 1 (workability) and 2 (access) to determine WHEN mill scale removal happens based on the specific pieces and assembly in this project.
- Decorative flat bar / small pieces that will be hard to grind after cutting → remove on RAW STOCK before cutting.
- Large structural pieces / tube frames → remove AFTER all welding is done.
Think through which pieces need prep before cutting vs after assembly.
"""
        else:
            finish_context = """
FINISH CONTEXT:
This job will be painted, powder coated, or galvanized. No mill scale removal needed.
Do NOT include vinegar bath, acid wash, or mill scale removal steps.
"""

        # Build geometry summary from cut list
        geometry_summary = _build_geometry_summary(cut_list)
        geometry_block = ""
        if geometry_summary:
            geometry_block = "\n%s\n" % geometry_summary

        # Enforced dimensions block — values that MUST be used verbatim
        enforced_dims_block = ""
        if enforced_dimensions:
            dims_lines = ["\n## ENFORCED DIMENSIONS (use these exact values)"]
            for dim_name, dim_val in enforced_dimensions.items():
                dims_lines.append("- %s: %s" % (dim_name, dim_val))
            dims_lines.append("Do NOT calculate or modify these values. Use them exactly as given.\n")
            enforced_dims_block = "\n".join(dims_lines)

        # Build rules — conditional on whether mill scale removal is needed
        rules_lines = [
            "1. Each step must be SPECIFIC and ACTIONABLE — not generic. Reference actual pieces from the cut list.",
        ]
        if needs_mill_scale_removal:
            rules_lines.append(
                "2. SCHEDULING: Unattended processes (vinegar bath, paint cure) must be the FIRST step. "
                "All attended work happens WHILE the unattended process runs.")
            rules_lines.append(
                '3. For vinegar bath / mill scale removal: Step 1 is ALWAYS "Submerge stock in vinegar bath." '
                "Steps 2-N are structural work done WHILE the bath runs.")
        else:
            rules_lines.append(
                "2. SCHEDULING: Order steps for maximum efficiency. "
                "If paint cure is needed, schedule it so other work can happen during drying.")
        rules_lines.append(
            "%d. EXACT DIMENSIONS: Use the EXACT dimensions and quantities from the CUT LIST above. "
            "Do not round or invent dimensions." % (len(rules_lines) + 1))
        rules_block = "\n".join(rules_lines)

        # Shop equipment context
        shop_context_block = str(fields.get("_shop_context", "") or "")

        prompt = """You are an expert metal fabricator creating step-by-step build instructions.
A journeyman fabricator should be able to follow these instructions and build this project.

JOB TYPE: %s
%s%s
PROJECT DETAILS:
%s

CUT LIST:
%s
%s%s%s%s
TASK: Generate a practical fabrication sequence — the exact steps a fabricator follows
to build this project from raw material to finished product.

RULES:
%s

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
]""" % (job_type, knowledge_block, shop_context_block, fields_text, cuts_text,
        geometry_block, enforced_dims_block, weld_note, finish_context,
        rules_block)

        return prompt

    def _call_ai(self, prompt: str) -> str:
        """Call Claude API. Raises RuntimeError on failure."""
        text = call_fast(prompt, timeout=360)
        if text is None:
            raise RuntimeError("AI provider returned no response")
        return text

    def _parse_response(self, response_text: str) -> Optional[List[Dict]]:
        """Parse AI response into cut list items with expanded schema."""
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

            # Sheet/plate fields — pass through from Opus
            profile_lower = cut["profile"].lower()
            is_sheet_item = "sheet" in profile_lower or "plate" in profile_lower
            width_raw = item.get("width_inches", 0)
            try:
                cut["width_inches"] = float(width_raw) if width_raw else 0.0
            except (ValueError, TypeError):
                cut["width_inches"] = 0.0

            stock_size = item.get("sheet_stock_size")
            valid_stock_sizes = ([48, 96], [48, 120], [48, 144], [60, 120], [60, 144])
            if isinstance(stock_size, list) and len(stock_size) == 2:
                try:
                    stock_size = [int(stock_size[0]), int(stock_size[1])]
                    if stock_size not in valid_stock_sizes:
                        stock_size = None
                except (ValueError, TypeError):
                    stock_size = None
            else:
                stock_size = None
            cut["sheet_stock_size"] = stock_size

            sheets_raw = item.get("sheets_needed", 1 if is_sheet_item else 0)
            try:
                cut["sheets_needed"] = max(int(sheets_raw), 0)
            except (ValueError, TypeError):
                cut["sheets_needed"] = 1 if is_sheet_item else 0

            cut["seaming_required"] = bool(item.get("seaming_required", False))
            cut["from_drop"] = bool(item.get("from_drop", False))

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
        """Parse AI response into build instruction steps."""
        if not response_text:
            logger.warning("BUILD INSTRUCTIONS parse: empty response text")
            return None

        # Strip markdown code fences if present
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first line (```json or ```) and last line (```)
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r'\[[\s\S]*\]', cleaned)
            if not match:
                logger.warning("BUILD INSTRUCTIONS parse: no JSON array found in response (first 200 chars: %s)",
                               cleaned[:200])
                return None
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("BUILD INSTRUCTIONS parse: extracted JSON array failed to parse")
                return None

        # Handle dict wrapper — Claude often returns {"steps": [...]} or {"instructions": [...]}
        if isinstance(data, dict):
            # Try common wrapper keys
            for key in ("steps", "instructions", "build_instructions",
                        "fabrication_sequence", "sequence", "build_steps"):
                if key in data and isinstance(data[key], list):
                    logger.info("BUILD INSTRUCTIONS parse: unwrapped from dict key '%s'", key)
                    data = data[key]
                    break
            else:
                # Last resort: look for any list value in the dict
                for key, val in data.items():
                    if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                        logger.info("BUILD INSTRUCTIONS parse: unwrapped from dict key '%s' (fallback)", key)
                        data = val
                        break

        if not isinstance(data, list):
            logger.warning("BUILD INSTRUCTIONS parse: response is not a list (type=%s)", type(data).__name__)
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

    # ------------------------------------------------------------------
    # FULL PACKAGE — One call, everything Opus knows
    # ------------------------------------------------------------------

    def generate_full_package(self, job_type: str, fields: dict) -> Optional[Dict]:
        """
        Generate a complete fabrication package in ONE AI call.

        Returns dict with: cut_list, build_instructions, hardware, consumables,
        labor_hours, finishing_method, assumptions, exclusions.
        Or None on any failure (caller falls back to existing code).
        """
        if not is_configured():
            logger.info("No AI provider configured — skipping full package")
            return None

        try:
            prompt = self._build_full_package_prompt(job_type, fields)
            response_text = self._call_ai(prompt)
            package = self._parse_full_package(response_text)
            if package and package.get("cut_list"):
                return package
            logger.warning("Full package returned empty cut_list — falling back")
            return None
        except Exception as e:
            logger.warning("Full package generation failed: %s — falling back", e)
            return None

    def _build_full_package_prompt(self, job_type: str, fields: dict) -> str:
        """
        Build ONE prompt that gets Opus to return the full fabrication package.

        Reuses: profile list, field context, weld guidance, fab knowledge.
        Adds: build instructions, hardware/consumables, labor hours, finishing.
        """
        # --- Reuse all the context builders from _build_prompt ---
        field_lines = []
        for key, val in fields.items():
            if key.startswith("_") and not key.startswith("_ai_"):
                continue
            if val is not None and str(val).strip():
                field_lines.append("  - %s: %s" % (key, val))
        fields_text = "\n".join(field_lines) if field_lines else "  (no fields provided)"

        all_fields_text = " ".join(str(v) for v in fields.values()).lower()

        # TIG / material detection
        tig_indicators = [
            "ground smooth", "blended", "furniture finish", "show quality",
            "visible welds", "tig", "glass top", "grind flush", "grind smooth",
            "seamless", "showroom", "polished", "mirror finish",
            "stainless", "aluminum", "chrome", "brushed finish",
        ]
        needs_tig = any(ind in all_fields_text for ind in tig_indicators)

        # Material type detection — uses question tree field first, falls back to description
        material_constraint, is_aluminum, is_stainless = self._detect_material_constraint(fields)
        # Legacy fallback for jobs without material_type field
        if not material_constraint and not is_aluminum and not is_stainless:
            if "stainless" in all_fields_text or "304" in all_fields_text or "316" in all_fields_text:
                is_stainless = True
            if "aluminum" in all_fields_text or "6061" in all_fields_text:
                is_aluminum = True

        weld_guidance = self._build_weld_guidance(needs_tig, is_stainless, is_aluminum)
        profiles_text = self._get_profiles_for_job_type(job_type)

        # Filter profiles based on material selection
        if is_aluminum and material_constraint:
            # User explicitly chose aluminum — ONLY aluminum profiles
            al_groups = ["al_sq_tube", "al_rect_tube", "al_flat_bar",
                         "al_angle", "al_round_tube", "al_sheet"]
            al_lines = []
            for ag in al_groups:
                line = _PROFILE_GROUPS.get(ag)
                if line:
                    al_lines.append(line)
            profiles_text = "\n".join(al_lines)
        elif is_aluminum:
            # Detected from description — add aluminum but keep steel (legacy behavior)
            al_groups = ["al_sq_tube", "al_rect_tube", "al_flat_bar",
                         "al_angle", "al_round_tube", "al_sheet"]
            for ag in al_groups:
                line = _PROFILE_GROUPS.get(ag)
                if line and line not in profiles_text:
                    profiles_text += "\n" + line
        elif material_constraint and not is_stainless:
            # User explicitly chose carbon steel — strip any aluminum profiles
            profile_lines = profiles_text.split("\n")
            profiles_text = "\n".join(l for l in profile_lines if "Aluminum" not in l)

        # Fab knowledge injection
        finish_type = str(fields.get("finish", fields.get("finish_type", "")) or "")
        description = str(fields.get("description", "") or "")
        from .fab_knowledge import get_relevant_knowledge
        knowledge_snippet = get_relevant_knowledge(
            job_type, finish_type, is_stainless, description=description)
        knowledge_block = ""
        if knowledge_snippet:
            knowledge_block = "\nSHOP KNOWLEDGE BASE:\n%s\n---\n" % knowledge_snippet

        # Shop equipment context
        shop_context_block = str(fields.get("_shop_context", "") or "")

        context_blocks = self._build_field_context(job_type, fields)

        # Material context — from explicit selection or legacy detection
        material_context = material_constraint
        if not material_context and is_aluminum:
            material_context = (
                "\nMATERIAL CONTEXT — ALUMINUM:\n"
                "Use al_* profile keys. Set material_type to \"aluminum_6061\". "
                "Weld process: \"tig\" for all joints.\n"
            )

        # --- Gauge / thickness constraint ---
        gauge_constraint = self._detect_gauge_constraint(fields)

        # --- Customer-specified profiles constraint ---
        # If the customer answered specific questions about picket size, frame
        # size, post size etc., Opus MUST use those exact profiles.
        customer_specs = self._build_customer_profile_constraints(fields)
        if customer_specs:
            fields_text = customer_specs + "\n\n" + fields_text

        # --- Labor calibration from shop owner benchmarks ---
        from .labor_calculator import LABOR_CALIBRATION_NOTES
        labor_calibration = LABOR_CALIBRATION_NOTES

        prompt = """You are an expert metal fabricator. Given a job description and project details, generate a COMPLETE fabrication package: cut list, build instructions, hardware, consumables, labor hours, and finishing recommendation.

Think through this like you're planning the entire job from raw material to delivery.

SCOPE BOUNDARY (CRITICAL):
Only include materials, hardware, and processes that the user EXPLICITLY described or that are essential to fabricate what they described.
- If the user describes a sign but not posts or footings, do NOT add posts, concrete, or footings — put them in "exclusions".
- If the user doesn't mention concrete, anchors, or site installation, do NOT add them.
- Anything the user didn't describe goes in "exclusions" with a note like "Not included: mounting posts and footings — add if needed."
- Do NOT invent mounting infrastructure, site work, or installation materials unless specifically requested.
- Do NOT add materials in gauges or thicknesses the user didn't specify — use the gauge they gave for ALL parts.
- The user is a fabricator — they know what they need. Quote what they asked for, nothing more.

JOB TYPE: %s
%s%s%s
PROJECT INFO:
%s
%s
WELD PROCESS GUIDANCE:
%s
%s
AVAILABLE PROFILES (use ONLY these for cut list items):
%s

MATERIAL TYPES: square_tubing, round_tubing, flat_bar, angle_iron, channel, pipe, plate, mild_steel, stainless_304, aluminum_6061, dom_tubing

CUT TYPES: square, miter_45, miter_22.5, cope, notch, compound

SHEET/PLATE RULES:
For sheet/plate items include: width_inches, sheet_stock_size ([W,H] from standard sizes: [48,96], [48,120], [48,144], [60,120], [60,144]), sheets_needed.

LASER CUT DROP RULE:
When a sheet is laser-cut to produce a decorative face (e.g., channel letter faces, sign panels with cutouts):
- The DROP (remaining sheet after cutouts are removed) IS the finished part.
- The cutout shapes are WASTE — do NOT create separate line items for them.
- sheets_needed applies to the parent sheet only. One face panel = 1 sheet piece.
- Example: sign face with cut-out letters = 1 sheet piece. The letter-shaped holes are waste, not pieces.

CUT LIST DROP REUSE:
- When a piece is laser-cut FROM another piece (e.g., letter cutouts from a face panel, raised elements from base layer drops), set "from_drop": true
- from_drop pieces do NOT require purchasing additional sheet stock — they come from the waste/drop of another cut
- Only the parent piece (the sheet being cut) needs sheets_needed
- Example: A sign face panel is laser cut with letter openings. The letter pieces that fall out ARE the raised layer elements. The face panel needs 1 sheet. The letter pieces need 0 additional sheets (from_drop: true).

SIDE WALL / RETURN MATERIAL RULE:
For side walls, returns, and channel sides that are 6 inches deep or less:
- Use FLAT BAR stock (flat_bar_*) instead of cutting strips from sheet.
- Flat bar is cheaper, already straight-edged, and needs no sheet nesting.
- Example: 6" deep sign return → flat_bar_3x0.25, NOT a 6" strip cut from sheet_11ga.
- Side walls deeper than 6" → sheet/plate strip is acceptable.

LABOR HOUR ESTIMATION RULES:
- TIG welding (aluminum, stainless) is 2.5-3x slower per inch than MIG (mild steel).
- Outdoor painted steel: grind is cleanup pass, not full furniture-grade grinding.
- Bare metal finish (clear coat, brushed): requires mill scale removal — significant grind time.
- Ground smooth / blended joints: grind time can equal or exceed weld time.
- Batch cutting: identical pieces share setup — one stop setting, then feed-and-cut.
- If powder_coat or galvanized: clearcoat and paint = 0 (outsourced).
- If raw finish: finish_prep = minimal (1.0 hr cleanup), clearcoat/paint = 0.
- When in doubt, estimate LOWER — shop owner consistently reports AI overestimates.

%s

LABOR PROCESSES (use these exact names):
layout_setup, cut_prep, fit_tack, full_weld, grind_clean, finish_prep, clearcoat, paint, hardware_install, site_install, final_inspection

Return ONLY valid JSON matching this structure:
{
    "cut_list": [
        {
            "description": "Part description",
            "piece_name": "part_id",
            "group": "group_name",
            "material_type": "mild_steel",
            "profile": "sq_tube_2x2_11ga",
            "length_inches": 30.0,
            "width_inches": 0,
            "quantity": 4,
            "cut_type": "square",
            "cut_angle": 90.0,
            "weld_process": "mig",
            "weld_type": "fillet",
            "sheet_stock_size": null,
            "sheets_needed": 0,
            "from_drop": false,
            "notes": "Brief fabrication note"
        }
    ],
    "build_instructions": [
        {
            "step": 1,
            "title": "Step title",
            "description": "Detailed actionable instruction for a journeyman fabricator",
            "tools": ["tool1", "tool2"],
            "duration_minutes": 30,
            "safety_notes": "Safety note"
        }
    ],
    "hardware": [
        {"description": "Item name", "quantity": 1, "estimated_price": 25.00}
    ],

HARDWARE PRICING RULES:
- estimated_price is ALWAYS the price PER SINGLE UNIT (per piece, per item)
- The pricing engine multiplies estimated_price × quantity — so if you put $25 for 40 screws, it bills $1,000
- For bulk items (screws, bolts, nuts, washers, rivets, cable ties, wire connectors): price is per PIECE, not per box/bag/pack
  - CORRECT: 40 machine screws → quantity: 40, estimated_price: 0.50 (total = $20)
  - WRONG: 40 machine screws → quantity: 40, estimated_price: 25.00 (that's a box price, would bill $1,000)
- For kit items (gas lens kit, connector assortment): quantity: 1, estimated_price: kit price
- For rolls/spools (LED strip, wire, tape): quantity is number of rolls, estimated_price is per roll
- For packs (cable gland 10-pack): quantity: 1, estimated_price: pack price — OR quantity: 10, estimated_price: per-piece price
    "consumables": [
        {"description": "Item name", "quantity": 1, "unit_price": 5.00}
    ],
    "labor_hours": {
        "layout_setup": {"hours": 1.0, "notes": "reason"},
        "cut_prep": {"hours": 1.0, "notes": "reason"},
        "fit_tack": {"hours": 1.0, "notes": "reason"},
        "full_weld": {"hours": 1.0, "notes": "reason"},
        "grind_clean": {"hours": 0.5, "notes": "reason"},
        "finish_prep": {"hours": 0.5, "notes": "reason"},
        "clearcoat": {"hours": 0.0, "notes": "reason"},
        "paint": {"hours": 0.0, "notes": "reason"},
        "hardware_install": {"hours": 0.5, "notes": "reason"},
        "site_install": {"hours": 0.0, "notes": "reason or N/A"},
        "final_inspection": {"hours": 0.25, "notes": "reason"}
    },
    "finishing_method": "paint",
    "assumptions": ["assumption 1"],
    "exclusions": ["exclusion 1"]
}""" % (job_type, knowledge_block, shop_context_block, material_context, fields_text,
        context_blocks, weld_guidance, gauge_constraint,
        profiles_text, labor_calibration)

        return prompt

    @staticmethod
    def _build_customer_profile_constraints(fields):
        # type: (dict) -> str
        """Extract customer-specified profiles and build a constraint block.

        When the customer explicitly chose picket size, frame gauge, post size,
        etc., Opus MUST use those exact profiles — not guess independently.
        """
        specs = []
        # Map field names to constraint descriptions
        profile_fields = {
            "picket_material": "PICKET MATERIAL/SIZE",
            "picket_spacing": "PICKET SPACING",
            "frame_material": "FRAME MATERIAL",
            "frame_gauge": "FRAME GAUGE/THICKNESS",
            "frame_size": "FRAME TUBE SIZE",
            "post_size": "POST SIZE",
            "Fence posts": "FENCE POST SIZE",
            "top_rail_profile": "TOP RAIL PROFILE",
            "infill_type": "INFILL TYPE",
            "infill_style": "INFILL STYLE",
            "railing_height": "RAILING HEIGHT",
        }
        for field_key, label in profile_fields.items():
            val = fields.get(field_key, "")
            if val and str(val).strip():
                specs.append("  - %s: %s" % (label, val))

        if not specs:
            return ""

        return (
            "CUSTOMER-SPECIFIED PROFILES (MANDATORY — use these EXACT materials):\n"
            "The customer explicitly chose these. Do NOT substitute or override:\n"
            + "\n".join(specs)
        )

    # 11 canonical labor processes
    _CANONICAL_PROCESSES = (
        "layout_setup", "cut_prep", "fit_tack", "full_weld",
        "grind_clean", "finish_prep", "clearcoat", "paint",
        "hardware_install", "site_install", "final_inspection",
    )

    # Valid finishing methods
    _VALID_FINISHING = (
        "raw", "clearcoat", "paint", "powder_coat", "galvanized",
        "brushed", "anodized", "ceramic", "patina",
    )

    def _parse_full_package(self, response_text: str) -> Optional[Dict]:
        """
        Parse full package AI response. Returns dict or None.

        Required: cut_list (non-empty).
        Optional but expected: build_instructions, hardware, consumables,
        labor_hours, finishing_method, assumptions, exclusions.
        """
        if not response_text:
            return None

        # Strip markdown code fences
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', cleaned)
            if not match:
                logger.warning("Full package parse: no JSON object found")
                return None
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Full package parse: extracted JSON failed to parse")
                return None

        if not isinstance(data, dict):
            logger.warning("Full package parse: response is not a dict")
            return None

        # --- Cut list (required) ---
        raw_cuts = data.get("cut_list", [])
        if not isinstance(raw_cuts, list) or len(raw_cuts) == 0:
            logger.warning("Full package: missing or empty cut_list")
            return None

        # Reuse existing cut list parser
        cut_list = self._parse_response(json.dumps(raw_cuts))
        if not cut_list:
            return None

        # --- Build instructions (optional) ---
        raw_instructions = data.get("build_instructions", [])
        build_instructions = None
        if isinstance(raw_instructions, list) and raw_instructions:
            build_instructions = self._parse_instructions_response(
                json.dumps(raw_instructions))
            if build_instructions:
                _strip_banned_terms_from_steps(build_instructions)

        # --- Hardware (optional) ---
        raw_hw = data.get("hardware", [])
        hardware = []
        if isinstance(raw_hw, list):
            for item in raw_hw:
                if not isinstance(item, dict):
                    continue
                desc = str(item.get("description", ""))
                if not desc:
                    continue
                qty = max(int(item.get("quantity", 1)), 1)
                price = float(item.get("estimated_price", item.get("price", 0)))
                hardware.append({
                    "description": desc,
                    "quantity": qty,
                    "estimated_price": round(price, 2),
                })

        # --- Consumables (optional) ---
        raw_cons = data.get("consumables", [])
        consumables = []
        if isinstance(raw_cons, list):
            for item in raw_cons:
                if not isinstance(item, dict):
                    continue
                desc = str(item.get("description", ""))
                if not desc:
                    continue
                qty = max(float(item.get("quantity", 1)), 0.1)
                unit_price = float(item.get("unit_price", item.get("price", 0)))
                consumables.append({
                    "description": desc,
                    "quantity": qty,
                    "unit_price": round(unit_price, 2),
                    "line_total": round(qty * unit_price, 2),
                    "category": "consumable",
                })

        # --- Labor hours (optional) ---
        raw_labor = data.get("labor_hours", {})
        labor_hours = {}
        if isinstance(raw_labor, dict):
            for process in self._CANONICAL_PROCESSES:
                entry = raw_labor.get(process, {})
                if isinstance(entry, dict):
                    hours = max(float(entry.get("hours", 0)), 0)
                    notes = str(entry.get("notes", ""))
                elif isinstance(entry, (int, float)):
                    hours = max(float(entry), 0)
                    notes = ""
                else:
                    hours = 0.0
                    notes = ""
                labor_hours[process] = {"hours": round(hours, 2), "notes": notes}

        # --- Finishing method (optional) ---
        finishing_method = str(data.get("finishing_method", "raw")).lower().strip()
        if finishing_method not in self._VALID_FINISHING:
            finishing_method = "raw"

        # --- Assumptions and exclusions (optional) ---
        assumptions = data.get("assumptions", [])
        if not isinstance(assumptions, list):
            assumptions = []
        assumptions = [str(a) for a in assumptions if a]

        exclusions = data.get("exclusions", [])
        if not isinstance(exclusions, list):
            exclusions = []
        exclusions = [str(e) for e in exclusions if e]

        return {
            "cut_list": cut_list,
            "build_instructions": build_instructions,
            "hardware": hardware,
            "consumables": consumables,
            "labor_hours": labor_hours,
            "finishing_method": finishing_method,
            "assumptions": assumptions,
            "exclusions": exclusions,
        }
