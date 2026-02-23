from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/quotes", tags=["quotes"])

def generate_quote_number(db: Session) -> str:
    count = db.query(models.Quote).count()
    year = datetime.utcnow().year
    return f"CS-{year}-{str(count + 1).zfill(4)}"

def calculate_totals(quote: models.Quote, db: Session):
    subtotal = 0.0
    for item in quote.line_items:
        item.labor_cost = item.labor_hours * quote.labor_rate
        item.line_total = (item.material_cost + item.labor_cost) * item.quantity
        subtotal += item.line_total
    quote.subtotal = subtotal
    quote.total = round(subtotal * quote.markup, 2)
    db.commit()

@router.post("/", response_model=schemas.Quote)
def create_quote(quote: schemas.QuoteCreate, db: Session = Depends(get_db)):
    customer = db.query(models.Customer).filter(models.Customer.id == quote.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    db_quote = models.Quote(
        quote_number=generate_quote_number(db),
        customer_id=quote.customer_id,
        project_description=quote.project_description,
        notes=quote.notes,
        labor_rate=quote.labor_rate,
        markup=quote.markup,
        valid_days=quote.valid_days,
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
    return db_quote

@router.get("/", response_model=List[schemas.Quote])
def list_quotes(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(models.Quote).order_by(models.Quote.created_at.desc()).offset(skip).limit(limit).all()

@router.get("/{quote_id}", response_model=schemas.Quote)
def get_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote

@router.patch("/{quote_id}", response_model=schemas.Quote)
def update_quote(quote_id: int, update: schemas.QuoteUpdate, db: Session = Depends(get_db)):
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(quote, field, value)
    db.commit()
    db.refresh(quote)
    return quote

@router.delete("/{quote_id}")
def delete_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    db.delete(quote)
    db.commit()
    return {"ok": True}
