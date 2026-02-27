# BUILD_LOG.md — CreateStage Quoting App

## MANDATORY: Read this at the start of every Claude Code session. Write to it at the end.

---

## Current Status: Session 1 complete — auth, schema, seed infra built

**Live URL:** createstage-quoting-app-production.up.railway.app
**Repo:** github.com/checkertron-coder/createstage-quoting-app
**Model:** Gemini 2.0 Flash (upgrade to Gemini 3.1 Pro or Opus 4.6 for v2)
**DB:** PostgreSQL on Railway (online, connected)

---

## v2 Spec
Full spec is at: `~/workspace/QUOTING-APP-SPEC.md`
Read it before starting any session. It is the ground truth.

**Open decisions that BLOCK Session 1:**
- O1: Bayern Software name and API access
- O2: Scope — all 12 job types or start with 5?
- O3: Multi-user auth in v2 or single-user?
- O4: Photo storage (Railway volume / Cloudflare R2 / pass-through only)
- O5: PDF branding (CreateStage-specific or white-labeled from day 1)
- O6: Additional pricing data from Burton before build starts?

---

## Session Log

### Session 1 — 2026-02-27 (Opus 4.6)

#### Completed
- **Deliverable 1 — Database Schema Migration**
  - Added 5 new tables: `users`, `auth_tokens`, `quote_sessions`, `hardware_items`, `historical_actuals`
  - Extended `quotes` table with v2 columns: `user_id`, `session_id`, `inputs_json`, `outputs_json`, `selected_markup_pct`, `pdf_url`
  - Replaced `JobType` enum with VARCHAR — `V2_JOB_TYPES` list in models.py for validation reference
  - Set up Alembic (`alembic/`), initial migration runs clean on fresh DB
  - Migration file: `alembic/versions/82694c65cf42_v2_foundation_...py`

- **Deliverable 2 — Auth System**
  - `backend/auth.py` — JWT creation/validation, bcrypt password hashing, `get_current_user` FastAPI dependency
  - `backend/routers/auth.py` — 6 endpoints: `POST /register`, `POST /login`, `POST /refresh`, `POST /guest`, `GET /me`, `PUT /profile`
  - Provisional account flow works: guest → JWT → quote → claim with real email
  - Access tokens: 15 min, refresh tokens: 30 day (hashed in DB)
  - Wired into `main.py` at `/api/auth/*`

- **Deliverable 3 — Data Seed Infrastructure**
  - `data/seed_from_invoices.py` — reads JSON from `data/raw/`, inserts/updates material_prices and historical_actuals
  - `data/raw/.gitkeep` — placeholder, JSON files gitignored
  - `data/README.md` — instructions for adding invoice data

- **Config updates**
  - `backend/config.py` — added `JWT_SECRET`, `JWT_ACCESS_EXPIRE_MINUTES`, `JWT_REFRESH_EXPIRE_DAYS`, Cloudflare R2 vars, fixed `GEMINI_MODEL` default to `gemini-2.0-flash`

- **Dependencies added**
  - `python-jose[cryptography]==3.3.0`, `passlib[bcrypt]==1.7.4`, `bcrypt==4.1.3`, `pytest==8.1.1`, `pytest-asyncio==0.23.5`
  - Created `.venv/` virtual environment

#### Not completed / blocked
- None — all 3 deliverables complete

#### Architectural decisions made
- `JobType` enum removed entirely, replaced with `String` column + `V2_JOB_TYPES` list constant
- `bcrypt` pinned to 4.1.3 (passlib 1.7.4 incompatible with bcrypt 5.x)
- Used `sqlalchemy.JSON` (not `postgresql.JSONB`) for JSON columns — works on both SQLite and PostgreSQL
- `Quote.customer_id` made nullable (quotes can now exist without a customer, attached to user instead)

#### Tests
- pytest results: **11 passed, 0 failed**
- Test file: `tests/test_session1_schema.py`
- Tests cover: user table, v2 tables, job_type varchar, provisional account flow, JWT round-trip, refresh tokens, quote-user attachment, seed script, duplicate registration, wrong password, profile update

---

## Architectural Decisions (append here when made)

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-27 | 6-stage pipeline (Intake→Clarify→Calculate→Estimate→Price→Output) | AI only in stages 2+4; everything else deterministic |
| 2026-02-27 | Vanilla HTML/CSS/JS frontend, FastAPI backend | Keep it simple, no framework overhead |
| 2026-02-27 | Bayern Software stubbed as interface, not implemented | Phase 3 — but architecture must accommodate |
| 2026-02-27 | Finishing is ALWAYS a separate line item | Most underquoted stage, must be visible |
| 2026-02-27 | JobType enum → VARCHAR + V2_JOB_TYPES list | Adding new job types shouldn't require a migration |
| 2026-02-27 | bcrypt pinned to 4.1.3 | passlib 1.7.4 crashes with bcrypt 5.x |
| 2026-02-27 | JSON columns (not JSONB) for cross-DB compat | Works on SQLite (tests) and PostgreSQL (prod) |
| 2026-02-27 | Quote.customer_id now nullable | v2 quotes attach to users, customer is optional |

