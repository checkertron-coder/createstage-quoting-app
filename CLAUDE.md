# CLAUDE.md — CreateStage Fabrication Intelligence Platform
*Read this at the start of EVERY session. This is the definitive reference.*
*Last verified: Post Session 10 hotfix (Feb 28, 2026) — all contracts verified against code.*

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
- **Tests:** 324 passing tests across 13 test files

### Post Session 10 Hotfix — AI Cut List Bug Fixes

**Silent exception override bug (critical):**
6 calculators (furniture_table, custom_fab, furniture_other, led_sign_custom, repair_decorative, repair_structural) had local `_try_ai_cut_list()` and `_build_from_ai_cuts()` overrides with `except Exception: return None` — silently swallowing ALL Gemini errors. This caused AI cut list generation to always fail silently and fall back to generic templates (76ms response instead of 10-20s). Fix: deleted all 6 local overrides (-514 lines). All calculators now use BaseCalculator's versions which have `logger.warning()` on failure, price fallbacks ($3.50/ft), and weight fallbacks (2.0 lbs/ft).

**material_lookup.py — New profile:**
- Added `flat_bar_1x0.125` = $1.10/ft (1" wide x 1/8" thick flat bar). User submitted an end table job with "1x1/8 flat bar" pyramid pattern — this profile didn't exist so Gemini couldn't use it, silently skipping the entire flat bar feature from the materials list.

**furniture_table.py — Tube size respects user input:**
- Template fallback now reads `leg_material_profile` field AND `description` text to detect tube size
- "1 inch", "1x1", "1\" square" → `sq_tube_1x1_14ga` for legs and frame
- "1.5", "1-1/2" → `sq_tube_1.5x1.5_11ga`
- "2 inch", "2x2" → `sq_tube_2x2_11ga` legs / `sq_tube_1.5x1.5_11ga` frame
- Previously hardcoded to 2x2 legs / 1.5x1.5 frame regardless of what the user specified.

**ai_cut_list.py — Prompt improvements:**
- Added `flat_bar_1x0.125` and `flat_bar_1x0.1875` to AVAILABLE PROFILES list in Gemini prompt
- Added CRITICAL RULES FOR CUSTOM FEATURES block: patterns (pyramid, grid, concentric squares) MUST appear as real line items with quantities and lengths — never just mentioned in notes or build steps. Concentric square patterns calculate each layer separately, stepping inward by specified spacing until no more full squares fit, each layer = 4 pieces.

### Workflow Rule
- Direct code edits to this repo go through Claude Code prompts only. Checker (the OpenClaw AI assistant) diagnoses problems and writes the prompt; Claude Code executes and runs tests. Claude Code has full repo context, runs the test suite, and handles edge cases better than one-off direct edits.

### What's Still Needed
- Live hardware pricing (web search / API)
- ENITEO/SteelXML integration (Phase 3)
- Fusion 360 parametric model generation (Phase 3)

---

## 3. File Map (verified Session 10)

```
createstage-quoting-app/
├── backend/
│   ├── __init__.py
│   ├── main.py              — FastAPI app, startup, CORS, static files, router mounting
│   ├── models.py            — SQLAlchemy ORM (User, Quote, QuoteSession, AuthToken, BidAnalysis, etc.)
│   ├── schemas.py           — Pydantic request/response schemas
│   ├── database.py          — DB engine, SessionLocal, Base
│   ├── config.py            — Settings via pydantic-settings (env vars)
│   ├── auth.py              — JWT creation/validation, bcrypt hashing, get_current_user dependency
│   ├── weights.py           — Steel weight calculator by profile type (DO NOT MODIFY)
│   ├── labor_estimator.py   — Stage 4: AI labor estimation (Gemini) + rule-based fallback
│   ├── finishing.py         — Stage 4: FinishingBuilder (raw/clearcoat/paint/powder_coat/galvanized)
│   ├── historical_validator.py — Stage 4: Compare estimates vs historical actuals
│   ├── hardware_sourcer.py  — Stage 5: 25-item hardware catalog + consumable estimation
│   ├── pricing_engine.py    — Stage 5: PricedQuote assembly, markup options, subtotals
│   ├── pdf_generator.py     — Stage 6: PDF generation (10 sections), _safe() Unicode helper
│   ├── bid_parser.py        — Session 7: Bid scope extraction (Gemini + keyword fallback)
│   ├── pdf_extractor.py     — Session 7: PDF text extraction via pdfplumber
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py          — /api/auth/* (register, login, guest, refresh, me, profile)
│   │   ├── quote_session.py — /api/session/* (start, answer, status, calculate, estimate, price)
│   │   ├── quotes.py        — /api/quotes/* (CRUD, /mine, /detail, /breakdown, /markup)
│   │   ├── pdf.py           — /api/quotes/{id}/pdf (download with query param auth)
│   │   ├── bid_parser.py    — /api/bid/* (upload, parse-text, quote-items)
│   │   ├── ai_quote.py      — /api/ai/* (legacy v1 AI estimation)
│   │   ├── photos.py        — /api/photos/* (upload with R2 or local fallback)
│   │   ├── customers.py     — /api/customers/* (CRUD)
│   │   ├── materials.py     — /api/materials/* (seed, list, update) + DEFAULT_PRICES
│   │   └── process_rates.py — /api/process-rates/* (seed, list, update) + DEFAULT_RATES
│   ├── calculators/
│   │   ├── __init__.py
│   │   ├── base.py              — Abstract BaseCalculator + make_material_item/list/hardware + AI-first helpers (_has_description, _try_ai_cut_list, _build_from_ai_cuts)
│   │   ├── material_lookup.py   — Price lookup: seeded prices (35) → hardcoded defaults fallback
│   │   ├── registry.py          — Calculator registry (25 job types → calculator classes, CustomFab fallback)
│   │   ├── cantilever_gate.py   — Cantilever gate geometry + materials
│   │   ├── swing_gate.py        — Swing gate geometry + materials
│   │   ├── straight_railing.py  — Straight railing geometry + materials
│   │   ├── stair_railing.py     — Stair railing geometry + materials
│   │   ├── repair_decorative.py — Decorative repair estimation
│   │   ├── ornamental_fence.py  — Panel-based fence (posts, rails, pickets)
│   │   ├── complete_stair.py    — Stringer + treads + landing (rise/run geometry)
│   │   ├── spiral_stair.py      — Center column + pie treads + spiral handrail
│   │   ├── window_security_grate.py — Frame + bars, batch multiply
│   │   ├── balcony_railing.py   — Delegates to StraightRailingCalculator + structural frame
│   │   ├── furniture_table.py   — Legs + frame + stretchers
│   │   ├── utility_enclosure.py — Sheet metal box + door hardware
│   │   ├── bollard.py           — Pipe + cap + base plate, multiply by count
│   │   ├── repair_structural.py — Conservative estimate by repair_type
│   │   ├── custom_fab.py        — Universal fallback, NEVER fails
│   │   ├── offroad_bumper.py    — Plate + tube structure by bumper_position
│   │   ├── rock_slider.py       — DOM tube rails + mount brackets (always pair)
│   │   ├── roll_cage.py         — Tube footage by cage_style
│   │   ├── exhaust_custom.py    — Pipe runs + bends + flanges
│   │   ├── trailer_fab.py       — Channel frame + cross members + deck
│   │   ├── structural_frame.py  — Routes by frame_type (mezzanine/canopy/portal)
│   │   ├── furniture_other.py   — Routes by item_type (shelving/bracket/generic)
│   │   ├── sign_frame.py        — Frame tube + mounting by sign_type
│   │   ├── led_sign_custom.py   — Channel letters / cabinet estimate
│   │   ├── product_firetable.py — BOM-based from firetable_pro_bom.json
│   │   ├── ai_cut_list.py      — AI-assisted cut list + build instructions (Gemini)
│   │   └── fab_knowledge.py    — FAB_KNOWLEDGE.md parser, targeted section injection into AI prompts
│   └── question_trees/
│       ├── __init__.py
│       ├── engine.py        — QuestionTreeEngine (load, detect_job_type, extract_fields, extract_from_photo, next_questions)
│       └── data/            — 25 JSON question tree files (one per job type)
│           ├── cantilever_gate.json    ├── ornamental_fence.json
│           ├── swing_gate.json         ├── complete_stair.json
│           ├── straight_railing.json   ├── spiral_stair.json
│           ├── stair_railing.json      ├── window_security_grate.json
│           ├── repair_decorative.json  ├── balcony_railing.json
│           ├── furniture_table.json    ├── utility_enclosure.json
│           ├── bollard.json            ├── repair_structural.json
│           ├── custom_fab.json         ├── offroad_bumper.json
│           ├── rock_slider.json        ├── roll_cage.json
│           ├── exhaust_custom.json     ├── trailer_fab.json
│           ├── structural_frame.json   ├── furniture_other.json
│           ├── sign_frame.json         ├── led_sign_custom.json
│           └── product_firetable.json
├── frontend/
│   ├── index.html           — SPA shell (nav + 4 view containers)
│   ├── css/style.css        — Responsive CSS with custom properties
│   ├── js/
│   │   ├── api.js           — API client with JWT token management
│   │   ├── auth.js          — Auth UI (login, register, guest, profile)
│   │   ├── quote-flow.js    — Quoting pipeline UI + QuoteHistory
│   │   └── app.js           — App controller, view management
│   └── static/              — Legacy static files (v1, kept for compat)
│       ├── app.js
│       └── style.css
├── data/
│   ├── seed_from_invoices.py — Profile key parser + price seeder (processes raw/ → seeded_prices.json)
│   ├── seeded_prices.json    — 35 profile prices from Osorio/Wexler (generated output)
│   ├── README.md
│   └── raw/                  — Source invoice/price files
│       ├── osorio_prices_seed.json    — 35 items, per-foot prices
│       ├── osorio_prices_raw.json     — Raw Osorio data
│       ├── wexler_prices_raw.json     — 16 items, mixed units
│       ├── createstage_invoices.json  — 15 invoices with hours/costs
│       └── firetable_pro_bom.json     — Single product BOM
├── tests/
│   ├── __init__.py
│   ├── conftest.py          — Fixtures (client, db, auth_headers, guest_headers)
│   ├── test_session1_schema.py         — 11 tests (DB schema, models)
│   ├── test_session2a_question_trees.py — 21 tests (Priority A trees)
│   ├── test_session2b_question_trees.py — 23 tests (Priority B+C trees)
│   ├── test_session3_calculators.py     — 30 tests (5 Priority A calculators)
│   ├── test_session3b_all_calculators.py — 35 tests (20 new calculators, registry, detection, trees)
│   ├── test_session4_labor.py           — 26 tests (labor estimation)
│   ├── test_session5_pricing.py         — 26 tests (pricing engine)
│   ├── test_session6_output.py          — 25 tests (PDF, frontend, auth)
│   ├── test_session7_bid_parser.py      — 26 tests (bid parser)
│   ├── test_session8_integration.py    — 15 tests (smoke, seed data, meta)
│   ├── test_photo_extraction.py        — 20 tests (photo upload, vision, extraction confirmation)
│   ├── test_ai_cut_list.py             — 20 tests (AI cut list, furniture fixes, PDF sections)
│   ├── test_session10_intelligence.py  — 39 tests (intelligence layer, AI-first, weld process)
│   └── fixtures/
│       └── sample_bid_excerpt.txt       — SECTION 05 50 00 test fixture
├── alembic/                 — Database migrations
│   ├── env.py
│   └── versions/82694c65cf42_v2_foundation_....py
├── BUILD_LOG.md             — Session-by-session progress log
├── CLAUDE.md                — This file
├── railway.json             — Railway deploy config
├── requirements.txt         — Python dependencies
├── SPEC.md                  — Old v1 spec (ignore)
├── SESSION_1_PROMPT.md      — Session 1 instructions (historical)
├── SESSION_2A_PROMPT.md     — Session 2A instructions (historical)
└── AGENT_TASK.md            — Agent task reference
```

---

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

## 5. Data Contracts Between Stages (verified against code — Session 8)

These match the actual implementations. The code is the source of truth.

```python
# Stage 1 → Stage 2 (engine.py:263-329)
class IntakeResult(TypedDict):
    job_type: str                    # e.g. "cantilever_gate", "straight_railing"
    confidence: float                # 0.0-1.0 — from Gemini (0.0 if API unavailable)
    ambiguous: bool                  # True if user could mean multiple job types

# NOTE: extracted_fields is returned separately by engine.extract_fields_from_description(),
# not as part of IntakeResult. The session router combines them.

# Stage 2 → Stage 3 (engine.py:159-182)
class QuoteParams(TypedDict):
    job_type: str
    user_id: int
    session_id: str
    fields: dict                     # All required fields for this job type, fully populated
    photos: list[str]                # Cloudflare R2 URLs
    notes: str                       # Anything that doesn't fit structured fields

# Stage 3 output (base.py:114-164)
class MaterialItem(TypedDict):
    description: str                 # e.g. "2\" sq tube 11ga - gate frame"
    material_type: str               # matches MaterialType enum
    profile: str                     # "sq_tube_2x2_11ga", "flat_bar_1x0.25", etc.
    length_inches: float             # Rounded to 2 decimals
    quantity: int
    unit_price: float                # From seeded prices or market average
    line_total: float                # quantity × unit_price
    cut_type: str                    # "miter_45" | "square" | "cope" | "notch"
    waste_factor: float              # 0.0-0.15 as decimal

class HardwareItem(TypedDict):
    description: str                 # e.g. "Heavy duty weld-on gate hinge pair"
    quantity: int
    options: list[PricingOption]     # 3 options: McMaster + Amazon + other

class PricingOption(TypedDict):
    supplier: str                    # "McMaster-Carr" | "Amazon" | "Grainger" | etc.
    price: float                     # Rounded to 2 decimals
    url: str
    part_number: str | None
    lead_days: int | None

class MaterialList(TypedDict):
    job_type: str
    items: list[MaterialItem]
    hardware: list[HardwareItem]
    total_weight_lbs: float          # Rounded to 1 decimal
    total_sq_ft: float               # For finish area calculation
    weld_linear_inches: float        # For labor + consumable estimation
    assumptions: list[str]           # Calculator assumptions made

# Stage 4 output (labor_estimator.py:50-376)
class LaborProcess(TypedDict):
    process: str                     # One of 11 canonical process names (see below)
    hours: float                     # Rounded to 2 decimals
    rate: float                      # From user's rate_inshop or rate_onsite
    notes: str                       # AI reasoning or fallback explanation

# 11 canonical processes:
# "layout_setup", "cut_prep", "fit_tack", "full_weld", "grind_clean",
# "finish_prep", "clearcoat", "paint", "hardware_install",
# "site_install", "final_inspection"

class LaborEstimate(TypedDict):
    processes: list[LaborProcess]
    total_hours: float               # Sum of all process hours — computed, not AI-provided
    flagged: bool                    # True if >25% variance from historical actuals
    flag_reason: str | None

# Stage 4 — Finishing (finishing.py:27-123)
class FinishingSection(TypedDict):
    method: str                      # "raw" | "clearcoat" | "paint" | "powder_coat" | "galvanized"
    area_sq_ft: float                # Rounded to 1 decimal
    hours: float                     # In-house finish hours, rounded to 2 decimals
    materials_cost: float            # Product cost (paint, clearcoat, etc.)
    outsource_cost: float            # Powder coat / galvanizing service cost
    total: float                     # Sum of materials_cost or outsource_cost
    # FINISHING IS NEVER OPTIONAL. If raw: method="raw", everything else 0, note it.

# Stage 5 output (pricing_engine.py:28-127)
class PricedQuote(TypedDict):
    quote_id: int | None             # None until Quote DB record created
    user_id: int
    job_type: str
    client_name: str | None          # Currently: user.shop_name (TODO: actual client name)
    materials: list[MaterialItem]
    hardware: list[HardwareItem]
    consumables: list[dict]          # NEW: welding wire, discs, gas, etc.
    labor: list[LaborProcess]
    finishing: FinishingSection
    material_subtotal: float         # Sum of material line_totals
    hardware_subtotal: float         # Sum of cheapest hardware option per item
    consumable_subtotal: float       # Sum of consumable line_totals
    labor_subtotal: float            # Sum of (hours × rate) per process
    finishing_subtotal: float        # finishing.total
    subtotal: float                  # Sum of all above subtotals
    markup_options: dict             # {"0": float, "5": float, ..., "30": float}
    selected_markup_pct: int         # Default from user profile
    total: float                     # subtotal × (1 + markup_pct/100)
    created_at: str                  # ISO format timestamp
    assumptions: list[str]           # Every assumption made
    exclusions: list[str]            # Every item explicitly not included
```

---

## 6. API Endpoint Reference (44 total — verified Session 3B-Hotfix)

### Auth — `/api/auth`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/register` | No | Register or claim provisional account |
| POST | `/api/auth/login` | No | Login, returns access + refresh tokens |
| POST | `/api/auth/refresh` | No | Exchange refresh token for new access token |
| POST | `/api/auth/guest` | No | Create provisional account, returns JWT |
| GET | `/api/auth/me` | Yes | Get current user profile |
| PUT | `/api/auth/profile` | Yes | Update shop profile (name, rates, markup) |

### Photos — `/api/photos`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/photos/upload` | Yes | Upload photo (R2 or local), returns photo_url + filename |

### Quote Sessions — `/api/session` (the main v2 pipeline)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/session/start` | Yes | Start quote from description + photos → detect job type, extract fields, run vision |
| POST | `/api/session/{id}/answer` | Yes | Submit field answers + optional photo_url → get next questions |
| GET | `/api/session/{id}/status` | Yes | Get session state, completion %, remaining questions |
| POST | `/api/session/{id}/calculate` | Yes | Run Stage 3 calculator → MaterialList |
| POST | `/api/session/{id}/estimate` | Yes | Run Stage 4 labor estimator → LaborEstimate + Finishing |
| POST | `/api/session/{id}/price` | Yes | Run Stage 5 pricing → create Quote, return PricedQuote |

### Quotes — `/api/quotes`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/quotes/` | No | Create quote (v1 legacy) |
| GET | `/api/quotes/` | No | List all quotes (paginated) |
| GET | `/api/quotes/mine` | Yes | List user's quotes, newest first |
| GET | `/api/quotes/{id}` | No | Get single quote |
| GET | `/api/quotes/{id}/detail` | Yes | Get full PricedQuote from outputs_json |
| GET | `/api/quotes/{id}/breakdown` | No | Get cost breakdown |
| PATCH | `/api/quotes/{id}` | No | Update quote fields |
| DELETE | `/api/quotes/{id}` | No | Delete quote |
| PUT | `/api/quotes/{id}/markup` | Yes | Change markup % and recalculate total |
| GET | `/api/quotes/{id}/pdf` | Yes* | Download PDF (*supports `?token=` query param) |

### Bid Parser — `/api/bid`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/bid/upload` | Yes | Upload PDF bid doc, extract metal fab scope (50MB limit) |
| POST | `/api/bid/parse-text` | Yes | Parse pasted bid text for scope items |
| POST | `/api/bid/{bid_id}/quote-items` | Yes | Create quote sessions from selected bid items |

### Legacy AI — `/api/ai`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/ai/estimate` | No | Plain English → structured estimate (doesn't save) |
| POST | `/api/ai/quote` | No | Plain English → saved draft quote |
| GET | `/api/ai/test` | No | Verify Gemini API key works |

### Customers — `/api/customers`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/customers/` | No | Create customer |
| GET | `/api/customers/` | No | List customers (paginated) |
| GET | `/api/customers/{id}` | No | Get customer |
| PATCH | `/api/customers/{id}` | No | Update customer |

### Materials — `/api/materials`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/materials/seed` | No | Seed default material prices (idempotent) |
| GET | `/api/materials/` | No | List all material prices |
| PATCH | `/api/materials/{type}` | No | Update material price |

### Process Rates — `/api/process-rates`
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/process-rates/seed` | No | Seed default process rates (idempotent) |
| GET | `/api/process-rates/` | No | List all process rates |
| PATCH | `/api/process-rates/{type}` | No | Update process rate |

### System
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | Serve frontend |
| GET | `/health` | No | Health check → `{"status": "ok"}` |

---

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

| Usage | Model | Config |
|---|---|---|
| Job type detection (Stage 1) | `gemini-2.0-flash` | `settings.GEMINI_MODEL` |
| Question clarification (Stage 2) | `gemini-2.0-flash` | `settings.GEMINI_MODEL` |
| Labor estimation (Stage 4) | `gemini-2.0-flash` | `settings.GEMINI_MODEL` |
| Photo vision | `gemini-2.0-flash` | `settings.GEMINI_MODEL` |
| Bid parsing (Session 7) | `gemini-2.0-flash` | `settings.GEMINI_MODEL` |

Upgrade path: set `GEMINI_MODEL=gemini-3.0-flash` env var to upgrade all without code changes.

---

## 13. Environment Variables

```bash
# Required
DATABASE_URL=...            # PostgreSQL connection string
GEMINI_API_KEY=...          # Gemini API key
JWT_SECRET=...              # openssl rand -hex 32

# Optional (with defaults)
GEMINI_MODEL=gemini-2.0-flash
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

## 15. Testing Protocol

```bash
# Run all tests
pytest tests/ -v

# Run specific session tests
pytest tests/test_session3_calculators.py -v

# Run with random order (verify isolation)
pip install pytest-randomly && pytest tests/ -v -p randomly
```

- Framework: pytest
- DB: SQLite in-memory for tests (overridden in `conftest.py`)
- Auth: `auth_headers` and `guest_headers` fixtures provide JWT tokens
- Naming: `test_{session_number}_{what_is_tested}.py`
- Rule: **FIX FAILING TESTS BEFORE PROCEEDING. Do not push failing tests.**
- Each session adds at least 3 new passing tests

### Test Count by Session
| File | Tests |
|------|-------|
| `test_session1_schema.py` | 11 |
| `test_session2a_question_trees.py` | 21 |
| `test_session2b_question_trees.py` | 23 |
| `test_session3_calculators.py` | 30 |
| `test_session3b_all_calculators.py` | 35 |
| `test_session4_labor.py` | 26 |
| `test_session5_pricing.py` | 26 |
| `test_session6_output.py` | 25 |
| `test_session7_bid_parser.py` | 26 |
| `test_session8_integration.py` | 15 |
| `test_photo_extraction.py` | 20 |
| `test_ai_cut_list.py` | 20 |
| `test_session10_intelligence.py` | 39 |
| **Total** | **324** |

---

## 16. Python Version + Dependencies

**Python 3.9** — do NOT use `str | None` syntax (use `Optional[str]` from typing)

Key dependencies (from `requirements.txt`):
- `fastapi==0.110.0` + `uvicorn==0.27.1` — web framework
- `sqlalchemy==2.0.28` — ORM
- `psycopg2-binary==2.9.9` — PostgreSQL driver
- `pydantic==2.6.3` + `pydantic-settings==2.2.1` — validation + config
- `python-jose[cryptography]==3.3.0` — JWT tokens
- `passlib[bcrypt]==1.7.4` + `bcrypt==4.1.3` — password hashing
- `fpdf2==2.8.4` — PDF generation
- `pdfplumber==0.11.4` — PDF text extraction
- `boto3==1.34.69` — Cloudflare R2 / S3 photo storage
- `alembic==1.13.1` — DB migrations
- `httpx==0.27.0` — async HTTP client (Gemini API)
- `pytest==8.1.1` — testing

---

## 17. Integration Stubs (Phase 3 — do not implement yet)

```python
# integrations/steel_pricing.py
class SteelPricingIntegration:
    """
    Stub for Enmark ENITEO / SteelXML integration — Phase 3
    Bayern Software (founded 1985, Indiana) merged with Enmark Systems (2024).
    Product: ENITEO — #1 ERP for metal service centers in North America.
    Integration path: SteelXML (AISC standard) + e-Acquire360.
    """
    def get_price(self, material_type, size, quantity, zip_code) -> float:
        raise NotImplementedError

# integrations/fusion360.py
class Fusion360Integration:
    """Stub for Fusion 360 parametric model generation — Phase 3"""
    def generate_model(self, job_params: dict) -> str:
        raise NotImplementedError
```

---

## 18. Hardcoded Rules

1. **Finishing is NEVER optional.** Every quote has a finishing section. If raw: `method="raw"`, all costs 0.
2. **Labor is always per-process.** Never a single total from AI — always breakdown by 11 canonical processes.
3. **Consumables are first-class line items.** Welding wire, grinding discs, gas estimated from weld_linear_inches + sq_ft.
4. **Markup options always 0-30%.** Dict keys: `"0"`, `"5"`, `"10"`, `"15"`, `"20"`, `"25"`, `"30"`.
5. **No CreateStage-specific branding in DB/API.** Only in user profile data.

---

## 19. What Not To Touch

- `backend/weights.py` — working correctly, used by all calculators
- `backend/database.py` — working correctly, shared by all modules
- `requirements.txt` — add to it, don't remove without flagging
- Existing SQLAlchemy table definitions in `models.py` — extend them, don't replace (data migration required)
- `data/seeded_prices.json` — generated output, regenerate via `python data/seed_from_invoices.py`

---

## Session Completion Checklist

Before marking a session complete:
- [ ] All new tests pass: `pytest tests/ -v`
- [ ] App starts without errors: `uvicorn backend.main:app --reload`
- [ ] BUILD_LOG.md updated with what was completed and what was not
- [ ] CLAUDE.md updated if any architectural decision was made
- [ ] No hardcoded values that should be config
- [ ] No CreateStage-specific branding in database schema or API logic
