"""
Question Tree Engine — loads, processes, and walks through job-type-specific question trees.

This is the brain of Stage 1 (Intake) and Stage 2 (Clarify) of the pipeline.
It determines what questions to ask, respects branching logic, and avoids
re-asking questions already answered in the user's initial description.
"""

import base64
import json
import logging
import urllib.request
from pathlib import Path
from typing import Optional

from ..claude_client import call_fast, call_vision as _claude_vision

logger = logging.getLogger(__name__)

# Directory where question tree JSON files live
DATA_DIR = Path(__file__).parent / "data"


class QuestionTreeEngine:
    """Core logic for the question tree system."""

    def __init__(self):
        self._cache: dict[str, dict] = {}

    def load_tree(self, job_type: str) -> dict:
        """Load question tree JSON for a job type. Cached after first load."""
        if job_type in self._cache:
            return self._cache[job_type]

        filepath = DATA_DIR / f"{job_type}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"No question tree found for job type: {job_type}")

        with open(filepath) as f:
            tree = json.load(f)

        self._cache[job_type] = tree
        return tree

    def list_available_trees(self) -> list[str]:
        """Return list of job types that have question tree JSON files."""
        return sorted(
            p.stem for p in DATA_DIR.glob("*.json")
        )

    def get_all_questions(self, job_type: str) -> list[dict]:
        """Return all questions for a job type."""
        tree = self.load_tree(job_type)
        return tree.get("questions", [])

    def get_required_fields(self, job_type: str) -> list[str]:
        """Return list of required field IDs for a job type."""
        tree = self.load_tree(job_type)
        return tree.get("required_fields", [])

    def extract_from_description(self, job_type: str, description: str) -> dict:
        """
        Use Claude to parse a natural language description and extract
        any fields that were already answered.

        Returns: {field_id: extracted_value} for fields found in description.
        Only returns fields with >90% confidence. Never guesses measurements
        from vague descriptions.
        """
        tree = self.load_tree(job_type)
        questions = tree.get("questions", [])

        # Build field descriptions for the extraction prompt
        field_descriptions = []
        for q in questions:
            field_desc = f"- {q['id']}: {q['text']}"
            if q.get("type") == "choice" and q.get("options"):
                field_desc += f" Options: {', '.join(q['options'])}"
            elif q.get("type") == "measurement":
                field_desc += f" (numeric value in {q.get('unit', 'units')})"
            field_descriptions.append(field_desc)

        prompt = _build_extraction_prompt(
            job_type=job_type,
            display_name=tree.get("display_name", job_type),
            description=description,
            field_descriptions="\n".join(field_descriptions),
        )

        # Call Claude for extraction
        raw_extracted = _call_claude_extract(prompt)
        logger.info(
            "Field extraction for %s: raw=%d fields from description (%d chars)",
            job_type, len(raw_extracted), len(description),
        )

        # Normalize choice values to exact option strings
        extracted = _normalize_extracted_fields(raw_extracted, questions)
        if len(extracted) != len(raw_extracted):
            dropped = set(raw_extracted.keys()) - set(extracted.keys())
            logger.warning(
                "Field extraction normalization dropped %d fields: %s",
                len(dropped), dropped,
            )
        return extracted

    def extract_from_photo(self, job_type: str, photo_url_or_path: str,
                           description: str = "") -> dict:
        """
        Send a photo to Claude Vision to extract job-relevant information.

        Returns: {
            "extracted_fields": dict,     # field_id: value pairs
            "photo_observations": str,    # Plain language description
            "material_detected": str,     # Material type if identifiable
            "dimensions_detected": dict,  # Any measurements visible
            "damage_assessment": str,     # For repair jobs
            "confidence": float,          # Overall confidence
        }
        """
        tree = self.load_tree(job_type)
        questions = tree.get("questions", [])

        # Build field descriptions for the prompt
        field_descriptions = []
        for q in questions:
            field_desc = f"- {q['id']}: {q['text']}"
            if q.get("type") == "choice" and q.get("options"):
                field_desc += f" Options: {', '.join(q['options'])}"
            elif q.get("type") == "measurement":
                field_desc += f" (numeric value in {q.get('unit', 'units')})"
            field_descriptions.append(field_desc)

        # Read the image
        try:
            image_data = _read_image(photo_url_or_path)
        except Exception:
            return _empty_photo_result()

        if not image_data:
            return _empty_photo_result()

        image_b64 = base64.b64encode(image_data).decode("utf-8")

        # Detect mime type
        ext = photo_url_or_path.rsplit(".", 1)[-1].lower() if "." in photo_url_or_path else "jpg"
        mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
        mime_type = mime_map.get(ext, "image/jpeg")

        vision_prompt = _build_vision_prompt(
            job_type=job_type,
            description=description,
            field_descriptions="\n".join(field_descriptions),
        )

        result = _call_claude_vision(vision_prompt, image_b64, mime_type)
        return result

    def get_next_questions(self, job_type: str, answered_fields: dict) -> list[dict]:
        """
        Given what's already answered, return the next unanswered questions.

        Respects branching logic:
        - Questions with depends_on are only shown if their dependency is answered
        - Branch-activated questions are only shown if the branching answer triggers them
        - Already-answered questions are never returned

        Returns questions in tree order, skipping answered and blocked ones.
        """
        tree = self.load_tree(job_type)
        questions = tree.get("questions", [])
        next_qs = []

        # Build a set of questions activated by branches
        branch_activated = set()
        for q in questions:
            if q.get("branches"):
                answered_value = answered_fields.get(q["id"])
                if answered_value and answered_value in q["branches"]:
                    for activated_id in q["branches"][answered_value]:
                        branch_activated.add(activated_id)

        for q in questions:
            qid = q["id"]

            # Skip already answered
            if qid in answered_fields:
                continue

            # Check depends_on — only show if the parent question is answered
            depends_on = q.get("depends_on")
            if depends_on:
                if depends_on not in answered_fields:
                    continue
                # Also check if this question is branch-activated
                # If the parent has branches, this question must be in an activated branch
                parent = _find_question(questions, depends_on)
                if parent and parent.get("branches"):
                    if qid not in branch_activated:
                        continue

            # Questions without depends_on are always eligible (top-level)
            next_qs.append(q)

        return next_qs

    # Fields that every quote needs regardless of whether the tree lists them
    _ALWAYS_REQUIRED = ("finish",)

    def is_complete(self, job_type: str, answered_fields: dict) -> bool:
        """Are all required fields answered?

        Branch-dependent fields that are NOT activated by the user's answers
        are treated as satisfied — e.g. picket_material is only required
        when infill_type = "Pickets (vertical bars)", not when "Expanded metal".

        finish is always required (even if not in tree's required_fields)
        because every quote needs a finishing section.
        """
        tree = self.load_tree(job_type)
        questions = tree.get("questions", [])
        required = list(tree.get("required_fields", []))

        # Ensure always-required fields are in the list
        for f in self._ALWAYS_REQUIRED:
            if f not in required:
                required.append(f)

        # Build set of branch-activated question IDs
        branch_activated = set()
        for q in questions:
            if q.get("branches"):
                answered_value = answered_fields.get(q["id"])
                if answered_value and answered_value in q["branches"]:
                    for activated_id in q["branches"][answered_value]:
                        branch_activated.add(activated_id)

        for field in required:
            if field in answered_fields:
                continue
            # Check if this field is branch-dependent and NOT activated
            q = _find_question(questions, field)
            if q and q.get("depends_on"):
                parent = _find_question(questions, q["depends_on"])
                if parent and parent.get("branches"):
                    # This field requires a specific parent answer to activate
                    if field not in branch_activated:
                        continue  # Not activated = not required for this path
            return False  # Required, not answered, not branch-blocked
        return True

    def get_completion_status(self, job_type: str, answered_fields: dict) -> dict:
        """Return detailed completion status.

        Branch-dependent fields that are NOT activated by the user's answers
        are excluded from the 'missing' count.

        finish is always required (even if not in tree's required_fields).
        """
        tree = self.load_tree(job_type)
        questions = tree.get("questions", [])
        required = list(tree.get("required_fields", []))

        # Ensure always-required fields are in the list
        for f in self._ALWAYS_REQUIRED:
            if f not in required:
                required.append(f)

        # Build set of branch-activated question IDs
        branch_activated = set()
        for q in questions:
            if q.get("branches"):
                answered_value = answered_fields.get(q["id"])
                if answered_value and answered_value in q["branches"]:
                    for activated_id in q["branches"][answered_value]:
                        branch_activated.add(activated_id)

        answered_required = []
        missing_required = []
        for field in required:
            if field in answered_fields:
                answered_required.append(field)
            else:
                # Check if branch-dependent and NOT activated
                q = _find_question(questions, field)
                if q and q.get("depends_on"):
                    parent = _find_question(questions, q["depends_on"])
                    if parent and parent.get("branches"):
                        if field not in branch_activated:
                            # Not activated = treated as satisfied
                            answered_required.append(field)
                            continue
                missing_required.append(field)

        total_answered = len(answered_fields)

        return {
            "is_complete": len(missing_required) == 0,
            "required_total": len(required),
            "required_answered": len(answered_required),
            "required_missing": missing_required,
            "total_answered": total_answered,
            "completion_pct": round(
                len(answered_required) / max(len(required), 1) * 100, 1
            ),
        }

    def suggest_additional_questions(self, job_type: str, description: str,
                                     extracted_fields: dict,
                                     tree_question_ids: list) -> list:
        """
        Use AI to suggest 0-3 additional questions not covered by the question tree.

        Identifies critical fabrication/engineering details (gauge, electronics specs,
        waterproofing, paint coats, etc.) that would materially affect materials,
        labor, or pricing.

        Returns list of question dicts matching the tree question schema, or [].
        Never raises — returns [] on any error.
        """
        try:
            if not description or not description.strip():
                return []

            # Build context about what's already covered
            extracted_summary = ""
            if extracted_fields:
                extracted_lines = [
                    "  - %s: %s" % (k, v)
                    for k, v in extracted_fields.items()
                    if not str(k).startswith("_")
                ]
                if extracted_lines:
                    extracted_summary = "\n".join(extracted_lines)

            tree_topics = ", ".join(tree_question_ids) if tree_question_ids else "(none)"

            prompt = (
                "You are a metal fabrication quoting assistant. A customer submitted "
                "a job description and we already have a standard set of questions "
                "for this job type. Identify 0-3 CRITICAL fabrication details NOT "
                "covered by the existing questions that would materially affect "
                "materials, labor, or pricing.\n\n"
                "If everything important is already covered, return `[]`.\n\n"
                "Job type: %s\n\n"
                "Customer description:\n\"\"\"%s\"\"\"\n\n"
                "Already extracted fields:\n%s\n\n"
                "Existing question topics already covered: %s\n\n"
                "EXAMPLES of what to ask about (only if relevant to this description):\n"
                "- Material gauge/thickness when not specified\n"
                "- Electronics specs (controllers, LED drivers, voltage)\n"
                "- Waterproofing/IP rating for outdoor items\n"
                "- Number of paint/clear coats\n"
                "- Surface finish quality (mill finish, brushed, mirror)\n"
                "- Load rating / weight capacity requirements\n"
                "- Specific alloy grade (6061 vs 5052 aluminum, 304 vs 316 SS)\n\n"
                "RULES:\n"
                "1. Only ask about things the description HINTS at but doesn't specify.\n"
                "2. Do NOT repeat questions already covered by the existing topics.\n"
                "3. Each question must have a clear impact on materials, labor, or price.\n"
                "4. Max 3 questions. Fewer is better. Return [] if none needed.\n\n"
                "KNOWLEDGE vs PREFERENCE:\n"
                "- KNOWLEDGE: Standard fabrication practices with one correct approach. Do NOT ask.\n"
                "  Examples: miter angle for square joints (45 deg), weld process for aluminum (TIG),\n"
                "  deburring cuts, weld sequence (tack first then full), joint prep for structural welds.\n"
                "- PREFERENCES: Design choices where multiple valid approaches exist and affect\n"
                "  cost, labor, or appearance. ALWAYS ask when relevant.\n\n"
                "HIGH-IMPACT PREFERENCES (ask these first):\n"
                "- Weld finish quality: industrial (leave as-welded) vs furniture-grade (grind flush + blend)\n"
                "- Number of finish coats: 1 coat vs 2 coats (affects labor + materials 30-50%%)\n"
                "- Hardware quality tier: economy (Amazon) vs commercial (McMaster) vs premium (specialty)\n"
                "- Mounting method: surface mount vs embedded/core-drilled vs through-bolt\n"
                "- Edge treatment: sharp/raw vs ground smooth vs radiused\n\n"
                "SIGN-SPECIFIC PREFERENCES (when job_type contains 'sign' or 'led'):\n"
                "- LED pixel density: 30/m vs 60/m vs 144/m (huge cost difference)\n"
                "- Controller: basic on/off vs WiFi/Bluetooth vs DMX/Art-Net\n"
                "- Weatherproofing: indoor-only vs outdoor IP65 vs outdoor IP67 (submersible)\n"
                "- Power redundancy: single PSU vs dual with failover\n"
                "- Letter style: flat-cut vs channel vs halo-lit vs combination\n\n"
                "Ask 1-3 PREFERENCE questions with biggest impact on quote accuracy.\n"
                "Do NOT ask about things that are standard practice or already specified.\n\n"
                "Return ONLY valid JSON — an array of question objects:\n"
                "[\n"
                "  {\n"
                '    "id": "material_gauge",\n'
                '    "text": "What gauge/thickness for the aluminum?",\n'
                '    "type": "choice",\n'
                '    "options": ["14 gauge", "11 gauge", "3/16\\"", "1/4\\""],\n'
                '    "hint": "Thicker = stronger but heavier and more expensive"\n'
                "  }\n"
                "]\n\n"
                "Valid types: choice, measurement, text, number\n"
                "For choice type, provide 2-5 practical options.\n"
                "Return ONLY the JSON array, nothing else."
                % (job_type, description, extracted_summary or "  (none)", tree_topics)
            )

            text = call_fast(prompt, timeout=30)
            if text is None:
                return []

            # Strip markdown code fences
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            parsed = json.loads(cleaned)
            if not isinstance(parsed, list):
                return []

            # Validate, normalize, and cap at 3
            validated = []
            for q in parsed:
                if not isinstance(q, dict):
                    continue
                if not q.get("text") or not q.get("type"):
                    continue

                # Ensure _ai_ prefix on ID
                qid = str(q.get("id", "question"))
                if not qid.startswith("_ai_"):
                    qid = "_ai_" + qid

                question = {
                    "id": qid,
                    "text": str(q["text"]),
                    "type": str(q["type"]),
                    "required": False,
                    "hint": q.get("hint"),
                    "source": "ai_suggested",
                }
                if q.get("options") and isinstance(q["options"], list):
                    question["options"] = [str(o) for o in q["options"]]
                if q.get("unit"):
                    question["unit"] = str(q["unit"])

                validated.append(question)
                if len(validated) >= 3:
                    break

            if validated:
                logger.info(
                    "AI suggested %d additional questions for %s: %s",
                    len(validated), job_type,
                    [q["id"] for q in validated],
                )
            return validated

        except Exception as e:
            logger.warning("AI question suggestion failed: %s", e)
            return []

    def get_quote_params(self, job_type: str, answered_fields: dict,
                         user_id: int = 0, session_id: str = "",
                         photos: Optional[list[str]] = None,
                         notes: str = "") -> dict:
        """
        Convert answered fields into a QuoteParams dict matching CLAUDE.md contract.

        QuoteParams = {
            job_type: str,
            user_id: int,
            session_id: str,
            fields: dict,
            photos: list[str],
            notes: str,
        }
        """
        return {
            "job_type": job_type,
            "user_id": user_id,
            "session_id": session_id,
            "fields": dict(answered_fields),
            "photos": photos or [],
            "notes": notes,
        }


def _find_question(questions: list[dict], question_id: str) -> Optional[dict]:
    """Find a question by ID in a list of questions."""
    for q in questions:
        if q["id"] == question_id:
            return q
    return None


def _build_extraction_prompt(job_type: str, display_name: str,
                             description: str, field_descriptions: str) -> str:
    """Build the Claude prompt for field extraction from a description."""
    return f"""You are extracting structured fields from a metal fabrication quote request.

Job type: {display_name} ({job_type})

Customer description:
\"\"\"{description}\"\"\"

EXTRACT every field the customer stated or clearly implied. Be AGGRESSIVE — if the customer said it, extract it.

RULES:
1. MEASUREMENTS: Convert to the field's unit. "10 feet" -> 10. "120 inches" -> 10 (feet). "10'" -> 10. "10x6" -> width=10, height=6.
2. CHOICE FIELDS: You MUST return the EXACT option string from the options list. Do NOT paraphrase.
   - If customer says "paint" and options are ["Powder coat (most durable, outsourced)", "Paint (in-house)", ...] -> return "Paint (in-house)"
   - If customer says "motor" or "electric" and options are ["Yes", "No — manual operation", ...] -> return "Yes"
   - If customer says "install" or "full install" and options include "Full installation (gate + posts + concrete)" -> return that exact string
   - If customer says "pickup" or "no install" and options include "Shop pickup (no installation)" -> return that exact string
   - If customer says "pickets" and options include "Pickets (vertical bars)" -> return "Pickets (vertical bars)"
3. BOOLEAN/YES-NO: "with motor" -> "Yes". "no motor" -> "No — manual operation" (use exact option string).
4. If the field is NOT mentioned at all, omit it. But if mentioned even briefly, EXTRACT it.
5. Return ONLY a JSON object with field_id: extracted_value pairs. Empty object {{{{}}}} if nothing found.
6. FINISH FIELD: If the customer mentions ANY finish/coating term, extract the "finish" field. Map these terms:
   - "clear coat", "clear coated", "clearcoat", "clear-coat", "permalac", "lacquer" -> closest clear coat option, or "clearcoat" if no exact match
   - "powder coat", "powdercoat" -> closest powder coat option
   - "anodize", "anodized" -> "anodized"
   - "brushed", "polished", "mill finish" -> closest option
   - "raw", "no finish" -> "raw"
   If NO option in the list matches, still extract the finish field with the customer's term verbatim.

FIELDS:
{field_descriptions}

Return ONLY valid JSON:"""


def _call_claude_extract(prompt: str) -> dict:
    """
    Call Claude API to extract fields from description.
    Returns parsed dict of extracted fields.
    Falls back to empty dict on any error.
    """
    try:
        text = call_fast(prompt, timeout=30)
        if text is None:
            logger.warning("Claude extraction returned None — API key may not be set")
            return {}
        # Strip markdown code fences if Claude wrapped the JSON
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]  # remove first line
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            logger.info("Claude extraction parsed %d fields: %s",
                        len(parsed), list(parsed.keys()))
            return parsed
        logger.warning("Claude extraction returned non-dict: %s", type(parsed))
        return {}
    except json.JSONDecodeError as e:
        logger.warning("Claude extraction JSON parse error: %s — raw text: %.200s",
                       e, text)
        return {}
    except Exception as e:
        logger.warning("Claude extraction failed: %s", e)
        return {}


def _normalize_extracted_fields(extracted: dict, questions: list) -> dict:
    """
    Normalize extracted field values to match exact option strings from the
    question tree. This ensures branching logic works (exact string match).

    Strategy for choice fields:
    1. Exact match — value is already a valid option string
    2. Case-insensitive match — "yes" -> "Yes"
    3. Substring match — "paint" -> "Paint (in-house)" if only one option contains it
    4. Drop — no match found, remove the field

    Measurement/text/number fields pass through unchanged.
    """
    # Build lookup: field_id -> question dict
    q_map = {}
    for q in questions:
        q_map[q["id"]] = q

    result = {}
    for field_id, value in extracted.items():
        q = q_map.get(field_id)
        if q is None:
            # Unknown field — skip
            logger.warning("Extraction returned unknown field: %s", field_id)
            continue

        field_type = q.get("type", "text")
        options = q.get("options", [])

        if field_type in ("choice", "multi_choice") and options:
            normalized = _match_option(str(value), options)
            if normalized is not None:
                result[field_id] = normalized
            else:
                logger.warning(
                    "Dropping field %s: value '%s' matched no option in %s",
                    field_id, value, options,
                )
        else:
            # Measurement, text, number, boolean, photo — pass through
            result[field_id] = value

    return result


def _match_option(value: str, options: list) -> Optional[str]:
    """
    Match a raw extracted value to the closest option string.

    Returns the exact option string, or None if no match.
    """
    # 1. Exact match
    if value in options:
        return value

    # 2. Case-insensitive exact match
    val_lower = value.lower().strip()
    for opt in options:
        if opt.lower().strip() == val_lower:
            return opt

    # 3. Substring match — value is contained in exactly one option
    substring_matches = [opt for opt in options if val_lower in opt.lower()]
    if len(substring_matches) == 1:
        return substring_matches[0]

    # 4. Reverse substring — option is contained in value
    reverse_matches = [opt for opt in options if opt.lower().strip() in val_lower]
    if len(reverse_matches) == 1:
        return reverse_matches[0]

    # 5. Word overlap — find the option with the most shared words
    val_words = set(val_lower.split())
    best_opt = None
    best_overlap = 0
    for opt in options:
        opt_words = set(opt.lower().split())
        overlap = len(val_words & opt_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_opt = opt
    if best_overlap >= 1 and best_opt is not None:
        return best_opt

    return None


def _read_image(photo_url_or_path: str) -> Optional[bytes]:
    """Read image data from a URL or local file path."""
    if photo_url_or_path.startswith("http"):
        req = urllib.request.Request(photo_url_or_path)
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
    else:
        # Local file — try absolute path first, then relative
        path = Path(photo_url_or_path)
        if not path.exists():
            # Try stripping leading /uploads/ for local dev
            stripped = photo_url_or_path.lstrip("/")
            path = Path(stripped)
        if path.exists():
            with open(path, "rb") as f:
                return f.read()
    return None


def _empty_photo_result() -> dict:
    """Return empty photo extraction result."""
    return {
        "extracted_fields": {},
        "photo_observations": "Photo received — vision processing unavailable. Photo stored for reference.",
        "material_detected": "unknown",
        "dimensions_detected": {},
        "damage_assessment": "N/A",
        "confidence": 0.0,
    }


def _build_vision_prompt(job_type: str, description: str, field_descriptions: str) -> str:
    """Build the Claude Vision prompt for photo analysis."""
    return f"""You are analyzing a photo for a metal fabrication quoting system.
Job type: {job_type}
Additional context from user: {description}

Look for and extract the following information from this photo:

1. MEASUREMENTS: Look for tape measures, rulers, measuring tools visible in the photo.
   Read any measurements you can see and report them with units.

2. MATERIAL TYPE: What metal is this?
   - Orange/red rust = mild steel or wrought iron
   - No rust, shiny silver = stainless steel or aluminum
   - Dull grey with no rust = galvanized
   - Uniform color coating = painted or powder coated
   - Brown/orange patina (intentional) = corten/weathering steel

3. DIMENSIONS: Even without a tape measure, estimate dimensions from context:
   - Door frames are typically 36" wide x 80" tall
   - Standard truck beds are 5-8 feet long
   - Standard ceiling height is 8-9 feet
   - A person's hand span is approximately 8 inches

4. CONDITION/DAMAGE (for repair jobs):
   - Cracks, breaks, or weld failures
   - Rust-through vs surface rust
   - Deformation, bending, impact damage
   - Missing pieces or sections

5. EXISTING HARDWARE: Identify any visible:
   - Hinges (type, condition)
   - Latches, locks
   - Gate operators/motors (brand if visible)
   - Mounting brackets, flanges

6. DESIGN ELEMENTS:
   - Picket style, spacing
   - Infill pattern
   - Decorative elements (scrollwork, spears, rings)
   - Frame profile (square tube, round tube, flat bar)

These are the specific fields I need for this job type:
{field_descriptions}

Return ONLY a JSON object with:
{{
    "extracted_fields": {{"field_id": "value", ...}},
    "photo_observations": "plain language description of everything you see",
    "material_detected": "mild_steel" or "stainless" or "aluminum" or "galvanized" or "unknown",
    "dimensions_detected": {{"description": "value_with_units", ...}},
    "damage_assessment": "description of any damage or N/A",
    "confidence": 0.0 to 1.0
}}

Only include fields you are confident about (>80% confidence).
Do NOT guess measurements — only report what you can clearly see or reasonably estimate."""


def _call_claude_vision(prompt: str, image_b64: str, mime_type: str) -> dict:
    """
    Call Claude Vision API with image + prompt.
    Returns parsed photo extraction result.
    Falls back to empty result on any error.
    """
    try:
        text = _claude_vision(prompt, image_b64, mime_type, timeout=60)
        if text is None:
            return _empty_photo_result()
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return {
                "extracted_fields": parsed.get("extracted_fields", {}),
                "photo_observations": parsed.get("photo_observations", ""),
                "material_detected": parsed.get("material_detected", "unknown"),
                "dimensions_detected": parsed.get("dimensions_detected", {}),
                "damage_assessment": parsed.get("damage_assessment", "N/A"),
                "confidence": float(parsed.get("confidence", 0.0)),
            }
        return _empty_photo_result()
    except Exception:
        return _empty_photo_result()


DETECTION_KEYWORDS = {
    "cantilever_gate": ["cantilever", "sliding gate", "slide gate", "roller gate"],
    "swing_gate": ["swing gate", "hinged gate", "driveway gate"],
    "straight_railing": ["railing", "handrail", "guardrail", "guard rail"],
    "stair_railing": ["stair railing", "staircase railing", "stair handrail"],
    "repair_decorative": ["repair", "fix", "restore", "broken", "rusted", "ornamental repair"],
    "ornamental_fence": ["fence", "fencing", "iron fence", "picket fence"],
    "complete_stair": ["stairs", "staircase", "stringer", "steel stairs", "metal stairs"],
    "spiral_stair": ["spiral stair", "spiral staircase", "helical stair"],
    "window_security_grate": ["window guard", "security bar", "window grate", "burglar bar", "security grate"],
    "balcony_railing": ["balcony", "juliet balcony", "balcony rail"],
    "furniture_table": ["table base", "table frame", "steel table", "metal table", "desk frame", "table leg"],
    "utility_enclosure": ["enclosure", "electrical box", "nema", "equipment enclosure", "utility box"],
    "bollard": ["bollard", "parking post", "vehicle barrier"],
    "repair_structural": ["structural repair", "trailer repair", "chassis repair", "beam repair", "weld repair"],
    "custom_fab": ["custom", "fabricat", "one-off", "prototype"],
    "offroad_bumper": ["bumper", "front bumper", "rear bumper", "off-road bumper", "offroad bumper", "truck bumper", "jeep bumper"],
    "rock_slider": ["rock slider", "rocker panel", "rock rail", "slider", "rocker guard"],
    "roll_cage": ["roll cage", "roll bar", "cage", "race cage", "utv cage"],
    "exhaust_custom": ["exhaust", "header", "downpipe", "exhaust pipe", "exhaust system", "turbo exhaust"],
    "trailer_fab": ["trailer", "flatbed trailer", "utility trailer", "trailer frame", "car hauler"],
    "structural_frame": ["structural", "beam", "column", "mezzanine", "canopy frame", "steel frame", "i-beam", "h-beam"],
    "furniture_other": ["shelf", "shelving", "bracket", "mount", "rack", "stand", "console", "bench frame"],
    "sign_frame": ["sign frame", "sign bracket", "sign post", "monument sign", "sign mount"],
    "led_sign_custom": ["led sign", "channel letter", "neon sign", "illuminated sign", "backlit sign", "light box"],
    "product_firetable": ["fire table", "firetable", "fire pit", "fire bowl", "firepit"],
}


def _detect_by_keywords(description: str) -> Optional[dict]:
    """
    Scan description for keyword matches. Returns IntakeResult dict if a
    high-confidence match is found, else None.

    Multi-word keywords are checked first (more specific), then single-word.
    """
    desc_lower = description.lower()

    # Score each job type by keyword matches
    best_type = None
    best_score = 0
    best_keyword_len = 0

    for job_type, keywords in DETECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                # Multi-word keywords score higher than single-word
                score = len(kw.split())
                if score > best_score or (score == best_score and len(kw) > best_keyword_len):
                    best_type = job_type
                    best_score = score
                    best_keyword_len = len(kw)

    if best_type and best_score >= 2:
        # Multi-word match — high confidence
        return {
            "job_type": best_type,
            "confidence": 0.9,
            "ambiguous": False,
        }
    elif best_type and best_score == 1:
        # Single-word match — moderate confidence, let Claude confirm if available
        return {
            "job_type": best_type,
            "confidence": 0.6,
            "ambiguous": True,
        }
    return None


def detect_job_type(description: str) -> dict:
    """
    Detect the job type from a natural language description.

    Strategy:
    1. Try keyword matching first (fast, no API call)
    2. If high-confidence keyword match, return immediately
    3. Otherwise, fall through to Claude with the full 25-type list
    4. If Claude unavailable, use keyword result or default to custom_fab

    Returns IntakeResult-shaped dict.
    This is Stage 1 (Intake) of the pipeline.
    """
    from ..models import V2_JOB_TYPES

    # Step 1: Try keyword detection
    keyword_result = _detect_by_keywords(description)

    # Step 2: If high confidence keyword match, return immediately
    if keyword_result and keyword_result["confidence"] >= 0.9:
        return keyword_result

    # Step 3: Try Claude for better accuracy
    from ..claude_client import is_configured
    if not is_configured():
        if keyword_result:
            return keyword_result
        return {
            "job_type": "custom_fab",
            "confidence": 0.0,
            "ambiguous": True,
        }

    job_types_str = ", ".join(V2_JOB_TYPES)
    prompt = f"""You are a metal fabrication quoting assistant. A customer has described a job. Determine which job type best matches their description.

Available job types: {job_types_str}

Customer description:
\"\"\"{description}\"\"\"

RULES:
- Choose the single best matching job type from the list above
- If the description could match multiple types, set ambiguous=true and pick the most likely
- confidence: 0.0-1.0 where 1.0 means you're certain
- If nothing matches well, use "custom_fab"

Return ONLY valid JSON:
{{"job_type": "one_of_the_types", "confidence": 0.85, "ambiguous": false}}"""

    try:
        text = call_fast(prompt)
        if text is None:
            if keyword_result:
                return keyword_result
            return {"job_type": "custom_fab", "confidence": 0.0, "ambiguous": True}
        parsed = json.loads(text)
        if parsed.get("job_type") not in V2_JOB_TYPES:
            parsed["job_type"] = "custom_fab"
            parsed["confidence"] = max(parsed.get("confidence", 0) * 0.5, 0.1)
        return parsed
    except Exception:
        if keyword_result:
            return keyword_result
        return {
            "job_type": "custom_fab",
            "confidence": 0.0,
            "ambiguous": True,
        }
