# PROMPT 42 — "Think Like a Fabricator"

*Nate B. Jones — 5 Spec Engineering Primitives*

P41 nailed labor calibration and materials formatting. P42 fixes the remaining pipeline breaks and teaches the system the difference between knowledge and preference.

---

## 1. Problem Statement

Three categories of defects remain after P41:

**A. Finish pipeline is broken — answers go in, nothing comes out.**
The user answers the finish question (e.g., "1 coat of clear coat") but the quote output still says "Raw Aluminum — No finish applied, $0." The finish answer is being collected by the frontend but is NOT flowing through to the pricing engine and PDF generator. This has persisted across CS-2026-0059 through CS-2026-0063. The end table (CS-2026-0061) DID get finish correct — so the pipeline works for SOME job types but fails for others. Trace the full path: user answer → session params → pricing engine → finish calculation → PDF output. Find where it drops.

**B. Hardware/consumables BOM is untamed — Opus over-lists everything.**
After P41/Claude Code extras, the Opus-driven BOM swung from missing ESP32 to listing 200 blind rivets, 100 screws at $0.12 each, DIN rail, prototype PCBs, piano hinges — over-engineering for NASA when we're building a sign. CS-2026-0064 hardware hit $1,045 because Opus itemized every possible fastener. The BOM needs TIERED guidance:
- **Tier 1 (itemize):** Project-specific purchases you'd actually go BUY for this job — ESP32, LED strips, PSU, specialty connectors, polycarbonate diffuser
- **Tier 2 (lump sum):** Shop stock fasteners/small hardware — screws, nuts, washers, rivets, cable ties, heat shrink. ONE line item: "Fastener & small hardware kit: $XX" — every shop has bins of #8 screws, you're not ordering 100 for one job
- **Tier 3 (don't include):** Over-engineered additions not in the description — DIN rail when standoffs work, piano hinge when screws work, prototype PCBs when you're direct-soldering. Match the complexity the customer described, don't add engineering they didn't ask for.

**C. The system doesn't distinguish between fabrication knowledge and design preferences.**
Opus knows how to miter at 45° for a square frame (knowledge — don't ask). But it GUESSES on tab count per letter (72 tabs when the answer is ~9-18) instead of ASKING (preference — always ask). The question generation needs to surface design preferences where multiple valid approaches exist and the choice affects cost, labor, or appearance.

**D. Section subtotals don't refresh when adjusting quantities.**
When the user adjusts labor hours or material quantities in the UI, the grand total updates correctly but the section subtotals (Labor Subtotal, Material Subtotal, Consumable Subtotal) stay stale. The user has to scroll to the bottom to see the change.

**E. Hardware Install labor still 0.4 hours for electronics.**
The labor calibration notes mention 4-6 hours for electronics install but Opus is still outputting 0.4 hours. The calibration context needs to be more explicit about electronics hardware install vs structural hardware install.

**G. Labor calibration notes are being parroted, not used as reference points.**
The `LABOR_CALIBRATION_NOTES` in `labor_calculator.py` give specific hour counts (Fit & Tack: 6, Full Weld: 6, etc.) and Opus just copies them verbatim for every LED sign quote regardless of actual scope. A 48"×24" sign with 3 letters gets the same 6/6/4 as a 138"×28" sign with 9 letters. The calibration notes need to be rewritten as SCALING REFERENCES, not answers — give Opus a benchmark WITH the job size that produced it, then tell it to reason proportionally.

**F. Aluminum weights still empty.**
P41 was supposed to calculate weights but all aluminum items still show "-" in the Weight column.

---

## 2. Acceptance Criteria

### AC-1: Finish flows from user answer to PDF output
- When a user answers a finish question (clear coat, paint, anodize, powder coat, raw), that answer MUST appear in the quote output
- The FINISHING section must show: method name, material cost (if applicable), labor hours for finish application
- Finish labor must appear as a line item in the labor table (e.g., "Clear Coat: 1.5 hrs")
- Consumables must include finish materials (clear coat spray, primer, paint, etc.)
- Test: Run LED sign quote, answer "1 coat clear coat" → output shows "Clear Coat (in-house)", includes clear coat materials in consumables, includes clear coat labor

### AC-2: Opus-driven hardware & consumables BOM with TIERED output
- REMOVE the keyword-matching electronics catalog approach
- INSTEAD: After the cut list is generated, send a SECOND Opus call that receives the full project description + the generated cut list and asks:
  ```
  Based on this project description and cut list, generate a bill of materials using these tiers:

  TIER 1 — PROJECT-SPECIFIC PURCHASES (itemize each):
  Components you would actually GO BUY for this specific job. Things not already in a typical metal fab shop.
  Examples: ESP32, LED strips, specific power supplies, specialty connectors, polycarbonate sheets, custom brackets.
  Format: description, qty, estimated unit price, supplier suggestion.

  TIER 2 — SHOP STOCK & FASTENERS (ONE lump-sum line):
  Common fasteners, small hardware, and minor consumables that any metal fab shop keeps in bins.
  Screws, nuts, washers, rivets, cable ties, heat shrink, solder, tape — lump these into a single line item
  with a flat dollar estimate. Do NOT itemize 100 screws at $0.12 each.
  Format: "Fastener & small hardware kit — $XX"

  TIER 3 — DO NOT INCLUDE:
  Over-engineered items not described or implied by the customer. Don't add DIN rail when standoffs work.
  Don't add piano hinges when screws work. Don't add prototype PCBs when direct-soldering works.
  Match the complexity the customer described — don't engineer beyond their spec.

  CONSUMABLES (itemize categories, not individual pieces):
  Welding consumables (filler rod type + qty, gas type + volume, tungsten electrodes)
  Grinding/cutting (disc types + qty — group by type, not individual discs)
  Finish materials (clear coat, primer, paint — based on the specified finish)
  Cleaning supplies (acetone/alcohol, rags — one line each)
  ```
- This replaces the static catalog with dynamic AI reasoning
- The existing catalog can remain as a FALLBACK if the Opus call fails

### AC-3: Design preference questions surface automatically
- Update the `suggest_additional_questions` prompt in `engine.py` to explicitly distinguish:
  ```
  KNOWLEDGE vs PREFERENCE:
  - KNOWLEDGE: Standard fabrication practices with one correct approach. Do NOT ask about these. Examples: miter angle for square joints (45°), weld process for aluminum (TIG), deburring after cuts.
  - PREFERENCES: Design choices where multiple valid approaches exist and the choice affects cost, labor, or appearance. ALWAYS ask about these. Examples:
    * Number of tabs/spacers per component and spacing
    * Number of finish coats (clear coat layers, paint coats)
    * Picket spacing on fences
    * Weld finish quality (industrial vs furniture grade)
    * Hardware quality level (budget vs premium)
    * Color choices when multiple options exist
  Ask 1-3 preference questions that would have the biggest impact on the quote accuracy.
  ```

### AC-4: Section subtotals refresh on quantity adjustment
- In `quote-flow.js`: When any editable quantity (labor hours, material quantities, consumable quantities) changes, recalculate and update the corresponding section subtotal element immediately
- The same input change handler that updates the grand total must ALSO update the section subtotal
- Applies to: Labor Subtotal, Material Subtotal, Hardware Subtotal, Consumable Subtotal

### AC-5: Hardware Install calibration for electronics
- Update the labor calibration notes in `labor_calculator.py` to be more explicit:
  ```
  HARDWARE INSTALL CALIBRATION:
  - Structural hardware (bolts, brackets, hinges, latches): 0.5-2 hours typical
  - Electronics hardware (ESP32, LED strips, power supply, wiring, waterproofing, testing): 4-6 hours MINIMUM
  - If the project includes electronics/controllers/LED/wiring, hardware install is ALWAYS 4+ hours, never 0.4
  ```

### AC-7: Labor calibration notes rewritten as scaling references
- REWRITE the `LABOR_CALIBRATION_NOTES` in `labor_calculator.py` from fixed answers to scaling benchmarks:
  ```
  LABOR CALIBRATION — SCALING REFERENCES (do NOT copy these numbers directly):
  These are real-world benchmarks from a specific job. Use them to SCALE your estimate proportionally to the actual job scope.

  BENCHMARK: LED Sign, 138"x28"x6" aluminum box, 9 laser-cut letters, 54 weld joints, electronics install:
    Fit & Tack: 6 hrs | Full Weld: 6 hrs | Grind & Clean: 4 hrs | Hardware Install (electronics): 5 hrs

  BENCHMARK: Fence/Gate, 12' cantilever gate + 28' fence, 128 pickets, 10' tall:
    Fit & Tack: 6 hrs | Full Weld: 6-8 hrs | Grind & Clean: 4 hrs | Hardware Install: 2 hrs

  BENCHMARK: End Table, simple steel frame, 4 legs + top rails + shelf:
    Fit & Tack: 1-2 hrs | Full Weld: 1-2 hrs | Grind & Clean: 1-2 hrs

  HOW TO USE: Count joints, component count, and surface area. A sign half the size with 4 letters has roughly
  half the joints → scale labor down ~40-50%. A fence twice as long → scale up proportionally.
  The shop owner consistently reports AI OVERESTIMATES — when in doubt, estimate LOWER.
  ```

### AC-6: Aluminum weight calculation working
- Verify that the weight calculation code added in P41 is actually being called for aluminum profiles
- Standard aluminum density: 0.098 lb/in³ (169 lb/ft³) for 6061-T6
- Weight = cross-section area × length × density
- If the weight calc function exists but isn't being called, find where it's skipped and fix it

---

## 3. Constraint Architecture

- **DO NOT remove `_opus_estimate_labor()`** — only update the calibration notes (AC-5)
- **DO NOT remove the electronics catalog entirely** — keep it as fallback, but make Opus-driven tiered BOM the primary path (AC-2)
- **BOM tiering is critical** — Tier 1 itemized, Tier 2 lump sum, Tier 3 excluded. Do NOT let Opus itemize common fasteners individually.
- **DO NOT modify question tree JSON files** — preference questions come from `suggest_additional_questions`, not the static tree
- **The finish pipeline fix (AC-1) is likely a data flow bug** — trace the exact path, don't rewrite the pipeline. The end table (CS-2026-0061) proved the pipeline CAN work.
- **Opus BOM call (AC-2) should use `call_deep`** (same model as labor estimation) with a reasonable timeout (60s)
- **Keep all changes backward-compatible** — existing tests must pass

---

## 4. Decomposition

### Task A: Trace and fix finish pipeline (AC-1) — CRITICAL, DO THIS FIRST
1. Add logging at every step: user answer received → stored in session params → passed to pricing engine → passed to finish calculator → output in PDF
2. Run the LED sign quote flow manually (or in a test) and check logs to find where the finish field drops
3. Compare with the end table flow (which works) to identify the difference
4. Fix the break point — likely a missing field mapping or a conditional that skips certain job types

### Task B: Opus-driven BOM (AC-2)
**Files:** `backend/hardware_sourcer.py`, `backend/pricing_engine.py`
1. Add a new function `_opus_estimate_hardware_and_consumables(description, cut_list, material_type)` that calls Opus with the project description + cut list
2. Parse Opus's response into hardware items and consumable items
3. Wire it into the pricing pipeline AFTER cut list generation
4. Keep the existing catalog as fallback if the Opus call fails or times out

### Task C: Preference questions (AC-3)
**File:** `backend/question_trees/engine.py`
Update the `suggest_additional_questions` prompt to include the knowledge vs preference distinction and examples.

### Task D: Subtotal refresh (AC-4)
**File:** `frontend/js/quote-flow.js`
Find the input change handler that updates the grand total. Add section subtotal recalculation to the same handler.

### Task E: Hardware Install calibration + labor scaling rewrite (AC-5, AC-7)
**File:** `backend/calculators/labor_calculator.py`
1. REWRITE `LABOR_CALIBRATION_NOTES` entirely — replace fixed numbers with scaling benchmarks per AC-7
2. Add explicit electronics vs structural hardware distinction per AC-5
3. Include the "HOW TO USE" scaling guidance so Opus reasons proportionally

### Task F: Aluminum weight fix (AC-6)
**Files:** `backend/pdf_generator.py` or wherever weight calculation lives
Verify the weight calc function runs for `al_*` profiles. If it exists but isn't called, fix the call site.

---

## 5. Evaluation Design

### Test Quotes (run ALL after changes):

**Test 1: LED Sign (same description as CS-2026-0063)**
Answer "1 coat clear coat" to finish question, "aluminum" to material question.
- [ ] Finish section shows "Clear Coat" with materials cost and labor hours
- [ ] ESP32 appears in hardware with price
- [ ] ALL electronics listed (ESP32, PSU, LED strips, cable glands, wire, solder, heat shrink)
- [ ] Consumables include solder, flux, silicone sealant, masking tape, acetone
- [ ] Hardware Install: 4+ hours
- [ ] Aluminum weights calculated (not "-")
- [ ] Tab count question was ASKED (not assumed)
- [ ] Section subtotals update when adjusting quantities

**Test 2: Fence/Gate (same description as CS-2026-0062)**
Answer "steel" to material, "paint" to finish.
- [ ] Finish section shows "Paint" with primer + paint materials and labor
- [ ] All profiles are steel (no `al_*`)
- [ ] Consumables include tape, plastic sheeting, primer, paint, thinner
- [ ] Picket spacing question was asked

**Test 3: End Table (same description as CS-2026-0061)**
- [ ] Clear coat still works (regression check)
- [ ] Subtotals refresh when adjusting hours

### Automated Tests:
Add to `tests/test_prompt42.py`:
1. `test_finish_flows_to_output` — mock a session with finish="clear_coat", verify it appears in pricing output
2. `test_opus_bom_includes_electronics` — description with ESP32 → hardware includes controller board
3. `test_preference_questions_surface` — description with "letter tabs" → question about tab count appears
4. `test_subtotal_refresh` — (frontend test, may need manual verification)
5. `test_hardware_install_electronics_minimum` — electronics project → hardware install ≥ 4 hours
6. `test_aluminum_weight_calculated` — aluminum profile → weight > 0

### Existing tests:
`pytest tests/` — ALL existing tests must pass.

### Commit:
```
git add . && git commit -m "P42: Think Like a Fabricator — finish pipeline, Opus BOM, preference questions, subtotal refresh" && git push
```
