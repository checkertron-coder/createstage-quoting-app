# PROMPT-60: Emergency — Fix App Startup Crash

## Problem Statement

The app is crash-looping on Railway. Every deploy fails immediately — the container starts and stops within seconds. Users cannot log in. The app is completely down.

Two crashes were identified and partially fixed but the app is still not starting:

1. `backend/routers/shop_profile.py` had `from ..gemini_client import call_fast` — gemini_client does not exist. Fixed to `claude_client`.
2. `backend/config.py` Settings class was rejecting unknown env vars (GEMINI_API_KEY, GEMINI_MODEL set in Railway). Fixed with `extra = "ignore"`.

The app is still crashing. There may be additional import errors, missing dependencies, or other startup failures introduced by P58 or P59.

---

## Acceptance Criteria

1. The app starts cleanly on Railway without crash-looping
2. All routes load correctly — auth, quotes, shop_profile, pdf, etc.
3. No import errors, no missing modules, no config validation errors
4. Users can log in successfully
5. All existing tests pass

---

## Constraint Architecture

**In scope:**
- Any file causing startup crashes — imports, config, models, routers
- `requirements.txt` — ensure all required packages are listed
- `backend/config.py` — ensure unknown env vars are ignored
- Any file referencing `gemini_client` — must be changed to `claude_client`

**Off limits:**
- Do not change business logic
- Do not change the database schema
- Do not change auth flow beyond what's needed to fix startup

---

## Decomposition

### Chunk 1: Full startup audit
Run the app locally and capture every error on startup. Fix each one in order:
- Import errors (wrong module names, missing modules)
- Config validation errors (unknown fields, missing required fields)
- Database connection errors (these are expected locally, skip them)
- Any other crash on import

### Chunk 2: Scan for gemini_client references
Search the entire codebase for any remaining references to `gemini_client`. Replace all with `claude_client`. The app uses Claude exclusively — Gemini is not available.

### Chunk 3: Verify requirements.txt is complete
Check that every imported third-party package in the codebase is listed in `requirements.txt`. Add any that are missing.

### Chunk 4: Verify config handles Railway env vars
Railway has these env vars set that may not be in the Settings model: `GEMINI_API_KEY`, `GEMINI_MODEL`. The `Settings` class must have `extra = "ignore"` in its Config class so unknown env vars don't crash startup.

### Chunk 5: Test clean startup
After fixes, verify the app imports cleanly:
```bash
python3 -c "from backend.main import app; print('OK')"
```
This must print `OK` with no errors (database connection errors are acceptable since there's no local DB).

---

## Evaluation Design

### Test 1: Clean import
```bash
python3 -c "from backend.main import app; print('OK')"
```
Expected: prints `OK` (database errors acceptable, import errors not acceptable)

### Test 2: Railway deploy
After pushing, Railway deploy succeeds — no crash loop, container stays up

### Test 3: Login works
User can log in at the production URL

### Test 4: Regression
`pytest tests/ -x -q` — all existing tests pass

---

## Save Point

```
git add -A && git commit -m "P60: Fix startup crash — clean imports, config, requirements"
```
