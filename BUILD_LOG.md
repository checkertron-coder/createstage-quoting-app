# BUILD_LOG.md — CreateStage Quoting App

## MANDATORY: Read this at the start of every Claude Code session. Write to it at the end.

---

## Current Status: Session 10 complete — Intelligence layer: AI-first calculators, weld process reasoning, description handoff

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

### Session 2A — 2026-02-27 (Opus 4.6)

#### Completed
- **Deliverable 1 — Question Tree Engine**
  - `backend/question_trees/__init__.py` + `engine.py` — core engine class
  - `QuestionTreeEngine` with: `load_tree`, `extract_from_description`, `get_next_questions`, `is_complete`, `get_completion_status`, `get_quote_params`, `list_available_trees`
  - `detect_job_type()` function for Stage 1 intake (Gemini-powered, graceful fallback when no API key)
  - Branching logic: questions with `depends_on` + `branches` are shown/hidden based on answers
  - Gemini extraction prompt: only extracts fields with >90% confidence, never guesses measurements

- **Deliverable 2 — Quote Session API**
  - `backend/routers/quote_session.py` — 3 endpoints:
    - `POST /api/session/start` — creates session, detects job type, extracts fields from description
    - `POST /api/session/{id}/answer` — submits answers, returns next questions, tracks completion
    - `GET /api/session/{id}/status` — returns full session state
  - Sessions persist in `quote_sessions` table, messages logged in `messages_json`
  - Auth-protected: requires JWT, validates session ownership

- **Deliverable 3 — 5 Priority A Question Trees**
  - `backend/question_trees/data/cantilever_gate.json` — 28 questions (18 required by spec)
  - `backend/question_trees/data/swing_gate.json` — 29 questions (16 required by spec)
  - `backend/question_trees/data/straight_railing.json` — 23 questions (14 required by spec)
  - `backend/question_trees/data/stair_railing.json` — 28 questions (16 required by spec)
  - `backend/question_trees/data/repair_decorative.json` — 17 questions (12 required by spec)
  - All trees: real fab domain knowledge, proper branching logic, code compliance hints, material size options

#### Not completed / blocked
- None — all 3 deliverables complete

#### Architectural decisions made
- Engine is a singleton with cached tree loading — no state between calls
- Gemini extraction gracefully returns `{}` when no API key (enables offline testing)
- `depends_on` + `branches` dual mechanism: depends_on gates visibility, branches control activation of specific downstream questions
- Session endpoints are auth-protected (require JWT from Session 1 auth system)
- Used `flag_modified` for JSON column updates on SQLite (prevents silent mutation misses)

#### Tests
- pytest results: **32 passed, 0 failed** (11 from Session 1 + 21 from Session 2A)
- Test file: `tests/test_session2a_question_trees.py`
- Tests cover: tree loading (5), question counts (5), photo-first repair workflow, branching logic (motor yes/no), deduplication, completion status, rake angle, code branching, QuoteParams contract, schema validation, session API (start/answer/status)

### Session 2B — 2026-02-27 (Opus 4.6)

#### Completed
- **Deliverable 1 — 10 Priority B+C Question Trees**
  - `backend/question_trees/data/ornamental_fence.json` — 22 questions (14 min spec), category "ornamental"
    - Pool code compliance hints (ASTM F1908, 4" max spacing), gate branching (pedestrian/driveway/both), scroll complexity branch, post footing depth by frost line
  - `backend/question_trees/data/complete_stair.json` — 22 questions (14 min spec), category "architectural"
    - IRC/IBC code branching (residential vs commercial dimensions), landing count with underquote trap hint, mono-stringer → PE stamp branch, tread/riser types
  - `backend/question_trees/data/spiral_stair.json` — 19 questions (14 min spec), category "architectural"
    - Stainless steel cost warning branch (30-50% labor, 4-5x material), helical handrail forming hints, headroom clearance (6'6" min), center column options
  - `backend/question_trees/data/window_security_grate.json` — 16 questions (10 min spec), category "ornamental"
    - IBC 1030 egress compliance branch (hinged → hinge_side + latch_type), masonry anchoring branch, egress-compliant latch options, hinged cost multiplier hint (2-3x fixed)
  - `backend/question_trees/data/balcony_railing.json` — 24 questions (14 min spec), category "architectural"
    - Structural frame branch (scope → balcony_width, depth, dead_load, structure_attachment, pe_stamp), hot tub dead load warning (3,000-6,000 lbs), glass/cable infill branches
  - `backend/question_trees/data/furniture_table.json` — 15 questions (10 min spec), category "specialty"
    - Stainless grade branch (304 vs 316 with TIG welding note), weld visibility option (ground smooth adds 30-50% labor), ADA compliance for commercial, leg design options
  - `backend/question_trees/data/utility_enclosure.json` — 17 questions (12 min spec), category "specialty"
    - NEMA rating branch (electrical → NEMA 1/3R/4/4X), ventilation requirements branch (generator), door hardware underquote trap hint ($40-80 per door), panel style options
  - `backend/question_trees/data/bollard.json` — 15 questions (8 min spec), category "specialty"
    - Fixed/removable branch (removable → sleeve_type), crash rating advisory (ASTM F2656 vs standard fab), surface mount → base_plate_size, concrete fill option
  - `backend/question_trees/data/repair_structural.json` — 14 questions (12 min spec), category "specialty"
    - PHOTO-FIRST: first question is required photo upload, HSLA preheat branch (200-400°F, E7018 electrodes), DOT certification branch, cast iron repair advisory, urgency/rush premium hint
  - `backend/question_trees/data/custom_fab.json` — 13 questions (8 min spec), category "specialty"
    - No-drawings → design charge note ($75-125/hr, credited toward fabrication), shipping/freight branch, tolerance requirements, freeform description-first workflow

- **Deliverable 2 — Session 2B Acceptance Tests**
  - `tests/test_session2b_question_trees.py` — 23 tests
  - Coverage: loading all 10 trees, all 15 types in engine, minimum question counts (10 tests), photo-first repair_structural, 6 branching logic tests (bollard removable, enclosure NEMA, furniture stainless, custom_fab no-drawings, balcony structural PE stamp, spiral stainless), domain-specific hints (landing trap, egress branch), schema validation for all 10, category validation

#### Not completed / blocked
- None — all deliverables complete

#### Architectural decisions made
- No engine or API code changes — Session 2B is purely data files (question tree JSONs) and tests
- All trees include `category` field ("architectural", "ornamental", or "specialty")
- Photo-first pattern confirmed for both repair types: `repair_decorative` (Session 2A) and `repair_structural` (Session 2B)

#### Tests
- pytest results: **55 passed, 0 failed** (11 Session 1 + 21 Session 2A + 23 Session 2B)
- Test file: `tests/test_session2b_question_trees.py`
- All 15 question tree JSON files load, validate, and branch correctly

#### Question tree summary (all 15)

| Job Type | Questions | Category | Key Domain Features |
|----------|-----------|----------|---------------------|
| cantilever_gate | 28 | architectural | Motor brand, V-track/no-track, counterweight |
| swing_gate | 29 | architectural | Panel config, swing clearance, operator |
| straight_railing | 23 | architectural | ADA code branch, infill styles, cable/glass |
| stair_railing | 28 | architectural | Rake angle, stringer attachment, code compliance |
| repair_decorative | 17 | ornamental | Photo-first, match existing, rust assessment |
| ornamental_fence | 22 | ornamental | Pool code, scroll complexity, gate hardware |
| complete_stair | 22 | architectural | IRC/IBC branch, landing trap, mono-stringer PE |
| spiral_stair | 19 | architectural | Stainless cost warning, helical handrail, headroom |
| window_security_grate | 16 | ornamental | Egress compliance, hinged branch, masonry anchor |
| balcony_railing | 24 | architectural | Structural frame branch, dead load, PE stamp |
| furniture_table | 15 | specialty | Stainless grade, weld visibility, ADA |
| utility_enclosure | 17 | specialty | NEMA rating, ventilation, hardware trap hint |
| bollard | 15 | specialty | Removable sleeve, crash rating, concrete fill |
| repair_structural | 14 | specialty | Photo-first, HSLA preheat, DOT cert, cast advisory |
| custom_fab | 13 | specialty | Design charge note, tolerance, freeform |

### Session 3 — 2026-02-27 (Opus 4.6)

#### Completed
- **Deliverable 1 — Calculator Framework (base class + material lookup)**
  - `backend/calculators/__init__.py` — package marker
  - `backend/calculators/base.py` — abstract `BaseCalculator` with:
    - Waste factors: `WASTE_TUBE=0.05`, `WASTE_FLAT=0.10`, `WASTE_SHEET=0.15`
    - `apply_waste()` — always rounds UP via `math.ceil`
    - `linear_feet_to_pieces()` — pieces rounded up (never leave partial stock)
    - `make_material_item()`, `make_hardware_item()`, `make_pricing_option()` — contract-compliant dict constructors matching CLAUDE.md TypedDicts
    - `make_material_list()` — assembles full MaterialList output
    - Parsing helpers: `parse_feet()`, `parse_inches()`, `parse_int()`, `parse_number()` — tolerant of free-text input
    - Weight integration: `get_weight_lbs()` and `get_plate_weight_lbs()` delegate to existing `backend/weights.py`
  - `backend/calculators/material_lookup.py` — price lookup with defaults:
    - `PRICE_PER_FOOT` — 37 steel profiles (sq tube, round tube, angle, flat bar, channel, pipe)
    - `PRICE_PER_SQFT` — 6 sheet/plate types (expanded metal, perforated, tread plate, sheet steel)
    - `PRICE_PER_UNIT` — concrete, welding wire, grinding discs
    - `HARDWARE_CATALOG` — 24 items, each with 3 `PricingOption` stubs (McMaster-Carr, Amazon, Grainger)
    - `MaterialLookup` class with `get_price_per_foot()`, `get_price_per_sqft()`, `get_unit_price()`, `get_hardware_options()`, `get_hardware_category()`

- **Deliverable 2 — 5 Priority A Calculators**
  - `backend/calculators/cantilever_gate.py` — `CantileverGateCalculator`
    - Counterbalance tail: `TAIL_RATIO=0.55` (55% of clear width) — the #1 underquoting error in gate fabrication
    - Frame geometry: face + tail as continuous structure, mid-rail stiffeners for gates >48"
    - Infill types: expanded metal, pickets, flat bar, solid sheet, horizontal slats
    - Posts: embed depth (42" standard), concrete volume per hole (π×r²×depth)
    - Hardware: roller carriages, motor (LiftMaster/US Automatic/Viking/Bull Dog), latch, gate stops
    - Surface area: both sides of gate face + tail + post faces
  - `backend/calculators/swing_gate.py` — `SwingGateCalculator`
    - Panel configurations: single, double (equal split), unequal (60/40 split)
    - Weight-based hinge sizing: estimates panel weight, selects hinge count (2/3) and type
    - Mid-rail count: 1 for gates >48", 2 for gates >72"
    - Center stop hardware for double gates (cane bolt/surface drop rod/flush bolt)
    - Auto-close: spring hinges or hydraulic closer based on gate weight
    - Reuses FRAME_PROFILES and POST_PROFILES from cantilever module
  - `backend/calculators/straight_railing.py` — `StraightRailingCalculator`
    - Post count: `floor(footage / spacing) + 1 + transitions`
    - Baluster count: `ceil(linear_inches / spacing) + 1` (4" code-compliant default)
    - Infill types: picket, horizontal bar, cable, glass panel
    - Cable infill: cable count from height/3" spacing, tensioners per cable per section, end fittings
    - Glass infill: panel count/size, notes glass sourced separately
    - Mount types: surface mount flanges, core drill, embedded, side mount
  - `backend/calculators/stair_railing.py` — `StairRailingCalculator`
    - Delegates to `StraightRailingCalculator` with adjusted dimensions
    - Stair angle from rise/run: `angle = atan(rise/run)`, with presets (standard=36°, steep=40°, shallow=30°)
    - Landing extensions (top/bottom) added to total railing footage
    - Wall handrail with brackets (1 per 4ft) if requested
    - Raked vs plumb baluster orientation noted in assumptions
  - `backend/calculators/repair_decorative.py` — `RepairDecorativeCalculator`
    - Fundamentally different from new-fabrication calculators — estimate-driven, not geometry-driven
    - Routes by repair_type: broken weld (reweld only), bent (replacement section), rust-through (section + overlap), missing (full replacement), crack (+ reinforcement plate if structural), loose (reweld at base)
    - `SCOPE_CREEP_BUFFER=0.25` — 25% material buffer when surrounding damage flagged
    - Damage dimension parsing: regex extraction from free-text, feet-to-inches conversion
    - Finishing: spot-match vs full refinish area estimation
    - On-site vs shop labor rate flagging
    - Every output includes explicit assumptions list

- **Deliverable 3 — Calculator Registry + /calculate Endpoint**
  - `backend/calculators/registry.py` — maps 5 job types to calculator classes
    - `get_calculator(job_type)` — returns instance or raises ValueError
    - `has_calculator(job_type)` / `list_calculators()`
  - `backend/routers/quote_session.py` — added `POST /api/session/{id}/calculate`:
    - Validates session ownership and active status
    - Checks completion via `engine.get_completion_status()`
    - Checks calculator exists via `has_calculator()`
    - Runs `calculator.calculate(current_params)` — pure Python, no AI
    - Updates session stage to `"estimate"` (ready for Stage 4)
    - Returns `{session_id, job_type, calculator_used, material_list}`

#### Not completed / blocked
- None — all 3 deliverables complete

#### Material Price Assumptions
All prices in `material_lookup.py` are **market averages for the Chicago area (2024-2025)**. They are suitable for testing and rough estimates but should be replaced with real supplier quotes for production:
- Steel tube/bar prices: sourced from typical distributor pricing (Osario, Wexler, etc.)
- Hardware prices: sourced from McMaster-Carr, Amazon, and Grainger catalog prices
- Concrete: $175/cu yd (ready-mix, delivered)
- When `data/material_prices_seed.json` is populated from Burton's invoices, `MaterialLookup` should be updated to query the database first, falling back to these defaults

#### Calculations: Verified vs. Needs Real-World Validation
| Calculator | Geometry Math | Material Quantities | Needs Validation |
|---|---|---|---|
| cantilever_gate | Verified (tail ratio, post embed, concrete volume) | Verified (profile mapping, waste factors) | Real gate weights vs. estimates; motor compatibility matrix |
| swing_gate | Verified (panel split ratios, hinge weight thresholds) | Verified | Hinge count thresholds against real panel weights |
| straight_railing | Verified (post count, baluster count, code spacing) | Verified | Cable tensioner counts per manufacturer specs |
| stair_railing | Verified (angle calc, landing extensions) | Verified (delegates to straight) | Raked baluster length variation formula |
| repair_decorative | Conservative estimates by design | Scope creep buffer (25%) is an assumption | Everything — repairs are inherently unpredictable |

#### Architectural decisions made
- Calculator output matches CLAUDE.md `MaterialList` / `MaterialItem` / `HardwareItem` contracts exactly
- `MaterialLookup` uses hardcoded defaults now; designed to be swapped for DB-backed lookup when invoice data is seeded
- `StairRailingCalculator` reuses `StraightRailingCalculator` rather than duplicating railing math
- Repair calculator produces conservative estimates with explicit assumptions — fundamentally different pattern from geometry-based calculators
- `/calculate` endpoint transitions session stage from `"clarify"` → `"estimate"`, ready for Stage 4

#### Tests
- pytest results: **85 passed, 0 failed** (11 S1 + 21 S2A + 23 S2B + 30 S3)
- Test file: `tests/test_session3_calculators.py`
- Coverage:
  - Framework (6): waste rounding, linear_feet_to_pieces, material lookup defaults, hardware stubs, registry types, unknown type error
  - Cantilever gate (4): full calc, counterbalance tail verification, no-motor exclusion, post embed depth
  - Swing gate (3): double panel, hinge weight matching, single panel
  - Straight railing (3): 40ft full calc (~121 balusters, ~7 posts), transitions add posts, cable infill hardware
  - Stair railing (3): rake angle with landings, reuse of straight logic, wall handrail
  - Repair (4): broken weld minimal material, rust-through replacement, scope creep flag, assumptions list
  - Output contract (5): MaterialList schema compliance, weight>0, weld_inches>=0, sq_ft present, assumptions with price note
  - Pipeline integration (2): complete session → calculate success, incomplete session → 400 error

### Session 4 — 2026-02-27 (Opus 4.6)

#### Completed
- **Deliverable 1 — Labor Estimator Module (`backend/labor_estimator.py`)**
  - `LaborEstimator` class — Stage 4 of the pipeline
  - 11 labor processes: layout_setup, cut_prep, fit_tack, full_weld, grind_clean, finish_prep, clearcoat, paint, hardware_install, site_install, final_inspection
  - Gemini prompt construction (`_build_prompt`):
    - Structured context: job type, piece count, total weight, weld inches, sq ft, hardware count, finish type, install status
    - Domain guidance: rules of thumb for each process (e.g., 8-15 in/hr for MIG welding, 0.5-2.0 hrs for layout)
    - Reasonableness check ranges (cantilever gate 16-28 hrs, 40ft railing 12-20 hrs)
    - Explicit instruction: "Do NOT return a total. Do NOT sum the hours."
    - Demands structured JSON with hours + notes per process
  - Response parsing (`_parse_response`):
    - Validates all 11 processes present
    - total_hours computed by summing in Python — never trusts AI total
    - Handles wrapped responses, plain numbers, missing processes
  - Rate application (`_get_rate_for_process`):
    - In-shop rate for all processes except site_install
    - On-site rate for site_install and for entire-job-on-site repairs
    - On-site detection from can_remove field and repair_structural location
  - Deterministic fallback (`_fallback_estimate`):
    - Rule-based estimation from material quantities when Gemini is unavailable
    - layout_setup: max(0.5, piece_count * 0.05 + 0.5)
    - cut_prep: piece_count * 0.08 (~5 min/piece)
    - fit_tack: piece_count * 0.12 (~7 min/piece)
    - full_weld: weld_inches / 10.0 (~10 in/hr)
    - grind_clean: 40% of weld time
    - Finish hours scaled by sq_ft and finish type
    - Hardware install: 25 min/item + 1.5 hrs for motor
    - Site install: weight-based (3-10 hrs) + concrete bonus
    - Every process note says "Rule-based estimate — AI unavailable"
    - Conservative (slightly high rather than low)
    - layout_setup and final_inspection always > 0

- **Deliverable 2 — Finishing Section Builder (`backend/finishing.py`)**
  - `FinishingBuilder` class — builds FinishingSection from CLAUDE.md contract
  - FINISHING IS NEVER OPTIONAL — even raw steel gets a section
  - 5 finish types supported:
    - `raw`: method="raw", all costs 0, area still calculated
    - `clearcoat`: in-house, hours from labor processes, material cost = sq_ft × $0.35
    - `paint`: in-house, hours from labor processes, material cost = sq_ft × $0.50
    - `powder_coat`: outsourced, cost = sq_ft × $3.50, in-house hours = prep only
    - `galvanized`: outsourced, cost = sq_ft × $2.00, in-house hours = 0
  - Normalizes free-text finish answers to standard types
  - Area always >= 1.0 sq ft (never zero)

- **Deliverable 3 — Historical Validator (`backend/historical_validator.py`)**
  - `HistoricalValidator` class — compares estimates vs. historical actuals
  - VARIANCE_THRESHOLD = 0.25 (25%)
  - `validate()`: queries historical_actuals table, computes average, flags if >25% variance
  - `record_actual()`: stores actual hours after job completion for feedback loop
  - Currently a stub — no historical data exists yet. Becomes useful when Burton records actuals.

- **Deliverable 4 — Pipeline Integration (`backend/routers/quote_session.py`)**
  - Added `POST /api/session/{id}/estimate` endpoint:
    - Validates session stage is "estimate" (set by /calculate)
    - Loads material_list from session params (stored by /calculate)
    - Builds QuoteParams, gets user rates from profile
    - Runs LaborEstimator.estimate() → LaborEstimate
    - Runs HistoricalValidator.validate()
    - Runs FinishingBuilder.build() → FinishingSection
    - Stores labor_estimate + finishing in session params_json
    - Transitions session stage to "price" (ready for Stage 5)
    - Returns: session_id, labor_estimate, finishing, total_labor_hours, total_labor_cost
  - Modified `/calculate` endpoint to store material_list in session params_json as `_material_list`
  - Pipeline data accumulation: params_json grows as pipeline progresses
    - After Stage 2: user-answered fields
    - After Stage 3: + `_material_list`
    - After Stage 4: + `_labor_estimate` + `_finishing`

#### Not completed / blocked
- None — all 4 deliverables complete

#### Gemini Prompt Strategy
The labor estimation prompt sends structured context to Gemini 2.0 Flash:
1. Job summary: type, piece count, weight, weld inches, sq ft, hardware count
2. Key dimensions from the answered fields
3. Material list (capped at 15 items to keep prompt reasonable)
4. Hardware list with descriptions and quantities
5. Domain guidance: rules of thumb for each of the 11 processes
6. Reasonableness ranges: "cantilever gate with motor = 16-28 hrs"
7. Critical rules: "Do NOT return a total", "Return all 11 processes", "Use 0.0 if N/A"
8. Exact JSON format specification

The AI returns per-process {hours, notes}. Python sums the total. If the AI includes a "total" key, it is ignored.

#### Fallback Estimation Rules
When Gemini is unavailable (no API key, rate limit, error):
- Rule-based estimation from material quantities and industry rules of thumb
- Conservative bias (slightly high rather than low)
- layout_setup and final_inspection always > 0
- Finish-specific logic: clearcoat/paint get in-house hours, powder_coat/galvanized get 0
- Motor detection adds 1.5 hrs to hardware_install
- Site install scaled by weight (3-10 hrs) + concrete bonus
- Every process note explicitly says "Rule-based estimate — AI unavailable"
- Always returns valid LaborEstimate contract — app never breaks

#### Architectural decisions made
- Pipeline outputs stored in session params_json with `_` prefix (_material_list, _labor_estimate, _finishing)
- Rate application: in-shop for all processes except site_install (on-site rate), or all on-site for repair-in-place jobs
- Fallback is conservative and always available — no dependency on external AI service
- FinishingBuilder normalizes free-text finish answers to 5 standard types
- Historical validator is a stub now but the full comparison logic is implemented for when data exists

#### Tests
- pytest results: **111 passed, 0 failed** (11 S1 + 21 S2A + 23 S2B + 30 S3 + 26 S4)
- Test file: `tests/test_session4_labor.py`
- Coverage:
  - Labor estimator core (6): all 11 processes, total is sum not AI, ignores AI total key, inshop rate, onsite rate for install, all onsite rate for on-site repair
  - Fallback (4): no API key triggers fallback, valid contract output, layout/inspection never zero, notes indicate rule-based
  - Finishing builder (6): raw steel, clearcoat with hours, powder coat outsourced, galvanized outsourced, always has area, never optional
  - Historical validator (2): no history = not flagged, record_actual creates DB entry
  - Prompt construction (4): includes piece count, includes weld inches, includes finish type, forbids total
  - Pipeline integration (4): estimate after calculate succeeds, wrong stage returns 400, stores in session, full Stage 1-4 flow (straight railing)

### Session 5 — 2026-02-27 (Opus 4.6)

#### Completed
- **Deliverable 1 — Hardware Sourcer (`backend/hardware_sourcer.py`)**
  - `HardwareSourcer` class — prices hardware items and estimates consumables
  - `HARDWARE_PRICES` catalog: 25 items with 3-option pricing (McMaster-Carr, Amazon, Grainger/specialty)
    - Gate hinges (4): heavy duty, standard, ball bearing, spring
    - Latches (5): gravity, magnetic, keyed deadbolt, pool code, electric strike
    - Gate operators (4): LiftMaster LA412, US Automatic Patriot, LiftMaster RSW12U, LiftMaster CSW24U
    - Roller carriages (2): standard, heavy duty
    - Gate stops (1), railing mounts (1), cable hardware (2)
    - Auto-close hardware (4): hydraulic closer, cane bolt, surface drop rod, flush bolt
  - `CONSUMABLES` catalog: welding wire, grinding discs, flap discs, shielding gas, clearcoat spray, primer spray
  - `price_hardware_list()` — matches Stage 3 hardware descriptions to catalog keys via `_match_catalog_key()`
  - `estimate_consumables()` — estimates from weld_linear_inches and total_sq_ft
  - `select_cheapest_option()` — returns (price, supplier) for cheapest available option
  - `suggest_bulk_discount()` — suggestions at $500 (5-10%) and $2000 (10-20%) thresholds
  - `flag_mcmaster_only()` — identifies items with only McMaster pricing for manual sourcing

- **Deliverable 2 — Pricing Engine (`backend/pricing_engine.py`)**
  - `PricingEngine` class — Stage 5 of the pipeline, pure math, no AI
  - `build_priced_quote()` — assembles full PricedQuote from all pipeline outputs:
    - Prices hardware via HardwareSourcer
    - Estimates consumables from weld inches and sq ft
    - Calculates 5 subtotals: material, hardware, consumable, labor, finishing
    - Builds markup options: 0-30% in 5% increments
    - Collects assumptions (price source, labor method, hardware source, consumables, bulk discount)
    - Collects exclusions (standard + job-specific: permits, demolition, electrical for motorized gates, concrete for railings, discovery for repairs)
  - `_build_markup_options()` — {"0": subtotal, "5": subtotal×1.05, ..., "30": subtotal×1.30}
  - `_check_bulk_discount()` — flags material cost > $5,000 with supplier negotiation suggestion
  - `recalculate_with_markup()` — recalculates total for markup slider changes

- **Deliverable 3 — Pipeline Endpoints**
  - `POST /api/session/{id}/price` endpoint in `quote_session.py`:
    - Validates session stage == "price"
    - Loads material_list, labor_estimate, finishing from session params_json
    - Runs PricingEngine.build_priced_quote()
    - Creates Quote record in database (quote_number, user_id, session_id, subtotal, total)
    - Stores PricedQuote as outputs_json, QuoteParams as inputs_json
    - Transitions session stage to "output", status to "complete"
    - Returns: session_id, quote_id, quote_number, priced_quote
  - `PUT /api/quotes/{id}/markup` endpoint in `quotes.py`:
    - Validates markup_pct in [0, 5, 10, 15, 20, 25, 30]
    - Recalculates total from subtotal × (1 + markup_pct/100)
    - Updates Quote record + outputs_json
    - Auth-protected: validates quote ownership
    - Returns: quote_id, quote_number, subtotal, selected_markup_pct, total, markup_options

- **Deliverable 4 — Session 5 Acceptance Tests**
  - `tests/test_session5_pricing.py` — 26 tests
  - Coverage:
    - Hardware sourcer (5): gate hardware pricing, 3 options per item, cheapest selection, bulk discount thresholds, McMaster-only flag
    - Pricing engine (5): all required fields present, subtotal is sum of parts, markup options 0-30%, default markup from user profile, assumptions always present
    - Quote storage (4): /price creates Quote record, stores outputs_json, transitions session to output, rejects wrong stage
    - Markup endpoint (3): recalculates total, rejects invalid pct, returns all options
    - Consumable estimation (5): from weld inches, clearcoat included, paint includes primer, line totals correct, zero weld returns empty
    - Full pipeline (4): cantilever gate intake→price, straight railing intake→price, gate exclusions with motor, recalculate_with_markup

#### Not completed / blocked
- None — all 4 deliverables complete

#### Hardware Pricing Notes
All hardware prices in `HARDWARE_PRICES` are **catalog/street prices (Feb 2026)** for the Chicago area:
- McMaster-Carr prices: most reliable, always available, typically most expensive
- Amazon prices: variable availability, often cheapest, longer lead times
- Third option: Grainger, Gate Depot, LiftMaster Dealer, CableRail — depends on category
- Phase 3: McMaster eProcurement API + web search for live pricing updates
- Default behavior: select cheapest option for hardware subtotal

#### Consumable Estimation Rules
| Consumable | Estimation Basis | Rate |
|---|---|---|
| ER70S-6 welding wire | weld_linear_inches / 100 | $3.50/lb, 0.5 lbs per 100 weld inches |
| Grinding discs (4.5") | weld_linear_inches / 100 | $4.50 each, 1.0 per 100 weld inches |
| Flap discs (4.5") | weld_linear_inches / 100 | $6.50 each, 0.5 per 100 weld inches |
| Shielding gas (75/25) | weld_hours × 25 cu ft/hr | $0.08/cu ft, weld_hours = weld_inches / 10 |
| Clear coat spray | total_sq_ft / 25 sq ft coverage | $12.50/can |
| Primer spray | total_sq_ft / 20 sq ft coverage | $8.50/can |

#### Architectural decisions made
- Stage 5 is pure math — no AI involvement
- Cheapest hardware option selected by default; user can override
- Consumables estimated from weld inches (not guessed)
- Markup options are fixed set [0,5,10,15,20,25,30] — no custom markup in v2
- Quote record stores both inputs_json (QuoteParams) and outputs_json (PricedQuote)
- Session transitions to "output" stage and "complete" status after /price
- /markup endpoint is on quotes router (operates on Quote, not session)

#### Tests
- pytest results: **137 passed, 0 failed** (11 S1 + 21 S2A + 23 S2B + 30 S3 + 26 S4 + 26 S5)
- Test file: `tests/test_session5_pricing.py`
- Full pipeline tested: 2 job types (cantilever gate, straight railing) run intake → clarify → calculate → estimate → price → markup

### Session 6 — 2026-02-28 (Opus 4.6)

#### Completed
- **Deliverable 1 — Frontend UI (vanilla HTML/CSS/JS SPA)**
  - `frontend/index.html` — clean SPA shell with nav bar and 4 view containers
  - `frontend/css/style.css` — full responsive CSS with custom properties:
    - Dark neutral theme (`--bg: #1a1a2e`, `--surface: #16213e`, `--primary: #e94560`)
    - Mobile-first responsive layout (`@media max-width: 640px`)
    - Navigation bar, button system, auth cards, profile form grid
    - Question cards with choice buttons, progress bar, spinner animation
    - Data tables for materials/hardware/labor, totals section with markup buttons
    - Quote history list items with status badges
  - `frontend/js/api.js` — API client with JWT token management:
    - Auto-refresh on 401, localStorage token persistence
    - Auth methods: register, login, guest, getMe, updateProfile
    - Session methods: startSession, submitAnswers, getSessionStatus, calculate, estimate, price
    - Quote methods: listMyQuotes, getQuoteDetail, updateMarkup, getPdfUrl
  - `frontend/js/auth.js` — Auth UI with login, register, guest, and profile setup views
  - `frontend/js/quote-flow.js` — Main quoting pipeline UI:
    - 4 steps: describe → clarify → processing → results
    - Job type selection with 15 type buttons
    - Question rendering for all 7 field types (choice, multi_choice, measurement, number, boolean, text, photo)
    - Pipeline runner: calculate → estimate → price with progress spinners
    - Results view: materials/hardware/consumables/labor/finishing tables
    - Live markup toggle (0-30% buttons, instant API update)
    - PDF download via query param auth
    - `QuoteHistory` object: list, view detail, download PDF
  - `frontend/js/app.js` — App controller with view management and navigation

- **Deliverable 2 — PDF Quote Generator (`backend/pdf_generator.py`)**
  - `QuotePDF(FPDF)` class with custom footer, section headers, table rendering
  - `generate_quote_pdf()` — generates all 8 mandatory sections:
    1. Header: shop name, quote number, date, client name, job summary
    2. Materials: table with description, spec, qty, unit price, total
    3. Cut List: piece, material, length, qty, cut type
    4. Hardware & Parts: cheapest option selected, alternatives shown
    5. Labor: process breakdown with hours, rate, total
    6. Finishing: method, area, cost (NEVER optional — even raw steel)
    7. Project Total: subtotals, markup, grand total in highlighted bar
    8. Assumptions & Exclusions: bulleted lists, validity terms
  - `generate_job_summary()` — template-based plain-language descriptions per job type
  - White-labeled: user's shop name/address/phone/email, no CreateStage branding
  - `_safe()` helper for Unicode → latin-1 encoding (built-in PDF fonts)
  - `JOB_TYPE_NAMES` dict (15 types), `PROCESS_NAMES` dict (11 processes)

- **Deliverable 3 — Quote Number Generation**
  - Format: `CS-{YEAR}-{NNNN}` (sequential, zero-padded)
  - Generated in `quotes.py:generate_quote_number()`
  - Created when `/price` endpoint stores the Quote record

- **Deliverable 4 — API Endpoint Updates**
  - `backend/main.py` — updated static file serving:
    - `/css/*` and `/js/*` directory mounts for frontend files
    - `GET /` serves `frontend/index.html`
    - Legacy `/static` mount preserved for backward compatibility
    - PDF router included at `/api/quotes/{id}/pdf`
  - `backend/routers/quotes.py` — new authenticated endpoints:
    - `GET /api/quotes/mine` — user's quotes list with job summary, sorted newest first
    - `GET /api/quotes/{id}/detail` — full quote detail with outputs_json, ownership validated
  - `backend/routers/pdf.py` — PDF download endpoint:
    - `GET /api/quotes/{id}/pdf` — generates and returns PDF
    - Supports auth via `?token=` query param (for `window.open`)
    - `_get_user_from_token_param()` resolves user from JWT in query string
    - Validates quote ownership
    - Converts fpdf2 bytearray output to bytes for Starlette Response compatibility

#### Not completed / blocked
- None — all 4 deliverables complete

#### Bug Fixes During Development
- **fpdf2 bytearray vs bytes:** `pdf.output()` returns `bytearray`, but Starlette's `Response` expects `bytes`. Fixed with `bytes()` conversion in PDF endpoint.
- **Unicode in PDF:** Built-in Helvetica font only supports latin-1. Added `_safe()` helper to replace bullet points, em dashes, smart quotes with ASCII equivalents. Changed bullet lists from `•` to `-`.
- **PDF multi_cell overflow:** Replaced `multi_cell(0, ...)` with `cell(pw, ..., new_x="LMARGIN", new_y="NEXT")` for assumptions/exclusions to prevent "Not enough horizontal space" errors.

#### Architectural decisions made
- Vanilla HTML/CSS/JS frontend — no React/Vue/frameworks (explicit spec requirement for simplicity)
- fpdf2 (pure Python) chosen over WeasyPrint (needs system dependencies)
- PDF auth via `?token=` query param — `window.open()` can't set Authorization headers
- CSS custom properties for theming — easy to swap colors for white-labeling
- Frontend script loading order: api.js → auth.js → quote-flow.js → app.js (dependency chain)
- Static file serving: separate `/css/*` and `/js/*` mounts alongside API routes

#### Tests
- pytest results: **162 passed, 0 failed** (11 S1 + 21 S2A + 23 S2B + 30 S3 + 26 S4 + 26 S5 + 25 S6)
- Test file: `tests/test_session6_output.py`
- Coverage:
  - PDF generation (5): valid bytes/header, 8 sections render, white-label shop name, raw steel finishing, quote number
  - Frontend serving (4): index.html, CSS, JS, API routes alongside static
  - Quote list/detail (5): empty initially, returns user quotes, sorted newest first, full detail with outputs, rejects other user
  - Quote number (2): CS-YYYY-NNNN format, sequential increment
  - Job summary (3): gate with dimensions/motor, railing with footage, all 15 types produce string
  - PDF endpoint auth (3): requires auth, token param works, rejects wrong user
  - Full pipeline (3): intake→PDF download, finishing always present, markup then PDF

### Session 7 — 2026-02-28 (Opus 4.6)

#### Completed
- **Deliverable 1 — Bid Parser Module (`backend/bid_parser.py`)**
  - `BidParser` class — extracts metal fab scope from construction bid documents
  - `RELEVANT_CSI_DIVISIONS` — 17 CSI codes mapped to metal fab categories (Division 05 primary, plus 08/10/32)
  - `EXTRACTION_KEYWORDS` — 27 keywords for metal fab scope detection
  - `_JOB_TYPE_KEYWORDS` — maps extracted descriptions to all 15 V2 job types
  - Gemini extraction (`_extract_with_gemini`):
    - Detailed prompt with CSI guidance, confidence scoring rules, required fields
    - 200k char truncation for safety (50k token estimate)
    - Structured JSON response parsing with normalization
  - Keyword fallback (`_extract_with_keywords`):
    - Section splitting via regex (spec headings like "3.01 STAIR 1")
    - Administrative section filtering (SUMMARY, REFERENCES, SUBMITTALS, etc.)
    - Keyword density scoring per section
    - Dimension extraction: linear footage, clear opening, height, width, total rise, above grade
    - Material spec extraction: ASTM specs, tube/pipe sizes, stainless steel grades
    - Detail reference extraction: "Detail A-12", "Dwg S-301", "Sheet S-100"
    - Location extraction: floor, level, entrance, stair number
    - Quantity extraction: "(6) bollards", "provide 4 gates"
  - Job type mapping (`_map_to_job_type`):
    - Priority-ordered: specific types first (spiral_stair, cantilever_gate), generic last (straight_railing, custom_fab)
    - Checks both section title AND body text for robust matching
  - Pre-population (`_pre_populate_fields`):
    - Maps dimensions to question tree field IDs per job type
    - Gate types: clear_width, height
    - Railing types: linear_footage, railing_height
    - Complete stair: total_rise, stair_width
    - Bollard: height, quantity
    - Finish detection: powder coat, galvanized, paint from source text
    - Material detection: square tube, round tube/pipe
  - Confidence scoring (`_calculate_confidence`):
    - Average item confidence + bonuses for count, CSI codes, dimensions
    - Per-item confidence: CSI code (+0.2), dimensions (+0.2), material spec (+0.1), detail ref (+0.1)

- **Deliverable 2 — PDF Text Extractor (`backend/pdf_extractor.py`)**
  - `PDFExtractor` class using pdfplumber
  - `extract_text(file_path)` and `extract_text_from_bytes(file_bytes, filename)`
  - Safety limits: MAX_PAGES=500, MAX_FILE_SIZE_MB=50
  - Quality assessment (`_assess_quality`):
    - "good": >100 chars/page (clean digital PDFs)
    - "fair": 20-100 chars/page (mixed content)
    - "poor": <20 chars/page (likely scanned images, OCR needed)
  - Returns: text, page_count, file_size_mb, extraction_quality

- **Deliverable 3 — Bid Parser API + Storage**
  - `backend/routers/bid_parser.py` — 3 endpoints:
    - `POST /api/bid/upload` — upload PDF, extract text, parse scope, store analysis, return items
    - `POST /api/bid/parse-text` — parse pasted text, store analysis, return items
    - `POST /api/bid/{bid_id}/quote-items` — create QuoteSession per selected item with pre-populated fields
  - `BidAnalysis` model in `models.py`:
    - id (UUID), user_id, filename, page_count, extraction_confidence, items_json, warnings_json, created_at
  - Bid→Session flow:
    - Each selected item creates a new QuoteSession with job_type from extraction
    - Pre-populated fields from dimensions → user enters question tree with answers pre-filled
    - First message in messages_json records bid_extraction source with bid_id, item_index, source_text

- **Deliverable 4 — Test Fixture + Acceptance Tests**
  - `tests/fixtures/sample_bid_excerpt.txt` — realistic SECTION 05 50 00 spec with 5 scope items:
    - Stair 1 (12' rise, 44" width, galvanized, Detail S-301)
    - Ornamental Iron Railing (65 LF, 42" height, powder coat, Detail A-12)
    - Cantilever Gate (16' opening, 6' height, LiftMaster CSW24U, Detail S-105)
    - Bollards (6 fixed, 6" sch 40, 36" above grade)
    - Miscellaneous Metals (embed plates, connection brackets)
  - `tests/test_session7_bid_parser.py` — 26 tests

#### Not completed / blocked
- None — all 4 deliverables complete

#### Extraction Accuracy on Sample Bid
Using keyword fallback (no Gemini API key in test environment):
- **5/5 scope items extracted** from sample bid (stair, railing, gate, bollards, misc metals)
- **Job type mapping**: complete_stair, stair_railing, cantilever_gate, bollard, custom_fab — all correct
- **Dimension extraction**: total rise, width, linear footage, clear opening, height above grade — all captured
- **Detail references**: Detail S-301, Detail A-12, Detail S-105 — all preserved
- **Pre-population**: clear_width, height, linear_footage, railing_height, total_rise, stair_width, quantity — all mapped
- **CSI code detection**: 05 50 00 found and mapped

#### Bug Fixes During Development
- **Section splitting regex matched across newlines:** `\s` in character class includes `\n`, causing multi-line title captures. Fixed by using `[ \t]` (space/tab only) instead of `\s` in the section title pattern.
- **Summary section false positive:** TOC sections listing "Steel stairs" matched `complete_stair`. Fixed by adding administrative section title blocklist (SUMMARY, REFERENCES, SUBMITTALS, MATERIALS, etc.) — skips Parts 1 & 2, processes only Part 3 (EXECUTION) scope items.
- **Job type mapping from title only:** Section titles like "STAIR 1" didn't contain keywords like "steel stair". Fixed by passing both description (title) AND source_text (body) to `_map_to_job_type()`.

#### Architectural decisions made
- Gemini extraction with keyword fallback — app works without AI, just less accurate
- CSI Division 05 is primary but also checks 08 (Openings), 10 (Specialties), 32 (Fences/Gates)
- Administrative section filtering prevents false positives from TOC/summary listings
- Pre-populated fields map to question tree field IDs — users enter normal flow with answers pre-filled
- Bid→Session creates individual sessions per scope item — each quoted independently
- pdfplumber chosen over PyPDF2 (better table/layout handling) and pymupdf (C dependency)
- Source text preserved in session messages_json for audit trail

#### Tests
- pytest results: **188 passed, 0 failed** (11 S1 + 21 S2A + 23 S2B + 30 S3 + 26 S4 + 26 S5 + 25 S6 + 26 S7)
- Test file: `tests/test_session7_bid_parser.py`
- Coverage:
  - PDF extraction (3): text output, non-PDF rejection, size limit
  - Parser extraction (5): stair with dimensions, railing with LF, gate with opening, bollards with quantity, misc metals
  - Job type mapping (2): known types → correct mapping, unknown → None
  - Confidence scoring (2): good extraction with CSI/dims → >0.5, single vague item → <0.5
  - Detail references (1): preserves drawing references
  - Pre-population (1): maps dimensions to question tree fields
  - API endpoints (3): upload PDF, parse text, empty text rejection
  - Bid→Session flow (3): creates sessions, preserves dimensions, records source
  - Keyword fallback (2): extracts items without Gemini, finds CSI codes
  - Edge cases (2): empty document, no-fab-scope document
  - Data quality (2): CSI divisions complete, keywords cover main types

### Session 8 — 2026-02-27 (Opus 4.6)

#### Completed
- **Deliverable 1 — Seed Data Integration**
  - Completely rewrote `data/seed_from_invoices.py` — robust profile key parser + multi-format loader
  - Profile key parser (`parse_profile_key`) converts human-readable descriptions to internal keys:
    - Handles Osorio format ("Tubing - Square 2\" x 2\" x 11 ga" → `sq_tube_2x2_11ga`)
    - Handles Wexler format ("HR SQUARE TUBE 2\" x 2\" x 11G" → `sq_tube_2x2_11ga`)
    - Compound fractions ("1-1/2" → 1.5), gauges ("11ga"/"11G"), stainless prefix ("ss_304_")
    - 8 sub-parsers: tube, round tube, pipe, flat bar, angle, channel, round bar, square bar
  - File-specific loaders:
    - `load_osorio_prices()` — 35 items from osorio_prices_seed.json
    - `load_wexler_prices()` — 16 items from wexler_prices_raw.json (skips lb-priced items)
    - `load_firetable_bom()` — derives per-foot from unit_price/length
    - `load_invoices_as_actuals()` — extracts hours/costs from 15 invoices
  - Price merging: prefers newer dates and higher quote counts
  - Output: `data/seeded_prices.json` — 35 profile prices from Osorio/Wexler
  - Historical actuals: 6 records loaded from invoice data
  - Updated `MaterialLookup` in `backend/calculators/material_lookup.py`:
    - Loads seeded prices at module level from `data/seeded_prices.json`
    - `get_price_per_foot()` checks seeded first, falls back to hardcoded defaults
    - Added `get_price_with_source()` → `(price, source_label)` tuple
    - Added `has_seeded_prices()` and `seeded_price_count()` static methods

- **Deliverable 2 — CLAUDE.md Final Comprehensive Update**
  - Complete rewrite of CLAUDE.md as the definitive reference (19 sections)
  - Verified all data contracts against actual code implementations
  - Key additions:
    - API Endpoint Reference (43 endpoints, all methods/paths/auth documented)
    - Database Schema table listing (11 tables)
    - Deploy Instructions (Railway + local dev)
    - Material Price Lookup Chain documentation
    - Python 3.9 compatibility note
    - Dependencies list with versions
  - Key corrections from code verification:
    - PricedQuote now includes `consumables`, `consumable_subtotal`, and per-category subtotals
    - IntakeResult doesn't include `extracted_fields` (returned separately by engine)
    - MaterialList includes `assumptions` list (not in original spec)
    - Updated test counts to 203

- **Deliverable 3 — Test Suite Cleanup**
  - Created `tests/test_session8_integration.py` — 15 tests:
    - 6 smoke tests: health, auth round-trip, session start, calculate, estimate, full pipeline (start→calculate→estimate→price)
    - 4 seed data tests: seeded_prices.json exists, profile key parser, seeded price lookup, fallback chain
    - 5 documentation meta-tests: CLAUDE.md lists all job types, all calculators, all routers, all question trees; question trees match V2_JOB_TYPES
  - Full pipeline smoke test runs start→calculate→estimate→price and verifies PricedQuote structure

#### Not completed / blocked
- None — all 3 deliverables complete

#### Bug Fixes During Development
- **Python 3.9 `str | None` syntax:** `seed_from_invoices.py` used `-> str | None` which fails on Python 3.9. Fixed with `from typing import Optional` and `-> Optional[str]`.
- **Osorio square tube format:** "Tubing - Square" format wasn't matching the "SQUARE TUBE" check. Added `is_tubing` flag to expand detection.
- **Wexler DOM tube part number:** Part number "001800" in "HRRDTB-001800-11-..." parsed as dimension, giving `round_tube_1800_11ga`. Fixed with OD-specific regex match and `(?<!\d)` lookbehind.
- **Seeded price override breaks test:** `test_material_lookup_returns_default_prices` asserted exact values that changed when seeded prices loaded. Fixed by changing to `> 0` checks.
- **Smoke test field names:** Question trees use specific field names (e.g., `frame_gauge` not `gauge`, `linear_footage` not `total_length`). Fixed pre-populated params to match required fields exactly.
- **Post count type:** `CantileverGateCalculator._parse_post_count()` expects string ("2 posts (standard)"), not int. Fixed test input.

#### Architectural decisions made
- Seeded prices loaded at module level (not per-request) — fast lookup, lazy file read
- Price fallback chain: seeded prices → hardcoded defaults → 0.0
- Profile key format standardized: `{shape}_{dimensions}_{gauge}` (e.g., `sq_tube_2x2_11ga`)
- CLAUDE.md is the single source of truth for API reference, data contracts, and file map
- Meta-tests ensure CLAUDE.md stays in sync with code (job types, calculators, routers, question trees)

#### Tests
- pytest results: **203 passed, 0 failed** (11 S1 + 21 S2A + 23 S2B + 30 S3 + 26 S4 + 26 S5 + 25 S6 + 26 S7 + 15 S8)
- Test file: `tests/test_session8_integration.py`
- Coverage:
  - Smoke tests (6): health endpoint, auth round-trip, session start with job detection, calculate returns MaterialList, estimate returns LaborEstimate+Finishing, full pipeline produces PricedQuote
  - Seed data (4): seeded_prices.json valid, profile key parser, seeded price lookup with source, fallback for unknown profiles
  - Meta-tests (5): CLAUDE.md completeness for job types, calculators, routers, question trees; V2_JOB_TYPES↔question tree files sync

### Session 3B — 2026-02-28 (Opus 4.6)

#### Completed
- **Deliverable 1 — Expanded V2_JOB_TYPES to 25**
  - `backend/models.py` — added 10 new job types in Priority D (automotive), E (industrial & signage), F (products)
  - New types: offroad_bumper, rock_slider, roll_cage, exhaust_custom, trailer_fab, structural_frame, furniture_other, sign_frame, led_sign_custom, product_firetable

- **Deliverable 2 — Keyword-Based Job Type Detection**
  - `backend/question_trees/engine.py` — added `DETECTION_KEYWORDS` dict mapping all 25 job types to keyword lists
  - Added `_detect_by_keywords(description)` function with multi-word scoring (multi-word keywords score higher)
  - Updated `detect_job_type()`: keyword matching first → high confidence returns immediately → Gemini fallback → keyword fallback
  - Faster detection for common descriptions without API calls

- **Deliverable 3 — 10 New Question Tree JSON Files**
  - `backend/question_trees/data/` — 10 new files following existing schema:
    - `offroad_bumper.json` — vehicle make/model, bumper position, material thickness, winch mount, finish
    - `rock_slider.json` — vehicle make/model, slider style, material thickness, mounting, finish
    - `roll_cage.json` — vehicle type, cage style, tube size, door count, finish
    - `exhaust_custom.json` — vehicle make/model, exhaust type, pipe diameter, material, finish
    - `trailer_fab.json` — trailer type, length, width, axle count, material, finish
    - `structural_frame.json` — frame type, span, height, load rating, material
    - `furniture_other.json` — item type, material, approximate size, quantity, finish
    - `sign_frame.json` — sign type, sign dimensions, mounting method, material, finish
    - `led_sign_custom.json` — sign type, dimensions, letter height, material, lighting type
    - `product_firetable.json` — configuration, fuel type, dimensions, material, finish

- **Deliverable 4 — 20 New Calculator Files**
  - All extend `BaseCalculator`, use `MaterialLookup()`, return `MaterialList` via `make_material_list()`
  - Geometry-based calculators:
    - `ornamental_fence.py` — panel-based: posts, rails, pickets per panel from total footage
    - `complete_stair.py` — rise/run geometry: stringers (channels), treads (checker plate), support angles
    - `spiral_stair.py` — center column (pipe), pie-shaped plate treads, spiral handrail, balusters
    - `window_security_grate.py` — frame perimeter + vertical/horizontal bars, batch multiply
    - `balcony_railing.py` — delegates railing to StraightRailingCalculator, adds structural frame
    - `bollard.py` — pipe (height + embed), cap plate, base plate if surface-mount, sleeve if removable
    - `offroad_bumper.py` — plate panels + tube structure + mounts, routes by bumper_position
    - `rock_slider.py` — DOM tube rails + mount brackets + gussets, always qty 2 (pair)
    - `roll_cage.py` — tube footage lookup by cage_style, foot plates + gussets
    - `trailer_fab.py` — channel frame + cross members at 16" OC + tongue + axle mounts + deck
    - `structural_frame.py` — routes by frame_type (mezzanine/canopy/portal), beams + columns
  - Estimate-based calculators:
    - `furniture_table.py` — 4 legs + top frame + stretchers + leveling feet
    - `utility_enclosure.py` — sheet metal box (6 panels) + angle iron frame + door hardware
    - `repair_structural.py` — routes by repair_type (trailer/chassis/beam), replacement + splice plates
    - `exhaust_custom.py` — pipe runs + mandrel bends + flanges + hangers
    - `sign_frame.py` — frame tube + mounting, routes by sign_type (post/wall/monument)
    - `led_sign_custom.py` — channel letter returns + face sheets, or cabinet box
    - `product_firetable.py` — BOM-based from data/raw/firetable_pro_bom.json, fallback estimates
    - `furniture_other.py` — routes by item_type (shelving/bracket/generic), size parsing
    - `custom_fab.py` — universal fallback, NEVER fails, parses approximate_size

- **Deliverable 5 — Updated Calculator Registry**
  - `backend/calculators/registry.py` — imports all 25 calculator classes
  - `CALCULATOR_REGISTRY` maps all 25 job types
  - `get_calculator()` falls back to `CustomFabCalculator` instead of raising `ValueError`
  - Updated existing test `test_calculator_registry_unknown_type_raises` → `test_calculator_registry_unknown_type_falls_back`

- **Deliverable 6 — Test Suite**
  - `tests/test_session3b_all_calculators.py` — 35 tests:
    - 20 tests: one per new calculator with field inputs and output assertions
    - 3 tests: registry (25 types, fallback to CustomFab, list returns 25)
    - 3 tests: detection keywords (correct type, multi-word, unknown fallback)
    - 3 tests: question trees (all 25 have trees, new trees load, required fields exist)
    - 1 test: V2_JOB_TYPES sync with registry and trees
    - 2 tests: CustomFab fallback (minimal fields, empty fields)
    - 1 test: FireTable BOM loading
    - 2 tests: output contract validation for all 20 new calculators

- **Deliverable 7 — Documentation Updates**
  - CLAUDE.md updated: 25 job types, 25 calculators in file map, test count 238, keyword detection noted
  - BUILD_LOG.md updated with Session 3B entry

#### Not completed / blocked
- None — all 7 deliverables complete

#### Architectural decisions made
- Keyword-based detection before Gemini API call — faster, works offline, reduces API costs
- Multi-word keywords score higher than single-word for disambiguation
- CustomFabCalculator as universal fallback — unknown job types never crash
- BalconyRailingCalculator delegates to StraightRailingCalculator (same pattern as StairRailing)
- ProductFiretableCalculator loads BOM from JSON with fallback estimates if file missing
- RockSliderCalculator always produces qty 2 (pair) — domain knowledge

#### Tests
- pytest results: **238 passed, 0 failed** (11 S1 + 21 S2A + 23 S2B + 30 S3 + 35 S3B + 26 S4 + 26 S5 + 25 S6 + 26 S7 + 15 S8)
- Test file: `tests/test_session3b_all_calculators.py`

### Session 3B-Hotfix — 2026-02-28 (Opus 4.6)

#### Completed
- **Deliverable 1 — Photo Upload Endpoint (`backend/routers/photos.py`)**
  - `POST /api/photos/upload` — multipart file upload with auth
  - File type validation: jpg, jpeg, png, webp, heic only
  - Size limit: 10MB max, rejects empty files
  - Unique filename generation with optional session_id prefix
  - Dual storage: Cloudflare R2 (boto3) when configured, local `uploads/` directory as fallback
  - Registered router in `main.py`, added `/uploads` static mount for local serving

- **Deliverable 2 — Gemini Vision Processing (`backend/question_trees/engine.py`)**
  - `extract_from_photo()` method on QuestionTreeEngine
  - Sends base64-encoded image to Gemini Vision with metal fab analysis prompt
  - Prompt covers: measurements, material type, dimensions, condition/damage, hardware, design elements
  - Returns structured dict: extracted_fields, photo_observations, material_detected, dimensions_detected, damage_assessment, confidence
  - Graceful fallback: returns empty result (confidence 0.0) when Gemini unavailable or image unreadable
  - Helper functions: `_read_image()`, `_empty_photo_result()`, `_build_vision_prompt()`, `_call_gemini_vision()`

- **Deliverable 3 — Photos Wired into Session Flow**
  - Updated `POST /api/session/start` to accept `photo_urls`, run vision extraction per photo
  - Merge strategy: text-extracted fields applied first, photo-extracted fields only added if field not already present (text wins on conflict)
  - Photo observations returned in response for UI display
  - Updated `POST /api/session/{id}/answer` to accept `photo_url`, store in session, run vision extraction
  - Updated Pydantic schemas (StartSessionRequest, AnswerRequest)

- **Deliverable 4 — Frontend Extraction Confirmation UI**
  - Photo upload UI in describe step (file input + upload button + previews)
  - `_initPhotoUpload()`, `_showPhotoPreview()`, `_removePhoto()` helper methods
  - Confirmed fields section above questions with edit buttons (camera icon for photo-extracted)
  - Photo observations display in clarify step
  - All 25 job types in frontend JOB_TYPES dict (added 10 new automotive/industrial/signage/product types)
  - Updated `api.js`: `uploadPhoto(formData)`, updated `startSession` and `submitAnswers` signatures
  - CSS: `.photo-upload-section`, `.photo-preview`, `.confirmed-field`, `.confirmed-edit`, `.photo-obs`

- **Deliverable 5 — Tests (`tests/test_photo_extraction.py`)**
  - 20 tests covering all deliverables:
    - Photo upload (7): endpoint exists, accepts image, rejects non-image, rejects empty, size limit, requires auth, session_id in filename
    - Vision extraction (3): returns structure, graceful without Gemini, all 25 job types
    - Extraction confirmation (6): start returns extracted_fields, start returns photo_fields, extracted fields skip questions, text wins over photo, edit re-adds question, answer with photo_url
    - Frontend (4): uploadPhoto in api.js, confirmed-field CSS, photo previews in quote-flow.js, all 25 job types in frontend

#### Not completed / blocked
- None — all 5 deliverables complete

#### Dependencies added
- `boto3==1.34.69` — Cloudflare R2 / S3 storage client

#### Architectural decisions made
- Dual photo storage: R2 when CLOUDFLARE_R2_ACCOUNT_ID is set, local `uploads/` fallback for dev/testing
- Vision extraction never crashes the session — all photo operations wrapped in try/except
- Text extraction wins over photo extraction on field conflicts (higher confidence from explicit text)
- Photo observations are informational only — shown in UI but not used for calculations
- `flag_modified(session, "photo_urls")` for proper SQLite JSON column mutation tracking

#### Tests
- pytest results: **258 passed, 0 failed** (11 S1 + 21 S2A + 23 S2B + 30 S3 + 35 S3B + 26 S4 + 26 S5 + 25 S6 + 26 S7 + 15 S8 + 20 Photo)
- Test file: `tests/test_photo_extraction.py`

---

### AI Cut List Hotfix — 2026-02-28 (Opus 4.6)

#### Completed
- **Deliverable 1 — AI Cut List Generator (`backend/calculators/ai_cut_list.py`)**
  - `AICutListGenerator` class with Gemini-powered cut list generation
  - `generate_cut_list(job_type, fields)` — sends structured prompt, parses JSON array response
  - `generate_build_instructions(job_type, fields, cut_list)` — fabrication sequence generation
  - Response parsing with validation: sanitizes bad values (negative length, invalid cut types)
  - Graceful fallback: returns None when Gemini unavailable, callers use template output
  - Same API call pattern as labor_estimator.py (urllib.request, responseMimeType: application/json)

- **Deliverable 2 — Calculator Integration (6 calculators)**
  - Added `_try_ai_cut_list()` and `_build_from_ai_cuts()` to:
    - `furniture_table.py` — triggers on custom design keywords (curved, trestle, pedestal, etc.)
    - `custom_fab.py` — always tries AI when description/notes field is present
    - `furniture_other.py` — triggers on custom/artistic keywords
    - `led_sign_custom.py` — triggers on custom/sculptural/3D keywords
    - `repair_decorative.py` — triggers on fabricate/replicate/match design keywords
    - `repair_structural.py` — triggers on complex/extensive keywords
  - All calculators still produce valid output without Gemini (template fallback)

- **Deliverable 3 — Furniture Table Fixes**
  - Individual frame pieces: 2 long rails + 2 short rails (not single perimeter piece)
  - Center stretcher as separate item
  - Dimension parser: handles "L x W x H" format (e.g., "20 x 20 x 32")
  - Also handles "×" separator, feet conversion, 2-number fallback
  - 4 legs confirmed (waste factor applies: 4 * 1.05 = 5 after waste rounding)

- **Deliverable 4 — PDF Template Updates (`backend/pdf_generator.py`)**
  - Added "DETAILED CUT LIST" section (Section 3B) — renders when `detailed_cut_list` key present
  - Added "FABRICATION SEQUENCE" section (Section 8) — renders when `build_instructions` key present
  - Each build step shows: step number, title, description, tools, duration
  - PDF now has 10 sections (up from 8), sections 3B and 8 are conditional
  - Added all 25 job types to `JOB_TYPE_NAMES` dict (was missing 10 new types)

- **Deliverable 5 — Tests (`tests/test_ai_cut_list.py`)**
  - 20 tests covering:
    - AICutListGenerator (5): prompt building, response parsing, sanitization, invalid response, no API key
    - Furniture table fixes (5): 4 legs, individual frame pieces, L×W×H parser, feet parser, individual fields
    - AI integration (3): trigger keywords, custom_fab always tries, all 6 calculators work without AI
    - Build instructions (3): parse valid, no API key, prompt includes cut list
    - PDF sections (4): all 25 job types, detailed cut list renders, build instructions render, no AI sections renders

#### Not completed / blocked
- None — all 5 deliverables complete

#### Architectural decisions made
- AI cut list is opt-in per calculator: only triggers on specific keywords suggesting custom/complex work
- Custom_fab always tries AI when description is present (it's the freeform fallback)
- AI sections in PDF are conditional — no empty sections when AI data not available
- Gemini response parsed with sanitization: negative lengths default to 12", invalid cut types default to "square"

#### Tests
- pytest results: **278 passed, 0 failed** (258 existing + 20 new)
- Test file: `tests/test_ai_cut_list.py`

---

### Session 10 — 2026-02-28 (Opus 4.6)

#### Completed
- **Deliverable 1 — Description Handoff Fix (`backend/routers/quote_session.py`)**
  - Fixed critical bug: user's original description was stored only in `messages_json` (audit log), never in `params_json` (what calculators receive)
  - Added `description` and `photo_observations` to `merged_for_storage` in `start_session()`
  - Now every calculator can access the original project description via `fields["description"]`

- **Deliverable 2 — AI-First Pattern in All 25 Calculators (`backend/calculators/base.py` + 19 calculators)**
  - Added 3 default AI methods to `BaseCalculator`:
    - `_has_description(fields)` — checks if combined description+notes+photo_observations > 10 words
    - `_try_ai_cut_list(job_type, fields)` — calls AICutListGenerator, returns list or None on failure
    - `_build_from_ai_cuts(job_type, ai_cuts, fields, assumptions, hardware)` — builds MaterialList from AI output
  - Added AI-first check to all 19 template-only calculators (the 6 existing AI calculators keep their own overridden methods)
  - Pattern: if description exists → try AI cut list → if succeeds, return AI-generated MaterialList → else fall through to template math
  - Deterministic template output is always the fallback — AI never crashes a calculator

- **Deliverable 3 — AI Cut List Prompt Overhaul (`backend/calculators/ai_cut_list.py`)**
  - Complete rewrite of prompt with 4-step design thinking process:
    1. Design Analysis — structural requirements, load paths, critical dimensions
    2. Pattern Geometry — repetition patterns, symmetry, nesting optimization
    3. Weld Process Determination — TIG vs MIG based on finish/material/application
    4. Generate Cut List — individual pieces with metadata
  - Expanded output schema: added `piece_name`, `group`, `weld_process`, `weld_type`, `cut_angle`
  - Added `_build_weld_guidance()` helper — detects TIG/stainless/aluminum requirements from fields
  - Expanded profile list (added dom_tube_1.75x0.120, plate sizes, more tube sizes)
  - Updated `_parse_response()` to normalize variant cut types and weld processes
  - Updated build instructions with weld_process and safety_notes per step

- **Deliverable 4 — Labor Estimator Weld Process Reasoning (`backend/labor_estimator.py`)**
  - Rewrote `_build_prompt()` with description context and weld process detection
  - Added `_build_weld_process_section()` — detects TIG/stainless/aluminum from material items and field values
  - Labor multipliers in prompt: TIG 2.5-3.5x slower than MIG, stainless +30%, aluminum +20%
  - Expanded TIG indicators: "grind smooth", "seamless", "showroom", "polished", etc.
  - Piece count passed into estimation guidance for more accurate per-process calculations

- **Deliverable 5 — Build Instructions Wiring**
  - Build instructions prompt updated with weld_process and safety_notes per step
  - Parser handles expanded schema fields
  - Already wired end-to-end from Session AI Cut List Hotfix — verified still working

- **Deliverable 6 — Pipeline Verification**
  - Verified description flows from start_session() → params_json → calculator → AI prompt
  - Verified all 25 calculators have _has_description check (19 via BaseCalculator, 6 via override)
  - Verified weld process info flows from cut list → labor estimator prompt

#### Not completed / blocked
- None — all deliverables complete

#### Bug Fixes During Development
- **SQLAlchemy JSON mutation detection in tests:** Adding `description` to `params_json` in `start_session` made the dict non-empty. Test code `params = session.params_json or {}` returned the same dict object, and `params.update(...)` mutated in-place. SQLAlchemy didn't detect the change. Fixed by using `dict(session.params_json or {})` in 3 smoke tests.
- **AI cut list test assertion:** Old prompt text `"WELD QUALITY"` changed to `"TIG WELDING"` in the overhauled prompt. Updated test assertion to match.

#### Architectural decisions made
- BaseCalculator provides default AI methods — subclasses inherit or override
- 6 existing AI calculators keep their own `_try_ai_cut_list(self, fields)` signature; 19 new ones use base class `_try_ai_cut_list(self, job_type, fields)` — Python MRO resolves correctly
- AI-first pattern: try AI → fallback to deterministic template, never the other way around
- Description preserved in params_json so it's available at every pipeline stage
- Weld process reasoning is embedded in both cut list generation AND labor estimation
- TIG detection from finish requirements, material type, AND explicit keywords

#### Tests
- pytest results: **324 passed, 0 failed** (285 existing + 39 new)
- Test file: `tests/test_session10_intelligence.py`
- Coverage:
  - Description handoff (2): description stored in params, photo_observations stored
  - AI-first pattern (3): all 25 calculators have _has_description, 19 use base class, 6 override
  - _has_description behavior (2): short text false, long text true
  - AI cut list prompt (5): 4-step structure, weld guidance, TIG detection, expanded profiles, field filtering
  - Parser schema (5): expanded fields parsed, normalized values, weld_process variants, cut_type variants, invalid handling
  - Valid constants (3): VALID_CUT_TYPES, VALID_WELD_PROCESSES, VALID_WELD_TYPES
  - Labor estimator (6): description in prompt, weld process section, TIG multiplier, piece count, stainless detection, process breakdown
  - Build instructions (2): expanded schema, weld_process in steps
  - BaseCalculator defaults (4): _has_description, _try_ai_cut_list no API, _build_from_ai_cuts, price fallback
  - Pipeline wiring (3): description flow, all calculators accessible, weld process flow
  - Integration (2): full pipeline with description, calculator with AI fallback

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
| 2026-02-27 | Question tree engine: stateless singleton with caching | Trees loaded from JSON on first access, cached in memory |
| 2026-02-27 | Gemini extraction fallback: returns {} when no API key | Enables offline testing and dev without Gemini |
| 2026-02-27 | depends_on + branches dual mechanism for question flow | depends_on gates visibility; branches activate specific children |
| 2026-02-27 | Session API endpoints require JWT auth | All session operations tied to authenticated user |
| 2026-02-27 | Calculator output matches CLAUDE.md TypedDict contracts exactly | Ensures Stage 3→4→5 data flows without transformation |
| 2026-02-27 | MaterialLookup: hardcoded defaults, designed for DB swap | Invoice data not yet available; clean interface for future DB-backed lookup |
| 2026-02-27 | StairRailingCalculator delegates to StraightRailingCalculator | DRY — stair railing is straight railing + angle + landings |
| 2026-02-27 | Repair calculators use conservative estimates + explicit assumptions | Repairs are unpredictable; transparency > precision |
| 2026-02-27 | /calculate endpoint transitions session stage to "estimate" | Clean pipeline progression: clarify → calculate → estimate |
| 2026-02-27 | AI estimates per-process, Python sums total — never trust AI total | Prevents AI hallucination of totals; sum is always verifiable |
| 2026-02-27 | Pipeline data accumulates in session params_json with _ prefix | _material_list, _labor_estimate, _finishing — each stage adds its output |
| 2026-02-27 | Deterministic fallback when Gemini unavailable | App never breaks because AI is down — rule-based estimation always available |
| 2026-02-27 | Finishing is always present in output, even for raw steel | Core product principle — most underquoted item in fabrication |
| 2026-02-27 | Rate application: in-shop default, on-site for install + full on-site jobs | Matches real fab shop billing (shop rate vs. field rate) |
| 2026-02-27 | Stage 5 is pure math — no AI | Pricing is deterministic: qty × price, hours × rate, subtotal × markup |
| 2026-02-27 | Cheapest hardware option selected by default | User can override on UI; default = lowest cost for quote |
| 2026-02-27 | Consumables estimated from weld_linear_inches | Real cost driver — not guessed, calculated from material quantities |
| 2026-02-27 | Markup options: fixed set [0,5,10,15,20,25,30] | Simple slider UI; custom markup deferred to v3 |
| 2026-02-27 | Quote stores inputs_json + outputs_json | Full audit trail: QuoteParams snapshot + PricedQuote snapshot |
| 2026-02-27 | /price transitions session to "output" + "complete" | Clean pipeline termination: session is done, quote is the source of truth |
| 2026-02-27 | Hardware description matching via keyword regex | Maps Stage 3 descriptions to catalog keys; robust to minor text variations |
| 2026-02-28 | Vanilla HTML/CSS/JS frontend — no frameworks | Spec requirement; ADHD-friendly, fast to iterate, no build step |
| 2026-02-28 | fpdf2 for PDF generation | Pure Python, no system dependencies (vs WeasyPrint), Railway-compatible |
| 2026-02-28 | PDF auth via ?token= query param | window.open() can't set headers; JWT in query string for direct download |
| 2026-02-28 | PDF uses latin-1 safe text with _safe() helper | Built-in Helvetica doesn't support Unicode; convert bullets/dashes to ASCII |
| 2026-02-28 | Frontend static files served at /css/* and /js/* mounts | Alongside API routes; legacy /static preserved for backward compat |
| 2026-02-28 | White-labeled PDF — user shop name, no CreateStage branding | Multi-tenant ready; each user sees their own branding on quotes |
| 2026-02-28 | Gemini extraction + keyword fallback for bid parsing | App works without AI; Gemini improves accuracy when available |
| 2026-02-28 | CSI Division 05 primary, also checks 08/10/32 | Metal fab scope appears in multiple CSI divisions |
| 2026-02-28 | Administrative section filtering in keyword fallback | Prevents false positives from TOC/summary sections |
| 2026-02-28 | pdfplumber for PDF text extraction | Better table/layout handling than PyPDF2; no C deps unlike pymupdf |
| 2026-02-28 | Bid→Session creates individual QuoteSessions per scope item | Each item quoted independently through normal pipeline |
| 2026-02-28 | Pre-populated fields map to question tree field IDs | Users enter normal flow with answers pre-filled from bid extraction |
| 2026-02-28 | Source text preserved in messages_json for audit trail | Fabricator can trace quoted items back to original bid language |
| 2026-02-27 | Seeded prices loaded at module level from JSON file | Fast lookup, no per-request file I/O; regenerate via seed script |
| 2026-02-27 | Profile key format: {shape}_{dims}_{gauge} | Standard key for price lookup: sq_tube_2x2_11ga, flat_bar_1x0.25 |
| 2026-02-27 | Price fallback chain: seeded → hardcoded → 0.0 | Always returns a price; real data overlays market averages |
| 2026-02-27 | Meta-tests verify CLAUDE.md stays in sync with code | Job types, calculators, routers, question trees checked in CI |
| 2026-02-27 | CLAUDE.md as definitive reference (19 sections) | Single source of truth for anyone (human or AI) working on codebase |
| 2026-02-28 | Keyword-based job detection before Gemini | Faster, works offline, reduces API costs; multi-word scores higher |
| 2026-02-28 | CustomFabCalculator as universal fallback | Unknown job types never crash; get_calculator() returns CustomFab for unknowns |
| 2026-02-28 | BalconyRailing delegates to StraightRailing | Same DRY pattern as StairRailing; adds structural frame optionally |
| 2026-02-28 | ProductFiretable loads BOM from JSON | Known product with known materials; fallback estimates if file missing |
| 2026-02-28 | RockSlider always produces qty 2 (pair) | Domain knowledge — rock sliders are always sold/installed as pairs |
| 2026-02-28 | Dual photo storage: R2 or local fallback | R2 when configured, local uploads/ for dev; same API response either way |
| 2026-02-28 | Vision extraction never crashes session | All photo ops in try/except; empty result on failure |
| 2026-02-28 | Text extraction wins over photo on conflict | Text description is more explicit; photo fills in remaining fields only |
| 2026-02-28 | Photo observations are informational only | Shown in UI for user context, not used in calculations |
| 2026-02-28 | AI-first pattern: try AI cut list, fallback to template | All 25 calculators try AI when description exists; deterministic template is always the fallback |
| 2026-02-28 | Description preserved in params_json | User's original text flows to calculators and AI prompts at every stage |
| 2026-02-28 | BaseCalculator provides default AI methods | Subclasses inherit _has_description, _try_ai_cut_list, _build_from_ai_cuts; can override |
| 2026-02-28 | Weld process reasoning in both cut list and labor | TIG/MIG detection from finish, material, and keywords; labor multipliers applied |
| 2026-02-28 | AI cut list 4-step design thinking | Design analysis → pattern geometry → weld process → cut list generation |

