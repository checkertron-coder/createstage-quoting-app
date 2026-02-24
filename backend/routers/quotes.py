from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from .. import models
from ..database import get_db

router = APIRouter(prefix="/quotes", tags=["quotes"])


def generate_quote_number(db: Session) -> str:
    count = db.query(models.Quote).count()
    year = datetime.utcnow().year
    return f"CS-{year}-{str(count + 1).zfill(4)}"


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

            item.labor_cost = round(item.labor_hours * rate, 2)

            # Material with waste factor
            item_waste = item.waste_factor if item.waste_factor is not None else quote_waste
            effective_material = item.material_cost * (1 + item_waste)

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
    contingency_pct: float = 0.0
    profit_margin_pct: float = 20.0
    valid_days: int = 30
    region: str = "chicago"
    line_items: List[LineItemCreate] = []


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


@router.get("/{quote_id}")
def get_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return _quote_to_dict(quote)


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
