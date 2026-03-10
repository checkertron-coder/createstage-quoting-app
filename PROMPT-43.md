# PROMPT 43 — "Fix the Foundation"

*Nate B. Jones — 5 Spec Engineering Primitives*

P42 added powerful features. P43 fixes what's broken BEFORE adding anything new. Three bugs, one prompt. No new features — just make the existing ones work correctly.

---

## 1. Problem Statement

Three bugs have persisted across multiple prompts (CS-2026-0059 through CS-2026-0064). They keep getting bundled with new features and never get the focused attention needed to actually fix them. This prompt does NOTHING but fix these three issues.

**A. Finish pipeline is broken — user answers go in, nothing comes out.**
The user answers the finish question (e.g., "1 coat of clear coat") but the FINISHING section in the quote output says "Raw Aluminum — No finish applied — $0." This has persisted across SIX consecutive quotes. Here's the smoking gun:
- ✅ The fab sequence generator HAS the finish data — Step 42 says "Apply Clear Coat to All Exterior Surfaces"
- ✅ The consumables estimator HAS the finish data — lists clear coat spray ($28.50), primer ($36), paint ($51)
- ❌ The FINISHING section does NOT have the finish data — shows "Raw Aluminum — $0"
- ❌ The labor table does NOT have finish labor — no clear coat application hours
- ✅ The end table (CS-2026-0061) DID get finish correct — so the pipeline WORKS for some job types

The finish answer reaches two downstream consumers but not the third. This is a data flow bug at a specific handoff point.

**B. Section subtotals don't update when adjusting quantities in the UI.**
When the user changes labor hours or material quantities in the adjustable fields, the GRAND TOTAL at the bottom updates correctly, but the section subtotals (Labor Subtotal, Material Subtotal, Hardware Subtotal, Consumable Subtotal) stay stale. The user has to scroll all the way to the bottom to see their change reflected. This matters when nudging a price — you need to see the subtotal react immediately next to the line items you're editing.

**C. Labor calibration notes are being copied verbatim instead of used as scaling references.**
The `LABOR_CALIBRATION_NOTES` in `labor_calculator.py` give specific hour counts (Fit & Tack: 6, Full Weld: 6, Grind & Clean: 4) and Opus copies them word-for-word for every LED sign quote regardless of actual scope. A 48"×24" sign with 3 letters gets the same 6/6/4 as a 138"×28" sign with 9 letters. Also, Hardware Install is still 0.4 hrs on electronics projects — should be 4-6 hours minimum.

---

## 2. Acceptance Criteria

### AC-1: Finish answer flows from user input to FINISHING section in PDF output
- When a user answers a finish question (clear coat, paint, anodize, powder coat, raw), that EXACT answer must appear in the FINISHING section of the quote
- The FINISHING section must show: method name, material cost (if applicable), labor hours for application
- Finish labor must appear as a line item in the LABOR table (e.g., "Clear Coat Application: 1.5 hrs")
- If finish consumables are already in the consumables list, that's correct — keep them there too
- **Verification test:** Run the LED sign quote, answer "1 coat clear coat" to the finish question → FINISHING section MUST show "Clear Coat (in-house)" with a non-zero cost. If it shows "Raw Aluminum" or "No finish applied," the fix failed.

### AC-2: Section subtotals refresh immediately on quantity adjustment
- In `quote-flow.js`: when ANY editable input changes (labor hours, material quantities, hardware quantities, consumable quantities), recalculate and update the corresponding SECTION subtotal element immediately
- The same `input`/`change` event handler that recalculates the grand total must ALSO recalculate: Labor Subtotal, Material Subtotal, Hardware Subtotal, Consumable Subtotal
- Each section subtotal element must be targetable (has an id or class that JS can select)
- Verify: change a labor hour value → Labor Subtotal updates immediately without scrolling

### AC-3: Labor calibration notes rewritten as scaling references
REPLACE the entire `LABOR_CALIBRATION_NOTES` string in `labor_calculator.py` with:

```
LABOR CALIBRATION — SCALING REFERENCES (do NOT copy these numbers — SCALE them):

These are real-world benchmarks from specific jobs tested by the shop owner.
Use them to SCALE your estimate proportionally to the actual job scope.
Count the weld joints, component count, and surface area in the current job's cut list,
then scale hours up or down relative to the closest benchmark.

BENCHMARK A — LED Sign, 138"x28"x6" aluminum box, 9 laser-cut letters, ~54 weld joints:
  Fit & Tack: 6 hrs | Full Weld: 6 hrs | Grind & Clean: 4 hrs | Hardware Install (electronics): 5 hrs
  Total: ~21 shop hours

BENCHMARK B — Fence/Gate, 12' cantilever sliding gate + 28' fence, 128 pickets, 10' tall:
  Fit & Tack: 6 hrs | Full Weld: 6-8 hrs | Grind & Clean: 4 hrs | Hardware Install: 2 hrs
  Total: ~20 shop hours

BENCHMARK C — End Table, simple steel frame, 4 legs + top rails + shelf, ~16 weld joints:
  Fit & Tack: 1.5 hrs | Full Weld: 1.5 hrs | Grind & Clean: 1 hr
  Total: ~4 shop hours

HOW TO SCALE:
1. Count weld joints in the current cut list
2. A job with half the joints of a benchmark → roughly 50-60% of benchmark hours
3. A job with double the joints → roughly 170-180% (setup is fixed, repetitive work scales linearly)
4. Electronics hardware install (ESP32, LED strips, power supply, wiring, waterproofing, testing): ALWAYS 4-6 hours minimum
5. Structural hardware install (bolts, brackets, hinges, latches): 0.5-2 hours
6. The shop owner consistently reports AI OVERESTIMATES — when in doubt, estimate LOWER
7. NEVER copy benchmark hours directly — always count joints and scale
```

---

## 3. Constraint Architecture

- **This prompt adds ZERO new features** — fix only, no new capabilities
- **DO NOT modify question tree JSON files**
- **DO NOT modify `FAB_KNOWLEDGE.md`**
- **DO NOT remove `_opus_estimate_labor()`** — only rewrite the calibration notes string
- **DO NOT touch the BOM/hardware sourcer** — that's P44's job
- **The finish fix is a DATA FLOW bug** — trace it methodically. Do NOT rewrite the finish system. Find the one place where the data drops and connect it.
- **Compare the end table path (works) vs LED sign path (broken)** — the difference between these two code paths IS the bug
- **All 893+ existing tests must pass**

---

## 4. Decomposition

### Task A: Trace and fix finish pipeline (AC-1) — DO THIS FIRST, SPEND THE MOST TIME HERE
This is the CRITICAL fix. Methodical approach:

1. **Find where the fab sequence gets finish info.** Search for where Step 42 ("Apply Clear Coat") text is generated. What variable holds the finish type? Where does it come from?

2. **Find where the consumables estimator gets finish info.** Search for where "Clear Coat Spray" consumable is added. What variable/field triggers it?

3. **Find where the FINISHING section gets finish info.** This is in `backend/finishing.py` and/or `backend/pricing_engine.py`. What variable does it read? Where does that variable come from?

4. **Compare #1 and #2 (which work) with #3 (which doesn't).** The difference is the bug. Maybe the fab sequence reads from `session.description` while the pricing engine reads from `session.fields.finish_type` and that field is never set. Maybe it's a different key name. Maybe it's a conditional that skips certain job types.

5. **Compare the end table code path (CS-2026-0061, finish works) with the LED sign code path (CS-2026-0064, finish broken).** What's different? Different job type? Different calculator? Different field mapping?

6. **Fix the break point.** Should be a small change — connecting the field that has the data to the function that needs it.

7. **Add a test** that creates a session with finish="clear_coat", runs it through pricing, and verifies the FINISHING section output is non-zero.

### Task B: Subtotal refresh (AC-2)
**File:** `frontend/js/quote-flow.js`

1. Find the existing `input` or `change` event handler that updates the grand total when quantities are adjusted
2. In that SAME handler, also recalculate each section subtotal:
   - Sum all labor line item costs → update Labor Subtotal element
   - Sum all material line item costs → update Material Subtotal element
   - Sum all hardware line item costs → update Hardware Subtotal element
   - Sum all consumable line item costs → update Consumable Subtotal element
3. If the subtotal elements don't have selectable IDs, add them (e.g., `id="labor-subtotal"`, `id="material-subtotal"`)

### Task C: Labor calibration rewrite (AC-3)
**File:** `backend/calculators/labor_calculator.py`

1. Find the `LABOR_CALIBRATION_NOTES` string constant
2. Replace it entirely with the scaling reference version from AC-3
3. Do NOT change anything else in the labor calculator — same function signature, same Opus call, just different context text

---

## 5. Evaluation Design

### Test Quotes (run ALL three after changes):

**Test 1: LED Sign (same description as CS-2026-0064)**
Answer "1 coat clear coat" to finish question, "aluminum" to material question.
- [ ] FINISHING section shows "Clear Coat" with non-zero cost — NOT "Raw Aluminum"
- [ ] Labor table includes a finish application line item
- [ ] Section subtotals update when adjusting quantities
- [ ] Labor hours are NOT identical to previous quote (should be scaled based on joint count)
- [ ] Hardware Install ≥ 4 hours for electronics

**Test 2: Fence/Gate (same description as CS-2026-0062)**
Answer "paint" to finish question.
- [ ] FINISHING section shows "Paint" with labor and material cost
- [ ] Labor scales proportionally (not copy of benchmark)

**Test 3: End Table (same description as CS-2026-0061)**
- [ ] Clear coat STILL works (regression — this was the one that worked before)

### Automated Tests (`tests/test_prompt43.py`):
1. `test_finish_clear_coat_flows_to_output` — session with finish="clear_coat" → FINISHING section shows clear coat
2. `test_finish_paint_flows_to_output` — session with finish="paint" → FINISHING section shows paint
3. `test_finish_raw_is_explicit` — finish="raw" → FINISHING shows "Raw" (intentional, not default)
4. `test_labor_scales_with_joint_count` — 20 joints vs 50 joints → different labor hours
5. `test_hardware_install_electronics_minimum` — electronics project → hardware install ≥ 4 hrs
6. `test_labor_not_exact_benchmark_copy` — labor hours for a different-sized sign ≠ exact benchmark numbers

### Existing tests:
`pytest tests/` — ALL must pass.

### Commit:
```
git add . && git commit -m "P43: Fix the Foundation — finish pipeline, subtotal refresh, labor scaling" && git push
```
