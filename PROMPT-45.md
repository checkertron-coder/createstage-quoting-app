# PROMPT 45 — "The Finish Line"

**Traced bugs with exact root causes. No guessing. Change these lines.**

---

## 1. Problem Statement

Three prompts (P42, P43, P44) tried to fix the finish pipeline. All failed because they rewrote logic without understanding the actual execution path. This prompt fixes 4 traced bugs with surgical changes.

**Bug A — "Raw Aluminum — $0" on every LED sign quote:**
The finish answer `"Brushed stainless (no coating)"` passes through `_normalize_finish_type()` in `backend/finishing.py`. The method checks `"no coating"` in the raw/no-finish block (line ~172) BEFORE checking `"brush"` in the brushed block (line ~204). Result: "raw" → $0.

**Bug B — "clear coat" extracts as "Powder coat":**
When Claude extracts `"clear coat"` from the description, `_match_option()` in `backend/question_trees/engine.py` does substring matching: `"coat"` appears in `"Powder coat (most common)"` → match. Customer says clear coat, gets powder coat pricing.

**Bug C — Extraction silently steals the user's chance to answer:**
The LED sign question tree has NO clear coat option. When Claude maps the customer's "clear coat" to the wrong option via fuzzy matching, the finish field appears "answered" → the question tree never asks the user → user never sees it → can't correct it.

**Bug D — Frontend subtotal doesn't update on user edits:**
`_recalcTotals()` in `frontend/js/quote-flow.js` (line ~1046) is missing `shop_stock_subtotal` in the sum. Also, the TABLE subtotal rows (inside each section) are static HTML — they render once and never update when quantities change.

---

## 2. Acceptance Criteria

- AC-1: `_normalize_finish_type("Brushed stainless (no coating)")` returns `"brushed"`, not `"raw"`
- AC-2: `_normalize_finish_type("Brushed aluminum (no coating)")` returns `"brushed"`, not `"raw"`
- AC-3: `_match_option("clear coat", led_sign_options)` does NOT return `"Powder coat (most common)"`
- AC-4: When extraction sets finish to a value that doesn't closely match any option, keep the raw value instead of dropping it — `_normalize_finish_type` handles free text
- AC-5: `_recalcTotals()` includes `shop_stock_subtotal` in the subtotal sum
- AC-6: Table subtotal rows update dynamically when user edits quantities
- AC-7: All 924+ existing tests pass
- AC-8: New tests verify AC-1 through AC-4

---

## 3. Constraint Architecture

- DO NOT rewrite `_normalize_finish_type` — just reorder the checks
- DO NOT modify question tree JSON files
- DO NOT add new AI calls
- DO NOT change the FinishingBuilder.build() method
- DO NOT touch labor, BOM validation, or tiering code
- Frontend changes: vanilla JS only, no new dependencies
- Keep changes minimal — this is 4 surgical fixes, not a refactor

---

## 4. Decomposition

### Fix A: Reorder `_normalize_finish_type()` in `backend/finishing.py`

**File:** `backend/finishing.py`, method `_normalize_finish_type` (~line 160-220)

**Current order (BROKEN):**
```python
# 1. raw/no-finish check (includes "no coating")  ← FIRST
# 2. clearcoat
# 3. powder coat
# 4. galvanized
# 5. anodized
# 6. ceramic
# 7. patina
# 8. brushed/polished/mirror  ← TOO LATE
# 9. paint
```

**New order (FIXED):**
```python
# 1. brushed/polished/mirror  ← MOVE UP (before raw check)
# 2. clearcoat
# 3. powder coat  
# 4. galvanized
# 5. anodized
# 6. ceramic
# 7. patina
# 8. paint
# 9. raw/no-finish check  ← MOVE TO LAST (catch-all for genuinely raw)
# 10. none check
```

**Why:** The raw check's `"no coating"` keyword matches inside `"Brushed stainless (no coating)"`. By checking brushed FIRST, the `"brush"` keyword matches before `"no coating"` ever gets checked. Moving raw to last makes it the true fallback — if nothing else matched, THEN it's raw.

**Also update the raw check** to exclude cases where another finish keyword is present:
```python
# Before the raw block, strip parenthetical notes
# "Brushed stainless (no coating)" → check "Brushed stainless" first
# Only fall through to raw if no other finish type keyword is found
```

Actually, the simpler fix: just reorder. The `any(k in f ...)` for brushed will match `"brush"` in `"Brushed stainless (no coating)"` before the raw block ever runs.

### Fix B + C: Smarter finish matching in `_normalize_extracted_fields()`

**File:** `backend/question_trees/engine.py`, function `_normalize_extracted_fields` (~line 561-600)

**Current behavior:** For choice fields, if the extracted value doesn't exactly match an option, it tries substring matching, reverse substring, then word overlap. For finish specifically, `"clear coat"` substring-matches `"Powder coat (most common)"` because `"coat"` is in both.

**Fix:** Add a special case for the `finish` field. If the matched option's normalized finish TYPE (via `_normalize_finish_type`) differs from the raw extraction's normalized finish type, keep the raw value instead. This lets `_normalize_finish_type` in pricing_engine.py handle the free text correctly.

```python
# In _normalize_extracted_fields, after the existing matching logic:
if field_id == "finish" and normalized is not None:
    # Verify the match preserves finish intent
    from ..finishing import FinishingBuilder
    fb = FinishingBuilder()
    raw_type = fb._normalize_finish_type(str(value))
    matched_type = fb._normalize_finish_type(normalized)
    if raw_type != matched_type and raw_type != "raw":
        # The match changed the finish type — keep raw value
        # _normalize_finish_type in pricing_engine will handle it
        result[field_id] = str(value)
        logger.info("Finish field: keeping raw '%s' (%s) over matched '%s' (%s)",
                     value, raw_type, normalized, matched_type)
        continue  # skip the normal assignment
```

Wait — there's a circular import risk here (`question_trees/engine.py` importing from `finishing.py`). Instead, do the check inline with a simple keyword overlap:

**Simpler approach:** For the `finish` field only, require that the matched option shares at least one SIGNIFICANT word (not just "coat", "finish", "steel", "aluminum") with the raw extraction:

```python
if field_id == "finish":
    # For finish, don't rely on loose substring matching
    # Only accept exact match or case-insensitive match
    # If those fail, keep the raw value — _normalize_finish_type handles free text
    exact = None
    val_lower = str(value).lower().strip()
    for opt in options:
        if opt.lower().strip() == val_lower:
            exact = opt
            break
    if exact:
        result[field_id] = exact
    else:
        # Keep the raw extraction — the finishing normalizer handles it
        result[field_id] = str(value)
        logger.info("Finish field: no exact match for '%s', keeping raw value", value)
    continue
```

This way:
- `"Powder coat (most common)"` typed by user → exact match → kept ✅
- `"clear coat"` extracted by Claude → no exact match → kept as `"clear coat"` → `_normalize_finish_type("clear coat")` → `"clearcoat"` ✅
- `"brushed"` extracted → no exact match → kept as `"brushed"` → `_normalize_finish_type("brushed")` → `"brushed"` ✅
- `"Painted (custom colors)"` selected by user → exact match → kept ✅

**Insert this BEFORE the existing matching logic** for the finish field, inside the `for field_id, value in extracted.items():` loop, right after the `if field_type in ("choice", "multi_choice") and options:` check.

### Fix D: Frontend subtotal refresh

**File:** `frontend/js/quote-flow.js`

**Fix D1:** Add `shop_stock_subtotal` to `_recalcTotals()` (~line 1055):

```javascript
// CURRENT:
pq.subtotal = Math.round((
    (pq.material_subtotal || 0) +
    (pq.hardware_subtotal || 0) +
    (pq.consumable_subtotal || 0) +
    pq.labor_subtotal +
    (pq.finishing_subtotal || 0)
) * 100) / 100;

// FIXED:
pq.subtotal = Math.round((
    (pq.material_subtotal || 0) +
    (pq.hardware_subtotal || 0) +
    (pq.consumable_subtotal || 0) +
    (pq.shop_stock_subtotal || 0) +
    pq.labor_subtotal +
    (pq.finishing_subtotal || 0)
) * 100) / 100;
```

**Fix D2:** Add shop stock subtotal display element. In the summary section (~line 576), add after consumables:
```javascript
<div class="total-row"><span>Shop Stock</span><span id="shop-stock-subtotal-amount">${this._fmt(pq.shop_stock_subtotal || 0)}</span></div>
```

And in `_recalcTotals()`, add update for the new element:
```javascript
const shopEl = document.getElementById('shop-stock-subtotal-amount');
if (shopEl) shopEl.textContent = this._fmt(pq.shop_stock_subtotal || 0);
```

**Fix D3:** Make TABLE subtotal rows update dynamically. Give each table subtotal cell an ID:

In the materials table subtotal row (~line 674-676):
```javascript
// CURRENT:
<td class="r"><strong>${this._fmt(pq.material_subtotal)}</strong></td>

// FIXED:
<td class="r"><strong id="mat-table-subtotal">${this._fmt(pq.material_subtotal)}</strong></td>
```

Do the same for hardware (~line 734-736), consumables (~line 761-763), and labor (~line 790-792) table subtotals. Use IDs: `hw-table-subtotal`, `con-table-subtotal`, `labor-table-subtotal`.

Then in `_recalcTotals()`, update them:
```javascript
const matTbl = document.getElementById('mat-table-subtotal');
const hwTbl = document.getElementById('hw-table-subtotal');
const conTbl = document.getElementById('con-table-subtotal');
const laborTbl = document.getElementById('labor-table-subtotal');
if (matTbl) matTbl.textContent = this._fmt(pq.material_subtotal);
if (hwTbl) hwTbl.textContent = this._fmt(pq.hardware_subtotal);
if (conTbl) conTbl.textContent = this._fmt(pq.consumable_subtotal);
if (laborTbl) laborTbl.textContent = this._fmt(pq.labor_subtotal);
```

---

## 5. Evaluation Design

### New Tests (`tests/test_prompt45.py`)

```
test_normalize_finish_brushed_no_coating → "Brushed stainless (no coating)" → "brushed" (NOT "raw")
test_normalize_finish_brushed_aluminum_no_coating → "Brushed aluminum (no coating)" → "brushed"
test_normalize_finish_clear_coat → "clear coat" → "clearcoat"
test_normalize_finish_raw_still_works → "raw" → "raw"
test_normalize_finish_no_finish → "no finish" → "raw"
test_normalize_finish_raw_steel → "Raw steel" → "raw"
test_normalize_finish_order_brushed_before_raw → verify brushed check runs before raw check
test_extraction_finish_keeps_raw_value → when extraction returns "clear coat" and LED sign tree has no match, fields["finish"] = "clear coat" (not dropped, not "Powder coat")
test_extraction_finish_exact_match_preserved → "Powder coat (most common)" exact match → kept as-is
```

### Verification Commands

```bash
# New tests
source .venv/bin/activate && pytest tests/test_prompt45.py -v

# Full suite
source .venv/bin/activate && pytest tests/ -v

# Manual finish check
python3 -c "
from backend.finishing import FinishingBuilder
fb = FinishingBuilder()
tests = [
    'Brushed stainless (no coating)',
    'Brushed aluminum (no coating)', 
    'clear coat',
    'clearcoat',
    'raw',
    'no finish',
    'Powder coat (most common)',
    'Paint (in-house)',
]
for t in tests:
    print(f'  {t!r:45s} → {fb._normalize_finish_type(t)!r}')
"

# App starts
python3 -c "from backend.main import app; print('App starts: OK')"
```

---

## Files Modified

| File | Change |
|------|--------|
| `backend/finishing.py` | Reorder `_normalize_finish_type` checks: brushed before raw (AC-1, AC-2) |
| `backend/question_trees/engine.py` | Finish field: exact match only, keep raw value on mismatch (AC-3, AC-4) |
| `frontend/js/quote-flow.js` | Shop stock in subtotal, dynamic table subtotals (AC-5, AC-6) |
| `tests/test_prompt45.py` | NEW — ~9 tests (AC-8) |

## Files NOT Modified

- Question tree JSON files (per constraint)
- `backend/pricing_engine.py` — no changes needed
- `backend/pdf_generator.py` — no changes needed
- `backend/hardware_sourcer.py` — no changes needed
- `backend/bom_validator.py` — no changes needed
