# CC Prompt 51: Fix Consumable Pricing, Routing & Tiering

## Context
After P49 and P50 landed, 4 quotes were re-run. Three bugs remain in the pricing engine — all in `backend/pricing_engine.py`. These are Python data-routing and pricing fixes. No Opus prompts, no frontend, no calculator logic changes.

## Bug 1: ALL consumables routed to shop_stock (consumable_subtotal always $0)

**File:** `backend/pricing_engine.py`, method `_tier_items()` (~line 860)

**Root cause:** The tiering logic checks `if cat == "consumable"` and moves those items to `shop_stock`. But EVERY consumable from Opus has `category: "consumable"` — so they ALL get moved. The `remaining_consumables` list is always empty. `consumable_subtotal` is always $0.

**Fix:** The tier logic should distinguish between:
- **Consumables** (job-specific, customer sees): filler rod, tungsten, concrete mix, solder, heat shrink, silicone sealant, cutting fluid, tack cloth, reducer, gloves
- **Shop stock** (shop overhead, separate line): welding wire spools, shielding gas, grinding/flap discs, roloc discs, wire wheels, acetone, primer, paint/clear coat, masking tape, anti-spatter tape, weatherstrip, wire, zip ties, VHB tape, cable mounts

The current `_SHOP_STOCK_KEYWORDS` (~line 803) are close but the tiering condition is wrong. Change the condition from:

```python
if cat == "consumable" or any(kw in desc for kw in self._SHOP_STOCK_KEYWORDS):
```

to:

```python
if any(kw in desc for kw in self._SHOP_STOCK_KEYWORDS):
```

Remove the `cat == "consumable"` check entirely. Let ONLY the keyword match drive the split. Items that don't match any shop stock keyword stay in `consumables`.

Also update `_SHOP_STOCK_KEYWORDS` to be more precise — add these keywords that ARE shop stock:
- `"anti-spatter"`, `"weatherstrip"`, `"gasket"`, `"cable mount"`, `"zip tie"`, `"wire loom"`, `"vhb"`, `"foam tape"`, `"scotch-brite"`, `"roloc"`

And REMOVE `"welding"` from the keyword list — it's too broad and catches job-specific items like "welding blanket" or "welding rod" that should stay in consumables. The specific welding shop stock items (wire, gas, discs) are already caught by their own keywords.

## Bug 2: $0 prices on consumables (loanDepot quote #116)

**File:** `backend/pricing_engine.py`, full package path (~line 74-80)

**Root cause:** When Opus returns `unit_price: 0` for consumables, the code trusts it blindly:
```python
unit_price = float(item.get("unit_price", 0) or 0)
item["line_total"] = round(qty * unit_price, 2)
```

The `_validate_consumable_prices()` method exists (~line 381) with a good fallback price table, but it's NEVER CALLED anywhere.

**Fix:** Call `_validate_consumable_prices()` on the consumables list AFTER building it, in BOTH paths:

1. In the full package path (after the for loop at ~line 80), add:
```python
consumables = self._validate_consumable_prices(consumables)
```

2. In the legacy path (after consumables are built at ~line 165), add:
```python
consumables = self._validate_consumable_prices(consumables)
```

Also add these missing entries to `_CONSUMABLE_FALLBACK_PRICES` (~line 353):
```python
"tungsten": 3.00,        # per electrode
"filler rod": 18.00,     # per lb tube
"tack cloth": 2.00,
"solder": 8.00,
"flux": 6.00,
"silicone": 8.00,
"sealant": 8.00,
"heat shrink": 10.00,
"nitrile": 12.00,        # box of gloves
"gloves": 12.00,
"cutting fluid": 8.00,
"reducer": 18.00,        # paint reducer
"rags": 6.00,
"lint-free": 6.00,
```

## Bug 3: shop_stock_subtotal not including $0 items in total

**File:** `backend/pricing_engine.py`, method `_calculate_shop_stock_subtotal()` (~line 900)

**Root cause:** After Bug 1 routes items to shop_stock, some have $0 prices (from Bug 2). The subtotal sums these zeros faithfully. With Bug 2 fixed, this resolves itself — but verify that `_validate_consumable_prices` is called BEFORE `_tier_items` so both arrays get validated prices.

**Execution order in `price_quote()` should be:**
1. Build consumables list (from Opus or legacy)
2. Call `_validate_consumable_prices(consumables)` — fixes $0 prices
3. Call `_tier_items(hardware, consumables)` — splits into tiers with correct prices
4. Calculate subtotals

## Verification

After making these changes, run the test suite:
```bash
cd /Users/CTron/createstage-quoting-app
python -m pytest tests/ -x -q 2>&1 | tail -20
```

Then verify with a mental trace:
- A consumable like "ER4043 filler rod" with `category: "consumable"` should stay in the `consumables` array (no shop stock keyword match)
- A consumable like "4.5in flap discs 60 grit" should move to `shop_stock` (matches "flap" and "disc" keywords)
- A consumable with `unit_price: 0` should get a fallback price before tiering
- `consumable_subtotal` should be > $0 when job-specific consumables exist
- `shop_stock_subtotal` should be > $0 when shop supplies exist

## Files to modify
- `backend/pricing_engine.py` — all 3 fixes are in this one file

## DO NOT modify
- Any calculator files
- Any Opus prompts
- Any frontend files
- The `_tier_items` return shape (hardware/consumables/shop_stock dict stays the same)
