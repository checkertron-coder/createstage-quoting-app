"""
Deterministic labor hour calculator based on cut list analysis.

Uses TYPE A / TYPE B categorization from FAB_KNOWLEDGE.md Section 7:
  TYPE A — Structural welding (tube frames, legs, rails): weld-inch math
  TYPE B — Precision decorative placement (flat bar patterns, pickets,
           ornamental grids): per-piece time standard (5-8 min/piece)

Every hour is traceable to a rule. No AI involved.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# Profile cross-section perimeters in inches (for TYPE A weld length)
_PROFILE_PERIMETERS = {
    "sq_tube_1x1": 4.0,
    "sq_tube_1.5x1.5": 6.0,
    "sq_tube_2x2": 8.0,
    "sq_tube_3x3": 12.0,
    "sq_tube_4x4": 16.0,
    "rect_tube_2x3": 10.0,
    "rect_tube_2x4": 12.0,
    "round_tube_1.5": 4.7,
    "round_tube_2": 6.3,
    "dom_tube_1.75": 5.5,
    "pipe_3": 11.0,
    "pipe_4": 14.1,
    "pipe_6": 20.4,
    "channel_4": 8.0,
    "channel_6": 12.0,
    "angle_1.5x1.5": 6.0,
    "angle_2x2": 8.0,
    "angle_3x3": 12.0,
    "sq_bar_0.5": 2.0,
    "sq_bar_0.625": 2.5,
    "sq_bar_0.75": 3.0,
    "round_bar_0.5": 1.6,
    "round_bar_0.625": 2.0,
}

_DEFAULT_PERIMETER = 6.0

# Keywords that indicate TYPE B (precision decorative placement)
_DECORATIVE_KEYWORDS = (
    "picket", "baluster", "decorative", "pattern", "pyramid",
    "ornamental", "grid", "inlay", "concentric", "accent",
    "infill", "slat",
)

_DECORATIVE_GROUPS = ("infill", "decorative", "pattern")


def _get_perimeter(profile):
    # type: (str) -> float
    """Get cross-section perimeter for a profile key."""
    if not profile:
        return _DEFAULT_PERIMETER
    p = profile.lower()
    for key, val in _PROFILE_PERIMETERS.items():
        if p.startswith(key):
            return val
    if "sheet" in p or "plate" in p:
        return 4.0
    return _DEFAULT_PERIMETER


def _is_type_b(item):
    # type: (dict) -> bool
    """Classify a cut list item as TYPE B (precision decorative placement).

    TYPE B pieces require individual measurement, positioning, clamping,
    and multi-side welding. Time standard: 5-8 min per piece.

    Criteria:
    - flat_bar profile (always decorative placement)
    - Group is infill / decorative / pattern
    - Description contains decorative keywords
    """
    profile = str(item.get("profile", "")).lower()
    if "flat_bar" in profile:
        return True

    group = str(item.get("group", "")).lower()
    if group in _DECORATIVE_GROUPS:
        return True

    text = (str(item.get("description", "")) + " "
            + str(item.get("piece_name", ""))).lower()
    if any(kw in text for kw in _DECORATIVE_KEYWORDS):
        return True

    return False


def calculate_labor_hours(job_type, cut_list, fields):
    # type: (str, List[Dict], Dict) -> Dict[str, object]
    """
    Deterministic labor hours from TYPE A / TYPE B categorization.

    Returns dict with 8 hour keys (floats) plus:
      _reasoning: str  — chain-of-thought calculation log
      _flagged: bool    — True if any guardrail was tripped

    Args:
        job_type: The job type string
        cut_list: List of cut item dicts from Stage 3
        fields: Answered fields from Stage 2
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
            "_reasoning": "Empty cut list — using minimum defaults.",
            "_flagged": False,
        }

    # --- Detect finish and weld process ---
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

    reasoning_lines = []

    # ======================================================
    # STEP 1 — CATEGORIZE ALL PIECES
    # ======================================================
    type_a_count = 0       # structural pieces
    type_b_count = 0       # precision decorative pieces
    type_a_weld_inches = 0.0
    type_a_joints = 0
    type_b_joints = 0
    total_pieces = 0
    miter_cuts = 0

    for item in cut_list:
        qty = int(item.get("quantity", 1))
        total_pieces += qty
        profile = str(item.get("profile", ""))
        cut_type = str(item.get("cut_type", "square")).lower()

        if cut_type in ("miter_45", "miter_22.5", "compound"):
            miter_cuts += qty

        if _is_type_b(item):
            type_b_count += qty
            type_b_joints += qty * 2
            reasoning_lines.append(
                "  TYPE B: %s — %d pcs (decorative placement)"
                % (item.get("description", profile), qty)
            )
        else:
            type_a_count += qty
            perim = _get_perimeter(profile)
            weld_per_piece = perim * 0.75 * 2  # 2 joints × 75% coverage
            type_a_weld_inches += weld_per_piece * qty
            type_a_joints += qty * 2
            reasoning_lines.append(
                "  TYPE A: %s — %d pcs, %.0f\" weld each (%.0f\" total)"
                % (item.get("description", profile), qty,
                   weld_per_piece, weld_per_piece * qty)
            )

    reasoning_lines.insert(0,
        "STEP 1: Categorized %d TYPE A (structural), %d TYPE B (decorative) "
        "from %d total pieces." % (type_a_count, type_b_count, total_pieces))

    # ======================================================
    # STEP 2 — WELD TIME
    # ======================================================
    weld_speed = 4.0 if needs_tig else 10.0
    weld_label = "TIG" if needs_tig else "MIG"

    type_a_weld_min = (type_a_weld_inches / weld_speed) * 1.3 if type_a_weld_inches > 0 else 0.0
    type_b_weld_min = type_b_count * 5.0  # 5 min/piece baseline

    full_weld_min = type_a_weld_min + type_b_weld_min
    full_weld = max(0.5, full_weld_min / 60.0)

    reasoning_lines.append(
        "STEP 2 — WELD: TYPE A = %.0f\" ÷ %s %.0f in/min × 1.3 = %.1f min. "
        "TYPE B = %d pcs × 5 min = %.1f min. Sum = %.1f min (%.2f hr)."
        % (type_a_weld_inches, weld_label, weld_speed, type_a_weld_min,
           type_b_count, type_b_weld_min, full_weld_min, full_weld))

    # ======================================================
    # STEP 3 — GRIND TIME
    # ======================================================
    grind_min = type_a_joints * 6 + type_b_joints * 3  # 6 min structural, 3 min decorative
    grind_min += 30  # wire brush / final clean
    if needs_mill_scale:
        grind_min += 90  # 1.5 hrs for mill scale removal
    grind_clean = max(0.5, grind_min / 60.0)

    reasoning_lines.append(
        "STEP 3 — GRIND: %d TYPE A joints × 6 min + %d TYPE B welds × 3 min "
        "+ 30 min clean%s = %.1f min (%.2f hr)."
        % (type_a_joints, type_b_joints,
           " + 90 min mill scale" if needs_mill_scale else "",
           grind_min, grind_clean))

    # ======================================================
    # STEP 4 — REMAINING CATEGORIES
    # ======================================================

    # CUT & PREP: all pieces × 4 min + miter cuts × 2 min extra
    cut_min = total_pieces * 4 + miter_cuts * 2
    cut_prep = max(1.0, cut_min / 60.0)

    # FIT & TACK: structural frame pieces ONLY × 5 min
    # (TYPE B fitting time is already in the 5 min/piece weld time)
    fit_min = type_a_count * 5
    fit_tack = max(1.0, fit_min / 60.0)

    # LAYOUT & SETUP: 1.5 hrs + 0.25 hr per 10 decorative pieces beyond 20
    extra_decorative = max(0, type_b_count - 20)
    layout_setup = 1.5 + (extra_decorative / 10.0) * 0.25

    # FINISH PREP
    if any(k in finish for k in ("clear", "brushed", "patina", "wax")):
        finish_prep = 1.5
    elif "powder" in finish:
        finish_prep = 1.0
    elif "paint" in finish:
        finish_prep = 1.0
    elif "galv" in finish:
        finish_prep = 0.5
    elif "raw" in finish:
        finish_prep = 1.0
    else:
        finish_prep = 1.0

    # COATING APPLICATION
    if "clear" in finish:
        coating_application = 1.0
    elif "paint" in finish and "powder" not in finish:
        coating_application = 1.5
    elif "powder" in finish or "galv" in finish:
        coating_application = 0.0
    elif "raw" in finish:
        coating_application = 0.0
    else:
        coating_application = 0.0

    # FINAL INSPECTION
    final_inspection = 0.5

    reasoning_lines.append(
        "STEP 4 — CUT: %d pcs × 4 min + %d miter × 2 = %.1f min (%.2f hr). "
        "FIT: %d TYPE A × 5 min = %.1f min (%.2f hr). "
        "LAYOUT: 1.5 + 0.25 × %d/10 = %.2f hr."
        % (total_pieces, miter_cuts, cut_min, cut_prep,
           type_a_count, fit_min, fit_tack,
           extra_decorative, layout_setup))

    # ======================================================
    # STEP 5 — SANITY CHECK / GUARDRAILS
    # ======================================================
    flagged = False
    flag_reasons = []

    # Guardrail: full_weld > 40 hrs
    if full_weld > 40:
        flag_reasons.append(
            "full_weld %.1f hrs exceeds 40 hr threshold — review required" % full_weld)
        flagged = True
        logger.warning("Labor calc: full_weld %.1f > 40 hrs for %s", full_weld, job_type)

    # Guardrail: grind_clean > full_weld
    if grind_clean > full_weld:
        flag_reasons.append(
            "grind_clean %.1f hrs > full_weld %.1f hrs — unusual but possible for "
            "many small decorative welds" % (grind_clean, full_weld))
        flagged = True
        logger.warning("Labor calc: grind_clean %.1f > full_weld %.1f for %s",
                        grind_clean, full_weld, job_type)

    # Guardrail: negative or None → 0
    def _safe(val):
        if val is None or val < 0:
            return 0.0
        return round(val, 2)

    total_hrs = (layout_setup + cut_prep + fit_tack + full_weld
                 + grind_clean + finish_prep + coating_application + final_inspection)
    days = total_hrs / 8.0

    reasoning_lines.append(
        "STEP 5 — SANITY: Total %.1f hrs = %.1f days at 8 hr/day. "
        "A skilled journeyman with a jig would take approximately %.1f days "
        "for this scope." % (total_hrs, days, days))
    if flag_reasons:
        reasoning_lines.append("FLAGS: " + "; ".join(flag_reasons))

    result = {
        "layout_setup": _safe(layout_setup),
        "cut_prep": _safe(cut_prep),
        "fit_tack": _safe(fit_tack),
        "full_weld": _safe(full_weld),
        "grind_clean": _safe(grind_clean),
        "finish_prep": _safe(finish_prep),
        "coating_application": _safe(coating_application),
        "final_inspection": _safe(final_inspection),
        "_reasoning": "\n".join(reasoning_lines),
        "_flagged": flagged,
    }

    logger.info(
        "Labor calc for %s: %d pcs (%dA/%dB), %s, %.1f total hrs%s",
        job_type, total_pieces, type_a_count, type_b_count,
        weld_label, total_hrs,
        " [FLAGGED]" if flagged else "",
    )

    return result
