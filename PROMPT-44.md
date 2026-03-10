# PROMPT 44 — "No Orphans, No Assumptions"

*Nate B. Jones — 5 Spec Engineering Primitives*

P43 fixed the foundation (finish pipeline, subtotals, labor scaling). P44 adds intelligence — the system learns when to ask vs assume, when to itemize vs lump, and enforces consistency between what it lists and what it builds.

---

## 1. Problem Statement

Four feature gaps identified from CS-2026-0064 analysis:

**A. BOM and fabrication sequence are disconnected — orphaned items in both directions.**
CS-2026-0064 lists 200 blind rivets, rivet drill bits, DIN rail, piano hinges, prototype PCBs — none appear in the 44-step fab sequence. The BOM and fab sequence are two views of the SAME build. Every BOM item must have a fab step that uses it. Every fab step must reference items from the BOM.

**B. BOM is over-engineered — no tiering, no deduplication.**
Hardware hit $1,045 because Opus itemized 100 screws at $0.12, 200 rivets at $0.06, 80 washers at $0.07. It listed 3 Mean Well PSUs (one generic + 2 specific) and triple-counted wire. Rivets on a waterproof welded sign box make no sense. The BOM needs tiered output (project-specific vs shop stock vs excluded) and deduplication.

**C. The system makes design decisions without asking — preferences treated as knowledge.**
CS-2026-0064 used two sheet gauges (0.080" face, 0.063" back) without asking. It assumed rect tube framing without asking if the box depth is sufficient. It generated 54 tabs when the answer is 9-18 (1-2 per letter). These are PREFERENCES with multiple valid approaches — the system should ask, not assume.

**D. No "Shop Stock" distinction for bulk inventory items.**
Wire spools, heat shrink kits, sandpaper 50-packs, gloves, rags — you don't buy these FOR one job. The quote needs a separate section for shop inventory items with partial cost allocation.

---

## 2. Acceptance Criteria

### AC-1: BOM ↔ Fab sequence mirror rule
- After generating the BOM and fabrication sequence, run a VALIDATION pass in Python (not another AI call):
  - For each hardware item: check if any fab step text contains a keyword match (item name, category, or component type)
  - Items with NO fab step reference → REMOVE from BOM automatically
  - Fab steps referencing unlisted items → log a warning (don't block output)
- This catches: rivets with no rivet step, drill bits for unused fasteners, DIN rail with no DIN rail step

### AC-2: Tiered BOM output
Update the Opus BOM prompt to produce tiered output:

**Tier 1 — Project-Specific Purchases (itemize each):**
Components you'd actually GO BUY for this job. Not in a typical shop.
Examples: ESP32, LED strips, power supplies, specialty connectors, polycarbonate, laser cutting.

**Tier 2 — Shop Stock (list with partial allocation):**
Bulk items that go into shop inventory.
List full purchase price + percentage allocated to this job.
Format: "Heat shrink kit — $12.00 (shop stock, ~10% to this job = $1.20)"
Only the allocated amount adds to the quote total.

**Tier 3 — Do Not Include:**
Over-engineered items not in the description. Items that don't match the job's fastening method (no rivets on welded waterproof assemblies). Items with no corresponding fab step.

**Deduplication:** If the same component appears twice (generic + specific listing, or old catalog + new Opus), merge into ONE entry. No triple-counted wire, no duplicate PSUs.

### AC-3: Design preferences are asked, not assumed
Update `suggest_additional_questions` prompt in `engine.py` with explicit knowledge vs preference distinction:

```
PREFERENCES — ALWAYS ASK when not specified in description:
* Sheet gauge/thickness — NEVER use different gauges for different panels without asking
  Options: 0.063" (1/16"), 0.080" (5/64"), 0.125" (1/8") for aluminum; 11ga, 14ga, 16ga for steel
* Number of tabs/spacers per letter/component AND tab spacing (typically 2-3 per letter, NOT 54)
* Internal framing — does the assembly need stiffeners, or does the geometry provide rigidity?
  (A 6" deep box may be rigid enough with just a couple 90° gusset brackets)
* Number of finish coats (1 coat, 2 coats, etc.)
* Picket/baluster spacing on fences
* Weld finish quality (production/industrial vs furniture grade)
* Fastening method for non-obvious joints

SIGN-SPECIFIC PREFERENCES (for LED/illuminated sign jobs):
* Letter construction method:
  (A) Open-back letters with spacer tabs — letters pushed into box by tabs, LEDs visible through
      cutouts from behind, light reflects off back panel and spills through gaps. Simpler build.
  (B) Channel letters with formed sidewalls — bent sheet wraps around each letter perimeter creating
      enclosed 3D letter forms. LEDs hidden inside each letter channel. More complex, higher cost.
  This DRAMATICALLY changes the build — different materials, different fab steps, different look.
* If channel letters (option B): what gauge for formed sidewalls? (14ga bends easier around curves,
  1/8" resists TIG heat warping better on tight radii — fabricator preference)
* If channel letters (option B): weld coverage — full perimeter weld or tack/spot weld?
  (Full weld only needed if sidewalls are visible up close)
* Waterproof scope — what needs to be waterproof?
  (A) Entire sign assembly sealed (all seams welded shut)
  (B) Only the electronics enclosure (ESP32, PSU) — sign body and LEDs are already IP67 rated
  This changes whether side panels get welded shut or left accessible.
* Back panel access method:
  (A) Sealed/welded shut
  (B) Removable panel with screws (for electronics access/maintenance)
  (C) Hinged access panel
  (D) Underlapping panels with gap for wiring access

KNOWLEDGE — NEVER ASK (just execute):
* Miter angle for square frames (45°)
* Weld process by material (TIG for aluminum, MIG for steel in shop)
* Deburring after cuts
* Waterproof assemblies where specified = welded seams, not riveted/screwed
```

### AC-4: Shop Stock section in quote output
- Add a "SHOP STOCK" section to the PDF output, separate from "HARDWARE & PARTS"
- Items show: description, full purchase price, allocation percentage, allocated cost
- Only allocated costs roll into the quote total
- Consumables that are clearly shop stock (sandpaper packs, glove boxes, rag bundles) go here too

### AC-5: Aluminum weight calculation for sheet stock
- Sheet weights must be calculated (currently "-" for sheets)
- Weight = length × width × thickness × density
- Aluminum 6061-T6: 0.098 lb/in³

---

## 3. Constraint Architecture

- **DO NOT modify the finish pipeline** — P43 fixed it
- **DO NOT modify labor calibration notes** — P43 rewrote them
- **DO NOT modify question tree JSON files** — preferences come from `suggest_additional_questions`
- **DO NOT modify `FAB_KNOWLEDGE.md`**
- **BOM validation must be deterministic Python**, not another AI call
- **Keep P41 electronics catalog as FALLBACK** — Opus BOM is primary
- **All existing tests must pass**

---

## 4. Decomposition

### Task A: BOM ↔ Fab sequence validation (AC-1)
**Files:** New `backend/bom_validator.py`, wire into `backend/pricing_engine.py`
1. After BOM and fab sequence are generated, cross-reference them
2. Build keyword sets from BOM items (e.g., "rivet" → ["rivet", "riveting", "pop rivet"])
3. Scan fab step text for each keyword set — no match = orphaned item → remove
4. Log removals for debugging

### Task B: BOM tiering + deduplication (AC-2)
**Files:** `backend/hardware_sourcer.py`, `backend/pricing_engine.py`, `backend/pdf_generator.py`
1. Update Opus BOM prompt with tiered instructions
2. Parse response into Tier 1 and Tier 2 items
3. Deduplication pass: group by component type, merge duplicates
4. Update PDF to show separate sections

### Task C: Preference questions (AC-3)
**File:** `backend/question_trees/engine.py`
Update `suggest_additional_questions` prompt with knowledge vs preference distinction.

### Task D: Shop Stock section (AC-4)
**File:** `backend/pdf_generator.py`
Add Shop Stock section to PDF output with allocation math.

### Task E: Sheet weight fix (AC-5)
**File:** `backend/pdf_generator.py`
Ensure weight calculation runs for sheet profiles (length × width × thickness × density).

---

## 5. Evaluation Design

### Test Quotes:

**Test 1: LED Sign**
- [ ] No orphaned BOM items (rivets removed, DIN rail removed if no fab step)
- [ ] No duplicate hardware (one PSU entry, one wire entry)
- [ ] Shop stock items in separate section with partial allocation
- [ ] Hardware total < $600 (was $1,045)
- [ ] Gauge question was ASKED
- [ ] Tab count question was ASKED
- [ ] Framing question was ASKED
- [ ] Sheet weights calculated

**Test 2: Fence/Gate**
- [ ] Picket spacing question asked
- [ ] No rivets (welded fence)
- [ ] All steel profiles (no al_*)

**Test 3: End Table**
- [ ] Regression — everything still works

### Automated Tests (`tests/test_prompt44.py`):
1. `test_bom_fab_no_orphans` — BOM item with no fab step → removed
2. `test_bom_deduplication` — duplicate PSUs → merged to one
3. `test_preference_gauge_question` — no gauge in description → question fires
4. `test_preference_tab_question` — sign with letters → tab count question fires
5. `test_preference_framing_question` — box construction → framing question fires
6. `test_shop_stock_allocation` — bulk items show partial allocation
7. `test_sheet_weight_calculated` — al_sheet → weight > 0

### Commit:
```
git add . && git commit -m "P44: No Orphans No Assumptions — BOM validation, tiering, preferences, shop stock" && git push
```
