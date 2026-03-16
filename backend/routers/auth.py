"""
Auth endpoints — register, login, refresh, me, profile.

Registration flow:
- POST /api/auth/register → create account (with optional invite code + terms acceptance)
- POST /api/auth/login → authenticate with email + password
- POST /api/auth/validate-code → check if invite code is valid
- POST /api/auth/guest → 410 Gone (removed in P53)
"""

import base64
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
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
    password: Optional[str] = None  # Optional when invite code provided
    invite_code: Optional[str] = None
    terms_accepted: Optional[bool] = False
    nda_accepted: Optional[bool] = False  # Kept for backward compat, ignored
    demo_token: Optional[str] = None  # If upgrading a demo user


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


class ValidateCodeRequest(BaseModel):
    code: str


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
    subscription_status: Optional[str] = None
    trial_ends_at: Optional[str] = None
    quotes_this_month: Optional[int] = 0
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
        "subscription_status": getattr(user, "subscription_status", "trial"),
        "trial_ends_at": (
            user.trial_ends_at.isoformat()
            if getattr(user, "trial_ends_at", None) else None
        ),
        "quotes_this_month": getattr(user, "quotes_this_month", 0),
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


def _validate_invite_code(code_str: str, db: Session):
    """Validate an invite code. Returns the InviteCode record or None."""
    code = db.query(models.InviteCode).filter(
        models.InviteCode.code == code_str.strip().upper()
    ).first()
    if not code:
        return None
    if not code.is_active:
        return None
    if code.expires_at and code.expires_at < datetime.utcnow():
        return None
    if code.max_uses is not None and code.uses >= code.max_uses:
        return None
    return code


# --- Endpoints ---

@router.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    Create a new account or claim a provisional one.

    - With invite code: password is optional (passwordless beta onboarding).
    - With demo_token: upgrades existing demo user to real account.
    - Without invite code: password required (min 8 chars).
    """
    # Validate invite code if provided
    invite_code_record = None
    if request.invite_code:
        invite_code_record = _validate_invite_code(request.invite_code, db)
        if not invite_code_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired invite code",
            )

    # Password validation: required unless invite code is provided
    has_password = request.password and len(request.password) >= 8
    if request.password and len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )
    if not invite_code_record and not has_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    # Demo token upgrade: transfer demo user to real account
    if request.demo_token:
        demo_link = db.query(models.DemoLink).filter(
            models.DemoLink.token == request.demo_token,
        ).first()
        if demo_link and demo_link.demo_user_id:
            demo_user = db.query(models.User).filter(
                models.User.id == demo_link.demo_user_id,
            ).first()
            if demo_user and demo_user.is_provisional:
                # Upgrade demo user — change email, set password, keep quotes
                demo_user.email = request.email
                if has_password:
                    demo_user.password_hash = hash_password(request.password)
                    demo_user.is_provisional = False
                demo_user.updated_at = datetime.utcnow()

                if invite_code_record:
                    demo_user.tier = invite_code_record.tier
                    demo_user.invite_code_used = invite_code_record.code
                    invite_code_record.uses += 1
                else:
                    demo_user.tier = "free"

                demo_user.trial_ends_at = datetime.utcnow() + timedelta(days=14)
                demo_user.subscription_status = "trial"
                if request.terms_accepted:
                    demo_user.terms_accepted_at = datetime.utcnow()

                db.commit()
                db.refresh(demo_user)
                tokens = _issue_tokens(demo_user, db)
                return {**tokens, "user": _user_to_response(demo_user), "upgraded_demo": True}

    existing = db.query(models.User).filter(models.User.email == request.email).first()

    if existing:
        if existing.is_provisional and not existing.password_hash:
            # Claim provisional account
            if has_password:
                existing.password_hash = hash_password(request.password)
                existing.is_provisional = False
            existing.updated_at = datetime.utcnow()

            # Set subscription fields
            if invite_code_record:
                existing.tier = invite_code_record.tier
                existing.invite_code_used = invite_code_record.code
                invite_code_record.uses += 1
            else:
                existing.tier = "free"

            existing.trial_ends_at = datetime.utcnow() + timedelta(days=14)
            existing.subscription_status = "trial"

            if request.terms_accepted:
                existing.terms_accepted_at = datetime.utcnow()

            db.commit()
            db.refresh(existing)
            tokens = _issue_tokens(existing, db)
            return {**tokens, "user": _user_to_response(existing), "claimed_provisional": True}
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account with this email already exists",
            )

    # Determine tier based on invite code
    tier = "free"
    if invite_code_record:
        tier = invite_code_record.tier

    password_hash = hash_password(request.password) if has_password else None

    user = models.User(
        email=request.email,
        password_hash=password_hash,
        is_provisional=not has_password,
        is_verified=False,
        tier=tier,
        subscription_status="trial",
        trial_ends_at=datetime.utcnow() + timedelta(days=14),
        invite_code_used=invite_code_record.code if invite_code_record else None,
        terms_accepted_at=datetime.utcnow() if request.terms_accepted else None,
    )
    db.add(user)

    # Increment invite code uses
    if invite_code_record:
        invite_code_record.uses += 1

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
def guest():
    """
    Guest access has been removed. All users must register.

    Returns 410 Gone for backward compatibility signaling.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Guest access has been removed. Please register for an account.",
    )


@router.post("/validate-code")
def validate_code(request: ValidateCodeRequest, db: Session = Depends(get_db)):
    """Check if an invite code is valid without consuming it."""
    code = _validate_invite_code(request.code, db)
    if not code:
        return {"valid": False, "tier": None}
    return {"valid": True, "tier": code.tier}


@router.post("/redeem-demo")
def redeem_demo(token: str, db: Session = Depends(get_db)):
    """
    Redeem a demo link token.

    Creates a provisional user, issues JWT, returns tokens.
    Called by GET /demo/{token} route in main.py.
    """
    demo_link = db.query(models.DemoLink).filter(
        models.DemoLink.token == token,
    ).first()

    if not demo_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo link not found",
        )

    if demo_link.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This demo link has expired. Register for full access.",
        )

    # If already redeemed, reissue tokens for existing demo user
    if demo_link.is_used and demo_link.demo_user_id:
        demo_user = db.query(models.User).filter(
            models.User.id == demo_link.demo_user_id,
        ).first()
        if demo_user:
            tokens = _issue_tokens(demo_user, db)
            return {**tokens, "user": _user_to_response(demo_user), "demo": True}

    # Create provisional demo user
    demo_email = "demo-%s@createquote.app" % demo_link.token[:12]
    demo_user = models.User(
        email=demo_email,
        password_hash=None,
        is_provisional=True,
        is_verified=False,
        tier=demo_link.tier,
        subscription_status="demo",
        quotes_this_month=0,
    )
    db.add(demo_user)
    db.flush()  # Get the user ID

    demo_link.is_used = True
    demo_link.used_at = datetime.utcnow()
    demo_link.demo_user_id = demo_user.id

    db.commit()
    db.refresh(demo_user)

    tokens = _issue_tokens(demo_user, db)
    return {**tokens, "user": _user_to_response(demo_user), "demo": True}


@router.get("/demo-status")
def demo_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if current user is a demo user and return remaining quota."""
    demo_link = db.query(models.DemoLink).filter(
        models.DemoLink.demo_user_id == current_user.id,
    ).first()

    if not demo_link:
        return {"is_demo": False}

    quotes_used = getattr(current_user, "quotes_this_month", 0) or 0
    return {
        "is_demo": True,
        "quotes_remaining": max(0, demo_link.max_quotes - quotes_used),
        "max_quotes": demo_link.max_quotes,
        "expires_at": demo_link.expires_at.isoformat() if demo_link.expires_at else None,
        "demo_token": demo_link.token,
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


ALLOWED_LOGO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB


@router.post("/profile/logo")
async def upload_logo(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a shop logo. Stored as base64 data URI in user.logo_url.

    Validates: JPG/PNG/WEBP, max 2MB.
    Railway has ephemeral filesystem so we store as data URI.
    """
    if file.content_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Allowed: JPG, PNG, WEBP.",
        )

    contents = await file.read()
    if len(contents) > MAX_LOGO_SIZE:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum 2MB.",
        )

    # Encode as data URI
    b64 = base64.b64encode(contents).decode("ascii")
    data_uri = "data:%s;base64,%s" % (file.content_type, b64)

    current_user.logo_url = data_uri
    current_user.updated_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Logo uploaded successfully",
        "logo_url": data_uri[:50] + "...",  # Truncated for response
    }


# --- Quote access control ---

# Quota limits per tier
TIER_QUOTE_LIMITS = {
    "free": 3,           # 3 quotes total (demo)
    "starter": 10,       # 10 per month
    "professional": None, # unlimited
    "shop": None,         # unlimited
}


def check_quote_access(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Dependency that checks whether the user can create a new quote.

    For demo users: checks the DemoLink's max_quotes and expiration.
    For regular users: checks tier quota limits.
    Raises 403 if quota exceeded.
    """
    # Check if this is a demo user
    demo_link = db.query(models.DemoLink).filter(
        models.DemoLink.demo_user_id == current_user.id,
    ).first()

    if demo_link:
        # Demo user — check expiration and max_quotes
        if demo_link.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Demo link has expired. Register for full access.",
            )
        quotes_used = getattr(current_user, "quotes_this_month", 0) or 0
        if quotes_used >= demo_link.max_quotes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Demo limit reached (%d quotes). Register for full access."
                    % demo_link.max_quotes
                ),
            )
        return current_user

    # Regular user — check tier limits
    tier = getattr(current_user, "tier", "free") or "free"
    limit = TIER_QUOTE_LIMITS.get(tier)

    if limit is None:
        # Unlimited
        return current_user

    quotes_used = getattr(current_user, "quotes_this_month", 0) or 0
    if quotes_used >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You've reached the %d-quote limit for the %s tier. "
                "Upgrade your plan at createquote.app to continue quoting."
                % (limit, tier.title())
            ),
        )

    return current_user
