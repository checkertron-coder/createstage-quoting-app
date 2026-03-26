"""
Output validation rules — catches AI hallucinations, invalid dimensions,
banned process combinations, and sanity check failures before they reach
the PDF generator.

Sources: AWS D1.1 limits, shop experience, CreateStage historical data,
and observed AI failure modes from production.

Shop-specific overrides marked with # SHOP: CreateStage
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BANNED TERMS — per process and per context
# ---------------------------------------------------------------------------
# These terms should NEVER appear in AI-generated output for the given context.
# If found, the output should be flagged or corrected.

BANNED_TERMS = {

    # SHOP: CreateStage — post-vinegar cleanup NEVER includes these
    "vinegar_bath_cleanup": [
        "baking soda",
        "neutralize with baking soda",
        "baking soda solution",
        "compressed air",
        "blow dry",
        "wire brush",
        "chemical neutralizer",
        "neutralizing agent",
    ],

    # Decorative stock prep — NEVER these
    "decorative_stock_prep": [
        "grind after cutting",
        "grind small pieces",
        "grind individual pieces",
        "grind cut pieces",
        "re-grind finished surfaces",
        "re-grind after assembly",
        "polish each piece",
    ],

    # Decorative assembly — NEVER these
    "decorative_assembly": [
        "dry fit entire pattern",
        "dry-fit entire pattern",
        "dry fit all pieces",
        "lay out all pieces first",
        "position all pieces before welding",
        "pre-position entire assembly",
    ],

    # Stainless welding — NEVER these filler errors
    "stainless_welding": [
        "ER70S-6 on stainless",
        "mild steel filler on stainless",
        "carbon steel wire on stainless",
        "E7018 on stainless",
    ],

    # Aluminum welding — NEVER these
    "aluminum_welding": [
        "4043 on 5052",
        "stick weld aluminum",
        "E7018 on aluminum",
        "E6013 on aluminum",
        "preheat aluminum above 200",
    ],

    # General fabrication — NEVER these
    "general": [
        "weld on galvanized without ventilation",
        "hand hold while cutting",
        "hand-hold while cutting",
        "no PPE required",
        "skip inspection",
        "grind before welding is done",
        "surface prep before welding complete",
    ],

    # Powder coat — NEVER combine with in-house clear coat
    "powder_coat": [
        "clear coat after powder coat",
        "in-house clear coat on powder coated",
        "spray over powder coat",
        "vinegar bath for powder coat prep",
    ],

    # Mill scale — context-dependent
    "mill_scale_removal_not_needed": [
        "vinegar bath for powder coat",
        "vinegar bath before paint",
        "remove mill scale for powder coat",
        "blast for standard powder coat",
    ],

    # Labor estimation — NEVER count unattended time
    "labor_hours": [
        "soak time as labor",
        "cure time as labor",
        "drying time as labor",
        "waiting time as labor",
        "vinegar soak hours",
        "paint cure hours",
    ],

    # Leveler foot installation — NEVER drill into hollow tube wall
    "leveler_install": [
        "drill into tube",
        "drill into the tube",
        "drill through tube wall",
        "drill and tap tube wall",
        "tap directly into tube",
        "self-tapping screw into tube",
        "drill a hole in the tube",
        "drill a hole in the leg",
        "drill into the bottom of the leg",
        "drill a 3/8 hole",
        "drill a pilot hole",
        "drill and tap",
        "tap a thread into",
        "self-tapping screw",
    ],
}


# ---------------------------------------------------------------------------
# DIMENSION SANITY RANGES — by job type
# ---------------------------------------------------------------------------
# Each job type has expected dimension ranges. Values outside these
# ranges should be flagged (not rejected — could be unusual but valid).

DIMENSION_RANGES = {

    "cantilever_gate": {
        "clear_width_ft": {"min": 4, "max": 60, "typical": (10, 25)},
        "height_ft": {"min": 3, "max": 12, "typical": (5, 8)},
        "frame_tube_size_in": {"min": 1.5, "max": 6, "typical": (2, 4)},
        "total_weight_lbs": {"min": 50, "max": 4000, "typical": (200, 1500)},
    },

    "swing_gate": {
        "clear_width_ft": {"min": 2, "max": 20, "typical": (3, 8)},
        "height_ft": {"min": 3, "max": 10, "typical": (4, 7)},
        "frame_tube_size_in": {"min": 1, "max": 4, "typical": (1.5, 2)},
        "total_weight_lbs": {"min": 30, "max": 800, "typical": (75, 400)},
    },

    "straight_railing": {
        "length_ft": {"min": 1, "max": 100, "typical": (3, 20)},
        "height_in": {"min": 30, "max": 48, "typical": (34, 42)},
        "post_spacing_ft": {"min": 3, "max": 8, "typical": (4, 6)},
        "total_weight_lbs": {"min": 10, "max": 500, "typical": (30, 200)},
    },

    "stair_railing": {
        "length_ft": {"min": 2, "max": 30, "typical": (4, 15)},
        "height_in": {"min": 30, "max": 42, "typical": (34, 38)},
        "angle_degrees": {"min": 20, "max": 55, "typical": (30, 42)},
        "total_weight_lbs": {"min": 15, "max": 400, "typical": (40, 150)},
    },

    "furniture_table": {
        "length_in": {"min": 12, "max": 144, "typical": (30, 96)},
        "width_in": {"min": 12, "max": 60, "typical": (18, 42)},
        "height_in": {"min": 12, "max": 48, "typical": (17, 36)},
        "total_weight_lbs": {"min": 10, "max": 500, "typical": (30, 200)},
    },

    "bollard": {
        "height_in": {"min": 24, "max": 60, "typical": (36, 48)},
        "pipe_diameter_in": {"min": 3, "max": 8, "typical": (4, 6)},
        "count": {"min": 1, "max": 100, "typical": (1, 20)},
        "total_weight_lbs": {"min": 20, "max": 5000, "typical": (50, 500)},
    },

    "ornamental_fence": {
        "section_length_ft": {"min": 3, "max": 10, "typical": (6, 8)},
        "height_ft": {"min": 3, "max": 10, "typical": (4, 6)},
        "picket_spacing_in": {"min": 2, "max": 8, "typical": (3.5, 5)},
        "total_weight_lbs": {"min": 20, "max": 2000, "typical": (100, 800)},
    },

    "complete_stair": {
        "rise_in": {"min": 6, "max": 10, "typical": (7, 8)},
        "run_in": {"min": 9, "max": 14, "typical": (10, 12)},
        "width_in": {"min": 24, "max": 60, "typical": (30, 48)},
        "total_rise_ft": {"min": 2, "max": 20, "typical": (3, 12)},
        "total_weight_lbs": {"min": 100, "max": 5000, "typical": (300, 2000)},
    },

    "spiral_stair": {
        "diameter_ft": {"min": 3, "max": 10, "typical": (4, 7)},
        "total_rise_ft": {"min": 6, "max": 20, "typical": (8, 14)},
        "total_weight_lbs": {"min": 200, "max": 5000, "typical": (500, 2500)},
    },

    "utility_enclosure": {
        "width_in": {"min": 6, "max": 96, "typical": (12, 48)},
        "height_in": {"min": 6, "max": 96, "typical": (12, 60)},
        "depth_in": {"min": 4, "max": 48, "typical": (6, 24)},
        "total_weight_lbs": {"min": 5, "max": 500, "typical": (20, 200)},
    },

    "offroad_bumper": {
        "width_in": {"min": 40, "max": 80, "typical": (54, 72)},
        "total_weight_lbs": {"min": 40, "max": 300, "typical": (60, 180)},
    },

    "rock_slider": {
        "length_in": {"min": 40, "max": 84, "typical": (48, 72)},
        "total_weight_lbs": {"min": 30, "max": 200, "typical": (50, 100)},
        "count": {"min": 2, "max": 2, "typical": (2, 2)},  # always pair
    },

    "roll_cage": {
        "total_weight_lbs": {"min": 30, "max": 500, "typical": (60, 200)},
    },

    "exhaust_custom": {
        "pipe_diameter_in": {"min": 1.5, "max": 5, "typical": (2, 3.5)},
        "total_length_ft": {"min": 2, "max": 20, "typical": (4, 12)},
        "total_weight_lbs": {"min": 5, "max": 100, "typical": (10, 50)},
    },

    "trailer_fab": {
        "length_ft": {"min": 4, "max": 53, "typical": (8, 24)},
        "width_ft": {"min": 4, "max": 8.5, "typical": (5, 7)},
        "total_weight_lbs": {"min": 200, "max": 10000, "typical": (500, 5000)},
    },

    "structural_frame": {
        "total_weight_lbs": {"min": 50, "max": 50000, "typical": (200, 10000)},
    },

    "sign_frame": {
        "width_in": {"min": 12, "max": 240, "typical": (24, 120)},
        "height_in": {"min": 12, "max": 120, "typical": (18, 60)},
        "total_weight_lbs": {"min": 5, "max": 500, "typical": (15, 200)},
    },

    "led_sign_custom": {
        "width_in": {"min": 6, "max": 300, "typical": (24, 120)},
        "height_in": {"min": 4, "max": 60, "typical": (12, 36)},
        "total_weight_lbs": {"min": 3, "max": 300, "typical": (10, 100)},
    },
}


# ---------------------------------------------------------------------------
# CUT LIST VALIDATION RULES
# ---------------------------------------------------------------------------

# Valid profile keys (must match material_lookup.py)
VALID_PROFILES = {
    # Square tube
    "sq_tube_1x1_11ga", "sq_tube_1x1_14ga", "sq_tube_1x1_16ga",
    "sq_tube_1.25x1.25_11ga",
    "sq_tube_1.5x1.5_11ga", "sq_tube_1.5x1.5_14ga", "sq_tube_1.5x1.5_16ga",
    "sq_tube_1.75x1.75_11ga",
    "sq_tube_2x2_11ga", "sq_tube_2x2_14ga", "sq_tube_2x2_16ga",
    "sq_tube_2.5x2.5_11ga",
    "sq_tube_3x3_11ga", "sq_tube_3x3_7ga",
    "sq_tube_4x4_11ga",
    "sq_tube_6x6_7ga",
    # Rectangular tube
    "rect_tube_2x1_11ga", "rect_tube_2x3_11ga", "rect_tube_2x4_11ga",
    # Round tube
    "round_tube_1.25_14ga", "round_tube_1.5_11ga", "round_tube_1.5_14ga",
    "round_tube_2_11ga",
    # DOM tube
    "dom_tube_1.75x0.120",
    # Flat bar
    "flat_bar_0.75x0.25",
    "flat_bar_1x0.125", "flat_bar_1x0.1875", "flat_bar_1x0.25",
    "flat_bar_1.5x0.25", "flat_bar_2x0.25", "flat_bar_3x0.25",
    # Angle iron
    "angle_1.5x1.5x0.125", "angle_2x2x0.125", "angle_2x2x0.1875",
    "angle_2x2x0.25", "angle_3x3x0.1875",
    # Square bar
    "sq_bar_0.5", "sq_bar_0.625", "sq_bar_0.75", "sq_bar_1.0",
    # Round bar
    "round_bar_0.5", "round_bar_0.625", "round_bar_0.75",
    # Channel
    "channel_4x5.4", "channel_6x8.2",
    # Pre-punched channel (fence mid-rails)
    "punched_channel_1x0.5_fits_0.5",
    "punched_channel_1.5x0.5_fits_0.5", "punched_channel_1.5x0.5_fits_0.625",
    "punched_channel_1.5x0.5_fits_0.75",
    "punched_channel_2x1_fits_0.75",
    # Pipe
    "pipe_3_sch40", "pipe_3.5_sch40", "pipe_4_sch40", "pipe_6_sch40",
    # HSS
    "hss_4x4_0.25", "hss_6x4_0.25",
    # Sheet / plate
    "sheet_11ga", "sheet_14ga", "sheet_16ga",
    "plate_0.1875", "plate_0.25", "plate_0.375", "plate_0.5", "plate_0.75", "plate_1.0",
    # Expanded metal
    "expanded_metal_10ga", "expanded_metal_13ga", "expanded_metal_16ga",
    # Aluminum tube — 6061-T6 (P38)
    "al_sq_tube_1x1_0.125", "al_sq_tube_1.5x1.5_0.125", "al_sq_tube_2x2_0.125",
    "al_rect_tube_1x2_0.125",
    # Aluminum angle (P38)
    "al_angle_1.5x1.5x0.125", "al_angle_2x2x0.125",
    # Aluminum flat bar (P38)
    "al_flat_bar_1x0.125", "al_flat_bar_1.5x0.125", "al_flat_bar_2x0.25",
    # Aluminum round tube (P38)
    "al_round_tube_1.5_0.125",
    # Aluminum sheet (P38)
    "al_sheet_0.040", "al_sheet_0.063", "al_sheet_0.080",
    "al_sheet_0.125", "al_sheet_0.190",
}

# Valid cut types
VALID_CUT_TYPES = {
    "square", "miter_45", "miter_22.5", "miter_30",
    "cope", "notch", "compound",
    "plasma", "torch",
}

# Valid weld processes
VALID_WELD_PROCESSES = {
    "mig", "tig", "stick", "flux_core",
    "none",  # non-welded items (hardware, purchased parts)
}

# Valid weld types
VALID_WELD_TYPES = {
    "fillet", "butt", "plug", "edge",
    "tack_only", "none",
}

# Valid material types (matching base.py MaterialType enum)
VALID_MATERIAL_TYPES = {
    "tube_steel", "flat_bar", "angle_iron", "plate", "sheet_metal",
    "round_bar", "square_bar", "pipe", "channel", "expanded_metal",
    "hardware", "other",
    # AI-generated material types (ai_cut_list.py tells Claude to use these)
    "square_tubing", "round_tubing", "dom_tubing",
    "mild_steel", "stainless_304", "aluminum_6061",
}

# Max reasonable values
MAX_PIECE_LENGTH_INCHES = 480     # 40 feet — longest common stock
MAX_PIECE_QUANTITY = 500          # beyond this, it's likely an error
MAX_TOTAL_ITEMS = 200             # cut list with more items is suspicious
MAX_WEIGHT_LBS = 50000            # 25 tons — beyond typical fab shop
MAX_WELD_INCHES = 50000           # sanity limit


# ---------------------------------------------------------------------------
# PROCESS COMPATIBILITY MATRIX
# ---------------------------------------------------------------------------
# Validates that weld process is compatible with material

PROCESS_MATERIAL_COMPAT = {
    "mig": {
        "allowed": ["mild_steel", "mild_steel_a36", "mild_steel_a500",
                     "mild_steel_a513", "stainless_304", "stainless_316",
                     "aluminum_6061", "aluminum_5052", "dom_tube"],
        "requires_spool_gun": ["aluminum_6061", "aluminum_5052"],
    },
    "tig": {
        "allowed": ["mild_steel", "mild_steel_a36", "mild_steel_a500",
                     "mild_steel_a513", "stainless_304", "stainless_316",
                     "aluminum_6061", "aluminum_5052", "dom_tube"],
        "requires_ac": ["aluminum_6061", "aluminum_5052"],
        "requires_purge": ["stainless_304", "stainless_316"],
    },
    "stick": {
        "allowed": ["mild_steel", "mild_steel_a36", "mild_steel_a500",
                     "mild_steel_a513"],
        "not_allowed": ["stainless_304", "stainless_316",
                        "aluminum_6061", "aluminum_5052"],
    },
    "flux_core": {
        "allowed": ["mild_steel", "mild_steel_a36", "mild_steel_a500"],
        "not_allowed": ["stainless_304", "stainless_316",
                        "aluminum_6061", "aluminum_5052"],
    },
}


# ---------------------------------------------------------------------------
# VALIDATION FUNCTIONS
# ---------------------------------------------------------------------------

class ValidationResult:
    """Result of a validation check."""

    def __init__(self):
        self.errors = []       # type: List[str]  # must fix before output
        self.warnings = []     # type: List[str]  # review recommended
        self.info = []         # type: List[str]  # informational notes

    @property
    def is_valid(self):
        """True if no errors (warnings and info are OK)."""
        return len(self.errors) == 0

    def add_error(self, msg):
        # type: (str) -> None
        self.errors.append(msg)
        logger.warning("Validation ERROR: %s", msg)

    def add_warning(self, msg):
        # type: (str) -> None
        self.warnings.append(msg)
        logger.info("Validation WARNING: %s", msg)

    def add_info(self, msg):
        # type: (str) -> None
        self.info.append(msg)

    def summary(self):
        # type: () -> str
        """Return human-readable summary."""
        parts = []
        if self.errors:
            parts.append("ERRORS (%d):\n  %s" % (len(self.errors),
                                                    "\n  ".join(self.errors)))
        if self.warnings:
            parts.append("WARNINGS (%d):\n  %s" % (len(self.warnings),
                                                      "\n  ".join(self.warnings)))
        if self.info:
            parts.append("INFO (%d):\n  %s" % (len(self.info),
                                                  "\n  ".join(self.info)))
        if not parts:
            return "All validation checks passed."
        return "\n".join(parts)


def validate_cut_list_item(item):
    # type: (dict) -> ValidationResult
    """
    Validate a single cut list item (MaterialItem dict).

    Checks:
    - Profile is recognized
    - Length is within reasonable range
    - Quantity is positive and reasonable
    - Cut type is valid
    - Material type is valid
    """
    result = ValidationResult()

    profile = item.get("profile", "")
    length = item.get("length_inches", 0)
    qty = item.get("quantity", 0)
    cut_type = item.get("cut_type", "square")
    material_type = item.get("material_type", "")
    description = item.get("description", "")

    # Profile check
    if profile and profile not in VALID_PROFILES:
        result.add_warning(
            "Unrecognized profile '%s' in '%s' — price lookup may fail"
            % (profile, description)
        )

    # Length check
    if length <= 0:
        result.add_error(
            "Invalid length %.2f inches for '%s'" % (length, description)
        )
    elif length > MAX_PIECE_LENGTH_INCHES:
        result.add_warning(
            "Length %.1f inches (%.1f ft) exceeds typical stock length for '%s'"
            % (length, length / 12, description)
        )

    # Quantity check
    if qty <= 0:
        result.add_error(
            "Invalid quantity %d for '%s'" % (qty, description)
        )
    elif qty > MAX_PIECE_QUANTITY:
        result.add_warning(
            "Quantity %d seems unusually high for '%s'" % (qty, description)
        )

    # Cut type check
    if cut_type and cut_type not in VALID_CUT_TYPES:
        result.add_warning(
            "Unrecognized cut type '%s' for '%s'" % (cut_type, description)
        )

    # Material type check
    if material_type and material_type not in VALID_MATERIAL_TYPES:
        result.add_warning(
            "Unrecognized material type '%s' for '%s'"
            % (material_type, description)
        )

    return result


def validate_cut_list(items):
    # type: (list) -> ValidationResult
    """
    Validate an entire cut list (list of MaterialItem dicts).

    Checks individual items plus aggregate sanity:
    - Total item count
    - Total weight
    - Total weld inches
    """
    result = ValidationResult()

    if not items:
        result.add_warning("Cut list is empty")
        return result

    if len(items) > MAX_TOTAL_ITEMS:
        result.add_warning(
            "Cut list has %d items — verify this is correct" % len(items)
        )

    total_weight = 0
    total_weld = 0

    for i, item in enumerate(items):
        item_result = validate_cut_list_item(item)
        for err in item_result.errors:
            result.add_error("Item %d: %s" % (i + 1, err))
        for warn in item_result.warnings:
            result.add_warning("Item %d: %s" % (i + 1, warn))

        # Accumulate
        weight = item.get("weight_lbs", 0)
        if isinstance(weight, (int, float)):
            total_weight += weight * item.get("quantity", 1)

    if total_weight > MAX_WEIGHT_LBS:
        result.add_warning(
            "Total weight %.0f lbs exceeds typical shop capacity" % total_weight
        )

    return result


def validate_dimensions(job_type, dimensions):
    # type: (str, dict) -> ValidationResult
    """
    Validate job dimensions against expected ranges.

    Args:
        job_type: the job type string
        dimensions: dict of dimension name → value

    Returns:
        ValidationResult with warnings for out-of-range values
    """
    result = ValidationResult()
    ranges = DIMENSION_RANGES.get(job_type)
    if not ranges:
        return result  # no ranges defined for this job type

    for dim_name, value in dimensions.items():
        if dim_name not in ranges:
            continue
        dim_range = ranges[dim_name]
        min_val = dim_range.get("min", 0)
        max_val = dim_range.get("max", float("inf"))
        typical = dim_range.get("typical", (min_val, max_val))

        if not isinstance(value, (int, float)):
            continue

        if value < min_val:
            result.add_error(
                "%s = %.1f is below minimum %.1f for %s"
                % (dim_name, value, min_val, job_type)
            )
        elif value > max_val:
            result.add_error(
                "%s = %.1f exceeds maximum %.1f for %s"
                % (dim_name, value, max_val, job_type)
            )
        elif value < typical[0] or value > typical[1]:
            result.add_warning(
                "%s = %.1f is outside typical range (%.1f - %.1f) for %s"
                % (dim_name, value, typical[0], typical[1], job_type)
            )

    return result


def validate_weld_process_material(weld_process, material_type):
    # type: (str, str) -> ValidationResult
    """
    Validate that a weld process is compatible with a material.

    Args:
        weld_process: "mig", "tig", "stick", "flux_core"
        material_type: material key

    Returns:
        ValidationResult
    """
    result = ValidationResult()
    compat = PROCESS_MATERIAL_COMPAT.get(weld_process)
    if not compat:
        if weld_process and weld_process != "none":
            result.add_warning("Unknown weld process '%s'" % weld_process)
        return result

    allowed = compat.get("allowed", [])
    not_allowed = compat.get("not_allowed", [])

    if material_type in not_allowed:
        result.add_error(
            "%s welding is NOT compatible with %s"
            % (weld_process.upper(), material_type)
        )
    elif material_type not in allowed and material_type:
        result.add_warning(
            "Unverified: %s welding on %s — check compatibility"
            % (weld_process.upper(), material_type)
        )

    # Special requirements
    if material_type in compat.get("requires_spool_gun", []):
        result.add_info(
            "%s on %s requires spool gun" % (weld_process.upper(), material_type)
        )
    if material_type in compat.get("requires_ac", []):
        result.add_info(
            "TIG on %s requires AC mode" % material_type
        )
    if material_type in compat.get("requires_purge", []):
        result.add_info(
            "TIG on %s requires argon back-purge for full penetration welds"
            % material_type
        )

    return result


def build_instructions_to_text(steps):
    # type: (list) -> str
    """
    Convert a list of build instruction step dicts to a single text string
    for banned terms scanning.

    Args:
        steps: list of step dicts with title, description, safety_notes keys

    Returns:
        Concatenated text from all steps
    """
    if not steps:
        return ""
    parts = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        parts.append(str(step.get("title", "")))
        parts.append(str(step.get("description", "")))
        parts.append(str(step.get("safety_notes", "")))
    return " ".join(p for p in parts if p)


def check_banned_terms(text, context="general"):
    # type: (str, str) -> List[str]
    """
    Check text for banned terms in a given context.

    Args:
        text: text to scan (AI output, build instructions, etc.)
        context: key from BANNED_TERMS dict

    Returns:
        List of banned terms found (empty if clean)
    """
    terms = BANNED_TERMS.get(context, [])
    text_lower = text.lower()
    found = []
    for term in terms:
        if term.lower() in text_lower:
            found.append(term)
    return found


def check_all_banned_terms(text):
    # type: (str) -> dict
    """
    Check text against ALL banned term categories.

    Returns:
        dict of context → list of found banned terms (only non-empty)
    """
    results = {}
    for context in BANNED_TERMS:
        found = check_banned_terms(text, context)
        if found:
            results[context] = found
    return results


def validate_labor_processes(processes):
    # type: (list) -> ValidationResult
    """
    Validate labor process breakdown.

    Checks:
    - All process names are from canonical 11
    - No negative hours
    - No single process > 40 hours (red flag)
    - Total hours sanity check
    """
    result = ValidationResult()

    CANONICAL_PROCESSES = {
        "layout_setup", "cut_prep", "fit_tack", "full_weld", "grind_clean",
        "finish_prep", "clearcoat", "paint", "hardware_install",
        "site_install", "final_inspection",
        # Extended processes generated by labor_calculator.py for decorative jobs
        "stock_prep_grind", "post_weld_cleanup", "powder_coat",
    }

    total_hours = 0
    for proc in processes:
        name = proc.get("process", "")
        hours = proc.get("hours", 0)

        if name not in CANONICAL_PROCESSES:
            result.add_warning(
                "Non-canonical process name '%s' — may not display correctly"
                % name
            )

        if not isinstance(hours, (int, float)):
            result.add_error("Non-numeric hours for process '%s'" % name)
            continue

        if hours < 0:
            result.add_error(
                "Negative hours (%.2f) for process '%s'" % (hours, name)
            )
        elif hours > 40:
            result.add_warning(
                "Process '%s' has %.1f hours — verify this is correct"
                % (name, hours)
            )

        total_hours += hours

    if total_hours <= 0:
        result.add_error("Total labor hours is zero or negative")
    elif total_hours > 200:
        result.add_warning(
            "Total labor %.1f hours (%.1f weeks) — verify this job size"
            % (total_hours, total_hours / 40)
        )

    return result


def validate_decorative_pattern(items, pattern_type="pyramid"):
    # type: (list, str) -> ValidationResult
    """
    Validate decorative pattern cut list items.

    For pyramids / concentric squares: verifies layers step inward,
    quantities make sense, and pattern pieces are actual line items.

    Args:
        items: list of cut list items
        pattern_type: "pyramid", "concentric_squares", "grid"

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    # Filter to flat bar items
    flat_bar_items = [
        i for i in items
        if "flat_bar" in str(i.get("profile", "")).lower()
        or "flat bar" in str(i.get("description", "")).lower()
    ]

    if not flat_bar_items:
        result.add_warning(
            "Pattern type '%s' specified but no flat bar items in cut list"
            % pattern_type
        )
        return result

    if pattern_type in ("pyramid", "concentric_squares"):
        # Check for multiple lengths (layers should step inward)
        lengths = sorted(set(
            i.get("length_inches", 0) for i in flat_bar_items
        ))
        if len(lengths) < 2:
            result.add_warning(
                "Pattern '%s' has only %d unique flat bar length(s) — "
                "expected multiple layers stepping inward"
                % (pattern_type, len(lengths))
            )

        # Check quantities — each layer should have 4 pieces (4-sided pattern)
        for item in flat_bar_items:
            qty = item.get("quantity", 0)
            if qty > 0 and qty % 4 != 0:
                result.add_info(
                    "Flat bar qty %d is not a multiple of 4 — "
                    "verify if pattern has 4 sides"
                    % qty
                )

    return result


def validate_spacer_items(items):
    # type: (list) -> ValidationResult
    """
    Validate that spacer items are individual pieces, not assembled units.

    The cut list should show individual spacer PIECES, not the assembled
    spacer unit. Each spacer location = N individual pieces.
    """
    result = ValidationResult()

    for item in items:
        desc = str(item.get("description", "")).lower()
        if "spacer" not in desc and "shim" not in desc:
            continue

        # Check that description mentions individual pieces, not assemblies
        if "assembled" in desc or "unit" in desc or "set" in desc:
            result.add_warning(
                "Spacer item '%s' may describe assembled unit — "
                "cut list should show INDIVIDUAL pieces"
                % item.get("description", "")
            )

        # Check length — spacers should be short
        length = item.get("length_inches", 0)
        if isinstance(length, (int, float)) and length > 6:
            result.add_warning(
                "Spacer length %.1f inches seems long — verify this is a spacer"
                % length
            )

    return result


def validate_full_output(job_type, cut_list_items, labor_processes,
                          build_instructions="", dimensions=None):
    # type: (str, list, list, str, Optional[dict]) -> ValidationResult
    """
    Run all validation checks on a complete quote output.

    Args:
        job_type: the job type string
        cut_list_items: list of MaterialItem dicts
        labor_processes: list of LaborProcess dicts
        build_instructions: AI-generated build instructions text
        dimensions: dict of dimension name → value (optional)

    Returns:
        Comprehensive ValidationResult
    """
    result = ValidationResult()

    # 1. Cut list validation
    cl_result = validate_cut_list(cut_list_items)
    result.errors.extend(cl_result.errors)
    result.warnings.extend(cl_result.warnings)
    result.info.extend(cl_result.info)

    # 2. Labor validation
    if labor_processes:
        labor_result = validate_labor_processes(labor_processes)
        result.errors.extend(labor_result.errors)
        result.warnings.extend(labor_result.warnings)
        result.info.extend(labor_result.info)

    # 3. Dimension validation
    if dimensions:
        dim_result = validate_dimensions(job_type, dimensions)
        result.errors.extend(dim_result.errors)
        result.warnings.extend(dim_result.warnings)
        result.info.extend(dim_result.info)

    # 4. Banned term check on build instructions
    if build_instructions:
        banned = check_all_banned_terms(build_instructions)
        for context, terms in banned.items():
            result.add_warning(
                "Build instructions contain banned terms for '%s': %s"
                % (context, ", ".join(terms))
            )

    # 5. Decorative pattern checks
    desc_text = build_instructions.lower() if build_instructions else ""
    if "pyramid" in desc_text or "concentric" in desc_text:
        pattern_result = validate_decorative_pattern(cut_list_items)
        result.warnings.extend(pattern_result.warnings)
        result.info.extend(pattern_result.info)

    # 6. Spacer checks
    spacer_result = validate_spacer_items(cut_list_items)
    result.warnings.extend(spacer_result.warnings)
    result.info.extend(spacer_result.info)

    return result
