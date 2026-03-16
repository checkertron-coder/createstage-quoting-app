"""
Admin endpoints — invite code + demo link management.

Protected by ADMIN_SECRET env var (simple shared secret for now).
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "createstage-admin-2026")


def _require_admin(x_admin_secret: Optional[str] = Header(None)):
    """Verify admin secret header."""
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin secret",
        )


class CreateInviteCodeRequest(BaseModel):
    code: str
    tier: Optional[str] = "professional"
    max_uses: Optional[int] = None
    expires_at: Optional[str] = None  # ISO format datetime
    created_by: Optional[str] = "admin"


@router.post("/invite-codes", dependencies=[Depends(_require_admin)])
def create_invite_code(
    request: CreateInviteCodeRequest,
    db: Session = Depends(get_db),
):
    """Create a new invite code."""
    code_upper = request.code.strip().upper()

    existing = db.query(models.InviteCode).filter(
        models.InviteCode.code == code_upper
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invite code already exists",
        )

    expires_at = None
    if request.expires_at:
        try:
            expires_at = datetime.fromisoformat(request.expires_at)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid expires_at format. Use ISO 8601.",
            )

    code = models.InviteCode(
        code=code_upper,
        tier=request.tier or "professional",
        max_uses=request.max_uses,
        expires_at=expires_at,
        created_by=request.created_by or "admin",
    )
    db.add(code)
    db.commit()
    db.refresh(code)

    return {
        "id": code.id,
        "code": code.code,
        "tier": code.tier,
        "max_uses": code.max_uses,
        "uses": code.uses,
        "expires_at": code.expires_at.isoformat() if code.expires_at else None,
        "is_active": code.is_active,
    }


@router.get("/invite-codes", dependencies=[Depends(_require_admin)])
def list_invite_codes(db: Session = Depends(get_db)):
    """List all invite codes."""
    codes = db.query(models.InviteCode).order_by(
        models.InviteCode.created_at.desc()
    ).all()
    return [
        {
            "id": c.id,
            "code": c.code,
            "tier": c.tier,
            "max_uses": c.max_uses,
            "uses": c.uses,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "is_active": c.is_active,
            "created_by": c.created_by,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in codes
    ]


# --- Demo Links ---

class CreateDemoLinkRequest(BaseModel):
    label: Optional[str] = None
    max_quotes: Optional[int] = 3
    expires_hours: Optional[int] = 48


@router.post("/demo-links", dependencies=[Depends(_require_admin)])
def create_demo_link(
    request: CreateDemoLinkRequest,
    db: Session = Depends(get_db),
):
    """Create a 48-hour magic demo link."""
    token = secrets.token_urlsafe(24)
    expires_at = datetime.utcnow() + timedelta(hours=request.expires_hours or 48)

    link = models.DemoLink(
        token=token,
        label=request.label,
        tier="professional",
        max_quotes=request.max_quotes or 3,
        expires_at=expires_at,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    return {
        "id": link.id,
        "token": link.token,
        "url": "/demo/%s" % link.token,
        "label": link.label,
        "max_quotes": link.max_quotes,
        "expires_at": link.expires_at.isoformat(),
    }


@router.get("/demo-links", dependencies=[Depends(_require_admin)])
def list_demo_links(db: Session = Depends(get_db)):
    """List all demo links."""
    links = db.query(models.DemoLink).order_by(
        models.DemoLink.created_at.desc()
    ).all()
    return [
        {
            "id": dl.id,
            "token": dl.token,
            "label": dl.label,
            "max_quotes": dl.max_quotes,
            "is_used": dl.is_used,
            "demo_user_id": dl.demo_user_id,
            "expires_at": dl.expires_at.isoformat() if dl.expires_at else None,
            "created_at": dl.created_at.isoformat() if dl.created_at else None,
        }
        for dl in links
    ]
