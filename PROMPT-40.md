# PROMPT 40 — "Don't Skip the Good Questions"

## 1. Problem Statement

CS-2026-0059 (LED sign quote) exposed multiple issues that all trace to one flow:
- The text extractor pulled all 4 required fields from a detailed description
- Backend set `is_complete: true` and returned `next_questions` with AI-suggested + electronics questions
- **Frontend checked `is_complete` FIRST and skipped straight to `_runPipeline()`** — never showed the questions
- Result: zero questions asked, Opus hallucinated 72 letter extension tabs (should be ~9-18), priced laser cutting at $195 (should be $400-800+), missed electronics entirely, labeled finish as "Raw Steel" on an aluminum job

Secondary issues:
- `VALID_PROFILES` in `backend/knowledge/validation.py` has zero aluminum profiles (P38 added prices to `material_lookup.py` but never updated validation whitelist)
- Finish extraction doesn't catch "clear coated" from the description text

## 2. Acceptance Criteria

### AC-1: Frontend never skips questions when next_questions exist
- When `is_complete: true` BUT `next_questions.length > 0`, show the questions BEFORE running the pipeline
- Only auto-run pipeline when `is_complete: true` AND `next_questions` is empty
- This is a ~3 line fix in `frontend/js/quote-flow.js` around line 204

### AC-2: Aluminum profiles recognized in validation
- Every `al_*` profile key in `material_lookup.py` MUST also exist in `VALID_PROFILES` in `backend/knowledge/validation.py`
- Add a test that cross-checks: any key in the pricing dict that's not in `VALID_PROFILES` = test failure

### AC-3: Finish extraction catches "clear coat" variants
- In the field extraction logic, ensure these terms map to a clear coat / clear finish:
  - "clear coat", "clear coated", "clearcoat", "clear-coat"
  - "permalac", "lacquer"
  - Already handled in `finishing.py` normalizer but the EXTRACTOR needs to pull "clear coat" from descriptions as the `finish` field value
- The finish field should be extracted from the description text, not just from the question tree answer

### AC-4: is_complete considers AI-suggested questions
- If `suggest_additional_questions()` or electronics injection added questions to `next_questions`, the response should set `is_complete: false` (or add a new field like `has_pending_questions: true`)
- Alternative simpler fix: just fix the frontend (AC-1) and leave backend alone — the backend already returns the questions, the frontend just ignores them

## 3. Constraint Architecture

- **DO NOT modify the question tree JSON files** — the tree structure is fine
- **DO NOT modify calculators** — this is a flow/UI fix, not a calculation fix
- **DO NOT modify `ai_cut_list.py`** — Opus's cut list generation is separate from the question flow
- **Frontend fix is the priority** — AC-1 is the root cause of everything
- Keep the fix MINIMAL — we are not redesigning the question system, just ensuring existing questions actually get shown
- The `suggest_additional_questions()` and electronics injection code from P36/P39 already work — they just need to reach the user

## 4. Decomposition

### Task A: Frontend question flow fix (AC-1) — CRITICAL
File: `frontend/js/quote-flow.js` ~line 204

Current:
```js
if (data.completion && data.completion.is_complete) {
    await this._runPipeline();
} else if (data.next_questions && data.next_questions.length > 0) {
    this._renderClarifyStep(data);
    this._showStep('clarify');
} else {
    this._showProcessing('No questions available...');
}
```

Fix to:
```js
if (data.next_questions && data.next_questions.length > 0) {
    this._renderClarifyStep(data);
    this._showStep('clarify');
} else if (data.completion && data.completion.is_complete) {
    await this._runPipeline();
} else {
    this._showProcessing('No questions available...');
}
```

Questions take priority over auto-complete. Always. If we have questions, show them.

### Task B: Aluminum VALID_PROFILES (AC-2)
File: `backend/knowledge/validation.py` ~line 261

Add all `al_*` keys from `material_lookup.py` to the `VALID_PROFILES` set. Cross-reference by reading the actual keys from the pricing dict — don't hardcode a separate list that can drift.

Add test: `tests/test_prompt40.py` — import both `VALID_PROFILES` and the pricing dict, assert every pricing key is in `VALID_PROFILES`.

### Task C: Finish extraction improvement (AC-3)
In the field extraction logic (likely in `engine.py` `extract_from_description()`), ensure the AI prompt tells the extractor to look for finish-related terms in the description and extract them as the `finish` field. Terms: "clear coat/coated", "powder coat", "paint", "anodize/anodized", "brushed", "polished", "raw/mill finish", "permalac", "lacquer".

If `extract_from_description` already uses an AI call, just update its prompt to explicitly mention finish extraction. If it's keyword-based, add the terms.

## 5. Evaluation Design

### Tests to add (`tests/test_prompt40.py`):
1. **Profile coverage test**: Every key in material_lookup pricing dict exists in VALID_PROFILES
2. **Frontend logic test** (if testable): When is_complete=true and next_questions has items, questions are shown (may need to be manual verification)
3. **Finish extraction test**: A description containing "clear coated aluminum" should extract finish="clear coat" or similar

### Manual verification:
Run a quote with this exact description (CS-2026-0059 description) and confirm:
- Questions are shown (electronics question at minimum)
- No "Unrecognized profile" warnings for al_* profiles
- Finish is NOT "Raw Steel"

### Existing tests:
`pytest tests/` — all must pass, 858+ existing tests unchanged.

### Commit:
`git add . && git commit -m "P40: Fix question skip, aluminum validation, finish extraction" && git push`
