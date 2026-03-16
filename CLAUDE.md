# CLAUDE.md — CreateStage Fabrication Intelligence Platform
*Read this at the start of EVERY session. This is the definitive reference.*
*Last verified: Prompt 47+ (March 16, 2026)*

---

## 0. How We Build — The Nate B. Jones 5-Primitive Approach

Every prompt and every implementation follows this framework. No exceptions.

### The 5 Primitives
1. **Problem Statement** — What's broken, why it matters, what the user experiences. Plain language. No code.
2. **Acceptance Criteria** — What "done" looks like from the user's perspective. Testable outcomes, not implementation details.
3. **Constraint Architecture** — What files are in play, what's off-limits, what must not break. Guard rails, not blueprints.
4. **Decomposition** — Break the work into logical chunks. Describe WHAT each chunk accomplishes, not HOW to code it. Trust the builder.
5. **Evaluation Design** — How to verify it worked. Real-world test cases, expected before/after.

### The Philosophy: Opus First, Always
- **Opus is the brain. Python is the calculator.** Opus reasons about fabrication (cut lists, labor, build sequences, material selection). Python does deterministic math (pricing, totals, markup, PDF rendering). If you're writing Python code that makes fabrication decisions, you're overriding Opus — stop.
- **Don't build code that second-guesses Opus.** No post-processors that recalculate quantities. No hardcoded rules that override AI output. No Python that adds materials Opus didn't return. The knowledge base is CONTEXT, not curriculum — feed Opus facts (prices, dimensions, shop prefs), not process instructions.
- **Don't teach Opus what it already knows.** Opus knows how to weld. It knows steel comes in 20' sticks. It knows outdoor work needs paint. Only include rules for things Opus CAN'T know: your shop rate, your preferred suppliers, your specific tooling.
- **Fewer rules, better rules** — every rule in an AI prompt is noise that dilutes the rules that matter. If a rule hasn't prevented a real mistake, delete it.
- **TEACH the theory, don't dictate the code** — "outdoor painted steel gets a cleanup pass, not full grinding" is a principle. "Set grind_hours = 2.0" is a crutch. Trust the builder.
- **Scale over specifics** — a fix that only works for "this test case" is worthless. Teach the underlying principle so it works for every job type.

### Anti-Patterns (things that have burned us)
- ❌ Hardcoding hours/minutes for specific job types — breaks on every other job
- ❌ Writing the Python code in the prompt — Claude Code becomes a typist, not a thinker
- ❌ 16 numbered rules in an AI prompt — Opus drowns in noise, misses what matters
- ❌ "For this test case..." — if it only works for one scenario, it's not a fix
- ❌ Telling the AI what answer to produce — it'll parrot it back without understanding
- ❌ Sweeping changes (10+ files) in a single session — compound errors, impossible to untangle (blast radius)
- ❌ Agent running 5+ minutes without human review — stop, check, then continue
- ❌ One massive AGENTS.md — "when everything is marked important, nothing is, and the file rots instantly" (Nate/Anthropic)

### Session Discipline (from Nate's 5 Agent Management Skills)
- **Save point before every prompt session.** `git add . && git commit -m "pre-P{N} save point"` BEFORE running the prompt. Non-negotiable.
- **Fresh conversation per task.** Don't let a login fix drift into a dashboard redesign. Context window = whiteboard being erased from the left while you write on the right.
- **30-message rule.** After ~30 back-and-forth messages, summarize where you are and start fresh. Agent isn't getting dumber — it's running out of room.
- **Screenshots over paragraphs.** A screenshot uses a fraction of the context that three paragraphs of description use. Use them for UI bugs.
- **Progressive disclosure.** CLAUDE.md is the primary doc. FAB_KNOWLEDGE.md, DECISIONS.md, PROMPT-XX files are cross-linked supplements. Don't pile everything into one file.

---

## 1. What This App Is

A metal fabrication quoting platform. It takes job descriptions (text + photos) from fabricators, asks smart domain-specific follow-up questions, does deterministic math for materials and geometry, uses AI only for labor hour estimation, and outputs a professional itemized quote with PDF.

Not a chatbot. Not a generic LLM wrapper. A domain-specific tool that knows how fab shops work.

---

## 2. Current State (v2, Sessions 1-10 + hotfix complete)

### What Works — Full 6-Stage Pipeline + Intelligence Layer
- **Stage 1 — Intake:** Job type detection via keyword matching + Gemini fallback, field extraction from description + photos
- **Stage 2 — Clarify:** 25 question trees (all job types), branching logic, completion tracking, extraction confirmation UI
- **Stage 3 — Calculate:** 25 calculators with AI-first pattern (all try AI cut list from description, fall back to deterministic template math), CustomFab as universal fallback
- **Stage 4 — Estimate:** AI labor estimation with weld process reasoning (TIG/MIG detection, material-specific multipliers), rule-based fallback, finishing builder, historical validator
- **Stage 5 — Price:** Hardware sourcing (25-item catalog), consumable estimation, pricing engine, markup options (0-30%)
- **Stage 6 — Output:** Frontend UI (vanilla JS SPA), PDF generator (fpdf2), quote history, PDF download
- **Intelligence Layer (Session 10):** Description flows to all calculators, AI cut list with 4-step design thinking, weld process reasoning in labor estimation, expanded cut list schema (piece_name, group, weld_process, weld_type, cut_angle)
- **Bid Parser (Session 7):** PDF extraction (pdfplumber), scope extraction (Gemini + keyword fallback), CSI division mapping, job type mapping, dimension extraction, bid-to-session flow
- **Seed Data (Session 8):** 35 material prices from Osorio/Wexler invoices, 6 historical actuals, profile key parser
- **Auth:** JWT access/refresh tokens, guest/register/login, profile management
- **Database:** PostgreSQL on Railway (SQLite for tests), all v2 tables implemented
- **Async AI Processing:** POST `/api/ai/estimate` and `/api/ai/quote` return `job_id` immediately, Gemini runs in background thread, frontend polls `GET /api/ai/job/{job_id}` — prevents Railway 30s proxy 503 timeout
- **Centralized Gemini Client:** All Gemini API calls go through `backend/gemini_client.py` — tiered model selection (fast/deep), unified error handling with 429 retry, structured logging
- **Tests:** 384 passing tests across 15 test files

### Workflow Rule
- Direct code edits to this repo go through Claude Code prompts only. Checker (the OpenClaw AI assistant) diagnoses problems and writes the prompt; Claude Code executes and runs tests. Claude Code has full repo context, runs the test suite, and handles edge cases better than one-off direct edits.

### What's Still Needed
- Live hardware pricing (web search / API)
- ENITEO/SteelXML integration (Phase 3)
- Fusion 360 parametric model generation (Phase 3)

---

## 3. File Map

**Use `find` and `ls` to explore the repo — don't rely on a static map.** Key directories:

- `backend/` — FastAPI app, routers, calculators, AI clients, PDF generator
- `backend/routers/` — auth, quote_session, quotes, pdf, bid_parser, admin, photos, customers, materials, process_rates
- `backend/calculators/` — 25 job-type calculators + base, registry, ai_cut_list, fab_knowledge, labor_calculator, material_lookup
- `backend/question_trees/data/` — 25 JSON question tree files
- `frontend/` — Landing page (index.html), App (app.html), JS (api, auth, quote-flow, app, bid-upload), CSS
- `data/` — Seeded prices, raw invoices, BOM
- `tests/` — 1090+ tests across multiple test files
- `alembic/` — Database migrations


## 4. The 6-Stage Pipeline

```
User Input (text / photo)
    │
    ▼
[Stage 1: INTAKE]  ── engine.py:detect_job_type()
    job_type detected → question tree loaded
    Output: IntakeResult { job_type, confidence, ambiguous }
    │
    ▼
[Stage 2: CLARIFY]  ── engine.py:get_quote_params() + next_questions()
    AI works through question tree, asks only for missing fields
    DO NOT repeat questions already answered in the description
    Output: QuoteParams { job_type, user_id, session_id, fields, photos, notes }
    │
    ▼
[Stage 3: CALCULATE]  ── calculators/{job_type}.py
    AI-first: if description exists, try AI cut list (Gemini) → fallback to deterministic template math
    AI cut list includes design thinking, pattern geometry, weld process determination
    Output: MaterialList { items, hardware, weight, sq_ft, weld_inches, assumptions }
    │
    ▼
[Stage 4: ESTIMATE]  ── labor_estimator.py + finishing.py
    AI receives structured job params → returns JSON of hours per process
    NEVER returns a single total — always per-process breakdown
    Output: LaborEstimate { processes[], total_hours } + FinishingSection
    │
    ▼
[Stage 5: PRICE]  ── pricing_engine.py + hardware_sourcer.py
    Apply shop_rate × hours, material_price × quantity, hardware + consumables
    NO AI INVOLVEMENT HERE
    Output: PricedQuote { materials, hardware, consumables, labor, finishing, subtotals, markup_options }
    │
    ▼
[Stage 6: OUTPUT]  ── pdf_generator.py + frontend/
    Render to UI and PDF
    Output: QuoteDocument + PDFBytes
```

**AI is in Stages 1 (detection), 2 (clarify), 3 (cut list generation, with deterministic fallback), and 4 (labor). Stages 5, 6 are deterministic code.**

---

## 5. Data Contracts Between Stages

**The code is the source of truth.** Read the TypedDicts directly from the source files:
- **Stage 1 → 2:** `IntakeResult` in `backend/question_trees/engine.py`
- **Stage 2 → 3:** `QuoteParams` in `backend/question_trees/engine.py`
- **Stage 3 output:** `MaterialItem`, `HardwareItem`, `MaterialList` in `backend/calculators/base.py`
- **Stage 4 output:** `LaborProcess`, `LaborEstimate` in `backend/labor_estimator.py` + `FinishingSection` in `backend/finishing.py`
- **Stage 5 output:** `PricedQuote` in `backend/pricing_engine.py`

**Key rules:**
- 11 canonical labor processes: layout_setup, cut_prep, fit_tack, full_weld, grind_clean, finish_prep, clearcoat, paint, hardware_install, site_install, final_inspection
- Finishing is NEVER optional — if raw: method="raw", all costs 0
- Labor total is Python-computed sum, NEVER AI-provided
- Markup options: fixed set [0, 5, 10, 15, 20, 25, 30]%


## 6. API Endpoints

**Discover endpoints from the router files** — `backend/routers/*.py`. Key route groups:
- `/api/auth/*` — register, login, refresh, me, profile, validate-code (P53)
- `/api/admin/*` — invite code CRUD (P53)
- `/api/session/*` — start, answer, status, calculate, estimate, price (main pipeline)
- `/api/quotes/*` — CRUD, /mine, /detail, /breakdown, /markup, /{id}/pdf
- `/api/bid/*` — upload, parse-text, quote-items
- `/api/photos/*` — upload (R2 or local fallback)
- `/api/ai/*` — legacy async estimation (job_id polling)
- `/api/customers/*`, `/api/materials/*`, `/api/process-rates/*` — CRUD
- `/` — landing page, `/app` — quoting app (P53), `/health` — health check


## 7. Database Schema (implemented — all tables exist)

### Tables
| Table | Model | Purpose |
|-------|-------|---------|
| `users` | `User` | Multi-tenant shop accounts (email, password_hash, rates, markup) |
| `auth_tokens` | `AuthToken` | JWT refresh token storage (access tokens are stateless) |
| `quote_sessions` | `QuoteSession` | Pipeline conversation state (params_json, stage, status) |
| `quotes` | `Quote` | Final quote records (inputs_json, outputs_json, totals) |
| `quote_line_items` | `QuoteLineItem` | Individual quote line items (v1 structure, still used) |
| `customers` | `Customer` | Customer records (name, company, email, phone) |
| `material_prices` | `MaterialPrice` | Material prices by type (per_lb, per_sqft, per_foot) |
| `process_rates` | `ProcessRate` | Per-process hourly rates |
| `hardware_items` | `HardwareItem` | 3-option hardware sourcing (McMaster, alt1, alt2) |
| `historical_actuals` | `HistoricalActual` | Labor accuracy tracking (estimated vs actual) |
| `bid_analyses` | `BidAnalysis` | Stored bid document extractions |

---

## 8. v2 Job Type List (25 types — all have calculators + question trees)

```python
V2_JOB_TYPES = [
    # Priority A — gates & railings
    "cantilever_gate",          # sliding, with or without motor
    "swing_gate",               # hinged, single or double panel
    "straight_railing",         # flat platform / exterior / ADA
    "stair_railing",            # along stair stringer
    "repair_decorative",        # ornamental iron repair (photo-first)
    # Priority B — structural & architectural
    "ornamental_fence",         # picket/flat bar fence sections
    "complete_stair",           # stringer + treads + landing
    "spiral_stair",             # center column, treads, handrail
    "window_security_grate",    # fixed or hinged security bar grate
    "balcony_railing",          # with or without structural balcony frame
    # Priority C — specialty
    "furniture_table",          # steel base / frame
    "utility_enclosure",        # box fabrication, NEMA rating
    "bollard",                  # vehicle barrier, fixed or removable
    "repair_structural",        # chassis, trailer, structural repair (photo-first)
    "custom_fab",               # freeform, universal fallback (NEVER fails)
    # Priority D — automotive
    "offroad_bumper",           # front/rear bumper for trucks/Jeeps
    "rock_slider",              # rocker panel guards (always pair)
    "roll_cage",                # roll bar / race cage / UTV cage
    "exhaust_custom",           # headers, downpipes, full systems
    # Priority E — industrial & signage
    "trailer_fab",              # flatbed, utility, car hauler trailers
    "structural_frame",         # mezzanine, canopy, portal frame
    "furniture_other",          # shelving, brackets, racks, stands
    "sign_frame",               # post-mount, wall-mount, monument signs
    "led_sign_custom",          # channel letters, cabinet/box signs
    # Priority F — products
    "product_firetable",        # FireTable Pro (BOM-based)
]
```

**Calculator status:** All 25 types have dedicated calculators. Unknown types fall back to `CustomFabCalculator`.

---

## 9. Question Tree JSON Schema

Every job type's question tree lives in `backend/question_trees/data/{job_type}.json`.

```json
{
    "job_type": "cantilever_gate",
    "version": "1.0",
    "display_name": "Cantilever Sliding Gate",
    "required_fields": ["clear_width", "height", "frame_material", "post_count"],
    "questions": [
        {
            "id": "clear_width",
            "text": "What is the clear opening width?",
            "type": "measurement",
            "unit": "feet",
            "required": true,
            "hint": "Measure from post to post",
            "branches": null
        },
        {
            "id": "has_motor",
            "text": "Will this gate have an electric operator?",
            "type": "choice",
            "options": ["Yes", "No", "Not sure"],
            "required": true,
            "hint": null,
            "branches": {
                "Yes": ["motor_brand"],
                "Not sure": ["motor_info_display", "motor_brand"]
            }
        }
    ]
}
```

Field types: `"measurement"` | `"choice"` | `"multi_choice"` | `"text"` | `"photo"` | `"number"` | `"boolean"`

---

## 10. Material Price Lookup Chain

```
MaterialLookup.get_price_per_foot(profile)
    │
    ├── 1. Check seeded prices (data/seeded_prices.json — 35 profiles from Osorio/Wexler)
    │      Returns price + supplier name ("Osorio", "Wexler")
    │
    └── 2. Fallback to hardcoded PRICE_PER_FOOT defaults (market averages)
           Returns price + "market_average" source label
```

**Seeded price file:** `data/seeded_prices.json` — generated by `data/seed_from_invoices.py`
**Source data:** `data/raw/` — Osorio prices, Wexler prices, CreateStage invoices, FireTable BOM
**Price with source:** `MaterialLookup.get_price_with_source(profile)` returns `(price, source_label)` tuple

Profile key format: `{shape}_{dimensions}_{gauge}` — e.g. `sq_tube_2x2_11ga`, `flat_bar_1x0.25`, `angle_3x3x0.1875`

---

## 11. Auth System

- Email + password (bcrypt hash via `passlib[bcrypt]`)
- JWT access tokens (15 min expiry) + refresh tokens (30 day expiry) via `python-jose`
- Provisional accounts: guest → can immediately quote → password set later via register
- PDF download supports `?token=` query param for direct link access
- Auth dependency: `get_current_user` in `backend/auth.py`

---

## 12. AI Model Assignments

All Gemini calls go through `backend/gemini_client.py` with tiered model selection:

| Usage | Tier | Default | Env Override |
|---|---|---|---|
| Job type detection (Stage 1) | fast | `gemini-2.5-flash` | `GEMINI_FAST_MODEL` |
| Field extraction (Stage 2) | fast | `gemini-2.5-flash` | `GEMINI_FAST_MODEL` |
| Photo vision (Stage 2) | fast | `gemini-2.5-flash` | `GEMINI_FAST_MODEL` |
| AI cut list (Stage 3) | deep | `gemini-2.5-flash` | `GEMINI_DEEP_MODEL` |
| Labor estimation (Stage 4) | deep | `gemini-2.5-flash` | `GEMINI_DEEP_MODEL` |
| Bid parsing (Session 7) | deep | `gemini-2.5-flash` | `GEMINI_DEEP_MODEL` |
| Legacy AI quote | deep | `gemini-2.5-flash` | `GEMINI_DEEP_MODEL` |

Model resolution chains (backward-compatible):
- **Fast:** `GEMINI_FAST_MODEL` → `GEMINI_CUTLIST_MODEL` → `gemini-2.5-flash`
- **Deep:** `GEMINI_DEEP_MODEL` → `GEMINI_MODEL` → `gemini-2.5-flash`

Upgrade path: set `GEMINI_DEEP_MODEL=gemini-3.0-flash` to upgrade deep calls without affecting fast detection.

---

## 13. Environment Variables

```bash
# Required
DATABASE_URL=...            # PostgreSQL connection string
GEMINI_API_KEY=...          # Gemini API key
JWT_SECRET=...              # openssl rand -hex 32

# Optional (with defaults)
GEMINI_MODEL=gemini-2.5-flash          # Deep tier fallback
GEMINI_FAST_MODEL=                     # Fast tier primary (default: GEMINI_CUTLIST_MODEL → gemini-2.5-flash)
GEMINI_DEEP_MODEL=                     # Deep tier primary (default: GEMINI_MODEL → gemini-2.5-flash)
JWT_ALGORITHM=HS256
JWT_ACCESS_EXPIRE_MINUTES=15
JWT_REFRESH_EXPIRE_DAYS=30

# Future — Cloudflare R2 (not yet integrated)
CLOUDFLARE_R2_ACCOUNT_ID=...
CLOUDFLARE_R2_ACCESS_KEY_ID=...
CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
CLOUDFLARE_R2_BUCKET=createstage-quotes
```

---

## 14. Deploy Instructions

### Railway (production)
```bash
# Deploy via Railway CLI or GitHub integration
# Config: railway.json sets start command
# Start: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
# Builder: NIXPACKS
# Restart: ON_FAILURE (max 3 retries)
```

Production URL: `createstage-quoting-app-production.up.railway.app`

### Local Development
```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run
uvicorn backend.main:app --reload

# Seed material prices (optional — from invoice data)
python data/seed_from_invoices.py

# DB migration
alembic upgrade head
```

---

## 15. Testing

```bash
pytest tests/ -v          # Run all tests
pytest tests/test_X.py -v # Run specific file
```

- pytest, SQLite in-memory (conftest.py), fixtures: `auth_headers`/`guest_headers`
- **1090+ tests** as of P53. Rule: **NEVER push failing tests.**

---

## 16. Python 3.9

**Do NOT use `str | None`** — use `Optional[str]` from typing.
Key constraint: `bcrypt==4.1.3` pinned (passlib crashes with bcrypt 5.x). Read `requirements.txt` for full deps.


## 18. Hardcoded Rules

1. **Finishing is NEVER optional.** Every quote has a finishing section. If raw: `method="raw"`, all costs 0.
2. **Labor is always per-process.** Never a single total from AI — always breakdown by 11 canonical processes.
3. **Consumables are first-class line items.** Welding wire, grinding discs, gas estimated from weld_linear_inches + sq_ft.
4. **Markup options always 0-30%.** Dict keys: `"0"`, `"5"`, `"10"`, `"15"`, `"20"`, `"25"`, `"30"`.
5. **No CreateStage-specific branding in DB/API.** Only in user profile data.

---

## 19. Integration Rules (Learned from Prompts 13-15)

1. **Building a module is not done until it's CALLED in the pipeline.** After creating any new function, grep the codebase to verify it's called in the actual request flow (not just imported). If `grep -rn "function_name" backend/routers/ backend/calculators/` shows zero calls, you're not done.

2. **Fallback logic must not override the fix.** If you build a new data source to replace an old one, the old source must be REMOVED or SUBORDINATED. Never write `if old_source: return old_data` after building new_data — the old source will always exist and will always win.

3. **FAB_KNOWLEDGE.md is SUPPLEMENTAL, not primary.** Structured data in `backend/knowledge/` is the source of truth. FAB_KNOWLEDGE.md provides prose context for build sequences only. If structured data and FAB_KNOWLEDGE.md contradict, structured data wins. Always.

4. **Test integration, not just units.** After any change, the real test is: generate a quote and verify the output. Unit tests passing means nothing if the integration is broken.

5. **Validation must be in the hot path.** `validate_full_output()` must run on every quote before it reaches PDF generation. If validation isn't in the hot path, it doesn't exist.

---

## 20. What Not To Touch

- `backend/weights.py` — working correctly, used by all calculators
- `backend/database.py` — working correctly, shared by all modules
- `requirements.txt` — add to it, don't remove without flagging
- Existing SQLAlchemy table definitions in `models.py` — extend them, don't replace (data migration required)
- `data/seeded_prices.json` — generated output, regenerate via `python data/seed_from_invoices.py`

---

## 21. Defensive Engineering Rules (Agent Standing Orders)

These rules exist because agents won't think to ask about them. Enforce on every session.

### Error Handling — No Blank Screens, Ever
- Every API call from frontend must have a `.catch()` or `try/catch` with a **user-visible error message**
- Never show a white page, raw JSON error, or browser console error to the user
- Payment failures, server timeouts, API rate limits → friendly message + retry option
- If Opus/Gemini returns empty or garbage → show "AI is thinking harder, please wait" or fall back gracefully
- **Rule:** If `fetch()` or `httpx` can fail, it MUST be wrapped with user-facing error handling

### Data Security — Row-Level Isolation
- Every database query that returns user data MUST filter by `user_id`
- No endpoint should ever return another user's quotes, sessions, or customer data
- **Never log** customer emails, payment info, or API keys to stdout/file
- API keys go in env vars ONLY — never hardcoded, never in prompts, never in DB
- JWT secrets: minimum 256-bit, rotated if compromised
- **Rule:** Before adding any new GET endpoint, verify it filters by authenticated user

### Scale Expectations
- Target: **500 active shops within 12 months** of launch, scaling to 5,000+
- Database queries must use indexes on `user_id`, `created_at`, `job_type`
- Avoid N+1 query patterns — use joins or eager loading
- PDF generation must handle 50+ line item quotes without timeout
- Background jobs (AI calls) must have timeout + cleanup — no zombie threads
- **Rule:** Every new table needs a `user_id` foreign key + index. Every list endpoint needs pagination.

### Blast Radius Control
- One prompt = one focused change. Don't touch unrelated files.
- If a change touches more than 10 files, decompose it into smaller prompts
- Always run `pytest tests/ -v` after changes — never push failing tests
- Git commit at every working state — **save points are mandatory, not optional**
- **Rule:** If you're about to modify a calculator AND a router AND the frontend in one session, stop and break it up.

---

## Session Completion Checklist

Before marking a session complete:
- [ ] All new tests pass: `pytest tests/ -v`
- [ ] App starts without errors: `uvicorn backend.main:app --reload`
- [ ] BUILD_LOG.md updated with what was completed and what was not
- [ ] CLAUDE.md updated if any architectural decision was made
- [ ] No hardcoded values that should be config
- [ ] No CreateStage-specific branding in database schema or API logic
