"""
JWT token creation/validation and password hashing utilities.

Libraries: python-jose[cryptography] for JWT, passlib[bcrypt] for passwords.
"""

import hashlib
import uuid
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from . import models

# --- Password hashing ---

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT tokens ---

security = HTTPBearer(auto_error=False)


def _get_jwt_secret() -> str:
    """Get JWT secret, failing loudly if not configured."""
    secret = settings.JWT_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET not configured — set it in environment variables",
        )
    return secret


def create_access_token(user_id: int) -> str:
    """Create a short-lived access token (15 min default)."""
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """Create a long-lived refresh token (30 day default). Raw token returned; hash stored in DB."""
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid.uuid4()),  # Unique ID for this token
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=settings.JWT_ALGORITHM)


def hash_token(token: str) -> str:
    """SHA-256 hash of a token for storage. Refresh tokens are stored hashed."""
    return hashlib.sha256(token.encode()).hexdigest()


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def store_refresh_token(db: Session, user_id: int, token: str) -> models.AuthToken:
    """Store a hashed refresh token in the database."""
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    db_token = models.AuthToken(
        user_id=user_id,
        token_hash=hash_token(token),
        token_type="refresh",
        expires_at=expire,
    )
    db.add(db_token)
    db.commit()
    return db_token


# --- FastAPI dependency: get current user from JWT ---

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> models.User:
    """FastAPI dependency — extracts and validates JWT, returns User object."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — use an access token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user
