"""
Quote Session API — conversation flow for the 6-stage pipeline.

POST /api/session/start        — Start a new quote session from a description
POST /api/session/{id}/answer  — Submit answers, get next questions
GET  /api/session/{id}/status  — Current state of a session
POST /api/session/{id}/calculate — Run Stage 3 calculator on completed session
POST /api/session/{id}/estimate  — Run Stage 4 labor estimator on calculated session
POST /api/session/{id}/price     — Run Stage 5 pricing engine, create Quote record
"""

import logging
import threading
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from .auth import check_quote_access
from ..database import get_db
from ..claude_client import is_configured as ai_is_configured
from ..question_trees.engine import QuestionTreeEngine, detect_job_type
from ..question_trees.universal_intake import (
    generate_intake_questions,
    generate_followup_questions,
    build_completion_from_readiness,
    build_extracted_fields_from_known,
)
from ..calculators.registry import get_calculator, has_calculator
from ..knowledge.validation import (
    build_instructions_to_text,
    check_banned_terms,
    validate_full_output,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["quote-session"])

# Engine kept for detect_job_type, get_quote_params, and legacy methods
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


class CustomerInfoRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None


# --- Endpoints ---

@router.post("/start")
def start_session(
    request: StartSessionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_quote_access),
):
    """
    Start a new quote session using Universal Intake.

    Returns immediately with session_id + status="processing".
    AI intake runs in a background thread to avoid Railway's 30s proxy timeout.
    Frontend polls GET /session/{id}/status until status="active".
    """
    logger.info("/start called: desc_len=%d, photo_urls=%s",
                len(request.description), request.photo_urls or request.photos)

    # --- Step 1: Detect job type (fast keyword match, no AI) ---
    if request.job_type:
        job_type = request.job_type
        detection_confidence = 1.0
        ambiguous = False
    else:
        detection = detect_job_type(request.description)
        job_type = detection.get("job_type", "custom_fab")
        detection_confidence = detection.get("confidence", 0.0)
        ambiguous = detection.get("ambiguous", True)

    photo_urls = list(request.photo_urls or request.photos or [])

    # --- Decide: sync (instant fallback) vs async (real AI, needs background) ---
    use_async = ai_is_configured()

    if use_async:
        # --- ASYNC PATH: return immediately, AI runs in background ---
        session_id = str(uuid.uuid4())
        params_for_storage = {
            "description": request.description,
            "_known_facts": {},
            "_qa_history": [],
            "_readiness": "needs_questions",
        }
        initial_messages = [{
            "role": "user",
            "content": request.description,
            "timestamp": datetime.utcnow().isoformat(),
        }]

        session = models.QuoteSession(
            id=session_id,
            user_id=current_user.id,
            job_type=job_type,
            stage="intake",
            params_json=params_for_storage,
            messages_json=initial_messages,
            photo_urls=photo_urls,
            status="processing",
        )
        db.add(session)
        db.commit()

        _run_intake_background(
            session_id=session_id,
            description=request.description,
            job_type=job_type,
            photo_urls=photo_urls,
        )

        logger.info("SESSION START (async): session=%s, job_type=%s", session_id, job_type)

        return {
            "session_id": session_id,
            "job_type": job_type,
            "detection_confidence": detection_confidence,
            "ambiguous": ambiguous,
            "status": "processing",
        }

    # --- SYNC PATH: no AI configured, fallback is instant ---
    return _start_session_sync(
        request, job_type, detection_confidence, ambiguous,
        photo_urls, db, current_user,
    )


def _start_session_sync(request, job_type, detection_confidence, ambiguous,
                        photo_urls, db, current_user):
    """Original synchronous intake — used when AI is not configured (instant fallback)."""
    # Photo extraction (will no-op without AI key)
    photo_observations = ""
    photo_extracted_fields = {}
    if photo_urls:
        try:
            photo_result = engine.extract_from_photos(
                job_type, photo_urls, request.description
            )
            photo_observations = photo_result.get("photo_observations", "")
            photo_extracted_fields = photo_result.get("extracted_fields", {})
        except Exception as e:
            logger.error("Photo extraction failed: %s: %s", type(e).__name__, e)

    # Universal Intake (will use fallback questions without AI)
    intake_result = generate_intake_questions(
        description=request.description,
        photo_observations=photo_observations,
    )

    known_facts = intake_result.get("known_facts", {})
    questions = intake_result.get("questions", [])
    readiness = intake_result.get("readiness", "needs_questions")

    for k, v in photo_extracted_fields.items():
        if k not in known_facts:
            known_facts[k] = v

    extracted_fields = build_extracted_fields_from_known(known_facts)
    completion = build_completion_from_readiness(readiness, known_facts, questions)

    session_id = str(uuid.uuid4())
    params_for_storage = dict(known_facts)
    params_for_storage["description"] = request.description
    if photo_observations:
        params_for_storage["photo_observations"] = photo_observations
    params_for_storage["_known_facts"] = known_facts
    params_for_storage["_qa_history"] = []
    params_for_storage["_readiness"] = readiness

    initial_messages = [{
        "role": "user",
        "content": request.description,
        "timestamp": datetime.utcnow().isoformat(),
    }]
    if questions:
        initial_messages.append({
            "role": "ai_questions",
            "content": questions,
            "timestamp": datetime.utcnow().isoformat(),
        })

    session = models.QuoteSession(
        id=session_id,
        user_id=current_user.id,
        job_type=job_type,
        stage="clarify" if questions else "calculate",
        params_json=params_for_storage,
        messages_json=initial_messages,
        photo_urls=photo_urls,
        status="active",
    )
    db.add(session)
    db.commit()

    logger.info(
        "SESSION START (sync): job_type=%s, known=%d, questions=%d, readiness=%s",
        job_type, len(known_facts), len(questions), readiness,
    )

    return {
        "session_id": session_id,
        "job_type": job_type,
        "detection_confidence": detection_confidence,
        "ambiguous": ambiguous,
        "tree_loaded": True,
        "extracted_fields": extracted_fields,
        "photo_extracted_fields": photo_extracted_fields,
        "photo_observations": photo_observations,
        "next_questions": _serialize_questions(questions),
        "completion": completion,
    }


def _run_intake_background(session_id, description, job_type, photo_urls):
    """Spawn a daemon thread to run AI intake and update the session."""

    def _worker():
        from ..database import SessionLocal
        bg_db = SessionLocal()
        try:
            # --- Photo extraction (if photos) ---
            photo_observations = ""
            photo_extracted_fields = {}
            if photo_urls:
                try:
                    photo_result = engine.extract_from_photos(
                        job_type, photo_urls, description
                    )
                    photo_observations = photo_result.get("photo_observations", "")
                    photo_extracted_fields = photo_result.get("extracted_fields", {})
                except Exception as e:
                    logger.error("BG photo extraction failed: %s: %s",
                                 type(e).__name__, e)

            # --- Universal Intake AI call ---
            intake_result = generate_intake_questions(
                description=description,
                photo_observations=photo_observations,
            )

            known_facts = intake_result.get("known_facts", {})
            questions = intake_result.get("questions", [])
            readiness = intake_result.get("readiness", "needs_questions")

            # Merge photo-extracted fields (AI text wins on conflict)
            for k, v in photo_extracted_fields.items():
                if k not in known_facts:
                    known_facts[k] = v

            # Build storage
            params_for_storage = dict(known_facts)
            params_for_storage["description"] = description
            if photo_observations:
                params_for_storage["photo_observations"] = photo_observations
            params_for_storage["_known_facts"] = known_facts
            params_for_storage["_qa_history"] = []
            params_for_storage["_readiness"] = readiness

            messages = [{
                "role": "user",
                "content": description,
                "timestamp": datetime.utcnow().isoformat(),
            }]
            if questions:
                messages.append({
                    "role": "ai_questions",
                    "content": questions,
                    "timestamp": datetime.utcnow().isoformat(),
                })

            # Build frontend-compatible shapes and store them for the status endpoint
            extracted_fields = build_extracted_fields_from_known(known_facts)
            completion = build_completion_from_readiness(readiness, known_facts, questions)

            # Update session in DB
            session = bg_db.query(models.QuoteSession).filter(
                models.QuoteSession.id == session_id,
            ).first()
            if session:
                session.params_json = params_for_storage
                session.messages_json = messages
                session.stage = "clarify" if questions else "calculate"
                session.status = "active"
                bg_db.commit()
                logger.info(
                    "BG INTAKE DONE: session=%s, known=%d, questions=%d, readiness=%s",
                    session_id, len(known_facts), len(questions), readiness,
                )
            else:
                logger.error("BG intake: session %s not found in DB", session_id)

        except Exception as e:
            logger.error("BG intake failed for session %s: %s: %s",
                         session_id, type(e).__name__, e)
            # Mark session as failed so frontend can show error
            try:
                session = bg_db.query(models.QuoteSession).filter(
                    models.QuoteSession.id == session_id,
                ).first()
                if session:
                    session.status = "error"
                    bg_db.commit()
            except Exception:
                pass
        finally:
            bg_db.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


@router.post("/{session_id}/answer")
def answer_questions(
    session_id: str,
    request: AnswerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Submit answers to questions. Uses Universal Intake AI to generate
    follow-up questions based on accumulated Q&A history.
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

    # Merge new answers into existing params
    current_params = dict(session.params_json or {})
    current_params.update(request.answers)

    # Retrieve intake state
    known_facts = dict(current_params.get("_known_facts", {}))
    qa_history = list(current_params.get("_qa_history", []))
    description = current_params.get("description", "")
    photo_observations_text = current_params.get("photo_observations", "")

    # Merge new answers into known facts
    for field_id, value in request.answers.items():
        if not str(field_id).startswith("_"):
            known_facts[field_id] = value

    # Build QA history entries from the answers
    # Match answer values to the questions that were asked
    messages = list(session.messages_json or [])
    last_questions = []
    for msg in reversed(messages):
        if msg.get("role") == "ai_questions":
            last_questions = msg.get("content", [])
            break

    for field_id, value in request.answers.items():
        q_text = field_id  # default
        for q in last_questions:
            if isinstance(q, dict) and q.get("id") == field_id:
                q_text = q.get("text", field_id)
                break
        qa_history.append({"question": q_text, "answer": str(value)})

    # Handle photo answer if provided
    photo_extracted_fields = {}
    if request.photo_url:
        current_photos = list(session.photo_urls or [])
        current_photos.append(request.photo_url)
        session.photo_urls = current_photos

        try:
            photo_result = engine.extract_from_photo(
                session.job_type, request.photo_url,
                description=description,
            )
            new_photo_obs = photo_result.get("photo_observations", "")
            if new_photo_obs:
                photo_observations_text = (
                    (photo_observations_text + "\n" + new_photo_obs).strip()
                )
            for field_id, value in photo_result.get("extracted_fields", {}).items():
                if field_id not in known_facts:
                    known_facts[field_id] = value
                    photo_extracted_fields[field_id] = value
        except Exception as e:
            logger.error("Photo extraction failed in /answer: %s: %s",
                         type(e).__name__, e)

    # --- Universal Intake followup AI call ---
    followup_result = generate_followup_questions(
        description=description,
        known_facts=known_facts,
        qa_history=qa_history,
        photo_observations=photo_observations_text,
    )

    # Update known facts from AI response (AI may have merged/refined)
    ai_known = followup_result.get("known_facts", {})
    if ai_known:
        known_facts.update(ai_known)

    questions = followup_result.get("questions", [])
    readiness = followup_result.get("readiness", "ready")

    # Build completion
    completion = build_completion_from_readiness(readiness, known_facts, questions)

    # Log answers in message history
    messages.append({
        "role": "user_answers",
        "content": request.answers,
        "timestamp": datetime.utcnow().isoformat(),
    })
    # Store questions for next QA matching
    if questions:
        messages.append({
            "role": "ai_questions",
            "content": questions,
            "timestamp": datetime.utcnow().isoformat(),
        })

    # Update session state
    from sqlalchemy.orm.attributes import flag_modified
    current_params.update({k: v for k, v in known_facts.items()
                           if not str(k).startswith("_")})
    current_params["_known_facts"] = known_facts
    current_params["_qa_history"] = qa_history
    current_params["_readiness"] = readiness
    if photo_observations_text:
        current_params["photo_observations"] = photo_observations_text

    session.params_json = current_params
    session.messages_json = messages
    session.updated_at = datetime.utcnow()
    flag_modified(session, "params_json")
    flag_modified(session, "messages_json")
    flag_modified(session, "photo_urls")

    if completion["is_complete"]:
        session.stage = "calculate"

    db.commit()

    logger.info(
        "ANSWER (universal): session=%s, %d new answers, %d known, %d followup qs, readiness=%s",
        session_id, len(request.answers), len(known_facts), len(questions), readiness,
    )

    response = {
        "session_id": session_id,
        "answered_count": len(known_facts),
        "required_total": completion["required_total"],
        "next_questions": _serialize_questions(questions),
        "is_complete": completion["is_complete"],
        "completion": completion,
    }

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
    Frontend polls this after /start returns status="processing".
    """
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    # If still processing, return minimal status for polling
    if session.status == "processing":
        return {
            "session_id": session_id,
            "job_type": session.job_type,
            "stage": session.stage,
            "status": "processing",
            "pipeline_stage": session.stage,
        }

    current_params = dict(session.params_json or {})

    # Universal intake: use stored readiness state
    known_facts = current_params.get("_known_facts", {})
    readiness = current_params.get("_readiness", "needs_questions")

    # Retrieve questions from messages_json (stored by background intake)
    questions = []
    for msg in (session.messages_json or []):
        if msg.get("role") == "ai_questions":
            questions = msg.get("content", [])
            break

    completion = build_completion_from_readiness(readiness, known_facts, questions)
    # Answered fields = everything except internal keys
    answered_fields = {k: v for k, v in current_params.items()
                       if not str(k).startswith("_")}
    extracted_fields = build_extracted_fields_from_known(known_facts)

    # Photo data
    photo_observations = current_params.get("photo_observations", "")
    photo_extracted_fields = {k: v for k, v in current_params.items()
                              if k.startswith("photo_") and k != "photo_observations"}

    response = {
        "session_id": session_id,
        "job_type": session.job_type,
        "stage": session.stage,
        "status": session.status,
        "answered_fields": answered_fields,
        "extracted_fields": extracted_fields,
        "photo_extracted_fields": photo_extracted_fields,
        "photo_observations": photo_observations,
        "next_questions": _serialize_questions(questions),
        "completion": completion,
        "photo_urls": session.photo_urls or [],
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }

    # P71: Include quote data when pipeline is complete (for async polling)
    if session.stage == "output" and session.status == "complete":
        quote = db.query(models.Quote).filter(
            models.Quote.session_id == session_id,
        ).first()
        if quote:
            response["quote_id"] = quote.id
            response["quote_number"] = quote.quote_number
            response["priced_quote"] = quote.outputs_json

    # P71: Include stage error for failed pipeline stages
    stage_error = current_params.get("_stage_error")
    if stage_error:
        response["stage_error"] = stage_error

    return response


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
    current_params = dict(session.params_json or {})

    # Universal intake: check AI readiness state (not tree completion)
    readiness = current_params.get("_readiness", "ready")
    if readiness == "needs_critical_info":
        raise HTTPException(
            status_code=400,
            detail="Session is missing critical information. Answer more questions first.",
        )

    # Check calculator exists
    if not has_calculator(job_type):
        raise HTTPException(
            status_code=404,
            detail=f"No calculator registered for job type: {job_type}",
        )

    # P71: Async path — return immediately, run calculator in background thread
    use_async = ai_is_configured()
    if use_async:
        session.status = "processing"
        session.stage = "calculate"
        session.updated_at = datetime.utcnow()
        db.commit()
        _run_calculate_background(session_id, current_user.id)
        return {"session_id": session_id, "status": "processing", "stage": "calculate"}

    # --- Sync path (tests / no API key) ---
    # Inject shop equipment context into params for AI prompts
    from ..shop_context import build_shop_context_block
    shop_ctx = build_shop_context_block(current_user.id, db)
    if shop_ctx:
        current_params["_shop_context"] = shop_ctx

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


def _run_calculate_background(session_id, user_id):
    """P71: Spawn a daemon thread to run Stage 3 calculator in background."""

    def _worker():
        from ..database import SessionLocal
        from ..shop_context import build_shop_context_block
        from sqlalchemy.orm.attributes import flag_modified
        bg_db = SessionLocal()
        try:
            session = bg_db.query(models.QuoteSession).filter(
                models.QuoteSession.id == session_id,
            ).first()
            if not session:
                logger.error("BG calculate: session %s not found", session_id)
                return

            user = bg_db.query(models.User).filter(
                models.User.id == user_id,
            ).first()

            current_params = dict(session.params_json or {})
            job_type = session.job_type

            # Inject shop context
            if user:
                shop_ctx = build_shop_context_block(user.id, bg_db)
                if shop_ctx:
                    current_params["_shop_context"] = shop_ctx

            # Run calculator
            calculator = get_calculator(job_type)
            material_list = calculator.calculate(current_params)

            # Store results
            current_params["_material_list"] = material_list
            current_params.pop("_stage_error", None)
            session.params_json = current_params
            session.stage = "estimate"
            session.status = "active"
            session.updated_at = datetime.utcnow()
            flag_modified(session, "params_json")
            bg_db.commit()

            logger.info("BG CALCULATE DONE: session=%s, job_type=%s", session_id, job_type)

        except Exception as e:
            logger.error("BG calculate failed for session %s: %s: %s",
                         session_id, type(e).__name__, e)
            try:
                session = bg_db.query(models.QuoteSession).filter(
                    models.QuoteSession.id == session_id,
                ).first()
                if session:
                    params = dict(session.params_json or {})
                    params["_stage_error"] = "Calculate failed: %s" % str(e)
                    session.params_json = params
                    session.status = "error"
                    flag_modified(session, "params_json")
                    bg_db.commit()
            except Exception:
                pass
        finally:
            bg_db.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


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

    # --- Full package shortcut ---
    # If Opus full package provided labor + build + finishing in Stage 3,
    # use them directly and skip the separate AI calls.
    if material_list.get("_opus_labor_hours"):
        return _estimate_from_opus_package(
            session, current_params, material_list, current_user, db,
        )

    # P71: Async path — return immediately, run estimation in background thread
    use_async = ai_is_configured()
    if use_async:
        session.status = "processing"
        # stage is already "estimate" from calculate
        session.updated_at = datetime.utcnow()
        db.commit()
        _run_estimate_background(session_id, current_user.id)
        return {"session_id": session_id, "status": "processing", "stage": "estimate"}

    # --- Sync path (tests / no API key) ---
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
    finish_type = fields.get("finish", fields.get("finish_type", ""))
    finish_source = "user_answer" if finish_type else "default"

    # Fallback: extract finish from description if field is missing
    if not finish_type:
        desc_lower = str(fields.get("description", "")).lower()
        if "powder" in desc_lower and "coat" in desc_lower:
            finish_type = "powder_coat"
            finish_source = "description_extraction"
        elif "clear coat" in desc_lower or "clearcoat" in desc_lower:
            finish_type = "clearcoat"
            finish_source = "description_extraction"
        elif "paint" in desc_lower and "powder" not in desc_lower:
            finish_type = "paint"
            finish_source = "description_extraction"
        elif "galvaniz" in desc_lower:
            finish_type = "galvanized"
            finish_source = "description_extraction"
        elif "anodiz" in desc_lower:
            finish_type = "anodized"
            finish_source = "description_extraction"
        elif "patina" in desc_lower or "blacken" in desc_lower:
            finish_type = "patina"
            finish_source = "description_extraction"
        elif "brush" in desc_lower or "polish" in desc_lower:
            finish_type = "brushed"
            finish_source = "description_extraction"
        else:
            finish_type = "raw"

    logger.info(
        "ESTIMATE: job_type=%s, finish=%s, finish_source=%s",
        session.job_type, finish_type, finish_source,
    )

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
    except Exception as est_err:
        logger.warning("Labor estimation failed, using fallback: %s", est_err)

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

    # Generate build instructions — ALWAYS attempted, independent of labor estimation
    build_instructions = None
    build_instructions_error = None
    try:
        from ..calculators.ai_cut_list import AICutListGenerator
        ai_gen = AICutListGenerator()

        # Build enforced dimensions for the build instructions prompt
        build_fields = {k: v for k, v in current_params.items()
                        if not k.startswith("_")}
        # Pass shop context through to AI prompt
        if current_params.get("_shop_context"):
            build_fields["_shop_context"] = current_params["_shop_context"]
        enforced_dims = None
        if session.job_type == "cantilever_gate":
            enforced_dims = {}
            cw = build_fields.get("clear_width", "")
            ht = build_fields.get("height", "")
            if cw:
                try:
                    cw_val = float(str(cw).split()[0])
                    enforced_dims["opening_width"] = "%s ft" % cw
                    enforced_dims["gate_length"] = "%.1f ft (opening x 1.5)" % (cw_val * 1.5)
                    enforced_dims["post_spacing"] = "%s ft (matches opening width)" % cw
                    enforced_dims["post_embed_depth"] = "42 inches (Chicago frost line)"
                except (ValueError, IndexError):
                    pass
            if ht:
                try:
                    ht_val = float(str(ht).split()[0])
                    enforced_dims["gate_height"] = "%s ft (%.0f inches)" % (ht, ht_val * 12)
                except (ValueError, IndexError):
                    pass

        # Use detailed cut list (per-piece), NOT consolidated items (per-profile).
        # The build instructions prompt needs actual pieces ("Frame leg, 30in, qty 4")
        # not profile summaries ("sq_tube_2x2_11ga — 48.5 ft").
        detailed_cuts = material_list.get("cut_list", material_list.get("items", []))
        logger.info("BUILD INSTRUCTIONS: starting generation for %s with %d cut items",
                    session.job_type, len(detailed_cuts))
        build_instructions = ai_gen.generate_build_instructions(
            session.job_type,
            build_fields,
            detailed_cuts,
            enforced_dimensions=enforced_dims,
        )
        if build_instructions:
            logger.info("BUILD INSTRUCTIONS: generated %d steps", len(build_instructions))
        else:
            logger.warning("BUILD INSTRUCTIONS: returned None — AI may be unconfigured or call failed")
            build_instructions_error = "AI returned empty response"
    except Exception as bi_err:
        logger.warning("Build instructions generation failed: %s", bi_err, exc_info=True)
        build_instructions_error = str(bi_err)

    # Store all results in session
    current_params["_labor_estimate"] = labor_estimate
    current_params["_finishing"] = finishing
    if build_instructions:
        current_params["_build_instructions"] = build_instructions
        current_params.pop("_build_instructions_error", None)
    else:
        current_params["_build_instructions_error"] = build_instructions_error or "generation failed"
    # Store detailed cut list from material items
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
        "build_instructions_status": "ok (%d steps)" % len(build_instructions) if build_instructions else "FAILED — check logs",
    }


def _run_estimate_background(session_id, user_id):
    """P71: Spawn a daemon thread to run Stage 4 labor estimation in background."""

    def _worker():
        from ..database import SessionLocal
        from ..labor_estimator import LaborEstimator
        from ..historical_validator import HistoricalValidator
        from ..finishing import FinishingBuilder
        from ..calculators.ai_cut_list import AICutListGenerator
        from sqlalchemy.orm.attributes import flag_modified
        bg_db = SessionLocal()
        try:
            session = bg_db.query(models.QuoteSession).filter(
                models.QuoteSession.id == session_id,
            ).first()
            if not session:
                logger.error("BG estimate: session %s not found", session_id)
                return

            user = bg_db.query(models.User).filter(
                models.User.id == user_id,
            ).first()

            current_params = dict(session.params_json or {})
            material_list = current_params.get("_material_list", {})

            # Build QuoteParams for the estimator
            quote_params = engine.get_quote_params(
                job_type=session.job_type,
                answered_fields={k: v for k, v in current_params.items()
                                 if not k.startswith("_")},
                user_id=user_id,
                session_id=session_id,
                photos=session.photo_urls or [],
            )

            # Get user rates
            user_rates = {
                "rate_inshop": (user.rate_inshop if user else None) or 125.00,
                "rate_onsite": (user.rate_onsite if user else None) or 145.00,
            }

            estimator = LaborEstimator()
            fields = quote_params.get("fields", {})
            finish_type = fields.get("finish", fields.get("finish_type", ""))

            # Fallback: extract finish from description if field is missing
            if not finish_type:
                desc_lower = str(fields.get("description", "")).lower()
                if "powder" in desc_lower and "coat" in desc_lower:
                    finish_type = "powder_coat"
                elif "clear coat" in desc_lower or "clearcoat" in desc_lower:
                    finish_type = "clearcoat"
                elif "paint" in desc_lower and "powder" not in desc_lower:
                    finish_type = "paint"
                elif "galvaniz" in desc_lower:
                    finish_type = "galvanized"
                elif "anodiz" in desc_lower:
                    finish_type = "anodized"
                elif "patina" in desc_lower or "blacken" in desc_lower:
                    finish_type = "patina"
                elif "brush" in desc_lower or "polish" in desc_lower:
                    finish_type = "brushed"
                else:
                    finish_type = "raw"

            logger.info("BG ESTIMATE: job_type=%s, finish=%s", session.job_type, finish_type)

            try:
                labor_estimate = estimator.estimate(material_list, quote_params, user_rates)
                validator = HistoricalValidator()
                labor_estimate = validator.validate(labor_estimate, session.job_type, bg_db)
                finishing_builder = FinishingBuilder()
                finishing = finishing_builder.build(
                    finish_type=finish_type,
                    total_sq_ft=material_list.get("total_sq_ft", 0),
                    labor_processes=labor_estimate.get("processes", []),
                )
            except Exception as est_err:
                logger.warning("BG estimate: Labor estimation failed, using fallback: %s", est_err)
                labor_estimate = estimator._fallback_estimate(
                    material_list, quote_params, user_rates)
                finishing_builder = FinishingBuilder()
                finishing = finishing_builder.build(
                    finish_type=finish_type,
                    total_sq_ft=material_list.get("total_sq_ft", 0),
                    labor_processes=labor_estimate.get("processes", []),
                )

            # Generate build instructions
            build_instructions = None
            build_instructions_error = None
            try:
                ai_gen = AICutListGenerator()
                build_fields = {k: v for k, v in current_params.items()
                                if not k.startswith("_")}
                if current_params.get("_shop_context"):
                    build_fields["_shop_context"] = current_params["_shop_context"]
                enforced_dims = None
                if session.job_type == "cantilever_gate":
                    enforced_dims = {}
                    cw = build_fields.get("clear_width", "")
                    ht = build_fields.get("height", "")
                    if cw:
                        try:
                            cw_val = float(str(cw).split()[0])
                            enforced_dims["opening_width"] = "%s ft" % cw
                            enforced_dims["gate_length"] = "%.1f ft (opening x 1.5)" % (cw_val * 1.5)
                            enforced_dims["post_spacing"] = "%s ft (matches opening width)" % cw
                            enforced_dims["post_embed_depth"] = "42 inches (Chicago frost line)"
                        except (ValueError, IndexError):
                            pass
                    if ht:
                        try:
                            ht_val = float(str(ht).split()[0])
                            enforced_dims["gate_height"] = "%s ft (%.0f inches)" % (ht, ht_val * 12)
                        except (ValueError, IndexError):
                            pass

                detailed_cuts = material_list.get("cut_list", material_list.get("items", []))
                build_instructions = ai_gen.generate_build_instructions(
                    session.job_type,
                    build_fields,
                    detailed_cuts,
                    enforced_dimensions=enforced_dims,
                )
                if not build_instructions:
                    build_instructions_error = "AI returned empty response"
            except Exception as bi_err:
                logger.warning("BG estimate: Build instructions failed: %s", bi_err)
                build_instructions_error = str(bi_err)

            # Store all results in session
            current_params["_labor_estimate"] = labor_estimate
            current_params["_finishing"] = finishing
            if build_instructions:
                current_params["_build_instructions"] = build_instructions
                current_params.pop("_build_instructions_error", None)
            else:
                current_params["_build_instructions_error"] = (
                    build_instructions_error or "generation failed"
                )
            current_params["_detailed_cut_list"] = material_list.get(
                "cut_list", material_list.get("items", []))
            current_params.pop("_stage_error", None)
            session.params_json = current_params
            session.stage = "price"
            session.status = "active"
            session.updated_at = datetime.utcnow()
            flag_modified(session, "params_json")
            bg_db.commit()

            logger.info("BG ESTIMATE DONE: session=%s, job_type=%s", session_id, session.job_type)

        except Exception as e:
            logger.error("BG estimate failed for session %s: %s: %s",
                         session_id, type(e).__name__, e)
            try:
                session = bg_db.query(models.QuoteSession).filter(
                    models.QuoteSession.id == session_id,
                ).first()
                if session:
                    params = dict(session.params_json or {})
                    params["_stage_error"] = "Estimate failed: %s" % str(e)
                    session.params_json = params
                    session.status = "error"
                    flag_modified(session, "params_json")
                    bg_db.commit()
            except Exception:
                pass
        finally:
            bg_db.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


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

    # P71: Async path — return immediately, run pricing in background thread
    use_async = ai_is_configured()
    if use_async:
        session.status = "processing"
        # stage is already "price" from estimate
        session.updated_at = datetime.utcnow()
        db.commit()
        _run_price_background(session_id, current_user.id)
        return {"session_id": session_id, "status": "processing", "stage": "price"}

    # --- Sync path (tests / no API key) ---
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

    # Pass build instructions error flag so frontend can show retry button
    bi_error = current_params.get("_build_instructions_error")
    if bi_error and not priced_quote.get("build_instructions"):
        priced_quote["_build_instructions_error"] = bi_error

    # --- Validation layer: catch AI hallucinations before PDF ---
    try:
        build_text = build_instructions_to_text(
            current_params.get("_build_instructions", [])
        )

        # Check banned terms on specific contexts
        validation_warnings = []
        for context in ("vinegar_bath_cleanup", "decorative_stock_prep",
                        "decorative_assembly"):
            found = check_banned_terms(build_text, context)
            for term in found:
                validation_warnings.append(
                    "[ERROR] Banned term '%s' found in build instructions (context: %s)"
                    % (term, context)
                )

        # Full output validation
        vr = validate_full_output(
            job_type=session.job_type,
            cut_list_items=current_params.get("_detailed_cut_list", []),
            labor_processes=current_params.get("_labor_estimate", {}).get("processes", []),
            build_instructions=build_text,
            dimensions={k: v for k, v in fields.items()
                        if isinstance(v, (int, float))},
        )
        for msg in vr.errors:
            validation_warnings.append("[ERROR] %s" % msg)
        for msg in vr.warnings:
            validation_warnings.append("[WARNING] %s" % msg)
        for msg in vr.info:
            validation_warnings.append("[INFO] %s" % msg)

        if validation_warnings:
            priced_quote["validation_warnings"] = validation_warnings
            for w in validation_warnings:
                if w.startswith("[ERROR]") or w.startswith("[WARNING]"):
                    logger.warning("Quote validation: %s", w)
    except Exception:
        logger.exception("Validation layer failed — continuing without validation")

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
        # Increment quote counter for tier quota enforcement
        current_user.quotes_this_month = (current_user.quotes_this_month or 0) + 1

        flag_modified(session, "params_json")
        db.commit()

        # Auto-review disabled — adds latency for no value when Opus generates.
        # Use the manual POST /session/{id}/review endpoint if needed.

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


def _run_price_background(session_id, user_id):
    """P71: Spawn a daemon thread to run Stage 5 pricing in background."""

    def _worker():
        from ..database import SessionLocal
        from ..pricing_engine import PricingEngine
        from .quotes import generate_quote_number
        from sqlalchemy.orm.attributes import flag_modified
        bg_db = SessionLocal()
        try:
            session = bg_db.query(models.QuoteSession).filter(
                models.QuoteSession.id == session_id,
            ).first()
            if not session:
                logger.error("BG price: session %s not found", session_id)
                return

            user = bg_db.query(models.User).filter(
                models.User.id == user_id,
            ).first()

            current_params = dict(session.params_json or {})
            material_list = current_params.get("_material_list", {})
            labor_estimate = current_params.get("_labor_estimate", {})
            finishing = current_params.get("_finishing", {})

            # Build session_data for PricingEngine
            fields = {k: v for k, v in current_params.items()
                      if not k.startswith("_")}
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
                "id": user.id if user else user_id,
                "shop_name": user.shop_name if user else None,
                "markup_default": (user.markup_default if user else None) or 15,
                "rate_inshop": (user.rate_inshop if user else None) or 125.00,
                "rate_onsite": (user.rate_onsite if user else None) or 145.00,
            }

            # Run pricing engine
            pricing_engine = PricingEngine()
            priced_quote = pricing_engine.build_priced_quote(session_data, user_dict)

            # Pass build instructions error flag
            bi_error = current_params.get("_build_instructions_error")
            if bi_error and not priced_quote.get("build_instructions"):
                priced_quote["_build_instructions_error"] = bi_error

            # Validation layer
            try:
                build_text = build_instructions_to_text(
                    current_params.get("_build_instructions", [])
                )
                validation_warnings = []
                for context in ("vinegar_bath_cleanup", "decorative_stock_prep",
                                "decorative_assembly"):
                    found = check_banned_terms(build_text, context)
                    for term in found:
                        validation_warnings.append(
                            "[ERROR] Banned term '%s' found in build instructions (context: %s)"
                            % (term, context)
                        )
                vr = validate_full_output(
                    job_type=session.job_type,
                    cut_list_items=current_params.get("_detailed_cut_list", []),
                    labor_processes=current_params.get("_labor_estimate", {}).get("processes", []),
                    build_instructions=build_text,
                    dimensions={k: v for k, v in fields.items()
                                if isinstance(v, (int, float))},
                )
                for msg in vr.errors:
                    validation_warnings.append("[ERROR] %s" % msg)
                for msg in vr.warnings:
                    validation_warnings.append("[WARNING] %s" % msg)
                for msg in vr.info:
                    validation_warnings.append("[INFO] %s" % msg)
                if validation_warnings:
                    priced_quote["validation_warnings"] = validation_warnings
            except Exception:
                logger.exception("BG price: Validation layer failed")

            # Build QuoteParams snapshot (inputs)
            quote_params = engine.get_quote_params(
                job_type=session.job_type,
                answered_fields=fields,
                user_id=user_id,
                session_id=session_id,
                photos=session.photo_urls or [],
            )

            # Generate quote number and create Quote record
            quote_number = generate_quote_number(bg_db)
            quote = models.Quote(
                quote_number=quote_number,
                job_type=session.job_type,
                user_id=user_id,
                session_id=session_id,
                inputs_json=quote_params,
                outputs_json=priced_quote,
                selected_markup_pct=priced_quote.get("selected_markup_pct", 15),
                subtotal=priced_quote.get("subtotal", 0),
                total=priced_quote.get("total", 0),
                project_description=fields.get("description", ""),
            )
            bg_db.add(quote)
            bg_db.flush()

            priced_quote["quote_id"] = quote.id
            quote.outputs_json = priced_quote

            # Transition session
            session.stage = "output"
            session.status = "complete"
            session.updated_at = datetime.utcnow()
            # Increment quote counter
            if user:
                user.quotes_this_month = (user.quotes_this_month or 0) + 1

            current_params.pop("_stage_error", None)
            session.params_json = current_params
            flag_modified(session, "params_json")
            bg_db.commit()

            logger.info("BG PRICE DONE: session=%s, quote_id=%d, quote_number=%s",
                         session_id, quote.id, quote_number)

        except Exception as e:
            logger.error("BG price failed for session %s: %s: %s",
                         session_id, type(e).__name__, e)
            try:
                bg_db.rollback()
                session = bg_db.query(models.QuoteSession).filter(
                    models.QuoteSession.id == session_id,
                ).first()
                if session:
                    params = dict(session.params_json or {})
                    params["_stage_error"] = "Price failed: %s" % str(e)
                    session.params_json = params
                    session.status = "error"
                    flag_modified(session, "params_json")
                    bg_db.commit()
            except Exception:
                pass
        finally:
            bg_db.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


@router.post("/{session_id}/review")
def review_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Run Claude review on a priced session.

    Requires: session has been priced (stage == "output").
    Calls Claude API to review the quote for issues, warnings, and suggestions.
    Stores review in session params_json["_review"].
    """
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    if session.stage != "output":
        raise HTTPException(
            status_code=400,
            detail="Session stage is '%s', not 'output'. Run /price first." % session.stage,
        )

    current_params = dict(session.params_json or {})

    # Get the quote data — look for the Quote record linked to this session
    quote = db.query(models.Quote).filter(
        models.Quote.session_id == session_id,
    ).first()
    if not quote or not quote.outputs_json:
        raise HTTPException(
            status_code=400,
            detail="No priced quote found for this session.",
        )

    quote_data = dict(quote.outputs_json)
    fields = {k: v for k, v in current_params.items() if not k.startswith("_")}

    # Run review (lazy import — top-level import removed with auto-review)
    from ..claude_reviewer import review_quote
    review_result = review_quote(quote_data, fields)

    # Store review in session
    from sqlalchemy.orm.attributes import flag_modified
    current_params["_review"] = review_result
    session.params_json = current_params
    session.updated_at = datetime.utcnow()
    flag_modified(session, "params_json")
    db.commit()

    return {
        "session_id": session_id,
        "review": review_result,
    }


@router.post("/{session_id}/retry-build-instructions")
def retry_build_instructions(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Retry generating build instructions for a completed quote.

    Can be called any time after /estimate. Regenerates build instructions
    and updates both the session and the Quote record's outputs_json.
    """
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    current_params = dict(session.params_json or {})
    material_list = current_params.get("_material_list")
    if not material_list:
        raise HTTPException(status_code=400, detail="No material_list — run /calculate first.")

    from ..calculators.ai_cut_list import AICutListGenerator
    from sqlalchemy.orm.attributes import flag_modified

    ai_gen = AICutListGenerator()
    build_fields = {k: v for k, v in current_params.items() if not k.startswith("_")}

    # Build enforced dimensions (same logic as /estimate)
    enforced_dims = None
    if session.job_type == "cantilever_gate":
        enforced_dims = {}
        cw = build_fields.get("clear_width", "")
        ht = build_fields.get("height", "")
        if cw:
            try:
                cw_val = float(str(cw).split()[0])
                enforced_dims["opening_width"] = "%s ft" % cw
                enforced_dims["gate_length"] = "%.1f ft (opening x 1.5)" % (cw_val * 1.5)
                enforced_dims["post_spacing"] = "%s ft (matches opening width)" % cw
                enforced_dims["post_embed_depth"] = "42 inches (Chicago frost line)"
            except (ValueError, IndexError):
                pass
        if ht:
            try:
                ht_val = float(str(ht).split()[0])
                enforced_dims["gate_height"] = "%s ft (%.0f inches)" % (ht, ht_val * 12)
            except (ValueError, IndexError):
                pass

    detailed_cuts = material_list.get("cut_list", material_list.get("items", []))
    logger.info("RETRY BUILD INSTRUCTIONS: %s with %d cut items", session.job_type, len(detailed_cuts))

    try:
        build_instructions = ai_gen.generate_build_instructions(
            session.job_type,
            build_fields,
            detailed_cuts,
            enforced_dimensions=enforced_dims,
        )
    except Exception as e:
        logger.warning("Retry build instructions failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Build instructions generation failed: %s" % str(e),
        )

    if not build_instructions:
        raise HTTPException(
            status_code=500,
            detail="AI returned empty build instructions. Check ANTHROPIC_API_KEY on server.",
        )

    logger.info("RETRY BUILD INSTRUCTIONS: generated %d steps", len(build_instructions))

    # Store in session
    current_params["_build_instructions"] = build_instructions
    current_params.pop("_build_instructions_error", None)
    session.params_json = current_params
    session.updated_at = datetime.utcnow()
    flag_modified(session, "params_json")

    # Also update the Quote record if it exists
    quote = db.query(models.Quote).filter(
        models.Quote.session_id == session_id,
    ).first()
    if quote and quote.outputs_json:
        outputs = dict(quote.outputs_json)
        outputs["build_instructions"] = build_instructions
        outputs.pop("_build_instructions_error", None)
        quote.outputs_json = outputs
        quote.updated_at = datetime.utcnow()
        flag_modified(quote, "outputs_json")

    db.commit()

    return {
        "session_id": session_id,
        "build_instructions": build_instructions,
        "step_count": len(build_instructions),
    }


@router.patch("/{session_id}/customer")
def update_customer_info(
    session_id: str,
    request: CustomerInfoRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Update customer information for a quote session.

    Stores in session.params_json["_customer"].
    Also updates quote.outputs_json["_customer"] and client_name if Quote exists.
    """
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    from sqlalchemy.orm.attributes import flag_modified

    customer_data = {
        "name": request.name or "",
        "phone": request.phone or "",
        "email": request.email or "",
        "address": request.address or "",
    }

    # Store in session params
    current_params = dict(session.params_json or {})
    current_params["_customer"] = customer_data
    session.params_json = current_params
    session.updated_at = datetime.utcnow()
    flag_modified(session, "params_json")

    # Also update Quote record if it exists
    quote = db.query(models.Quote).filter(
        models.Quote.session_id == session_id,
    ).first()
    if quote and quote.outputs_json:
        outputs = dict(quote.outputs_json)
        outputs["_customer"] = customer_data
        outputs["client_name"] = customer_data.get("name", "")
        quote.outputs_json = outputs
        flag_modified(quote, "outputs_json")

    db.commit()

    return {
        "session_id": session_id,
        "customer": customer_data,
    }


def _estimate_from_opus_package(session, current_params, material_list, current_user, db):
    """
    Opus full package already provided labor, build instructions, and finishing.
    Format into standard shapes and store in session — skip separate AI calls.
    """
    from ..finishing import FinishingBuilder
    from sqlalchemy.orm.attributes import flag_modified

    opus_labor = material_list.get("_opus_labor_hours", {})
    opus_build = material_list.get("_opus_build_instructions")
    opus_finishing = material_list.get("_opus_finishing_method", "raw")

    rate_inshop = current_user.rate_inshop or 125.00
    rate_onsite = current_user.rate_onsite or 145.00

    processes = []
    for proc_name, entry in opus_labor.items():
        if isinstance(entry, dict):
            h = round(float(entry.get("hours", 0)), 2)
        else:
            h = round(float(entry or 0), 2)
        if h <= 0:
            continue
        rate = rate_onsite if proc_name == "site_install" else rate_inshop
        processes.append({
            "process": proc_name,
            "hours": h,
            "rate": rate,
            "notes": "Opus full package estimate",
        })

    labor_estimate = {
        "processes": processes,
        "total_hours": round(sum(p["hours"] for p in processes), 2),
        "flagged": False,
        "flag_reason": None,
    }
    total_labor_hours = labor_estimate["total_hours"]
    total_labor_cost = round(sum(p["hours"] * p["rate"] for p in processes), 2)

    # Finishing from Opus method
    fields = {k: v for k, v in current_params.items() if not k.startswith("_")}
    finish_field = fields.get("finish", fields.get("finish_type", ""))
    finish_method = opus_finishing or finish_field or "raw"
    finishing_builder = FinishingBuilder()
    finishing = finishing_builder.build(
        finish_type=finish_method,
        total_sq_ft=material_list.get("total_sq_ft", 0),
        labor_processes=processes,
    )

    # Store in session
    current_params["_labor_estimate"] = labor_estimate
    current_params["_finishing"] = finishing
    if opus_build:
        current_params["_build_instructions"] = opus_build
        current_params.pop("_build_instructions_error", None)
    else:
        current_params["_build_instructions_error"] = "not provided in full package"
    current_params["_detailed_cut_list"] = material_list.get(
        "cut_list", material_list.get("items", []))
    session.params_json = current_params
    session.stage = "price"
    session.updated_at = datetime.utcnow()
    flag_modified(session, "params_json")
    db.commit()

    logger.info(
        "ESTIMATE (Opus full package): job_type=%s, %d processes, %.1f total hours",
        session.job_type, len(processes), total_labor_hours,
    )

    return {
        "session_id": session.id,
        "labor_estimate": labor_estimate,
        "finishing": finishing,
        "total_labor_hours": total_labor_hours,
        "total_labor_cost": total_labor_cost,
        "build_instructions_status": (
            "ok (%d steps)" % len(opus_build) if opus_build
            else "not provided in full package"
        ),
    }


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
