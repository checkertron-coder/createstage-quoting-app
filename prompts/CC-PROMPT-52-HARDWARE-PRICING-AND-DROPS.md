# CC Prompt 52: Fix Hardware Pricing & Laser Cut Drop Reuse

Two remaining issues after P51 landed successfully.

## Bug 1: Hardware pricing — Opus returns lot/box prices as per-unit

**Problem:** Opus returns hardware like `{"description": "Stainless steel machine screws 1/4-20", "quantity": 40, "estimated_price": 25.00}` meaning "$25 for a box of 40 screws." But the pricing engine does `price × quantity = 25 × 40 = $1,000` — treating $25 as per-screw pricing. This inflated the loanDepot sign hardware from ~$200 to $2,018.

**Root cause:** The Opus prompt example shows `"quantity": 1, "estimated_price": 25.00` with no guidance on what `estimated_price` means. Opus sometimes returns per-unit prices and sometimes per-lot prices inconsistently.

**Fix — two parts:**

### Part A: Clarify the Opus prompt (ai_cut_list.py)

In `backend/calculators/ai_cut_list.py`, find the hardware example in the prompt template (~line 1490). Change:

```json
"hardware": [
    {"description": "Item name", "quantity": 1, "estimated_price": 25.00}
],
```

to:

```json
"hardware": [
    {"description": "Item name", "quantity": 1, "estimated_price": 25.00}
],
```

And add this instruction text right before or after the hardware JSON example:

```
HARDWARE PRICING RULES:
- estimated_price is ALWAYS the price PER UNIT (per single piece/item)
- For bulk items (screws, bolts, nuts, washers, rivets, cable ties, wire connectors): price is per PIECE, not per box/bag
  - Example: 40 machine screws at $0.50 each → quantity: 40, estimated_price: 0.50
  - NOT: quantity: 40, estimated_price: 25.00 (that's a box price)
- For kit items (gas lens kit, connector assortment): quantity: 1, estimated_price: kit price
- For rolls/spools (LED strip, wire, tape): quantity is number of rolls, estimated_price is per roll
```

### Part B: Add a sanity check in the pricing engine

In `backend/pricing_engine.py`, add a method `_validate_hardware_prices` and call it on the hardware list BEFORE `_calculate_hardware_subtotal`. This catches Opus mistakes:

```python
_HARDWARE_UNIT_PRICE_CAPS = {
    # Keywords → max reasonable per-unit price
    "screw": 2.00,
    "bolt": 5.00,
    "nut": 1.50,
    "washer": 1.00,
    "rivet": 0.50,
    "cable tie": 0.20,
    "zip tie": 0.20,
    "wire connector": 2.00,
    "cable clip": 1.50,
    "cable mount": 1.50,
    "wire nut": 0.50,
    "crimp": 1.00,
    "resistor": 0.50,
    "capacitor": 2.00,
}

def _validate_hardware_prices(self, hardware):
    """
    Catch Opus returning box/lot prices as per-unit for bulk fasteners.
    If quantity > 10 and per-unit price exceeds cap for that item type,
    assume Opus returned a lot price and divide by quantity.
    """
    for item in hardware:
        options = item.get("options", [])
        qty = item.get("quantity", 1)
        if qty <= 10 or not options:
            continue
        
        desc = str(item.get("description", "")).lower()
        for keyword, max_unit in self._HARDWARE_UNIT_PRICE_CAPS.items():
            if keyword in desc:
                for opt in options:
                    price = float(opt.get("price", 0))
                    if price > max_unit:
                        # Opus likely returned a lot/box price
                        opt["price"] = round(price / qty, 2)
                        opt["supplier"] = opt.get("supplier", "Estimated") + " (corrected from lot price)"
                break
    
    return hardware
```

Call it in `price_quote()` right before the `_dedup_hardware` call (~line 183):

```python
priced_hardware = self._validate_hardware_prices(priced_hardware)
priced_hardware = self._dedup_hardware(priced_hardware)
```

## Bug 2: Laser cut drops not reused — calculator buys separate sheets

**Problem:** When Opus describes a layered sign (like the Hacienda), the cut list correctly notes that raised layer elements "come from the laser cutouts of the face panel — NOT separate sheet." But the calculator sees `al_sheet_0.125` pieces with dimensions and allocates separate sheets for them anyway.

Example from Hacienda non-LED (#118):
- `face_base_layer`: 60×60, needs 1 sheet of 60×120 ✅
- `layer2_elements`: 60×30 — Opus notes say "these come from laser cutouts" but calculator still buys a 48×96 sheet
- `layer3_elements`: 30×24 — same issue, gets another 48×96 sheet
- Result: 3 sheets bought when 1 would suffice (face disc cutouts ARE the raised pieces)

**Root cause:** The calculator in `base.py` groups pieces by `(profile, sheet_stock_size)` and bins them. It has no concept of "this piece comes from the drop of another piece." Opus indicates this in notes text, but the calculator doesn't read notes.

**Fix:** Add a `from_drop` boolean field to cut list items. When `from_drop: true`, the piece is excluded from sheet area calculations (it comes from an existing cut).

### Part A: Update the Opus prompt to emit `from_drop`

In `backend/calculators/ai_cut_list.py`, add to the cut list item schema in the prompt:

After the existing fields in the cut list example, add:
```
"from_drop": false
```

And add this instruction:
```
CUT LIST DROP REUSE:
- When a piece is laser-cut FROM another piece (e.g., letter cutouts from a face panel, raised elements from base layer drops), set "from_drop": true
- from_drop pieces do NOT require purchasing additional sheet stock — they come from the waste/drop of another cut
- Only the parent piece (the sheet being cut) needs sheets_needed
- Example: A sign face panel is laser cut with letter openings. The letter pieces that fall out ARE the raised layer elements. The face panel needs 1 sheet. The letter pieces need 0 additional sheets (from_drop: true).
```

### Part B: Skip `from_drop` pieces in sheet area calculation

In `backend/calculators/base.py`, in the `_build_from_ai_cuts` method, where pieces are added to `profile_totals` for sheet area calculation (~line 340-395), add a check:

```python
# Skip from_drop pieces — they come from another cut's waste
if cut.get("from_drop", False):
    # Still add to cut list for display, but don't count toward sheet purchases
    # Add the cut_entry to the detailed list but skip area accumulation
    continue  # skip adding to profile_totals area
```

This should be placed AFTER the cut_entry is built and added to the detailed cut list, but BEFORE the piece is added to `profile_totals` for area/length accumulation. The piece still appears in the cut list and build instructions — it just doesn't trigger a sheet purchase.

**Important:** The `from_drop` field needs to flow through the parser too. In `_parse_full_package()` method (~line 1560-1610 in ai_cut_list.py), where cut list items are parsed, add:

```python
"from_drop": bool(item.get("from_drop", False)),
```

to the parsed cut entry dict.

## Verification

After both fixes, run the test suite:
```bash
cd /Users/CTron/createstage-quoting-app
python -m pytest tests/ -x -q 2>&1 | tail -20
```

Then mentally verify:
- loanDepot: 40 machine screws at $25 → corrected to $0.63/screw → $25 total (not $1,000)
- Hacienda non-LED: face panel = 1 sheet of 60×120. Layer 2/3 elements = from_drop, 0 additional sheets. Total: 1-2 sheets (face + back panel + side ring), not 3-4.
- Hacienda LED: same drop logic. Face disc cutouts are the raised elements.

## Files to modify
- `backend/calculators/ai_cut_list.py` — Opus prompt (hardware pricing rules + from_drop field + parser)
- `backend/calculators/base.py` — skip from_drop pieces in sheet accumulation
- `backend/pricing_engine.py` — hardware price validation

## DO NOT modify
- Frontend files
- Question tree / intake logic
- The consumable pricing/tiering from P51 (it's working correctly now)
