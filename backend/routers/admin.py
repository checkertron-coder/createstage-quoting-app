"""
Admin endpoints — invite code + demo link management + account diagnostics.

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
from ..auth import hash_password
from ..database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")


def _require_admin(x_admin_secret: Optional[str] = Header(None)):
    """Verify admin secret header. Returns 503 if ADMIN_SECRET not configured."""
    if not ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin endpoints not configured — set ADMIN_SECRET env var",
        )
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


@router.delete("/invite-codes/{code}", dependencies=[Depends(_require_admin)])
def delete_invite_code(
    code: str,
    db: Session = Depends(get_db),
):
    """Permanently delete an invite code."""
    invite = db.query(models.InviteCode).filter(
        models.InviteCode.code == code.strip().upper()
    ).first()
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite code not found: %s" % code,
        )
    db.delete(invite)
    db.commit()
    return {"deleted": code.strip().upper()}


@router.patch("/invite-codes/{code}/reset", dependencies=[Depends(_require_admin)])
def reset_invite_code(
    code: str,
    db: Session = Depends(get_db),
):
    """Reset uses to 0 and clear used_by_email for an invite code."""
    invite = db.query(models.InviteCode).filter(
        models.InviteCode.code == code.strip().upper()
    ).first()
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite code not found: %s" % code,
        )
    invite.uses = 0
    invite.used_by_email = None
    db.commit()
    db.refresh(invite)
    return {
        "code": invite.code,
        "uses": invite.uses,
        "used_by_email": invite.used_by_email,
        "is_active": invite.is_active,
    }


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


# --- Account Diagnostics ---

@router.get("/users", dependencies=[Depends(_require_admin)])
def list_users(db: Session = Depends(get_db)):
    """List all user accounts with auth diagnostics (no secrets exposed)."""
    users = db.query(models.User).order_by(models.User.id).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "has_password": bool(u.password_hash),
            "hash_prefix": u.password_hash[:7] if u.password_hash else None,
            "hash_len": len(u.password_hash) if u.password_hash else 0,
            "email_verified": getattr(u, "email_verified", None),
            "tier": u.tier,
            "subscription_status": getattr(u, "subscription_status", None),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


class ForcePasswordRequest(BaseModel):
    email: str
    new_password: str


@router.post("/force-password", dependencies=[Depends(_require_admin)])
def force_password(
    request: ForcePasswordRequest,
    db: Session = Depends(get_db),
):
    """Force-set a user's password. Also sets email_verified=True."""
    from sqlalchemy import func
    user = db.query(models.User).filter(
        func.lower(models.User.email) == request.email.strip().lower()
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found: %s" % request.email)

    user.password_hash = hash_password(request.new_password)
    user.email_verified = True
    db.commit()
    return {
        "email": user.email,
        "password_reset": True,
        "email_verified": True,
        "hash_prefix": user.password_hash[:7],
    }
