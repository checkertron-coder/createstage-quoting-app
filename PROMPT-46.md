# PROMPT-46: Real Sheet Sizing — Stop Hallucinating Dimensions

## Context
The quoting app has no concept of real sheet sizes. Sheets are sold as 4'×8' (48×96"), 4'×10' (48×120"), or 5'×10' (60×120"). Our system:
1. AI cut list generates sheet pieces with `length_inches` but NO WIDTH — can't determine which sheet to buy
2. `_aggregate_materials()` returns `stock_length_ft: 0` for all sheets (knowledge/materials.py `get_stock_length` returns `None`)
3. PDF generator can't display sheet sizes because `stk_len` is always 0
4. LED sign calculator divides by 32 sqft (assumes 4×8) even when pieces are 138" long (won't fit on ANY 4×8)
5. Laser perimeter is hallucinated by AI — not calculated from actual piece geometry

The result: a 24×120" sign costs MORE than a 28×138" sign. Completely backwards.

## Spec (Nate B. Jones 5 Primitives)

### 1. Inputs
- AI cut list items with `profile` containing "sheet" or "plate"
- Each sheet piece has `length_inches` (existing) and needs `width_inches` (NEW)
- Standard sheet sizes (steel AND aluminum): `[(48, 96), (48, 120), (48, 144), (60, 120), (60, 144)]` — 4'×8', 4'×10', 4'×12', 5'×10', 5'×12'

### 2. Outputs
- Each sheet material line in `materials_summary` must show:
  - `sheet_size`: tuple like `(48, 120)` — the actual stock sheet to order
  - `sheets_needed`: integer — how many of that stock sheet
  - `stock_length_ft` populated (e.g., 10 for 4'×10') so PDF display works
- Cut list display shows piece dimensions (W×L) not just length
- `SEAMING_REQUIRED` flag when largest piece exceeds all standard sheet sizes
- Laser perimeter calculated from actual piece dimensions, NOT hallucinated

### 3. Behavior
- For each sheet/plate profile group, find the LARGEST piece (max of width, length)
- Select the SMALLEST standard sheet that fits: both piece dimensions must fit within sheet dimensions (pieces can be rotated)
- Count sheets needed by simple nesting: how many pieces fit on one sheet, divide total pieces
- If NO standard sheet fits the largest piece → set `seaming_required: True` and use the largest available sheet + flag it
- Laser perimeter for rectangular pieces = `2 × (width + length) × quantity` — deterministic, not AI-guessed
- For letter cutouts in signs: AI still estimates letter perimeter, but box perimeter is calculated

### 4. Constraints
- DO NOT change the AI cut list prompt to ask for "nesting" — just add `width_inches` to the output schema
- DO NOT create a complex 2D nesting algorithm — simple "how many fit" is fine for quoting
- DO NOT break existing non-sheet materials (tubes, bars, angles) — they keep working as-is
- ALL existing tests must pass
- The `_fmt_sheet_dims` function in pdf_generator.py must use real sheet sizes, not the broken threshold logic

### 5. Acceptance Criteria
- [ ] AI cut list prompt schema includes `width_inches` for all items (sheet items MUST populate it; non-sheet can be 0 or omitted)
- [ ] `_build_from_ai_cuts` in `base.py` tracks `width_inches` on sheet/plate items and passes it through to material items
- [ ] New function `select_sheet_size(pieces)` in `knowledge/materials.py`:
  - Input: list of `(width_in, length_in, qty)` tuples for one profile
  - Output: `{"sheet_size": (W, H), "sheets_needed": int, "seaming_required": bool}`
  - Logic: find smallest standard sheet where both dimensions fit (allow rotation), calculate count
- [ ] `_aggregate_materials` in `pricing_engine.py` calls `select_sheet_size` for sheet/plate groups and populates `stock_length_ft`, `sheet_size`, `sheets_needed`, `seaming_required`
- [ ] `_fmt_sheet_dims` in `pdf_generator.py` replaced with real sheet size display: shows "2 × 4'×10'" or "1 × 5'×10' ⚠️SEAM" etc.
- [ ] Sheet material cost based on actual sheet count × price per sheet (from sqft price × sheet sqft), not abstract area division
- [ ] Laser perimeter for box/panel pieces calculated as `2*(W+L)*qty` in `_build_from_ai_cuts`, stored as `laser_perimeter_inches` on the material item — used by laser cost calculation instead of AI-hallucinated perimeter
- [ ] Running the same LED sign at 24×120" vs 28×138" produces: smaller sign costs LESS in materials (not more)
- [ ] Materials table in PDF/UI shows actual sheet size (e.g., "al sheet 0.125 | 1 pcs | 5'×10' | ...")
- [ ] All existing tests pass

## Files to Modify
1. **`backend/calculators/ai_cut_list.py`** — Add `width_inches` to cut list prompt schema and JSON output format. Add to validation in `_parse_response`.
2. **`backend/calculators/base.py`** `_build_from_ai_cuts` — Track `width_inches` on items. Calculate laser perimeter for sheet items deterministically. Pass dimensions through to material items.
3. **`backend/knowledge/materials.py`** — Add `STANDARD_SHEET_SIZES` constant and `select_sheet_size()` function.
4. **`backend/pricing_engine.py`** `_aggregate_materials` — For sheet/plate groups, call `select_sheet_size`, populate `sheet_size`, `sheets_needed`, `stock_length_ft`, `seaming_required`.
5. **`backend/pdf_generator.py`** — Replace `_fmt_sheet_dims` with real sheet size display. Handle `seaming_required` flag with warning icon.

## Standard Sheet Sizes Reference
```python
STANDARD_SHEET_SIZES = [
    (48, 96),    # 4'×8' (most common)
    (48, 120),   # 4'×10'
    (48, 144),   # 4'×12'
    (60, 120),   # 5'×10'
    (60, 144),   # 5'×12'
]
```

## Example
A 28×138" LED sign box needs:
- Face panel: 28" × 138" → fits on 48×144" (4'×12') ✓
- Back panel: 28" × 138" → fits on 48×144" ✓
- Side strips: 6" × 138" → fits on 48×144" ✓
- End caps: 6" × 28" → fits on ANY standard sheet

A 24×120" LED sign box needs:
- Face panel: 24" × 120" → fits on 48×120" (4'×10') ✓
- Back panel: 24" × 120" → fits on 48×120" ✓
- Side strips: 6" × 120" → fits on 48×120" ✓

Result: 28×138" costs MORE (seaming + more material). 24×120" costs LESS (standard sheets, no seaming). **This is correct.**
