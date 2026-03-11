"""
Labor hour calculator — Opus AI estimation with deterministic fallback.

Primary path: Opus AI receives job context + FAB_KNOWLEDGE domain guidance,
returns per-process hour breakdown as JSON.

Fallback path: TYPE A / TYPE B categorization from FAB_KNOWLEDGE.md Section 7:
  TYPE A — Structural welding (tube frames, legs, rails): weld-inch math
  TYPE B — Precision decorative placement (flat bar patterns, pickets,
           ornamental grids): per-piece time standard (5-8 min/piece)

Fallback is deterministic — every hour is traceable to a rule.
"""

import json
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

# Outdoor job types — reduced grind requirements (cleanup only, not furniture-grade)
_OUTDOOR_JOB_TYPES = (
    "cantilever_gate", "swing_gate", "ornamental_fence",
    "straight_railing", "stair_railing", "balcony_railing",
    "bollard", "sign_frame", "window_security_grate",
)


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
    Labor hours — tries Opus AI first, falls back to deterministic.

    Returns dict with 8 hour keys (floats) plus:
      _reasoning: str  — chain-of-thought calculation log
      _flagged: bool    — True if any guardrail was tripped

    Args:
        job_type: The job type string
        cut_list: List of cut item dicts from Stage 3
        fields: Answered fields from Stage 2
    """
    # Try Opus AI estimation first
    try:
        result = _opus_estimate_labor(job_type, cut_list, fields)
        if result is not None:
            return result
    except Exception as e:
        logger.warning("Opus labor estimation failed, using fallback: %s", e)

    # Deterministic fallback
    return _fallback_calculate_labor_hours(job_type, cut_list, fields)


# Shop owner calibration benchmarks — injected into Opus prompt as SCALING reference
LABOR_CALIBRATION_NOTES = """
LABOR CALIBRATION — SCALING REFERENCES (from shop owner testing):

These are BENCHMARKS for specific scopes. You MUST scale proportionally by piece
count and weld inches — NEVER copy these numbers for a different-sized job.

BENCHMARK A — Large Gate + Fence Combo (shop + site)
  Scope: 18' cantilever gate + 28' fence, 124 pickets, 7 posts, mild steel, paint, on-site install.
  Total pieces: ~160 | Material weight: ~3,000 lbs
  SHOP HOURS (MIG, ~26 hrs):
    - cut_prep: 3.5-4 hrs (124 batch pickets, 28 rails, 7 posts, beam, plates)
    - fit_tack: 4-5 hrs (gate frame layout, checking square, tacking 46 pickets)
    - full_weld: 6-7 hrs (46 gate pickets × 4 weld points each = 184 fillet welds, plus frame joints)
    - grind_clean: 2.5-3 hrs (die grinder between pickets is slow — tight access)
    - finish_prep + paint: 5-6 hrs (spray setup, 2 coats primer, 2 coats topcoat, dry time)
    - hardware + layout: 2 hrs
  SITE HOURS (stick E7018, ~22-24 hrs):
    - Post holes through pavement + set + concrete: 10-12 hrs
    - Overhead beam lift + weld + hang gate: 5-6 hrs
    - Fence rails + 82 field pickets (stick welded): 6-8 hrs
    - Touch-up paint + inspection: 2 hrs
  Total: ~48-50 hrs. A 6' gate with 0 pickets is ~4-5 hours shop, NOT 26.

BENCHMARK B — Large LED Box Sign
  Scope: 138"x28"x6" aluminum cabinet, laser-cut face letters, TIG welded.
  Pieces: ~40 | Weld: ~100 linear inches TIG | Result: ~22 total labor hours.
  A 48"x24" sign is ~40-50% of this scope. Scale by surface area and piece count.

BENCHMARK C — Simple End Table
  Scope: 4-leg steel frame with cross rails, MIG welded, clear coat finish.
  Pieces: ~8 | Weld: ~20 linear inches | Result: ~5 total labor hours.
  This is the baseline for small furniture. More complex = multiply from here.

SCALING RULES:
- Double the pieces ≈ 1.7x the hours (batch efficiency saves ~15%).
- TIG (aluminum, stainless) = 2.5-3x slower per inch than MIG (mild steel).
- Pickets with jig: 2-3 min/picket to position + tack. Each picket welds to EACH rail it crosses
  (top, mid1, mid2, bottom = 4 weld points per picket). Count total welds, not just pickets.
- Batch cutting: set stop once, feed-and-cut. 50 identical cuts ≈ 25 min total.
- Grinding between pickets: die grinder access only — 2x slower than open grinding.
- Field welding with stick (E7018) is ~1.5x slower per joint than shop MIG.
- Paint for large jobs (100+ pieces): spray setup + 2 primer + 2 topcoat coats = 4-6 hrs minimum.
- Electronics (ESP32, LED, power supply, wiring): ALWAYS 4+ hrs install, never 0.4.
- Gate operators (LiftMaster, US Automatic): 2-3 hrs mount + setup + test.
- When in doubt, estimate LOWER — but do not undercount weld points on repetitive work like pickets.
"""


def _opus_estimate_labor(job_type, cut_list, fields):
    # type: (str, List[Dict], Dict) -> Optional[Dict[str, object]]
    """
    Call Opus to estimate labor hours from job context + cut list.

    Returns a dict matching _fallback_calculate_labor_hours output format,
    or None if Opus is unavailable or returns invalid data.
    """
    from ..claude_client import call_deep, is_configured

    if not is_configured():
        return None

    if not cut_list:
        return None  # Let fallback handle empty cut lists

    # Build context
    finish = str(fields.get("finish", fields.get("finish_type", "raw")) or "raw").lower()
    all_fields = " ".join(str(v) for v in fields.values()).lower()
    description = str(fields.get("description", "") or "")

    is_aluminum = any(k in all_fields for k in ("aluminum", "6061", "5052"))
    is_stainless = any(k in all_fields for k in ("stainless", "304", "316"))

    total_pieces = sum(int(item.get("quantity", 1)) for item in cut_list)

    # Summarize cut list for prompt
    cut_summary_lines = []
    for item in cut_list[:30]:  # Cap at 30 items
        desc = item.get("description", item.get("profile", "unknown"))
        qty = item.get("quantity", 1)
        length = item.get("length_inches", 0)
        cut_type = item.get("cut_type", "square")
        profile = item.get("profile", "")
        group = item.get("group", "")
        weld_proc = item.get("weld_process", "")
        cut_summary_lines.append(
            "  - %s | profile=%s | %.0f\" | qty=%d | cut=%s | group=%s%s"
            % (desc, profile, length, qty, cut_type, group,
               " | weld=%s" % weld_proc if weld_proc else "")
        )

    # Get relevant FAB_KNOWLEDGE context
    fab_knowledge = ""
    try:
        from .fab_knowledge import get_relevant_knowledge
        fab_knowledge = get_relevant_knowledge(
            job_type, finish,
            has_stainless=is_stainless,
            description=description,
        )
    except Exception:
        pass

    material_label = "ALUMINUM" if is_aluminum else ("STAINLESS STEEL" if is_stainless else "MILD STEEL")

    prompt = """You are an expert metal fabrication labor estimator with 20+ years of shop experience.

TASK: Estimate labor hours per process for a %s job.

JOB TYPE: %s
MATERIAL: %s
FINISH: %s
TOTAL PIECES: %d

DESCRIPTION:
%s

CUT LIST:
%s

=== DOMAIN KNOWLEDGE ===
%s

=== LABOR HOUR ESTIMATION ===

Return hours for these 8 processes. These are the ONLY keys you may use:

1. layout_setup — Reading drawings, measuring, marking, squaring table. Usually 1.0-2.0 hrs.
2. cut_prep — Sawing, plasma cutting, deburring. Scale with piece count and cut complexity.
3. fit_tack — Fitting pieces together, clamping, tack welding. Most variable — think carefully.
4. full_weld — Full welding all joints. Base on weld inches and process (MIG vs TIG).
5. grind_clean — Grinding, cleaning, blending welds. Depends on finish requirements.
6. finish_prep — Surface prep for coating. 0 for raw steel.
7. coating_application — In-house clear coat or paint application. 0 for raw/powder coat/galvanized.
8. final_inspection — Always 0.5 hrs.

CRITICAL RULES:
- TIG welding is 2.5-3x slower than MIG. Stainless/aluminum require TIG.
- Outdoor painted steel: grind is cleanup pass, not full furniture-grade grinding.
- Bare metal finish (clear coat, raw, brushed): requires mill scale removal — significant grind time.
- Ground smooth / blended joints: grind time can equal or exceed weld time.
- Batch cutting: identical pieces share setup — one stop setting, then feed-and-cut.
- If powder_coat or galvanized finish: coating_application = 0 (outsourced).
- If raw finish: finish_prep = minimal (1.0 hr cleanup), coating_application = 0.

=== SHOP OWNER REFERENCE DATA ===
%s

Return ONLY valid JSON:
{
    "layout_setup": 1.5,
    "cut_prep": 2.0,
    "fit_tack": 3.0,
    "full_weld": 4.0,
    "grind_clean": 1.5,
    "finish_prep": 1.0,
    "coating_application": 0.0,
    "final_inspection": 0.5,
    "reasoning": "Brief chain of thought explaining your estimates"
}""" % (
        job_type, job_type, material_label, finish, total_pieces,
        description[:500] if description else "(no description)",
        "\n".join(cut_summary_lines) if cut_summary_lines else "  (no cut list)",
        fab_knowledge if fab_knowledge else "(no domain knowledge available)",
        LABOR_CALIBRATION_NOTES,
    )

    text = call_deep(prompt, temperature=0.1, timeout=90)
    if text is None:
        return None

    # Parse response
    try:
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            logger.warning("Opus labor: response is not a dict")
            return None

        # Extract and validate the 8 required keys
        required_keys = [
            "layout_setup", "cut_prep", "fit_tack", "full_weld",
            "grind_clean", "finish_prep", "coating_application", "final_inspection",
        ]

        result = {}
        for key in required_keys:
            val = parsed.get(key, 0.0)
            if isinstance(val, dict):
                val = val.get("hours", 0.0)
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = 0.0
            result[key] = round(max(val, 0.0), 2)

        # Sanity checks
        total_hrs = sum(result.values())
        if total_hrs < 1.0 or total_hrs > 200.0:
            logger.warning(
                "Opus labor: total %.1f hrs out of range [1, 200] — rejecting",
                total_hrs,
            )
            return None

        # Extract reasoning
        reasoning = parsed.get("reasoning", "Opus AI estimation")
        if isinstance(reasoning, dict):
            reasoning = str(reasoning)

        # Guardrails
        flagged = False
        if result["full_weld"] > 40:
            flagged = True
            reasoning += " [FLAGGED: full_weld %.1f > 40 hrs]" % result["full_weld"]
        if result["grind_clean"] > result["full_weld"] * 2:
            flagged = True
            reasoning += " [FLAGGED: grind_clean %.1f > 2x full_weld]" % result["grind_clean"]

        result["_reasoning"] = "Opus AI: " + str(reasoning)
        result["_flagged"] = flagged
        # Track extra keys with zero so downstream code doesn't break
        result["stock_prep_grind"] = 0.0
        result["post_weld_cleanup"] = 0.0

        logger.info(
            "Opus labor for %s: %.1f total hrs (%d pcs)",
            job_type, total_hrs, total_pieces,
        )
        return result

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Opus labor: failed to parse response: %s", e)
        return None


def _fallback_calculate_labor_hours(job_type, cut_list, fields):
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

    is_aluminum = any(k in all_fields for k in ("aluminum", "6061", "5052"))
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
    # Aluminum has no mill scale — suppress unconditionally
    if is_aluminum:
        needs_mill_scale = False
    is_outdoor = job_type in _OUTDOOR_JOB_TYPES

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

    # Sheet/plate piece count — needed for panel/sign grind path
    sheet_piece_count = 0
    for item in cut_list:
        profile = str(item.get("profile", "")).lower()
        if profile.startswith("sheet_") or profile.startswith("plate_"):
            sheet_piece_count += int(item.get("quantity", 1))
    sheet_pct = sheet_piece_count / max(total_pieces, 1)
    is_panel_job = (
        job_type in ("led_sign_custom", "sign_frame")
        or sheet_pct > 0.4
    )

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
    if is_outdoor and has_coating:
        # Outdoor painted/coated: flat cleanup pass — walk the assembly with a flap disc
        # Not per-joint grinding. One pass: hit spatter, sharp edges, high spots.
        # TYPE A structural: 1 min each (inspect joint, knock down spatter)
        # TYPE B decorative/pickets: 0.3 min each (quick pass, less weld to clean)
        # Miters: +2 min each (more cleanup at miter joints)
        grind_min = 30 + type_a_count * 1.0 + type_b_count * 0.3 + miter_cuts * 2
        grind_label = "outdoor cleanup pass"
        if needs_mill_scale:
            grind_min += 90
        grind_clean = max(0.5, grind_min / 60.0)
        reasoning_lines.append(
            "STEP 3 — GRIND (%s): 30 base + %d structural x 1 min + %d decorative x 0.3 min "
            "+ %d miters x 2 min%s = %.1f min (%.2f hr)."
            % (grind_label, type_a_count, type_b_count, miter_cuts,
               " + 90 min mill scale" if needs_mill_scale else "",
               grind_min, grind_clean))
    elif is_panel_job:
        # Sign/panel jobs: surface-area-based grind, not per-joint furniture grind.
        # Sheet pieces get one flap disc pass per face. Structural joints get cleanup only.
        grind_min = 20 + sheet_piece_count * 8 + type_a_joints * 1.5
        grind_label = "panel/sign surface grind"
        if "clear" in finish:
            grind_min = int(grind_min * 0.5)
            grind_label += " (clear coat 0.5x)"
        if is_aluminum:
            grind_min = int(grind_min * 0.7)
            grind_label += " (aluminum 0.7x)"
        if needs_mill_scale:
            grind_min += 90
        grind_clean = max(0.5, grind_min / 60.0)
        reasoning_lines.append(
            "STEP 3 — GRIND (%s): 20 base + %d sheet pcs x 8 min + %d structural joints x 1.5 min"
            "%s = %.1f min (%.2f hr)."
            % (grind_label, sheet_piece_count, type_a_joints,
               " + 90 min mill scale" if needs_mill_scale else "",
               grind_min, grind_clean))
    else:
        # Indoor/furniture/bare metal: full grind — smooth joints, blend welds per-joint
        grind_min = type_a_joints * 6 + type_b_joints * 3 + 30
        grind_label = "indoor full grind"
        if needs_mill_scale:
            grind_min += 90
        grind_clean = max(0.5, grind_min / 60.0)
        reasoning_lines.append(
            "STEP 3 — GRIND (%s): %d TYPE A joints x 6 min + %d TYPE B welds x 3 min "
            "+ 30 min clean%s = %.1f min (%.2f hr)."
            % (grind_label, type_a_joints, type_b_joints,
               " + 90 min mill scale" if needs_mill_scale else "",
               grind_min, grind_clean))

    # --- Grind split for decorative flat bar + bare metal ---
    has_decorative_flat_bar = type_b_count > 0 and any(
        "flat_bar" in str(item.get("profile", "")).lower() for item in cut_list
    )
    stock_prep_grind = 0.0
    post_weld_cleanup = 0.0
    if has_decorative_flat_bar and needs_mill_scale:
        stock_prep_grind = round(grind_clean * 0.65, 2)
        post_weld_cleanup = min(round(grind_clean * 0.35, 2), 2.0)
        reasoning_lines.append(
            "GRIND SPLIT: Decorative flat bar + bare metal → "
            "stock_prep_grind = %.2f hr (65%%), post_weld_cleanup = %.2f hr "
            "(35%%, capped 2.0). Original grind_clean zeroed."
            % (stock_prep_grind, post_weld_cleanup))
        grind_clean = 0.0

    # ======================================================
    # STEP 4 — REMAINING CATEGORIES
    # ======================================================

    # CUT & PREP: batch cutting — identical pieces share setup
    # Group by (profile, length, cut_type) — each batch: set stop once, then feed
    cut_batches = {}  # type: dict
    for item in cut_list:
        profile = str(item.get("profile", ""))
        length = round(item.get("length_inches", 0), 1)
        ct = str(item.get("cut_type", "square")).lower()
        batch_key = (profile, length, ct)
        qty = int(item.get("quantity", 1))
        if batch_key not in cut_batches:
            cut_batches[batch_key] = {"qty": 0, "cut_type": ct}
        cut_batches[batch_key]["qty"] += qty

    cut_min = 0.0
    for batch_key, batch in cut_batches.items():
        is_miter = batch["cut_type"] in ("miter_45", "miter_22.5", "compound")
        setup = 6.0 if is_miter else 4.0   # first piece: measure, mark, set stop
        feed = 1.0 if is_miter else 0.5    # subsequent: feed and cut
        cut_min += setup + max(0, batch["qty"] - 1) * feed
    cut_prep = max(1.0, cut_min / 60.0)
    reasoning_lines.append(
        "CUT BATCH: %d batches from %d pieces. Setup once per batch, feed-and-cut for identical."
        % (len(cut_batches), total_pieces))

    # FIT & TACK: structural frame pieces × 5 min + picket positioning × 2.5 min
    # Pickets require individual measurement, plumbing, clamping, and tack welding
    picket_count = 0
    for item in cut_list:
        text = (str(item.get("description", "")) + " "
                + str(item.get("piece_name", ""))).lower()
        if "picket" in text or "baluster" in text:
            picket_count += int(item.get("quantity", 1))
    fit_min = type_a_count * 5 + picket_count * 2.5  # 2.5 min/picket to position/plumb/tack
    fit_tack = max(1.0, fit_min / 60.0)

    # Pre-punched channel reduces picket positioning time by ~35%
    # Channel self-spaces pickets — no individual measuring/plumbing needed
    uses_punched_channel = any(
        "punched_channel" in str(item.get("profile", ""))
        for item in cut_list
    )
    if uses_punched_channel and picket_count > 0:
        fit_tack = max(1.0, fit_tack * 0.65)  # 35% reduction
        # Grind fix: punched channel pickets sit in pre-punched holes,
        # grind is per channel run not per picket
        channel_runs = sum(
            int(item.get("quantity", 1)) for item in cut_list
            if "punched_channel" in str(item.get("profile", ""))
        )
        picket_grind_min = picket_count * 2  # what was counted (2 joints/picket × 1 min each)
        channel_grind_min = channel_runs * 4  # 4 min per channel run cleanup
        grind_clean = max(0.5, grind_clean - (picket_grind_min - channel_grind_min) / 60.0)
        reasoning_lines.append(
            "PUNCHED CHANNEL grind fix: -%d picket-joint min, +%d channel-run min."
            % (picket_grind_min, channel_grind_min)
        )

    # Plate cutting labor: plasma cut + deburr adds 8 min per piece
    plate_piece_count = 0
    for item in cut_list:
        profile = str(item.get("profile", "")).lower()
        if profile.startswith("plate_") or profile.startswith("sheet_"):
            plate_piece_count += int(item.get("quantity", 1))
    if plate_piece_count > 0:
        plate_cut_min = plate_piece_count * 8  # layout + plasma cut + deburr
        cut_prep = cut_prep + plate_cut_min / 60.0
        reasoning_lines.append(
            "PLATE CUTTING: %d plate/sheet pcs × 8 min = %d min added to cut_prep."
            % (plate_piece_count, plate_cut_min)
        )

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
    # Estimate surface area from cut list for paint coverage
    total_length_ft = sum(
        item.get("length_inches", 0) * item.get("quantity", 1) / 12.0
        for item in cut_list)
    est_sqft = total_length_ft * 0.5  # rough: ~6" average exposed surface width

    if "clear" in finish:
        coating_application = 1.0
    elif "paint" in finish and "powder" not in finish:
        # Prime + paint: 0.5 hr per 100 sqft + 1.5 hr setup/cleanup/dry
        coating_application = max(2.0, est_sqft / 100.0 * 0.5 + 1.5)
    elif "powder" in finish or "galv" in finish:
        coating_application = 0.0
    elif "raw" in finish:
        coating_application = 0.0
    else:
        coating_application = 0.0

    # FINAL INSPECTION
    final_inspection = 0.5

    punched_note = " (x 0.65 pre-punched channel)" if uses_punched_channel and picket_count > 0 else ""
    reasoning_lines.append(
        "STEP 4 — CUT: %d batches, %.1f min (%.2f hr). "
        "FIT: %d TYPE A x 5 min + %d pickets x 2.5 min = %.1f min (%.2f hr)%s. "
        "LAYOUT: 1.5 + 0.25 x %d/10 = %.2f hr."
        % (len(cut_batches), cut_min, cut_prep,
           type_a_count, picket_count, fit_min, fit_tack, punched_note,
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
                 + grind_clean + stock_prep_grind + post_weld_cleanup
                 + finish_prep + coating_application + final_inspection)
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
        "stock_prep_grind": _safe(stock_prep_grind),
        "post_weld_cleanup": _safe(post_weld_cleanup),
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
