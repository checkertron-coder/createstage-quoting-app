# PROMPT 41 — "Calibrate the Machine"

*Dedicated to our boy Nate B. Jones — 5 Spec Engineering Primitives*

This prompt addresses ALL issues found across quotes CS-2026-0059 through CS-2026-0062 (LED sign, end table, fence/gate). P40 fixed the frontend question-skip bug. P41 fixes everything else.

---

## 1. Problem Statement

After P39 ("Let Opus Drive") introduced AI-based labor estimation and P40 fixed the question-skip frontend bug, four test quotes exposed six categories of defects:

**A. Labor hours are wildly inflated** — Opus labor estimation has zero calibration from the shop owner's corrections. A fence/gate that previously quoted at ~$12K total (CS-2026-0053) now has labor ALONE at $12,165. Full weld on a fence/gate went from reasonable (~6-8 hrs) to 32 hours. The old deterministic calculator had Burton's corrections baked in; the new Opus estimator starts blind.

**B. Material type defaults wrong** — A painted alley fence (CS-2026-0062) got aluminum tube (`al_sq_tube_2x2_0.125` at $6/ft) for the frame instead of steel (`sq_tube_2x2_11ga` at ~$1.50/ft). Aluminum was never specified — the extractor/calculator defaulted wrong. Steel posts + aluminum frame = nonsensical.

**C. Finish extraction is inconsistent** — Works on some jobs (end table CS-2026-0061: "Clear Coat" ✅) but fails on others (LED sign CS-2026-0060: says "Raw Steel — no finish" despite description saying "clear coated"). Also says "Raw Steel" on an ALUMINUM job. The word "steel" should never appear on an aluminum quote.

**D. Materials PDF is unusable for ordering** — Column headers wrong ("Sticks" for sheet goods), sheet material displayed as linear feet ("4x20'" sheets don't exist — real sheets are 4'×8', 4'×10', 5'×10'), weights empty on aluminum items, no alloy designation (5052-H32 vs 6061-T6), profile descriptions unreadable by distributors.

**E. Electronics/specialty hardware not sourced** — LED sign quote lists zero electronics (no ESP32, no Mean Well PSU, no LED strips, no waterproof connectors) despite the description specifying exact products with URLs. The hardware sourcer only knows structural hardware.

**F. Adjustable material quantities missing from UI** — The frontend used to allow editing material quantities. This capability was lost.

---

## 2. Acceptance Criteria

### AC-1: Opus labor estimation receives calibration context
The labor estimation prompt (in `labor_calculator.py` `_opus_estimate_labor()`) MUST include a "Shop Owner Calibration Notes" section with these benchmarks:
```
LABOR CALIBRATION (from shop owner testing):
- Fence/Gate (12' cantilever + 28' of fence sections, 128 pickets):
  Fit & Tack: ~6 hrs | Full Weld: ~6-8 hrs | Grind & Clean: ~4 hrs
- LED Sign (138"×28"×6" aluminum box with laser-cut letters):
  Fit & Tack: ~6 hrs | Full Weld: ~6 hrs | Grind & Clean: ~4 hrs | Hardware Install: ~4-6 hrs
- These are REFERENCE POINTS, not hard limits. Scale proportionally for larger/smaller jobs.
- When in doubt, estimate LOWER — the shop owner consistently reports AI overestimates welding time.
- Hardware install for electronics (ESP32, LED strips, wiring, waterproofing): 4-6 hours minimum, NOT 0.4 hours.
```
This is context, not rules. Opus should use these as anchors and reason from there.

### AC-2: Material type defaults to steel unless explicitly specified
In the field extraction and calculator pipeline:
- If the user does NOT specify material (aluminum, stainless, etc.), default to **mild steel**
- Only use aluminum profiles (`al_*`) when the user explicitly says "aluminum" or the job type inherently requires it (e.g., `led_sign_custom` defaults to aluminum per industry standard)
- For `fence_gate`, `railing`, `staircase` job types: default to **steel** unless user specifies otherwise
- NEVER mix aluminum frame with steel posts in the same assembly unless the user explicitly requests it

### AC-3: Finish label never says "steel" on aluminum jobs
- The finish display must use the ACTUAL material name: "Raw Aluminum", "Clear Coat (Aluminum)", "Paint (Aluminum)" — never "Raw Steel" on a job using aluminum profiles
- Finish extraction must catch these terms from descriptions: "clear coat", "clear coated", "clearcoat", "clear-coat", "permalac", "lacquer", "powder coat", "anodize", "anodized", "brushed", "polished"
- When "clear coat" appears ANYWHERE in the description, the extracted finish field should be "clear_coat", not "raw" or "none"

### AC-4: Materials PDF reformatted for real-world ordering
The materials/stock order table (in `pdf_generator.py`) must be updated:

**Column header changes:**
- "Sticks" → "Dimensions" (shows actual stock dimensions: "4'×10' sheet", "20' length", "24' length")
- "Total" → "Total Length" (for linear stock) or "Total Area" (for sheet stock)
- "Weight" → must be CALCULATED, never empty. Use standard densities:
  - Mild steel: 490 lb/ft³
  - Aluminum 6061: 169 lb/ft³
  - Stainless 304: 501 lb/ft³

**Sheet stock display:**
- Sheet materials (anything with "sheet" or "plate" in the profile) must display as sheet count × sheet dimensions, NOT linear feet
- Example: Instead of "al_sheet_0.125 | 75.3' | 4 x 20'" → show "Al Sheet 0.125 (1/8") | 4 sheets | 48"×120" (4'×10') | Remainder: 1 partial sheet"
- Standard sheet sizes to reference: 36"×96", 48"×96" (4'×8'), 48"×120" (4'×10'), 60"×120" (5'×10')

**Profile descriptions must be human-readable:**
- Instead of `al_sq_tube_1x1_0.125` → "6061-T6 Aluminum Square Tube, 1"×1", 0.125" wall"
- Instead of `sq_tube_2x2_11ga` → "Mild Steel Square Tube, 2"×2", 11ga"
- Instead of `flat_bar_1x0.125` → "Mild Steel Flat Bar, 1"×1/8""

### AC-5: Electronics/specialty hardware sourced and priced
When the description mentions electronics components (ESP32, Arduino, LED strips, power supplies, controllers, sensors, etc.):
- The hardware sourcer MUST include them as line items with estimated prices
- If the user provided specific product names or URLs, reference those
- Include at minimum: controller board, power supply, LED strips/modules, waterproof connectors, wire/solder/heat shrink
- Price estimates can be approximate — label as "Est." if not from a specific source
- For the LED sign specifically:
  - ESP32 dev board: ~$8-15
  - Mean Well APV-35-5 (5V 35W): ~$15-25
  - BTF-LIGHTING SK6812 RGBW IP67 strip (5m): ~$25-40
  - Waterproof cable glands (PG7/PG9): ~$8-12 pack
  - Wire, connectors, heat shrink: ~$15-20

### AC-6: Adjustable material quantities restored in frontend
The materials section in the quote UI must allow the user to adjust quantities (number of sticks/sheets, consumable amounts). This was previously working — find where it was removed and restore it. Check `quote-flow.js` and related frontend files for the quantity adjustment controls.

---

## 3. Constraint Architecture

- **DO NOT remove Opus labor estimation** — keep `_opus_estimate_labor()` as primary, `_fallback_calculate_labor_hours` as fallback. Only ADD calibration context to the Opus prompt.
- **DO NOT modify question tree JSON files** — the tree structure is fine, P40 fixed the display
- **DO NOT modify `FAB_KNOWLEDGE.md`** — that's Opus's context feed, not a config file
- **DO NOT add hardcoded labor formulas** — the calibration notes are CONTEXT for Opus, not deterministic rules
- **Material type logic goes in the extraction/calculator pipeline** — not in the AI prompt
- **Sheet sizing logic goes in `pdf_generator.py` and stock calculation** — this is display/math, not AI reasoning
- **Weight calculation is deterministic** — use density × volume, not AI estimation
- **Keep profile keys as-is in the database** — only change the DISPLAY format in PDFs

---

## 4. Decomposition

### Task A: Labor calibration context (AC-1)
**File:** `backend/calculators/labor_calculator.py`
**What:** Add a `LABOR_CALIBRATION_NOTES` string constant with Burton's benchmark corrections. Inject it into the Opus prompt in `_opus_estimate_labor()` as a "Shop Owner Reference Data" section.

### Task B: Material type defaults (AC-2)
**Files:** `backend/question_trees/engine.py` (extraction), `backend/calculators/` (calculator selection)
**What:** When `material` field is not extracted or answered, default to "Mild steel" for structural job types (fence, gate, railing, staircase, furniture). Default to "Aluminum" for signage job types (led_sign_custom, channel_letters). Add a `DEFAULT_MATERIAL_BY_JOB_TYPE` dict.

### Task C: Finish label fix (AC-3)
**Files:** `backend/finishing.py`, `backend/pdf_generator.py`
**What:**
1. In `finishing.py`: Update `_normalize_finish_type()` to catch "clear coat/coated/clearcoat" from description text. Ensure it never returns a label containing "steel" when the job material is aluminum.
2. In `pdf_generator.py`: When rendering the finish section, substitute material-appropriate labels ("Raw Aluminum" not "Raw Steel" when profiles are `al_*`).
3. In the extraction prompt: Explicitly tell the AI to extract finish information including "clear coat" variants.

### Task D: Materials PDF reformat (AC-4)
**File:** `backend/pdf_generator.py`
**What:**
1. Rename column headers: Sticks→Dimensions, update Total label
2. Add sheet-aware display logic: detect `sheet_*` or `plate_*` profiles, render as sheet count × dimensions instead of linear feet
3. Calculate weights using `MATERIAL_DENSITIES` dict with standard values
4. Create a `_format_profile_display(profile_key, material_type)` function that converts internal keys to human-readable descriptions with alloy designations

### Task E: Electronics hardware sourcing (AC-5)
**File:** `backend/calculators/hardware_sourcer.py` (or equivalent)
**What:** Add an electronics detection step: when the description mentions electronics keywords (ESP32, Arduino, LED strip, power supply, controller, sensor, etc.), generate hardware line items for the common components. Use estimated prices. If the user provided URLs or product names, include those as reference.

### Task F: Restore adjustable quantities (AC-6)
**Files:** `frontend/js/quote-flow.js`, related frontend files
**What:** Find where material quantity adjustment was removed (compare git history if needed) and restore the editable quantity inputs in the materials section of the quote output view.

---

## 5. Evaluation Design

### Test Quotes (run ALL three after changes):

**Test 1: LED Sign (same description as CS-2026-0059/0060)**
- [ ] Finish shows "Clear Coat" not "Raw Steel"
- [ ] Electronics appear in hardware (ESP32, PSU, LED strips with prices)
- [ ] Materials show sheet dimensions (4'×10' or 4'×8'), not "4x20'"
- [ ] Weights calculated for all aluminum items
- [ ] Labor: Fit & Tack ~6 hrs, Full Weld ~6 hrs, Hardware Install ~4-6 hrs
- [ ] Profile descriptions human-readable in PDF
- [ ] No "Unrecognized profile" warnings (P40 should have fixed this)

**Test 2: End Table (same description as CS-2026-0061)**
- [ ] Clear coat still works ✅ (regression check)
- [ ] Weights still calculated ✅
- [ ] Material quantities adjustable in UI

**Test 3: Fence/Gate (same description as CS-2026-0062)**
- [ ] Frame material is STEEL (sq_tube_2x2_11ga), NOT aluminum
- [ ] Full Weld: ~6-8 hrs, not 32
- [ ] Fit & Tack: ~6-8 hrs, not 18
- [ ] Total labor in the ~$5-6K range, not $12K
- [ ] Finish shows "Paint" with material-appropriate label
- [ ] Weights calculated for all items

### Automated Tests:
- Add tests to `tests/test_prompt41.py`:
  1. `test_labor_calibration_in_prompt` — verify calibration notes appear in Opus prompt
  2. `test_default_material_steel_for_fence` — fence job defaults to steel
  3. `test_default_material_aluminum_for_sign` — LED sign defaults to aluminum
  4. `test_finish_label_aluminum` — never says "steel" on aluminum job
  5. `test_finish_extraction_clear_coat` — "clear coated" in description → finish = clear_coat
  6. `test_weight_calculation` — verify weight calc for known profiles
  7. `test_sheet_display_format` — sheet profiles show sheet dimensions, not linear feet

### Existing tests:
`pytest tests/` — ALL 858+ existing tests must still pass.

### Commit:
```
git add . && git commit -m "P41: Labor calibration, material defaults, finish fix, materials PDF reformat, electronics sourcing, adjustable quantities" && git push
```
