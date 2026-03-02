"""
Fabrication knowledge injection for AI prompts.

Sources knowledge from structured Python modules in backend/knowledge/
(processes, materials, joints, consumables, validation) and supplements
with build sequence prose from FAB_KNOWLEDGE.md.

Keeps token budget low (~300-500 words) by extracting only actionable rules.
"""

import logging
import re
from pathlib import Path
from typing import Optional

from ..knowledge.materials import (
    DISTORTION_RISK,
    LABOR_MULTIPLIERS,
    POSITION_MULTIPLIERS,
)
from ..knowledge.processes import (
    get_process,
    get_banned_terms,
)
from ..knowledge.validation import (
    check_banned_terms,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FAB_KNOWLEDGE.md — still used for build sequence prose sections.
# Structured data (welding, labor, distortion, mill scale, stainless) now
# comes from backend/knowledge/ modules.
# ---------------------------------------------------------------------------

_KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent.parent / "FAB_KNOWLEDGE.md"

_SECTIONS = {}  # type: dict[str, str]

try:
    _raw = _KNOWLEDGE_PATH.read_text(encoding="utf-8")
    _parts = re.split(r'^(## .+)$', _raw, flags=re.MULTILINE)
    for i in range(1, len(_parts) - 1, 2):
        header = _parts[i].strip().lstrip("# ").strip()
        body = _parts[i + 1].strip()
        _SECTIONS[header] = body
    logger.info("Loaded %d sections from FAB_KNOWLEDGE.md", len(_SECTIONS))
except FileNotFoundError:
    logger.warning("FAB_KNOWLEDGE.md not found at %s — build sequences unavailable", _KNOWLEDGE_PATH)
except Exception as e:
    logger.warning("Failed to parse FAB_KNOWLEDGE.md: %s", e)


def _find_section(keyword):
    # type: (str) -> Optional[str]
    """Find a section by keyword match in the header."""
    for header, body in _SECTIONS.items():
        if keyword.lower() in header.lower():
            return body
    return None


# ---------------------------------------------------------------------------
# Pre-built summaries — sourced from structured knowledge modules
# ---------------------------------------------------------------------------

def _build_welding_summary():
    # type: () -> str
    """Build welding process summary from structured process data."""
    mig = get_process("mig_weld")
    tig = get_process("tig_weld")
    if not mig or not tig:
        return ""
    return """WELDING PROCESS SELECTION:
- MIG (ER70S-6, 75/25 gas): structural frames, furniture legs, railings, gates. Mild steel >=12ga. Long welds.
- TIG (ER70S-2 mild, ER308L stainless): stainless steel, thin sheet <=14ga, visible/decorative welds, ground-flush joints.
- TIG labor = 2.5-3x MIG for same weld length.
- Fillet size rule: 3/4 x thinner plate thickness. 3/16" fillet sufficient for most furniture on 1" tube.
- Overwelding = wasted time + heat distortion."""


def _build_labor_summary():
    # type: () -> str
    """Build labor time standards from structured process data."""
    chop = get_process("chop_saw_cut")
    grinder = get_process("angle_grinder_grinding")
    if not chop or not grinder:
        return ""
    return """LABOR TIME STANDARDS:
- Chop saw cut (1" tube): 2-3 min/cut. (2" tube): 3-5 min/cut.
- Cope/notch tube end: 10-20 min/end.
- MIG fillet (3/16"): 12-18 in/min travel. TIG fillet: 4-6 in/min travel.
- Grind weld flush: 5-10 min/ft. Brush finish: 15-30 min/sq ft.
- Die grinder cleanup (tight access): 3-5 min per weld area.
- Stainless multiplier: %.1fx. Thin material (<=16ga): 1.4x. Overhead position: %.1fx.
- Tooling access: 4.5" angle grinder (open surfaces), die grinder with 2" roloc (constrained spaces), hand files (tight spots). "Inaccessible" = smaller tooling + more time, not impossible.""" % (
        LABOR_MULTIPLIERS.get("stainless_304", 1.5),
        POSITION_MULTIPLIERS.get("overhead_4f_4g", 1.7),
    )


def _build_distortion_table():
    # type: () -> str
    """Build distortion risk table from structured material data."""
    if not DISTORTION_RISK:
        return ""

    # Extract key job types for the concise summary
    lines = ["DISTORTION CONTROL:"]
    key_jobs = [
        ("furniture_table", "Furniture (flat bar top)"),
        ("straight_railing", "Railing (post-to-rail)"),
        ("cantilever_gate", "Gate (diagonal frame)"),
        ("sign_frame", "Sign frame (thin sheet)"),
        ("structural_frame", "Structural frame (heavy)"),
    ]
    for job_key, label in key_jobs:
        info = DISTORTION_RISK.get(job_key, {})
        risk = info.get("risk", "medium").upper()
        control = info.get("control", "Standard controls")
        lines.append("- %s: %s — %s." % (label, risk, control))
    lines.append("- Always tack all corners before continuous welds. Check square at every stage.")
    return "\n".join(lines)


def _build_mill_scale_rules():
    # type: () -> str
    """Build mill scale decision rules from structured process data."""
    vinegar = get_process("vinegar_bath")
    if not vinegar:
        return ""
    return """MILL SCALE DECISION:
- Powder coat or paint: SKIP mill scale removal. Clean + degrease only.
- Clear coat / raw / brushed / patina: REMOVE mill scale. WHEN depends on the pieces:
  - Decorative flat bar / small pieces that will be hard to grind after cutting: Remove on RAW STOCK BEFORE cutting (Principle 1 — workability). Vinegar bath full lengths, heavy grind to finish, then cut to size.
  - Large structural pieces / tube frames: Remove AFTER all welding is done. Assembly is stable enough to grind.
  - Apply Principle 1 (workability) and Principle 2 (access) to determine which path fits the specific job.
- TIG weld areas: remove scale at weld zones before welding (grind or flap disc) — mill scale causes porosity with TIG.
- Methods: vinegar bath (small parts, 12-24hr soak), flap disc grind (fastest for accessible areas), wire wheel (welds/transitions)."""


def _build_stainless_notes():
    # type: () -> str
    """Build stainless-specific rules from structured material data."""
    return """STAINLESS STEEL RULES:
- ALWAYS use stainless filler (ER308L for 304, ER309L for dissimilar).
- Dedicate grinding wheels, wire brushes, clamps — carbon steel contamination causes rust.
- TIG preferred for thin stainless. Keep heat input low.
- Back-purge with argon for full-pen welds on pipe/tube (prevents sugaring).
- Harder to cut — adjust chop saw RPM down, use stainless-rated blades."""


def _build_furniture_sequence():
    # type: () -> str
    """Extract furniture build sequence from FAB_KNOWLEDGE.md Section 5."""
    raw = _find_section("BUILD SEQUENCE")
    if not raw:
        return ""
    lines = raw.split("\n")
    furniture_lines = []
    in_furniture = False
    for line in lines:
        if "### Furniture" in line:
            in_furniture = True
            continue
        elif line.startswith("### ") and in_furniture:
            break
        elif in_furniture:
            furniture_lines.append(line)
    if furniture_lines:
        return "FURNITURE BUILD SEQUENCE (from FAB_KNOWLEDGE.md):\n" + "\n".join(
            l for l in furniture_lines if l.strip()
        )
    return ""


def _build_railing_sequence():
    # type: () -> str
    """Extract railing build sequence from FAB_KNOWLEDGE.md Section 5."""
    raw = _find_section("BUILD SEQUENCE")
    if not raw:
        return ""
    lines = raw.split("\n")
    railing_lines = []
    in_railing = False
    for line in lines:
        if "### Railings" in line:
            in_railing = True
            continue
        elif line.startswith("### ") and in_railing:
            break
        elif in_railing:
            railing_lines.append(line)
    if railing_lines:
        return "RAILING BUILD SEQUENCE (from FAB_KNOWLEDGE.md):\n" + "\n".join(
            l for l in railing_lines if l.strip()
        )
    return ""


def _build_gate_sequence():
    # type: () -> str
    """Extract gate build sequence from FAB_KNOWLEDGE.md Section 5."""
    raw = _find_section("BUILD SEQUENCE")
    if not raw:
        return ""
    lines = raw.split("\n")
    gate_lines = []
    in_gate = False
    for line in lines:
        if "### Gates" in line:
            in_gate = True
            continue
        elif line.startswith("### ") and in_gate:
            break
        elif in_gate:
            gate_lines.append(line)
    if gate_lines:
        return "GATE BUILD SEQUENCE (from FAB_KNOWLEDGE.md):\n" + "\n".join(
            l for l in gate_lines if l.strip()
        )
    return ""


def _build_reasoning_principles():
    # type: () -> str
    """Extract Section 12 — Fabrication Reasoning Principles. Always included.

    Uses full text (not trimmed) because principles contain critical
    prose paragraphs essential for AI reasoning.
    """
    raw = _find_section("FABRICATION REASONING PRINCIPLES")
    if not raw:
        return ""
    lines = raw.strip().split("\n")
    kept = [l for l in lines if l.strip()]
    return "FABRICATION REASONING PRINCIPLES:\n" + "\n".join(kept[:60])


def _build_decorative_stock_prep():
    # type: () -> str
    """Build decorative stock prep rules from structured process data + FAB_KNOWLEDGE.md.

    Uses full text because this section contains critical prose paragraphs
    (spacer dimensions, why-this-matters) essential for AI reasoning.
    """
    # Try structured data first
    proc = get_process("decorative_stock_prep")
    if proc:
        notes = proc.get("notes", "")
        never = get_banned_terms("decorative_stock_prep")
        result = "DECORATIVE STOCK PREP — PROCESS ORDER:\n"
        result += notes + "\n"
        if never:
            result += "NEVER: " + ", ".join(never) + "\n"

    # Supplement with FAB_KNOWLEDGE.md prose (has spacer dimensions, etc.)
    raw = _find_section("DECORATIVE STOCK PREP")
    if raw:
        lines = raw.strip().split("\n")
        kept = [l for l in lines if l.strip()]
        return "DECORATIVE STOCK PREP — PROCESS ORDER:\n" + "\n".join(kept[:50])

    if proc:
        return result
    return ""


# Cache the always-included snippets at import time
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

# Knowledge is available if structured modules loaded (always True since they're
# Python code, not external files). FAB_KNOWLEDGE.md is optional supplemental.
_KNOWLEDGE_AVAILABLE = True


def get_relevant_knowledge(job_type, finish_type,
                           has_stainless=False,
                           description=""):
    # type: (str, str, bool, str) -> str
    """
    Return a focused knowledge snippet for AI prompt injection.

    Args:
        job_type: The job type string (e.g. "furniture_table")
        finish_type: The finish description from user fields
        has_stainless: True if stainless steel is involved
        description: Job description text (for keyword detection)

    Returns:
        A string of relevant fab knowledge.
    """
    if not _KNOWLEDGE_AVAILABLE:
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
