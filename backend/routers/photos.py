"""
Photo upload endpoint.

POST /api/photos/upload — Upload image(s) for quote sessions.
Stores to Cloudflare R2 if configured, otherwise local uploads/ directory.
"""

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..config import settings
from ..database import get_db

router = APIRouter(prefix="/photos", tags=["photos"])

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _get_extension(filename: str) -> str:
    """Extract and validate file extension."""
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _r2_configured() -> bool:
    """Check if Cloudflare R2 credentials are set."""
    return bool(
        settings.CLOUDFLARE_R2_ACCOUNT_ID
        and settings.CLOUDFLARE_R2_ACCESS_KEY_ID
        and settings.CLOUDFLARE_R2_SECRET_ACCESS_KEY
    )


async def _upload_to_r2(file_bytes: bytes, filename: str, content_type: str) -> str:
    """Upload file to Cloudflare R2 and return the public URL."""
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{settings.CLOUDFLARE_R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.CLOUDFLARE_R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
    )
    from io import BytesIO

    s3.upload_fileobj(
        BytesIO(file_bytes),
        settings.CLOUDFLARE_R2_BUCKET,
        filename,
        ExtraArgs={"ContentType": content_type},
    )
    return f"https://{settings.CLOUDFLARE_R2_BUCKET}.{settings.CLOUDFLARE_R2_ACCOUNT_ID}.r2.dev/{filename}"


async def _save_locally(file_bytes: bytes, filename: str) -> str:
    """Save file to local uploads/ directory and return the path."""
    upload_dir = Path("uploads") / "photos"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / filename
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return f"/uploads/photos/{filename}"


@router.post("/upload")
async def upload_photo(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    current_user: models.User = Depends(get_current_user),
):
    """
    Upload a photo for a quote session.

    - Validates file type (jpg, jpeg, png, webp, heic)
    - Validates file size (max 10MB)
    - Stores to R2 if configured, otherwise local uploads/
    - Returns the photo URL/path
    """
    # Validate file type
    ext = _get_extension(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read file content
    file_bytes = await file.read()

    # Validate file size
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(file_bytes) / 1024 / 1024:.1f}MB). Maximum is 10MB.",
        )

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")

    # Generate unique filename
    prefix = session_id or "unsorted"
    unique_name = f"{prefix}_{uuid.uuid4().hex[:12]}.{ext}"

    # Determine content type
    content_type_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "heic": "image/heic",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")

    # Upload to R2 or save locally
    if _r2_configured():
        photo_url = await _upload_to_r2(file_bytes, unique_name, content_type)
    else:
        photo_url = await _save_locally(file_bytes, unique_name)

    return {
        "photo_url": photo_url,
        "filename": unique_name,
    }
