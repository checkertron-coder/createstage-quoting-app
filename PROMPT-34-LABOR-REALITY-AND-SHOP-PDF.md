# PROMPT 34 — Labor Reality Check: Batch Cuts & Outdoor Grind

## 1. Problem Statement

The labor calculator treats every piece as individually handled, ignoring batch operations. This produces absurd hours:

- **Cut & Prep: 13 hrs** for mostly chop saw cuts. Formula: `total_pieces × 4 min`. 127 identical pickets × 4 min = 508 min (8.5 hrs). Reality: batch-cut pickets on a chop saw with one fence stop = 45 min for all 127.
- **Grind & Clean: 7.1 hrs** for outdoor painted steel. Formula: `type_b_joints × 1 min + type_a_joints × 2 min + 15`. 127 pickets × 2 joints × 1 min = 254 min just from pickets. Reality: outdoor painted = cleanup only (spatter, sharp edges, high spots). One pass down each face of the assembly with a flap disc. Maybe 1.5-2 hrs total.

NOTE: The shop PDF materials section is CORRECT showing per-piece detail — do NOT change it. The Stock Order Summary is a bonus section, keep it where it is.

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

### AC-3: Do NOT change the shop PDF materials section
The per-piece materials list is correct for the shop copy. Do not aggregate it. The Stock Order Summary section added in P33 stays as-is.

## 3. Constraint Architecture

### Files to modify:

**`backend/calculators/labor_calculator.py`**
- Line ~278: Replace `total_pieces * 4` with batch-aware cut time calculation
- Lines ~229-233: Replace per-joint outdoor grind with flat rate by project scale
- The punched_channel grind fix block (lines 298-310) can stay but will be moot for outdoor painted — the flat rate overrides it

**`backend/pdf_generator.py`** — NO CHANGES to materials section

**`backend/pricing_engine.py`** — NO CHANGES needed

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
- Test materials_summary includes cost data
- Test shop PDF has aggregated materials (no 28 per-piece lines)

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

### Run full test suite:
```bash
pytest tests/ -v
```
