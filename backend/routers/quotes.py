from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from .. import models
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/quotes", tags=["quotes"])


def generate_quote_number(db: Session) -> str:
    try:
        count = db.query(models.Quote).count()
        year = datetime.utcnow().year
        return f"CS-{year}-{str(count + 1).zfill(4)}"
    except Exception:
        db.rollback()
        # Fallback: timestamp-based quote number if DB schema is outdated
        now = datetime.utcnow()
        return f"CS-{now.year}-{now.strftime('%m%d%H%M%S')}"


def get_process_rate(process_type, db: Session, fallback_rate: float = 125.0) -> float:
    """Get hourly rate for a process type from the rate table."""
    if not process_type:
        return fallback_rate
    rate = db.query(models.ProcessRate).filter(
        models.ProcessRate.process_type == process_type
    ).first()
    return rate.rate_per_hour if rate else fallback_rate


def calculate_totals(quote: models.Quote, db: Session):
    """
    Recalculate all line item costs and quote totals.

    Formula per line item:
    - If outsourced: line_total = sq_ft * outsource_rate_per_sqft * quantity
    - If labor: rate = override > process_rate_table > quote.labor_rate (fallback)
               labor_cost = labor_hours * rate
               material_with_waste = material_cost * (1 + waste_factor)
               line_total = (material_with_waste + labor_cost) * quantity

    Quote totals:
    - subtotal = sum of all line totals
    - subtotal_with_contingency = subtotal * (1 + contingency_pct/100)
    - total = subtotal_with_contingency * (1 + profit_margin_pct/100)
    """
    subtotal = 0.0
    quote_waste = quote.waste_factor if quote.waste_factor is not None else 0.05

    for item in quote.line_items:
        if item.outsourced:
            # Outsourced service — priced by sq ft (powder coat, laser cut, sandblast)
            rate_per_sqft = item.outsource_rate_per_sqft or 2.50  # default $2.50/sqft
            sq_ft = item.sq_ft or 0.0
            item.labor_cost = 0.0
            item.line_total = round(rate_per_sqft * sq_ft * item.quantity, 2)
        else:
            # Determine labor rate
            if item.process_rate_override:
                rate = item.process_rate_override
            else:
                rate = get_process_rate(item.process_type, db, fallback_rate=quote.labor_rate or 125.0)

            # Apply stainless multiplier to labor hours
            stainless_mult = quote.stainless_multiplier or 1.0
            effective_hours = item.labor_hours * stainless_mult
            item.labor_cost = round(effective_hours * rate, 2)

            # Material with waste factor + material markup (sourcing overhead, delivery, small qty premium)
            item_waste = item.waste_factor if item.waste_factor is not None else quote_waste
            material_markup = (quote.material_markup_pct or 15.0) / 100.0
            effective_material = item.material_cost * (1 + item_waste) * (1 + material_markup)

            item.line_total = round((effective_material + item.labor_cost) * item.quantity, 2)

        subtotal += item.line_total

    # Contingency
    contingency_pct = quote.contingency_pct or 0.0
    subtotal_with_contingency = subtotal * (1 + contingency_pct / 100.0)

    # Profit margin (internal — not shown on client-facing PDF)
    profit_pct = quote.profit_margin_pct if quote.profit_margin_pct is not None else 20.0

    quote.subtotal = round(subtotal_with_contingency, 2)
    quote.total = round(subtotal_with_contingency * (1 + profit_pct / 100.0), 2)

    db.commit()


# --- Schemas ---
class LineItemCreate(BaseModel):
    description: str
    material_type: Optional[str] = None
    process_type: Optional[str] = None
    quantity: float = 1.0
    unit: str = "ea"
    dim_length: Optional[float] = None
    dim_width: Optional[float] = None
    dim_thickness: Optional[float] = None
    weight_lbs: Optional[float] = None
    waste_factor: Optional[float] = None
    material_cost: float = 0.0
    labor_hours: float = 0.0
    process_rate_override: Optional[float] = None
    outsourced: bool = False
    outsource_service: Optional[str] = None
    outsource_rate_per_sqft: Optional[float] = None
    sq_ft: Optional[float] = None
    notes: Optional[str] = None


class QuoteCreate(BaseModel):
    customer_id: int
    job_type: str = "custom"
    project_description: Optional[str] = None
    notes: Optional[str] = None
    labor_rate: float = 125.0
    waste_factor: float = 0.05
    material_markup_pct: float = 15.0       # 10-20% standard — sourcing overhead
    stainless_multiplier: float = 1.0       # 1.3-1.5x for stainless/food-grade jobs
    contingency_pct: float = 0.0
    profit_margin_pct: float = 20.0
    valid_days: int = 30
    region: str = "chicago"
    line_items: List[LineItemCreate] = []


class MarkupRequest(BaseModel):
    markup_pct: int


class SwapMaterialRequest(BaseModel):
    item_index: int
    new_profile: str


class QuoteUpdate(BaseModel):
    status: Optional[str] = None
    project_description: Optional[str] = None
    notes: Optional[str] = None
    labor_rate: Optional[float] = None
    contingency_pct: Optional[float] = None
    profit_margin_pct: Optional[float] = None
    job_type: Optional[str] = None


# --- Endpoints ---

@router.post("/")
def create_quote(quote: QuoteCreate, db: Session = Depends(get_db)):
    customer = db.query(models.Customer).filter(models.Customer.id == quote.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    db_quote = models.Quote(
        quote_number=generate_quote_number(db),
        customer_id=quote.customer_id,
        job_type=quote.job_type,
        project_description=quote.project_description,
        notes=quote.notes,
        labor_rate=quote.labor_rate,
        waste_factor=quote.waste_factor,
        material_markup_pct=quote.material_markup_pct,
        stainless_multiplier=quote.stainless_multiplier,
        contingency_pct=quote.contingency_pct,
        profit_margin_pct=quote.profit_margin_pct,
        valid_days=quote.valid_days,
        region=quote.region,
    )
    db.add(db_quote)
    db.flush()

    for item_data in quote.line_items:
        db_item = models.QuoteLineItem(quote_id=db_quote.id, **item_data.model_dump())
        db.add(db_item)
    db.flush()

    db.refresh(db_quote)
    calculate_totals(db_quote, db)
    db.refresh(db_quote)
    return _quote_to_dict(db_quote)


@router.get("/")
def list_quotes(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    quotes = db.query(models.Quote).order_by(models.Quote.created_at.desc()).offset(skip).limit(limit).all()
    return [_quote_to_dict(q) for q in quotes]


@router.get("/mine")
def list_my_quotes(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List quotes for the authenticated user, newest first."""
    from ..pdf_generator import generate_job_summary
    quotes = db.query(models.Quote).filter(
        models.Quote.user_id == current_user.id,
    ).order_by(models.Quote.created_at.desc()).offset(skip).limit(limit).all()

    results = []
    for q in quotes:
        outputs = q.outputs_json or {}
        inputs = q.inputs_json or {}
        fields = inputs.get("fields", {})
        summary = generate_job_summary(q.job_type or "", fields)
        results.append({
            "id": q.id,
            "quote_number": q.quote_number,
            "job_type": q.job_type,
            "status": q.status.value if q.status else "draft",
            "subtotal": q.subtotal,
            "total": q.total,
            "selected_markup_pct": q.selected_markup_pct,
            "summary": summary,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        })
    return results


@router.get("/{quote_id}")
def get_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return _quote_to_dict(quote)


@router.get("/{quote_id}/detail")
def get_quote_detail(
    quote_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return full PricedQuote from outputs_json for the authenticated user."""
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quote")
    return {
        "id": quote.id,
        "quote_number": quote.quote_number,
        "job_type": quote.job_type,
        "status": quote.status.value if quote.status else "draft",
        "subtotal": quote.subtotal,
        "total": quote.total,
        "selected_markup_pct": quote.selected_markup_pct,
        "inputs": quote.inputs_json,
        "outputs": quote.outputs_json,
        "created_at": quote.created_at.isoformat() if quote.created_at else None,
    }


@router.patch("/{quote_id}")
def update_quote(quote_id: int, update: QuoteUpdate, db: Session = Depends(get_db)):
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(quote, field, value)
    calculate_totals(quote, db)
    db.refresh(quote)
    return _quote_to_dict(quote)


@router.delete("/{quote_id}")
def delete_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    db.delete(quote)
    db.commit()
    return {"ok": True}


ALLOWED_MARKUPS = [0, 5, 10, 15, 20, 25, 30]


@router.put("/{quote_id}/markup")
def update_markup(
    quote_id: int,
    request: MarkupRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Update the markup percentage on a v2 pipeline quote.

    Validates markup_pct is in [0, 5, 10, 15, 20, 25, 30].
    Recalculates total from subtotal × (1 + markup_pct/100).
    Updates the Quote record and outputs_json.
    """
    if request.markup_pct not in ALLOWED_MARKUPS:
        raise HTTPException(
            status_code=400,
            detail=f"markup_pct must be one of {ALLOWED_MARKUPS}, got {request.markup_pct}",
        )

    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quote")

    # Recalculate
    from ..pricing_engine import PricingEngine
    pricing_engine = PricingEngine()

    subtotal = quote.subtotal or 0.0
    new_total = round(subtotal * (1 + request.markup_pct / 100.0), 2)

    quote.selected_markup_pct = request.markup_pct
    quote.total = new_total
    quote.updated_at = datetime.utcnow()

    # Update outputs_json if present
    if quote.outputs_json:
        outputs = dict(quote.outputs_json)
        outputs["selected_markup_pct"] = request.markup_pct
        outputs["total"] = new_total
        quote.outputs_json = outputs
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(quote, "outputs_json")

    db.commit()
    db.refresh(quote)

    return {
        "quote_id": quote.id,
        "quote_number": quote.quote_number,
        "subtotal": quote.subtotal,
        "selected_markup_pct": request.markup_pct,
        "total": new_total,
        "markup_options": pricing_engine._build_markup_options(subtotal),
    }


@router.post("/{quote_id}/swap-material")
def swap_material(
    quote_id: int,
    request: SwapMaterialRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Swap a material item's profile and recalculate pricing.

    Replaces profile + recalculates unit_price, line_total,
    material_subtotal, subtotal, markup_options, total.
    """
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quote")
    if not quote.outputs_json:
        raise HTTPException(status_code=400, detail="Quote has no outputs")

    from ..calculators.material_lookup import MaterialLookup, PRICE_PER_FOOT
    lookup = MaterialLookup()

    outputs = dict(quote.outputs_json)
    materials = outputs.get("materials", [])

    if request.item_index < 0 or request.item_index >= len(materials):
        raise HTTPException(status_code=400, detail="Invalid item_index")

    # Verify the new profile exists
    new_price = lookup.get_price_per_foot(request.new_profile)
    if new_price == 0.0:
        raise HTTPException(
            status_code=400,
            detail="Unknown profile: %s" % request.new_profile,
        )

    item = materials[request.item_index]
    old_profile = item.get("profile", "")

    # Update the item
    item["profile"] = request.new_profile
    item["description"] = "%s -- %.1f ft" % (
        request.new_profile,
        (item.get("length_inches", 0) or 0) / 12.0,
    )

    # Recalculate line_total: for AI-consolidated items, unit_price IS line_total
    length_ft = (item.get("length_inches", 0) or 0) / 12.0
    quantity = item.get("quantity", 1)
    waste = item.get("waste_factor", 0.05)
    new_line_total = round(length_ft * (1 + waste) * new_price * quantity, 2)
    item["unit_price"] = round(new_line_total / max(quantity, 1), 2)
    item["line_total"] = new_line_total

    # Recalculate material_subtotal
    material_subtotal = round(sum(m.get("line_total", 0) for m in materials), 2)
    outputs["materials"] = materials
    outputs["material_subtotal"] = material_subtotal

    # Recalculate subtotal and total
    subtotal = round(
        material_subtotal
        + outputs.get("hardware_subtotal", 0)
        + outputs.get("consumable_subtotal", 0)
        + outputs.get("labor_subtotal", 0)
        + outputs.get("finishing_subtotal", 0),
        2,
    )
    outputs["subtotal"] = subtotal

    # Rebuild markup options
    from ..pricing_engine import PricingEngine
    pe = PricingEngine()
    outputs["markup_options"] = pe._build_markup_options(subtotal)

    markup_pct = outputs.get("selected_markup_pct", 0)
    outputs["total"] = outputs["markup_options"].get(str(markup_pct), subtotal)

    # Persist
    quote.outputs_json = outputs
    quote.subtotal = subtotal
    quote.total = outputs["total"]
    quote.updated_at = datetime.utcnow()
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(quote, "outputs_json")
    db.commit()
    db.refresh(quote)

    return outputs


@router.get("/{quote_id}/material-alternatives")
def get_material_alternatives(
    quote_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    For each material item with a profile, return alternative profiles
    in the same shape family with price deltas.
    """
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quote")
    if not quote.outputs_json:
        raise HTTPException(status_code=400, detail="Quote has no outputs")

    from ..calculators.material_lookup import MaterialLookup
    lookup = MaterialLookup()

    materials = quote.outputs_json.get("materials", [])
    results = []

    for idx, item in enumerate(materials):
        profile = item.get("profile", "")
        if not profile:
            continue
        current_price = lookup.get_price_per_foot(profile)
        alternatives = lookup.get_alternatives(profile)
        if not alternatives:
            continue
        results.append({
            "item_index": idx,
            "current_profile": profile,
            "current_price": current_price,
            "alternatives": [
                {
                    "profile": a["profile"],
                    "description": a["description"],
                    "price": a["price"],
                    "delta": round(a["price"] - current_price, 2),
                }
                for a in alternatives
            ],
        })

    return results


class AdjustLineItemsRequest(BaseModel):
    """Adjust labor hours, hardware quantities, or consumable quantities."""
    labor_adjustments: Optional[dict] = None      # {"process_name": new_hours, ...}
    hardware_adjustments: Optional[dict] = None    # {"item_index": new_qty, ...}
    consumable_adjustments: Optional[dict] = None  # {"item_index": new_qty, ...}


@router.patch("/{quote_id}/adjust")
def adjust_line_items(
    quote_id: int,
    request: AdjustLineItemsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Adjust labor hours, hardware quantities, or consumable quantities on a quote.

    Recalculates all affected subtotals, markup options, and total.
    Returns the updated outputs_json.
    """
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quote")
    if not quote.outputs_json:
        raise HTTPException(status_code=400, detail="Quote has no outputs")

    outputs = dict(quote.outputs_json)
    changed = False

    # --- Labor hour adjustments ---
    if request.labor_adjustments:
        labor = outputs.get("labor", [])
        for proc_name, new_hours in request.labor_adjustments.items():
            new_hours = max(0, float(new_hours))
            for proc in labor:
                if proc.get("process") == proc_name:
                    proc["hours"] = round(new_hours, 2)
                    changed = True
                    break
        if changed:
            outputs["labor"] = labor
            outputs["labor_subtotal"] = round(
                sum(p.get("hours", 0) * p.get("rate", 0) for p in labor), 2
            )

    # --- Hardware quantity adjustments ---
    if request.hardware_adjustments:
        hardware = outputs.get("hardware", [])
        for idx_str, new_qty in request.hardware_adjustments.items():
            idx = int(idx_str)
            new_qty = max(0, int(new_qty))
            if 0 <= idx < len(hardware):
                hardware[idx]["quantity"] = new_qty
                changed = True
        if changed:
            outputs["hardware"] = hardware
            # Recalculate hardware subtotal
            hw_total = 0.0
            for item in hardware:
                qty = item.get("quantity", 1)
                options = item.get("options", [])
                valid = [o for o in options if o.get("price") is not None]
                if valid:
                    cheapest = min(valid, key=lambda o: o["price"])
                    hw_total += cheapest["price"] * qty
            outputs["hardware_subtotal"] = round(hw_total, 2)

    # --- Consumable quantity adjustments ---
    if request.consumable_adjustments:
        consumables = outputs.get("consumables", [])
        for idx_str, new_qty in request.consumable_adjustments.items():
            idx = int(idx_str)
            new_qty = max(0, float(new_qty))
            if 0 <= idx < len(consumables):
                item = consumables[idx]
                unit_price = item.get("unit_price", 0)
                item["quantity"] = round(new_qty, 2)
                item["line_total"] = round(unit_price * new_qty, 2)
                changed = True
        if changed:
            outputs["consumables"] = consumables
            outputs["consumable_subtotal"] = round(
                sum(c.get("line_total", 0) for c in consumables), 2
            )

    if not changed:
        return outputs

    # Recalculate subtotal and total
    subtotal = round(
        outputs.get("material_subtotal", 0)
        + outputs.get("hardware_subtotal", 0)
        + outputs.get("consumable_subtotal", 0)
        + outputs.get("labor_subtotal", 0)
        + outputs.get("finishing_subtotal", 0),
        2,
    )
    outputs["subtotal"] = subtotal

    from ..pricing_engine import PricingEngine
    pe = PricingEngine()
    outputs["markup_options"] = pe._build_markup_options(subtotal)

    markup_pct = outputs.get("selected_markup_pct", 0)
    outputs["total"] = outputs["markup_options"].get(str(markup_pct), subtotal)

    # Persist
    quote.outputs_json = outputs
    quote.subtotal = subtotal
    quote.total = outputs["total"]
    quote.updated_at = datetime.utcnow()
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(quote, "outputs_json")
    db.commit()
    db.refresh(quote)

    return outputs


@router.get("/{quote_id}/breakdown")
def get_quote_breakdown(quote_id: int, db: Session = Depends(get_db)):
    """Returns full cost breakdown — for internal use (shows profit margin)."""
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    material_total = sum(
        (i.material_cost * (1 + (i.waste_factor or quote.waste_factor or 0.05))) * i.quantity
        for i in quote.line_items if not i.outsourced
    )
    labor_total = sum(i.labor_cost * i.quantity for i in quote.line_items if not i.outsourced)
    outsource_total = sum(i.line_total for i in quote.line_items if i.outsourced)
    subtotal_raw = material_total + labor_total + outsource_total
    contingency_amt = subtotal_raw * ((quote.contingency_pct or 0) / 100)
    subtotal_w_cont = subtotal_raw + contingency_amt
    profit_amt = subtotal_w_cont * ((quote.profit_margin_pct or 20) / 100)

    return {
        "quote_number": quote.quote_number,
        "material_cost": round(material_total, 2),
        "labor_cost": round(labor_total, 2),
        "outsourced_cost": round(outsource_total, 2),
        "subtotal_raw": round(subtotal_raw, 2),
        "contingency_pct": quote.contingency_pct,
        "contingency_amt": round(contingency_amt, 2),
        "subtotal_with_contingency": round(subtotal_w_cont, 2),
        "profit_margin_pct": quote.profit_margin_pct,
        "profit_amt": round(profit_amt, 2),
        "total": quote.total,
    }


def _quote_to_dict(q: models.Quote) -> dict:
    return {
        "id": q.id,
        "quote_number": q.quote_number,
        "status": q.status,
        "job_type": q.job_type,
        "project_description": q.project_description,
        "notes": q.notes,
        "labor_rate": q.labor_rate,
        "waste_factor": q.waste_factor,
        "material_markup_pct": q.material_markup_pct,
        "stainless_multiplier": q.stainless_multiplier,
        "contingency_pct": q.contingency_pct,
        "profit_margin_pct": q.profit_margin_pct,
        "subtotal": q.subtotal,
        "total": q.total,
        "valid_days": q.valid_days,
        "region": q.region,
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "updated_at": q.updated_at.isoformat() if q.updated_at else None,
        "customer": {
            "id": q.customer.id,
            "name": q.customer.name,
            "company": q.customer.company,
            "email": q.customer.email,
            "phone": q.customer.phone,
        } if q.customer else None,
        "customer_id": q.customer_id,
        "line_items": [_item_to_dict(i) for i in q.line_items],
    }


def _item_to_dict(i: models.QuoteLineItem) -> dict:
    return {
        "id": i.id,
        "description": i.description,
        "material_type": i.material_type,
        "process_type": i.process_type,
        "quantity": i.quantity,
        "unit": i.unit,
        "dim_length": i.dim_length,
        "dim_width": i.dim_width,
        "dim_thickness": i.dim_thickness,
        "weight_lbs": i.weight_lbs,
        "waste_factor": i.waste_factor,
        "material_cost": i.material_cost,
        "labor_hours": i.labor_hours,
        "process_rate_override": i.process_rate_override,
        "labor_cost": i.labor_cost,
        "outsourced": i.outsourced,
        "outsource_service": i.outsource_service,
        "outsource_rate_per_sqft": i.outsource_rate_per_sqft,
        "sq_ft": i.sq_ft,
        "line_total": i.line_total,
        "notes": i.notes,
    }
