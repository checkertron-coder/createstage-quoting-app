"""
Shop context builder — formats equipment profile into an Opus-readable context block.

Used by ai_cut_list.py and labor_estimator.py to inject shop capabilities into prompts.
If no profile exists, returns empty string — Opus falls back to general knowledge.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from . import models

logger = logging.getLogger(__name__)


def build_shop_context(user_id: int, db: Session) -> str:
    """
    Build a concise shop capabilities block from the user's equipment profile.

    Returns an empty string if no profile exists — Opus uses general knowledge.
    """
    if not user_id or not db:
        return ""

    try:
        equipment = db.query(models.ShopEquipment).filter(
            models.ShopEquipment.user_id == user_id
        ).first()
    except Exception as e:
        logger.warning("Failed to load shop equipment for user %s: %s", user_id, e)
        return ""

    if not equipment:
        return ""

    lines = []

    # Welding
    welding = equipment.welding_processes or []
    if welding:
        weld_parts = []
        for w in welding:
            proc = w.get("process", "unknown")
            wire = w.get("wire_type", "")
            primary = w.get("primary", False)
            notes = w.get("notes", "")
            desc = proc
            if wire:
                desc += " (%s)" % wire
            if primary:
                desc += " [primary]"
            if notes:
                desc += " — %s" % notes
            weld_parts.append(desc)
        lines.append("- Welding: %s" % ", ".join(weld_parts))
    else:
        lines.append("- Welding: not specified")

    # Cutting
    cutting = equipment.cutting_capabilities or []
    if cutting:
        cut_parts = []
        for c in cutting:
            tool = c.get("tool", "unknown")
            cnc = c.get("cnc", False)
            notes = c.get("notes", "")
            if cnc:
                tool += " (CNC)"
            if notes:
                tool += " — %s" % notes
            cut_parts.append(tool)
        lines.append("- Cutting: %s" % ", ".join(cut_parts))
    else:
        lines.append("- Cutting: not specified")

    # Forming
    forming = equipment.forming_equipment or []
    if forming:
        form_parts = []
        for f in forming:
            tool = f.get("tool", "unknown")
            specs = f.get("specs", "")
            notes = f.get("notes", "")
            if specs:
                tool += " (%s)" % specs
            if notes:
                tool += " — %s" % notes
            form_parts.append(tool)
        lines.append("- Forming: %s" % ", ".join(form_parts))
    else:
        lines.append("- Forming: none — outsource bending/forming")

    # Finishing
    finishing = equipment.finishing_capabilities or []
    if finishing:
        in_house = []
        outsourced = []
        for f in finishing:
            method = f.get("method", "unknown")
            notes = f.get("notes", "")
            if notes:
                method += " — %s" % notes
            if f.get("in_house", False):
                in_house.append(method)
            else:
                outsourced.append(method)
        parts = []
        if in_house:
            parts.append("In-house: %s" % ", ".join(in_house))
        if outsourced:
            parts.append("Outsource: %s" % ", ".join(outsourced))
        lines.append("- Finishing: %s" % "; ".join(parts))
    else:
        lines.append("- Finishing: not specified")

    # Shop notes
    notes = equipment.shop_notes
    if notes:
        lines.append("- Notes: %s" % notes)

    if not any(l != "- Welding: not specified" and
               l != "- Cutting: not specified" and
               l != "- Forming: none — outsource bending/forming" and
               l != "- Finishing: not specified"
               for l in lines):
        return ""

    return "\n".join(lines)


def build_shop_context_block(user_id: int, db: Session) -> str:
    """
    Build the full prompt block with header. Returns empty string if no context.
    """
    context = build_shop_context(user_id, db)
    if not context:
        return ""

    return """
SHOP EQUIPMENT & CAPABILITIES (this shop's actual tools — adjust estimates accordingly):
%s

IMPORTANT: Use ONLY processes this shop can perform in-house. If a process is unavailable,
note it as outsourced and estimate outsource cost instead of in-house labor. If the shop
has a CNC plasma table, use CNC cut times (faster, more precise). If they only have a
hand plasma or torch, use manual cut times. Match weld process to what the shop actually runs.
---
""" % context
