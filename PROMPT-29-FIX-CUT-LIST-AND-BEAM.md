# PROMPT 29 — Fix Aggregated Cut List + Overhead Beam Qty + Gate Picket Count

## Context for Claude Code

You just implemented Prompt 28 which simplified the post-processor. Some things got better, some things got worse. Here's the FULL picture — what's right, what was always right, what's broken now, and what was broken before and is still broken.

## ACTUAL OUTPUT FROM CS-2026-0037 (your last implementation)

### Job Description (user input):
```
12' wide, cantilever sliding gate, 10' tall, with Square tube frame, and Pickets infill.
Paint finish. Full site installation included. I am trying to build a fence, in the back
of an alley, that connects the two sides of the properties fence together. The one side of
the fence is 15' long, there is 12' opening, then there is a 13' fence. There will be 4
fence posts, two per each side of each fence portion. The customer wants a Cantilever gate,
with the rollers on the top so there is nothing to obscure the bottom.
```

### Materials Section:
```
Gate frame - 2x2 11ga (face + cou)    sq_tube_2x2_11ga    5    $33.52    $167.60
Mid-rail stiffeners - 2x2 11ga ×      sq_tube_2x2_11ga    2    $46.39    $92.78
Infill - Pickets at 4" OC             sq_bar_0.625        39    $10.82    $421.98
Posts - 4×3 (13.7 ft each)            sq_tube_4x4_11ga    3    $67.65    $202.95
Post concrete - 3 holes × 12" × 42"   concrete_footing    3    $17.82    $53.46
Overhead support beam HSS 6×4×1/4     hss_6x4_0.25        2    $247.20   $494.40
Fence posts Side 1 × 2                sq_tube_4x4_11ga    2    $67.65    $135.30
Fence post concrete Side 1            concrete_footing     2    $17.82    $35.64
Fence rails Side 1 top+bottom         sq_tube_2x2_11ga    3    $37.41    $112.23
Fence mid-rails Side 1 × 2            punched_channel      2    $74.25    $148.50
Fence pickets Side 1 × 46 pcs         sq_bar_0.625        49    $10.82    $530.18
Fence posts Side 2 × 2                sq_tube_4x4_11ga    2    $67.65    $135.30
Fence post concrete Side 2            concrete_footing     2    $17.82    $35.64
Fence rails Side 2 top+bottom         sq_tube_2x2_11ga    3    $32.42    $97.26
Fence mid-rails Side 2 × 2            punched_channel      2    $64.35    $128.70
Fence pickets Side 2 × 40 pcs         sq_bar_0.625        42    $10.82    $454.44
Material Subtotal: $3,246.36
```

### Cut List:
```
Gate frame - 2x2 11ga      sq_tube_2x2_11ga   806.4"   5   miter_45
Mid-rail stiffeners         sq_tube_2x2_11ga   446.4"   2   square
Infill - Pickets            sq_bar_0.625       118"    39   square
Posts - 4×3                 sq_tube_4x4_11ga   164"     3   square
Post concrete               concrete_footing    42"     3   n/a
Overhead support beam       hss_6x4_0.25      247.2"    2   square
(fence items follow identically to materials list)
```

### Detailed Cut List:
```
(Exact copy of the Cut List above — NO individual piece breakdown)
```

### Fab Sequence Excerpts:
```
Step 1: "Mark the 5 gate frame members (2x2 11ga, 806.4" each) with 45-degree miter angles"
Step 2: "Gate frame: cut 5 pieces of 2x2 11ga square tube at 806.4" with 45-degree miters"
Step 3: "The gate is 18.0 ft long x 10 ft tall" ← CORRECT dimension!
Step 8: "Clean all fabricated steel with degreaser wipe-down before priming" ← should be surface prep solvent, not degreaser
Step 11: "Mount the 2 overhead support beams (HSS 6x4x1/4", 247.2" = 20.6 ft each)" ← qty 2 is WRONG
```

### Consumables:
```
ER70S-6 welding wire (4 lbs)                    $14.00
4.5" grinding disc x7                           $31.50
4.5" flap disc x4                               $26.00
75/25 Ar/CO2 shielding gas (215 cu ft)          $17.20
Primer - 3 gallon(s)                           $105.00
Paint - 3 gallon(s)                            $135.00
Surface prep solvent - denatured alcohol (5 gal) $75.00
```

### Labor:
```
Layout & Setup     4.2 hrs   $125/hr   $531.25
Cut & Prep        11.0 hrs   $125/hr  $1,378.75
Fit & Tack         5.3 hrs   $125/hr   $663.75
Full Weld         11.8 hrs   $125/hr  $1,473.75
Grind & Clean      6.8 hrs   $125/hr   $847.50
Finish Prep        1.0 hrs   $125/hr   $125.00
Paint              6.5 hrs   $125/hr   $810.00
Hardware Install   2.0 hrs   $125/hr   $250.00
Site Install      12.0 hrs   $145/hr  $1,740.00
Final Inspection   0.5 hrs   $125/hr    $62.50
Labor Subtotal: $7,882.50
```

---

## ✅ WHAT'S RIGHT (DO NOT BREAK THESE)

These things are working correctly. Do not change the code that produces them:

1. **Gate posts are `sq_tube_4x4_11ga`** — no more pipe/tube confusion from CS-2026-0036
2. **No duplicate gate posts** — only 3 posts, one material entry. The post dedup fix worked.
3. **Fab sequence says "18.0 ft" gate** — no more 27' hallucination. The enforced dimensions fix worked.
4. **Surface prep solvent in consumables** — new addition, present and priced
5. **Post length = 164"** (122" above grade + 42" Chicago frost line embed) — consistent everywhere
6. **Picket material = sq_bar_0.625** — consistent across gate and both fence sections
7. **Pre-punched mid-rail channels on fence** — correctly specified
8. **"Do NOT grind welds flush or smooth"** in fab sequence Step 6 — correct language
9. **MIG/GMAW for all shop fab** — correct
10. **Site install at $145/hr, shop at $125/hr** — correct rate split
11. **Primer and paint as separate steps** (Steps 8 and 9) — correct
12. **Hardware**: 2 roller carriages, 2 gate stops, 1 gravity latch — correct
13. **Fence posts**: 2 per side, `sq_tube_4x4_11ga`, 164" — correct
14. **Fence rails**: 3 per side (top, bottom, mid) — correct
15. **Fence mid-rails**: 2 pre-punched channels per side — correct for 10' height

## 🔴 WHAT'S BROKEN NOW (introduced by Prompt 28 changes)

### Bug A: Gate frame is aggregated into 5 monster pieces instead of individual cuts

**Symptom**: Cut list shows `Gate frame - 2x2 11ga, 806.4" × 5, miter_45`. 806.4" = 67.2 feet per piece. Stock comes in 20' or 24' sticks. You can't cut a 67-foot piece. This is not a cut list — it's a material summary pretending to be a cut list.

**What it should be**: Individual pieces a fabricator can actually cut:
```
Gate frame - top rail           sq_tube_2x2_11ga   216"   1   square    (18' gate length)
Gate frame - bottom rail        sq_tube_2x2_11ga   216"   1   square    (18' gate length)
Gate frame - leading stile      sq_tube_2x2_11ga   116"   1   square    (10' height minus rail widths)
Gate frame - trailing stile     sq_tube_2x2_11ga   116"   1   square    (tail end vertical)
Gate frame - mid-rail           sq_tube_2x2_11ga   216"   2   square    (horizontal stiffeners)
Gate frame - diagonal brace     sq_tube_2x2_11ga   ~185"  1   miter_45  (counterbalance zone)
Gate frame - diagonal brace     sq_tube_2x2_11ga   ~136"  1   miter_45  (opening zone)
```

**What likely happened**: When you simplified the post-processor, the AI prompt constraints that told Claude to generate piece-by-piece cut lists may have been loosened or the prompt itself changed. Claude is now aggregating/lumping material into bulk quantities instead of cutting individual pieces.

**Where to look**:
- `backend/calculators/ai_cut_list.py` — the `_build_cut_list_prompt()` method. Check if the prompt still explicitly requires individual cuttable pieces with max length of 240" (20' stock). If this language was removed or weakened, restore it.
- The JSON schema in the prompt should require `piece_name` and `group` fields that force Claude to name each individual piece.
- Add this rule to the cut list prompt if not already there:
  ```
  CRITICAL: Every line in the cut list must be a SINGLE CUTTABLE PIECE that fits within standard
  stock lengths (max 240" / 20 ft). Do NOT aggregate multiple pieces into one line. Do NOT report
  total linear footage as a "length" — report the actual cut length of ONE piece with the quantity
  showing how many of that piece to cut. A fabricator reads this cut list at the chop saw — each
  line = one stop on the saw fence.
  ```

### Bug B: Detailed cut list is just a copy of the materials list

**Symptom**: The "Detailed Cut List" section on the PDF is identical to the "Cut List" section. No individual piece breakdown.

**What it should be**: The detailed cut list should show every individual piece with its name, profile, exact length, quantity, cut type, and fabrication notes. This is what CS-2026-0036 had (and it was correct):
```
Gate frame - top rail, full 18ft     sq_tube_2x2_11ga   216"   1   square
Gate frame - bottom rail, full 18ft  sq_tube_2x2_11ga   216"   1   square
Gate frame - vertical end stile      sq_tube_2x2_11ga   116"   1   square
Gate frame - vertical end stile      sq_tube_2x2_11ga   116"   1   square
Gate frame - mid-rail horizontal     sq_tube_2x2_11ga   216"   2   square
Gate frame - diagonal brace          sq_tube_2x2_11ga   185"   1   miter_45
Gate frame - diagonal brace          sq_tube_2x2_11ga   136"   1   miter_45
Gate picket - 5/8in sq bar           sq_bar_0.625       116"  35   square
Gate picket - 5/8in sq bar (tail)    sq_bar_0.625       116"  17   square
```

**Where to look**:
- `backend/routers/quote_session.py` — around line 495: `current_params["_detailed_cut_list"] = material_list.get("cut_list", material_list.get("items", []))`. If `cut_list` is empty or missing, it falls back to `items` (the materials list). Check whether the AI is still populating the `cut_list` key in its response.
- `backend/calculators/base.py` — `_build_from_ai_cuts()` — check what it returns and whether `cut_list` is a separate key from `items`.

### Bug C: Overhead beam qty = 2 (should be 1)

**Symptom**: `Overhead support beam - HSS 6×4×1/4, hss_6x4_0.25, qty 2, $494.40`. Should be qty 1.

**This was also broken in CS-2026-0036.** The post-processor used to try to dedup this but the keyword check failed. Now with the simplified post-processor, it's not even trying.

**The fix needs to happen in TWO places:**

1. **AI prompt** (`_build_cut_list_prompt()` in `ai_cut_list.py`): Add an explicit constraint:
   ```
   OVERHEAD BEAM: For top-hung cantilever gates, there is exactly ONE (1) overhead support beam.
   It spans the full gate panel length plus 24" overhang (12" each side). Never qty 2.
   For residential gates under 800 lbs estimated weight, use hss_4x4_0.25.
   For heavy commercial gates over 800 lbs, use hss_6x4_0.25.
   ```

2. **Post-processor** (`_post_process_ai_result()` in `cantilever_gate.py`): In the simplified safety-net check for overhead beam, enforce qty=1. If the AI returned qty=2, correct it to qty=1:
   ```python
   # Find overhead beam items (by HSS profile or by keyword)
   for item in items:
       profile = item.get("profile", "")
       desc_lower = item.get("description", "").lower()
       if profile.startswith("hss_") or "overhead" in desc_lower or "support beam" in desc_lower:
           if item.get("quantity", 1) > 1:
               item["quantity"] = 1
               assumptions.append("Overhead beam quantity corrected to 1 (one beam spans full gate length).")
   ```

### Bug D: Gate picket count = 39 (should be ~54)

**Symptom**: Only 39 gate pickets for an 18' (216") gate at 4" on-center spacing.

**Correct calculation**: `216" / 4" + 1 = 55 pickets` (+ 1 for the end picket). Even accounting for the leading and trailing stiles taking up ~4" total, it should be ~53-54 pickets minimum.

39 pickets at 4" OC would only cover `(39-1) × 4" = 152" = 12.67'` — that's roughly the 12' opening, not the full 18' panel. Claude counted pickets for the opening instead of the full panel (opening + counterbalance tail).

**The fix**: In the AI cut list prompt, add:
```
GATE PICKET COUNT: Pickets span the FULL gate panel length (opening × 1.5), NOT just the
opening width. A 12' opening with 1.5× ratio = 18' panel = 216". At 4" OC spacing:
216 / 4 + 1 = 55 pickets. The counterbalance tail section gets pickets too — it's visible
when the gate is closed.
```

Also, the post-processor safety net should validate:
```python
# Validate gate picket count
expected_picket_count = math.ceil(total_gate_length_in / infill_spacing_in) + 1
for item in items:
    if "picket" in item.get("description", "").lower() and "fence" not in item.get("description", "").lower():
        if item.get("quantity", 0) < expected_picket_count * 0.8:  # more than 20% short
            assumptions.append(
                "WARNING: Gate picket count (%d) may be low. Expected ~%d for %.0f\" panel at %.0f\" spacing."
                % (item.get("quantity", 0), expected_picket_count, total_gate_length_in, infill_spacing_in))
```

## 🟡 STILL BROKEN FROM BEFORE (not fixed by Prompt 28)

### Bug E: Fence picket description/qty mismatch

**Symptom**: Side 1 description says "46 pcs" but qty column says 49. Side 2 says "40 pcs" but qty is 42.

**Root cause**: `_generate_fence_sections()` in `cantilever_gate.py` calculates picket count (e.g., 46), then passes it through `apply_waste(46, 0.05)` = `ceil(48.3)` = 49 for the material quantity. The description uses the pre-waste count, the qty uses the post-waste count.

**Fix**: Either:
- (a) Show the waste-adjusted count in the description: `"Fence pickets — Side 1 × 49 pcs (46 + 5% waste)"`
- (b) Or use the same number in both places and note waste separately in assumptions

Choose (a) — it's clearer for the fabricator:
```python
raw_count = math.ceil(length_in / infill_spacing_in) + 1
qty_with_waste = self.apply_waste(raw_count, self.WASTE_TUBE)

items.append(self.make_material_item(
    description=f"Fence pickets — {side_name} × {qty_with_waste} pcs ({raw_count} + {int(self.WASTE_TUBE * 100)}% waste)",
    ...
    quantity=qty_with_waste,
    ...
))
```

### Bug F: Overhead beam profile should be hss_4x4_0.25 for residential

**Symptom**: Quote shows `hss_6x4_0.25` ($240/ea). For a residential gate under 800 lbs, it should be `hss_4x4_0.25` (~$190).

**Root cause**: The post-processor has logic to select beam profile based on weight (under 800 lbs = 4×4, over = 6×4), but if the AI already generated the beam with the wrong profile and the simplified post-processor no longer overrides it, the wrong profile sticks.

**Fix**: The AI prompt constraint (see Bug C fix above) should specify `hss_4x4_0.25` for residential. The post-processor safety net should also validate:
```python
# Validate beam profile matches weight class
if estimated_gate_weight < 800:
    correct_profile = "hss_4x4_0.25"
else:
    correct_profile = "hss_6x4_0.25"

for item in items:
    if item.get("profile", "").startswith("hss_"):
        if item["profile"] != correct_profile:
            old = item["profile"]
            item["profile"] = correct_profile
            item["unit_price"] = round(beam_length_ft * lookup.get_price_per_foot(correct_profile), 2)
            assumptions.append("Beam profile corrected: %s → %s (estimated gate weight %.0f lbs)." % (old, correct_profile, estimated_gate_weight))
```

### Bug G: Fab sequence Step 8 says "degreaser" instead of "surface prep solvent"

**Symptom**: Step 8 says "Clean all fabricated steel with degreaser wipe-down before priming."

**What it should say**: "Wipe all fabricated steel with surface prep solvent and clean rags before priming."

**Fix**: In `BANNED_TERM_REPLACEMENTS` in `ai_cut_list.py`, add:
```python
"degreaser": "surface prep solvent",
"degreaser wipe-down": "surface prep solvent wipe-down",
"degreaser spray": "surface prep solvent",
```

Or better yet, add this to the fab sequence prompt rules:
```
PRE-PAINT WIPE: Before priming, wipe all steel with surface prep solvent and clean rags.
Do NOT say "degreaser" — the product is surface prep solvent. It removes oils, dust, and
contaminants before primer application.
```

## Decomposition (execution order)

1. **Fix AI cut list prompt** — add rules for individual cuttable pieces (max 240"), overhead beam qty=1 + profile selection, gate picket count spanning full panel, surface prep solvent language
2. **Fix detailed cut list population** — verify `cut_list` key is being returned by AI and stored separately from `items`
3. **Add safety-net checks to post-processor** — beam qty=1 enforcement, beam profile validation, gate picket count validation (warn if >20% low)
4. **Fix fence picket description/qty mismatch** — show waste-adjusted count in description
5. **Add banned terms** — "degreaser" → "surface prep solvent"
6. **Verify nothing from the ✅ list broke** — run the grep/import checks from Prompt 28

## Evaluation Design

### Grep checks:
```bash
# Verify cut list prompt has max length constraint:
grep -n "240\|max.*stock\|cuttable\|chop saw" backend/calculators/ai_cut_list.py | head -10

# Verify overhead beam qty enforcement exists:
grep -n "quantity.*1\|qty.*1\|beam.*one\|ONE.*beam" backend/calculators/cantilever_gate.py | head -10

# Verify gate picket count validation exists:
grep -n "expected_picket_count\|picket.*count\|picket.*low" backend/calculators/cantilever_gate.py | head -5

# Verify surface prep solvent in banned terms or prompt:
grep -n "degreaser\|surface prep solvent" backend/calculators/ai_cut_list.py | head -5

# Verify detailed cut list storage:
grep -n "_detailed_cut_list\|cut_list" backend/routers/quote_session.py | head -10
```

### Runtime verification:
```bash
cd backend && python -c "from calculators.cantilever_gate import CantileverGateCalculator; print('cantilever OK')"
cd backend && python -c "from calculators.ai_cut_list import AICutListGenerator; print('ai_cut_list OK')"
```
