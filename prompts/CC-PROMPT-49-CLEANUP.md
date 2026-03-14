# CC Prompt 49: Test Fixes + Sheet Nesting + Frontend Polish

## Context
We just landed universal intake (P47/48) and a first pass at three fixes (sheet nesting, Other button, edit button). The app works on Railway but has **8 test failures + 71 test errors** that need fixing, and the sheet nesting calculator still overcounts.

**Test summary:** `8 failed, 989 passed, 2 skipped, 71 errors`

Run `python3 -m pytest tests/ --tb=line -q` to see current state.

---

## Fix 1: bcrypt/passlib Test Failures (8 failed + 61 errors)

**Root cause:** `bcrypt==5.0.0` + `passlib` incompatibility. bcrypt 5.x removed the `__about__` module and changed password length enforcement. passlib's `CryptContext` breaks.

**Fix:** In `backend/auth.py`, replace passlib with direct bcrypt usage:

```python
import bcrypt

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8')[:72], bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8')[:72], hashed_password.encode('utf-8'))
```

Remove the `passlib` import and `pwd_context` entirely. Keep everything else in `auth.py` unchanged (JWT, refresh tokens, etc.).

Update `requirements.txt`: remove `passlib[bcrypt]`, keep `bcrypt>=4.0.0`.

**Verify:** All tests in `test_session1_schema.py` should pass, and all 71 `ERROR` tests should resolve (they all fail at app startup due to passlib).

---

## Fix 2: Sheet Nesting Calculator (Backend)

**File:** `backend/calculators/base.py`

**Current problem:** The area-based nesting at line ~329 uses a flat 85% efficiency factor. For a 5' circular sign, this means:
- Two 60" circular panels = 7200 sq in total area
- One 60x120 sheet at 85% = 6120 sq in usable
- Result: 2 sheets (wrong — both circles fit on one 60x120 sheet)

**The real fix:** Opus already tells us the right answer. In its full-package response, Opus includes `sheets_needed` at the CUT LIST level AND often states nesting in assumptions (e.g., "front face + back panel from one 60x120 sheet"). The problem was that the OLD code summed per-piece `sheets_needed` independently. But Opus sometimes returns a TOTAL `sheets_needed` in the response metadata or assumptions.

**What to do:**

1. In `_build_materials_from_full_package()`, after aggregating all cut list pieces into `profile_totals`, check if Opus's full package response includes a top-level or per-material `total_sheets` or `sheets_needed` value. If it does and `trust_opus` is True, use that directly instead of calculating.

2. If no Opus total is available, fall back to area-based nesting BUT use a smarter approach:
   - For each profile, collect all individual piece dimensions (length x width x quantity)
   - Use a simple first-fit-decreasing bin packing: sort pieces by largest dimension descending, place each on the first sheet that fits
   - This handles the circular sign case because two 60" circles on a 60x120 sheet clearly fit side by side

3. As a safety rail: if the calculated sheets > Opus's per-piece sum, use Opus's sum (it's already an overcount, so anything higher is definitely wrong).

**Key constraint:** Don't break the existing tube/bar/angle material paths. Only change the `if is_sheet` branch.

---

## Fix 3: Frontend — Verify "Other" Button and Edit Button Work

CC already added both features in commits `49d7519` and `90c82f0`. **Verify they work correctly:**

1. **"Other" button:** Should appear on every choice question. Clicking it highlights it, shows a text input. The typed value should be collected in `_collectAnswers()` when `selected.dataset.value === '__other__'`.

2. **Edit button:** Clicking Edit on a confirmed field should re-render it as an editable question (not make it disappear). The fix in `90c82f0` stores `_currentJobType` and constructs a generic question — verify this path works by reading the code flow.

3. **If either is broken**, fix it. If both look correct, leave them alone.

---

## Fix 4: Test Errors in `test_photo_extraction.py` (10 errors)

These likely fail at app startup due to the passlib issue (Fix 1). After Fix 1 lands, re-run and check if any photo extraction tests still fail. If they do, check if it's the vision bug (frontend not sending `photo_urls` in `/start` POST body). The backend vision endpoint should work — the issue was in `frontend/js/api.js` not including `photo_urls` in the start request.

Check `frontend/js/api.js` — the `startSession()` function should send `photo_urls` in the POST body to `/api/quote/start`.

---

## Verification

After all fixes:
```bash
python3 -m pytest tests/ --tb=line -q
```

Target: **0 failures, 0 errors** (or at minimum, only failures from missing external API keys, not code bugs).

Also verify the app starts locally:
```bash
cd backend && python3 -m uvicorn main:app --port 8000
```

---

## Do NOT Change
- Universal intake logic (`universal_intake.py`)
- Opus full-package prompt or response parsing (except reading `sheets_needed` total)
- Calculator logic for tubes/bars/angles
- Any pricing formulas or markup calculations
- Frontend styling beyond what's needed for Other button
