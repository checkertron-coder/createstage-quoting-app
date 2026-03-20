# PHASE 2 SPEC — CreateQuote Fabrication Intelligence Platform
*Authored: March 19, 2026 | Status: APPROVED FOR BUILD*
*Prompt numbering continues from Prompt 34 — Phase 2A begins at Prompt 35*

---

## PHASE 2 VISION

Phase 2 transforms CreateQuote from a smart quoting tool into a **shop-specific AI estimation engine that gets smarter every time a fabricator corrects it.** In Phase 1, every shop using the app got the same generic AI estimates. In Phase 2, each shop configures their actual equipment, labor rates, and capabilities — and the AI uses that context to produce estimates tailored to *that shop's* workflow and cost structure. More importantly, every time a shop owner edits an AI-generated number — hours, materials, markup, anything — that correction is silently captured as a training signal. Over time, the system feeds those corrections back into the AI as context, so the next estimate for that shop is already nudged toward how they actually work. Customer data, job history, QuickBooks exports, and a financial dashboard round out the platform, turning CreateQuote into the operational backbone of a modern fab shop — while quietly building the most valuable dataset in the fabrication industry.

---

## THE MOAT INSIGHT

### What RLHF Is, In Plain Language

RLHF stands for Reinforcement Learning from Human Feedback. It's the technique Anthropic used to train Claude. Here's the simple version: an AI generates an answer, a human corrects it, and the system records the difference. Do that enough times, and you can train the AI to produce better answers automatically.

Burton independently arrived at this same architecture for fabrication quoting. Here's why it's the real asset:

**The problem with generic AI estimates:** Gemini doesn't know that your shop has a CNC plasma table that eliminates manual layout time. It doesn't know you charge $15 more per hour for TIG because your guy's certified. It doesn't know you always add 20% material buffer on stainless because your supplier has long lead times. A generic model guesses at all of this. It guesses *plausibly*, but it's wrong in ways that compound across a full quote.

**What correction data captures:** Every time a shop owner opens an AI-generated quote and changes "8 hours of fit-tack" to "5 hours" — that's not just a correction to that quote. That's a data point. `{job_type: "cantilever_gate", field: "fit_tack_hours", ai_value: 8.0, human_value: 5.0, shop_has_plasma_table: true}`. Captured silently. Costs the user nothing. Worth everything.

**Near-term use (RAG):** Before the dataset is large enough to train a model, correction history can be fed back into the AI as context at quote time. "Here's how this shop has corrected the last 50 estimates. Keep this in mind." No fine-tuning required. Buildable in Phase 2B. Makes accuracy dramatically better almost immediately.

**Long-term use (fine-tuning):** At ~10,000 high-quality correction pairs across dozens of shops, the dataset becomes large enough to fine-tune a small language model specifically for fabrication estimation. A model trained on real corrections from real fabricators is fundamentally different — and better — than a general-purpose model guessing at domain knowledge.

**Why this is defensible:** The data doesn't exist anywhere else. Fabrication job specs live in email threads, legal pads, and people's heads. No competitor can replicate a year of real correction data from real shops. The more shops use CreateQuote, the better it gets. The better it gets, the more shops use it. That's the flywheel.

**The key insight Burton named:** "Actual fabricators correcting Opus per their needed requirements. The data is important." That's it. That's the whole moat.

---

## PHASE 2A: SHOP PROFILE & EQUIPMENT

### What the Shop Owner Configures

The goal is to give the AI enough shop-specific context that estimates stop being generic and start reflecting how *this* shop actually operates. Not a complicated settings page — a focused profile that asks what actually moves the needle on estimates.

**Equipment capabilities:**
- Plasma table: yes/no, bed size (4x4, 4x8, 5x10), max thickness
- Press brake: yes/no, max tonnage, max bend length
- MIG stations: count (1, 2, 3+)
- TIG stations: count
- CNC router: yes/no, bed size
- Spray booth: yes/no
- Powder coat oven: yes/no (in-house or outsourced)
- Forklift: yes/no (affects install complexity assumptions)
- Overhead crane: yes/no, capacity

**Labor rates by process (overrides the global rate):**
- Shop labor rate (base hourly)
- TIG premium (% or $ above base)
- CNC plasma rate (different from manual cutting)
- Field install rate (separate from shop rate)
- Design/engineering rate

**Shop overhead & defaults:**
- Default markup %
- Default waste factor
- Default finishing method
- Standard quote validity days
- Tax rate (for financial exports)
- Shop timezone

**Material sourcing:**
- Primary steel supplier name (for PDF display)
- Secondary supplier name
- Notes on lead times or preferred profiles

### How It Feeds Into AI Context

The shop profile gets injected into the AI system prompt at the start of each estimation call. The injection tells the AI what this shop can actually do, so it doesn't estimate workarounds the shop doesn't need.

**What gets injected (condensed, not raw JSON):**
```
SHOP CONTEXT:
This shop has a CNC plasma table (4x8 bed, up to 1" mild steel). 
Layout and cutting time should reflect plasma table availability — 
manual scribing and layout steps are not needed for flat plate work.
TIG rate: $145/hr. MIG rate: $125/hr. Field install: $155/hr.
No in-house powder coat — outsourced at $4.50/sqft standard, $6.50/sqft specialty.
Default waste factor: 8%.
```

The AI doesn't receive a JSON blob — it receives a human-readable paragraph that teaches it how to estimate *for this shop*. The profile builder constructs this paragraph from the structured fields.

**Correction history context (Phase 2B handoff):**
After Phase 2B is built, an additional injection block is added:
```
SHOP CORRECTION HISTORY (last 30 quotes):
- fit_tack_hours: AI averages 20% high for gate work — this shop is faster
- material_buffer: Shop runs 12% buffer on stainless, not the default 8%
- site_install: Shop adds 2hr mobilization charge not captured in base rate
```

### DB Schema Additions

**New table: `shop_profiles`**
```
shop_profiles
  id                      INTEGER PRIMARY KEY
  user_id                 INTEGER FK → users.id (UNIQUE — one profile per shop)
  
  -- Equipment flags
  has_plasma_table        BOOLEAN DEFAULT false
  plasma_bed_size         VARCHAR  -- "4x4" | "4x8" | "5x10" | "custom"
  plasma_max_thickness_in FLOAT    -- inches, e.g. 0.75
  has_press_brake         BOOLEAN DEFAULT false
  press_brake_tonnage     INTEGER
  press_brake_max_len_in  FLOAT
  mig_station_count       INTEGER DEFAULT 1
  tig_station_count       INTEGER DEFAULT 0
  has_cnc_router          BOOLEAN DEFAULT false
  has_spray_booth         BOOLEAN DEFAULT false
  has_powder_coat_oven    BOOLEAN DEFAULT false
  has_forklift            BOOLEAN DEFAULT false
  has_overhead_crane      BOOLEAN DEFAULT false
  crane_capacity_tons     FLOAT
  
  -- Rate overrides (NULL = use user.rate_inshop)
  rate_tig                FLOAT
  rate_cnc_plasma         FLOAT
  rate_field_install      FLOAT
  rate_design             FLOAT
  
  -- Shop defaults
  waste_factor_default    FLOAT DEFAULT 0.08
  finish_method_default   VARCHAR DEFAULT 'raw'
  outsource_powder_rate   FLOAT   -- per sqft
  outsource_specialty_rate FLOAT
  tax_rate                FLOAT DEFAULT 0.0
  quote_valid_days        INTEGER DEFAULT 30
  timezone                VARCHAR DEFAULT 'America/Chicago'
  
  -- Supplier info (display only)
  primary_supplier        VARCHAR
  secondary_supplier      VARCHAR
  supplier_notes          TEXT
  
  -- Generated context paragraph (cached, rebuilt on save)
  ai_context_paragraph    TEXT
  
  created_at              TIMESTAMP DEFAULT now()
  updated_at              TIMESTAMP DEFAULT now()
```

**Modify existing `users` table:**
No schema change needed — `rate_inshop`, `rate_onsite`, `markup_default` already exist. Phase 2A *supplements* these with the granular shop_profiles table.

### UI Components Needed

1. **Shop Profile Setup Page** — new view in the SPA
   - Equipment checklist (toggle cards, not a form)
   - Rate overrides (only show if equipment is toggled on — e.g., TIG rate field only visible if `has_tig_stations > 0`)
   - Defaults section (waste factor, finish, quote validity)
   - "Save Profile" → POST to new endpoint
   - Preview panel: shows the AI context paragraph that will be injected

2. **Profile Completion Banner** — shown on dashboard if shop_profiles record doesn't exist or is incomplete
   - "Your estimates are generic right now. Set up your shop profile to get shop-specific estimates."
   - CTA → Profile Setup Page

3. **Profile Badge on Quote PDF** — small "Estimated for: [Shop Name] | [Equipment Summary]" line on PDF footer

### Acceptance Criteria

**Done looks like this:**
1. A shop owner opens the app, navigates to Shop Profile, and configures their equipment in under 5 minutes
2. They submit a cantilever gate quote — the labor estimate reflects that they have a plasma table (no manual layout time) and that their TIG rate is $145/hr, not the $125 default
3. The generated PDF footer shows "Profile: Plasma table, 2x MIG, 1x TIG"
4. If they have no shop profile, they see the setup banner on the dashboard
5. The AI context paragraph is visible in the profile UI so the owner can see exactly what the AI is being told about their shop
6. `pytest tests/ -v` passes all 384 existing tests plus new Phase 2A tests

### Claude Code Prompt — Phase 2A (Prompt 35)

---

**PROMPT 35: SHOP PROFILE & EQUIPMENT CONFIGURATION**

**Problem Statement**

Every shop using CreateQuote today receives the same AI estimates — because the AI has no idea what that shop can actually do. A shop with a CNC plasma table doesn't need manual layout time factored in. A shop with a TIG specialist charges differently than one with only MIG. A shop with an in-house powder coat oven has a different finishing cost structure. Right now, the AI ignores all of this and guesses at generic fab shop averages. The result: estimates that are always a little wrong in ways the owner has to manually fix every time. Phase 2A fixes this by letting each shop configure their actual equipment and rates, then injecting that context into every AI estimation call so the model estimates for *this* shop, not a hypothetical average shop.

**Acceptance Criteria**

1. A shop owner can navigate to a Shop Profile page in the SPA and configure their equipment (plasma table, press brake, MIG/TIG count, spray booth, powder coat, forklift, overhead crane), with rate overrides and shop defaults
2. The profile saves to a new `shop_profiles` database table (one record per user)
3. Every AI estimation call in the pipeline (Stage 4 labor, Stage 3 cut list) receives a shop context paragraph derived from the profile — the AI is told what equipment is available, what the rates are, and what the defaults are
4. If a shop has a plasma table, the AI's labor estimate for flat plate cutting jobs reflects reduced layout/cutting time vs. manual methods
5. The Shop Profile page shows the owner exactly what AI context paragraph will be injected (no black-box — they can see what they're telling the AI)
6. If no profile exists, a setup banner appears on the dashboard prompting the owner to complete it
7. All 384 existing tests pass plus new tests covering: profile creation, profile retrieval, context paragraph generation, and injection into the estimation flow

**Constraint Architecture**

*In scope:*
- New DB table: `shop_profiles` (see spec in PHASE-2-SPEC.md)
- New API endpoints under `/api/shop-profile/` (GET, POST, PUT)
- New frontend view: Shop Profile page
- Modify `backend/labor_estimator.py` to accept and inject shop context
- Modify `backend/calculators/ai_cut_list.py` to accept and inject shop context
- New test file: `tests/test_phase2a_shop_profile.py`

*Off limits — do not touch:*
- `backend/weights.py` — do not modify under any circumstances
- `backend/database.py` — do not modify
- `data/seeded_prices.json` — do not modify
- Existing migrations in `alembic/versions/` — add a new migration file, don't edit existing ones
- `backend/calculators/base.py` — modify only the context-passing pattern, do not touch calculator geometry logic
- All existing test files — do not modify, only add new ones

*Architecture rules:*
- Shop profile context is a *paragraph of prose*, not a JSON blob injected into the AI prompt. The system builds the paragraph from structured fields — the AI receives natural language instructions about the shop.
- Teach the AI what the equipment means for estimation — don't hardcode specific hour reductions. "This shop has a plasma table — cutting and layout time should reflect automated cutting rather than manual scribing" is the right instruction, not "subtract 2 hours from layout_setup."
- Python 3.9 — use `Optional[str]` not `str | None`
- The shop context injection must be additive — if no profile exists, estimation runs exactly as before (no regressions)

**Decomposition**

1. **Database layer** — Create the `shop_profiles` table. Write a new Alembic migration. Define the SQLAlchemy model in `models.py`. Understand what fields matter for estimation vs. what's display-only.

2. **Context paragraph builder** — A function that takes a `ShopProfile` record and returns a prose paragraph the AI can read. Understand the fabrication domain: what does having a plasma table actually change about the work? What does a TIG specialist vs. MIG-only shop mean for joint quality and time? The paragraph should teach, not list JSON fields.

3. **API layer** — Three endpoints: GET (retrieve profile), POST (create), PUT (update). Return the generated context paragraph in the response so the frontend can display it.

4. **Injection into estimation pipeline** — The labor estimator and AI cut list generator both build a system prompt. The shop context paragraph must be included in that system prompt, before the job-specific instructions. Design the injection so it's optional — fall back gracefully if no profile exists.

5. **Frontend: Shop Profile page** — Equipment checklist UI using toggle cards (not a dense form). Rate override fields that only appear when the relevant equipment is enabled. A preview panel that shows the AI context paragraph live. Save button that calls the API.

6. **Frontend: Setup banner** — On the main dashboard, check whether the current user has a shop profile. If not, show a prominent (but dismissible) prompt to complete setup.

7. **Tests** — Cover: profile CRUD, context paragraph generation for various equipment combinations, injection into estimation calls (verify the paragraph appears in the prompt), and the banner behavior.

**Evaluation Design**

*Test case 1: Plasma table impact*
- Configure a shop profile with `has_plasma_table = true`, plasma bed 4x8
- Submit a cantilever gate quote (12ft wide, 6ft tall, flat bar frame)
- The labor estimate's `layout_setup` and `cut_prep` hours should be noticeably lower than a quote generated without a shop profile for the same job
- Verify by running the same job with and without the profile and checking the process hour breakdown

*Test case 2: TIG rate override*
- Set `rate_tig = 145.0` in the shop profile
- Submit any job that involves TIG welding (stainless railing, ornamental fence)
- The `full_weld` process in the labor estimate should reflect $145/hr, not the default $125/hr
- PDF should show TIG labor line at $145 rate

*Test case 3: No profile fallback*
- Delete the shop profile for a test user
- Submit a quote — it should complete without error, using default rates
- No 500 errors, no broken estimates

*Test case 4: Context paragraph display*
- Create a shop profile with plasma table + powder coat oven
- Hit GET `/api/shop-profile/` — response includes `ai_context_paragraph` field
- The paragraph mentions both pieces of equipment in human-readable prose

---

## PHASE 2B: CORRECTION TRACKING

### What Gets Logged and When

Every time a shop owner edits any field in a generated quote, that edit is a correction delta. The system captures this silently — no UI prompt, no "submit feedback" button. The user just edits the quote normally. The logging happens in the background.

**Trigger events:**
- Editing an hours value in the labor breakdown (fit_tack: 8hrs → 5hrs)
- Editing a material quantity or line total
- Editing a markup percentage
- Changing a material type or profile in the line items
- Editing the description on a line item
- Deleting a line item the AI generated
- Adding a new line item the AI didn't generate

**What each delta captures:**
- `quote_id` — which quote was edited
- `session_id` — the quote session that produced this quote
- `job_type` — cantilever_gate, straight_railing, etc.
- `field_name` — "labor.fit_tack_hours", "materials[0].quantity", "markup_pct"
- `ai_value` — what the AI produced (stored as string for flexibility)
- `human_value` — what the owner changed it to
- `correction_type` — "hours_edit", "material_quantity", "markup", "line_delete", "line_add"
- `shop_id` — the user_id of the shop making the correction
- `shop_has_plasma` — denormalized equipment flag (makes querying easier)
- `shop_has_tig` — denormalized flag
- `job_size_category` — "small" (<$2k), "medium" ($2k-$10k), "large" (>$10k) — derived from quote total
- `created_at` — timestamp

**What is NOT captured:**
- Customer names, addresses, contact info — no PII in correction deltas
- Quote totals with dollar amounts (only ratios and percentages, not raw dollars)
- Any field the shop owner has marked private

### DB Schema: correction_deltas Table

```
correction_deltas
  id                    INTEGER PRIMARY KEY
  quote_id              INTEGER FK → quotes.id ON DELETE CASCADE
  session_id            VARCHAR  -- nullable, for tracing back to pipeline session
  user_id               INTEGER FK → users.id
  
  -- Job context (for querying and clustering)
  job_type              VARCHAR NOT NULL   -- "cantilever_gate", "straight_railing", etc.
  job_size_category     VARCHAR            -- "small" | "medium" | "large"
  
  -- The correction itself
  field_path            VARCHAR NOT NULL   -- "labor.fit_tack_hours" | "materials.sq_tube_2x2_11ga.quantity"
  correction_type       VARCHAR NOT NULL   -- "hours_edit" | "material_qty" | "markup" | "line_delete" | "line_add" | "material_swap"
  ai_value              TEXT               -- Original AI output (stored as string)
  human_value           TEXT               -- What the human changed it to
  delta_direction       VARCHAR            -- "up" | "down" | "neutral" (for hours/costs)
  delta_magnitude       FLOAT              -- Absolute difference (for numeric fields)
  delta_pct             FLOAT              -- % change (for trend analysis)
  
  -- Denormalized shop context (so we can query without joins)
  shop_has_plasma       BOOLEAN DEFAULT false
  shop_has_tig          BOOLEAN DEFAULT false
  shop_has_press_brake  BOOLEAN DEFAULT false
  
  -- Anonymization
  is_anonymized         BOOLEAN DEFAULT false  -- true once scrubbed for aggregate use
  
  created_at            TIMESTAMP DEFAULT now()
```

### How Correction History Feeds Back to Opus as RAG Context

**The RAG pattern (Phase 2B near-term goal):**

When a new quote is being estimated for a shop, the system queries the last N correction deltas for that shop and constructs a correction summary. This summary is injected into the AI system prompt alongside the shop profile context.

**What the injection looks like:**
```
CORRECTION HISTORY (last 30 quotes for this shop):
For cantilever gate jobs, this shop consistently reduces fit_tack_hours 
by ~25% from AI estimates (average: AI says 7.2hrs, shop corrects to 5.4hrs).
For stair railing jobs, material buffer is typically increased to 15% 
(AI default: 8%).
This shop has added a "mobilization" labor line item on 80% of field install jobs.
Consider these patterns when estimating.
```

The system doesn't inject raw correction records — it generates a *pattern summary* from the deltas. The summary generator runs on the N most recent deltas for that shop, grouped by job_type and field_path, and produces prose that the AI can understand.

**Query logic for pattern summary:**
- Group deltas by `job_type` + `field_path`
- For numeric fields: compute average delta_pct to find directional bias
- For line additions: count frequency of repeated additions (mobilization, travel, setup fee)
- Only include patterns with N ≥ 3 corrections (filter noise)
- Limit summary to top 10 patterns by frequency

### Privacy and Anonymization Approach

**Per-shop data:** Correction deltas are private to each shop. Shop A never sees Shop B's corrections. The RAG context injected into each shop's AI calls is derived only from that shop's own history.

**Aggregate data (long-term fine-tuning):** For training data collection, corrections are:
1. Stripped of user_id, quote_id, session_id before export
2. Job context retained (job_type, job_size_category, equipment flags) — this is the value
3. Dollar amounts replaced with ratios and percentages
4. Exported only in batches (never individual records from single shops)
5. Minimum shop count per batch: 10 (no single shop's data is isolated in a batch)
6. Shop opt-in required before their data is included in aggregate exports (default: off)

**The ethical model:** Each shop owns their correction data. They can delete it. They can opt out of aggregate collection at any time. If they opt in, their corrections become part of the shared training set — and they get priority access to the improved model.

### Near-Term Use (RAG) vs. Long-Term Use (Fine-Tuning)

| | Near-Term (RAG) | Long-Term (Fine-Tuning) |
|---|---|---|
| **When** | Phase 2B launch | ~10k correction pairs |
| **Requires** | ~20+ corrections per shop | Hundreds of shops × many quotes |
| **How** | Pattern summary injected into system prompt | Training dataset for dedicated model |
| **AI model** | Same Gemini/Claude model, better context | New purpose-trained fabrication LLM |
| **Buildable** | Yes, immediately | Yes, but at dataset scale |
| **Impact** | Significant accuracy improvement per shop | Transformative for the industry |

### Acceptance Criteria

**Done looks like this:**
1. A shop owner edits any field on a generated quote — `correction_deltas` table receives a new row with before/after values, no user prompt required
2. After 20+ corrections, the pattern summary generator produces a coherent natural-language summary of that shop's correction tendencies
3. The next quote generated for that shop has the correction summary injected into the AI context
4. Fetching GET `/api/corrections/summary` returns a pattern summary for the current user's shop
5. The corrections table stores no customer PII — names, addresses, emails are absent from all delta records
6. All 384 existing tests plus new Phase 2B tests pass

### Claude Code Prompt — Phase 2B (Prompt 36)

---

**PROMPT 36: CORRECTION TRACKING & RAG CONTEXT LOOP**

**Problem Statement**

Every time a shop owner opens a CreateQuote AI estimate and adjusts numbers — hours up, material quantity down, markup changed, line item deleted — they're correcting the AI. Right now, those corrections disappear. The edited quote is saved, but the information about *what changed and why* is lost. This is training signal that's being thrown away. Phase 2B captures that signal silently, every time, without burdening the user. And near-term, it feeds that signal back into the AI as context on the next quote — so the AI gradually learns this shop's tendencies without any fine-tuning required.

**Acceptance Criteria**

1. Any field edit made to a generated quote triggers a new row in `correction_deltas` — field path, before value, after value, job type, correction type, and shop context flags are all captured
2. Zero user-visible UI for correction logging — it happens silently in the backend when a quote is updated via the API
3. A pattern summary generator reads a shop's correction history and produces a natural-language paragraph suitable for AI context injection — grouping by job_type and field_path, computing directional bias, filtering noise (minimum 3 occurrences)
4. Pattern summary is injected into the AI system prompt for labor estimation and cut list generation — alongside the shop profile context from Phase 2A
5. Admin/debug endpoint `GET /api/corrections/summary` shows the current user's pattern summary (for testing and transparency)
6. No PII stored in correction_deltas — verified by test that checks no customer name, email, or address fields exist in the schema or sample records
7. All existing tests pass plus new Phase 2B test suite

**Constraint Architecture**

*In scope:*
- New DB table: `correction_deltas` (see PHASE-2-SPEC.md for schema)
- New Alembic migration for `correction_deltas`
- Correction capture logic triggered from existing quote update endpoints in `backend/routers/quotes.py`
- Pattern summary generator: new module `backend/correction_engine.py`
- Injection into `backend/labor_estimator.py` and `backend/calculators/ai_cut_list.py`
- New endpoint: `GET /api/corrections/summary` (auth required)
- New test file: `tests/test_phase2b_corrections.py`

*Off limits — do not touch:*
- `backend/weights.py` — do not modify
- `backend/database.py` — do not modify
- `data/seeded_prices.json` — do not modify
- Any existing test file — only add new ones
- The quote update logic itself — add hooks to capture deltas, but do not change what the update does to the quote record
- `backend/auth.py` — do not modify

*Privacy rules:*
- `correction_deltas` table must not contain: customer name, email, phone, address, or any field from the `customers` table
- Dollar amounts stored as ratios/percentages only (delta_pct), not raw dollar values
- user_id is retained (for per-shop RAG) but must never appear in aggregate exports

*Architecture rules:*
- Correction capture is non-blocking — if logging fails, the quote update must still succeed. Wrap capture logic in try/except, log the error, continue.
- Pattern summary is prose, not JSON — the AI context injection must be natural language the AI can interpret, not a data dump
- The pattern summary must teach the AI directional tendencies, not hardcode specific values. "This shop runs 20% shorter on fit_tack for gate work" is correct. "Set fit_tack to 5.2 hours" is wrong.
- Python 3.9 — use `Optional[str]` not `str | None`

**Decomposition**

1. **Capture layer** — Understand when quote fields change. The quote update endpoint already accepts PATCH requests. Add a correction delta writer that runs after a successful quote update: compare the before state (read from DB before update) with the after state, identify which fields changed, and write one correction_delta row per changed field. Understand which field paths matter for estimation quality: labor hours, material quantities, markup percentage, line item deletions/additions.

2. **correction_deltas table** — Create the SQLAlchemy model and Alembic migration. Study the schema in PHASE-2-SPEC.md. Understand the denormalized equipment flags: these are copied from the shop_profile at write time, not joined at query time. This makes aggregate analysis possible without exposing shop identity.

3. **Pattern summary generator** — `backend/correction_engine.py`. The core function: given a user_id, query their recent correction_deltas, group by job_type + field_path, compute the average delta_pct and direction for numeric corrections, identify frequently added line items. Filter out patterns with fewer than 3 occurrences. Return a prose paragraph. This is a data analysis function — study what makes a useful summary for an AI estimator vs. statistical noise.

4. **Injection into pipeline** — The labor estimator and cut list generator already have a context injection point from Phase 2A (shop profile paragraph). The correction pattern summary is the second paragraph in that context block. The injection function should: check if a pattern summary exists for this user, generate it if data is sufficient (N ≥ 3), append it after the shop profile context, pass it through. If no corrections exist, omit this block entirely.

5. **Summary endpoint** — `GET /api/corrections/summary` returns the current user's pattern summary as plain text (or structured JSON with the prose paragraph + metadata about how many corrections informed it). This is for transparency — the owner can see what their history is telling the AI.

6. **Tests** — Cover: correction delta creation on quote edit, fields logged correctly, field paths generated correctly for labor vs. material vs. markup edits, pattern summary generation with sufficient data, pattern summary returns empty/null with insufficient data, no PII in delta records, summary injection appears in AI prompt.

**Evaluation Design**

*Test case 1: Edit logging*
- Generate a quote for a cantilever gate job
- PATCH the quote to change fit_tack_hours from 7.0 to 5.0
- Query `correction_deltas` where quote_id = that quote — expect one row: field_path="labor.fit_tack_hours", ai_value="7.0", human_value="5.0", delta_direction="down", delta_pct≈-28%

*Test case 2: Pattern emergence*
- Make the same type of correction (fit_tack down ~25%) across 5 different gate quotes
- Call the pattern summary generator — expect output mentioning fit_tack_hours trending shorter on gate work
- Pattern should appear in natural language, not raw numbers

*Test case 3: RAG injection*
- Set up a shop with 10 corrections showing consistent material buffer increase on stainless jobs
- Generate a stainless stair railing quote
- Capture the AI system prompt — verify the correction summary paragraph is present and mentions material buffer tendencies

*Test case 4: PII absence*
- Inspect the correction_deltas table schema and all records generated in tests
- Assert: no column named `customer_name`, `email`, `phone`, `address` exists
- Assert: no test record contains customer-identifiable data

---

## PHASE 2C: CUSTOMER & JOB DATA MANAGEMENT

### CSV Upload Flow for Past Jobs and Customers

Most fab shops have years of job history sitting in spreadsheets, QuickBooks exports, or hand-maintained Excel files. Phase 2C lets them upload that history and have it populate the app without manual re-entry.

**Two upload flows:**

**Customer CSV upload:**
- Required columns: name (required), company (optional), email, phone, address
- Fuzzy deduplication: if an import record matches an existing customer by name + company similarity (>80%), prompt the user to merge or keep both
- Result: customer records populated, available for quote auto-fill

**Job history CSV upload:**
- Flexible format: system attempts to map columns from any reasonable spreadsheet format
- Expected columns: date, job_description, customer_name, job_type (optional), total_amount, labor_hours (optional), material_cost (optional)
- Job type inference: if job_type column absent or unparseable, use keyword detection from job_description (reuse Stage 1 detection logic)
- Result: historical quote records created (status=ACCEPTED, source=csv_import), linked to customer records
- These records feed Phase 2D financial dashboard immediately on import

**Upload UI:**
- Drag-and-drop CSV file area
- Column mapping step: show auto-detected column assignments, let user correct them
- Preview table: first 5 rows with mapped values
- Import results: N customers created, M updated, P jobs imported, Q skipped (with reasons)

### Customer Profile Auto-Building from Quote History

Every time a quote is generated and saved for a customer, the customer record is enriched:

- `last_quoted_at` — updated on each quote
- `quote_count` — running total
- `avg_job_value` — rolling average of quote totals
- `preferred_finish` — the finishing method most commonly chosen
- `preferred_markup_pct` — the markup most commonly applied to their quotes
- `primary_job_types` — JSON array of their most common job types (sorted by count)
- `notes` — manual field, never auto-updated

These fields are computed from the `quotes` table and cached on the `customers` record, refreshed each time a new quote is saved for them.

### Repeat Customer UX (Auto-Fill Preferences)

When a returning customer is selected on a new quote:
- The preferred markup is pre-filled (owner can override)
- Their preferred finish is suggested in Stage 4
- Their primary job types are surfaced as quick-start suggestions
- A "history panel" appears: last 3 quotes, dates, amounts, job types

This makes repeat customer quoting faster and more consistent — the shop owner isn't starting from scratch each time.

### Export Formats

**QuickBooks CSV export:**
- Column format: Date, Description, Customer Name, Class, Amount, Tax Code
- One row per line item category (materials, labor, finishing, hardware)
- Subtotals by class match QuickBooks chart of accounts conventions
- Date range filter: select by month, quarter, or year
- Delivered as `createstage_qb_export_YYYY-MM.csv`

**Generic CSV export:**
- All quote fields in a flat format
- One row per quote (not line item)
- Includes: date, quote_number, customer_name, job_type, material_subtotal, labor_subtotal, hardware_subtotal, finishing_subtotal, markup_pct, total
- Delivered as `createstage_quotes_export_YYYY-MM-DD.csv`

**Export endpoints:** `GET /api/export/quickbooks?start=YYYY-MM-DD&end=YYYY-MM-DD` and `GET /api/export/csv?start=&end=`

### Acceptance Criteria

**Done looks like this:**
1. A shop owner uploads a CSV of past customers — records are created, duplicates are flagged for review, not silently duplicated
2. A shop owner uploads a CSV of past jobs — historical quote records are created with correct job types (auto-detected from description when not explicit), linked to customer records
3. When starting a new quote, selecting a returning customer shows their history panel and pre-fills markup and finish preferences
4. GET `/api/export/quickbooks?start=2025-01-01&end=2025-12-31` downloads a valid QuickBooks-importable CSV
5. GET `/api/export/csv` downloads a flat CSV of all quotes in range
6. Customer records accumulate `quote_count`, `avg_job_value`, `preferred_finish` automatically on each new quote save
7. All 384 existing tests plus new Phase 2C tests pass

### Claude Code Prompt — Phase 2C (Prompt 37)

---

**PROMPT 37: CUSTOMER & JOB DATA MANAGEMENT**

**Problem Statement**

Shop owners have years of job history and customer data sitting in spreadsheets, and no clean way to get it into CreateQuote. They also have to manually re-enter the same preferences every time a repeat customer asks for a quote. Phase 2C solves both problems: a CSV import flow that pulls in historical jobs and customers with intelligent column mapping and deduplication, and a customer profile system that auto-builds from quote history so repeat customer quoting is faster and more consistent.

**Acceptance Criteria**

1. A shop owner can upload a CSV file of customers — records are created, and likely duplicates (same name + company) are flagged for review rather than blindly created
2. A shop owner can upload a CSV file of past jobs — historical quote records are created, linked to existing customer records where possible, with job type inferred from description when not explicit in the CSV
3. Returning customers are identified when starting a quote — their history panel shows last 3 jobs, and markup and finish preferences are pre-filled
4. Customer records update automatically (quote_count, avg_job_value, preferred_finish, preferred_markup_pct) each time a new quote is saved for them
5. GET `/api/export/quickbooks` returns a valid CSV formatted for QuickBooks import, filterable by date range
6. GET `/api/export/csv` returns a flat quotes CSV, filterable by date range
7. All existing tests pass plus new Phase 2C test file

**Constraint Architecture**

*In scope:*
- New API endpoints: `/api/import/customers` (POST), `/api/import/jobs` (POST)
- New API endpoints: `/api/export/quickbooks` (GET), `/api/export/csv` (GET)
- Extend `customers` table with profile accumulation fields (Alembic migration)
- New frontend: Import page (CSV upload + column mapping UI)
- Customer history panel in the quote start flow
- New module: `backend/csv_importer.py` (parsing, column mapping, deduplication logic)
- New module: `backend/csv_exporter.py` (QuickBooks format, generic format)
- New test file: `tests/test_phase2c_customers.py`

*Off limits — do not touch:*
- `backend/weights.py`, `backend/database.py` — do not modify
- `data/seeded_prices.json` — do not modify
- Any existing test file — only add
- Stage 1-6 pipeline routers — this phase does not touch the quoting pipeline
- `backend/auth.py` — do not modify

*Architecture rules:*
- CSV parsing is flexible: the system should attempt to auto-detect column mappings from common header names, then present the mapping to the user for confirmation — never silently reject a file because headers don't match exactly
- Deduplication is fuzzy, not exact: same-name + same-company is a likely duplicate, prompt the user to merge or skip rather than auto-merging
- Job type inference for CSV imports reuses `engine.py`'s `detect_job_type()` logic — don't write a new detector
- Historical imports are marked `source=csv_import` in the DB — clearly distinguished from quotes generated by the pipeline
- QuickBooks CSV format: one row per quote, not one row per line item — simplest valid import format for QuickBooks Desktop and Online
- Python 3.9 — use `Optional[str]` not `str | None`

**Decomposition**

1. **CSV importer module** — Understand the challenge of flexible CSV parsing. Real-world spreadsheets have inconsistent headers: "Customer Name", "client", "cust_name" all mean the same thing. Build a column mapping system that attempts fuzzy header matching, presents the detected mapping, and lets the user correct it before committing. Study what fields matter most for each import type (customers vs. jobs) and what to do when optional fields are missing.

2. **Customer table extension** — Add columns for accumulated profile data: `quote_count`, `avg_job_value`, `preferred_finish`, `preferred_markup_pct`, `primary_job_types`, `last_quoted_at`. Write the Alembic migration. Add a customer profile update function that runs after every new quote save — this function reads the customer's full quote history and recomputes the aggregate fields.

3. **Import endpoints** — Two POST endpoints that accept a CSV file upload. Each should: parse the file, run column mapping (auto + user-confirmed), check for duplicates, insert records, and return a result summary (N created, M skipped/flagged, P errors with reasons). Dry-run mode: `?dry_run=true` returns what would happen without committing.

4. **Repeat customer UX** — In the quote start flow, after job type selection, check if the description or a customer selector matches a known customer. If yes, show a history panel: last 3 quotes (date, job type, total), preferred finish, preferred markup. Pre-fill these fields in the quote session. The customer association must be saveable to the resulting Quote record.

5. **Export endpoints** — Two GET endpoints that build CSV responses from the quotes table. QuickBooks format requires specific column names and date formatting — research the QuickBooks CSV import spec. Generic format is simpler: flat denormalized view of each quote. Both accept `start` and `end` query params (ISO date strings). Validate date range — don't allow absurdly large ranges.

6. **Frontend: Import page** — Drag-and-drop file upload, column mapping table (auto-detected column → detected field, with override dropdowns), preview of first 5 rows, import button, results summary. Use the existing `api.js` client pattern.

7. **Tests** — Cover: CSV parsing with various header formats, deduplication flagging, job history import with type inference, customer profile accumulation, export format validation (correct columns), date range filtering, dry-run mode.

**Evaluation Design**

*Test case 1: Customer CSV import*
- Upload a CSV with columns: "Client", "Company", "Email", "Phone" (non-standard headers)
- System should map "Client" → name, "Company" → company, etc.
- After import: customer records created with correct field mapping
- Upload the same file again — existing records flagged as likely duplicates, not silently duplicated

*Test case 2: Job history import with type inference*
- Upload a CSV with: Date, Description, Customer, Amount (no job_type column)
- Description "12ft cantilever gate, aluminum tube frame" → detected as `cantilever_gate`
- Description "powder coated steel table base, 2x2 tube" → detected as `furniture_table`
- Historical quotes created with correct job_type, status=ACCEPTED, source=csv_import

*Test case 3: Profile accumulation*
- Create 3 quotes for the same customer: all use paint finish, all use 15% markup
- Check customer record: preferred_finish="paint", preferred_markup_pct=15, quote_count=3
- Start a 4th quote for that customer — markup field pre-filled to 15%, finish to paint

*Test case 4: QuickBooks export*
- Generate 5 quotes in Q1 2025
- GET `/api/export/quickbooks?start=2025-01-01&end=2025-03-31`
- Download CSV: verify it has Date, Description, Customer Name, Amount columns
- Verify date range filter: no records outside Q1 appear

---

## PHASE 2D: FINANCIAL INTELLIGENCE

### Revenue Dashboard Panels

A clean, lightweight financial view — not accounting software, but the data source *for* accounting software.

**Panel 1: Revenue Summary**
- Total quoted (all quotes in period)
- Total won (status=ACCEPTED)
- Total lost (status=DECLINED)
- Win rate %
- Average job value (won quotes)
- Date range selector: This month / This quarter / This year / Custom

**Panel 2: Revenue by Job Type**
- Bar chart or sorted table: which job types generated the most revenue this period
- Columns: job_type, count, total_revenue, avg_job_value
- Useful for knowing where the business actually lives

**Panel 3: Revenue by Material**
- Material category breakdown: mild steel, stainless, aluminum, etc.
- Shows material cost as % of total revenue (material margin health indicator)

**Panel 4: Labor Efficiency**
- Average estimated hours vs. actual hours (from historical_actuals table)
- Accuracy rate by job type
- Flagged jobs: where estimated hours were >25% off from actuals

**Panel 5: Open Quotes**
- Quotes currently in DRAFT or SENT status
- Total value of open pipeline
- Age of each open quote (days since created)

### Year-End Export Structure

Designed to hand off to an accountant or feed into QuickBooks/tax software. Not a financial product — a clean data hand-off.

**Year-end export columns:**
```
Date | Invoice # | Customer | Job Type | Material Category | 
Material Cost | Labor Hours | Labor Cost | Hardware Cost | 
Finishing Cost | Subtotal | Markup % | Total | Status | Notes
```

**Delivered as:** `createstage_yearend_YYYY.csv`

One row per quote. No line-item explosion. Accountants want summary rows, not BOM detail.

**Tax-ready categorization:**
- Materials → COGS (Cost of Goods Sold)
- Labor → COGS (direct labor)
- Hardware → COGS
- Finishing → COGS (or expense, depending on tax treatment — note in export)
- Markup → Gross Margin
- Each category has a suggested tax treatment note in the column header row

### Tax-Ready Data Structure

The financial export doesn't make tax decisions — it presents data in the categories accountants recognize:

```
Column: "Material Cost [COGS - Materials]"
Column: "Labor Cost [COGS - Direct Labor]"
Column: "Hardware Cost [COGS - Materials]"
Column: "Finishing Cost [COGS - Subcontractor or Materials]"
Column: "Total Revenue [Income]"
```

Each column header includes the suggested accounting category in brackets. The accountant overrides if their tax treatment differs — but they get the structure handed to them.

### Acceptance Criteria

**Done looks like this:**
1. A shop owner opens the Financial Dashboard and sees 5 panels with real data from their quote history
2. Each panel updates when the date range is changed (no page reload)
3. GET `/api/financial/summary?start=YYYY-MM-DD&end=YYYY-MM-DD` returns structured JSON for all 5 panels
4. GET `/api/export/yearend?year=2025` returns a properly formatted CSV with tax-category column headers
5. Revenue totals in the dashboard match what a manual count of quote totals produces (verified in tests)
6. All 384 existing tests plus new Phase 2D tests pass

### Claude Code Prompt — Phase 2D (Prompt 38)

---

**PROMPT 38: FINANCIAL INTELLIGENCE DASHBOARD**

**Problem Statement**

Shop owners don't know which job types make them the most money. They don't know their win rate. They don't know if their material costs are eating their margin. They have quotes in the database, but no way to look across them and understand the business. And at year end, they're manually compiling spreadsheets for their accountant. Phase 2D builds a lightweight financial intelligence layer — five dashboard panels that answer the key business questions, plus a year-end export that hands accountants clean, categorized data without making accounting software decisions for the shop.

**Acceptance Criteria**

1. Financial Dashboard shows five panels: Revenue Summary, Revenue by Job Type, Revenue by Material, Labor Efficiency, and Open Quotes Pipeline — all populated from the quotes table
2. Date range selector (This Month / Quarter / Year / Custom) refreshes all panels without page reload
3. `GET /api/financial/summary?start=YYYY-MM-DD&end=YYYY-MM-DD` returns JSON for all five panels
4. `GET /api/export/yearend?year=2025` returns a CSV where column headers include accounting category annotations in brackets (e.g., "Material Cost [COGS - Materials]")
5. Revenue totals in the API response match a manual SUM of quote totals for the same date range
6. Open Quotes panel shows quotes in DRAFT or SENT status with age in days
7. All existing tests pass plus new Phase 2D test file

**Constraint Architecture**

*In scope:*
- New API endpoints under `/api/financial/` (summary, by-job-type, by-material, labor-efficiency, open-pipeline)
- New API endpoint: `/api/export/yearend` (GET)
- New frontend view: Financial Dashboard (5 panels)
- New module: `backend/financial_engine.py` (query and aggregation logic)
- New test file: `tests/test_phase2d_financial.py`

*Off limits — do not touch:*
- `backend/weights.py`, `backend/database.py` — do not modify
- `data/seeded_prices.json` — do not modify
- Any existing test file — only add
- The quotes table schema — this phase reads data, does not add columns
- The pipeline routers (quote_session, quotes, etc.) — financial views are read-only queries
- `backend/auth.py` — do not modify

*Architecture rules:*
- All financial queries read from the `quotes` table using `outputs_json` for breakdown data (material_subtotal, labor_subtotal, etc. are stored in PricedQuote snapshots)
- No raw SQL — use SQLAlchemy ORM queries
- The financial dashboard is a **read-only view** of existing data — it never modifies quotes or financial records
- Date range validation: enforce maximum 3-year range to prevent performance problems
- Tax category annotations in CSV headers are static strings — don't build a tax rules engine, just annotate the columns
- Currency formatting: always round to 2 decimal places in API responses; CSV uses plain floats (no $ symbols, no commas in numbers)
- Python 3.9 — use `Optional[str]` not `str | None`

**Decomposition**

1. **Financial engine module** — `backend/financial_engine.py`. Understand the data source: quote totals live in the `quotes` table (total, subtotal, selected_markup_pct, job_type, status, created_at). Line-item breakdowns live in `outputs_json` (PricedQuote snapshot). Most dashboard panels can be computed from top-level quote fields without parsing outputs_json — only the material breakdown panel needs to dig into the snapshot. Build query functions for each panel. Think about what queries are expensive and whether they need indexes.

2. **Summary API** — One endpoint `GET /api/financial/summary?start=&end=` that returns all five panel datasets in a single JSON response. Understand what data structure each panel needs: Revenue Summary is aggregates, Revenue by Job Type is grouped counts and sums, Labor Efficiency needs joins to historical_actuals. Design the response shape so the frontend can render each panel with a single data binding.

3. **Year-end export** — `GET /api/export/yearend?year=2025`. Queries all ACCEPTED quotes for the given year. Builds a CSV row per quote with the required columns. The column headers include accounting category annotations — these are static string constants in the code, not computed. Understand the QuickBooks column conventions from Phase 2C (these exports should be compatible).

4. **Frontend: Financial Dashboard** — A new view with five panel components. Each panel is a card with a title, a summary number, and supporting detail (table or list). Date range controls at the top refresh all panels via the summary API. Keep it simple: no charting library unless vanilla canvas or SVG is sufficient — this is a fab shop tool, not a fintech dashboard. Readable data is better than pretty charts.

5. **Open Quotes panel** — Queries quotes with status DRAFT or SENT. Computes `age_days` from `created_at`. Shows customer name, job type, total, and age. A quote older than 30 days should be visually flagged (past standard validity window).

6. **Tests** — Cover: summary endpoint returns correct totals for date range, job type breakdown matches manual count, year-end CSV has correct columns and headers, date range validation (reject >3 years), open quotes panel shows correct statuses, age_days calculation is correct.

**Evaluation Design**

*Test case 1: Revenue totals*
- Insert 10 ACCEPTED quotes into the test DB with known totals (e.g., 5 × $2,000 + 5 × $5,000 = $35,000)
- GET `/api/financial/summary?start=2025-01-01&end=2025-12-31`
- Assert: revenue_won = 35000.0, count_won = 10, avg_job_value = 3500.0

*Test case 2: Job type breakdown*
- Insert 6 quotes: 3 cantilever_gate, 2 straight_railing, 1 furniture_table
- Revenue by Job Type panel: cantilever_gate count=3, straight_railing count=2, furniture_table count=1
- Totals add up to overall total

*Test case 3: Year-end CSV format*
- Generate 12 quotes across 2025 (one per month), all ACCEPTED
- GET `/api/export/yearend?year=2025` — download CSV
- Row count = 12
- Column headers include "[COGS - Materials]", "[COGS - Direct Labor]", "[Income]" annotations
- No $ symbols or commas in numeric fields

*Test case 4: Open pipeline aging*
- Insert a DRAFT quote created 45 days ago
- Open Quotes panel shows this quote with age_days=45
- Visual flag (flagged=true in API response) because >30 days old

---

## DATA ARCHITECTURE

### How All Phase 2 Data Connects

```
users (existing)
  └── shop_profiles (2A — one per user)
  └── quotes (existing — extended)
        └── correction_deltas (2B — one per field edit)
        └── historical_actuals (existing)
  └── quote_sessions (existing)
  └── customers (existing — extended in 2C)
        └── quotes (via customer_id)
  └── bid_analyses (existing)
```

**Data flow at quote time (all phases built):**

```
New Quote Request
  │
  ├── Load shop_profiles → build AI context paragraph (2A)
  ├── Query correction_deltas → build pattern summary (2B)
  ├── Check customer history → pre-fill preferences (2C)
  │
  ▼
AI Estimation (Gemini/Claude)
  System prompt = [Shop Context] + [Correction Pattern] + [Job Params]
  │
  ▼
Quote Generated
  │
  ├── Save to quotes table
  ├── Update customers.quote_count, avg_job_value, preferred_finish (2C)
  │
  ▼
Owner Reviews Quote
  │
  ├── Any field edit → correction_deltas row written (2B)
  │
  ▼
Quote Accepted
  │
  └── Feeds financial dashboard (2D)
```

### Full DB Schema After All Phase 2 Tables

**Existing (Phase 1):** users, auth_tokens, quote_sessions, quotes, quote_line_items, customers, material_prices, process_rates, hardware_items, historical_actuals, bid_analyses

**New in Phase 2:**
```
shop_profiles          (Phase 2A) — equipment config per shop
correction_deltas      (Phase 2B) — every field edit, before/after
```

**Extended in Phase 2:**
```
customers              (Phase 2C) — add: quote_count, avg_job_value, 
                                         preferred_finish, preferred_markup_pct,
                                         primary_job_types, last_quoted_at
```

**No new tables for Phase 2D** — financial dashboard reads from existing `quotes` table, year-end export is a computed view.

**Total tables after Phase 2:** 13 tables

### What Data Is Per-Shop vs. Aggregate

| Data | Per-Shop (Private) | Aggregate (Opt-In) |
|---|---|---|
| shop_profiles | ✓ — private | — |
| correction_deltas | ✓ — per user_id | Anonymized (no user_id, dollar ratios only) |
| customers | ✓ — private | — |
| quotes | ✓ — private | Anonymized job type + material totals only |
| historical_actuals | ✓ — private | Accuracy stats by job_type (opt-in) |
| financial exports | ✓ — private | — |

### Privacy Model

**Tier 1 — Always Private:** shop_profiles, customers, full quote records with dollar amounts, correction_deltas with user_id

**Tier 2 — Aggregate Opt-In:** Anonymized correction deltas (no user_id, no dollar amounts, only ratios and job context flags), accuracy statistics by job type, equipment configuration prevalence

**Anonymization rules for aggregate export:**
1. Strip: user_id, quote_id, session_id, customer_id, shop_name
2. Replace: all dollar amounts with ratios (delta as % of AI estimate)
3. Keep: job_type, job_size_category (small/medium/large), equipment flags, field_path, correction_type, delta_pct, delta_direction
4. Minimum batch: 10 shops contributing before any aggregate is exported
5. No individual record exports — only statistical summaries

---

## BUILD SEQUENCE

### Correct Order

```
Phase 2A → Phase 2B → Phase 2C → Phase 2D
```

This is the only valid order. Each phase has a dependency on the prior one.

### Dependencies

| Phase | Depends On | Why |
|---|---|---|
| 2A (Shop Profile) | Phase 1 complete | Extends User model, feeds AI context |
| 2B (Correction Tracking) | 2A complete | Correction pattern summary uses shop_profiles for equipment flags |
| 2C (Customer Management) | Phase 1 (customers table exists) | Can start independently of 2A/2B but ships after them |
| 2D (Financial Dashboard) | Phase 1 (quotes table), 2C (customer data enriched) | Reads all data; most useful after 2C is populated |

**Parallelism option:** 2C has minimal dependency on 2A/2B. If bandwidth allows, 2C can be developed in parallel with 2B and merged before 2D starts.

### Rough Time Estimates Per Phase

| Phase | Scope | Estimated Build Time |
|---|---|---|
| 2A: Shop Profile | New table, 3 endpoints, 1 new UI page, injection into 2 AI calls | 1–2 sessions |
| 2B: Correction Tracking | New table, capture hooks, pattern generator, injection | 2 sessions |
| 2C: Customer Management | CSV import/export, customer enrichment, repeat customer UX | 2–3 sessions |
| 2D: Financial Dashboard | 5 panels, 2 export endpoints, 1 new UI page | 1–2 sessions |
| **Total** | | **6–9 sessions** |

*Sessions = Claude Code working sessions as used in Phase 1 (Sessions 1–10)*

### Pre-Build Checklist for Each Phase

Before starting any Phase 2 prompt:
- [ ] Run `pytest tests/ -v` — confirm 384 tests still pass
- [ ] Confirm Railway deployment is healthy: `GET /health` returns `{"status": "ok"}`
- [ ] Read CLAUDE.md Section 20 ("What Not To Touch")
- [ ] Read PHASE-2-SPEC.md section for the current phase
- [ ] Confirm Alembic migration is needed and write it in scope

---

## THE LONG GAME

### Path from Correction Deltas to Fine-Tuned LLM

**Stage 1: Data collection (now → ~10k pairs)**

The correction_deltas table is a training data accumulator. Every edit made in every shop is a (prompt, correction) pair:
- Prompt: the AI system prompt that produced the estimate + the job description
- Correction: the field that was changed + the new value

These pairs are the raw material. At this stage, focus is on collection, not training. Let the data accumulate.

**Stage 2: Dataset curation (~5k pairs)**

Not all corrections are equal. An owner who edited a quote because they misread it isn't useful training signal. Curation filters:
- Corrections where the owner saved the quote and sent it to a customer (strong signal)
- Corrections that occur consistently across multiple quotes (pattern signal)
- Corrections where the AI was off by >15% (clear error signal)
- Exclude corrections to markup_pct (too shop-specific, not generalizable)

**Stage 3: RAG validation (~2k curated pairs)**

Before fine-tuning anything, test whether RAG with curated corrections produces measurable accuracy improvement. If 50 RAG-injected correction patterns reduce average delta_pct by 30%, the dataset is working. This validates the training signal quality before spending compute on fine-tuning.

**Stage 4: Fine-tuning a small model (~10k curated pairs)**

Target: fine-tune a 7B or 13B open-source model (Mistral, Llama 3, or similar) on the curated correction dataset. This is not replacing Claude/Gemini — it's building a *fabrication-specific estimation model* that's called when high domain accuracy matters more than general reasoning.

The fine-tuned model handles: labor hour estimation, material quantity estimation, job type classification. General reasoning (customer communication, description parsing) stays with the frontier model.

### When Is the Dataset Large Enough?

**Rough math:**
- 100 shops using CreateQuote regularly
- 10 quotes per shop per month
- 5 corrections per quote (conservative)
- 100 × 10 × 5 = 5,000 correction pairs per month
- **2 months of data = 10,000 pairs**

But raw count isn't the full picture. Quality matters:
- **Diversity** — corrections across all 25 job types, not just gates and railings
- **Consistency** — patterns that appear repeatedly, not one-off edits
- **Domain signal** — corrections that reveal fabrication-specific knowledge

Realistically: **10,000 high-quality pairs** from **50+ distinct shops** across **all major job types** is the threshold for a meaningful fine-tuning run.

### How to Anonymize and Aggregate Shop Data Ethically

**The anonymization chain:**
1. Shop submits correction delta (full record, private to their shop)
2. Quarterly anonymization job: strip identifiers, replace dollar amounts with ratios, bucket job sizes
3. Add to aggregate pool only after: shop has opted in AND pool has ≥10 contributing shops for this job type
4. Training data export: aggregate only — no individual shop's data is isolatable

**Opt-in model:**
- Default: all correction data is private and only used for that shop's RAG context
- Opt-in: shop agrees to contribute anonymized corrections to the shared training pool
- Incentive: opt-in shops get first access to the fine-tuned model when it ships
- Opt-out at any time: removes their contribution from the pool (does not retroactively remove from already-trained models — disclosed in terms)

**What you don't keep:**
- Customer names, addresses, contact info — never in correction deltas to begin with
- Raw dollar amounts — only ratios and percentages
- Shop identity in aggregate exports

### What a Fabrication-Domain LLM Would Actually Be Better At Than Generic Gemini

**1. Material quantity estimation**
Generic models don't know that a 20ft ornamental fence section needs 22ft of material to account for post embedment, cut waste, and end caps. A model trained on real corrections from real fabricators learns these domain rules from the corrections themselves.

**2. Weld process selection**
TIG vs. MIG for a given joint isn't obvious from a description. A fine-tuned model trained on thousands of real job corrections learns which process gets chosen by experienced fabricators for each material + joint type combination.

**3. Labor hour calibration**
The biggest source of error in generic estimates is labor. A fine-tuned model trained on real corrections — "AI said 8hrs, shop corrected to 5hrs, shop has plasma table" — learns to calibrate labor hours to real-world fab shop throughput, not textbook estimates.

**4. Job type classification edge cases**
"Custom steel privacy screen with planters and integrated gate" is ambiguous. A fine-tuned model trained on how fabricators actually categorize their work classifies this correctly more often.

**5. Shop-specific pattern learning**
Eventually, with enough data, the model can be personalized per shop without fine-tuning — prompt engineering with shop-specific correction history becomes so rich that the model effectively learns the shop's style.

**What it WON'T be better at than generic Claude/Gemini:**
- Customer communication and professional writing
- General reasoning and problem-solving
- Handling completely novel job types it hasn't seen
- Multi-step reasoning about unusual designs

The fabrication LLM is a *specialist*, not a generalist. It runs alongside the frontier model, not instead of it.

---

*End of PHASE-2-SPEC.md*
*Next action: Begin Prompt 35 (Phase 2A: Shop Profile & Equipment)*
*Author: Checker | March 19, 2026*
