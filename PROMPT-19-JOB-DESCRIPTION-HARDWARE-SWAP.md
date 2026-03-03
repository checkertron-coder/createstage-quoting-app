# PROMPT 19 — Show Job Description, Fix Hardware Pipeline, Inline Material Swap

## INTEGRATION RULES (from CLAUDE.md)
Building a module is not done until it's CALLED in the pipeline. After any change, trace the full path from user input → AI generation → validation → PDF output. If your new code isn't in that path, it's not done. Verify with grep after every change.

---

## PROBLEM STATEMENT

Three distinct problems that collectively make the quoting app feel incomplete to a fabricator using it daily:

1. **The customer's job description is invisible on the final quote.** Burton types a detailed description ("36" wide x 72" tall single swing gate, flat bar decorative infill, raw steel clear coat finish") — that description exists in `inputs_json.fields.description` but is never rendered on the frontend quote view or prominently on the PDF. A fabricator looking at their own quote 2 weeks later can't remember what this quote was even for without scrolling through session history.

2. **Several calculators generate $0 hardware because they never populate the hardware list from question tree answers.** The swing_gate calculator does this correctly — it reads `fields.get("hinge_type")`, `fields.get("latch_type")`, etc. and generates hardware items with real pricing. But `custom_fab.py` and several others initialize `hardware = []` and return it empty. When question tree answers specify hardware (hinges, latches, motors, brackets), those answers are sitting in `params_json` but never reach the hardware sourcer.

3. **No inline material swap.** Burton's #1 feature request. When looking at a completed quote, he wants to tap a material line item and swap it (e.g., 1.5" square tube → 2" square tube, or 11 gauge → 14 gauge) and see the price recalculate instantly. This is the killer feature that makes this app actually useful in the field — Burton's standing with a customer, they ask "what if we go heavier gauge?" and he can show them the price difference in real time.

---

## ACCEPTANCE CRITERIA

### Issue 1: Job Description on Quote
- [ ] The frontend `_renderResults()` method displays the job description prominently at the top of the quote, right below the quote number and job type
- [ ] The description comes from `pq.job_description` (new field) OR falls back to `pq.fields.description` if available
- [ ] The `PricingEngine.build_priced_quote()` method includes `job_description` in the output dict, sourced from `fields.get("description", "")`
- [ ] The PDF already renders a job summary via `generate_job_summary()` — verify this is working and that the raw description text is also included (not just the generated summary)
- [ ] If no description exists, the section is simply not rendered (no empty boxes)

### Issue 2: Hardware from Question Tree Answers
- [ ] Create a new utility function `generate_hardware_from_fields(job_type: str, fields: dict) -> list[dict]` in `backend/calculators/base.py` (or a new `hardware_mapper.py`)
- [ ] This function maps common question tree field patterns to hardware items:
  - `hinge_type` + `hinge_count` → hinge hardware items with pricing from `HARDWARE_CATALOG`
  - `latch_type` → latch hardware item
  - `has_motor` + `motor_brand` + `motor_arm_type` → motor/operator hardware
  - `auto_close` → spring hinge or hydraulic closer
  - `center_stop` → drop rod / cane bolt
  - `post_cap_type` → post caps
  - `bracket_type` → mounting brackets
- [ ] Calculators that currently return `hardware = []` get a fallback call: `hardware = generate_hardware_from_fields(job_type, fields)` if their own hardware list is empty
- [ ] The swing_gate calculator is the REFERENCE IMPLEMENTATION — it already does this correctly. The new utility function should use the same lookup patterns
- [ ] Don't break calculators that already generate hardware — only fill in when hardware is empty
- [ ] After implementation, run a swing_gate quote and verify hardware is NOT duplicated (calculator's own hardware takes priority)

### Issue 3: Inline Material Swap
- [ ] Add a new backend endpoint: `POST /api/quotes/{quote_id}/swap-material`
  - Request body: `{ "item_index": int, "new_profile": str }` (or `"new_size"` / `"new_gauge"`)
  - The endpoint looks up the new profile in `material_lookup.py`, recalculates the line item price, updates `outputs_json.materials[item_index]`, recalculates all subtotals/totals, and returns the updated PricedQuote
  - Must also update the Quote record in the database (subtotal, total, outputs_json)
- [ ] Add a new backend endpoint: `GET /api/materials/alternatives?profile=HSS_2x2_11ga`
  - Returns a list of alternative profiles in the same category (e.g., all square tube options, or all flat bar options) with their unit prices
  - Uses `material_lookup.py`'s existing catalog to find alternatives by matching the profile category/shape
- [ ] Frontend: Each material row in `_renderMaterialsTable()` becomes tappable/clickable
  - Clicking opens a dropdown/modal showing alternative materials (from the `/alternatives` endpoint)
  - Selecting an alternative calls `/swap-material` and re-renders the results
  - Show the price delta ("+$45" or "-$120") next to each alternative so Burton can see the impact before selecting
- [ ] The swap must cascade: changing a material profile changes the line_total, which changes material_subtotal, which changes subtotal, which changes total (through markup). All displayed totals must update.
- [ ] The swap should NOT re-run Gemini or any AI calls — this is pure math on existing data

---

## CONSTRAINT ARCHITECTURE

### What NOT to Change
- Do NOT modify the question tree JSON files — they're correct as-is
- Do NOT change the `PricingEngine` core math — it's working
- Do NOT re-run AI/Gemini for material swaps — pure lookup + math only
- Do NOT change the `HardwareSourcer.price_hardware_list()` interface — it works fine, the problem is upstream (empty lists going in)
- Do NOT modify calculators that already generate hardware correctly (swing_gate, cantilever_gate, straight_railing, etc.) — only add the fallback for calculators that return empty hardware

### What to Be Careful With
- **Material swap and stock lengths:** When swapping a profile, the stock length may change (e.g., 1" square tube comes in 20' sticks, 2" comes in 24' sticks). Update `stock_length_ft` on the item if it changes.
- **Material swap and weight:** Swapping to a heavier gauge increases weight, which affects total_weight_lbs. Update it.
- **Material swap and weld inches:** Don't recalculate weld inches on swap — that's AI-generated and changes to weld volume from a gauge swap are negligible for quoting purposes.
- **Hardware fallback priority:** Calculator's own hardware list > fallback utility. Only call the fallback when `len(hardware) == 0` after the calculator runs.
- **Database writes on swap:** Use `flag_modified(quote, "outputs_json")` before `db.commit()` — SQLAlchemy won't detect JSON mutations otherwise.

### Performance Constraints
- `/alternatives` endpoint must be fast — pure in-memory lookup from the material catalog, no AI, no database
- `/swap-material` must return < 500ms — it's a single JSON mutation + database write
- Frontend dropdown should feel instant — prefetch alternatives when the user hovers/focuses on a material row

---

## DECOMPOSITION

### Step 1: Job Description Display (Backend)

In `backend/pricing_engine.py`, inside `build_priced_quote()`, after the `result = { ... }` dict is built (around line 127), add:

```python
# Include job description for display
job_description = fields.get("description", "")
if job_description:
    result["job_description"] = job_description
```

Verify: After this change, the `outputs_json` stored on the Quote record will include `job_description`. Check by running a quote and inspecting the API response at `GET /api/quotes/{id}`.

### Step 2: Job Description Display (Frontend)

In `frontend/js/quote-flow.js`, inside `_renderResults()` (line ~492), add a job description section right after the `results-header` div and before the validation warnings:

```javascript
${pq.job_description ? `
    <div class="job-description-section">
        <h3>Job Description</h3>
        <p class="job-description-text">${pq.job_description}</p>
    </div>
` : ''}
```

Add corresponding CSS in `frontend/css/` for `.job-description-section` — subtle background, left border accent, readable font size. Keep it clean and scannable.

### Step 3: Hardware Fallback Utility

Create `backend/calculators/hardware_mapper.py`:

```python
"""
Hardware Mapper — generates hardware items from question tree field answers.

This is the FALLBACK for calculators that don't generate their own hardware.
If a calculator already populates hardware (e.g., swing_gate.py), this is NOT called.

Maps common field patterns → HARDWARE_CATALOG keys → priced hardware items.
"""

from .material_lookup import MaterialLookup

# Field name → (catalog_key_resolver, description_template)
# The resolver takes the field value and returns a HARDWARE_CATALOG key
FIELD_HARDWARE_MAP = {
    "hinge_type": {
        "Heavy duty weld-on barrel hinges": "heavy_duty_weld_hinge_pair",
        "Bolt-on adjustable hinges": "standard_weld_hinge_pair",
        "Ball-bearing hinges": "ball_bearing_hinge_pair",
        "J-bolt hinges (wrap-around)": "standard_weld_hinge_pair",
    },
    "latch_type": {
        "Gravity latch (auto-closing)": "gravity_latch",
        "Gravity latch": "gravity_latch",
        "Magnetic latch": "magnetic_latch",
        "Keyed deadbolt": "keyed_deadbolt",
        "Pool code latch (self-closing, self-latching)": "pool_code_latch",
        "Electric strike (with motor)": "electric_strike",
    },
    "auto_close": {
        "Yes": "hydraulic_closer",
    },
}


def generate_hardware_from_fields(job_type: str, fields: dict) -> list:
    """
    Generate hardware items from question tree answers.

    Only call this when the calculator's own hardware list is empty.
    Returns a list of HardwareItem dicts ready for PricingEngine.
    """
    lookup = MaterialLookup()
    hardware = []

    # --- Hinges ---
    hinge_type = fields.get("hinge_type", "")
    if hinge_type and hinge_type != "Not sure — recommend based on gate weight":
        hinge_key = FIELD_HARDWARE_MAP.get("hinge_type", {}).get(hinge_type)
        if not hinge_key:
            # Fuzzy fallback: if they picked something, default to heavy duty
            hinge_key = "heavy_duty_weld_hinge_pair"

        # Determine quantity from hinge_count field
        hinge_count_raw = fields.get("hinge_count", "2")
        hinge_count = 2  # default
        for digit in ["2", "3", "4"]:
            if digit in str(hinge_count_raw):
                hinge_count = int(digit)
                break

        # Account for panel count (double gates = 2 panels)
        panel_config = fields.get("panel_config", "Single")
        num_panels = 2 if "Double" in str(panel_config) or "Bi-parting" in str(panel_config) else 1
        total_hinge_pairs = hinge_count * num_panels

        hardware.append({
            "description": f"Gate hinge — {hinge_type} ({hinge_count}/panel × {num_panels} panel{'s' if num_panels > 1 else ''})",
            "quantity": total_hinge_pairs,
            "options": lookup.get_hardware_options(hinge_key),
        })

    # --- Latch ---
    latch_type = fields.get("latch_type", "")
    if latch_type and latch_type != "None":
        latch_key = FIELD_HARDWARE_MAP.get("latch_type", {}).get(latch_type)
        if not latch_key:
            latch_key = "gravity_latch"  # safe default
        hardware.append({
            "description": f"Gate latch — {latch_type}",
            "quantity": 1,
            "options": lookup.get_hardware_options(latch_key),
        })

    # --- Center stop / drop rod ---
    center_stop = fields.get("center_stop", "")
    if "Yes" in str(center_stop) or "Drop" in str(center_stop):
        hardware.append({
            "description": "Center stop — drop rod / cane bolt",
            "quantity": 1,
            "options": lookup.get_hardware_options("drop_rod"),
        })

    # --- Auto-close ---
    auto_close = fields.get("auto_close", "")
    if "Yes" in str(auto_close):
        hardware.append({
            "description": "Hydraulic gate closer",
            "quantity": 1,
            "options": lookup.get_hardware_options("hydraulic_closer"),
        })

    # --- Motor / Operator ---
    has_motor = fields.get("has_motor", "")
    if "Yes" in str(has_motor):
        motor_brand = fields.get("motor_brand", "LiftMaster RSW12U (residential)")
        motor_key = _resolve_motor_key(motor_brand)
        hardware.append({
            "description": f"Gate operator — {motor_brand}",
            "quantity": 1,
            "options": lookup.get_hardware_options(motor_key),
        })

    return hardware


def _resolve_motor_key(motor_brand: str) -> str:
    """Map motor brand selection to HARDWARE_CATALOG key."""
    brand_lower = motor_brand.lower()
    if "rsw12" in brand_lower:
        return "liftmaster_rsw12u"
    elif "csw24" in brand_lower:
        return "liftmaster_csw24u"
    elif "patriot" in brand_lower:
        return "us_auto_patriot"
    elif "viking" in brand_lower:
        return "viking_e5"
    elif "doorking" in brand_lower:
        return "doorking_6050"
    else:
        return "liftmaster_rsw12u"  # safe residential default
```

**CRITICAL:** Several hardware keys above (magnetic_latch, keyed_deadbolt, pool_code_latch, electric_strike, drop_rod, hydraulic_closer, and all motor keys) may NOT exist in `HARDWARE_CATALOG` yet. Check `backend/calculators/material_lookup.py`'s `HARDWARE_CATALOG` dict and `backend/hardware_sourcer.py`'s `HARDWARE_PRICES` dict. Add entries for any missing keys with realistic Chicago-area pricing (3 suppliers: McMaster-Carr, Amazon, Grainger/specialty). Use the existing entries as the format template.

### Step 4: Wire Hardware Fallback into Calculators

In `backend/calculators/base.py`, add a method to `BaseCalculator`:

```python
def _apply_hardware_fallback(self, hardware: list, job_type: str, fields: dict) -> list:
    """
    If the calculator returned no hardware but question tree answers
    specify hardware items, generate them from field mappings.
    """
    if hardware:
        return hardware  # Calculator already generated hardware — don't override
    from .hardware_mapper import generate_hardware_from_fields
    return generate_hardware_from_fields(job_type, fields)
```

Then, in EVERY calculator that currently returns `hardware = []` without populating it, add a call before the `return self.make_material_list(...)`:

```python
hardware = self._apply_hardware_fallback(hardware, "job_type_here", fields)
```

The calculators that need this (verify each — grep for `hardware = []` followed by no `.append`):
- `custom_fab.py`
- `furniture_other.py` (may or may not need it — check)
- `structural_frame.py`
- `bollard.py`
- `repair_structural.py`
- `repair_decorative.py`
- `sign_frame.py`
- `led_sign_custom.py`
- Any others where `hardware` stays empty

**DO NOT add this to:** `swing_gate.py`, `cantilever_gate.py`, `straight_railing.py`, `stair_railing.py`, `furniture_table.py`, or any calculator that already populates hardware. The `if hardware: return hardware` guard in the method prevents duplication, but don't even call it unnecessarily.

### Step 5: Material Alternatives Endpoint

Add to `backend/routers/quotes.py`:

```python
@router.get("/materials/alternatives")
def get_material_alternatives(
    profile: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return alternative material profiles in the same category.

    Given a profile like "HSS_2x2_11ga", returns all other square tube
    profiles with their unit prices.
    """
    from ..calculators.material_lookup import MaterialLookup
    lookup = MaterialLookup()
    alternatives = lookup.get_alternatives(profile)
    return {"profile": profile, "alternatives": alternatives}
```

**In `material_lookup.py`**, add a `get_alternatives(profile)` method to `MaterialLookup`:

```python
def get_alternatives(self, profile: str) -> list[dict]:
    """
    Return alternative profiles in the same shape/category.

    Strategy:
    1. Parse the profile to determine shape (HSS square, HSS round, flat bar, angle, etc.)
    2. Return all profiles of the same shape with their prices
    3. Sort by price ascending
    """
    shape = self._extract_shape(profile)
    alternatives = []
    for key, data in _SEEDED_PRICES.items():
        if self._extract_shape(key) == shape and key != profile:
            alternatives.append({
                "profile": key,
                "description": self._profile_to_description(key),
                "price_per_ft": data.get("price_per_ft", 0),
                "weight_per_ft": data.get("weight_per_ft", 0),
                "stock_length_ft": data.get("stock_length_ft", 20),
            })
    alternatives.sort(key=lambda x: x["price_per_ft"])
    return alternatives

def _extract_shape(self, profile: str) -> str:
    """Extract shape category from profile key."""
    profile_lower = profile.lower()
    if "flat_bar" in profile_lower or "flat" in profile_lower:
        return "flat_bar"
    elif "hss" in profile_lower and ("sq" in profile_lower or "x" in profile_lower):
        # Distinguish square from round
        # Square tubes have equal dimensions like 2x2
        parts = profile_lower.split("_")
        return "hss_square"
    elif "hss" in profile_lower and "round" in profile_lower:
        return "hss_round"
    elif "angle" in profile_lower:
        return "angle"
    elif "channel" in profile_lower:
        return "channel"
    elif "pipe" in profile_lower:
        return "pipe"
    elif "sheet" in profile_lower or "plate" in profile_lower:
        return "sheet"
    else:
        return "other"

def _profile_to_description(self, profile: str) -> str:
    """Convert profile key to human-readable description."""
    return profile.replace("_", " ").replace("  ", " ").title()
```

Review the existing `_SEEDED_PRICES` structure and adjust `_extract_shape()` to match the actual profile key naming convention used in the catalog. The above is a starting point — the real implementation must match whatever naming pattern exists in the data.

### Step 6: Material Swap Endpoint

Add to `backend/routers/quotes.py`:

```python
from pydantic import BaseModel

class MaterialSwapRequest(BaseModel):
    item_index: int
    new_profile: str

@router.post("/{quote_id}/swap-material")
def swap_material(
    quote_id: int,
    swap: MaterialSwapRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Swap a material line item to a different profile and recalculate.

    Pure math — no AI calls. Looks up new profile pricing, updates the
    line item, and cascades the recalculation through subtotals → total.
    """
    from ..calculators.material_lookup import MaterialLookup
    from sqlalchemy.orm.attributes import flag_modified

    quote = db.query(models.Quote).filter(
        models.Quote.id == quote_id,
        models.Quote.user_id == current_user.id,
    ).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    outputs = dict(quote.outputs_json)  # Don't mutate the original directly
    materials = outputs.get("materials", [])

    if swap.item_index < 0 or swap.item_index >= len(materials):
        raise HTTPException(status_code=400, detail=f"Invalid item_index: {swap.item_index}")

    item = dict(materials[swap.item_index])  # Copy the item

    # Look up new profile pricing
    lookup = MaterialLookup()
    new_price_data = lookup.lookup_price(swap.new_profile)
    if not new_price_data:
        raise HTTPException(status_code=404, detail=f"Profile not found: {swap.new_profile}")

    # Preserve quantity and length, update price and profile
    old_profile = item.get("profile", "")
    old_line_total = item.get("line_total", 0)
    quantity = item.get("quantity", 1)
    length_inches = item.get("length_inches", 0)
    length_ft = length_inches / 12 if length_inches else 0

    new_unit_price = new_price_data.get("price_per_ft", 0) * length_ft if length_ft else new_price_data.get("price_per_ft", 0)
    new_line_total = round(new_unit_price * quantity, 2)

    # Update the item
    item["profile"] = swap.new_profile
    item["description"] = lookup._profile_to_description(swap.new_profile)
    item["unit_price"] = round(new_unit_price, 2)
    item["line_total"] = new_line_total
    if "stock_length_ft" in new_price_data:
        item["stock_length_ft"] = new_price_data["stock_length_ft"]
    if "weight_per_ft" in new_price_data:
        item["weight_per_ft"] = new_price_data["weight_per_ft"]

    # Put updated item back
    materials[swap.item_index] = item
    outputs["materials"] = materials

    # Recalculate subtotals
    material_subtotal = round(sum(m.get("line_total", 0) for m in materials), 2)
    outputs["material_subtotal"] = material_subtotal

    # Recalculate grand subtotal
    subtotal = round(
        material_subtotal +
        outputs.get("hardware_subtotal", 0) +
        outputs.get("consumable_subtotal", 0) +
        outputs.get("labor_subtotal", 0) +
        outputs.get("finishing_subtotal", 0),
        2,
    )
    outputs["subtotal"] = subtotal

    # Recalculate markup options and total
    markup_pct = outputs.get("selected_markup_pct", 15)
    markup_options = {}
    for pct in [0, 5, 10, 15, 20, 25, 30]:
        markup_options[str(pct)] = round(subtotal * (1 + pct / 100), 2)
    outputs["markup_options"] = markup_options
    outputs["total"] = markup_options.get(str(markup_pct), subtotal)

    # Track swap history for audit trail
    swap_history = outputs.get("swap_history", [])
    swap_history.append({
        "item_index": swap.item_index,
        "old_profile": old_profile,
        "new_profile": swap.new_profile,
        "old_line_total": old_line_total,
        "new_line_total": new_line_total,
        "delta": round(new_line_total - old_line_total, 2),
    })
    outputs["swap_history"] = swap_history

    # Save to database
    quote.outputs_json = outputs
    quote.subtotal = subtotal
    quote.total = outputs["total"]
    flag_modified(quote, "outputs_json")
    db.commit()
    db.refresh(quote)

    return outputs
```

**IMPORTANT:** Check how `MaterialLookup.lookup_price()` works (or whatever the actual method name is for looking up a profile's pricing). The method name and return structure in the code above are guesses — use the actual method from `material_lookup.py`. The critical thing is: given a profile key string, get back `price_per_ft`, `weight_per_ft`, `stock_length_ft`.

### Step 7: Frontend Material Swap UI

In `frontend/js/quote-flow.js`, modify `_renderMaterialsTable()` to make each row interactive:

```javascript
// Each material row gets a click handler
<tr class="material-row swappable" data-index="${i}" data-profile="${m.profile || ''}"
    onclick="QuoteFlow.showMaterialSwap(${i}, '${(m.profile || '').replace(/'/g, "\\'")}')">
```

Add new methods to `QuoteFlow`:

```javascript
async showMaterialSwap(itemIndex, currentProfile) {
    if (!currentProfile) return;

    // Fetch alternatives
    const resp = await API.getMaterialAlternatives(currentProfile);
    const alts = resp.alternatives || [];
    if (!alts.length) {
        // No alternatives available
        return;
    }

    // Get current item for price comparison
    const currentItem = this.pricedQuote.materials[itemIndex];
    const currentLineTotal = currentItem.line_total || 0;

    // Build dropdown/modal
    const modal = document.createElement('div');
    modal.className = 'material-swap-modal';
    modal.innerHTML = `
        <div class="swap-overlay" onclick="QuoteFlow.closeSwapModal()"></div>
        <div class="swap-panel">
            <h4>Swap Material</h4>
            <p class="swap-current">Current: ${currentItem.description || currentProfile}</p>
            <div class="swap-options">
                ${alts.map(alt => {
                    // Calculate approximate price delta
                    const lengthFt = (currentItem.length_inches || 0) / 12;
                    const qty = currentItem.quantity || 1;
                    const newLineTotal = alt.price_per_ft * lengthFt * qty;
                    const delta = newLineTotal - currentLineTotal;
                    const deltaStr = delta >= 0 ? `+${this._fmt(delta)}` : this._fmt(delta);
                    const deltaClass = delta >= 0 ? 'delta-up' : 'delta-down';
                    return `
                        <div class="swap-option" onclick="QuoteFlow.executeMaterialSwap(${itemIndex}, '${alt.profile}')">
                            <span class="swap-desc">${alt.description}</span>
                            <span class="swap-price">${this._fmt(alt.price_per_ft)}/ft</span>
                            <span class="swap-delta ${deltaClass}">${deltaStr}</span>
                        </div>
                    `;
                }).join('')}
            </div>
            <button class="btn btn-ghost btn-sm" onclick="QuoteFlow.closeSwapModal()">Cancel</button>
        </div>
    `;
    document.body.appendChild(modal);
},

closeSwapModal() {
    const modal = document.querySelector('.material-swap-modal');
    if (modal) modal.remove();
},

async executeMaterialSwap(itemIndex, newProfile) {
    this.closeSwapModal();

    try {
        const result = await API.swapMaterial(this.quoteId, itemIndex, newProfile);
        // Update local state and re-render
        this.pricedQuote = result;
        this._renderResults({
            quote_number: this.pricedQuote.quote_number || '',
            priced_quote: this.pricedQuote,
        });
    } catch (e) {
        console.error('Material swap failed:', e);
        alert('Failed to swap material: ' + e.message);
    }
},
```

Add to `frontend/js/api.js`:

```javascript
async getMaterialAlternatives(profile) {
    const resp = await this.fetch(`/api/quotes/materials/alternatives?profile=${encodeURIComponent(profile)}`);
    return resp.json();
},

async swapMaterial(quoteId, itemIndex, newProfile) {
    const resp = await this.fetch(`/api/quotes/${quoteId}/swap-material`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_index: itemIndex, new_profile: newProfile }),
    });
    return resp.json();
},
```

### Step 8: Frontend CSS for Swap UI

Add to the CSS file:

```css
/* Swappable material rows */
.material-row.swappable {
    cursor: pointer;
    transition: background-color 0.15s;
}
.material-row.swappable:hover {
    background-color: rgba(59, 130, 246, 0.08);
}

/* Job description section */
.job-description-section {
    background: var(--bg-secondary, #f8f9fa);
    border-left: 3px solid var(--accent, #3b82f6);
    padding: 12px 16px;
    margin-bottom: 16px;
    border-radius: 0 6px 6px 0;
}
.job-description-text {
    margin: 4px 0 0;
    font-size: 14px;
    line-height: 1.5;
    color: var(--text-secondary, #4b5563);
}

/* Material swap modal */
.material-swap-modal {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
}
.swap-overlay {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.4);
}
.swap-panel {
    position: relative;
    background: var(--bg-primary, #fff);
    border-radius: 12px;
    padding: 20px;
    max-width: 420px;
    width: 90%;
    max-height: 70vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}
.swap-current {
    font-size: 13px;
    color: var(--text-secondary, #6b7280);
    margin-bottom: 12px;
}
.swap-option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s;
    gap: 8px;
}
.swap-option:hover {
    background: var(--bg-secondary, #f3f4f6);
}
.swap-desc { flex: 1; font-size: 14px; }
.swap-price { font-size: 13px; color: var(--text-secondary, #6b7280); white-space: nowrap; }
.swap-delta { font-size: 13px; font-weight: 600; white-space: nowrap; }
.delta-up { color: #ef4444; }
.delta-down { color: #22c55e; }
```

---

## EVALUATION DESIGN

### Test 1: Job Description Visibility
1. Start a new swing_gate session
2. Enter description: "36 wide x 72 tall single swing gate, flat bar decorative, raw steel clear coat"
3. Complete all questions, run through pipeline to final quote
4. **Verify:** Quote results page shows the description at the top
5. **Verify:** `GET /api/quotes/{id}` response includes `outputs.job_description`
6. **Verify:** PDF includes the description

### Test 2: Hardware Generation (Existing Calculator)
1. Run a swing_gate quote with hinge_type = "Heavy duty weld-on barrel hinges", latch_type = "Gravity latch"
2. **Verify:** Hardware section shows hinges and latch with real pricing (NOT $0)
3. **Verify:** No duplicate hardware items

### Test 3: Hardware Generation (Fallback Calculator)
1. Run a custom_fab quote
2. In the question tree, select hardware-related options if available
3. **Verify:** If hardware fields were answered, hardware section shows items with pricing
4. **Verify:** If no hardware fields were answered, hardware section correctly shows empty (don't generate phantom hardware)

### Test 4: Material Swap
1. Open a completed quote with materials
2. Click on a material row (e.g., "1.5" x 1.5" 11 gauge square tube")
3. **Verify:** Modal/dropdown appears showing alternatives (e.g., 2" x 2", 14 gauge, etc.)
4. **Verify:** Each alternative shows price delta ("+$45" / "-$120")
5. Select an alternative
6. **Verify:** Material row updates with new profile and price
7. **Verify:** Material subtotal updates
8. **Verify:** Grand total updates (including markup)
9. **Verify:** Reload page — changes persist (saved to database)
10. **Verify:** `outputs_json.swap_history` shows the swap record

### Test 5: Edge Cases
1. Try swapping a material on a quote with 0% markup — verify total = subtotal
2. Try swapping a material on a quote with 30% markup — verify math is correct
3. Try swapping to the same profile — should be a no-op (or at least not break)
4. Open a quote with no materials (edge case) — verify no crashes
5. Check a furniture_table quote (existing hardware) — verify no duplication from fallback

---

## FILES TO MODIFY (Summary)

**Backend:**
- `backend/pricing_engine.py` — add `job_description` to output
- `backend/calculators/hardware_mapper.py` — NEW FILE: hardware fallback utility
- `backend/calculators/base.py` — add `_apply_hardware_fallback()` method
- `backend/calculators/custom_fab.py` — wire in hardware fallback
- `backend/calculators/structural_frame.py` — wire in hardware fallback (if empty)
- `backend/calculators/bollard.py` — wire in hardware fallback (if empty)
- `backend/calculators/repair_structural.py` — wire in hardware fallback (if empty)
- `backend/calculators/repair_decorative.py` — wire in hardware fallback (if empty)
- `backend/calculators/sign_frame.py` — wire in hardware fallback (if empty)
- `backend/calculators/led_sign_custom.py` — wire in hardware fallback (if empty)
- `backend/calculators/material_lookup.py` — add `get_alternatives()`, `_extract_shape()`, `_profile_to_description()` methods
- `backend/hardware_sourcer.py` — add missing HARDWARE_PRICES entries (latches, motors, closers, etc.)
- `backend/calculators/material_lookup.py` — add missing HARDWARE_CATALOG entries to match
- `backend/routers/quotes.py` — add `/swap-material` POST and `/materials/alternatives` GET endpoints

**Frontend:**
- `frontend/js/quote-flow.js` — job description section + swappable material rows + swap modal
- `frontend/js/api.js` — add `getMaterialAlternatives()` and `swapMaterial()` methods
- `frontend/css/*.css` — styles for job description, swappable rows, swap modal

---

## VERIFICATION CHECKLIST (run after ALL changes)

```bash
# 1. Backend starts without import errors
cd /path/to/repo && python -c "from backend.main import app; print('OK')"

# 2. New hardware mapper imports clean
python -c "from backend.calculators.hardware_mapper import generate_hardware_from_fields; print('OK')"

# 3. Material alternatives endpoint works
curl -s localhost:8000/api/quotes/materials/alternatives?profile=HSS_2x2_11ga | python -m json.tool

# 4. No duplicate hardware in swing_gate (already generates its own)
# Run a swing_gate quote, inspect outputs_json.hardware — count entries

# 5. Job description in pricing engine output
# Run any quote, inspect outputs_json.job_description

# 6. Grep for integration
grep -rn "hardware_mapper\|generate_hardware_from_fields" backend/ --include="*.py" | grep -v __pycache__
grep -rn "job_description" backend/ frontend/ --include="*.py" --include="*.js" | grep -v __pycache__
grep -rn "swap-material\|swapMaterial\|swap_material" backend/ frontend/ --include="*.py" --include="*.js" | grep -v __pycache__
```
