from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from pydantic import BaseModel
from .. import models
from ..database import get_db

router = APIRouter(prefix="/process-rates", tags=["process-rates"])

# Default rates — Chicago commercial fab, 2024-2025
# Source: TheFabricator industry data + real project data (Leopardo sign @ $185/hr)
DEFAULT_RATES = {
    models.ProcessType.LAYOUT: {"rate_per_hour": 75.0, "description": "Layout, measuring, marking, planning"},
    models.ProcessType.CUTTING: {"rate_per_hour": 85.0, "description": "Cold saw, band saw, angle grinder cuts"},
    models.ProcessType.CNC_PLASMA: {"rate_per_hour": 125.0, "description": "CNC plasma table (machine time + setup)"},
    models.ProcessType.CNC_ROUTER: {"rate_per_hour": 125.0, "description": "CNC router (machine time + setup)"},
    models.ProcessType.WELDING: {"rate_per_hour": 125.0, "description": "MIG welding, structural and architectural"},
    models.ProcessType.TIG_WELDING: {"rate_per_hour": 150.0, "description": "TIG welding — stainless, aluminum, precision"},
    models.ProcessType.GRINDING: {"rate_per_hour": 75.0, "description": "Grinding, finishing, deburring, weld cleanup"},
    models.ProcessType.DRILLING: {"rate_per_hour": 85.0, "description": "Drilling, punching, tapping"},
    models.ProcessType.BENDING: {"rate_per_hour": 95.0, "description": "Press brake, tube bending, forming"},
    models.ProcessType.ASSEMBLY: {"rate_per_hour": 100.0, "description": "Fit-up, tacking, assembly, test fitting"},
    models.ProcessType.DESIGN: {"rate_per_hour": 150.0, "description": "Fusion 360 / CAD design, drawings, submittals"},
    models.ProcessType.FIELD_INSTALL: {"rate_per_hour": 185.0, "description": "On-site installation, field welding"},
    models.ProcessType.PROJECT_MANAGEMENT: {"rate_per_hour": 125.0, "description": "PM, coordination, submittals, client comms"},
    models.ProcessType.POWDER_COAT: {"rate_per_hour": 0.0, "description": "Outsourced — use sq_ft pricing (avg $2.50-5.00/sqft)"},
    models.ProcessType.PAINT: {"rate_per_hour": 75.0, "description": "In-house paint, primer, clear coat"},
}


class ProcessRateUpdate(BaseModel):
    rate_per_hour: float
    description: str = None


@router.get("/seed")
def seed_process_rates(db: Session = Depends(get_db)):
    """Seed default process rates. Safe to run multiple times — skips existing."""
    seeded = 0
    for proc_type, data in DEFAULT_RATES.items():
        existing = db.query(models.ProcessRate).filter(
            models.ProcessRate.process_type == proc_type
        ).first()
        if not existing:
            db.add(models.ProcessRate(process_type=proc_type, **data))
            seeded += 1
    db.commit()
    return {"ok": True, "seeded": seeded}


@router.get("/")
def list_process_rates(db: Session = Depends(get_db)):
    rates = db.query(models.ProcessRate).all()
    return [
        {
            "id": r.id,
            "process_type": r.process_type,
            "rate_per_hour": r.rate_per_hour,
            "description": r.description,
            "updated_at": r.updated_at,
        }
        for r in rates
    ]


@router.patch("/{process_type}")
def update_process_rate(
    process_type: models.ProcessType,
    update: ProcessRateUpdate,
    db: Session = Depends(get_db)
):
    rate = db.query(models.ProcessRate).filter(
        models.ProcessRate.process_type == process_type
    ).first()
    if not rate:
        raise HTTPException(status_code=404, detail="Process rate not found — run /process-rates/seed first")
    rate.rate_per_hour = update.rate_per_hour
    if update.description:
        rate.description = update.description
    db.commit()
    db.refresh(rate)
    return {"process_type": rate.process_type, "rate_per_hour": rate.rate_per_hour}
