"""
Universal Intake System — replaces 25 hardcoded question trees with a single
AI-driven intake loop.

Instead of routing through job-type-specific JSON trees, the AI reads the
customer's description (and photos), identifies what it knows, what it doesn't,
and generates project-specific questions ranked by impact on quote accuracy.

The frontend response shapes are IDENTICAL to the tree-based system:
  - next_questions: list of {id, text, type, required, hint, options, unit}
  - extracted_fields: dict of {field_id: value}
  - completion: {is_complete, required_total, required_answered, ...}
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..claude_client import call_deep, is_configured

logger = logging.getLogger(__name__)

# Directory where question tree JSON files live
_TREE_DATA_DIR = Path(__file__).parent / "data"


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

UNIVERSAL_INTAKE_PROMPT = """\
You are a quoting tool inside a metal fab shop. A fabricator just described a \
project{photo_clause}. Talk like a shop foreman — direct, practical, no fluff.

DESCRIPTION:
\"\"\"{description}\"\"\"
{photo_observations_block}
YOUR TASK — Do three things:

1. KNOWN FACTS: List every concrete, quotable fact from the description{photo_ref}.
   Format: a JSON object where keys are short snake_case field IDs and values
   are the extracted data. Examples:
     "clear_width": "10"
     "height": "6"
     "material": "mild steel"
     "finish": "powder coat black"
     "has_motor": "yes"
     "quantity": "2"
   RULES:
   - ONLY extract facts the customer EXPLICITLY stated.
   - Do NOT infer, assume, or guess. "aluminum" does NOT mean "6061-T6".
   - Measurements: extract as numbers in standard units (feet for large dims, inches for small).
   - If uncertain, OMIT. A missing field triggers a question. A wrong field produces a wrong quote.

2. QUESTIONS: Generate 5-10 questions ranked by impact on quote accuracy.
   Each question targets information that would change the quote by >5% if wrong.

   MANDATORY CATEGORIES (ask if not already known):
   - Overall dimensions (length, width, height) of every component
   - Material type and thickness/gauge
   - Finish method (powder coat, paint, galvanized, raw, etc.)
   - Installation scope (shop pickup, delivery only, full install)
   - Indoor vs outdoor use
   - Quantity
   - Internal structure/frame approach (e.g., tube frame vs angle iron, welded vs bolted)

   QUESTION FORMAT — each question is a JSON object:
   {{
     "id": "snake_case_field_id",
     "text": "Clear, specific question text?",
     "type": "choice" | "measurement" | "text" | "number",
     "options": ["Option 1", "Option 2", ...],  // only for choice type
     "unit": "feet",  // only for measurement type
     "required": true | false,
     "hint": "Why this matters for the quote"
   }}

   RULES FOR QUESTIONS:
   - Do NOT ask about things already stated in the description.
   - Do NOT ask about standard fabrication practices (weld sequence, joint prep, etc.).
   - DO ask about design PREFERENCES where multiple valid approaches exist.
   - For choice questions, provide 2-5 practical real-world options.
   - Every question must materially affect materials, labor, or pricing.
   - Put the most impactful questions first.

   TONE AND VOICE:
   - Talk like a shop foreman — direct, practical, no corporate fluff.
   - Use industry terms: "tube", "flat bar", "11ga", not "rectangular hollow section".
   - Questions should sound like a fabricator asking another fabricator.
   - Bad: "What type of metallic material would you prefer for this construction?"
   - Good: "What material? Mild steel, stainless, or aluminum?"

3. READINESS: Evaluate whether you have enough info to generate a quote
   within ±15% of reality.
   - "ready": All critical dimensions, material, finish, and scope are known.
   - "needs_questions": Missing info that would swing the quote >15%.
   - "needs_critical_info": Missing fundamental info (no dimensions at all, unclear what the project even is).

Return ONLY valid JSON:
{{
  "known_facts": {{"field_id": "value", ...}},
  "questions": [{{question objects}}],
  "readiness": "ready" | "needs_questions" | "needs_critical_info",
  "readiness_reason": "brief explanation"
}}"""


FOLLOWUP_PROMPT = """\
You are a quoting tool inside a metal fab shop. A fabricator is describing a \
project and you are gathering the details needed to build an accurate quote. \
Talk like a shop foreman — direct, practical, no fluff.

ORIGINAL DESCRIPTION:
\"\"\"{description}\"\"\"
{photo_observations_block}
WHAT WE ALREADY KNOW:
{known_facts_block}

Q&A HISTORY:
{qa_history_block}

YOUR TASK — Based on the new answers above, do three things:

1. UPDATED KNOWN FACTS: Return ALL known facts (previous + newly answered).
   Merge the new answers into the existing facts. Use the same snake_case field IDs.

2. FOLLOW-UP QUESTIONS: Generate 0-10 additional questions if needed.
   - Do NOT re-ask anything already answered.
   - Only ask if the answer would change the quote by >5%.
   - Consider whether the new answers reveal sub-questions (e.g., if they chose
     "powder coat", ask about color; if "full install", ask about site conditions).
   - For multi-component projects, each component needs its own dimensions and specs.
   - Return an empty array [] if no more questions are needed.
   - MANDATORY CATEGORIES to cover (ask if not yet known): dimensions, material/gauge,
     finish, installation scope, indoor/outdoor, quantity, internal structure/frame approach.

3. READINESS: Re-evaluate. With the new answers, can you generate a quote
   within ±15% of reality?

Return ONLY valid JSON:
{{
  "known_facts": {{"field_id": "value", ...}},
  "questions": [{{question objects}}],
  "readiness": "ready" | "needs_questions" | "needs_critical_info",
  "readiness_reason": "brief explanation"
}}"""


# ---------------------------------------------------------------------------
# Question tree hints — load per-job-type questions as AI context
# ---------------------------------------------------------------------------

def _get_tree_question_hints(job_type):
    # type: (str) -> str
    """Load question tree for job_type and return a compact summary for AI context.

    Returns a multi-line string of questions with their options, or "" if
    no tree exists for the job type. This is CONTEXT, not a script — Opus
    uses its judgment about which questions are relevant.
    """
    if not job_type:
        return ""
    try:
        tree_path = _TREE_DATA_DIR / ("%s.json" % job_type)
        if not tree_path.exists():
            return ""
        with open(tree_path) as f:
            tree = json.load(f)
        hints = []
        for q in tree.get("questions", []):
            qid = q.get("id", "")
            text = q.get("text", "")
            if not qid or not text:
                continue
            line = "- %s: %s" % (qid, text)
            qtype = q.get("type", "")
            options = q.get("options", [])
            if qtype == "choice" and options:
                line += " [%s]" % ", ".join(str(o) for o in options[:6])
            elif qtype == "measurement":
                unit = q.get("unit", "")
                if unit:
                    line += " (%s)" % unit
            hints.append(line)
        return "\n".join(hints) if hints else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_intake_questions(description, photo_observations=""):
    # type: (str, str) -> dict
    """
    First AI call — analyze description (+ photo observations) and generate
    initial questions.

    Returns:
        {
            "known_facts": dict,
            "questions": list[dict],
            "readiness": str,
            "readiness_reason": str,
        }
    Or a fallback dict if AI is unavailable.
    """
    if not is_configured():
        logger.warning("Universal intake: AI not configured, returning fallback questions")
        return _fallback_intake(description)

    photo_clause = " and uploaded photos" if photo_observations else ""
    photo_ref = " and photos" if photo_observations else ""
    photo_observations_block = ""
    if photo_observations:
        photo_observations_block = (
            "\nPHOTO OBSERVATIONS:\n\"\"\"%s\"\"\"\n" % photo_observations
        )

    prompt = UNIVERSAL_INTAKE_PROMPT.format(
        description=description,
        photo_clause=photo_clause,
        photo_ref=photo_ref,
        photo_observations_block=photo_observations_block,
    )

    try:
        text = call_deep(prompt, temperature=0.2, timeout=90)
        if text is None:
            logger.warning("Universal intake: AI returned None")
            return _fallback_intake(description)

        parsed = _parse_ai_response(text)
        if parsed is None:
            return _fallback_intake(description)

        # Validate and normalize questions
        parsed["questions"] = _validate_questions(parsed.get("questions", []))
        logger.info(
            "Universal intake: %d known facts, %d questions, readiness=%s",
            len(parsed.get("known_facts", {})),
            len(parsed.get("questions", [])),
            parsed.get("readiness", "unknown"),
        )
        return parsed

    except Exception as e:
        logger.error("Universal intake failed: %s: %s", type(e).__name__, e)
        return _fallback_intake(description)


def generate_followup_questions(description, known_facts, qa_history,
                                 photo_observations="", job_type=""):
    # type: (str, dict, list, str, str) -> dict
    """
    Subsequent AI calls — given accumulated Q&A, generate follow-up questions.

    Args:
        description: original project description
        known_facts: current dict of known facts
        qa_history: list of {"question": str, "answer": str} dicts
        photo_observations: photo analysis text (if any)
        job_type: detected job type (e.g., "ornamental_fence") — used to load
            question tree hints as AI context

    Returns same shape as generate_intake_questions().
    """
    if not is_configured():
        logger.warning("Universal followup: AI not configured")
        return {
            "known_facts": dict(known_facts),
            "questions": [],
            "readiness": "ready",
            "readiness_reason": "AI unavailable — proceeding with current info",
        }

    # Build known facts block
    known_lines = []
    for k, v in known_facts.items():
        known_lines.append("  - %s: %s" % (k, v))
    known_facts_block = "\n".join(known_lines) if known_lines else "  (none yet)"

    # Build QA history block
    qa_lines = []
    for qa in qa_history:
        qa_lines.append("Q: %s" % qa.get("question", ""))
        qa_lines.append("A: %s" % qa.get("answer", ""))
        qa_lines.append("")
    qa_history_block = "\n".join(qa_lines) if qa_lines else "(no Q&A yet)"

    photo_observations_block = ""
    if photo_observations:
        photo_observations_block = (
            "\nPHOTO OBSERVATIONS:\n\"\"\"%s\"\"\"\n" % photo_observations
        )

    prompt = FOLLOWUP_PROMPT.format(
        description=description,
        known_facts_block=known_facts_block,
        qa_history_block=qa_history_block,
        photo_observations_block=photo_observations_block,
    )

    # Inject question tree hints as domain context (not a script)
    tree_hints = _get_tree_question_hints(job_type)
    if tree_hints:
        tree_context = (
            "\nDOMAIN QUESTIONS for %s:\n"
            "These questions are known to be important for this job type. "
            "Ask about any that haven't been answered yet. Use the options "
            "shown as multiple-choice when available:\n\n%s\n"
        ) % (job_type.replace("_", " ").title(), tree_hints)
        prompt = prompt + tree_context

    try:
        text = call_deep(prompt, temperature=0.2, timeout=60)
        if text is None:
            logger.warning("Universal followup: AI returned None")
            return {
                "known_facts": dict(known_facts),
                "questions": [],
                "readiness": "ready",
                "readiness_reason": "AI unavailable",
            }

        parsed = _parse_ai_response(text)
        if parsed is None:
            return {
                "known_facts": dict(known_facts),
                "questions": [],
                "readiness": "ready",
                "readiness_reason": "Parse error",
            }

        parsed["questions"] = _validate_questions(parsed.get("questions", []))
        logger.info(
            "Universal followup: %d known facts, %d questions, readiness=%s",
            len(parsed.get("known_facts", {})),
            len(parsed.get("questions", [])),
            parsed.get("readiness", "unknown"),
        )
        return parsed

    except Exception as e:
        logger.error("Universal followup failed: %s: %s", type(e).__name__, e)
        return {
            "known_facts": dict(known_facts),
            "questions": [],
            "readiness": "ready",
            "readiness_reason": str(e),
        }


# ---------------------------------------------------------------------------
# Helpers: response shape builders
# ---------------------------------------------------------------------------

def build_completion_from_readiness(readiness, known_facts, questions):
    # type: (str, dict, list) -> dict
    """
    Convert AI readiness assessment into the completion dict shape
    that the frontend expects.

    Frontend expects:
        {
            "is_complete": bool,
            "required_total": int,
            "required_answered": int,
            "required_missing": list[str],
            "total_answered": int,
            "completion_pct": float,
        }
    """
    n_known = len(known_facts)
    n_questions = len(questions)
    total = n_known + n_questions

    if readiness == "ready":
        return {
            "is_complete": True,
            "required_total": max(total, n_known),
            "required_answered": n_known,
            "required_missing": [],
            "total_answered": n_known,
            "completion_pct": 100.0,
        }

    # Not ready — compute progress percentage
    pct = round(n_known / max(total, 1) * 100, 1) if total > 0 else 0.0
    missing = [q.get("id", "unknown") for q in questions if q.get("required", False)]

    return {
        "is_complete": False,
        "required_total": total,
        "required_answered": n_known,
        "required_missing": missing,
        "total_answered": n_known,
        "completion_pct": pct,
    }


def build_extracted_fields_from_known(known_facts):
    # type: (dict) -> dict
    """
    Convert AI known_facts into extracted_fields dict for the frontend.
    Filters out internal keys (starting with _).
    """
    return {
        k: v for k, v in known_facts.items()
        if not str(k).startswith("_")
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_ai_response(text):
    # type: (str) -> Optional[dict]
    """Parse AI response text into a dict. Handles markdown code blocks."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        logger.warning("Universal intake: AI response is not a dict: %s", type(parsed))
        return None
    except json.JSONDecodeError as e:
        logger.warning("Universal intake: JSON parse error: %s — raw: %.500s", e, text)
        return None


def _validate_questions(questions):
    # type: (list) -> list
    """Validate and normalize question dicts from AI response."""
    validated = []
    seen_ids = set()

    for q in questions:
        if not isinstance(q, dict):
            continue
        if not q.get("text") or not q.get("type"):
            continue

        qid = str(q.get("id", "q_%d" % len(validated)))
        # Ensure unique IDs
        if qid in seen_ids:
            qid = qid + "_%d" % len(validated)
        seen_ids.add(qid)

        question = {
            "id": qid,
            "text": str(q["text"]),
            "type": str(q["type"]),
            "required": bool(q.get("required", True)),
            "hint": q.get("hint"),
            "source": "universal_intake",
        }

        if q.get("options") and isinstance(q["options"], list):
            question["options"] = [str(o) for o in q["options"]]
        if q.get("unit"):
            question["unit"] = str(q["unit"])

        validated.append(question)

    return validated


def _fallback_intake(description):
    # type: (str) -> dict
    """
    Fallback when AI is unavailable. Returns universal questions that apply
    to any metal fabrication project, plus domain-specific questions based
    on keyword detection.
    """
    desc_lower = description.lower()

    # Try to extract obvious facts from description
    known = {}
    if any(kw in desc_lower for kw in ("mild steel", "carbon steel", "steel")):
        known["material"] = "mild steel"
    elif "aluminum" in desc_lower:
        known["material"] = "aluminum"
    elif "stainless" in desc_lower:
        known["material"] = "stainless steel"

    if "powder coat" in desc_lower:
        known["finish"] = "powder coat"
    elif "paint" in desc_lower and "powder" not in desc_lower:
        known["finish"] = "paint"
    elif "galvaniz" in desc_lower:
        known["finish"] = "galvanized"
    elif "raw" in desc_lower:
        known["finish"] = "raw"

    questions = []

    if "material" not in known:
        questions.append({
            "id": "material",
            "text": "What material is this project made from?",
            "type": "choice",
            "options": [
                "Mild steel",
                "Aluminum",
                "Stainless steel (304)",
                "Stainless steel (316)",
                "Other (specify in notes)",
            ],
            "required": True,
            "hint": "Material determines profile keys, weld process, and consumables",
            "source": "universal_intake",
        })

    questions.append({
        "id": "overall_dimensions",
        "text": "What are the overall dimensions of this project?",
        "type": "text",
        "required": True,
        "hint": "Length x width x height — this is the #1 driver of material cost",
        "source": "universal_intake",
    })

    if "finish" not in known:
        questions.append({
            "id": "finish",
            "text": "What finish do you want?",
            "type": "choice",
            "options": [
                "Powder coat",
                "Paint",
                "Clear coat",
                "Galvanized",
                "Raw (no finish)",
            ],
            "required": True,
            "hint": "Finish affects appearance, durability, and cost",
            "source": "universal_intake",
        })

    questions.append({
        "id": "installation",
        "text": "What's the installation scope?",
        "type": "choice",
        "options": [
            "Full installation (we install on site)",
            "Delivery only (no installation)",
            "Shop pickup (customer picks up)",
        ],
        "required": True,
        "hint": "Installation can be 20-40% of the total quote",
        "source": "universal_intake",
    })

    questions.append({
        "id": "quantity",
        "text": "How many units do you need?",
        "type": "number",
        "required": True,
        "hint": "Batch production can reduce per-unit cost",
        "source": "universal_intake",
    })

    questions.append({
        "id": "indoor_outdoor",
        "text": "Is this for indoor or outdoor use?",
        "type": "choice",
        "options": ["Indoor", "Outdoor", "Both / covered outdoor"],
        "required": True,
        "hint": "Outdoor use requires better finish and hardware grade",
        "source": "universal_intake",
    })

    # Electronics keyword detection — inject electronics question when
    # description mentions LED/neon/illumination terms
    _electronics_kw = ("led", "neon", "illuminat", "backlit", "back-lit",
                       "controller", "driver", "rgb", "pixel")
    if any(kw in desc_lower for kw in _electronics_kw):
        questions.append({
            "id": "electronics_spec",
            "text": "What electronics are needed? (power supply, LED driver, controller, voltage)",
            "type": "text",
            "required": False,
            "hint": "e.g. 12V LED modules with Mean Well power supply, or 'not sure'",
            "source": "universal_intake",
        })

    return {
        "known_facts": known,
        "questions": questions,
        "readiness": "needs_questions",
        "readiness_reason": "AI unavailable — using standard fallback questions",
    }
