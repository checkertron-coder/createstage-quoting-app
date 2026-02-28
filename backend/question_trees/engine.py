"""
Question Tree Engine — loads, processes, and walks through job-type-specific question trees.

This is the brain of Stage 1 (Intake) and Stage 2 (Clarify) of the pipeline.
It determines what questions to ask, respects branching logic, and avoids
re-asking questions already answered in the user's initial description.
"""

import base64
import json
import os
import urllib.request
from pathlib import Path
from typing import Optional

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
        Use Gemini to parse a natural language description and extract
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

        # Call Gemini for extraction
        extracted = _call_gemini_extract(prompt)
        return extracted

    def extract_from_photo(self, job_type: str, photo_url_or_path: str,
                           description: str = "") -> dict:
        """
        Send a photo to Gemini Vision to extract job-relevant information.

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

        result = _call_gemini_vision(vision_prompt, image_b64, mime_type)
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

    def is_complete(self, job_type: str, answered_fields: dict) -> bool:
        """Are all required fields answered?"""
        required = self.get_required_fields(job_type)
        return all(field in answered_fields for field in required)

    def get_completion_status(self, job_type: str, answered_fields: dict) -> dict:
        """Return detailed completion status."""
        required = self.get_required_fields(job_type)
        answered_required = [f for f in required if f in answered_fields]
        missing_required = [f for f in required if f not in answered_fields]
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
    """Build the Gemini prompt for field extraction from a description."""
    return f"""You are a metal fabrication quoting assistant. A customer is requesting a quote for a {display_name} ({job_type}).

The customer provided this description:
\"\"\"{description}\"\"\"

Below are the fields we need for this job type. Extract any values that the customer has CLEARLY stated in their description.

RULES:
- Only extract values you are >90% confident about
- For measurement fields, only extract if the customer gave a specific number (e.g., "10 feet" → 10). Do NOT guess from vague descriptions like "big" or "standard"
- For choice fields, map the customer's words to the closest option
- If a field is not mentioned or unclear, do NOT include it
- Return ONLY a JSON object with field_id: value pairs
- If nothing can be extracted, return an empty object {{}}

FIELDS:
{field_descriptions}

Return ONLY valid JSON, no explanation:"""


def _call_gemini_extract(prompt: str) -> dict:
    """
    Call Gemini API to extract fields from description.
    Returns parsed dict of extracted fields.
    Falls back to empty dict on any error.
    """
    import urllib.request
    import urllib.error

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not api_key:
        # No API key — return empty extraction (tests and dev without Gemini)
        return {}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            return {}
    except Exception:
        # Any failure — return empty extraction rather than crashing
        return {}


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
    """Build the Gemini Vision prompt for photo analysis."""
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


def _call_gemini_vision(prompt: str, image_b64: str, mime_type: str) -> dict:
    """
    Call Gemini Vision API with image + prompt.
    Returns parsed photo extraction result.
    Falls back to empty result on any error.
    """
    import urllib.error

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not api_key:
        return _empty_photo_result()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = json.dumps({
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": image_b64}},
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                # Ensure all expected keys exist
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
        # Single-word match — moderate confidence, let Gemini confirm if available
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
    3. Otherwise, fall through to Gemini with the full 25-type list
    4. If Gemini unavailable, use keyword result or default to custom_fab

    Returns IntakeResult-shaped dict.
    This is Stage 1 (Intake) of the pipeline.
    """
    from ..models import V2_JOB_TYPES

    # Step 1: Try keyword detection
    keyword_result = _detect_by_keywords(description)

    # Step 2: If high confidence keyword match, return immediately
    if keyword_result and keyword_result["confidence"] >= 0.9:
        return keyword_result

    # Step 3: Try Gemini for better accuracy
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not api_key:
        # No API key — use keyword result or default
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

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            # Validate job_type is in the list
            if parsed.get("job_type") not in V2_JOB_TYPES:
                parsed["job_type"] = "custom_fab"
                parsed["confidence"] = max(parsed.get("confidence", 0) * 0.5, 0.1)
            return parsed
    except Exception:
        # Gemini failed — use keyword result or default
        if keyword_result:
            return keyword_result
        return {
            "job_type": "custom_fab",
            "confidence": 0.0,
            "ambiguous": True,
        }
