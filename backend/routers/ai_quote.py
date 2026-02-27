"""
AI-powered quoting endpoint — powered by Gemini.

User describes a job in plain English.
Gemini interprets it, returns structured line items.
The app calculates all the math using real Osario/Wexler pricing.
"""

import json
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from .. import models
from ..database import get_db

router = APIRouter(prefix="/ai", tags=["ai-quoting"])

# Master Context — the brain of the estimating engine
# Built from real CreateStage project data, Osario/Wexler quotes, Leopardo/Saki/Globe builds
MASTER_CONTEXT = """
You are CreateStage Fabrication's metal estimating AI (Chicago, IL). Parse job descriptions into structured JSON estimates. Be conservative on labor; never underestimate stainless or complex architectural work.

## RATES ($/hr)
Layout/marking: 75 | Saw cutting: 85 | CNC plasma: 125 | MIG weld: 125 | TIG weld: 150 | Grinding/finishing: 75 | Drilling/punching: 85 | Bending/press brake: 95 | Assembly/fit-up: 100 | CNC router: 125 | Design/CAD: 150 | Field install: 185 | Project mgmt: 125

## MATERIALS ($/lb, Chicago, Osario+Wexler 2023-2025)
Mild steel A36: 0.67 | SS304: 3.28 | SS316: 4.20 | Al 6061: 1.85 | Al 5052: 1.70 | DOM tubing: 2.60 | HSS sq tube 11ga: 0.82 | Angle A36: 0.75 | Flat bar A36: 0.96 | Plate A36 3/8": 0.56 | Channel A36: 0.80
Cut charges: $1.50/cut (simple), $8.00/cut (complex)

## RULES
- Waste: 5% (10% stainless); markup: 15%
- Stainless fab: 1.3–1.5× mild steel hours; food-grade interior finishing: +15–20% labor
- Round labor UP; never quote materials at cost
- Powder coat outsourced: $2.50–5.00/sqft
- Interior weld grinding on vessels: always add buffer (chronically underestimated)
- Assembly/fit-up always longer than welding alone
- Field install: $185/hr, no discount; design: $150/hr
- Commercial/GC: +10–15% contingency

## MITER VS SQUARE CUTS — JOINT SELECTION RULES
- Decorative/furniture/architectural frames (tables, railings, gates, ornamental): use 45° MITER cuts at corners
  - Miter math: each mitered piece = nominal dimension MINUS one full tube width (e.g. 20" frame with 1" tube = 19" cut length per side for square miter)
  - Mark cut list as "45° miter both ends" or "45° miter one end, square other"
  - Cut charge: complex ($8/cut) for miters vs simple ($1.50/cut) for square
- Structural/hidden connections (columns, brackets, gussets, hidden frames): square cuts
  - Square cuts are stronger for full-pen welds and easier to fit tight
- Triangulated supports and gussets: always 45° or compound angle — calculate from geometry
- When in doubt on furniture/decorative: default to 45° miter

## CLEAR COAT FINISH (in-house, polished steel look)
For jobs requiring a polished near-stainless appearance with clear coat (no powder coat):
- Step 1 — Polish: grind and polish all surfaces to 320-400 grit before finishing. Labor: 2-4h depending on piece complexity and surface area.
- Step 2 — Clear coat application: spray top surfaces, let cure (1-2h), flip piece on lazy susan / padded surface, coat bottom and legs. Labor: 1-2h active time.
- Materials: clear coat, tack rags, masking = ~$25-40
- Total clear coat process adds: 3-5h labor + $30 materials (no outsource cost unlike powder coat)
- Use process_type: "grinding" for polish step, "paint" for clear coat step
- Do NOT include outsourced powder coat line item when job specifies clear coat

## MILD STEEL SURFACE PREP — VINEGAR BATH / MILL SCALE REMOVAL
For any mild steel job with aesthetic, architectural, or finish-quality requirements, include a vinegar bath line item:
- Process: after cutting, all parts soak in white vinegar bath overnight to dissolve mill scale; next day parts are washed and dried
- Active labor time: 0.5–1h setup (fill tub, load parts) + 0.5h wash/dry
- Use process_type: "grinding" (surface prep), labor_hours: 1.0–1.5, material_cost: $5–15 (vinegar consumable)
- Required for: architectural railings, furniture, decorative/ornamental work, any job going to powder coat or clear coat
- Not required for: structural/hidden steel, galvanized, stainless, aluminum

## NESTED PATTERN MATH (pyramid / stepped flat bar patterns)
For layered flat bar patterns inside a square/rectangular frame:
- Inside clear dimension = outer frame dimension - (2 × tube wall size)
  Example: 20" outer frame, 1" tube → inside clear = 18"
- Layer 1 length = inside clear - (2 × step_inward)
  Example: 18" - 2(0.25") = 17.5"
- Each successive layer = previous layer length - (2 × step_inward)
  Example: Layer 2 = 17.0", Layer 3 = 16.5", etc.
- Each layer has 2 bars running each direction = 4 bars per layer total
- Generate EXACT cut lengths for every layer in the cut list — do not approximate

## SCALE CALIBRATION — labor hours by physical size (CRITICAL)
Physical size drives labor. Before estimating hours, classify the job by size:

SMALL (fits on a workbench, under 36" in any dimension):
- Simple bracket/mount: 0.5–2 hrs total
- Small decorative shelf/bracket: 2–4 hrs total
- Custom furniture piece (end table, stool, small bench): 6–14 hrs total
- Small gate under 3ft: 4–8 hrs total
- Intricate small decorative work (pyramid patterns, ornamental): add 2–6 hrs

MEDIUM (3–8 ft in longest dimension):
- Standard table/desk: 10–20 hrs
- Gate 4–6ft: 8–16 hrs
- Railing section 10 LF: 8–12 hrs shop + 2–3 hrs field
- Architectural panel/sign under 6ft: 12–24 hrs

LARGE (8–16 ft):
- Cable railing 14 LF + gate: ~46 hrs
- Large gate or door: 20–40 hrs
- Structural frame: 30–60 hrs

EXTRA LARGE / COMMERCIAL (16ft+):
- 10ft steel globe: 32–40 hrs
- LED architectural sign 133×72": 54+ hrs
- SS press vessel 48×30×28": 119 hrs

RULE: A 20" end table with decorative detail is SMALL. Total labor should be 8–16 hrs max, not 30+. Scale your estimates to the actual physical footprint. A piece you can carry with one hand cannot take 40 hours.

## BENCHMARKS
- 10ft steel globe: 32–40 hrs, $1,200–2,200 materials
- 50-ton SS press vessel 48×30×28": 119 hrs, $5,600 materials
- LED architectural sign 133×72": 54+ hrs, $600–1,000 powder coat
- Cable railing 14 LF + gate: ~46 hrs, $450 powder coat
- Handrail 10 LF: 8–12 hrs shop + 2–3 hrs field
- Gate 4ft: 6–10 hrs
- Custom steel end table 20"×20"×32": 8–14 hrs total labor, $50–80 materials

## PAYMENT
50% labor deposit + 100% materials upfront; balance on completion

## OUTPUT RULES
- material_cost = RAW cost (weight × $/lb or unit price), BEFORE waste or markup. Backend applies waste_factor and material_markup_pct automatically.
- waste_factor = decimal (0.05 for 5%, 0.10 for stainless) — NOT a percentage integer
- labor_hours = total hours for this line item (not per-unit when quantity > 1)
Return ONLY valid JSON, no explanation or markdown:

{"job_summary":"","job_type":"structural|architectural|signage|led_integration|sculpture|custom","confidence":"high|medium|low","assumptions":[],"warnings":[],"labor_rate_fallback":125,"waste_factor":0.05,"material_markup_pct":15,"stainless_multiplier":1.0,"contingency_pct":0,"profit_margin_pct":20,"line_items":[{"description":"","material_type":"mild_steel|stainless_304|stainless_316|aluminum_6061|aluminum_5052|dom_tubing|square_tubing|angle_iron|flat_bar|plate|channel|null","process_type":"layout|cutting|cnc_plasma|cnc_router|welding|tig_welding|grinding|drilling|bending|assembly|design|field_install|project_management|powder_coat|paint|null","quantity":1,"unit":"ea|lf|sqft|hr|lot","dim_length":null,"dim_width":null,"dim_thickness":null,"weight_lbs":null,"material_cost":0.0,"labor_hours":0.0,"outsourced":false,"outsource_service":null,"outsource_rate_per_sqft":null,"sq_ft":null,"notes":""}],"cut_list":[{"piece_description":"","material":"","quantity":1,"length":null,"width":null,"thickness":null,"notes":""}],"build_order":["Step 1: ...","Step 2: ..."]}
"""

# Simple in-memory prompt cache — keyed on first 100 chars of prompt, max 50 entries
_prompt_cache: dict = {}
_CACHE_MAX = 50


def _normalize_estimate(estimate: dict) -> None:
    """Fix common Gemini formatting issues in-place.

    waste_factor: Gemini sometimes returns 5 (meaning 5%) instead of 0.05.
    Every other pct field (material_markup_pct, profit_margin_pct, contingency_pct)
    is an integer like 15/20/0 and is divided by 100 in the calculation code.
    waste_factor is the only field used as a decimal — normalize it here.
    """
    waste = estimate.get("waste_factor")
    if isinstance(waste, (int, float)) and waste > 1:
        estimate["waste_factor"] = waste / 100


class AIQuoteRequest(BaseModel):
    job_description: str
    customer_id: Optional[int] = None
    additional_context: Optional[str] = None
    pre_computed_estimate: Optional[dict] = None  # Skip Gemini if provided


class AIQuoteResponse(BaseModel):
    job_summary: str
    job_type: str
    confidence: str
    assumptions: list
    warnings: list
    estimated_total: float
    estimated_cost: float
    line_items_count: int
    raw_estimate: dict
    quote_id: Optional[int] = None


def call_gemini(prompt: str) -> dict:
    """Call Gemini API and return parsed JSON estimate."""
    import urllib.request
    import urllib.error

    cache_key = prompt[:100]
    if cache_key in _prompt_cache:
        return _prompt_cache[cache_key]

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = json.dumps({
        "contents": [{
            "parts": [{
                "text": MASTER_CONTEXT + "\n\n## JOB DESCRIPTION\n" + prompt
            }]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            _normalize_estimate(parsed)
            if len(_prompt_cache) >= _CACHE_MAX:
                _prompt_cache.pop(next(iter(_prompt_cache)))
            _prompt_cache[cache_key] = parsed
            return parsed
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise HTTPException(status_code=502, detail=f"Gemini API error: {error_body}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini call failed: {str(e)}")


def estimate_total(estimate: dict) -> tuple[float, float]:
    """Quick estimate of cost and total from AI output."""
    labor_rate = estimate.get("labor_rate_fallback", 125)
    waste = estimate.get("waste_factor", 0.05)
    mat_markup = estimate.get("material_markup_pct", 15) / 100
    ss_mult = estimate.get("stainless_multiplier", 1.0)
    contingency = estimate.get("contingency_pct", 0) / 100
    profit = estimate.get("profit_margin_pct", 20) / 100

    subtotal = 0.0
    for item in estimate.get("line_items", []):
        if item.get("outsourced"):
            line = (item.get("outsource_rate_per_sqft") or 2.50) * (item.get("sq_ft") or 0) * item.get("quantity", 1)
        else:
            mat = item.get("material_cost", 0) * (1 + waste) * (1 + mat_markup)
            labor = item.get("labor_hours", 0) * ss_mult * labor_rate
            line = (mat + labor) * item.get("quantity", 1)
        subtotal += line

    cost = subtotal * (1 + contingency)
    total = cost * (1 + profit)
    return round(cost, 2), round(total, 2)


@router.post("/estimate")
def ai_estimate(request: AIQuoteRequest):
    """
    Describe a job in plain English — get back a structured estimate.
    Does NOT save to database. Use /ai/quote to create a saved quote.
    """
    prompt = request.job_description
    if request.additional_context:
        prompt += f"\n\nAdditional context: {request.additional_context}"

    estimate = call_gemini(prompt)
    cost, total = estimate_total(estimate)

    return {
        "job_summary": estimate.get("job_summary", ""),
        "job_type": estimate.get("job_type", "custom"),
        "confidence": estimate.get("confidence", "medium"),
        "assumptions": estimate.get("assumptions", []),
        "warnings": estimate.get("warnings", []),
        "estimated_cost": cost,
        "estimated_total": total,
        "line_items_count": len(estimate.get("line_items", [])),
        "raw_estimate": estimate,
    }


@router.post("/quote")
def ai_create_quote(request: AIQuoteRequest, db: Session = Depends(get_db)):
    """
    Describe a job in plain English — AI estimates it and saves a draft quote.
    Requires customer_id. Returns a saved quote ready to review and adjust.
    """
    if not request.customer_id:
        raise HTTPException(status_code=400, detail="customer_id required to save a quote")

    customer = db.query(models.Customer).filter(models.Customer.id == request.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if request.pre_computed_estimate:
        # Use the estimate already shown to the user — no second Gemini call
        estimate = request.pre_computed_estimate
        _normalize_estimate(estimate)
    else:
        prompt = request.job_description
        if request.additional_context:
            prompt += f"\n\nAdditional context: {request.additional_context}"
        estimate = call_gemini(prompt)

    # Import here to avoid circular
    from .quotes import generate_quote_number, calculate_totals, _quote_to_dict

    # Build the Quote
    db_quote = models.Quote(
        quote_number=generate_quote_number(db),
        customer_id=request.customer_id,
        job_type=estimate.get("job_type", "custom"),
        project_description=estimate.get("job_summary", request.job_description),
        notes=f"AI-generated estimate. Assumptions: {'; '.join(estimate.get('assumptions', []))}. Warnings: {'; '.join(estimate.get('warnings', []))}",
        labor_rate=estimate.get("labor_rate_fallback", 125.0),
        waste_factor=estimate.get("waste_factor", 0.05),
        material_markup_pct=estimate.get("material_markup_pct", 15.0),
        stainless_multiplier=estimate.get("stainless_multiplier", 1.0),
        contingency_pct=estimate.get("contingency_pct", 0.0),
        profit_margin_pct=estimate.get("profit_margin_pct", 20.0),
    )
    db.add(db_quote)
    db.flush()

    # Add line items
    for item_data in estimate.get("line_items", []):
        db_item = models.QuoteLineItem(
            quote_id=db_quote.id,
            description=item_data.get("description", ""),
            material_type=item_data.get("material_type") or None,
            process_type=item_data.get("process_type") or None,
            quantity=item_data.get("quantity", 1),
            unit=item_data.get("unit", "ea"),
            dim_length=item_data.get("dim_length"),
            dim_width=item_data.get("dim_width"),
            dim_thickness=item_data.get("dim_thickness"),
            weight_lbs=item_data.get("weight_lbs"),
            material_cost=item_data.get("material_cost", 0),
            labor_hours=item_data.get("labor_hours", 0),
            outsourced=item_data.get("outsourced", False),
            outsource_service=item_data.get("outsource_service"),
            outsource_rate_per_sqft=item_data.get("outsource_rate_per_sqft"),
            sq_ft=item_data.get("sq_ft"),
            notes=item_data.get("notes"),
        )
        db.add(db_item)

    db.flush()
    db.refresh(db_quote)
    calculate_totals(db_quote, db)
    db.refresh(db_quote)

    return {
        "message": "AI quote created — review and adjust before sending",
        "confidence": estimate.get("confidence", "medium"),
        "assumptions": estimate.get("assumptions", []),
        "warnings": estimate.get("warnings", []),
        "quote": _quote_to_dict(db_quote),
    }


@router.get("/test")
def test_gemini():
    """Quick test to verify Gemini API key is working."""
    result = call_gemini("quote a simple steel frame")
    return {"status": "ok", "model": os.getenv("GEMINI_MODEL"), "result": result}
