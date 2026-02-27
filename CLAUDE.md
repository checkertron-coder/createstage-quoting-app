# CLAUDE.md — CreateStage Fabrication Intelligence Platform
*Read this at the start of EVERY session. Update it when architectural decisions are made.*
*This is your memory across sessions. If something changed, it's here.*

---

## What This App Is
A metal fabrication quoting platform. It takes job descriptions (text + photos) from fabricators, asks smart domain-specific follow-up questions, does deterministic math for materials and geometry, uses AI only for labor hour estimation, and outputs a professional itemized quote with PDF.

Not a chatbot. Not a generic LLM wrapper. A domain-specific tool that knows how fab shops work.

---

## Current State (as of Feb 27, 2026 — v1, pre-v2 build)

### What Works
- FastAPI backend running on Railway at `createstage-quoting-app-production.up.railway.app`
- PostgreSQL database on Railway (connected, schema in place)
- Basic quote CRUD via API (quotes, customers, materials, process_rates, ai_quote endpoints)
- Frontend: single HTML page, basic form-based interface
- Gemini 2.0 Flash connected via `GEMINI_API_KEY` env var
- Material weights calculator (`backend/weights.py`)
- Auto-seeding of process rates and material prices on startup

### What's Broken / Incomplete
- The current `JobType` enum is wrong for v2 — it has generic types (STRUCTURAL, ARCHITECTURAL, SIGNAGE) not the real fab job types (swing_gate, cantilever_gate, straight_railing, etc.)
- The AI quote endpoint in `ai_quote.py` is a generic LLM call with no domain knowledge — no question trees, no structured output
- No user authentication — single-user, CreateStage-specific
- No photo upload/storage
- No PDF generation
- No hardware sourcing / parts pricing
- No question tree system

### File Map
```
createstage-quoting-app/
├── backend/
│   ├── main.py              — FastAPI app, startup, routing
│   ├── models.py            — SQLAlchemy ORM models (Customer, Quote, QuoteLineItem, MaterialPrice, ProcessRate)
│   ├── schemas.py           — Pydantic request/response schemas
│   ├── database.py          — DB connection, SessionLocal, Base
│   ├── config.py            — Environment variable loading
│   ├── weights.py           — Steel weight calculator by profile type
│   └── routers/
│       ├── ai_quote.py      — AI estimation endpoint (needs full rewrite in v2)
│       ├── quotes.py        — Quote CRUD
│       ├── customers.py     — Customer CRUD
│       ├── materials.py     — Material prices + DEFAULT_PRICES seed data
│       └── process_rates.py — Process rates + DEFAULT_RATES seed data
├── frontend/
│   └── index.html           — Single page UI (needs full replacement in v2)
├── SPEC.md                  — OLD v1 spec (incomplete, ignore)
├── BUILD_LOG.md             — Session progress log (READ THIS TOO)
├── CLAUDE.md                — This file
└── requirements.txt
```

---

## The v2 Architecture — The 6-Stage Pipeline

```
User Input (text / photo)
    │
    ▼
[Stage 1: INTAKE]
    job_type detected → question tree loaded
    Output: IntakeResult { job_type, extracted_fields, confidence }
    │
    ▼
[Stage 2: CLARIFY]
    AI works through question tree, asks only for missing fields
    DO NOT repeat questions already answered in the description
    Output: QuoteParams { all required fields for this job type }
    │
    ▼
[Stage 3: CALCULATE]
    Pure Python math — geometry, piece counts, material quantities, weights, sq footage
    NO AI INVOLVEMENT HERE
    Output: MaterialList { line items with quantities and dimensions }
    │
    ▼
[Stage 4: ESTIMATE]
    AI receives structured job params → returns JSON of hours per process
    NEVER returns a single total — always per-process breakdown
    Output: LaborEstimate { process: str, hours: float } per process
    │
    ▼
[Stage 5: PRICE]
    Apply shop_rate × hours, material_price × quantity, hardware prices
    NO AI INVOLVEMENT HERE
    Output: PricedQuote { all line items with costs }
    │
    ▼
[Stage 6: OUTPUT]
    Render to UI and PDF
    Output: QuoteDocument + PDFBytes
```

**AI is ONLY in Stages 2 and 4. Stages 1, 3, 5, 6 are deterministic code.**

---

## Data Contracts Between Stages

These are the canonical Python TypedDicts. Use these exactly — do not invent new schemas.

```python
# Stage 1 → Stage 2
class IntakeResult(TypedDict):
    job_type: str                    # e.g. "cantilever_gate", "straight_railing"
    extracted_fields: dict           # fields already answered from initial description
    confidence: float                # 0.0-1.0 — how confident we are in job_type detection
    ambiguous: bool                  # True if user could mean multiple job types

# Stage 2 → Stage 3
class QuoteParams(TypedDict):
    job_type: str
    user_id: int
    session_id: str
    fields: dict                     # All required fields for this job type, fully populated
    photos: list[str]                # Cloudflare R2 URLs
    notes: str                       # Anything that doesn't fit structured fields

# Stage 3 → Stage 4 + Stage 5
class MaterialItem(TypedDict):
    description: str                 # e.g. "2\" sq tube 11ga - gate frame"
    material_type: str               # matches MaterialType enum
    profile: str                     # "sq_tube_2x11ga", "flat_bar_1x14ga", etc.
    length_inches: float
    quantity: int
    unit_price: float                # From materials table or market average
    line_total: float
    cut_type: str                    # "miter_45" | "square" | "cope" | "notch"
    waste_factor: float

class MaterialList(TypedDict):
    job_type: str
    items: list[MaterialItem]
    hardware: list[HardwareItem]
    total_weight_lbs: float
    total_sq_ft: float               # For finish area calculation
    weld_linear_inches: float        # For labor estimation

class HardwareItem(TypedDict):
    description: str                 # e.g. "Heavy duty weld-on gate hinge pair"
    quantity: int
    options: list[PricingOption]     # 3 options: McMaster + Amazon + other

class PricingOption(TypedDict):
    supplier: str                    # "McMaster-Carr" | "Amazon" | "Grainger" | etc.
    price: float
    url: str
    part_number: str | None
    lead_days: int | None

# Stage 4 output
class LaborProcess(TypedDict):
    process: str                     # "layout_setup" | "cut_prep" | "fit_tack" | "full_weld" |
                                     # "grind_clean" | "finish_prep" | "clearcoat" | "paint" |
                                     # "hardware_install" | "site_install" | "final_inspection"
    hours: float
    rate: float                      # From user's shop_rate or on_site_rate
    notes: str                       # AI reasoning (kept for audit trail)

class LaborEstimate(TypedDict):
    processes: list[LaborProcess]
    total_hours: float               # Sum of all process hours — computed, not AI-provided
    flagged: bool                    # True if >25% variance from historical actuals
    flag_reason: str | None

# Stage 5 → Stage 6
class PricedQuote(TypedDict):
    quote_id: str
    user_id: int
    job_type: str
    client_name: str | None
    materials: list[MaterialItem]    # With prices filled in
    hardware: list[HardwareItem]     # With selected option
    labor: list[LaborProcess]        # With costs computed
    finishing: FinishingSection
    subtotal: float                  # Sum of all before markup
    markup_options: dict             # {"5": float, "10": float, ..., "30": float}
    created_at: str
    assumptions: list[str]           # Every assumption made
    exclusions: list[str]            # Every item explicitly not included

class FinishingSection(TypedDict):
    method: str                      # "raw" | "clearcoat" | "paint" | "powder_coat" | "galvanized"
    area_sq_ft: float
    hours: float                     # In-house finish hours (0 if outsourced)
    materials_cost: float            # Clear coat product, paint, etc.
    outsource_cost: float            # Powder coat / galvanizing if outsourced
    total: float
    # FINISHING IS NEVER OPTIONAL. If raw: method="raw", everything else 0, note it.
```

---

## Database Schema (v2 target)

### New tables needed (in addition to existing)

```sql
-- User accounts (multi-tenant)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    is_provisional BOOLEAN DEFAULT TRUE,  -- True until password set
    shop_name VARCHAR,
    shop_address TEXT,
    shop_phone VARCHAR,
    shop_email VARCHAR,
    logo_url VARCHAR,                      -- Cloudflare R2 URL
    rate_inshop FLOAT DEFAULT 125.00,
    rate_onsite FLOAT DEFAULT 145.00,
    markup_default INTEGER DEFAULT 15,
    tier VARCHAR DEFAULT 'basic',          -- 'basic' | 'pro' | 'enterprise'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Auth tokens
CREATE TABLE auth_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    token_hash VARCHAR NOT NULL,
    token_type VARCHAR DEFAULT 'access',   -- 'access' | 'refresh'
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Quote sessions (conversation state)
CREATE TABLE quote_sessions (
    id VARCHAR PRIMARY KEY,                -- UUID
    user_id INTEGER REFERENCES users(id),
    job_type VARCHAR,
    stage VARCHAR DEFAULT 'intake',        -- current pipeline stage
    params_json JSONB DEFAULT '{}',        -- accumulated QuoteParams
    messages_json JSONB DEFAULT '[]',      -- conversation history
    photo_urls JSONB DEFAULT '[]',         -- Cloudflare R2 URLs
    status VARCHAR DEFAULT 'active',       -- 'active' | 'complete' | 'abandoned'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Final quotes (output of pipeline)
-- Extends existing quotes table — add columns:
ALTER TABLE quotes ADD COLUMN user_id INTEGER REFERENCES users(id);
ALTER TABLE quotes ADD COLUMN session_id VARCHAR;
ALTER TABLE quotes ADD COLUMN inputs_json JSONB;       -- QuoteParams
ALTER TABLE quotes ADD COLUMN outputs_json JSONB;      -- PricedQuote
ALTER TABLE quotes ADD COLUMN selected_markup_pct INTEGER DEFAULT 15;
ALTER TABLE quotes ADD COLUMN pdf_url VARCHAR;         -- Cloudflare R2 URL

-- Hardware items (separate from material prices)
CREATE TABLE hardware_items (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    category VARCHAR NOT NULL,             -- 'hinge' | 'latch' | 'operator' | etc.
    mcmaster_part VARCHAR,
    mcmaster_price FLOAT,
    mcmaster_url VARCHAR,
    alt1_supplier VARCHAR,
    alt1_price FLOAT,
    alt1_url VARCHAR,
    alt2_supplier VARCHAR,
    alt2_price FLOAT,
    alt2_url VARCHAR,
    last_updated TIMESTAMP DEFAULT NOW()
);

-- Historical actuals (for labor validation)
CREATE TABLE historical_actuals (
    id SERIAL PRIMARY KEY,
    quote_id INTEGER REFERENCES quotes(id),
    actual_hours_by_process JSONB,         -- {process: actual_hours}
    actual_material_cost FLOAT,
    notes TEXT,
    variance_pct FLOAT,                    -- vs. estimated
    recorded_at TIMESTAMP DEFAULT NOW()
);
```

---

## Authoritative v2 Job Type List (15 types — Sessions 1-8)

```python
V2_JOB_TYPES = [
    # Priority A — most common, highest data quality
    "cantilever_gate",          # sliding, with or without motor
    "swing_gate",               # hinged, single or double panel
    "straight_railing",         # flat platform / exterior / ADA
    "stair_railing",            # along stair stringer (different geometry)
    "repair_decorative",        # ornamental iron repair (photo-first)
    # Priority B — common, slightly more complex
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
    "custom_fab",               # freeform, AI-guided question tree
]
```

Session 2A covers the first 5 (Priority A).
Session 2B covers the remaining 10.

---

## Question Tree JSON Schema

Every job type's question tree lives in `question_trees/{job_type}.json`.
All question trees MUST follow this exact schema:

```json
{
    "job_type": "cantilever_gate",
    "version": "1.0",
    "display_name": "Cantilever Sliding Gate",
    "required_fields": ["clear_width", "height", "frame_material", "post_count"],
    "questions": [
        {
            "id": "clear_width",
            "text": "What is the clear opening width? (the space the gate needs to cover)",
            "type": "measurement",
            "unit": "feet",
            "required": true,
            "hint": "Measure from post to post, or tell us the driveway width",
            "branches": null
        },
        {
            "id": "has_motor",
            "text": "Will this gate have an electric operator (motor)?",
            "type": "choice",
            "options": ["Yes", "No", "Not sure — show me options"],
            "required": true,
            "hint": null,
            "branches": {
                "Yes": ["motor_brand"],
                "Not sure — show me options": ["motor_info_display", "motor_brand"]
            }
        },
        {
            "id": "motor_brand",
            "text": "Which gate operator are you considering?",
            "type": "choice",
            "options": ["LiftMaster LA412", "US Automatic Patriot", "Viking", "Bull Dog", "Other / not sure"],
            "required": false,
            "hint": "LiftMaster LA412 is the industry standard for residential/light commercial",
            "branches": null
        }
    ]
}
```

Field types: `"measurement"` | `"choice"` | `"multi_choice"` | `"text"` | `"photo"` | `"number"` | `"boolean"`

---

## Environment Variables Required

Set ALL of these in Railway before Session 1 starts:

```
# Already set
GEMINI_API_KEY=...          # Gemini 2.0 Flash + Vision
DATABASE_URL=...            # PostgreSQL on Railway

# New for v2 — set these before starting
JWT_SECRET=...              # Generate: openssl rand -hex 32
CLOUDFLARE_R2_ACCOUNT_ID=...
CLOUDFLARE_R2_ACCESS_KEY_ID=...
CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
CLOUDFLARE_R2_BUCKET=createstage-quotes

# Optional — for hardware sourcing web search
BRAVE_API_KEY=...           # For parts price search (Brave Search API)
```

---

## Auth System (decided — do not change without flagging)

- Email + password (bcrypt hash)
- JWT access tokens (15 min expiry) + refresh tokens (30 day expiry)
- Provisional accounts: user gives email → can immediately quote → password set later
- Quote sessions attach to user_id — provisional quotes transfer when account confirmed
- No OAuth for v2 (add in v3 if needed)
- Library: `python-jose` for JWT, `passlib[bcrypt]` for password hashing

---

## AI Model Assignments (decided — do not change)

| Stage | Model | Why |
|---|---|---|
| Stage 2 — Clarify (text) | `gemini-2.0-flash` | Fast, cheap, good enough for question routing |
| Stage 4 — Labor Estimate | `gemini-2.0-flash` | Structured JSON output, well within its capability |
| Photo Vision | `gemini-2.0-flash` | Has vision capability, same API key |
| Bid Parser (Session 7) | `gemini-2.0-flash` | Long context, good extraction |

Upgrade path: set `GEMINI_MODEL=gemini-3.0-flash` or `gemini-3.1-pro` to upgrade without code changes.

---

## Material Data Dependency

**Sessions 3-5 require seeded material prices to produce accurate output.**

Before running Session 3, Burton will provide invoices/quotes. These must be processed into:
`data/material_prices_seed.json` and `data/labor_actuals_seed.json`

Script to load: `python data/seed_from_invoices.py` (to be built in Session 1 alongside schema)

Until seeded, the app uses DEFAULT_PRICES from `backend/routers/materials.py` as fallback.
These are rough market averages — good enough for testing, not for production quotes.

---

## Testing Protocol (mandatory)

- Framework: pytest
- Location: `tests/`
- Run before any changes: `cd createstage-quoting-app && pytest tests/ -v`
- If tests fail: FIX THEM BEFORE PROCEEDING. Do not push failing tests.
- Each session must add at least 3 new passing tests to `tests/`
- Test naming: `test_{session_number}_{what_is_tested}.py`

---

## Integration Stubs (do not implement — define interface only)

```python
# integrations/steel_pricing.py
class SteelPricingIntegration:
    """Stub for Bayern Software / distributor pricing API — Phase 3"""
    def get_price(self, material_type: str, size: str, quantity: float, zip_code: str) -> float:
        raise NotImplementedError("Bayern Software integration not yet built — using market averages")

# integrations/fusion360.py
class Fusion360Integration:
    """Stub for Fusion 360 parametric model generation — Phase 3"""
    def generate_model(self, job_params: dict) -> str:  # Returns model file URL
        raise NotImplementedError("Fusion 360 integration not yet built")
```

---

## Finishing Is Never Optional — Hardcoded Rule

Every quote output MUST have a finishing section.
If the job is raw steel: `method="raw"`, `area_sq_ft=<calculated>`, all costs = 0.
Do NOT omit finishing from the output schema.
This is the most commonly underquoted item in fabrication — it is always visible.

---

## What Not To Touch

- `backend/weights.py` — working correctly, used by calculators
- `backend/database.py` — working correctly
- `requirements.txt` — add to it, don't remove without flagging
- Existing SQLAlchemy table definitions in `models.py` — extend them, don't replace (data migration required for changes)

---

## Session Completion Checklist

Before marking a session complete:
- [ ] All new tests pass: `pytest tests/ -v`
- [ ] App starts without errors: `uvicorn backend.main:app --reload`
- [ ] BUILD_LOG.md updated with what was completed and what was not
- [ ] CLAUDE.md updated if any architectural decision was made
- [ ] No hardcoded values that should be config (no hardcoded shop rates, no hardcoded "CreateStage")
- [ ] No CreateStage-specific branding in database schema or API logic (only in user profile data)
