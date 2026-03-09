# PROMPT 39 — "Let Opus Drive"
*Spec-engineered using Nate B. Jones' 5 Primitives*

---

## 1. PROBLEM STATEMENT

The quoting app's labor estimation is fully deterministic — `labor_calculator.py` uses hardcoded TYPE A/TYPE B categorization and formula math to compute hours. This fights the AI instead of leveraging it. The knowledge base (`FAB_KNOWLEDGE.md`) was designed as a **context feed** (facts, prices, shop prefs), but the labor calculator bypasses it entirely and computes hours from joint counts and weld-inch formulas.

Additionally, 5 persistent bugs have survived P37/P38:
- Finish label defaults to "Paint (in-house)" even when clear coat is specified
- Sheet stock outputs abstract quantities instead of real 4x8/5x10 dimensions
- No seaming detection when sign dimensions exceed stock sheet sizes
- Field extraction picks header text over body text on conflicts
- Electronics/LED questions don't fire in P36's dynamic question system

The core issue: **we're computing what Opus should be reasoning about.**

---

## 2. ACCEPTANCE CRITERIA

### AC-1: Opus Labor Estimation
- [ ] `calculate_labor_hours()` calls Opus (via `call_deep()`) with cut list + fields + FAB_KNOWLEDGE.md context
- [ ] Returns the same 8-key dict: `layout_setup`, `cut_prep`, `fit_tack`, `full_weld`, `grind_clean`, `finish_prep`, `coating_application`, `final_inspection` (plus optional `stock_prep_grind`, `post_weld_cleanup`)
- [ ] Includes `_reasoning` field with Opus's chain-of-thought
- [ ] Falls back to current deterministic calculation if Opus call fails
- [ ] Timeout: 360 seconds (Opus needs thinking time)

### AC-2: Finish Label Fix
- [ ] End table with "clear coat" finish → PDF shows "Clear Coat (in-house)", NOT "Paint (in-house)"
- [ ] `_normalize_finish_type()` default changed from `"paint"` to `"raw"` for unknown values
- [ ] User-answered finish field takes priority over extracted values

### AC-3: Real Sheet Dimensions
- [ ] LED sign quote shows "16ga sheet 4'×8'" or "16ga sheet 5'×10'" — NOT "sheet_16ga" with linear feet
- [ ] Sheet size selected based on job dimensions (use smallest standard sheet that fits)

### AC-4: Seaming Detection
- [ ] When any face dimension > 120" (largest stock sheet width): quote includes "SEAMING REQUIRED" note
- [ ] Seaming labor context passed to Opus for estimation

### AC-5: Electronics Questions
- [ ] LED sign job triggers dynamic questions about: LED module specs, power supply, controller, customer-supplied vs shop-sourced
- [ ] Keywords detected: LED, light, neon, backlit, illuminated, ESP32, Arduino, controller, pixel, RGB, module, power supply, driver, transformer

### AC-6: No Regressions
- [ ] All existing tests pass (mock Opus calls in test environment)
- [ ] 6-stage pipeline flow unchanged
- [ ] Calculator material output format unchanged

---

## 3. CONSTRAINT ARCHITECTURE

### DO NOT MODIFY
- `FAB_KNOWLEDGE.md` — context feed, not code. Read-only reference.
- 6-stage pipeline sequence (Intake → Clarify → Calculate → Estimate → Price → Output)
- Calculator material output format (`material_list` with `items`/`cut_list`)
- PDF layout structure (only fix labels, not layout)
- `gemini_client.py` API (use existing `call_deep()`)

### MUST PRESERVE
- Deterministic labor calculation as fallback (rename to `_fallback_calculate_labor_hours`)
- All 384+ existing tests (update mocks as needed)
- The `LABOR_PROCESSES` list in `labor_estimator.py` (11 processes)

### BOUNDARIES
- Opus receives FAB_KNOWLEDGE.md Section 5 (Build Sequence) and Section 7 (Labor Estimation Rules) as **reference context** — NOT as rules to execute blindly
- Opus prompt must say: "Think like a fabricator. How long would this actually take?"
- Sheet sizes limited to standard stock: 4'×8' (32 sqft), 4'×10' (40 sqft), 5'×10' (50 sqft)

---

## 4. DECOMPOSITION

Execute in this order. Run `pytest` after each step. Commit when green.

### Step 1: Preserve deterministic fallback
**File:** `backend/calculators/labor_calculator.py`
- Rename `calculate_labor_hours` → `_fallback_calculate_labor_hours`
- Create new `calculate_labor_hours` wrapper that will call Opus (Step 2) with fallback to `_fallback`
- Tests should still pass (function signature unchanged)

### Step 2: Build Opus labor prompt + call
**File:** `backend/calculators/labor_calculator.py`
- New function `_opus_estimate_labor(job_type, cut_list, fields)` that:
  1. Reads relevant sections from FAB_KNOWLEDGE.md (Sections 5 + 7)
  2. Builds prompt with: job type, full cut list (profiles, quantities, dimensions), all answered fields, finish type, material type
  3. Prompt instructs Opus to return JSON with 8 hour keys + `_reasoning`
  4. Calls `call_deep(prompt, temperature=0.2, timeout=360, json_mode=True)`
  5. Parses response, validates (no negatives, sanity checks), returns dict
- Update `calculate_labor_hours` wrapper: try Opus first, catch exceptions → fall back to `_fallback_calculate_labor_hours`
- Mock `call_deep` in tests

### Step 3: Fix finish default
**File:** `backend/finishing.py`
- In `_normalize_finish_type()`: change final fallback `return "paint"` → `return "raw"`
- Add explicit checks for more clear coat variants: "clear_coat", "clear-coat", "permalac", "lacquer"

### Step 4: Fix field extraction priority for finish
**File:** `backend/routers/quote_session.py`
- Find where `finish` field gets populated from extraction
- Add priority: user-answered (question tree) > description body > description header/title > default ("raw")

### Step 5: Real sheet dimensions
**File:** `backend/calculators/led_sign_custom.py`
- Replace abstract `sqft / 32.0` sheet calculation with:
  ```python
  STANDARD_SHEETS = [(48, 96, "4'×8'"), (48, 120, "4'×10'"), (60, 120, "5'×10'")]
  ```
- Select smallest sheet that fits the face dimensions
- Output description: "16ga sheet 4'×8' (A36)" with real dimensions
- Check and fix same pattern in `sign_frame.py`, `custom_fab.py` if applicable

### Step 6: Seaming detection
**File:** `backend/calculators/led_sign_custom.py`
- After sheet calculation: if `face_width > 120` or `face_height > 120`, add note: "SEAMING REQUIRED — face dimension exceeds maximum stock sheet size (5'×10')"
- Include seaming in cut list notes so Opus sees it during labor estimation

### Step 7: Electronics keywords for dynamic questions
**File:** Find P36 implementation (likely in `quote_session.py` or a question module)
- Add detection keywords: `["LED", "light", "neon", "backlit", "illuminated", "ESP32", "Arduino", "controller", "pixel", "RGB", "module", "power supply", "driver", "transformer"]`
- When detected (or job_type == "led_sign_custom"), inject electronics follow-up questions:
  - LED module specs (pitch, brand, quantity)?
  - Power supply requirements?
  - Controller/driver details?
  - Customer supplying electronics or shop sourcing?

---

## 5. EVALUATION DESIGN

### Test 1: End Table (Small, Decorative, Clear Coat)
- Input: "20x20x32 inch end table, 1 inch square tube frame, 1x1/8 flat bar pyramid pattern with 1/4 inch spacers, clear coat finish, 3/4 inch glass top"
- Expected: Finish section shows "Clear Coat (in-house)", NOT "Paint"
- Expected: Opus labor total between 8-16 hours (SMALL job benchmark)
- Expected: `_reasoning` field explains the thinking

### Test 2: LED Sign (Large, Aluminum, Sheet Stock)
- Input: "128 inch wide by 48 inch tall illuminated channel letter sign, 6061 aluminum frame, LED modules, brushed finish"
- Expected: Sheet items show real dimensions (e.g., "5'×10'")
- Expected: "SEAMING REQUIRED" note (128" > 120" stock width)
- Expected: Dynamic questions ask about LED specs and power supply

### Test 3: Cantilever Gate (Known Benchmark)
- Input: Same description that produced CS-2026-0053 (~$12K)
- Expected: Opus labor hours produce a quote in the $10K-$14K range
- Expected: Reasonable process breakdown (fit_tack ≥ 3 hours, not 1.5)

### Test 4: Regression — All Existing Tests
- `pytest tests/ -v` — all pass
- No import errors, no broken mocks

### Files Modified Summary
1. `backend/calculators/labor_calculator.py` — Major rewrite (Opus engine + fallback)
2. `backend/finishing.py` — Default "paint" → "raw", expanded clear coat matching
3. `backend/routers/quote_session.py` — Finish field extraction priority + electronics keywords
4. `backend/calculators/led_sign_custom.py` — Real sheet dimensions + seaming detection
5. `backend/pdf_generator.py` — Verify finish label displays correctly (may need no changes after upstream fix)
6. Test files — Mock `call_deep` for Opus labor tests
