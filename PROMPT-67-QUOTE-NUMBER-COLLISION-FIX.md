# PROMPT-67 — Quote Number Collision Fix

## Problem Statement

New users get a fatal error when saving a quote: `UniqueViolation: duplicate key value violates unique constraint "quotes_quote_number_key"`. The app crashes with a full stack trace instead of completing the quote.

Root cause: `generate_quote_number()` in `backend/routers/quotes.py` generates quote numbers based on total row count (`count + 1`). When a new user's count-based number happens to match an already-existing quote number in the database, the INSERT fails. This is a uniqueness collision bug — the function generates a candidate number but never verifies it's actually free before using it.

Example: 130 total quotes in DB → generates `CS-2026-0130` → but that number already exists → crash.

This breaks the core user flow. Every new user who hits a collision point gets a hard error with no recovery path.

---

## Acceptance Criteria

1. A user can complete a straight railing quote (or any job type) from start to finish without hitting a quote number collision error
2. Quote numbers remain in the format `CS-YYYY-XXXX` (zero-padded 4 digits minimum)
3. If the generated number already exists, the system automatically finds the next available number — no error, no retry required from the user
4. The fix is collision-proof under concurrent load (two users submitting at the same time cannot get the same number)
5. All existing quote numbers in the database are preserved — no migration, no renumbering
6. All existing tests pass

---

## Constraint Architecture

**In scope:**
- `backend/routers/quotes.py` — `generate_quote_number()` function
- `backend/routers/quote_session.py` — any call to `generate_quote_number()` that needs the same fix
- `backend/routers/ai_quote.py` — any call to `generate_quote_number()` that needs the same fix

**Off limits — do not touch:**
- The `quote_number` column definition in `backend/models.py` — unique constraint stays
- Any migration files — the schema is correct, only the generation logic is broken
- Any other router or calculator logic
- Frontend files

**Must not break:**
- Existing quote numbers in the database
- PDF generation (quote_number is embedded in PDF filenames and headers)
- All passing tests

---

## Decomposition

### Part 1 — Understand the collision pattern
The current function generates a number, then immediately tries to INSERT. If the number exists, Postgres raises UniqueViolation and the entire request fails. The fix must detect collisions before the INSERT, not after.

### Part 2 — Fix `generate_quote_number()`
Redesign the function so it:
- Generates a candidate number using a consistent strategy (max existing number + 1, or sequential scan — choose what's most collision-resistant)
- Queries the database to verify the candidate doesn't already exist
- If it does exist, increments and checks again — loops until a free number is found
- Wraps this in a way that handles concurrent requests safely (consider DB-level locking or a retry loop with SELECT FOR UPDATE or similar)

The principle: generate, verify, use — never assume a generated number is free.

### Part 3 — Apply consistently
The fix must be applied wherever `generate_quote_number()` is called. Check all three files in scope. If the function is centralized in `quotes.py` and called from the others, fixing it once may be sufficient — confirm this.

### Part 4 — Add a test
Add at least one test to `tests/test_prompt67.py` that:
- Creates quotes until a potential collision point
- Verifies the next quote gets a unique number without error
- Confirms no UniqueViolation is raised

---

## Evaluation Design

**Before:** Creating a quote when total count = 129 (next would be CS-2026-0130, which already exists) crashes with UniqueViolation

**After:**
- Same scenario: system detects CS-2026-0130 is taken, moves to CS-2026-0131, inserts cleanly
- User sees a completed quote, not an error screen
- `pytest tests/ -q` — 0 failures

**Manual test:**
1. Log into createquote.app with a fresh account
2. Run a straight railing quote end to end
3. Quote saves successfully, no error, quote number assigned correctly

---

## CC Commit & Push
After all changes are made and tests pass:
1. Run `pytest tests/ -q` — confirm 0 failures before committing
2. `git add backend/routers/quotes.py backend/routers/quote_session.py backend/routers/ai_quote.py tests/test_prompt67.py`
3. `git commit -m "P67: fix quote number collision — verify uniqueness before INSERT"`
4. `git push origin main`

## Deployment
Railway will auto-deploy on push. No env var changes needed. No manual steps.

## Brain Sync
After pushing code:
1. `cd ~/brain && git pull origin master`
2. Create `agents/cc-createquote/sessions/YYYY-MM-DD-HHMM.md`:
   - Accomplished: fixed quote number collision bug in generate_quote_number()
   - Root cause: count-based generation didn't verify uniqueness before INSERT
   - Files changed: backend/routers/quotes.py (+ quote_session.py and ai_quote.py if needed), tests/test_prompt67.py
   - Result: all tests passing, quote creation no longer crashes on collision
3. `git add -A && git commit -m "cc-createquote session: P67 quote number collision fix"`
4. `git push origin master`
