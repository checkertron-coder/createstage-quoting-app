"""
AI-assisted cut list generator for custom/complex jobs.

Uses Claude (preferred) or Gemini (fallback) to interpret freeform designs
into detailed cut lists. Called by ALL 25 calculators when a user provides
a design description. The AI thinks through design first, then generates
precise cut lists.

Fallback: if the AI fails or returns invalid JSON, the calling calculator
uses its own template-based output. Never crashes.
"""

import json
import logging
import re
from typing import Optional, List, Dict

from ..ai_client import call_fast, is_configured

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
}

# Which profile groups each job type needs
_JOB_TYPE_PROFILES = {
    "cantilever_gate": ["sq_tube", "rect_tube", "flat_bar", "angle", "sq_bar", "pipe", "sheet_plate", "hss"],
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
    Generates detailed cut lists by sending structured job info to AI (Claude or Gemini).

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
        if not is_configured():
            logger.info("No AI provider configured — skipping build instructions")
            return None

        try:
            prompt = self._build_instructions_prompt(job_type, fields, cut_list)
            response_text = self._call_ai(prompt)
            steps = self._parse_instructions_response(response_text)
            if steps and len(steps) > 0:
                # 1. Strip banned terms from customer-facing text FIRST
                _strip_banned_terms_from_steps(steps)

                # 2. THEN check for any remaining banned terms the stripping missed
                from ..knowledge.validation import check_banned_terms
                full_text = " ".join(
                    s.get("description", "") + " " + s.get("safety_notes", "")
                    for s in steps
                )
                for context in ["vinegar_bath_cleanup", "decorative_stock_prep",
                                "decorative_assembly", "leveler_install"]:
                    violations = check_banned_terms(full_text, context)
                    if violations:
                        logger.warning(
                            "BUILD SEQUENCE — banned terms remain after "
                            "stripping [%s]: %s", context, violations)
                        for step in steps:
                            desc = step.get("description", "")
                            for v in violations:
                                if v.lower() in desc.lower():
                                    step["description"] = (
                                        desc + " [REVIEW: contains banned "
                                        "term '%s']" % v
                                    )

                return steps
            logger.warning("AI build instructions returned empty — skipping")
            return None
        except Exception as e:
            logger.warning("AI build instructions failed: %s — skipping", e)
            return None

    def _build_prompt(self, job_type: str, fields: dict) -> str:
        """
        Build the AI prompt for cut list generation.

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

        # Build structured context blocks for compound/complex jobs
        context_blocks = self._build_field_context(job_type, fields)

        prompt = """You are an expert metal fabricator with 25+ years of shop experience.
You are generating a DETAILED cut list for a fabrication project.

IMPORTANT: Think through this design BEFORE listing pieces.

JOB TYPE: %s
%s
USER-PROVIDED INFORMATION:
%s
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
- UNIFORM LAYER STEPS: All layers in a concentric/pyramid pattern MUST reduce by the SAME increment.
  Calculate: step_size = interior_span / (desired_layers - 1), round to nearest 0.25".
  Example: 18" span, 10 layers -> step = 18/9 = 2.0". Layers: 18, 16, 14, 12, 10, 8, 6, 4.
  WRONG: 18, 16, 15, 14, 12, 10, 9 (inconsistent steps of -2, -1, -1, -2, -2, -1).
  RIGHT: 18, 16, 14, 12, 10, 8, 6, 4 (uniform -2" steps).
- Do NOT invent structural pieces (tabs, supports, connectors, spacers) that were not mentioned in the description. Only include pieces the user asked for.
- JOINT DESIGN determines cut geometry: Before assigning a cut type, determine the JOINT DESIGN at each end. Does it form a continuous profile at a corner, or does it cross/overlap/stack? Joint intent determines cut geometry, not material type.
- COMPONENT vs ASSEMBLED dimensions: When a description specifies component construction ("two pieces stacked," "assembled from smaller parts"), list the INDIVIDUAL pieces the fabricator physically cuts. Distinguish between: individual piece dimension, assembled unit dimension, and spacing/gap dimension. These are often different numbers.
- For repeating geometric patterns, calculate step increment from geometry and keep it UNIFORM unless description explicitly specifies variation. Irregular increments = calculation error — recheck math.

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
10. Decorative flat bar pieces in concentric/pyramid/grid patterns are ALWAYS square cut (cut_type: "square"). Only frame rails that form miter joints at corners get miter_45.
11. Spacers are ALWAYS square cut (cut_type: "square").

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
]""" % (job_type, knowledge_block, fields_text, context_blocks,
        weld_guidance, profiles_text)

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

                    post_block = (
                        "POST DIMENSIONS (calculator-verified — use EXACTLY):\n"
                        "  Above grade: %.0fin + %.0fin embed = %.0fin total (%.1f ft)\n"
                        "  Gate posts: %d\n"
                        % (above_grade_in, embed_in, total_in, total_in / 12.0, gate_post_count)
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
        """Build the AI prompt for fabrication sequence."""
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

        # Reasoning-based process order instruction
        reasoning_instruction = """
PROCESS ORDER — REASON THROUGH IT:
Determine the correct fabrication sequence by applying the reasoning principles from the SHOP KNOWLEDGE BASE above. For each step, verify:
- Is this operation physically workable at this stage? (Principle 1 — Workability)
- Will a later step block access to something I need to finish first? (Principle 2 — Access)
- Am I using component dimensions, not assembled or spacing dimensions? (Principle 3 — Dimensions)
- Does my cut type match how this piece joins its neighbor? (Principle 4 — Joint Design)
- Am I specifying only the finishing passes the customer's finish level requires? (Principle 5 — Finish as Design)
- Have I thought forward through how this step constrains later steps? (Principle 6 — Constraints)
"""

        prompt = """You are an expert metal fabricator creating step-by-step build instructions.
A journeyman fabricator should be able to follow these instructions and build this project.

JOB TYPE: %s
%s
PROJECT DETAILS:
%s

CUT LIST:
%s
%s%s%s%s
TASK: Generate a practical fabrication sequence — the exact steps a fabricator follows
to build this project from raw material to finished product.

RULES:
1. Each step must be SPECIFIC and ACTIONABLE — not generic. Reference actual pieces from the cut list.
2. Include the correct tools for each step (chop saw, band saw, TIG welder, MIG welder, angle grinder, etc.).
3. Specify weld process (MIG vs TIG) for each welding step.
4. Estimate realistic duration in minutes for each step.
5. Include safety notes where relevant (PPE, ventilation for galvanized, etc.).
6. 8-15 steps is typical. Group related operations but don't skip important steps.
7. Include quality checks: square check after tacking, level check, fit check before welding.
8. SCHEDULING: Unattended processes with long wait times (vinegar bath 12-24hr, paint cure, epoxy set) must be the FIRST step. Start the clock immediately. All attended work (cutting, welding, grinding) happens WHILE the unattended process runs. Never schedule an unattended long-duration process AFTER attended work — that wastes an entire day of shop time.
9. For jobs requiring vinegar bath / mill scale removal on stock that needs finish grinding before cutting: Step 1 is ALWAYS "Submerge stock in vinegar bath." Steps 2-N are frame/structural work done WHILE the bath runs. The step AFTER all frame work is "Pull stock from vinegar bath, wash, grind, cut."
10. WELD PROCESS SELECTION: Decorative flat bar work (1/8" or thinner, visible joints, furniture/ornamental pieces) MUST use TIG (GTAW), not MIG. TIG gives cleaner, more precise welds with less spatter and less heat input — critical for pre-finished decorative surfaces. MIG is for structural frame assembly (square tube joints, leg-to-frame connections). Spacer blocks can use either MIG (for speed) or TIG (for precision on small parts).
11. EXACT DIMENSIONS: Use the EXACT dimensions and quantities from the CUT LIST above. Do not estimate, round, or invent dimensions. When referring to a post, state its exact length from the cut list (e.g., "156 inches" not "15 feet"). When stating how many of a piece to cut, use the exact quantity from the cut list. If fence sections appear in the cut list, include fence fabrication and installation steps.
12. MILL SCALE: After EVERY tube/bar cut, grind 1-2" of mill scale from each cut end using flap disc before fit-up. Mill scale causes weld porosity. 30 seconds per end. Applies to ALL material regardless of finish.
13. WELDING PROCESS: Shop fabrication = MIG (GMAW). Field/site welding = Stick (SMAW, E7018) or self-shielded flux core (FCAW-S). NEVER specify MIG (GMAW) or TIG (GTAW) for outdoor field installation — wind disperses shielding gas. Dual-shield flux core is strongest/fastest for structural field work but not needed for fence/gate. Never use "file" for deburring — use "flap disc" or "die grinder."
14. GRINDING FOR OUTDOOR WORK: Gates, fences, railings with paint/powder finish — clean spatter, remove sharp edges, knock down high spots. DO NOT grind welds smooth or flat. Save smooth grinding for indoor/furniture/decorative work.
15. PAINT FOR OUTDOOR STEEL: Always prime THEN paint (two separate steps with dry time). Never combine into "prime and paint in one step."

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
]""" % (job_type, knowledge_block, fields_text, cuts_text,
        geometry_block, weld_note, finish_context, reasoning_instruction)

        return prompt

    def _call_ai(self, prompt: str) -> str:
        """Call AI provider (Claude or Gemini). Raises RuntimeError on failure."""
        text = call_fast(prompt, timeout=180)
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
