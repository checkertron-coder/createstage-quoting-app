"""
Bid Parser API — Session 7.

POST /api/bid/upload        — Upload PDF bid document, extract fab scope
POST /api/bid/parse-text    — Parse pasted text for fab scope
POST /api/bid/{bid_id}/quote-items — Create quote sessions from selected items
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..bid_parser import BidParser
from ..database import get_db
from ..pdf_extractor import PDFExtractor

router = APIRouter(prefix="/bid", tags=["bid-parser"])

# Singletons
_parser = BidParser()
_extractor = PDFExtractor()


class ParseTextRequest(BaseModel):
    text: str


class QuoteItemsRequest(BaseModel):
    item_indices: list


# --- Endpoints ---

@router.post("/upload")
def upload_bid(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Upload a PDF bid document and extract metal fab scope items.

    Returns extracted items mapped to job types with pre-populated fields.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Read file bytes
    file_bytes = file.file.read()

    # Check size (50 MB limit)
    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > 50:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size_mb:.1f} MB (max 50 MB)",
        )

    # Extract text from PDF
    try:
        extraction = _extractor.extract_text_from_bytes(file_bytes, filename=file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check extraction quality
    warnings = []
    if extraction["extraction_quality"] == "poor":
        warnings.append(
            "PDF appears to be scanned images with little selectable text. "
            "OCR would improve results. Consider pasting the text manually."
        )

    # Parse the extracted text
    result = _parser.parse_document(
        text=extraction["text"],
        filename=file.filename or "upload.pdf",
    )
    result["warnings"].extend(warnings)

    # Store the analysis
    bid_id = str(uuid.uuid4())
    analysis = models.BidAnalysis(
        id=bid_id,
        user_id=current_user.id,
        filename=file.filename,
        page_count=extraction["page_count"],
        extraction_confidence=result["extraction_confidence"],
        items_json=result["items"],
        warnings_json=result["warnings"],
    )
    db.add(analysis)
    db.commit()

    return {
        "bid_id": bid_id,
        "filename": file.filename,
        "page_count": extraction["page_count"],
        "file_size_mb": round(file_size_mb, 2),
        "extraction_quality": extraction["extraction_quality"],
        "extraction_confidence": result["extraction_confidence"],
        "items": result["items"],
        "warnings": result["warnings"],
    }


@router.post("/parse-text")
def parse_text(
    request: ParseTextRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Parse pasted text for metal fab scope items.
    For users who copy/paste from bid documents.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is empty")

    result = _parser.parse_document(text=request.text, filename="pasted-text")

    # Store the analysis
    bid_id = str(uuid.uuid4())
    analysis = models.BidAnalysis(
        id=bid_id,
        user_id=current_user.id,
        filename="pasted-text",
        page_count=result["total_pages_approx"],
        extraction_confidence=result["extraction_confidence"],
        items_json=result["items"],
        warnings_json=result["warnings"],
    )
    db.add(analysis)
    db.commit()

    return {
        "bid_id": bid_id,
        "filename": "pasted-text",
        "page_count": result["total_pages_approx"],
        "extraction_confidence": result["extraction_confidence"],
        "items": result["items"],
        "warnings": result["warnings"],
    }


@router.post("/{bid_id}/quote-items")
def create_quote_sessions(
    bid_id: str,
    request: QuoteItemsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Create quote sessions from selected bid items.

    For each selected item, creates a new quote session with
    pre-populated fields from the bid document extraction.
    The user then enters the normal question tree flow.
    """
    # Load bid analysis
    analysis = db.query(models.BidAnalysis).filter(
        models.BidAnalysis.id == bid_id,
    ).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Bid analysis not found")
    if analysis.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your bid analysis")

    items = analysis.items_json or []

    # Validate indices
    for idx in request.item_indices:
        if not isinstance(idx, int) or idx < 0 or idx >= len(items):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid item index: {idx}. Must be 0-{len(items) - 1}",
            )

    # Create a session for each selected item
    sessions = []
    from ..question_trees.engine import QuestionTreeEngine
    engine = QuestionTreeEngine()
    available_trees = engine.list_available_trees()

    for idx in request.item_indices:
        item = items[idx]
        job_type = item.get("job_type")

        # Skip items with no job type mapping
        if not job_type:
            sessions.append({
                "session_id": None,
                "job_type": None,
                "item_index": idx,
                "error": "No job type mapping for this item. Use custom_fab or specify manually.",
                "pre_populated": {},
            })
            continue

        # Build description from extracted item
        description = item.get("description", "")
        location = item.get("location")
        if location:
            description += f" at {location}"
        detail_ref = item.get("detail_reference")
        if detail_ref:
            description += f" ({detail_ref})"

        # Create session
        session_id = str(uuid.uuid4())
        pre_populated = item.get("pre_populated_fields", {})

        session = models.QuoteSession(
            id=session_id,
            user_id=current_user.id,
            job_type=job_type,
            stage="clarify" if job_type in available_trees else "intake",
            params_json=dict(pre_populated),
            messages_json=[{
                "role": "bid_extraction",
                "content": {
                    "bid_id": bid_id,
                    "item_index": idx,
                    "description": description,
                    "source_text": item.get("source_text", ""),
                },
                "timestamp": datetime.utcnow().isoformat(),
            }],
            photo_urls=[],
            status="active",
        )
        db.add(session)

        sessions.append({
            "session_id": session_id,
            "job_type": job_type,
            "item_index": idx,
            "pre_populated": pre_populated,
        })

    db.commit()

    return {"sessions": sessions}
