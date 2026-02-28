"""
Question Tree Engine — loads, processes, and walks through job-type-specific question trees.

This is the brain of Stage 1 (Intake) and Stage 2 (Clarify) of the pipeline.
It determines what questions to ask, respects branching logic, and avoids
re-asking questions already answered in the user's initial description.
"""

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


def detect_job_type(description: str) -> dict:
    """
    Use Gemini to detect the job type from a natural language description.
    Returns IntakeResult-shaped dict.

    This is Stage 1 (Intake) of the pipeline.
    """
    from ..models import V2_JOB_TYPES

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

    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    if not api_key:
        return {
            "job_type": "custom_fab",
            "confidence": 0.0,
            "ambiguous": True,
        }

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
        return {
            "job_type": "custom_fab",
            "confidence": 0.0,
            "ambiguous": True,
        }
