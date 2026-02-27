# Session 1 — Foundation: Auth, Schema, Onboarding, Data Seed Script

## Before You Start
1. Read `CLAUDE.md` — this is your architecture bible
2. Read `BUILD_LOG.md` — this is what's been done before
3. Run `pytest tests/ -v` — fix anything failing before you touch code
4. Read the existing `backend/models.py` — understand what's there

---

## Your Mission This Session

Build the foundation everything else depends on. Three deliverables:

### Deliverable 1 — Database Schema Migration
Add the v2 tables to `backend/models.py` using the exact schema in CLAUDE.md.

**New tables to add:**
- `users` — multi-tenant shop accounts (see CLAUDE.md schema)
- `auth_tokens` — JWT refresh token storage
- `quote_sessions` — conversation state across the pipeline
- `hardware_items` — parts pricing with 3-option sourcing
- `historical_actuals` — labor accuracy tracking

**Existing tables to extend:**
- `quotes` — add `user_id`, `session_id`, `inputs_json`, `outputs_json`, `selected_markup_pct`, `pdf_url`

**Rules:**
- Use Alembic for migrations. If Alembic isn't set up, set it up first.
- DO NOT drop existing tables or columns — only add
- The existing `JobType` enum in models.py is wrong — replace it with the V2_JOB_TYPES list from CLAUDE.md, but as a VARCHAR field, not an enum (so adding new types doesn't require a migration)
- Test: migration runs clean on a fresh DB AND on the existing DB without data loss

### Deliverable 2 — Auth System
Implement email/password auth with JWT tokens.

**Files to create:**
- `backend/auth.py` — JWT creation/validation, password hashing
- `backend/routers/auth.py` — API endpoints

**Endpoints to implement:**
```
POST /api/auth/register     — email + password → creates user, returns JWT
POST /api/auth/login        — email + password → returns access + refresh tokens
POST /api/auth/refresh      — refresh token → new access token
POST /api/auth/guest        — no args → creates provisional account, returns JWT + session_id
GET  /api/auth/me           — JWT → returns current user profile
PUT  /api/auth/profile      — JWT → update shop name, address, rates, logo_url
```

**Provisional account flow:**
- `POST /api/auth/guest` creates a user with `is_provisional=True`, generates a random email placeholder, returns a JWT
- User can immediately start quoting
- `POST /api/auth/register` can be called later to claim the account (sets real email, password, `is_provisional=False`)
- Quotes created with the provisional user_id stay attached

**Libraries:** `python-jose[cryptography]` for JWT, `passlib[bcrypt]` for passwords
Add both to `requirements.txt`

**Security:**
- Access tokens: 15 minute expiry
- Refresh tokens: 30 day expiry, stored hashed in `auth_tokens` table
- Never return password hash in any response
- Validate JWT on all protected endpoints via FastAPI dependency

### Deliverable 3 — Data Seed Infrastructure
Build the pipeline for loading Burton's historical invoices into the materials table.

**Files to create:**
- `data/` directory
- `data/seed_from_invoices.py` — reads JSON from `data/raw/`, inserts into `material_prices` and `historical_actuals`
- `data/raw/.gitkeep` — placeholder for invoice data (actual files are gitignored)
- `data/README.md` — instructions for Burton to add invoice data

**Seed script behavior:**
- Reads from `data/raw/*.json` files (Burton will drop invoices here after Checker processes them)
- Each file: `{ "material_type": "sq_tube_2x11ga", "price_per_foot": 3.45, "supplier": "Osorio", "date": "2024-03-15" }`
- Inserts or updates `material_prices` table — newer prices override older ones
- Prints summary: "Loaded X material prices, Y already current"
- Non-destructive: never deletes existing prices, only adds/updates

---

## Acceptance Tests to Write

Create `tests/test_session1_schema.py`:
```python
def test_user_table_exists()           # users table in DB
def test_provisional_account_flow()    # guest → quote → claim account
def test_jwt_auth_round_trip()         # register → login → /me returns user
def test_refresh_token_works()         # access expired → refresh → new access
def test_quote_attaches_to_user()      # quote created with JWT has correct user_id
def test_seed_script_runs_clean()      # python data/seed_from_invoices.py with empty raw/ dir
```

---

## What NOT To Build This Session

- Question trees (Session 2)
- Material calculators (Session 3)
- Labor estimator (Session 4)
- Hardware sourcing (Session 5)
- PDF output (Session 6)
- Frontend changes (Session 6)
- Cloudflare R2 integration (Session 3 — but add the env var loading to config.py now)

---

## Environment Variables

Add to `backend/config.py` (load from env, don't hardcode):
```python
JWT_SECRET: str              # Required — fail loudly if missing
JWT_ACCESS_EXPIRE_MINUTES: int = 15
JWT_REFRESH_EXPIRE_DAYS: int = 30
CLOUDFLARE_R2_ACCOUNT_ID: str = ""    # Optional now, required in Session 3
CLOUDFLARE_R2_ACCESS_KEY_ID: str = ""
CLOUDFLARE_R2_SECRET_ACCESS_KEY: str = ""
CLOUDFLARE_R2_BUCKET: str = "createstage-quotes"
GEMINI_MODEL: str = "gemini-2.0-flash"   # Upgradeable via env var
```

---

## When You're Done

Update `BUILD_LOG.md`:
```
## Session 1 — [date]
### Completed
- [list what you built]

### Not completed / blocked
- [list anything you couldn't finish and why]

### Architectural decisions made
- [anything that deviates from CLAUDE.md]

### Tests
- pytest results: X passed, Y failed
```

If you had to make any architectural decision not covered in CLAUDE.md, update CLAUDE.md too.

---

## The One Rule That Overrides Everything

If you hit something ambiguous and have to choose, always choose the option that:
1. Stores more structured data (not freeform text)
2. Does NOT hardcode anything CreateStage-specific
3. Is easiest to test in isolation

When in doubt, write a comment in the code: `# DECISION: [what you chose and why]`
These comments become the audit trail.
