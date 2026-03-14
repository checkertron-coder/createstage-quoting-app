# CC Prompt: Universal Intake System — Replace 25 Trees With One AI Loop

## Problem
The app has 25 hardcoded question tree JSON files (`backend/question_trees/data/*.json`). When a user describes a project, the system:
1. Calls `detect_job_type()` to guess which tree to use
2. Routes to that tree's preset questions
3. Uses `_match_option()` to force-fit Opus's extraction into tree options

This creates 3 critical failures:
- **Same project, different experience**: A sign described with "LED" goes to `led_sign_custom.json`, without "LED" goes to `sign_frame.json` — completely different questions, completely different quote
- **Garbage questions**: Trees ask things like "sign panel weight?" (that's the AI's job to calculate) and "height above ground?" (irrelevant at quoting stage)
- **Hallucinated assumptions**: The extraction prompt tells Opus to pick from tree options, so Opus GUESSES "monument mount" and "4+ layers" when the user never said any of that

## Acceptance Criteria
1. No question tree JSON files are used during intake (they can stay in the repo but must not be loaded)
2. `detect_job_type()` is still called (needed for calculator routing) but does NOT determine questions
3. All questions come from ONE Opus call that reads the description + photos and generates project-specific questions
4. The frontend receives the same response shape it gets today (`next_questions`, `extracted_fields`, `completion`, `is_complete`)
5. The `/answer` endpoint generates NEW follow-up questions based on accumulated answers (not tree lookups)
6. The `/calculate` endpoint still works — it uses `job_type` to pick the right calculator
7. All existing tests that test tree-specific behavior should be skipped/marked, not deleted
8. The Hacienda test case ("5-foot diameter circular aluminum sign for La Hacienda restaurant") must produce relevant questions about: mounting method, indoor/outdoor, finish details, sign thickness, installation scope — NOT sign weight, height above grade, or monument vs post mount

## Architecture

### New file: `backend/question_trees/universal_intake.py`

This replaces the tree-based intake with a single AI-driven loop.

```python
"""
Universal Intake Engine — replaces 25 job-type trees with one AI loop.

The system asks Opus to:
1. Parse the description and extract what's KNOWN (only what the user explicitly stated)
2. Identify what's UNKNOWN but needed to quote accurately  
3. Generate 5-10 questions ranked by impact on quote accuracy
4. Evaluate readiness: can we quote yet, or do we need more info?
"""

# --- Core Data Structures ---

# Universal project state — replaces tree field tracking
# {
#   "known_facts": {"material": "aluminum", "shape": "circular", "diameter": "5 feet"},
#   "inferred_facts": {"outdoor_use": "likely - restaurant sign"},  
#   "unknowns": ["mounting_method", "material_thickness", "finish_details"],
#   "assumptions": [],
#   "readiness": {"score": 0.45, "status": "needs_questions", "accuracy_band": "±30%"}
# }

UNIVERSAL_INTAKE_PROMPT = """You are a construction/fabrication quoting assistant. A customer has described a project. Your job is to understand what they need and figure out what information is missing before we can generate an accurate quote.

SHOP CONTEXT:
{shop_context}

PROJECT DESCRIPTION:
\"\"\"{description}\"\"\"

{photo_context}

WHAT YOU MUST DO:

1. EXTRACT KNOWN FACTS — ONLY things the customer explicitly stated. Do NOT infer, guess, or assume.
   - If they said "aluminum sign" → material: aluminum is KNOWN
   - If they said "5 feet diameter" → diameter: 5 feet is KNOWN  
   - If they did NOT mention mounting → mounting is UNKNOWN (do NOT guess "monument" or "post")

2. LIST UNKNOWNS — What information is missing that would change the quote by more than 5%?

3. GENERATE QUESTIONS — Ask 5-10 questions about the unknowns, ranked by how much they'd change the final price.
   Each question should be:
   - Specific to THIS project (not generic)
   - Answerable by the customer (don't ask technical fabrication questions they wouldn't know)
   - High-impact on price (mounting method matters more than edge radius)

4. EVALUATE READINESS — Can we quote this yet?
   - "ready" = we have enough for a ±15% accurate quote
   - "needs_questions" = missing info would swing the price more than 15%
   - "needs_critical_info" = we can't even ballpark this without more info

QUESTION TYPES:
- "choice" = provide 3-6 options (use when there are clear categories)
- "text" = free text (use for dimensions, descriptions, custom specs)  
- "boolean" = yes/no
- "measurement" = numeric with unit

RULES:
- NEVER ask about things that are standard trade practice (weld sequence, joint prep, deburring)
- NEVER ask the customer to calculate things (weight, material quantities, labor hours)
- NEVER ask about things already stated in the description
- DO ask about: mounting/installation, indoor vs outdoor, finish specifics, dimensions not yet given, scope boundaries (build only vs build+install), material grade/thickness when multiple options exist
- Questions should sound like a human estimator talking to a customer, not a form

Return ONLY valid JSON:
{{
  "known_facts": {{"key": "value"}},
  "inferred_facts": {{"key": "value — reason"}},
  "unknowns": ["list", "of", "missing", "info"],
  "questions": [
    {{
      "id": "unique_snake_case_id",
      "text": "Question text as shown to customer",
      "type": "choice|text|boolean|measurement",
      "options": ["only", "for", "choice", "type"],
      "hint": "Optional helper text",
      "required": true,
      "impact": "high|medium|low",
      "reason": "Why this matters for the quote"
    }}
  ],
  "readiness": {{
    "score": 0.0-1.0,
    "status": "ready|needs_questions|needs_critical_info",
    "accuracy_band": "±XX%",
    "explanation": "What we can and can't estimate right now"
  }}
}}"""

FOLLOWUP_PROMPT = """You are a construction/fabrication quoting assistant continuing an intake conversation.

SHOP CONTEXT:
{shop_context}

PROJECT DESCRIPTION:
\"\"\"{description}\"\"\"

{photo_context}

WHAT WE ALREADY KNOW:
{known_facts_summary}

QUESTIONS ALREADY ASKED AND ANSWERED:
{qa_history}

WHAT YOU MUST DO:

1. Update the known facts with new information from the answers
2. Re-evaluate what's still unknown
3. Generate 0-5 NEW follow-up questions (only if they'd change the quote by >5%)
4. Re-evaluate readiness — are we ready to quote now?

If we have enough information to produce a ±15% accurate quote, set readiness.status = "ready" and return an empty questions array.

RULES:
- Do NOT re-ask questions already answered
- Do NOT ask low-impact questions just to fill space — if we're ready, we're ready
- Each new question must be justified by what the previous answers revealed

Return ONLY valid JSON with the same schema as before."""
```

### Changes to `backend/routers/quote_session.py`

#### `/start` endpoint changes:
1. Keep `detect_job_type()` call (needed for calculator routing later)
2. Replace ALL tree-based extraction with one call to `universal_intake.py`:
   - Call Opus with `UNIVERSAL_INTAKE_PROMPT` 
   - Pass description + photo observations
   - Get back: `known_facts`, `questions`, `readiness`
3. Map `known_facts` to `extracted_fields` in the response (frontend compatibility)
4. Map `questions` to `next_questions` in the response (frontend compatibility)
5. Build `completion` from `readiness`:
   - `is_complete` = `readiness.status == "ready"`
   - `completion_pct` = `readiness.score * 100`
   - `required_total` = len(questions) + len(known_facts)
   - `required_answered` = len(known_facts)
6. Store the full project state (known_facts, inferred_facts, unknowns, readiness) in `params_json`
7. Remove: tree loading, `extract_from_description()`, `_enforce_conservative_extraction()`, `get_next_questions()`, `suggest_additional_questions()`, all the injected questions (material, finish, electronics)

#### `/answer` endpoint changes:
1. When answers come in, call Opus with `FOLLOWUP_PROMPT`:
   - Pass: original description, known facts so far, Q&A history, photos
   - Get back: updated known_facts, new questions (if any), updated readiness
2. If `readiness.status == "ready"` → set `is_complete = True`
3. If more questions needed → return them as `next_questions`
4. Store full project state in `params_json` including all Q&A history
5. Remove: tree-based `get_next_questions()`, `get_completion_status()`

#### `/calculate` endpoint:
- Keep as-is. It uses `job_type` from the session to pick the calculator.
- The calculator receives `params_json` which now has `known_facts` + all answers
- The `description` field is still in params_json (we set it during `/start`)
- Calculators already fall back to `_try_ai_cut_list()` which uses the description

### Shop context (for now):
```python
def get_shop_context() -> str:
    """Minimal shop context — just hourly rate for Phase 1."""
    return (
        "Shop type: Metal fabrication\n"
        "Shop rate: $125/hour\n"  
        "Mobile/site rate: $145/hour\n"
        "Location: Chicago, IL\n"
        "Capabilities: MIG welding, stick welding, flux core, cutting, grinding, "
        "bending, plasma cutting, basic CNC\n"
        "Note: This is a general metal fab shop. The AI should ask about ANY "
        "processes that might need to be subcontracted (powder coating, anodizing, "
        "laser cutting, CNC machining, etc.)"
    )
```

## Steps

1. Create `backend/question_trees/universal_intake.py` with:
   - `UNIVERSAL_INTAKE_PROMPT` and `FOLLOWUP_PROMPT` strings
   - `generate_intake_questions(description, photo_urls, photo_observations)` → calls Opus, returns parsed JSON
   - `generate_followup_questions(description, known_facts, qa_history, photo_observations)` → calls Opus, returns parsed JSON  
   - `get_shop_context()` → returns shop context string
   - `build_completion_from_readiness(readiness, known_facts, questions)` → returns frontend-compatible completion dict
   - `build_extracted_fields_from_known(known_facts)` → returns frontend-compatible extracted_fields dict

2. Modify `backend/routers/quote_session.py` `/start` endpoint:
   - Keep `detect_job_type()` (line ~87) 
   - Replace lines ~103-180 (tree loading, extraction, photo extraction, next_questions, injected questions) with:
     ```python
     from ..question_trees.universal_intake import (
         generate_intake_questions, build_completion_from_readiness,
         build_extracted_fields_from_known,
     )
     # Run universal intake
     intake = generate_intake_questions(
         request.description, photo_urls, photo_observations=""
     )
     known_facts = intake.get("known_facts", {})
     questions = intake.get("questions", [])
     readiness = intake.get("readiness", {})
     
     extracted_fields = build_extracted_fields_from_known(known_facts)
     next_questions = questions  # Already in correct format
     completion = build_completion_from_readiness(readiness, known_facts, questions)
     ```
   - Store project state in params_json:
     ```python
     merged_for_storage = {
         "description": request.description,
         "_known_facts": known_facts,
         "_inferred_facts": intake.get("inferred_facts", {}),
         "_unknowns": intake.get("unknowns", []),
         "_readiness": readiness,
         "_qa_history": [],
     }
     merged_for_storage.update(known_facts)  # Flat keys for calculator compat
     ```
   - Handle photos: if photo_urls exist, extract observations first via `call_vision_multi`, then include in the Opus intake call as photo_context

3. Modify `/answer` endpoint:
   - Replace tree-based logic with:
     ```python
     from ..question_trees.universal_intake import (
         generate_followup_questions, build_completion_from_readiness,
     )
     # Build QA history
     qa_history = list(current_params.get("_qa_history", []))
     qa_history.append({"answers": request.answers})
     
     # Update known facts with new answers
     known_facts = dict(current_params.get("_known_facts", {}))
     known_facts.update(request.answers)
     
     # Ask Opus for follow-up
     followup = generate_followup_questions(
         description=current_params.get("description", ""),
         known_facts=known_facts,
         qa_history=qa_history,
         photo_observations=current_params.get("photo_observations", ""),
     )
     
     new_known = followup.get("known_facts", {})
     known_facts.update(new_known)
     new_questions = followup.get("questions", [])
     readiness = followup.get("readiness", {})
     completion = build_completion_from_readiness(readiness, known_facts, new_questions)
     
     # Update params
     current_params["_known_facts"] = known_facts
     current_params["_qa_history"] = qa_history
     current_params["_readiness"] = readiness
     current_params.update(known_facts)  # Flat keys for calculator
     ```

4. Do NOT modify:
   - `backend/calculators/` — all calculators stay as-is
   - `backend/calculators/registry.py` — still routes by job_type
   - `backend/routers/ai_quote.py` — still generates full-package quotes
   - `frontend/` — nothing changes, same response shapes
   - `backend/question_trees/data/*.json` — leave files, just don't load them

5. Update `backend/question_trees/engine.py`:
   - Keep `detect_job_type()` function (still needed)
   - Keep `extract_from_photos()` / `call_vision_multi()` (still needed for photo observations)
   - The `QuestionTreeEngine` class methods are no longer called from quote_session.py but don't delete — other code may reference them

6. Run tests: `python -m pytest tests/ -x --tb=short 2>&1 | tail -30`
   - Skip/xfail any tests that specifically test tree-based extraction
   - All calculator tests should still pass
   - All auth/session tests should still pass

## Constraints
- Do NOT delete any files — just stop importing/calling tree-based functions from quote_session.py
- Do NOT modify calculators — they receive params_json and work with whatever keys are there
- Do NOT modify frontend — response shapes must match exactly
- The `job_type` field in the session is still set by `detect_job_type()` — calculators need it
- Use `call_fast()` for the intake Opus call (it's already configured to use claude-opus-4-6)
- JSON parsing from Opus: strip markdown fences, handle partial JSON gracefully
- If Opus call fails, fall back to returning just the material + finish injected questions (never crash)

## Verification
1. Start the app: `uvicorn backend.main:app --reload`
2. Create a new quote with description: "I need a 5-foot diameter circular aluminum sign for a restaurant called La Hacienda. It will display the restaurant name and logo with mounting."
3. Verify: NO questions about "sign panel weight", "height above grade", "monument vs post mount", "number of layers", "4+ layers"
4. Verify: Questions ARE about mounting method, indoor/outdoor, finish type, material thickness, build+install or build only, lighting/illumination
5. Answer 2-3 questions, verify follow-up questions make sense based on answers
6. Click "Calculate Quote" when ready, verify calculator runs and produces a material list
7. Run full pipeline through PDF generation — verify it still works end to end
