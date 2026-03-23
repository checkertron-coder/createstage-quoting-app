# PROMPT 65 HOTFIX — Alembic Migration Crash Fix

## CONTEXT — READ THIS FIRST

The P65 deploy is crashing on Railway. The app is returning 502. The cause is an Alembic migration conflict. This hotfix must bring the app back online.

---

## 1. PROBLEM STATEMENT

P65 added a migration file (`f2a4b6c8d0e1_add_nda_acceptances_and_invite_code_email.py`) with `down_revision = "e1f2a3b4c5d6"` — an old pre-merge branch revision. The correct current head is `62a3a640df71` (the P61 merge migration). This created multiple heads in the Alembic chain, causing the app to crash at startup before it can serve any requests.

Additionally: because Railway tried to deploy the broken migration before this fix was pushed, the live Railway PostgreSQL database may be in a partially migrated state — the `nda_acceptances` table and/or `used_by_email` column may or may not exist. The fix must handle both cases (clean DB and partially migrated DB).

---

## 2. ACCEPTANCE CRITERIA

- App starts successfully on Railway with no Alembic errors
- `alembic heads` returns exactly one head
- `nda_acceptances` table exists in the live DB
- `used_by_email` column exists on `invite_codes` table
- All existing data is intact — no user records lost
- `GET https://createquote.app/health` returns `{"status": "ok"}`
- Full test suite passes

---

## 3. CONSTRAINT ARCHITECTURE

**In scope:**
- `alembic/versions/f2a4b6c8d0e1_add_nda_acceptances_and_invite_code_email.py` — fix the down_revision
- Any additional migration or fix needed to resolve partial state on Railway DB

**Out of scope — do not touch:**
- Any other migration file
- Any application code from P65 (models, routers, frontend) — that code is correct
- Test files

**Must not break:**
- Existing user accounts and data
- The linear migration chain

**Critical constraint:**
The Railway DB may have already had the `nda_acceptances` table or `used_by_email` column created by the failed deploy. The migration upgrade must be idempotent — use `IF NOT EXISTS` or check-before-create patterns so it doesn't fail if those objects already exist.

---

## 4. DECOMPOSITION

**Chunk 1 — Diagnose current state**
Check the actual Alembic heads conflict. Confirm `f2a4b6c8d0e1` has the wrong `down_revision`. Understand what the correct chain should look like: the P61 merge head (`62a3a640df71`) is the tip before P65. P65's migration must descend from that head.

**Chunk 2 — Fix the migration**
Update `down_revision` in `f2a4b6c8d0e1` to `"62a3a640df71"`. Make the migration's `upgrade()` function idempotent — if `nda_acceptances` already exists or `used_by_email` column already exists, skip gracefully rather than error. This handles the Railway partially-migrated DB state.

**Chunk 3 — Verify the chain**
After the fix, confirm `alembic heads` shows exactly one head. Confirm the full chain traces cleanly from revision `82694c65cf42` through to `f2a4b6c8d0e1`.

**Chunk 4 — Test and push**
Run the full test suite. Push. Verify Railway deploys successfully and `/health` returns 200.

---

## 5. EVALUATION DESIGN

1. Locally: `alembic heads` → exactly one result: `f2a4b6c8d0e1`
2. Railway deploys without crash → `/health` returns `{"status": "ok"}`
3. Railway DB: `nda_acceptances` table exists, `invite_codes.used_by_email` column exists
4. All existing user accounts still present and loginable
5. `python -m pytest tests/ -v` → all pass
