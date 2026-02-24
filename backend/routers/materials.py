from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/materials", tags=["materials"])

# Default material prices (per lb) — update via API as market prices change
DEFAULT_PRICES = {
    # Prices derived from real Osario + Wexler quotes (Chicago, 2023-2025)
    # NOTE: These are RAW supplier costs. The app applies material_markup on top.
    models.MaterialType.MILD_STEEL: {"price_per_lb": 0.67, "notes": "A36 HR sheet/plate — Wexler/Osario avg"},
    models.MaterialType.STAINLESS_304: {"price_per_lb": 3.28, "notes": "304 2B sheet — Osario 1/2025"},
    models.MaterialType.STAINLESS_316: {"price_per_lb": 4.20, "notes": "316 — estimated ~28% over 304"},
    models.MaterialType.ALUMINUM_6061: {"price_per_lb": 1.85, "notes": "6061-T6 — market estimate"},
    models.MaterialType.ALUMINUM_5052: {"price_per_lb": 1.70, "notes": "5052-H32 — market estimate"},
    models.MaterialType.DOM_TUBING: {"price_per_lb": 2.60, "notes": "1.5\" OD 11G DOM round tube — Wexler 1/2025 ~$4.65/ft"},
    models.MaterialType.SQUARE_TUBING: {"price_per_lb": 0.82, "notes": "HSS square tubing 11ga — Osario/Wexler avg 2023-2025"},
    models.MaterialType.ANGLE_IRON: {"price_per_lb": 0.75, "notes": "A36 angle 2\"x2\"x3/16\" — Osario 1/2025"},
    models.MaterialType.FLAT_BAR: {"price_per_lb": 0.96, "notes": "A36 flat bar — Wexler/Osario avg 2023-2025"},
    models.MaterialType.PLATE: {"price_per_lb": 0.56, "notes": "3/8\" HR plate — Wexler 6/2024"},
    models.MaterialType.CHANNEL: {"price_per_lb": 0.80, "notes": "A36 channel — Osario avg"},
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
