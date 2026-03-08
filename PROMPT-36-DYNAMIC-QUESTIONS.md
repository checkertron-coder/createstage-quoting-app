# Prompt 36: Dynamic AI-Suggested Questions

## Problem Statement
The quoting app has 25 question trees for different job types. 16 of them are missing gauge/thickness questions — a fundamental fabrication detail. But the bigger problem isn't just gauge. When a customer describes an LED sign with ESP32 controllers and waterproof enclosures, the question tree has no way to ask about electronics specs, waterproofing ratings, or controller details. When a painter uses this app, the tree can't ask about paint type, number of coats, or surface prep. The static question trees can't anticipate every detail for every trade.

## Acceptance Criteria
After a user submits their job description and the AI extracts fields from the existing question tree:
1. The app makes a second AI call that reads the description + already-extracted fields and identifies 1-3 critical missing details
2. These AI-suggested questions appear in the question flow alongside the tree questions — the user can't tell the difference
3. The user's answers flow into `params_json` and get passed to the cut list / labor AI prompts like any other field
4. If the AI suggests zero questions (everything important is covered), nothing changes — no empty section, no delay

Test: Submit the LoanDepot LED sign description. The system should ask about aluminum gauge AND at least one electronics-related question (LED strip type, power supply specs, ESP32 housing requirements) that the static tree doesn't cover.

Test: Submit a simple mild steel railing description. The system should suggest gauge/thickness if the tree doesn't already ask for it.

Test: Submit a description that the tree fully covers (cantilever gate with all details specified). Dynamic questions should return empty — no redundant questions.

## Constraint Architecture
- **ONLY modify:** `backend/question_trees/engine.py` (add new method) and `backend/routers/quote_session.py` (call it during session start)
- **DO NOT modify:** Any existing question tree JSON files. Do not touch `_build_extraction_prompt`, `_normalize_extracted_fields`, or `get_next_questions`
- **DO NOT modify:** Frontend code — the existing `_renderQuestions()` in `quote-flow.js` already renders any question object that has `id`, `text`, `type`, and optionally `options`. AI-suggested questions just need to match this schema.
- API call budget: ONE additional `call_fast()` call with timeout=30
- Max 3 suggested questions per session
- AI-suggested question IDs must be prefixed with `_ai_` to avoid collision with tree question IDs (e.g., `_ai_material_gauge`, `_ai_led_type`)

## Decomposition

### Chunk 1: AI Question Suggestion Method
Add a new method to the `QuestionTreeEngine` class in `engine.py`:
- `suggest_additional_questions(job_type, description, extracted_fields, tree_questions)`
- Calls `call_fast()` with a prompt that provides: the job description, the fields already extracted, and the list of tree question topics already covered
- The prompt asks Opus to identify 1-3 critical fabrication/engineering details NOT covered by the existing questions that would materially affect the quote
- Returns a list of question dicts matching the tree question schema: `{"id": "_ai_xxx", "text": "...", "type": "choice"|"text"|"number", "options": [...] (if choice), "required": false, "hint": "...", "source": "ai_suggested"}`

### Chunk 2: Integration into Session Start
In `quote_session.py`, after the existing `engine.extract_from_description()` and `engine.get_next_questions()` calls in `start_session()`:
- Call `engine.suggest_additional_questions()`
- Append the returned questions to `next_questions`
- That's it — the frontend already renders whatever is in `next_questions`

### Chunk 3: Ensure AI-Suggested Answers Flow Through
In `answer_questions()`, AI-suggested field answers (prefixed `_ai_`) will already be stored in `params_json` through the existing `current_params.update(request.answers)` logic. Verify that the `_build_prompt()` in `ai_cut_list.py` includes them in the `PROJECT INFO` section — it already iterates `fields.items()` and skips keys starting with `_`, so change the skip condition: skip keys starting with `__` (double underscore) instead of `_`, OR specifically don't skip `_ai_` prefixed keys.

## Evaluation Design

### Test 1: LED Sign with Electronics
Input description: "Two aluminum LED signs, 38.5x128 inches, laser cut LoanDepot logo, ESP32 controlled programmable LEDs, waterproof outdoor, clear coat finish"
Expected: AI suggests questions about aluminum gauge AND electronics specs (at minimum)
Verify: Questions appear in `/api/session/{id}/answer` response alongside tree questions

### Test 2: Simple Job, Tree Covers Everything  
Input: "12 foot cantilever gate, 10 feet tall, 11 gauge, square tube frame, pickets, powder coat black, full install"
Expected: AI suggests 0 questions (everything specified)
Verify: No extra questions in response

### Test 3: Answers Flow to AI Prompt
After answering AI-suggested questions, run `/api/session/{id}/calculate`
Expected: The AI-suggested field values appear in the cut list AI prompt under PROJECT INFO
Verify: Check Railway logs for the prompt content
