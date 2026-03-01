"""
Quote Session API — conversation flow for the 6-stage pipeline.

POST /api/session/start        — Start a new quote session from a description
POST /api/session/{id}/answer  — Submit answers, get next questions
GET  /api/session/{id}/status  — Current state of a session
POST /api/session/{id}/calculate — Run Stage 3 calculator on completed session
POST /api/session/{id}/estimate  — Run Stage 4 labor estimator on calculated session
POST /api/session/{id}/price     — Run Stage 5 pricing engine, create Quote record
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..database import get_db
from ..question_trees.engine import QuestionTreeEngine, detect_job_type
from ..calculators.registry import get_calculator, has_calculator

router = APIRouter(prefix="/session", tags=["quote-session"])

# Singleton engine — cached trees, no state
engine = QuestionTreeEngine()


# --- Request/Response schemas ---

class StartSessionRequest(BaseModel):
    description: str
    job_type: Optional[str] = None
    photos: Optional[list] = None
    photo_urls: Optional[list] = None


class AnswerRequest(BaseModel):
    answers: dict  # {field_id: value, ...}
    photo_url: Optional[str] = None


# --- Endpoints ---

@router.post("/start")
def start_session(
    request: StartSessionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Start a new quote session.

    1. If job_type not provided, uses Gemini to detect it from description
    2. Runs extract_from_description to pull fields from initial text
    3. Returns session_id, detected job_type, extracted fields, and next questions
    """
    # Detect job type if not provided
    if request.job_type:
        job_type = request.job_type
        detection_confidence = 1.0
        ambiguous = False
    else:
        detection = detect_job_type(request.description)
        job_type = detection.get("job_type", "custom_fab")
        detection_confidence = detection.get("confidence", 0.0)
        ambiguous = detection.get("ambiguous", True)

    # Merge photo_urls from both fields (backward compat + new field)
    photo_urls = list(request.photo_urls or request.photos or [])

    # Validate that we have a question tree for this job type
    available = engine.list_available_trees()
    if job_type not in available:
        tree_loaded = False
        extracted_fields = {}
        photo_extracted_fields = {}
        photo_observations = ""
        next_questions = []
    else:
        tree_loaded = True
        # Extract fields from the description
        extracted_fields = engine.extract_from_description(job_type, request.description)

        # Extract fields from photos (if any)
        photo_extracted_fields = {}
        photo_observations = ""
        for photo_url in photo_urls:
            try:
                photo_result = engine.extract_from_photo(
                    job_type, photo_url, request.description
                )
                # Merge photo-extracted fields (text wins on conflict)
                for field_id, value in photo_result.get("extracted_fields", {}).items():
                    if field_id not in extracted_fields:
                        photo_extracted_fields[field_id] = value
                # Collect observations
                obs = photo_result.get("photo_observations", "")
                if obs:
                    photo_observations = (photo_observations + "\n" + obs).strip()
            except Exception:
                pass  # Photo extraction failure should never block session start

        # Merge: text fields first, then photo fields (text wins)
        merged_fields = dict(extracted_fields)
        merged_fields.update({k: v for k, v in photo_extracted_fields.items()
                              if k not in merged_fields})

        # Get next questions (skipping all extracted)
        next_questions = engine.get_next_questions(job_type, merged_fields)

    # Create session record
    session_id = str(uuid.uuid4())
    merged_for_storage = dict(extracted_fields)
    merged_for_storage.update({k: v for k, v in photo_extracted_fields.items()
                               if k not in merged_for_storage})
    # Preserve the original description so calculators can use it for AI cut lists
    merged_for_storage["description"] = request.description
    if photo_observations:
        merged_for_storage["photo_observations"] = photo_observations
    session = models.QuoteSession(
        id=session_id,
        user_id=current_user.id,
        job_type=job_type,
        stage="clarify" if tree_loaded else "intake",
        params_json=merged_for_storage,
        messages_json=[{
            "role": "user",
            "content": request.description,
            "timestamp": datetime.utcnow().isoformat(),
        }],
        photo_urls=photo_urls,
        status="active",
    )
    db.add(session)
    db.commit()

    # Build completion status
    if tree_loaded:
        completion = engine.get_completion_status(job_type, merged_for_storage)
    else:
        completion = {
            "is_complete": False,
            "required_total": 0,
            "required_answered": 0,
            "required_missing": [],
            "total_answered": 0,
            "completion_pct": 0.0,
        }

    return {
        "session_id": session_id,
        "job_type": job_type,
        "detection_confidence": detection_confidence,
        "ambiguous": ambiguous,
        "tree_loaded": tree_loaded,
        "extracted_fields": extracted_fields,
        "photo_extracted_fields": photo_extracted_fields,
        "photo_observations": photo_observations,
        "next_questions": _serialize_questions(next_questions),
        "completion": completion,
    }


@router.post("/{session_id}/answer")
def answer_questions(
    session_id: str,
    request: AnswerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Submit answers to questions. Returns next unanswered questions.
    """
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")
    if session.status != "active":
        raise HTTPException(status_code=400, detail=f"Session is {session.status}, not active")

    job_type = session.job_type
    if job_type not in engine.list_available_trees():
        raise HTTPException(status_code=400, detail=f"No question tree for job type: {job_type}")

    # Merge new answers into existing params
    current_params = dict(session.params_json or {})
    current_params.update(request.answers)

    # Handle photo answer if provided
    photo_observations = ""
    photo_extracted_fields = {}
    if request.photo_url:
        # Store the photo URL
        current_photos = list(session.photo_urls or [])
        current_photos.append(request.photo_url)
        session.photo_urls = current_photos

        # Run vision extraction on the new photo
        try:
            photo_result = engine.extract_from_photo(
                job_type, request.photo_url,
                description=str(request.answers.get("description", "")),
            )
            photo_observations = photo_result.get("photo_observations", "")
            for field_id, value in photo_result.get("extracted_fields", {}).items():
                if field_id not in current_params:
                    current_params[field_id] = value
                    photo_extracted_fields[field_id] = value
        except Exception:
            pass  # Photo extraction failure should not block answer submission

    # Log answers in message history
    messages = list(session.messages_json or [])
    messages.append({
        "role": "user_answers",
        "content": request.answers,
        "timestamp": datetime.utcnow().isoformat(),
    })

    # Update session — use flag_modified for JSON columns on SQLite
    from sqlalchemy.orm.attributes import flag_modified
    session.params_json = current_params
    session.messages_json = messages
    session.updated_at = datetime.utcnow()
    flag_modified(session, "params_json")
    flag_modified(session, "messages_json")
    flag_modified(session, "photo_urls")

    # Check completion
    completion = engine.get_completion_status(job_type, current_params)
    if completion["is_complete"]:
        session.stage = "calculate"

    db.commit()

    # Get next questions
    next_questions = engine.get_next_questions(job_type, current_params)

    response = {
        "session_id": session_id,
        "answered_count": completion["total_answered"],
        "required_total": completion["required_total"],
        "next_questions": _serialize_questions(next_questions),
        "is_complete": completion["is_complete"],
        "completion": completion,
    }

    if photo_observations:
        response["photo_observations"] = photo_observations
    if photo_extracted_fields:
        response["photo_extracted_fields"] = photo_extracted_fields

    return response


@router.get("/{session_id}/status")
def get_session_status(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return current state: answered fields, remaining questions, completion %.
    """
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    job_type = session.job_type
    current_params = dict(session.params_json or {})

    if job_type in engine.list_available_trees():
        completion = engine.get_completion_status(job_type, current_params)
        next_questions = engine.get_next_questions(job_type, current_params)
    else:
        completion = {
            "is_complete": False,
            "required_total": 0,
            "required_answered": 0,
            "required_missing": [],
            "total_answered": len(current_params),
            "completion_pct": 0.0,
        }
        next_questions = []

    return {
        "session_id": session_id,
        "job_type": job_type,
        "stage": session.stage,
        "status": session.status,
        "answered_fields": current_params,
        "next_questions": _serialize_questions(next_questions),
        "completion": completion,
        "photo_urls": session.photo_urls or [],
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


@router.post("/{session_id}/calculate")
def calculate_materials(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Run Stage 3 calculator on a completed session.

    Requires: all required fields answered (is_complete == True).
    Returns: material list with quantities, weights, costs.
    """
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    job_type = session.job_type

    # Check completion
    if job_type in engine.list_available_trees():
        current_params = dict(session.params_json or {})
        completion = engine.get_completion_status(job_type, current_params)
        if not completion["is_complete"]:
            raise HTTPException(
                status_code=400,
                detail=f"Session is not complete. Missing required fields: {completion['required_missing']}",
            )
    else:
        raise HTTPException(status_code=400, detail=f"No question tree for job type: {job_type}")

    # Check calculator exists
    if not has_calculator(job_type):
        raise HTTPException(
            status_code=404,
            detail=f"No calculator registered for job type: {job_type}",
        )

    # Run calculator
    print(f"CALCULATE DEBUG: fields keys = {list(current_params.keys())}")
    print(f"CALCULATE DEBUG: description = {str(current_params.get('description', 'NOT FOUND'))[:100]}")
    print(f"CALCULATE DEBUG: notes = {str(current_params.get('notes', 'NOT FOUND'))[:100]}")
    calculator = get_calculator(job_type)
    material_list = calculator.calculate(current_params)

    # Store material_list in session for Stage 4
    from sqlalchemy.orm.attributes import flag_modified
    current_params["_material_list"] = material_list
    session.params_json = current_params
    session.stage = "estimate"  # Ready for Stage 4
    session.updated_at = datetime.utcnow()
    flag_modified(session, "params_json")
    db.commit()

    return {
        "session_id": session_id,
        "job_type": job_type,
        "calculator_used": type(calculator).__name__,
        "material_list": material_list,
    }


@router.post("/{session_id}/estimate")
def estimate_labor(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Run Stage 4 labor estimator on a calculated session.

    Requires: session stage == "estimate" (set by /calculate endpoint).
    Requires: material_list stored in session (from /calculate).

    Returns labor estimate with per-process hours breakdown and finishing section.
    Transitions session stage to "price" (ready for Stage 5).
    """
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    if session.stage != "estimate":
        raise HTTPException(
            status_code=400,
            detail=f"Session stage is '{session.stage}', not 'estimate'. "
                   f"Run /calculate first.",
        )

    current_params = dict(session.params_json or {})

    # Retrieve material_list from session
    material_list = current_params.get("_material_list")
    if not material_list:
        raise HTTPException(
            status_code=400,
            detail="No material_list found in session. Run /calculate first.",
        )

    # Build QuoteParams for the estimator
    quote_params = engine.get_quote_params(
        job_type=session.job_type,
        answered_fields={k: v for k, v in current_params.items() if not k.startswith("_")},
        user_id=current_user.id,
        session_id=session_id,
        photos=session.photo_urls or [],
    )

    # Get user rates
    user_rates = {
        "rate_inshop": current_user.rate_inshop or 125.00,
        "rate_onsite": current_user.rate_onsite or 145.00,
    }

    # Run labor estimator (Stage 4)
    from ..labor_estimator import LaborEstimator
    from ..historical_validator import HistoricalValidator
    from ..finishing import FinishingBuilder
    from sqlalchemy.orm.attributes import flag_modified

    estimator = LaborEstimator()
    fields = quote_params.get("fields", {})
    finish_type = fields.get("finish", "raw")

    try:
        labor_estimate = estimator.estimate(material_list, quote_params, user_rates)

        # Run historical validation
        validator = HistoricalValidator()
        labor_estimate = validator.validate(labor_estimate, session.job_type, db)

        # Build finishing section
        finishing_builder = FinishingBuilder()
        finishing = finishing_builder.build(
            finish_type=finish_type,
            total_sq_ft=material_list.get("total_sq_ft", 0),
            labor_processes=labor_estimate.get("processes", []),
        )

        # Compute totals
        total_labor_hours = labor_estimate.get("total_hours", 0)
        total_labor_cost = round(
            sum(p["hours"] * p["rate"] for p in labor_estimate.get("processes", [])),
            2,
        )

        # Generate build instructions from material list
        build_instructions = None
        try:
            from ..calculators.ai_cut_list import AICutListGenerator
            ai_gen = AICutListGenerator()
            build_instructions = ai_gen.generate_build_instructions(
                session.job_type,
                {k: v for k, v in current_params.items() if not k.startswith("_")},
                material_list.get("items", []),
            )
        except Exception:
            pass  # Build instructions are optional — don't block the pipeline

        # Store results in session
        current_params["_labor_estimate"] = labor_estimate
        current_params["_finishing"] = finishing
        if build_instructions:
            current_params["_build_instructions"] = build_instructions
        # Store detailed cut list from material items
        current_params["_detailed_cut_list"] = material_list.get("cut_list", material_list.get("items", []))
        session.params_json = current_params
        session.stage = "price"  # Ready for Stage 5
        session.updated_at = datetime.utcnow()
        flag_modified(session, "params_json")
        db.commit()
    except Exception:
        db.rollback()

        # Fallback: use rule-based estimation
        labor_estimate = estimator._fallback_estimate(material_list, quote_params, user_rates)

        # Build finishing section with fallback estimate
        finishing_builder = FinishingBuilder()
        finishing = finishing_builder.build(
            finish_type=finish_type,
            total_sq_ft=material_list.get("total_sq_ft", 0),
            labor_processes=labor_estimate.get("processes", []),
        )

        # Compute totals
        total_labor_hours = labor_estimate.get("total_hours", 0)
        total_labor_cost = round(
            sum(p["hours"] * p["rate"] for p in labor_estimate.get("processes", [])),
            2,
        )

        # Store results in session
        current_params["_labor_estimate"] = labor_estimate
        current_params["_finishing"] = finishing
        current_params["_detailed_cut_list"] = material_list.get("cut_list", material_list.get("items", []))
        session.params_json = current_params
        session.stage = "price"  # Ready for Stage 5
        session.updated_at = datetime.utcnow()
        flag_modified(session, "params_json")
        db.commit()

    return {
        "session_id": session_id,
        "labor_estimate": labor_estimate,
        "finishing": finishing,
        "total_labor_hours": total_labor_hours,
        "total_labor_cost": total_labor_cost,
    }


@router.post("/{session_id}/price")
def price_quote(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Run Stage 5 pricing engine on an estimated session.

    Requires: session stage == "price" (set by /estimate endpoint).
    Requires: material_list, labor_estimate, finishing stored in session.

    Action:
    1. Run PricingEngine.build_priced_quote() with all session data
    2. Create a Quote record in the quotes table
    3. Store PricedQuote as outputs_json, QuoteParams as inputs_json
    4. Transition session stage to "output"

    Returns: PricedQuote with quote_id.
    """
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    if session.stage != "price":
        raise HTTPException(
            status_code=400,
            detail=f"Session stage is '{session.stage}', not 'price'. "
                   f"Run /estimate first.",
        )

    current_params = dict(session.params_json or {})

    # Retrieve pipeline outputs from session
    material_list = current_params.get("_material_list")
    labor_estimate = current_params.get("_labor_estimate")
    finishing = current_params.get("_finishing")

    if not material_list:
        raise HTTPException(status_code=400, detail="No material_list found. Run /calculate first.")
    if not labor_estimate:
        raise HTTPException(status_code=400, detail="No labor_estimate found. Run /estimate first.")
    if not finishing:
        raise HTTPException(status_code=400, detail="No finishing found. Run /estimate first.")

    # Build session_data for PricingEngine
    fields = {k: v for k, v in current_params.items() if not k.startswith("_")}
    session_data = {
        "session_id": session_id,
        "job_type": session.job_type,
        "fields": fields,
        "material_list": material_list,
        "labor_estimate": labor_estimate,
        "finishing": finishing,
        "detailed_cut_list": current_params.get("_detailed_cut_list", []),
        "build_instructions": current_params.get("_build_instructions", []),
    }

    # Build user dict for PricingEngine
    user_dict = {
        "id": current_user.id,
        "shop_name": current_user.shop_name,
        "markup_default": current_user.markup_default or 15,
        "rate_inshop": current_user.rate_inshop or 125.00,
        "rate_onsite": current_user.rate_onsite or 145.00,
    }

    # Run pricing engine
    from ..pricing_engine import PricingEngine
    from sqlalchemy.orm.attributes import flag_modified

    pricing_engine = PricingEngine()
    priced_quote = pricing_engine.build_priced_quote(session_data, user_dict)

    # Build QuoteParams snapshot (inputs)
    quote_params = engine.get_quote_params(
        job_type=session.job_type,
        answered_fields=fields,
        user_id=current_user.id,
        session_id=session_id,
        photos=session.photo_urls or [],
    )

    try:
        # Generate quote number
        from .quotes import generate_quote_number
        quote_number = generate_quote_number(db)

        # Create Quote record
        quote = models.Quote(
            quote_number=quote_number,
            job_type=session.job_type,
            user_id=current_user.id,
            session_id=session_id,
            inputs_json=quote_params,
            outputs_json=priced_quote,
            selected_markup_pct=priced_quote.get("selected_markup_pct", 15),
            subtotal=priced_quote.get("subtotal", 0),
            total=priced_quote.get("total", 0),
            project_description=fields.get("description", ""),
        )
        db.add(quote)
        db.flush()

        # Update priced_quote with the quote_id
        priced_quote["quote_id"] = quote.id
        quote.outputs_json = priced_quote

        # Transition session to output stage
        session.stage = "output"
        session.status = "complete"
        session.updated_at = datetime.utcnow()
        flag_modified(session, "params_json")
        db.commit()

        return {
            "session_id": session_id,
            "quote_id": quote.id,
            "quote_number": quote_number,
            "priced_quote": priced_quote,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Quote creation failed: {str(e)}. Session is intact — retry /price.",
        )


def _serialize_questions(questions: list[dict]) -> list[dict]:
    """Serialize question dicts for API response (strip internal-only fields)."""
    return [
        {
            "id": q["id"],
            "text": q["text"],
            "type": q["type"],
            "required": q.get("required", False),
            "hint": q.get("hint"),
            "options": q.get("options"),
            "unit": q.get("unit"),
        }
        for q in questions
    ]
