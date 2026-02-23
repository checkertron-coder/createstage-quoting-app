from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/materials", tags=["materials"])

# Default material prices (per lb) — update via API as market prices change
DEFAULT_PRICES = {
    models.MaterialType.MILD_STEEL: {"price_per_lb": 0.65, "notes": "A36 hot rolled"},
    models.MaterialType.STAINLESS_304: {"price_per_lb": 2.20, "notes": "304 HR sheet"},
    models.MaterialType.STAINLESS_316: {"price_per_lb": 3.10, "notes": "316 HR sheet"},
    models.MaterialType.ALUMINUM_6061: {"price_per_lb": 1.85, "notes": "6061-T6"},
    models.MaterialType.ALUMINUM_5052: {"price_per_lb": 1.70, "notes": "5052-H32"},
    models.MaterialType.DOM_TUBING: {"price_per_lb": 1.10, "notes": "DOM mechanical tubing"},
    models.MaterialType.SQUARE_TUBING: {"price_per_lb": 0.70, "notes": "HSS square tubing"},
    models.MaterialType.ANGLE_IRON: {"price_per_lb": 0.60, "notes": "A36 angle"},
    models.MaterialType.FLAT_BAR: {"price_per_lb": 0.65, "notes": "A36 flat bar"},
    models.MaterialType.PLATE: {"price_per_lb": 0.75, "notes": "A36 plate"},
}

@router.get("/seed")
def seed_prices(db: Session = Depends(get_db)):
    """Seed default material prices."""
    for mat_type, price_data in DEFAULT_PRICES.items():
        existing = db.query(models.MaterialPrice).filter(models.MaterialPrice.material_type == mat_type).first()
        if not existing:
            db.add(models.MaterialPrice(material_type=mat_type, **price_data))
    db.commit()
    return {"ok": True, "seeded": len(DEFAULT_PRICES)}

@router.get("/", response_model=List[schemas.MaterialPrice])
def list_prices(db: Session = Depends(get_db)):
    return db.query(models.MaterialPrice).all()

@router.patch("/{material_type}", response_model=schemas.MaterialPrice)
def update_price(material_type: models.MaterialType, update: schemas.MaterialPriceCreate, db: Session = Depends(get_db)):
    price = db.query(models.MaterialPrice).filter(models.MaterialPrice.material_type == material_type).first()
    if not price:
        raise HTTPException(status_code=404, detail="Material not found — run /materials/seed first")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(price, field, value)
    db.commit()
    db.refresh(price)
    return price
