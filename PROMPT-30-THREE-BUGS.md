# PROMPT 30 — Three Bugs Standing Between Us and a Working Quote

## Context

CS-2026-0038 is the closest we've gotten to a correct quote. The cut list is finally individual pieces. The fab sequence is 18 steps of real, detailed fabrication instructions. Hardware is right. Consumables are right. Surface prep solvent is in there. Overhead beam is qty 1.

But three bugs are making the quote wrong. Fix these three things and we have a working product.

## ACTUAL CS-2026-0038 OUTPUT (screenshots from the live app)

### Materials Section (first 5 lines are the problem):
```
sq_tube_4x4_11ga — 137.2 ft       qty 1    $679.14     ← BULK AGGREGATE from Claude
hss_4x4_0.25 — 21.0 ft            qty 1    $173.25     ← BULK AGGREGATE from Claude
sq_tube_2x2_11ga — 247.7 ft       qty 1    $617.81     ← BULK AGGREGATE from Claude
plate_0.25 — 3.0 ft               qty 1    $10.50      ← BULK AGGREGATE from Claude
sq_bar_0.625 — 2171.4 ft          qty 1    $2,388.54   ← BULK AGGREGATE from Claude
Gate posts — 3 × 4 (18.7 ft)      qty 3    $277.20     ← POST-PROCESSOR itemized (correct format)
Post concrete                      qty 3    $53.46      ← POST-PROCESSOR (correct)
Overhead support beam              qty 1    $240.00     ← POST-PROCESSOR (correct)
Fence posts Side 1                 qty 2    $184.80     ← POST-PROCESSOR (correct)
... (rest of fence items, all correct format)
```
Material Subtotal: $6,852.59 — DOUBLE COUNTED because bulk + itemized both contribute.

### Assumptions (shows the height bug):
```
Posts: 4, 18.7 ft each (180" above grade + 2" clearance + 42" embed).
```
180" above grade = 15 ft. The gate is 10 ft tall. Something parsed 15' fence length as gate height.

### Fab Sequence Step 2 (confirms height bug):
```
Gate is 18.0 ft (216") long x 15 ft (180") tall.
```
Should be 10 ft (120") tall.

### Cut List (NOW CORRECT FORMAT — individual pieces):
```
gate_post          sq tube 4x4 11ga    18.7 ft    3     ← length wrong (should be 13.7 ft)
fence_post         sq tube 4x4 11ga    18.7 ft    4     ← length wrong (should be 13.7 ft)
overhead_beam      hss 4x4 0.25        20.0 ft    1     ← CORRECT ✅
gate_top_rail      sq tube 2x2 11ga    18.0 ft    1     ← CORRECT ✅
gate_bottom_rail   sq tube 2x2 11ga    18.0 ft    1     ← CORRECT ✅
gate_vertical_stile sq tube 2x2 11ga   14.7 ft    2     ← wrong (should be ~9.7 ft for 10' gate)
gate_mid_rail      sq tube 2x2 11ga    17.7 ft    2     ← close enough
gate_diagonal_brace sq tube 2x2 11ga   11.6 ft    1     compound
gate_picket        sq bar 0.625        14.7 ft    55    ← length wrong (should be ~9.7 ft), count correct ✅
fence_s1_picket    sq bar 0.625        14.7 ft    46    ← length wrong
fence_s2_picket    sq bar 0.625        14.7 ft    40    ← length wrong
```

### What's CORRECT (do not touch):
- Gate panel length = 18.0 ft (216") ✅
- Overhead beam qty = 1 ✅
- Gate picket count = 55 ✅
- Fence picket counts = 46 and 40 ✅
- Hardware: 2 roller carriages, 2 stops, 1 latch ✅
- Consumables: welding wire, discs, gas, primer, paint, surface prep solvent ✅
- Fab sequence: 18 detailed steps with safety notes ✅
- Site install at $145/hr, shop at $125/hr ✅
- Field welding = Stick (SMAW, E7018) ✅
- Surface prep solvent wipe before priming ✅
- Markup selector with 0-30% options ✅
- Exclusions section ✅
- Stock order summary ✅

---

## BUG 1: Duplicate Materials — Bulk Aggregates + Itemized Items

### Symptom
The materials section has TWO sets of items:
1. Claude's bulk aggregates at the top (e.g., "sq_bar_0.625 — 2171.4 ft, qty 1, $2,388.54")
2. Post-processor's itemized pieces below (e.g., "Fence pickets — Side 1 × 49 pcs, $799.68")

Both contribute to the material subtotal. The customer is being charged twice for the same steel.

### Root Cause
When Claude generates a cut list via `_build_from_ai_cuts()` in `base.py`, it returns BOTH:
- `items`: consolidated material line items (total footage per profile — the bulk aggregates)
- `cut_list`: individual pieces with names and lengths

The `items` list goes into the materials section of the quote. The post-processor in `cantilever_gate.py` then ADDS more items (gate posts, fence sections, etc.) to the same `items` list. Result: both sets appear on the quote.

### Fix
The bulk aggregate lines from Claude should be REMOVED from the materials section when the post-processor has generated itemized replacements. The itemized pieces from the post-processor + cut list are what the customer should see.

**Option A (recommended):** In `_post_process_ai_result()`, at the very beginning, REMOVE all bulk aggregate items from the `items` list. A bulk aggregate is any item where qty=1 and the description is just a profile key + footage (e.g., "sq_tube_2x2_11ga — 247.7 ft"). Then the post-processor adds its own itemized items. The cut list individual pieces drive the material totals.

How to detect bulk aggregates:
```python
# Remove bulk aggregate items — these are Claude's raw material summaries
# that get replaced by the post-processor's itemized pieces.
# A bulk aggregate looks like: "sq_tube_2x2_11ga — 247.7 ft" with qty=1
items = [
    item for item in items
    if not (
        item.get("quantity", 0) == 1
        and " — " in item.get("description", "")
        and "ft" in item.get("description", "").split(" — ")[-1]
    )
]
```

**Option B:** Don't generate bulk aggregates at all. In `_build_from_ai_cuts()` in `base.py` (around line 220), change the consolidation logic to NOT create summary line items. Only populate the `cut_list` and let the post-processor build the `items` list from the cut list pieces.

**Go with Option A** — it's surgical and doesn't change the base class behavior that other calculators depend on.

### Where to make the change
`backend/calculators/cantilever_gate.py`, method `_post_process_ai_result()`, right at the top after `items = list(ai_result.get("items", []))` (around line 496).

---

## BUG 2: Gate Height Parsed as 15 ft Instead of 10 ft

### Symptom
Everything that depends on gate height is wrong:
- Posts are 18.7 ft (224") instead of 13.7 ft (164")
- Pickets are 14.7 ft (176") instead of ~9.7 ft (116")
- Vertical stiles are 14.7 ft instead of ~9.7 ft
- Fab sequence says "15 ft tall"
- Assumptions say "180" above grade"

### Root Cause
The job description says: "The one side of the fence is 15' long, there is 12' opening, then there is a 13' fence."

Something in the height parsing is picking up "15'" from the fence length instead of the actual "10' tall" from the gate specification. This could be:

1. The `parse_feet()` method grabbing the wrong number from the fields
2. The `height` field in `fields` dict actually containing "15" instead of "10"
3. The AI extracting height as 15 from the description during the question tree phase

**To diagnose:** Add a debug log or check what value `fields.get("height")` returns in `_post_process_ai_result()`. The fix depends on where the wrong value enters the pipeline.

**Most likely cause:** The `height` field in the question tree is being populated from the AI's extraction of the job description, and the AI is confusing "15' long" fence with gate height. Check `backend/question_trees/engine.py` — the `_call_claude_extract()` function that extracts fields from the description may be putting 15 in the height field.

### Fix

**Approach 1 — Fix at the calculator level (immediate):**
In `_post_process_ai_result()`, after parsing `height_ft`, add a sanity check:
```python
height_ft = self.parse_feet(fields.get("height"), default=6.0)

# Sanity check: residential gates/fences are typically 3-12 ft tall.
# If height exceeds 12 ft, it may be a parsing error (e.g., fence length
# being read as gate height). Log a warning.
if height_ft > 12.0:
    logger.warning(
        "Gate height %.1f ft seems too tall — may be a parsing error. "
        "Check that 'height' field (%s) is correct.",
        height_ft, fields.get("height"))
    # Don't auto-correct — but flag it in assumptions
    assumptions.append(
        "WARNING: Gate height %.1f ft exceeds typical residential range (3-12 ft). "
        "Verify the height field is correct." % height_ft)
```

**Approach 2 — Fix at the extraction level (better long-term):**
In the AI cut list prompt (`_build_cut_list_prompt()` in `ai_cut_list.py`), add the enforced height from the fields:
```
GATE HEIGHT: The gate height is {height} as specified by the user. Do NOT confuse fence section
lengths (15 ft, 13 ft) with gate height. The height applies to the gate AND the fence sections.
```

Also: in `_build_instructions_prompt()`, make sure `enforced_dimensions` includes `gate_height_inches` and pass it through. This was specified in Prompt 28 but may not be working if the `height` field itself is wrong.

**Approach 3 — Fix the question tree extraction:**
Check what the `height` field actually contains. In `backend/question_trees/data/cantilever_gate.json`, find the `height` question and check if it has validation that limits it to reasonable values. If the user answered "10" in the form, the field should be "10" — if it's "15", then the AI extraction overwrote it.

**Do all three approaches.** The sanity check catches it, the prompt reinforces it, and the extraction fix prevents it.

---

## BUG 3: Model is Still Sonnet, Not Opus

### Symptom
Assumptions section says: "Labor hours estimated by AI (claude-sonnet-4-6 via Claude)"

The owner wants Opus (claude-opus-4-6) for cut list generation. Sonnet is producing decent results but Opus will be more reliable on complex jobs.

### Fix
This is an environment variable on Railway, not a code change. The owner needs to set:
```
CLAUDE_FAST_MODEL=claude-opus-4-6
```

However, the code should also update the hardcoded default so it works without the env var:

In `backend/claude_client.py`, line 23:
```python
_DEFAULT_FAST = "claude-sonnet-4-6"
```
Change to:
```python
_DEFAULT_FAST = "claude-opus-4-6"
```

Leave `_DEFAULT_DEEP` as Sonnet — it's not being used for anything right now, and if we add deep calls later we can decide then.

---

## Decomposition

1. Fix Bug 1: Remove bulk aggregates from materials in `_post_process_ai_result()`
2. Fix Bug 2: Add height sanity check in calculator + reinforce in AI prompts + check question tree extraction
3. Fix Bug 3: Update default fast model to `claude-opus-4-6` in `claude_client.py`
4. Verify nothing from the ✅ list broke

## Evaluation Design

```bash
# Bug 1: Verify bulk aggregate removal code exists
grep -n "bulk aggregate\|Remove bulk\| — .*ft" backend/calculators/cantilever_gate.py | head -5

# Bug 2: Verify height sanity check exists
grep -n "height.*12\|height.*tall\|parsing error\|too tall" backend/calculators/cantilever_gate.py | head -5

# Bug 3: Verify model default
grep -n "DEFAULT_FAST" backend/claude_client.py

# Runtime check
cd backend && python -c "from calculators.cantilever_gate import CantileverGateCalculator; print('OK')"
cd backend && python -c "from claude_client import _DEFAULT_FAST; print('Model:', _DEFAULT_FAST)"
```
