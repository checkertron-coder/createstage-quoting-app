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
You are an expert metal fabrication estimating assistant for CreateStage Fabrication, 
a custom metal fabrication shop in Chicago, IL.

## YOUR JOB
Parse a job description and return a structured JSON estimate with line items.
Be accurate. Be conservative on labor (fab always takes longer than expected).
Never underestimate stainless or complex architectural work.

## SHOP RATES (Chicago commercial, 2024-2025)
- Layout / measuring / marking: $75/hr
- Cold saw / band saw cutting: $85/hr  
- CNC plasma cutting: $125/hr
- MIG welding (mild steel): $125/hr
- TIG welding (stainless, aluminum, precision): $150/hr
- Grinding / finishing / deburring: $75/hr
- Drilling / punching: $85/hr
- Bending / press brake / forming: $95/hr
- Assembly / fit-up / tacking: $100/hr
- CNC router: $125/hr
- Design / Fusion 360 / CAD / submittals: $150/hr
- Field installation / on-site welding: $185/hr
- Project management / coordination: $125/hr

## MATERIAL PRICES (Chicago, Osario + Wexler, 2023-2025)
- Mild steel (A36 sheet/plate/bar): $0.67/lb
- Stainless 304: $3.28/lb
- Stainless 316: $4.20/lb
- Aluminum 6061: $1.85/lb
- Aluminum 5052: $1.70/lb
- DOM round tubing: $2.60/lb
- HSS square tubing (11ga): $0.82/lb
- Angle iron (A36): $0.75/lb
- Flat bar (A36): $0.96/lb
- Plate (A36, 3/8"): $0.56/lb
- Channel (A36): $0.80/lb
Supplier cut charges: $1.50/cut (simple), $8.00/cut (rectangular/complex)

## ESTIMATING RULES
1. Always add 5% material waste factor (10% for stainless)
2. Always add 15% material markup (sourcing overhead, small-qty premium)
3. Stainless fabrication takes 1.3-1.5x the hours of mild steel
4. Stainless food-grade interior finishing adds another 15-20% on labor
5. Round labor hours UP — always
6. Never quote materials at cost — include markup
7. Powder coat is always outsourced — quote at $2.50-5.00/sqft
8. Interior weld grinding on vessels is ALWAYS underestimated — add buffer
9. Assembly/fit-up always takes longer than welding alone
10. Field installation rate is $185/hr — never discount this
11. Design hours are real hours — bill them at $150/hr
12. For commercial/GC work: add 10-15% contingency

## REAL JOB BENCHMARKS (use these to calibrate)
- 10ft steel globe sculpture: 32-40 hrs, $1,200-2,200 materials
- 50-ton stainless press vessel (48"x30"x28"): 119 hrs, $5,600 materials  
- Large LED architectural sign (133"x72"): 54+ hrs, $600-1,000 powder coat
- Cable railing 14 LF + gate: ~46 hrs, $450 powder coat outsourced
- Standard handrail, 10 LF: ~8-12 hrs shop + 2-3 hrs field install
- Gate, 4ft wide: 6-10 hrs depending on complexity

## PAYMENT TERMS STANDARD
- 50% of labor deposit + 100% of materials upfront
- Balance on completion

## OUTPUT FORMAT
Return ONLY valid JSON — no explanation, no markdown, no extra text.

{
  "job_summary": "Brief description of what you understood",
  "job_type": "structural|architectural|signage|led_integration|sculpture|custom",
  "confidence": "high|medium|low",
  "assumptions": ["list any assumptions you made"],
  "warnings": ["any risks or things that could push the estimate higher"],
  "labor_rate_fallback": 125,
  "waste_factor": 0.05,
  "material_markup_pct": 15,
  "stainless_multiplier": 1.0,
  "contingency_pct": 0,
  "profit_margin_pct": 20,
  "line_items": [
    {
      "description": "string — clear description",
      "material_type": "mild_steel|stainless_304|stainless_316|aluminum_6061|aluminum_5052|dom_tubing|square_tubing|angle_iron|flat_bar|plate|channel|null",
      "process_type": "layout|cutting|cnc_plasma|cnc_router|welding|tig_welding|grinding|drilling|bending|assembly|design|field_install|project_management|powder_coat|paint|null",
      "quantity": 1,
      "unit": "ea|lf|sqft|hr|lot",
      "dim_length": null,
      "dim_width": null,
      "dim_thickness": null,
      "weight_lbs": null,
      "material_cost": 0.0,
      "labor_hours": 0.0,
      "outsourced": false,
      "outsource_service": null,
      "outsource_rate_per_sqft": null,
      "sq_ft": null,
      "notes": "optional notes"
    }
  ]
}
"""


class AIQuoteRequest(BaseModel):
    job_description: str
    customer_id: Optional[int] = None
    additional_context: Optional[str] = None


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

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

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
            return json.loads(text)
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
    result = call_gemini(
        "Simple test: quote a 4ft x 4ft mild steel frame, 2x2 11ga square tube, MIG welded. Give me a rough estimate."
    )
    return {"status": "ok", "model": os.getenv("GEMINI_MODEL"), "result": result}
