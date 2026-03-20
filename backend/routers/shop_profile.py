"""
Shop equipment profile — conversational onboarding + CRUD.

Endpoints:
- POST /api/shop/onboarding — submit free-text answers, Opus interprets
- GET  /api/shop/equipment  — get current equipment profile
- PUT  /api/shop/equipment  — update structured equipment profile
"""

import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shop", tags=["shop"])


# --- Request/Response schemas ---

class OnboardingRequest(BaseModel):
    welding_answer: str
    forming_answer: str
    finishing_answer: str


class EquipmentUpdate(BaseModel):
    welding_processes: Optional[list] = None
    cutting_capabilities: Optional[list] = None
    forming_equipment: Optional[list] = None
    finishing_capabilities: Optional[list] = None
    shop_notes: Optional[str] = None


class EquipmentResponse(BaseModel):
    welding_processes: list = []
    cutting_capabilities: list = []
    forming_equipment: list = []
    finishing_capabilities: list = []
    raw_welding_answer: Optional[str] = None
    raw_forming_answer: Optional[str] = None
    raw_finishing_answer: Optional[str] = None
    shop_notes: Optional[str] = None
    onboarding_complete: bool = False


# --- Opus interpretation ---

def _interpret_with_opus(welding_answer: str, forming_answer: str, finishing_answer: str) -> dict:
    """
    Send free-text onboarding answers to Opus for structured interpretation.
    Returns a dict with welding_processes, cutting_capabilities, forming_equipment,
    finishing_capabilities.
    """
    prompt = """You are interpreting a fabricator's description of their shop equipment.
They answered three questions about their capabilities. Extract structured data from their answers.

IMPORTANT DISTINCTIONS:
- "Hand plasma" / "plasma cutter" = handheld plasma torch (operator-guided, freehand cuts)
- "CNC plasma table" / "plasma table with CNC" = automated CNC machine (programmatic cuts, nesting)
- A "plasma table" with no mention of CNC is just a flat cutting surface — NOT automated
- "Cold saw" vs "chop saw" vs "band saw" — these are distinct tools
- "Flux core" / "FCAW" = self-shielded wire (no gas needed, outdoor-capable, more spatter)
- "MIG" / "GMAW" = gas-shielded solid wire (cleaner, requires gas bottle)
- "Dual shield" = flux core with gas shielding (best penetration)

Question 1 — Welding & Cutting:
"%s"

Question 2 — Forming & Fabrication:
"%s"

Question 3 — Finishing:
"%s"

Return ONLY valid JSON with this structure:
{
    "shop_summary": "A 2-4 sentence factual summary of this shop's capabilities, written in third person. Describe what kind of work this shop is set up for based on their equipment. Be specific — mention their primary welding process, key tools, and finishing approach. Sound like a knowledgeable fabricator describing a peer's shop, not a marketing brochure.",
    "welding_processes": [
        {"process": "MIG", "primary": true, "wire_type": "flux core", "notes": ""}
    ],
    "cutting_capabilities": [
        {"tool": "hand plasma", "cnc": false, "notes": ""},
        {"tool": "cold saw", "cnc": false, "notes": ""}
    ],
    "forming_equipment": [
        {"tool": "press brake", "specs": "60 ton, 6ft bed", "notes": ""}
    ],
    "finishing_capabilities": [
        {"method": "spray paint", "in_house": true, "notes": ""},
        {"method": "powder coat", "in_house": false, "notes": "sends out"}
    ]
}

Rules:
- Only include capabilities the user actually mentioned — do NOT invent
- If user says "no" to something or doesn't mention it, leave it out
- "primary": true for the process they use most or mention first
- For cutting: set "cnc": true ONLY if they explicitly mention CNC or automated table
- For finishing: "in_house": false means they outsource it
- Keep "notes" brief — only add if user gave specific details (tonnage, brand, etc.)
- shop_summary: FACTUAL ONLY — only reference equipment and processes the user actually described. Do not assume or embellish.
""" % (welding_answer, forming_answer, finishing_answer)

    try:
        from ..claude_client import call_fast
        raw = call_fast(prompt, timeout=30)
        if not raw:
            return _fallback_interpret(welding_answer, forming_answer, finishing_answer)

        # Extract JSON from response
        text = raw.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)

        # Validate structure
        for key in ["welding_processes", "cutting_capabilities",
                     "forming_equipment", "finishing_capabilities"]:
            if key not in result or not isinstance(result[key], list):
                result[key] = []

        # Extract shop summary if present
        if "shop_summary" in result and isinstance(result["shop_summary"], str):
            result["shop_summary"] = result["shop_summary"]
        else:
            result["shop_summary"] = ""

        return result

    except Exception as e:
        logger.warning("Opus interpretation failed: %s — using fallback", e)
        return _fallback_interpret(welding_answer, forming_answer, finishing_answer)


def _fallback_interpret(welding_answer: str, forming_answer: str, finishing_answer: str) -> dict:
    """
    Simple keyword-based fallback when Opus is unavailable.
    Extracts basic capabilities from free text.
    """
    w = welding_answer.lower()
    f = forming_answer.lower()
    fin = finishing_answer.lower()

    welding = []
    cutting = []
    forming = []
    finishing = []

    # Welding processes
    if "mig" in w or "gmaw" in w:
        wire = "flux core" if ("flux" in w or "fcaw" in w) else "solid wire"
        welding.append({"process": "MIG", "primary": True, "wire_type": wire, "notes": ""})
    if "tig" in w or "gtaw" in w:
        is_primary = len(welding) == 0
        welding.append({"process": "TIG", "primary": is_primary, "wire_type": "", "notes": ""})
    if "stick" in w or "smaw" in w:
        is_primary = len(welding) == 0
        welding.append({"process": "Stick", "primary": is_primary, "wire_type": "", "notes": ""})

    # Cutting
    if "cnc plasma" in w or "plasma table" in w:
        cutting.append({"tool": "CNC plasma table", "cnc": True, "notes": ""})
    elif "plasma" in w:
        cutting.append({"tool": "hand plasma", "cnc": False, "notes": ""})
    if "cold saw" in w:
        cutting.append({"tool": "cold saw", "cnc": False, "notes": ""})
    if "chop saw" in w:
        cutting.append({"tool": "chop saw", "cnc": False, "notes": ""})
    if "band saw" in w:
        cutting.append({"tool": "band saw", "cnc": False, "notes": ""})
    if "torch" in w or "oxy" in w:
        cutting.append({"tool": "oxy-acetylene torch", "cnc": False, "notes": ""})
    if "angle grinder" in w or "grinder" in w:
        cutting.append({"tool": "angle grinder", "cnc": False, "notes": ""})

    # Forming
    if "press brake" in f or "brake" in f:
        forming.append({"tool": "press brake", "specs": "", "notes": ""})
    if "tube bender" in f or "bender" in f:
        forming.append({"tool": "tube bender", "specs": "", "notes": ""})
    if "fixture" in f or "welding table" in f:
        forming.append({"tool": "fixture table", "specs": "", "notes": ""})
    if "roller" in f or "slip roll" in f:
        forming.append({"tool": "slip roller", "specs": "", "notes": ""})

    # Finishing
    if "spray" in fin or "paint" in fin:
        finishing.append({"method": "spray paint", "in_house": True, "notes": ""})
    if "powder" in fin:
        in_house = "oven" in fin or "in-house" in fin or "in house" in fin
        finishing.append({"method": "powder coat", "in_house": in_house,
                          "notes": "" if in_house else "sends out"})
    if "blast" in fin or "media" in fin or "sandblast" in fin:
        finishing.append({"method": "media blast", "in_house": True, "notes": ""})
    if "send" in fin or "outsource" in fin:
        if not any(f.get("method") == "powder coat" for f in finishing):
            finishing.append({"method": "coating", "in_house": False, "notes": "outsourced"})

    # Build a basic summary from detected capabilities
    parts = []
    if welding:
        procs = [p["process"] for p in welding]
        parts.append("Runs %s" % " and ".join(procs))
    if cutting:
        tools = [c["tool"] for c in cutting]
        parts.append("cuts with %s" % ", ".join(tools))
    if forming:
        tools = [f["tool"] for f in forming]
        parts.append("has %s for forming" % ", ".join(tools))
    if finishing:
        in_house = [f["method"] for f in finishing if f.get("in_house")]
        outsourced = [f["method"] for f in finishing if not f.get("in_house")]
        if in_house:
            parts.append("handles %s in-house" % ", ".join(in_house))
        if outsourced:
            parts.append("sends out %s" % ", ".join(outsourced))
    summary = ". ".join(parts) + "." if parts else ""

    return {
        "shop_summary": summary,
        "welding_processes": welding,
        "cutting_capabilities": cutting,
        "forming_equipment": forming,
        "finishing_capabilities": finishing,
    }


# --- Endpoints ---

@router.post("/onboarding")
def submit_onboarding(
    request: OnboardingRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Accept three free-text onboarding answers, interpret with Opus,
    store structured equipment profile.
    """
    # Interpret answers
    profile = _interpret_with_opus(
        request.welding_answer,
        request.forming_answer,
        request.finishing_answer,
    )

    # Upsert ShopEquipment
    equipment = db.query(models.ShopEquipment).filter(
        models.ShopEquipment.user_id == current_user.id
    ).first()

    shop_summary = profile.get("shop_summary", "")

    if equipment:
        equipment.welding_processes = profile.get("welding_processes", [])
        equipment.cutting_capabilities = profile.get("cutting_capabilities", [])
        equipment.forming_equipment = profile.get("forming_equipment", [])
        equipment.finishing_capabilities = profile.get("finishing_capabilities", [])
        equipment.raw_welding_answer = request.welding_answer
        equipment.raw_forming_answer = request.forming_answer
        equipment.raw_finishing_answer = request.finishing_answer
        equipment.shop_notes = shop_summary
        equipment.updated_at = datetime.utcnow()
    else:
        equipment = models.ShopEquipment(
            user_id=current_user.id,
            welding_processes=profile.get("welding_processes", []),
            cutting_capabilities=profile.get("cutting_capabilities", []),
            forming_equipment=profile.get("forming_equipment", []),
            finishing_capabilities=profile.get("finishing_capabilities", []),
            raw_welding_answer=request.welding_answer,
            raw_forming_answer=request.forming_answer,
            raw_finishing_answer=request.finishing_answer,
            shop_notes=shop_summary,
        )
        db.add(equipment)

    # Mark onboarding complete
    current_user.onboarding_complete = True
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(equipment)

    return {
        "message": "Shop profile saved",
        "equipment": _equipment_to_response(equipment, current_user),
    }


@router.get("/equipment")
def get_equipment(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current shop equipment profile."""
    equipment = db.query(models.ShopEquipment).filter(
        models.ShopEquipment.user_id == current_user.id
    ).first()

    if not equipment:
        return EquipmentResponse(
            onboarding_complete=getattr(current_user, "onboarding_complete", False) or False,
        ).model_dump()

    return _equipment_to_response(equipment, current_user)


@router.put("/equipment")
def update_equipment(
    update: EquipmentUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update structured equipment profile directly (from settings page)."""
    equipment = db.query(models.ShopEquipment).filter(
        models.ShopEquipment.user_id == current_user.id
    ).first()

    if not equipment:
        equipment = models.ShopEquipment(user_id=current_user.id)
        db.add(equipment)

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(equipment, field, value)

    equipment.updated_at = datetime.utcnow()
    current_user.onboarding_complete = True
    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(equipment)

    return _equipment_to_response(equipment, current_user)


@router.post("/equipment/regenerate-summary")
def regenerate_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-run AI interpretation on existing raw answers to generate a shop summary."""
    equipment = db.query(models.ShopEquipment).filter(
        models.ShopEquipment.user_id == current_user.id
    ).first()

    if not equipment:
        raise HTTPException(status_code=404, detail="No equipment profile found")

    raw_w = equipment.raw_welding_answer or ""
    raw_f = equipment.raw_forming_answer or ""
    raw_fin = equipment.raw_finishing_answer or ""

    if not (raw_w or raw_f or raw_fin):
        raise HTTPException(status_code=400, detail="No original answers to regenerate from")

    profile = _interpret_with_opus(raw_w, raw_f, raw_fin)

    # Update structured data + summary
    equipment.welding_processes = profile.get("welding_processes", [])
    equipment.cutting_capabilities = profile.get("cutting_capabilities", [])
    equipment.forming_equipment = profile.get("forming_equipment", [])
    equipment.finishing_capabilities = profile.get("finishing_capabilities", [])
    equipment.shop_notes = profile.get("shop_summary", "")
    equipment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(equipment)

    return _equipment_to_response(equipment, current_user)


def _equipment_to_response(equipment: models.ShopEquipment, user: models.User) -> dict:
    """Convert ShopEquipment model to response dict."""
    return {
        "welding_processes": equipment.welding_processes or [],
        "cutting_capabilities": equipment.cutting_capabilities or [],
        "forming_equipment": equipment.forming_equipment or [],
        "finishing_capabilities": equipment.finishing_capabilities or [],
        "raw_welding_answer": equipment.raw_welding_answer,
        "raw_forming_answer": equipment.raw_forming_answer,
        "raw_finishing_answer": equipment.raw_finishing_answer,
        "shop_notes": equipment.shop_notes,
        "onboarding_complete": getattr(user, "onboarding_complete", False) or False,
    }
