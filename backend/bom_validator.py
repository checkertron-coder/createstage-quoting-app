"""
BOM Validator — validates hardware BOM against fabrication build instructions.

Ensures every hardware item in the BOM corresponds to at least one fabrication
step. Items that don't match any step are flagged as orphaned.

Consumables (wire, discs, gas, tape) and electronics always pass.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Keywords that identify consumable/shop-stock items — never orphaned
_CONSUMABLE_KEYWORDS = (
    "wire", "disc", "gas", "tape", "sandpaper", "solvent",
    "primer", "paint", "spray", "welding", "grinding", "flap",
    "shielding", "clear coat", "clearcoat", "denatured",
)

# Keywords that identify electronics items
_ELECTRONICS_KEYWORDS = (
    "esp32", "arduino", "led", "power supply", "psu", "controller",
    "cable gland", "connector", "heat shrink", "driver", "module",
    "wire harness", "wiring",
)

# Filler/adjective words to strip when extracting key nouns
_STRIP_WORDS = {
    "heavy", "duty", "standard", "premium", "pair", "set", "pack",
    "qty", "x", "of", "with", "for", "the", "and", "a", "an",
    "estimated", "est", "large", "small", "medium",
}


def _extract_key_nouns(description):
    # type: (str) -> set
    """Extract meaningful nouns from a hardware description."""
    desc = re.sub(r'[^a-z0-9\s]', ' ', description.lower())
    words = desc.split()
    return {w for w in words if w not in _STRIP_WORDS and len(w) > 2}


def _is_consumable(description):
    # type: (str) -> bool
    """Check if a hardware item is a consumable/shop-stock item."""
    desc_lower = description.lower()
    return any(kw in desc_lower for kw in _CONSUMABLE_KEYWORDS)


def _is_electronics(description):
    # type: (str) -> bool
    """Check if a hardware item is an electronics component."""
    desc_lower = description.lower()
    return any(kw in desc_lower for kw in _ELECTRONICS_KEYWORDS)


def _build_step_text(step):
    # type: (dict) -> str
    """Concatenate all text fields from a build step for matching."""
    parts = []
    parts.append(str(step.get("title", "")))
    parts.append(str(step.get("description", "")))
    tools = step.get("tools", [])
    if isinstance(tools, list):
        parts.extend(str(t) for t in tools)
    return " ".join(parts).lower()


def validate_bom_against_build(hardware, build_instructions):
    # type: (list, list) -> dict
    """
    Validate hardware BOM against build instructions.

    For each hardware item, check if its description (key nouns) appears in
    any build step's title, description, or tools list.

    Args:
        hardware: list of hardware item dicts with 'description'
        build_instructions: list of build step dicts with 'title', 'description', 'tools'

    Returns:
        {
            "kept": [items matching build steps],
            "orphaned": [items with no matching build step],
            "orphan_reasons": ["Item X: no matching build step found"],
        }
    """
    if not hardware:
        return {"kept": [], "orphaned": [], "orphan_reasons": []}

    # If no build instructions, keep everything (can't validate)
    if not build_instructions:
        return {"kept": list(hardware), "orphaned": [], "orphan_reasons": []}

    # Pre-compute all build step text
    all_step_text = " ".join(_build_step_text(s) for s in build_instructions)

    # Check for any electronics step
    has_electronics_step = any(
        kw in all_step_text
        for kw in ("electron", "wiring", "install controller", "led", "power")
    )

    kept = []
    orphaned = []
    orphan_reasons = []

    for item in hardware:
        desc = str(item.get("description", ""))

        # Consumables always pass
        if _is_consumable(desc):
            kept.append(item)
            continue

        # Electronics pass if ANY build step mentions electronics/wiring/install
        if _is_electronics(desc):
            if has_electronics_step:
                kept.append(item)
            else:
                orphaned.append(item)
                orphan_reasons.append(
                    "%s: electronics item but no electronics/wiring step in build sequence" % desc
                )
            continue

        # Extract key nouns and check against all build step text
        nouns = _extract_key_nouns(desc)
        matched = any(noun in all_step_text for noun in nouns)

        if matched:
            kept.append(item)
        else:
            orphaned.append(item)
            orphan_reasons.append(
                "%s: no matching build step found" % desc
            )

    if orphaned:
        logger.info(
            "BOM validation: kept %d, orphaned %d items: %s",
            len(kept), len(orphaned),
            [o.get("description", "?") for o in orphaned],
        )

    return {
        "kept": kept,
        "orphaned": orphaned,
        "orphan_reasons": orphan_reasons,
    }
