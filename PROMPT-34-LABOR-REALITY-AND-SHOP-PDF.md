# PROMPT 34 — Labor Reality Check: Batch Cuts, Outdoor Grind & Shop PDF Materials

## 1. Problem Statement

The labor calculator treats every piece as individually handled, ignoring batch operations. This produces absurd hours:

- **Cut & Prep: 13 hrs** for mostly chop saw cuts. Formula: `total_pieces × 4 min`. 127 identical pickets × 4 min = 508 min (8.5 hrs). Reality: batch-cut pickets on a chop saw with one fence stop = 45 min for all 127.
- **Grind & Clean: 7.1 hrs** for outdoor painted steel. Formula: `type_b_joints × 1 min + type_a_joints × 2 min + 15`. 127 pickets × 2 joints × 1 min = 254 min just from pickets. Reality: outdoor painted = cleanup only (spatter, sharp edges, high spots). One pass down each face of the assembly with a flap disc. Maybe 1.5-2 hrs total.

NOTE: The shop PDF materials section needs to be aggregated by profile (see AC-3). The per-piece detail lives in the CUT LIST section. The Stock Order Summary is a bonus section, keep it where it is.

## 2. Acceptance Criteria

### AC-1: Cut & Prep uses batch logic for identical pieces
- Identical pieces (same profile + same length + same cut type) are cut in batches
- First piece in a batch: 4 min (measure, set fence stop)
- Each additional identical piece: 0.5 min (just feed and cut)
- Miter cuts still add 2 min per piece (not per batch)
- Test: 127 pickets at 118" square cut = 4 + (126 × 0.5) = 67 min, NOT 508 min
- Test: 2 diagonal braces at different lengths = 2 × 4 = 8 min (not batched — different lengths)

### AC-2: Grind hours reflect outdoor painted reality
- **Outdoor painted finish**: grind_clean = flat rate based on project scale, NOT per-joint
  - Small project (≤ 30 pieces): 1.0 hr
  - Medium project (31-100 pieces): 1.5 hr
  - Large project (101-200 pieces): 2.0 hr
  - XL project (200+ pieces): 2.5 hr
  - Add 0.5 hr if any miter joints exist (weld cleanup at miters is more involved)
  - Add 1.5 hr if mill scale removal needed (unchanged)
- **Indoor/furniture/bare metal**: keep existing per-joint formula (these DO get ground smooth)
- The punched_channel grind fix from P33 is now unnecessary for outdoor — remove that conditional or let it be overridden by the flat rate
- Reasoning line must explain which path was taken

### AC-3: Shop PDF Materials Section — Aggregated by Profile
The shop PDF MATERIALS section currently shows 28 individual pieces with individual prices. This is useless for a shop copy — the guy in the shop doesn't need to know each picket costs $4.12. He needs to know "order 11 sticks of 2x2x11ga."

Replace the per-piece materials table with a profile-aggregated summary:

| Profile | Description | Total Footage | Sticks Needed | Stock Length | Est. Weight | Total Cost |
|---------|-------------|---------------|---------------|--------------|-------------|------------|
| sq_tube_2x2_11ga | 2"×2"×11ga Square Tube | 187.4 ft | 10 | 20 ft | 561 lbs | $1,247.80 |
| sq_bar_0.625 | 5/8" Square Bar | 42.1 ft | 3 | 20 ft | 55 lbs | $189.45 |
| ... | ... | ... | ... | ... | ... | ... |

Rules:
- Group all pieces by profile (sq_tube_2x2_11ga, sq_bar_0.625, etc.)
- Show total linear footage per profile (sum of all piece lengths in that profile)
- Show sticks needed: `ceil(total_ft / stock_length_ft)`
- Show estimated weight: `WEIGHT_PER_FOOT × total_footage` (pull from material catalog)
- Show total material cost: sum of all `line_total` values for that profile
- **Plates/sheets**: show as "X pcs" in the Total Footage column, not linear footage
- **Concrete**: show as a separate summary line BELOW the steel table (not in the steel table)
- The per-piece detail ALREADY exists in the CUT LIST section — do not duplicate it here
- Stock Order Summary section stays as bonus below (shows remainder/leftover per profile)
- **Material subtotal must remain mathematically identical** — this is aggregation only, not recalculation
- Test: sum of all Total Cost values in aggregated table must equal the existing material_subtotal to the penny

## 3. Constraint Architecture

### Files to modify:

**`backend/calculators/labor_calculator.py`**
- Line ~278: Replace `total_pieces * 4` with batch-aware cut time calculation
- Lines ~229-233: Replace per-joint outdoor grind with flat rate by project scale
- The punched_channel grind fix block (lines 298-310) can stay but will be moot for outdoor painted — the flat rate overrides it

**`backend/pdf_generator.py`** lines ~430-453
- Replace the per-piece materials loop with profile-aggregated table
- Add weight column using `weight_lbs` from aggregated materials data
- Render plates/sheets as "X pcs" not linear footage
- Render concrete as separate summary line below the steel table
- Keep Stock Order Summary section below as-is

**`backend/pricing_engine.py`** `_aggregate_materials()` method
- Add `weight_lbs` field to each aggregated profile group
- Calculate as: `WEIGHT_PER_FOOT[profile] × total_linear_feet`
- Source weight data from the material catalog constants
- Return aggregated list grouped by profile with: total_ft, sticks_needed, stock_length, weight_lbs, total_cost

### Files NOT to modify:
- `ai_cut_list.py` — cut list generation is fine
- `pdf.py` router — no endpoint changes
- `frontend/` — frontend materials display is fine
- Client PDF — already uses scope summary, not per-piece

### Hard rules:
- Python 3.9 — no `str | None`
- Don't break the per-piece data in `priced_quote["materials"]` — other code depends on it
- Material subtotal must stay mathematically identical
- All existing tests must pass

## 4. Decomposition

### Step 1: Batch-aware cut time (labor_calculator.py)
```python
# Group cut_list by (profile, length, cut_type) to find batches
batches = {}
for item in cut_list:
    key = (item.get("profile", ""), item.get("length_inches", 0), 
           item.get("cut_type", "square"))
    qty = int(item.get("quantity", 1))
    batches[key] = batches.get(key, 0) + qty

cut_min = 0
for (profile, length, cut_type), batch_qty in batches.items():
    first_piece = 4  # measure, set stop, cut
    additional = (batch_qty - 1) * 0.5  # feed and cut
    miter_extra = batch_qty * 2 if cut_type in ("miter_45", "miter_22.5", "compound") else 0
    cut_min += first_piece + additional + miter_extra
```

### Step 2: Flat-rate outdoor grind (labor_calculator.py)
Replace lines 229-233 with:
```python
if is_outdoor:
    # Outdoor painted: cleanup pass only — not per-joint grinding
    if total_pieces <= 30:
        grind_clean = 1.0
    elif total_pieces <= 100:
        grind_clean = 1.5
    elif total_pieces <= 200:
        grind_clean = 2.0
    else:
        grind_clean = 2.5
    if miter_cuts > 0:
        grind_clean += 0.5
    if needs_mill_scale:
        grind_clean += 1.5
    grind_label = "outdoor cleanup (flat rate)"
else:
    # Indoor: keep per-joint formula
    grind_min = type_a_joints * 6 + type_b_joints * 3 + 30
    grind_clean = max(0.5, grind_min / 60.0)
    grind_label = "indoor full grind"
```

### Step 3: Tests
- Test batch cut time: 127 identical pieces = 67 min, not 508
- Test outdoor grind: 160 pieces = 2.0 hr, not 7.1
- Test indoor grind: still uses per-joint formula
- Test _aggregate_materials() returns weight_lbs per profile
- Test shop PDF materials section shows profile-aggregated rows, not 28 per-piece lines
- Test aggregated total cost equals material_subtotal to the penny
- Test plates/sheets show as "X pcs" not linear footage
- Test concrete appears below steel table, not inside it

## 5. Evaluation Design

### Verify cut time:
```python
# 127 pickets + 9 frame pieces + 8 fence rails + 7 posts + 2 braces + plates
# Pickets: 4 + 126*0.5 = 67 min (was 508)
# Frame: ~9 batches × 4 min = 36 min  
# Expected: ~2-3 hrs cut prep, NOT 13
```

### Verify grind:
```python
# Outdoor, ~160 pieces, has miters, needs mill scale
# Expected: 2.0 + 0.5 + 1.5 = 4.0 hrs (was 7.1)
# Without mill scale: 2.0 + 0.5 = 2.5 hrs
```

### Verify materials aggregation:
```python
# Shop PDF should show ~6-8 profile rows, NOT 28 per-piece rows
# Each row: profile, description, total_ft, sticks_needed, stock_length, weight_lbs, total_cost
# Sum of total_cost column must == material_subtotal (to the penny)
# Plates: "2 pcs" not "4.5 ft"
# Concrete: separate line below table
```

### Run full test suite:
```bash
pytest tests/ -v
```
