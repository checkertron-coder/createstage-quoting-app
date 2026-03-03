# PROMPT 21 — Actually Fix the Cantilever Gate Calculator

## READ THIS FIRST

Prompt 20 wrote a detailed specification for three fixes to the cantilever gate system. **None of the actual code changes were implemented.** The prompt file was committed but the calculator, question tree, and AI cut list were left untouched. This prompt re-specifies the same fixes with additional issues discovered from testing CS-2026-0027.

From CLAUDE.md: Building a module is not done until it's CALLED in the pipeline. After any change, trace the full path from user input → AI generation → validation → PDF output. If your new code isn't in that path, it's not done.

---

## CURRENT STATE OF THE CODE

Before making ANY changes, verify you're looking at the actual current state:

```bash
# These should all return NOTHING — confirming Prompt 20 changes were NOT made:
grep -n "bottom_guide" backend/calculators/cantilever_gate.py
grep -n "adjacent_fence" backend/calculators/cantilever_gate.py
grep -n "adjacent_fence" backend/question_trees/data/cantilever_gate.json
grep -n "ADDITIONAL CONTEXT" backend/calculators/ai_cut_list.py
```

If any of those return results, Prompt 20 was partially applied — read what exists before adding duplicate code.

---

## PROBLEM STATEMENT

A fabricator described this real job:

> "I am trying to build a fence, in the back of an alley, that connects the two sides of the properties fence together. The one side of the fence is 15' long, there is 12' opening, then there is a 13' fence. There will be 4 fence posts, two per each side of each fence portion. The customer wants a Cantilever gate, with the rollers on the top so there is nothing to obscure the bottom."

The app produced CS-2026-0027 with these problems:

1. **Bottom guide logic never implemented.** `cantilever_gate.py` lines 281-294 ALWAYS generate a bottom guide rail. The `bottom_guide` question exists in the tree and the user answered "No bottom guide (top-hung only)" but the calculator never reads `fields.get("bottom_guide")`. The code literally doesn't reference this field at all — run `grep -n "bottom_guide" backend/calculators/cantilever_gate.py` to confirm.

2. **Fence sections not in calculator.** The fence materials that appeared on CS-2026-0027 came from Gemini's AI cut list interpreting the description — NOT from calculator logic. This means:
   - No fence-specific labor was calculated (labor actually DECREASED vs the gate-only quote)
   - The fab sequence ignores fence sections entirely (Steps 11-13 only mention 3 posts)
   - Fence material costs aren't structurally calculated — they depend on Gemini's mood

3. **Roller carriage shows qty=1 on PDF but code says qty=2.** The `carriage_count = 2` on line 298 is correct, but the PDF shows "Qty: 1" and "$165.00" (single unit price). Either the PDF renderer is showing unit price × 1 instead of qty × unit, or the hardware subtotal calculation is only counting 1 unit. Hardware subtotal is $177 ($165 + $12) which is 1 carriage + 1 stop — should be $342 ($165×2 + $12) for 2 carriages.

4. **Fab sequence post math is wrong.** Step 11 says "cut three 15' lengths" and "12' above ground, 3' embed" but the cut list says 156" posts (13' = 10' above ground + 36" embed). The AI is fabricating dimensions instead of reading the cut list.

5. **No latch hardware on quote.** The user selected a gravity latch but it doesn't appear in hardware. Check if `latch_type` field value is being parsed correctly — the `_lookup_latch()` method might not be matching the question tree answer string.

---

## ACCEPTANCE CRITERIA

### Fix 1: Bottom Guide Conditional Logic

- [ ] `cantilever_gate.py` reads `fields.get("bottom_guide", "Surface mount guide roller")`
- [ ] Three code paths based on the answer:
  - **"Surface mount guide roller"** → Current behavior (angle iron guide rail). No change.
  - **"Embedded track (flush with ground)"** → Heavier channel (C4×5.4 or similar). Add assumption about concrete channel pour.
  - **"No bottom guide (top-hung only)"** → NO bottom guide rail generated. Instead:
    - Generate an overhead support beam (HSS 4×4×1/4" for gates <800 lbs, HSS 6×4×1/4" for heavier)
    - Roller carriage description changes to "Top-mount roller carriage — standard/heavy"
    - Assumption added: "Top-hung system — minimum overhead clearance [gate height + 6"] required"
    - Post height may need to increase to support the overhead beam (add 6-12" above gate height for beam mounting)
- [ ] After implementation, `grep -c "bottom_guide" backend/calculators/cantilever_gate.py` returns at least 3

### Fix 2: Adjacent Fence Section Support

**Step A: Add questions to the question tree.**

In `backend/question_trees/data/cantilever_gate.json`, add these questions AFTER `site_access` and BEFORE `decorative_elements`:

```json
{
    "id": "adjacent_fence",
    "text": "Are there fence sections connecting to this gate?",
    "type": "choice",
    "options": [
        "Yes — fence on both sides",
        "Yes — fence on one side only",
        "No — gate only"
    ],
    "required": false,
    "hint": "Many gate installations include connecting fence sections. We can quote the complete job.",
    "depends_on": null,
    "branches": {
        "Yes — fence on both sides": ["fence_side_1_length", "fence_side_2_length", "fence_post_count", "fence_infill_match"],
        "Yes — fence on one side only": ["fence_side_1_length", "fence_post_count", "fence_infill_match"]
    }
},
{
    "id": "fence_side_1_length",
    "text": "Length of fence section 1? (in feet)",
    "type": "number",
    "required": true,
    "hint": "Measure the total run from the gate post to the end/corner.",
    "depends_on": "adjacent_fence"
},
{
    "id": "fence_side_2_length",
    "text": "Length of fence section 2? (in feet)",
    "type": "number",
    "required": true,
    "hint": "Measure the total run of the second fence section.",
    "depends_on": "adjacent_fence"
},
{
    "id": "fence_post_count",
    "text": "How many fence posts total? (not counting gate posts)",
    "type": "number",
    "required": false,
    "hint": "Typical: one post every 6-8 feet. We'll estimate if you skip this.",
    "depends_on": "adjacent_fence"
},
{
    "id": "fence_infill_match",
    "text": "Should the fence infill match the gate?",
    "type": "choice",
    "options": [
        "Yes — match the gate exactly",
        "No — simpler/different infill"
    ],
    "required": false,
    "hint": "Matching infill looks best but costs more.",
    "depends_on": "adjacent_fence"
}
```

**Step B: Add fence section generation to the calculator.**

In `backend/calculators/cantilever_gate.py`, AFTER the latch section (section 10) and BEFORE the square footage calculation (section 11), add fence section logic. This code runs in the RULE-BASED path (not the AI path).

The fence section must generate:
- Fence posts (same profile as gate posts, same height + embed depth)
- Fence post concrete (if gate posts have concrete)
- Top and bottom rails per section (same frame material as gate)
- Pickets per section (same infill as gate, or simplified if fence_infill_match is "No")
- Additional weld inches for fence work
- Additional square footage for finishing

Key variables already in scope from earlier in the calculator that the fence code needs:
- `height_in` — gate/fence height
- `post_concrete_depth_in` — embed depth
- `post_profile` — e.g. "sq_tube_4x4_11ga" (from `self._lookup_post(post_size)`)
- `post_size` — raw answer e.g. '4"×4"'
- `frame_profile` — e.g. "sq_tube_2x2_11ga"
- `frame_size`, `frame_gauge`
- `infill_type` — e.g. "Vertical pickets"
- `lookup` — MaterialLookup instance
- `items`, `hardware`, `assumptions`, `total_weight`, `total_sq_ft`, `total_weld_inches` — accumulator variables

For each fence section, calculate:
```python
# Per section, posts are spaced ~6-8 ft apart
# A 15' section gets 2 posts (one mid, one end — gate post is at the other end)
# A 13' section gets 2 posts
# Top rail + bottom rail = 2 pieces of frame material per section
# Pickets: section_length_in / (picket_width + spacing) + 1
# Picket height: height_in - (2 × frame_size_in) — fits inside top/bottom rails
# Weld inches: pickets × 2 welds × 1.5" each + rail-to-post × 4 welds × 3" each
```

Also update `total_sq_ft` with fence area (both sides per section).

**Step C: Ensure fence materials flow through the ENTIRE pipeline.**

After adding fence items to `items` list:
1. They automatically appear in the material table (make_material_list includes all items)
2. They automatically get priced in pricing_engine (sums all item line_totals)
3. They automatically appear on the PDF (renders all materials)
4. Labor estimator picks up additional weld inches → more labor hours

Verify: the fence materials MUST increase the total labor hours vs a gate-only quote.

### Fix 3: Roller Carriage Quantity Bug

- [ ] Verify `carriage_count = 2` in the calculator code (it IS 2, line 298)
- [ ] Check how `hardware_sourcer.py` → `price_hardware_list()` processes the quantity field
- [ ] Check how `pdf_generator.py` renders hardware quantity — it may be showing unit price in the "Qty" column instead of actual quantity
- [ ] The hardware subtotal MUST be $165×2 + $12 = $342 for standard carriages + stops (not $177)
- [ ] If the PDF shows qty=1, trace the data from `make_hardware_item(quantity=2)` → `outputs_json.hardware` → PDF render to find where quantity gets dropped

Look at these specific locations:
```bash
grep -n "quantity" backend/hardware_sourcer.py | head -20
grep -n "quantity\|Qty" backend/pdf_generator.py | head -20
```

### Fix 4: AI Build Instructions Must Reference Cut List Data

The AI-generated fabrication sequence invents its own dimensions instead of using the cut list. In `backend/calculators/ai_cut_list.py`, wherever the build instruction prompt is assembled:

- [ ] Include the actual cut list data in the prompt (piece names, profiles, lengths, quantities)
- [ ] Add this instruction to the prompt: "IMPORTANT: Use the EXACT dimensions from the cut list above. Do not estimate or round dimensions. When referring to a post, state its exact length from the cut list (e.g., '156 inches' not '15 feet'). When stating how many posts to cut, use the exact quantity from the cut list."
- [ ] Include fence sections in the build instructions prompt if they exist in the cut list

### Fix 5: Latch Hardware Missing

- [ ] Check the `latch_lock` question in `cantilever_gate.json` — what are the answer options?
- [ ] Check `_lookup_latch()` in `cantilever_gate.py` — does it match those answer strings?
- [ ] The user selected a gravity latch but it doesn't appear on the quote
- [ ] After fix, gravity latch must appear in hardware section with pricing

Look at:
```bash
python3 -c "
import json
d=json.load(open('backend/question_trees/data/cantilever_gate.json'))
for q in d['questions']:
    if q['id'] == 'latch_lock':
        print(json.dumps(q, indent=2))
"
```

Then compare the option strings with what `_lookup_latch()` expects. The function does `str(latch_str).lower()` and checks for "gravity" — so if the question answer is "Gravity latch" it should match. But maybe the field name is `latch_lock` in the tree and the calculator reads `latch_type` instead? Check:

```bash
grep -n "latch" backend/calculators/cantilever_gate.py | head -10
```

If the calculator reads `fields.get("latch_type")` but the question tree field is `latch_lock`, that's the bug — field name mismatch.

---

## CONSTRAINT ARCHITECTURE

### What NOT to Change
- Do NOT modify pricing_engine.py — it works fine
- Do NOT modify the frontend — it renders whatever the pipeline produces
- Do NOT modify pdf_generator.py UNLESS the qty bug is in the PDF renderer (if so, minimal fix only)
- Do NOT modify the hardware_mapper.py from Prompt 19
- Do NOT touch the swing_gate calculator — it's a different job type

### Important Implementation Notes
- The cantilever_gate calculator has TWO paths: AI path (line 60-63, when description exists) and rule-based path (line 64+). The bottom guide fix and fence section generation go in the RULE-BASED path.
- For the AI path: enrich the prompt so Gemini generates fence cuts + respects mounting style. But the CALCULATOR must also generate fence materials in the rule-based path, because the AI path may not always be used.
- When adding fence materials to the `items` list, make the descriptions clearly distinguishable: "Fence Section 1 — top rail" not just "top rail". The PDF and frontend need to show these as fence items.
- The labor estimator (`backend/calculators/labor_calculator.py`) calculates hours from weld inches, cut count, and material weight. By adding fence weld inches and additional items to the material list, labor SHOULD automatically increase. Verify this — if it doesn't, the labor estimator may need the fence items passed separately.

### Material Profiles That May Need Adding
Check `backend/calculators/material_lookup.py` `_SEEDED_PRICES` for:
- `hss_4x4_0.25` — 4"×4"×1/4" wall HSS (~$14/ft, 12.21 lbs/ft, 24' sticks)
- `channel_c4x5.4` — C4×5.4 channel (~$6/ft, 5.4 lbs/ft, 20' sticks)

Add them if missing. These are only needed for the top-hung overhead beam and embedded track options.

---

## DECOMPOSITION (execution order)

1. **Fix 5 first** (latch field name mismatch) — smallest fix, highest certainty
2. **Fix 3** (roller carriage quantity) — trace the data path, find where qty drops
3. **Fix 1** (bottom guide conditional) — modify the calculator section that generates bottom guide rail
4. **Fix 2** (fence sections) — add question tree questions, then add calculator logic
5. **Fix 4** (AI build instructions) — enrich the Gemini prompt with cut list data

After EACH fix, run:
```bash
python -c "from backend.main import app; print('OK')"
```
to verify no import errors.

---

## EVALUATION DESIGN

### Test 1: Latch Appears on Quote
Run a cantilever gate quote, select "Gravity latch" for latch_lock.
- [ ] Hardware section shows "Gate latch — Gravity latch" with pricing
- [ ] Hardware subtotal includes the latch price

### Test 2: Roller Carriage Quantity
Run a cantilever gate quote.
- [ ] Hardware shows roller carriage with Qty: 2
- [ ] Hardware subtotal = (carriage_price × 2) + (stop_price × 2) + (latch_price × 1)

### Test 3: Bottom Guide — Surface Mount
Select "Surface mount guide roller" for bottom_guide.
- [ ] Bottom guide rail (angle iron) appears in materials — existing behavior preserved

### Test 4: Bottom Guide — Top Hung
Select "No bottom guide (top-hung only)" for bottom_guide.
- [ ] NO bottom guide rail in materials
- [ ] Overhead support beam (HSS 4×4×1/4" or similar) in materials
- [ ] Roller carriage description says "Top-mount"
- [ ] Assumption about overhead clearance

### Test 5: Adjacent Fence — Both Sides
Answer "Yes — fence on both sides", 15' and 13' lengths, 4 fence posts.
- [ ] Fence posts appear in materials (4 × post profile)
- [ ] Fence rails appear (2 sections × top + bottom)
- [ ] Fence pickets appear per section
- [ ] Fence post concrete appears
- [ ] Total price is HIGHER than gate-only (not lower!)
- [ ] Labor hours are HIGHER than gate-only
- [ ] Fab sequence mentions fence fabrication and installation

### Test 6: Gate Only — No Regression
Answer "No — gate only" for adjacent_fence.
- [ ] No fence materials appear
- [ ] Quote matches pre-Prompt-21 gate-only behavior

### Test 7: The Full Job
Run Burton's exact description with: top-hung, both fence sides (15' + 13'), 4 fence posts, gravity latch.
- [ ] All fence materials present and separately labeled
- [ ] No bottom guide rail
- [ ] Overhead beam present
- [ ] Top-mount roller carriages × 2
- [ ] Gravity latch in hardware
- [ ] Gate stops × 2 in hardware
- [ ] Labor hours > 70 (fence adds significant welding)
- [ ] Total quote > $14,000 (gate + fence + installation)

---

## VERIFICATION CHECKLIST

```bash
# After ALL changes:

# 1. Bottom guide logic exists
grep -c "bottom_guide" backend/calculators/cantilever_gate.py
# Expected: >= 3

# 2. Fence section logic exists
grep -c "adjacent_fence\|fence_side" backend/calculators/cantilever_gate.py
# Expected: >= 5

# 3. New questions exist in tree
python3 -c "
import json
d=json.load(open('backend/question_trees/data/cantilever_gate.json'))
ids=[q['id'] for q in d['questions']]
for f in ['adjacent_fence','fence_side_1_length','fence_side_2_length','fence_post_count']:
    print(f'{f}: {\"OK\" if f in ids else \"MISSING\"}')"

# 4. Latch field name matches
grep "latch_lock\|latch_type" backend/calculators/cantilever_gate.py

# 5. App starts clean
python -c "from backend.main import app; print('OK')"

# 6. No duplicate fence questions (run twice to make sure)
python3 -c "
import json
d=json.load(open('backend/question_trees/data/cantilever_gate.json'))
ids=[q['id'] for q in d['questions']]
dupes=[x for x in ids if ids.count(x)>1]
print('DUPLICATES:',dupes if dupes else 'none')"
```

---

## FILES TO MODIFY

- `backend/question_trees/data/cantilever_gate.json` — add 5 new questions (adjacent_fence + 4 sub-questions)
- `backend/calculators/cantilever_gate.py` — bottom guide conditional (replace lines ~281-294), fence section generation (new section after latch), roller carriage description update, latch field name fix
- `backend/calculators/ai_cut_list.py` — enrich build instruction prompt with cut list data + fence context
- `backend/calculators/material_lookup.py` — add hss_4x4_0.25 and channel_c4x5.4 profiles if missing
- `backend/hardware_sourcer.py` OR `backend/pdf_generator.py` — fix roller carriage qty display (wherever the bug is)
