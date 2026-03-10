# PROMPT 43 — "No Orphans, No Assumptions"

*Nate B. Jones — 5 Spec Engineering Primitives*

P42 delivered the Opus-driven BOM, electronics sourcing, and consumables depth. P43 tames the beast — cuts the fat, asks the right questions, and enforces consistency between what we list and what we build.

---

## 1. Problem Statement

CS-2026-0064 (P42 output) revealed five systemic issues:

**A. BOM and fabrication sequence are disconnected.**
The quote lists 200 blind rivets, rivet drill bits, DIN rail, piano hinges, prototype PCBs — none of which appear in the 44-step fabrication sequence. Meanwhile, the fab sequence references "Apply Clear Coat" (Step 42) but the FINISHING section says "Raw Aluminum — $0." If an item isn't used in a fab step, it shouldn't be in the BOM. If a fab step uses something, it must be in the BOM. These are two views of the SAME build.

**B. BOM is over-engineered — Opus lists everything it can think of, not what the job needs.**
Hardware hit $1,045 because Opus itemized 100 screws at $0.12, 200 rivets at $0.06, 80 flat washers at $0.07. It listed 3 Mean Well power supplies (one generic + 2 specific) and triple-counted wire (kit + red spool + black spool + green spool). A waterproof welded sign box doesn't need rivets. The BOM needs TIERED output and deduplication.

**C. The system makes design decisions without asking.**
CS-2026-0064 used two different sheet gauges (0.080" face, 0.063" back) without asking. It assumed internal rect tube framing without asking if the 6" box depth provides sufficient rigidity. It generated 54 spacer tabs when the answer is 9-18 (1-2 per letter). These are all PREFERENCES — multiple valid approaches exist, and the choice affects cost and fabrication. The system should ASK, not decide.

**D. Finish pipeline is STILL broken.**
The user answered "1 coat clear coat" to the finish question. The fab sequence includes Step 42: "Apply Clear Coat to All Exterior Surfaces — ~90 min." The consumables include clear coat spray ($28.50), primer ($36), and paint ($51). But the FINISHING section shows "Raw Aluminum — No finish applied — $0." The finish answer reaches the fab sequence generator and consumables estimator but NOT the pricing engine's finish calculator. This has persisted across CS-2026-0059 through CS-2026-0064.

**E. Labor calibration notes are parroted, not used as scaling references.**
Every LED sign quote gets exactly Fit & Tack: 6 hrs, Full Weld: 6 hrs, Grind & Clean: 4 hrs — regardless of size. Those numbers came from a specific 138"×28" sign with 9 letters. A 48"×24" sign with 3 letters should get proportionally less. Also, Hardware Install is still 0.4 hrs for a project with ESP32, LED strips, power supply, and waterproofing — should be 4-6 hours.

**F. No "Shop Stock" distinction for bulk inventory items.**
Heat shrink comes in kits. Wire comes in spools. Sandpaper comes in 50-packs. Nitrile gloves come in boxes of 100. You don't buy these FOR one job — you STOCK them. The quote should distinguish project-specific purchases from shop inventory, allocating only a portion to the job cost.

---

## 2. Acceptance Criteria

### AC-1: BOM ↔ Fab sequence mirror rule
- After generating the BOM and fabrication sequence, run a VALIDATION pass (in code, not in the AI prompt):
  - Scan each hardware/consumable item — if NO fab step text references that item or its category, FLAG it for removal
  - Scan each fab step — if it references a material/tool/component not in the BOM, FLAG it for addition
  - Log warnings for mismatches but auto-remove obvious orphans (rivets with no rivet step, drill bits for unused fasteners)
- The validation pass runs AFTER both BOM and fab sequence are generated, BEFORE PDF output

### AC-2: Tiered BOM output
The Opus BOM prompt must produce THREE tiers:

**Tier 1 — Project-Specific Purchases (itemize each):**
Components you would actually GO BUY for this specific job. Things not in a typical metal fab shop.
Examples: ESP32, LED strips, specific power supplies, specialty connectors, polycarbonate sheets, laser cutting services.
Format: description, qty, estimated unit price, total.

**Tier 2 — Shop Stock (list with partial allocation):**
Bulk items that go into shop inventory. Wire spools, heat shrink kits, sandpaper packs, solder rolls, gloves, rags.
List the full purchase price AND the percentage allocated to this job.
Format: "Heat shrink tubing assortment kit — $12.00 (shop stock, 10% allocated = $1.20)"
Only the allocated amount adds to the quote total.

**Tier 3 — Do Not Include:**
Over-engineered items not described or implied by the customer. Items that don't match the fastening method required by the job (no rivets on welded assemblies, no screws on waterproof seams). Items with no corresponding fab step.

**Deduplication rule:** If the same component appears in both the old P41 catalog output AND the Opus BOM, keep ONE entry only. No duplicate power supplies, no duplicate wire listings.

### AC-3: Design preferences are ASKED, not assumed
Update `suggest_additional_questions` in `engine.py`:

```
PREFERENCES — ALWAYS ASK (do not assume):
* Sheet gauge/thickness — NEVER use different gauges for different panels without asking.
  Offer common options: 0.063" (1/16"), 0.080" (5/64"), 0.125" (1/8") for aluminum;
  11ga, 14ga, 16ga for steel.
* Number of tabs/spacers per letter/component AND spacing between them
* Internal framing — does the assembly need internal stiffeners, or does the box/enclosure
  geometry provide sufficient rigidity on its own?
* Fastening method for non-obvious joints (weld vs mechanical vs adhesive)
* Number of finish coats
* Picket/baluster spacing on fences
* Weld finish quality (production/industrial vs furniture grade)

KNOWLEDGE — NEVER ASK (just do it):
* Miter angle for square frames (45°)
* Weld process by material (TIG for aluminum, MIG for steel in shop)
* Deburring after cuts
* Waterproof assemblies = welded seams, not riveted/screwed
```

### AC-4: Finish pipeline fix — TRACE AND FIX THE BREAK
- The finish answer reaches: ✅ fab sequence generator (Step 42: "Apply Clear Coat"), ✅ consumables estimator (clear coat spray $28.50)
- The finish answer does NOT reach: ❌ FINISHING section (shows "Raw Aluminum — $0"), ❌ labor table (no finish labor line)
- TRACE the data flow:
  1. Where does the fab sequence generator get the finish info? (What variable/field?)
  2. Where does the consumables estimator get the finish info? (What variable/field?)
  3. Where does the FINISHING section / pricing engine get the finish info? (What variable/field?)
  4. Find the DIFFERENCE — why do #1 and #2 have the data but #3 doesn't?
- The end table (CS-2026-0061) finish worked correctly — compare that code path to the LED sign code path

### AC-5: Labor calibration rewritten as scaling references
REWRITE `LABOR_CALIBRATION_NOTES` in `labor_calculator.py`:

```
LABOR CALIBRATION — SCALING REFERENCES (do NOT copy these numbers — SCALE them):

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
1. Count weld joints in YOUR cut list — scale proportionally to the benchmark
2. A sign half the size with 4 letters ≈ half the joints → ~60% of benchmark hours
3. A fence twice as long → ~180% of benchmark hours (setup is fixed, repetitive work scales linearly)
4. Electronics hardware install is ALWAYS 4-6 hours when ESP32/LED/wiring/waterproofing involved
5. Structural hardware install (bolts, brackets, hinges): 0.5-2 hours
6. The shop owner consistently reports AI OVERESTIMATES — when in doubt, go LOWER

NEVER copy benchmark hours directly. Always count joints and scale.
```

### AC-6: Section subtotals refresh on quantity adjustment
- In `quote-flow.js`: When any editable quantity changes, recalculate the corresponding SECTION subtotal immediately
- The same event handler that updates the grand total must also update: Labor Subtotal, Material Subtotal, Hardware Subtotal, Consumable Subtotal
- User should see the subtotal change without scrolling to the bottom

### AC-7: Aluminum weight calculation working
- Sheet stock weights must be calculated (currently showing "-" for sheets, only tube/bar have weights)
- Aluminum density: 0.098 lb/in³ (169 lb/ft³) for 6061-T6
- Sheet weight = length × width × thickness × density
- Tube/bar weight = cross-section area × length × density (already working for some profiles — verify all)

---

## 3. Constraint Architecture

- **DO NOT remove `_opus_estimate_labor()`** — only rewrite the calibration notes
- **DO NOT modify question tree JSON files** — preference questions come from `suggest_additional_questions`
- **DO NOT modify `FAB_KNOWLEDGE.md`**
- **The finish pipeline fix is a DATA FLOW bug** — trace it, don't rewrite the pipeline
- **BOM validation pass should be deterministic Python code**, not another AI call
- **Keep the P41 electronics catalog as FALLBACK** — Opus BOM is primary, catalog catches failures
- **All 893+ existing tests must pass**

---

## 4. Decomposition

### Task A: Finish pipeline trace and fix (AC-4) — DO THIS FIRST
1. Add debug logging at EVERY handoff point in the finish data flow
2. Compare the end table path (works) vs LED sign path (broken)
3. Fix the break — likely a missing field in the session params → pricing engine handoff

### Task B: BOM tiering + deduplication (AC-2)
**Files:** `backend/hardware_sourcer.py`, `backend/pricing_engine.py`, `backend/pdf_generator.py`
1. Update the Opus BOM prompt with tiered output instructions
2. Parse Opus response into Tier 1 (itemized) and Tier 2 (shop stock with allocation)
3. Add deduplication pass — if same component appears twice, merge quantities and keep one line
4. Update PDF generator to show separate "Shop Stock" section

### Task C: BOM ↔ Fab sequence validation (AC-1)
**Files:** `backend/pricing_engine.py` or new `backend/bom_validator.py`
1. After BOM and fab sequence are both generated, cross-reference them
2. Remove BOM items with no fab step reference
3. Flag fab steps that reference items not in BOM (log warning, don't block)

### Task D: Preference questions (AC-3)
**File:** `backend/question_trees/engine.py`
Update `suggest_additional_questions` with knowledge vs preference distinction + new preference types (gauge, framing, tabs, fastening method).

### Task E: Labor calibration rewrite (AC-5)
**File:** `backend/calculators/labor_calculator.py`
Replace `LABOR_CALIBRATION_NOTES` with the scaling reference version. Include joint-counting guidance.

### Task F: Subtotal refresh (AC-6)
**File:** `frontend/js/quote-flow.js`
Wire section subtotal elements into the existing quantity change handler.

### Task G: Weight fix (AC-7)
**File:** `backend/pdf_generator.py`
Ensure weight calculation runs for ALL profile types including sheets.

---

## 5. Evaluation Design

### Test Quotes:

**Test 1: LED Sign (same description as CS-2026-0064)**
- [ ] Finish section shows "Clear Coat" with cost and labor hours (NOT "Raw Aluminum")
- [ ] No orphaned BOM items (everything in BOM has a fab step)
- [ ] No duplicate hardware (one PSU listing, not three)
- [ ] Shop stock items listed separately with partial allocation
- [ ] Gauge question was ASKED (not assumed 0.080/0.063 split)
- [ ] Tab count question was ASKED (not assumed 54)
- [ ] Framing question was ASKED (not assumed rect tube frame)
- [ ] Hardware Install: 4+ hours for electronics
- [ ] Sheet weights calculated
- [ ] Section subtotals refresh when adjusting quantities
- [ ] Hardware total < $600 (was $1,045 — most of the fat should be cut)

**Test 2: Fence/Gate**
- [ ] Picket spacing question asked
- [ ] Material = steel (all profiles, no al_*)
- [ ] Finish section shows paint method with labor
- [ ] No rivets in BOM (welded fence)

**Test 3: End Table**
- [ ] Clear coat still works (regression)
- [ ] Labor scales DOWN from benchmarks (fewer joints than benchmark)

### Automated Tests (`tests/test_prompt43.py`):
1. `test_bom_fab_sequence_no_orphans` — every BOM item has a fab step reference
2. `test_bom_deduplication` — no duplicate components
3. `test_preference_questions_gauge` — description without gauge specified → question fires
4. `test_preference_questions_tabs` — sign with letters → tab count question fires
5. `test_finish_flows_to_output` — finish answer → FINISHING section shows it
6. `test_labor_scales_with_size` — smaller sign → fewer hours than benchmark
7. `test_hardware_install_electronics` — electronics project → 4+ hours
8. `test_sheet_weight_calculated` — al_sheet profile → weight > 0
9. `test_shop_stock_allocation` — bulk items show partial allocation

### Commit:
```
git add . && git commit -m "P43: No Orphans No Assumptions — BOM validation, tiering, preferences, finish fix, labor scaling" && git push
```
