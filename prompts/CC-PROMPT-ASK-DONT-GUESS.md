# CC Prompt: Ask, Don't Guess

## Problem
Opus assumes values the user never provided. The extraction prompt says "Be AGGRESSIVE — if the customer said it, extract it" but in practice Opus extracts things the customer DIDN'T say. A user says "with mounting" and Opus assumes monument-style ground mount with 2 posts. A user describes 3 depth layers and Opus invents a 4th. The sign_frame tree has 7 questions for a project that needs 20. The AI-suggested follow-up questions are capped at 3 and sometimes ask irrelevant things ("how tall is this going?" for a wall-mounted circular sign). The result: Opus generates quotes full of hallucinated assumptions instead of asking the user.

**Root cause:** The system rewards guessing over asking. The extraction prompt encourages aggressive inference. The question suggestion is capped too low. There's no gate that says "you don't have enough info to quote this yet."

## Acceptance Criteria
1. Extraction prompt returns ONLY fields the user EXPLICITLY stated — never infers unstated values
2. AI-suggested questions expanded from max 3 to max 8, with smarter prompting
3. A new "scope readiness" check runs before quote generation — returns `ready`, `needs_questions`, or `insufficient` with a list of what's missing
4. The Hacienda sign (non-LED version) no longer assumes: monument mount, 2 posts, 4+ layers, or any field the user didn't specify
5. All existing tests still pass

## Steps

### Step 1: Fix the extraction prompt (engine.py)

**File:** `backend/question_trees/engine.py`, function `_build_extraction_prompt()`

Find the RULES section of the prompt string. Change rule 4 and add a new rule. The current text says:

```
4. If the field is NOT mentioned at all, omit it. But if mentioned even briefly, EXTRACT it.
```

Replace the entire RULES block (rules 1-6) with this:

```
RULES:
1. ONLY extract fields the customer EXPLICITLY stated. Do NOT infer, assume, or guess.
   - "with mounting" does NOT tell you the mount TYPE — omit mount type field
   - "multi-layer" does NOT tell you the exact layer count — omit layer count
   - "aluminum" does NOT mean 6061-T6 specifically — extract "aluminum" not an alloy grade
   - If you are less than 95% confident the customer stated this value, OMIT IT
2. MEASUREMENTS: Convert to the field's unit. "10 feet" -> 10. "120 inches" -> 10 (feet). Only extract measurements the customer gave explicitly.
3. CHOICE FIELDS: Return the EXACT option string from the options list. If no option is a confident match for what the customer said, OMIT the field entirely — do NOT pick the closest guess.
4. BOOLEAN/YES-NO: Only extract if the customer explicitly stated yes or no. "with motor" -> "Yes". Absence of mention is NOT "No" — it's omitted.
5. Return ONLY a JSON object with field_id: extracted_value pairs. Empty object {{}} if nothing matches confidently.
6. FINISH FIELD: Only extract if the customer explicitly mentions a finish. Map these terms:
   - "clear coat", "clearcoat", "clear-coat" -> closest clear coat option
   - "powder coat", "powdercoat" -> closest powder coat option
   - If the customer does NOT mention finish at all, OMIT the finish field entirely.
7. When in doubt, OMIT. A missing field triggers a question. A wrong field triggers a wrong quote. Questions are cheap. Wrong quotes lose customers.
```

Also change the intro line from:
```
EXTRACT every field the customer stated or clearly implied. Be AGGRESSIVE — if the customer said it, extract it.
```
To:
```
EXTRACT ONLY fields the customer EXPLICITLY stated. Be CONSERVATIVE — when in doubt, omit the field. A missing field will trigger a follow-up question; a wrong assumption will produce a wrong quote.
```

### Step 2: Expand AI-suggested questions (engine.py)

**File:** `backend/question_trees/engine.py`, function `suggest_additional_questions()`

**Change 1:** In the prompt string, change the max from 3 to 8:
- Find: `"Max 3 questions. Fewer is better. Return [] if none needed."`
- Replace: `"Ask 3-8 questions. Cover every gap that would materially affect the quote. Return [] ONLY if the description is so complete that zero ambiguity remains."`

**Change 2:** In the prompt string, change the intro instruction:
- Find: `"Identify 0-3 CRITICAL fabrication details NOT covered by the existing questions"`
- Replace: `"Identify 3-8 fabrication/engineering details NOT covered by the existing questions or NOT yet answered"`

**Change 3:** In the prompt, add this section before the RULES block:

```
SCOPE GAPS — things that MUST be asked if not already known:
- Mounting method (wall, posts, freestanding, hanging, customer-provided structure)
- Material thickness/gauge when not specified
- Exact dimensions of every component referenced but not dimensioned
- Indoor vs outdoor (drives finish, waterproofing, hardware grade)
- Number of finish coats
- Whether customer supplies any components (LED modules, mounting hardware, etc.)
- Access/serviceability requirements (access panels, removable parts)
- Weight capacity or structural load requirements
- Delivery vs installation (are we just building it, or installing too?)

These are NOT optional nice-to-haves. If any of these are unknown AND relevant to this job, ASK.
```

**Change 4:** In the validation loop at the bottom, change the cap from 3 to 8:
- Find: `if len(validated) >= 3:`
- Replace: `if len(validated) >= 8:`

**Change 5:** In the prompt, change:
- Find: `"Ask 1-3 PREFERENCE questions with biggest impact on quote accuracy."`
- Replace: `"Ask ALL preference questions that would change the quote by more than 5% in materials or labor. Do not cap yourself — if 8 questions are needed, ask 8."`

### Step 3: Add scope readiness check (engine.py)

**File:** `backend/question_trees/engine.py`, add a new method to `QuestionTreeEngine` class

Add this method after `suggest_additional_questions()`:

```python
def check_scope_readiness(self, job_type: str, description: str,
                          answered_fields: dict) -> dict:
    """
    Evaluate whether we have enough information to generate an accurate quote.
    
    Returns:
        {
            "status": "ready" | "needs_questions" | "insufficient",
            "missing_critical": ["list of critical gaps"],
            "confidence": 0.0-1.0,
            "message": "human-readable explanation"
        }
    """
    try:
        tree = self.load_tree(job_type)
        required = tree.get("required_fields", [])
        
        # Check required fields first
        missing_required = [f for f in required if f not in answered_fields]
        
        # Always require finish
        if "finish" not in answered_fields and "finish" not in missing_required:
            missing_required.append("finish")
        
        if missing_required:
            return {
                "status": "needs_questions",
                "missing_critical": missing_required,
                "confidence": 0.0,
                "message": "Missing required fields: %s" % ", ".join(missing_required),
            }
        
        # AI evaluation of scope completeness
        answered_summary = "\n".join(
            "  - %s: %s" % (k, v)
            for k, v in answered_fields.items()
            if not str(k).startswith("_")
        )
        
        prompt = (
            "You are a metal fabrication estimator reviewing a job scope before generating a quote.\n\n"
            "Job type: %s\n"
            "Customer description:\n\"\"\"%s\"\"\"\n\n"
            "Fields answered so far:\n%s\n\n"
            "EVALUATE: Do you have enough information to generate an accurate quote "
            "(within 15%% of reality)? Consider:\n"
            "- Are all critical dimensions specified or unambiguously implied?\n"
            "- Is the mounting/installation method clear?\n"
            "- Is the material fully specified (type, thickness)?\n"
            "- Is the finish specified?\n"
            "- Are there any components the customer might supply vs us fabricating?\n"
            "- Is indoor/outdoor use clear?\n\n"
            "Return ONLY valid JSON:\n"
            "{\"status\": \"ready\"|\"needs_questions\", "
            "\"missing_critical\": [\"list of gaps\"], "
            "\"confidence\": 0.0-1.0, "
            "\"message\": \"brief explanation\"}"
            % (job_type, description, answered_summary)
        )
        
        text = call_fast(prompt, timeout=30)
        if text is None:
            # Can't reach AI — fall through with basic check
            return {
                "status": "ready" if not missing_required else "needs_questions",
                "missing_critical": missing_required,
                "confidence": 0.5,
                "message": "AI unavailable — basic field check only",
            }
        
        # Parse response
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        
        import json as _json
        parsed = _json.loads(cleaned)
        if not isinstance(parsed, dict):
            return {"status": "ready", "missing_critical": [], "confidence": 0.5, "message": "Parse error"}
        
        return {
            "status": parsed.get("status", "ready"),
            "missing_critical": parsed.get("missing_critical", []),
            "confidence": float(parsed.get("confidence", 0.5)),
            "message": parsed.get("message", ""),
        }
    except Exception as e:
        logger.warning("Scope readiness check failed: %s", e)
        return {"status": "ready", "missing_critical": [], "confidence": 0.5, "message": str(e)}
```

### Step 4: Wire scope readiness into the calculate endpoint

**File:** `backend/routers/quote_session.py`, function `calculate_materials()`

After the completion check (the `if not completion["is_complete"]:` block), and BEFORE running the calculator, add:

```python
# Scope readiness check — does Opus have enough info to quote accurately?
description = str(current_params.get("description", "") or "")
scope_check = engine.check_scope_readiness(job_type, description, current_params)
logger.info("SCOPE CHECK: %s (confidence=%.2f) — %s",
            scope_check["status"], scope_check["confidence"], scope_check["message"])

if scope_check["status"] == "needs_questions" and scope_check.get("missing_critical"):
    # Generate questions for the missing gaps
    additional_qs = engine.suggest_additional_questions(
        job_type, description, current_params,
        [q["id"] for q in engine.get_all_questions(job_type)]
    )
    if additional_qs:
        return {
            "session_id": session_id,
            "status": "needs_more_info",
            "scope_check": scope_check,
            "additional_questions": _serialize_questions(additional_qs),
            "message": "More information needed for an accurate quote. Please answer the additional questions.",
        }
```

### Step 5: Handle the new response in the frontend

**File:** `frontend/js/api.js` or equivalent frontend file that calls `/calculate`

Find where the frontend handles the `/calculate` response. Add handling for the new `needs_more_info` status:

When the response has `status: "needs_more_info"`, display the `additional_questions` to the user the same way the initial questions are displayed. When the user answers them, POST to `/{session_id}/answer` with the answers, then retry `/calculate`.

Look at how the existing question display works in the frontend and replicate that pattern. The additional questions have the same schema as tree questions (id, text, type, options, hint).

### Step 6: Update tests

**File:** `tests/` — find and update relevant test files

1. Update any test that checks the extraction prompt text — it now says "CONSERVATIVE" not "AGGRESSIVE"
2. Add a test for `check_scope_readiness()` — mock the Claude call, verify it returns the right structure
3. Update any test that checks `suggest_additional_questions()` max count — now 8 not 3
4. Run the full test suite: `python -m pytest tests/ -v`

## Constraints
- Do NOT modify question tree JSON files — the fix is in how Opus uses them, not in adding more static questions
- Do NOT add Python code that makes assumptions or fills in defaults — the entire point is to ASK not GUESS  
- Do NOT change the Opus "full package" prompt or the calculator logic — this prompt is ONLY about the intake/question phase
- The scope readiness check must NOT block quotes when AI is unavailable — fall through gracefully
- All changes are in `engine.py`, `quote_session.py`, and frontend JS — no new files needed
- Keep the `call_fast` model for extraction and questions — these are fast tasks, not deep reasoning

## Verification
1. Start a new sign_frame session with: "I need to build a sign out of aluminum. It will be a circle shape, 5' in diameter, each layer of the design will have different heights from the base layer. It will have a 5 inch side and a full back with mounting."
2. Verify extraction does NOT assume: monument mount, post count, layer count, finish type, material grade
3. Verify at least 5 follow-up questions are generated, including: mounting method, finish, material thickness, indoor/outdoor, layer count
4. Verify the scope readiness check fires and returns `needs_questions` before allowing calculation
5. Run `python -m pytest tests/ -v` — all existing tests pass
6. Run the same description through led_sign_custom tree — verify similar conservative extraction
