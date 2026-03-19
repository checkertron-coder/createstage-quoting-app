# PROMPT-56: Deposit Terms Fix + AI Scope Generation Fix

## Problem Statement

Two regressions are active in production right now, both costing real money:

**Deposit Terms (Critical — money on the line)**
The client-facing proposal PDF says "50% deposit due at signing. Remaining 50% due upon completion." This is wrong. The correct policy is: 50% of labor + 100% of materials up front. Two quotes went out with the wrong deposit language. This must be corrected immediately and cannot regress again.

The wrong text appears in two places:
- `backend/pdf_generator.py` line ~1020 (shop terms, inside `generate_quote_pdf`)
- `backend/pdf_generator.py` line ~1223 (client proposal terms, inside `generate_client_pdf`)

**AI Scope Generation Silently Failing**
The `generate_client_scope()` function in `backend/pdf_generator.py` (line ~414) uses a relative import: `from .claude_client import call_fast`. This relative import fails because `pdf_generator.py` is at the `backend/` package level — not inside a sub-package. The `ImportError` is silently caught, and the fallback returns the raw job description instead of AI-generated prose. The client proposal shows the user's unedited job description — unprofessional and broken.

The fix is to change the import to an absolute import: `from backend.claude_client import call_fast`.

---

## Acceptance Criteria

1. **Deposit language** — both the shop PDF and client proposal PDF show:
   - `"Deposit due at signing: 50% of labor + 100% of materials."`
   - `"Remaining labor balance due upon completion."`
   - No occurrence of "Remaining 50%" anywhere in payment terms
2. **AI scope generation** — when generating a client proposal for a fence/gate job (or any job type), the Scope of Work section contains AI-written professional prose describing the finished product, NOT a copy of the user's original job description text
3. **All existing tests still pass**
4. **No new tests required** — these are targeted fixes, not new features

---

## Constraint Architecture

**In scope:**
- `backend/pdf_generator.py` — two deposit text strings + one import statement
- `tests/` — only if an existing test asserts the wrong deposit text (update it to match the new correct text)

**Off limits:**
- Do not change deposit calculation logic anywhere
- Do not change `backend/claude_client.py`
- Do not change `backend/routers/pdf.py`
- Do not change any other file

**Must not break:**
- The `is_ai_generated` flag and caching logic in `routers/pdf.py` — the import fix should make it work, not restructure it
- The fallback path — if the AI call genuinely fails (no API key, timeout), the fallback to `generate_job_summary()` should still work

---

## Decomposition

### Chunk 1: Fix the relative import in `generate_client_scope()`

In `backend/pdf_generator.py`, inside the `generate_client_scope()` function:

Find:
```
from .claude_client import call_fast
```

Replace with:
```
from backend.claude_client import call_fast
```

This single change makes the AI scope generation work. No other logic changes needed.

### Chunk 2: Fix deposit text — shop PDF

In `backend/pdf_generator.py`, inside `generate_quote_pdf()` (line ~1020):

Find the payment terms line that reads:
```
"Payment terms: 50% deposit due at signing. Remaining 50% due upon completion."
```

Replace with:
```
"Payment terms: Deposit due at signing: 50% of labor + 100% of materials. Remaining labor balance due upon completion."
```

### Chunk 3: Fix deposit text — client proposal PDF

In `backend/pdf_generator.py`, inside `generate_client_pdf()` (line ~1223):

Find the terms list entry that reads:
```
"50% deposit due at signing. Remaining 50% due upon completion.",
```

Replace with:
```
"Deposit due at signing: 50% of labor + 100% of materials. Remaining labor balance due upon completion.",
```

### Chunk 4: Search for any other occurrences

After making the above changes, search the entire codebase for `"50% deposit"` and `"Remaining 50%"` — if any other occurrences exist in payment-facing text, fix those too using the same correct language.

### Chunk 5: Update any tests that assert the wrong deposit text

Search `tests/` for the old deposit text strings. If any test asserts `"50% deposit due at signing"` or `"Remaining 50% due upon completion"`, update those assertions to match the new correct text.

---

## Evaluation Design

### Test 1: Deposit text — shop PDF
- Generate a shop PDF for any quote
- Open the PDF and find the payment terms section
- Expected: `"Deposit due at signing: 50% of labor + 100% of materials. Remaining labor balance due upon completion."`
- Not acceptable: any mention of "Remaining 50%"

### Test 2: Deposit text — client proposal PDF
- Generate a client proposal PDF for any quote
- Open the PDF and find the Terms & Conditions section
- Expected: same correct deposit language as above
- Not acceptable: any mention of "Remaining 50%"

### Test 3: AI scope generation
- Generate a client proposal for a fence/gate job (e.g., "12-foot driveway cantilever gate, 2x2 square tube steel frame, horizontal flat bar infill, black powder coat, motor-ready")
- Open the PDF and read the Scope of Work section
- Expected: 2-3 paragraphs of professional prose describing what the client receives — the finished gate, its features, finish quality, etc.
- Not acceptable: the user's raw job description appearing verbatim in the scope section

### Test 4: Regression
- Run `pytest tests/ -x -q`
- Expected: same number of passing tests as before (or more if any test assertions were updated)
- No new failures

---

## Save Point

Commit after all 5 chunks are complete and tests pass:
```
git add -A && git commit -m "P56: Fix deposit terms (50% labor + 100% materials) + fix AI scope import"
```
