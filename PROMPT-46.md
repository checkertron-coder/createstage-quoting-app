# PROMPT-46: Trust Opus on Sheets — Remove Broken Aggregation

## Context
Our Python `_aggregate_materials()` is BREAKING Opus's output for sheet/plate items. It:
- Returns `stock_length_ft: 0` for all sheets (can't display sizes)
- Divides by 32 sqft (hardcoded 4×8 assumption) regardless of actual piece dimensions
- Results in a smaller sign costing MORE than a bigger sign — completely backwards

**The fix is NOT more Python math. The fix is letting Opus tell us what to order.**

Opus already knows standard sheet sizes (48×96, 48×120, 48×144, 60×120, 60×144). Opus already knows a 28×138" panel needs a 4'×12' sheet. We just never asked it to output that information, then our dumb Python mangled the numbers.

## Spec (Nate B. Jones 5 Primitives)

### 1. Inputs
- AI cut list response from Opus (already works)
- New fields Opus will output for sheet/plate items: `sheet_stock_size`, `sheets_needed`, `width_inches`

### 2. Outputs
- Materials summary shows REAL sheet sizes from Opus (e.g., "2 × 4'×12'")
- Sheet cost based on Opus's sheet count × price per sheet
- Seaming flag when Opus says a piece exceeds all standard sheets
- Laser perimeter calculated from `width_inches × length_inches` geometry — NOT hallucinated separately

### 3. Behavior

**A. Modify AI cut list prompt** (`ai_cut_list.py` `_build_prompt`):
Add to the prompt schema and rules:
```
For sheet/plate items, you MUST also include:
- "width_inches": the WIDTH of the piece (not just length)
- "sheet_stock_size": [W, H] — the standard sheet to order from. Options: [48,96], [48,120], [48,144], [60,120], [60,144]
  Pick the SMALLEST standard sheet where BOTH piece dimensions fit (piece can be rotated).
  If NO standard sheet fits, use the largest [60,144] and set "seaming_required": true
- "sheets_needed": how many of that stock sheet this piece requires (usually 1 per piece, but if cutting multiple small pieces from one sheet, group them)
```

Add `width_inches` to the JSON example for a sheet item.

**B. Pass through Opus's sheet data** (`base.py` `_build_from_ai_cuts`):
- For sheet/plate items, read `width_inches`, `sheet_stock_size`, `sheets_needed`, `seaming_required` from the AI response
- Store these on the material item dict (pass through, don't recalculate)
- Calculate laser perimeter deterministically: `2 * (width_inches + length_inches) * quantity` for box/panel pieces. Store as `laser_perimeter_inches`.
- Use `laser_perimeter_inches` for laser cost calculation INSTEAD of the current `sheet_perim_inches += length_in * qty * 2` hack

**C. Fix `_aggregate_materials`** (`pricing_engine.py`):
- For sheet/plate profile groups: read the `sheet_stock_size` and `sheets_needed` from the material items (Opus's data)
- Set `stock_length_ft` = sheet length / 12 (so PDF display works)
- Add `sheet_size`, `sheets_needed`, `seaming_required` to the aggregated result
- DO NOT calculate sheet count from sqft/32 anymore — use Opus's number
- For cost: `sheets_needed × sheet_sqft × price_per_sqft`

**D. Fix PDF display** (`pdf_generator.py`):
- Replace `_fmt_sheet_dims()` with logic that reads `sheet_size` from the material summary
- Display as: "2 × 4'×12'" or "1 × 5'×10'" or "3 × 4'×8' ⚠️SEAM"
- For `is_area_sold` items WITH `sheet_size`: show `sheets_needed × WxH`
- For `is_area_sold` items WITHOUT `sheet_size` (legacy/fallback): show `"N pcs"` as before

**E. Validation** (`ai_cut_list.py` `_parse_response`):
- Add `width_inches` to parsed fields (default 0 for non-sheet items)
- Add `sheet_stock_size` (default None), `sheets_needed` (default 1), `seaming_required` (default False)
- Validate `sheet_stock_size` is one of the 5 valid options if present

### 4. Constraints
- DO NOT build a 2D nesting algorithm — Opus handles this
- DO NOT add new Python calculators for sheet math — we're REMOVING calculation, not adding
- DO NOT change behavior for non-sheet materials (tubes, bars, angles)
- ALL existing tests must pass
- If Opus omits sheet fields (older cached responses or test data), fall back to current behavior gracefully

### 5. Acceptance Criteria
- [ ] AI cut list prompt includes `width_inches`, `sheet_stock_size`, `sheets_needed` in schema for sheet items
- [ ] `_parse_response` reads and validates new sheet fields
- [ ] `_build_from_ai_cuts` passes through sheet data and calculates deterministic laser perimeter
- [ ] `_aggregate_materials` uses Opus's sheet data instead of sqft/32 math
- [ ] PDF shows real sheet sizes (e.g., "2 × 4'×10'")
- [ ] Seaming flagged when `seaming_required: true`
- [ ] Same LED sign at 24×120" costs LESS than at 28×138" (sanity check)
- [ ] Laser cost uses geometric perimeter, not AI-hallucinated number
- [ ] All existing tests pass
- [ ] Non-sheet materials unchanged

**F. Fix BOM↔Build mirror rule** (`ai_cut_list.py` `_build_instructions_prompt`):
- Add to the build instructions prompt rules: "Every hardware item in the BOM must be referenced in at least one build step. If a bolt is in the BOM, there must be a step that installs it. If a nut is in the BOM, the same step must reference it. Hardware without a matching build step will be flagged and removed."
- This makes Opus generate complete build sequences that reference ALL hardware, so the BOM validator stops orphaning valid items.

## Files to Modify
1. **`backend/calculators/ai_cut_list.py`** — Prompt schema + `_parse_response` validation + build instructions mirror rule
2. **`backend/calculators/base.py`** — `_build_from_ai_cuts` pass-through + deterministic laser perimeter
3. **`backend/pricing_engine.py`** — `_aggregate_materials` uses Opus's sheet data
4. **`backend/pdf_generator.py`** — Real sheet size display

## Standard Sheet Sizes (for the prompt)
```
[48, 96]   = 4'×8'
[48, 120]  = 4'×10'
[48, 144]  = 4'×12'
[60, 120]  = 5'×10'
[60, 144]  = 5'×12'
```
