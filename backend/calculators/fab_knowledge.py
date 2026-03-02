"""
Fabrication knowledge injection for AI prompts.

Reads FAB_KNOWLEDGE.md from the repo root, parses it by ## section headers,
and returns targeted snippets relevant to a specific job type and finish.

Keeps token budget low (~300-500 words) by extracting only actionable rules.
Handles missing file gracefully (returns empty string).
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Locate FAB_KNOWLEDGE.md relative to this file
_KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent.parent / "FAB_KNOWLEDGE.md"

# Parsed sections cache (loaded once at import time)
_SECTIONS = {}  # type: dict[str, str]

try:
    _raw = _KNOWLEDGE_PATH.read_text(encoding="utf-8")
    # Split by ## headers, keeping the header text
    _parts = re.split(r'^(## .+)$', _raw, flags=re.MULTILINE)
    # _parts alternates: [preamble, header1, body1, header2, body2, ...]
    for i in range(1, len(_parts) - 1, 2):
        header = _parts[i].strip().lstrip("# ").strip()
        body = _parts[i + 1].strip()
        _SECTIONS[header] = body
    logger.info("Loaded %d sections from FAB_KNOWLEDGE.md", len(_SECTIONS))
except FileNotFoundError:
    logger.warning("FAB_KNOWLEDGE.md not found at %s — knowledge injection disabled", _KNOWLEDGE_PATH)
except Exception as e:
    logger.warning("Failed to parse FAB_KNOWLEDGE.md: %s", e)


def _find_section(keyword: str) -> Optional[str]:
    """Find a section by keyword match in the header."""
    for header, body in _SECTIONS.items():
        if keyword.lower() in header.lower():
            return body
    return None


def _trim_to_rules(text: str, max_lines: int = 15) -> str:
    """Trim a section body to its most actionable lines."""
    lines = text.strip().split("\n")
    kept = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Keep bullet points, table rows, numbered items, and short headings
        if (s.startswith("-") or s.startswith("|") or
                re.match(r'^\d+\.', s) or s.startswith("###") or
                s.startswith("*")):
            kept.append(line)
        if len(kept) >= max_lines:
            break
    return "\n".join(kept)


# --- Pre-extracted summaries (trimmed at import time for speed) ---

def _build_welding_summary() -> str:
    """Extract key welding process rules."""
    raw = _find_section("WELDING PROCESSES")
    if not raw:
        return ""
    return """WELDING PROCESS SELECTION:
- MIG (ER70S-6, 75/25 gas): structural frames, furniture legs, railings, gates. Mild steel >=12ga. Long welds.
- TIG (ER70S-2 mild, ER308L stainless): stainless steel, thin sheet <=14ga, visible/decorative welds, ground-flush joints.
- TIG labor = 2.5-3x MIG for same weld length.
- Fillet size rule: 3/4 x thinner plate thickness. 3/16" fillet sufficient for most furniture on 1" tube.
- Overwelding = wasted time + heat distortion."""


def _build_labor_summary() -> str:
    """Extract key labor time standards."""
    raw = _find_section("LABOR ESTIMATION")
    if not raw:
        return ""
    return """LABOR TIME STANDARDS:
- Chop saw cut (1" tube): 2-3 min/cut. (2" tube): 3-5 min/cut.
- Cope/notch tube end: 10-20 min/end.
- MIG fillet (3/16"): 12-18 in/min travel. TIG fillet: 4-6 in/min travel.
- Grind weld flush: 5-10 min/ft. Brush finish: 15-30 min/sq ft.
- Stainless multiplier: 1.5x. Thin material (<=16ga): 1.4x. Overhead position: 1.7x."""


def _build_distortion_table() -> str:
    """Extract distortion risk table."""
    raw = _find_section("DISTORTION CONTROL")
    if not raw:
        return ""
    return """DISTORTION CONTROL:
- Furniture (flat bar top): HIGH risk — alternate welds, backstep.
- Railing (post-to-rail): MEDIUM — tack sequence, balanced welding.
- Gate (diagonal frame): HIGH — pre-set, weld toward center.
- Sign frame (thin sheet): HIGH — TIG or intermittent MIG.
- Structural frame (heavy): LOW — mass absorbs heat.
- Always tack all corners before continuous welds. Check square at every stage."""


def _build_mill_scale_rules() -> str:
    """Extract mill scale decision tree — reflects both before-cutting and after-welding paths."""
    return """MILL SCALE DECISION:
- Powder coat or paint: SKIP mill scale removal. Clean + degrease only.
- Clear coat / raw / brushed / patina: REMOVE mill scale. WHEN depends on the pieces:
  - Decorative flat bar / small pieces that will be hard to grind after cutting: Remove on RAW STOCK BEFORE cutting (Principle 1 — workability). Vinegar bath full lengths, heavy grind to finish, then cut to size.
  - Large structural pieces / tube frames: Remove AFTER all welding is done. Assembly is stable enough to grind.
  - Apply Principle 1 (workability) and Principle 2 (access) to determine which path fits the specific job.
- TIG weld areas: remove scale at weld zones before welding (grind or flap disc) — mill scale causes porosity with TIG.
- Methods: vinegar bath (small parts, 12-24hr soak), flap disc grind (fastest for accessible areas), wire wheel (welds/transitions)."""


def _build_stainless_notes() -> str:
    """Extract stainless-specific rules."""
    return """STAINLESS STEEL RULES:
- ALWAYS use stainless filler (ER308L for 304, ER309L for dissimilar).
- Dedicate grinding wheels, wire brushes, clamps — carbon steel contamination causes rust.
- TIG preferred for thin stainless. Keep heat input low.
- Back-purge with argon for full-pen welds on pipe/tube (prevents sugaring).
- Harder to cut — adjust chop saw RPM down, use stainless-rated blades."""


def _build_furniture_sequence() -> str:
    """Extract furniture build sequence from current FAB_KNOWLEDGE.md Section 5."""
    raw = _find_section("BUILD SEQUENCE")
    if not raw:
        return ""
    # Extract the Furniture subsection from the full build sequence section
    lines = raw.split("\n")
    furniture_lines = []
    in_furniture = False
    for line in lines:
        if "### Furniture" in line:
            in_furniture = True
            continue
        elif line.startswith("### ") and in_furniture:
            break  # Hit next subsection
        elif in_furniture:
            furniture_lines.append(line)
    if furniture_lines:
        return "FURNITURE BUILD SEQUENCE (from FAB_KNOWLEDGE.md):\n" + "\n".join(
            l for l in furniture_lines if l.strip()
        )
    return ""


def _build_railing_sequence() -> str:
    """Extract railing build sequence."""
    return """RAILING BUILD SEQUENCE:
1. Measure in-field — do not trust drawings alone for existing structures.
2. Fabricate top rail and bottom plate as flat assemblies.
3. Cut and fit balusters — jig for spacing consistency.
4. Tack all balusters before welding (spacing is locked once welded).
5. Weld balusters from center out to minimize accumulated spacing error.
6. Weld top and bottom rail connections.
7. Grind welds visible from walking side.
8. Prime/paint before installation (touch up field welds after)."""


def _build_gate_sequence() -> str:
    """Extract gate build sequence."""
    return """GATE BUILD SEQUENCE:
1. Lay out frame on welding table — square is critical.
2. Cut frame members with compound miter where needed.
3. Tack and check diagonal — gates are large, distortion is amplified.
4. Weld frame with backstep technique on long members.
5. Fit and weld infill (pickets, flat bar pattern, mesh).
6. Add hardware mounting plates (hinges, latch) BEFORE surface finishing.
7. Mock-install hinges and check swing before powder coat.
8. Surface prep and finish. Install hardware. Install gate."""


def _build_reasoning_principles() -> str:
    """Extract Section 12 — Fabrication Reasoning Principles. Always included."""
    raw = _find_section("FABRICATION REASONING PRINCIPLES")
    if not raw:
        return ""
    return "FABRICATION REASONING PRINCIPLES:\n" + _trim_to_rules(raw, max_lines=40)


def _build_decorative_stock_prep() -> str:
    """Extract Section 11 — Decorative Stock Prep. Included for decorative + bare metal jobs."""
    raw = _find_section("DECORATIVE STOCK PREP")
    if not raw:
        return ""
    return "DECORATIVE STOCK PREP — PROCESS ORDER:\n" + _trim_to_rules(raw, max_lines=30)


# Cache the always-included snippets
_WELDING_SUMMARY = _build_welding_summary()
_LABOR_SUMMARY = _build_labor_summary()
_DISTORTION_TABLE = _build_distortion_table()
_MILL_SCALE_RULES = _build_mill_scale_rules()
_STAINLESS_NOTES = _build_stainless_notes()
_FURNITURE_SEQ = _build_furniture_sequence()
_RAILING_SEQ = _build_railing_sequence()
_GATE_SEQ = _build_gate_sequence()
_REASONING_PRINCIPLES = _build_reasoning_principles()
_DECORATIVE_STOCK_PREP = _build_decorative_stock_prep()


def get_relevant_knowledge(job_type: str, finish_type: str,
                           has_stainless: bool = False,
                           description: str = "") -> str:
    """
    Return a focused knowledge snippet for AI prompt injection.

    Args:
        job_type: The job type string (e.g. "furniture_table")
        finish_type: The finish description from user fields
        has_stainless: True if stainless steel is involved
        description: Job description text (for keyword detection)

    Returns:
        A string of relevant fab knowledge,
        or empty string if FAB_KNOWLEDGE.md is missing.
    """
    if not _SECTIONS:
        return ""

    sections = []

    # ALWAYS include reasoning principles — these apply to every job
    if _REASONING_PRINCIPLES:
        sections.append(_REASONING_PRINCIPLES)

    # Always include welding process summary and distortion table
    if _WELDING_SUMMARY:
        sections.append(_WELDING_SUMMARY)
    if _DISTORTION_TABLE:
        sections.append(_DISTORTION_TABLE)

    # Mill scale rules — include when finish suggests bare metal
    finish_lower = str(finish_type).lower()
    bare_metal_keywords = [
        "clear_coat", "clear coat", "clearcoat",
        "raw", "waxed", "raw_steel", "raw steel",
        "brushed", "brushed_steel", "brushed steel",
        "patina", "chemical_patina",
    ]
    is_bare_metal = any(k in finish_lower for k in bare_metal_keywords)
    if is_bare_metal:
        sections.append(_MILL_SCALE_RULES)

    # Decorative stock prep — when description has decorative keywords + bare metal
    desc_lower = str(description).lower()
    decorative_keywords = [
        "decorative", "pattern", "layered", "woven", "ornamental",
        "pyramid", "concentric", "inlay", "flat bar",
    ]
    has_decorative = any(k in desc_lower for k in decorative_keywords)
    if has_decorative and is_bare_metal and _DECORATIVE_STOCK_PREP:
        sections.append(_DECORATIVE_STOCK_PREP)

    # Job-type-specific build sequences
    jt = str(job_type).lower()
    if "furniture" in jt or "table" in jt:
        if _FURNITURE_SEQ:
            sections.append(_FURNITURE_SEQ)
    elif "railing" in jt:
        if _RAILING_SEQ:
            sections.append(_RAILING_SEQ)
    elif "gate" in jt:
        if _GATE_SEQ:
            sections.append(_GATE_SEQ)

    # Stainless notes
    if has_stainless and _STAINLESS_NOTES:
        sections.append(_STAINLESS_NOTES)

    # Always include labor summary
    if _LABOR_SUMMARY:
        sections.append(_LABOR_SUMMARY)

    if not sections:
        return ""

    return "\n\n".join(sections)
