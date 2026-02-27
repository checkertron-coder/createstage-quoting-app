"""
Auth endpoints — register, login, refresh, guest, me, profile.

Provisional account flow:
- POST /api/auth/guest → creates provisional user, returns JWT
- User can immediately start quoting
- POST /api/auth/register → claims provisional or creates new account
- Quotes created with provisional user_id stay attached
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional

from .. import models
from ..auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    hash_token,
    store_refresh_token,
    verify_password,
)
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


# --- Request/Response schemas ---

class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ProfileUpdate(BaseModel):
    shop_name: Optional[str] = None
    shop_address: Optional[str] = None
    shop_phone: Optional[str] = None
    shop_email: Optional[str] = None
    logo_url: Optional[str] = None
    rate_inshop: Optional[float] = None
    rate_onsite: Optional[float] = None
    markup_default: Optional[int] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int


class UserResponse(BaseModel):
    id: int
    email: str
    is_verified: bool
    is_provisional: bool
    shop_name: Optional[str] = None
    shop_address: Optional[str] = None
    shop_phone: Optional[str] = None
    shop_email: Optional[str] = None
    logo_url: Optional[str] = None
    rate_inshop: float
    rate_onsite: float
    markup_default: int
    tier: str
    created_at: datetime

    class Config:
        from_attributes = True


def _user_to_response(user: models.User) -> dict:
    """Convert User model to response dict — never expose password_hash."""
    return {
        "id": user.id,
        "email": user.email,
        "is_verified": user.is_verified,
        "is_provisional": user.is_provisional,
        "shop_name": user.shop_name,
        "shop_address": user.shop_address,
        "shop_phone": user.shop_phone,
        "shop_email": user.shop_email,
        "logo_url": user.logo_url,
        "rate_inshop": user.rate_inshop,
        "rate_onsite": user.rate_onsite,
        "markup_default": user.markup_default,
        "tier": user.tier,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _issue_tokens(user: models.User, db: Session) -> dict:
    """Create access + refresh tokens for a user. Stores refresh token hash in DB."""
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    store_refresh_token(db, user.id, refresh_token)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_id": user.id,
    }


# --- Endpoints ---

@router.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    Create a new account or claim a provisional one.

    If user already exists with is_provisional=True and no password,
    this sets the password and converts to a full account.
    """
    existing = db.query(models.User).filter(models.User.email == request.email).first()

    if existing:
        if existing.is_provisional and not existing.password_hash:
            # Claim provisional account
            existing.password_hash = hash_password(request.password)
            existing.is_provisional = False
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            tokens = _issue_tokens(existing, db)
            return {**tokens, "user": _user_to_response(existing), "claimed_provisional": True}
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account with this email already exists",
            )

    user = models.User(
        email=request.email,
        password_hash=hash_password(request.password),
        is_provisional=False,
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    tokens = _issue_tokens(user, db)
    return {**tokens, "user": _user_to_response(user)}


@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email + password. Returns access + refresh tokens."""
    user = db.query(models.User).filter(models.User.email == request.email).first()

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    tokens = _issue_tokens(user, db)
    return {**tokens, "user": _user_to_response(user)}


@router.post("/refresh")
def refresh(request: RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a valid refresh token for a new access token."""
    payload = decode_token(request.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected refresh token",
        )

    # Verify the refresh token hash exists in DB
    token_hash = hash_token(request.refresh_token)
    db_token = db.query(models.AuthToken).filter(
        models.AuthToken.token_hash == token_hash,
        models.AuthToken.token_type == "refresh",
    ).first()

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found — it may have been revoked",
        )

    if db_token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user_id = int(payload["sub"])
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Issue new access token only (reuse existing refresh token)
    new_access = create_access_token(user.id)
    return {
        "access_token": new_access,
        "token_type": "bearer",
        "user_id": user.id,
    }


@router.post("/guest")
def guest(db: Session = Depends(get_db)):
    """
    Create a provisional account with no password.

    Returns a JWT immediately — user can start quoting right away.
    Call /register later to claim the account with a real email + password.
    """
    # Generate a unique placeholder email
    placeholder_email = f"guest_{uuid.uuid4().hex[:12]}@provisional.local"
    session_id = str(uuid.uuid4())

    user = models.User(
        email=placeholder_email,
        password_hash=None,
        is_provisional=True,
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    tokens = _issue_tokens(user, db)
    return {
        **tokens,
        "session_id": session_id,
        "user": _user_to_response(user),
    }


@router.get("/me")
def me(current_user: models.User = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return _user_to_response(current_user)


@router.put("/profile")
def update_profile(
    update: ProfileUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current user's shop profile."""
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    current_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    return _user_to_response(current_user)
