"""
Deterministic labor hour calculator based on cut list analysis.

Replaces AI-based labor estimation with Python math derived from
FAB_KNOWLEDGE.md shop time standards. Every hour is traceable to a rule.

Input: job_type, cut_list (from Stage 3), fields (from Stage 2)
Output: Dict of 8 labor categories with hours as floats
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


# Profile cross-section perimeters in inches (for weld length calculation)
# Weld per joint = perimeter × 0.75 (typical 3/4 coverage)
_PROFILE_PERIMETERS = {
    # Square tubing: perimeter = 4 × side
    "sq_tube_1x1": 4.0,
    "sq_tube_1.5x1.5": 6.0,
    "sq_tube_2x2": 8.0,
    "sq_tube_3x3": 12.0,
    "sq_tube_4x4": 16.0,
    # Rectangular tubing: perimeter = 2 × (w + h)
    "rect_tube_2x3": 10.0,
    "rect_tube_2x4": 12.0,
    # Round tubing: perimeter = pi × OD
    "round_tube_1.5": 4.7,
    "round_tube_2": 6.3,
    # DOM tube
    "dom_tube_1.75": 5.5,
    # Pipe (nominal size → OD-based perimeter)
    "pipe_3": 11.0,
    "pipe_4": 14.1,
    "pipe_6": 20.4,
    # Channel (web + 2 flanges approximate)
    "channel_4": 8.0,
    "channel_6": 12.0,
    # Angle (2 legs)
    "angle_1.5x1.5": 6.0,
    "angle_2x2": 8.0,
    "angle_3x3": 12.0,
    # Square bar
    "sq_bar_0.5": 2.0,
    "sq_bar_0.625": 2.5,
    "sq_bar_0.75": 3.0,
    # Round bar
    "round_bar_0.5": 1.6,
    "round_bar_0.625": 2.0,
}

_DEFAULT_PERIMETER = 6.0


def _get_perimeter(profile):
    # type: (str) -> float
    """Get cross-section perimeter for a profile key.
    Matches by prefix to handle gauge suffixes (e.g. sq_tube_2x2_11ga).
    """
    if not profile:
        return _DEFAULT_PERIMETER
    p = profile.lower()
    for key, val in _PROFILE_PERIMETERS.items():
        if p.startswith(key):
            return val
    # Sheet/plate: approximate for seam/plug welds
    if "sheet" in p or "plate" in p:
        return 4.0
    return _DEFAULT_PERIMETER


def _is_flat_bar(profile):
    # type: (str) -> bool
    return "flat_bar" in (profile or "").lower()


def calculate_labor_hours(job_type, cut_list, fields):
    # type: (str, List[Dict], Dict) -> Dict[str, float]
    """
    Deterministic labor hours from cut list analysis and shop time standards.

    Args:
        job_type: The job type string (e.g. "furniture_table")
        cut_list: List of cut item dicts (from AI cut list or calculator items).
                  Each dict should have: profile, quantity, cut_type.
                  Optional: weld_process, length_inches, description.
        fields: Answered fields from Stage 2 (has finish, description, etc.)

    Returns:
        Dict with 8 keys (hours as floats):
            layout_setup, cut_prep, fit_tack, full_weld,
            grind_clean, finish_prep, coating_application, final_inspection
    """
    if not cut_list:
        return {
            "layout_setup": 1.5,
            "cut_prep": 1.0,
            "fit_tack": 1.0,
            "full_weld": 1.0,
            "grind_clean": 0.5,
            "finish_prep": 1.0,
            "coating_application": 0.0,
            "final_inspection": 0.5,
        }

    # --- Detect finish type and weld process ---
    finish = str(fields.get("finish", fields.get("finish_type", "raw")) or "raw").lower()
    all_fields = " ".join(str(v) for v in fields.values()).lower()

    is_stainless = any(k in all_fields for k in ("stainless", "304", "316"))
    has_tig_items = any(
        str(item.get("weld_process", "")).lower() == "tig" for item in cut_list
    )
    tig_keywords = [
        "ground smooth", "blended", "furniture finish", "show quality",
        "visible welds", "tig", "glass top", "grind flush", "grind smooth",
        "seamless", "showroom", "polished", "mirror finish", "brushed finish",
    ]
    needs_tig = is_stainless or has_tig_items or any(k in all_fields for k in tig_keywords)

    bare_metal_kw = [
        "clear_coat", "clear coat", "clearcoat", "raw", "waxed",
        "raw_steel", "brushed", "patina", "chemical_patina",
    ]
    coating_kw = [
        "powder_coat", "powder coat", "powdercoat",
        "paint", "painted", "galvanized", "galvanize",
    ]
    has_coating = any(k in finish for k in coating_kw)
    needs_mill_scale = not has_coating and any(k in finish for k in bare_metal_kw)

    # --- Walk the cut list ---
    total_pieces = 0
    simple_cuts = 0
    miter_cuts = 0
    cope_notch_cuts = 0
    total_weld_inches = 0.0
    structural_joints = 0
    decorative_joints = 0

    for item in cut_list:
        qty = int(item.get("quantity", 1))
        total_pieces += qty
        profile = str(item.get("profile", ""))
        cut_type = str(item.get("cut_type", "square")).lower()
        weld_proc = str(item.get("weld_process", "")).lower()

        # Classify cut complexity
        if cut_type in ("cope", "notch"):
            cope_notch_cuts += qty
        elif cut_type in ("miter_45", "miter_22.5", "compound"):
            miter_cuts += qty
        else:
            simple_cuts += qty

        # Weld inches per piece
        if _is_flat_bar(profile):
            weld_per_piece = 2.0  # fillet on two sides
        else:
            perim = _get_perimeter(profile)
            weld_per_piece = perim * 0.75 * 2  # 2 joints per piece
        total_weld_inches += weld_per_piece * qty

        # Grind joints: 2 joints per piece
        if _is_flat_bar(profile) or weld_proc == "tig" or needs_tig:
            decorative_joints += qty * 2
        else:
            structural_joints += qty * 2

    # ======================================================
    # LAYOUT & SETUP
    # Base: 1.5 hrs + 0.5 hr per 10 pieces beyond 10
    # ======================================================
    extra = max(0, total_pieces - 10)
    layout_setup = 1.5 + (extra / 10.0) * 0.5

    # ======================================================
    # CUT & PREP
    # Per piece: cut time + 1 min/end deburr (2 ends) + 2 min layout/marking
    # Minimum 1.0 hr
    # ======================================================
    cut_minutes = (
        simple_cuts * 3          # 3 min/simple cut
        + miter_cuts * 5         # 5 min/miter
        + cope_notch_cuts * 15   # 15 min/cope or notch
        + total_pieces * 2       # deburr: 2 ends × 1 min
        + total_pieces * 2       # layout/marking: 2 min/piece
    )
    cut_prep = max(1.0, cut_minutes / 60.0)

    # ======================================================
    # FIT & TACK
    # Simple fit: 4 min/piece. Complex (miter, cope): 8 min/piece.
    # Minimum 1.0 hr
    # ======================================================
    fit_minutes = simple_cuts * 4 + (miter_cuts + cope_notch_cuts) * 8
    fit_tack = max(1.0, fit_minutes / 60.0)

    # ======================================================
    # FULL WELD
    # MIG: 10 in/min. TIG: 4 in/min. +25% overhead.
    # ======================================================
    weld_speed = 4.0 if needs_tig else 10.0
    weld_minutes = (total_weld_inches / weld_speed) * 1.25
    full_weld = max(0.5, weld_minutes / 60.0)

    # ======================================================
    # GRIND & CLEAN
    # Structural: 5 min/joint. Decorative: 3 min/joint.
    # +1.5 hr if mill scale removal. +30 min wire brush/clean.
    # Minimum 0.5 hr
    # ======================================================
    grind_minutes = structural_joints * 5 + decorative_joints * 3
    if needs_mill_scale:
        grind_minutes += 90   # 1.5 hrs flat
    grind_minutes += 30       # wire brush / final clean
    grind_clean = max(0.5, grind_minutes / 60.0)

    # ======================================================
    # FINISH PREP
    # ======================================================
    if any(k in finish for k in ("clear", "brushed", "patina", "wax")):
        finish_prep = 1.5   # scotch-brite + acetone wipe
    elif "powder" in finish:
        finish_prep = 1.0   # degrease, scuff, load
    elif "paint" in finish:
        finish_prep = 1.0
    elif "galv" in finish:
        finish_prep = 0.5
    elif "raw" in finish:
        finish_prep = 1.0   # basic cleanup for raw
    else:
        finish_prep = 1.0

    # ======================================================
    # COATING APPLICATION
    # ======================================================
    if "clear" in finish:
        coating_application = 1.0   # spray clearcoat
    elif "paint" in finish and "powder" not in finish:
        coating_application = 1.5   # primer + topcoat
    elif "powder" in finish or "galv" in finish:
        coating_application = 0.0   # outsourced
    elif "raw" in finish:
        coating_application = 0.0   # no coating
    else:
        coating_application = 0.0

    # ======================================================
    # FINAL INSPECTION — always 0.5 hr
    # ======================================================
    final_inspection = 0.5

    result = {
        "layout_setup": round(layout_setup, 2),
        "cut_prep": round(cut_prep, 2),
        "fit_tack": round(fit_tack, 2),
        "full_weld": round(full_weld, 2),
        "grind_clean": round(grind_clean, 2),
        "finish_prep": round(finish_prep, 2),
        "coating_application": round(coating_application, 2),
        "final_inspection": round(final_inspection, 2),
    }

    logger.info(
        "Labor calc for %s: %d pieces, %.0f weld-in, %s → %.1f total hrs",
        job_type, total_pieces, total_weld_inches,
        "TIG" if needs_tig else "MIG",
        sum(result.values()),
    )

    return result
