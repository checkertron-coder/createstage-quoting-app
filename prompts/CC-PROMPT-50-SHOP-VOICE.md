# CC Prompt 50: Shop Voice — Questions for Fabricators, Not Customers

## Problem

The universal intake questions read like a customer intake form:
- "Will you be providing the power supply and controller, or should we include those?"
- "Are you handling the programming yourself, or do you need a turnkey solution?"
- "What type of LED technology would you prefer?"

**This app is for fabricators and contractors quoting jobs, NOT for end customers.** The person using this app is a professional who already knows their craft. They need to specify job parameters for accurate pricing, not be walked through what a sign is.

Questions should sound like shop talk:
- "LED type?" → WS2812B / WS2815 / SK6812 / other
- "Power supply — in scope or client-supplied?"
- "Programming scope?" → firmware only / full UI+app / none
- "Back panel — same material/gauge or specify different?"

## Files to Change

### 1. `backend/question_trees/universal_intake.py`

#### UNIVERSAL_INTAKE_PROMPT (line ~28)

Change the opening from:
```
You are a metal fabrication quoting assistant used by professional fab shops.
A customer just submitted a project description
```

To:
```
You are a quoting tool for professional fabricators, welders, and contractors.
The user is a tradesperson entering a job they need to quote — they know their craft.
A job was just submitted
```

In the QUESTIONS section, add these rules:

```
   TONE AND VOICE:
   - The user is a FABRICATOR quoting a job, NOT an end customer buying a product.
   - Write questions in direct, concise shop language. No sales talk.
   - Use trade terminology. Don't explain what things are.
   - Keep question text SHORT — 3-10 words when possible.
   - For choice options, use industry-standard terms (e.g., "MIG", "TIG", "stick" — not "Metal Inert Gas welding").
   - Frame scope questions as "in scope or client-supplied?" not "will you be providing...?"
   - Never ask about standard fabrication practices the user already knows (weld sequence, grinding, surface prep).
   - Never ask questions the fabricator would answer by doing the work, not by filling out a form (e.g., "What welding positions will be required?" — they'll figure that out when they build it).
```

Also update the choice question rule to emphasize brevity:
```
   - For choice questions, provide 2-5 terse real-world options using trade terms.
```

#### FOLLOWUP_PROMPT (line ~100)

Same changes — update the opening from:
```
You are a metal fabrication quoting assistant. A customer is describing a project
and you are gathering information to generate an accurate quote.
```

To:
```
You are a quoting tool for professional fabricators and contractors.
The user is a tradesperson refining a job quote — they know their craft.
```

Add the same TONE AND VOICE rules to the follow-up question section.

### 2. Keep multi-trade readiness

Don't hardcode "metal fabrication" — use "fabricators, welders, and contractors" or just "tradespeople." The app will expand to painters, carpenters, etc. The tone guidance should work for any trade.

## Examples of Good vs Bad Questions

| ❌ Bad (customer voice) | ✅ Good (shop voice) |
|---|---|
| "What type of LED technology would you prefer for the sign?" | "LED type?" with options: WS2812B / WS2815 / SK6812 / other |
| "Will you be providing the power supply and controller?" | "Power supply — in scope or client-supplied?" |
| "Are you handling the programming yourself?" | "Programming scope?" → firmware only / full app / none / client-supplied |
| "What mounting method would you like?" | "Mount type?" → flush wall / standoff / monument / hanging |
| "Would you like the sign to have any special lighting effects?" | "Lighting mode?" → static / chase / fade / addressable patterns |
| "What finish would you prefer for your sign?" | "Finish?" → powder coat / wet paint / clear coat / raw / galvanized |
| "How would you like the sign delivered and installed?" | "Install scope?" → shop pickup / deliver only / full install |

---

## Bug Fix: Edit Button Skips Remaining Questions

### Problem
When a user clicks "Edit" on an already-captured field BEFORE answering all the AI-generated questions, it triggers the quote processing — skipping all remaining unanswered questions entirely. The user loses the chance to answer those questions, and the quote is generated with missing info.

### What to fix
In `frontend/js/quote-flow.js`, the `editExtractedField()` method and the Edit buttons in the "Already captured" section:

**Option (simplest):** Hide or disable the Edit buttons while there are still unanswered questions pending. Only show Edit buttons after ALL questions have been answered and the user is on the review/confirmation screen.

Implementation:
1. In the `_renderClarifyStep()` method, when rendering the "Already captured" extracted fields, check if `next_questions` is non-empty (questions still pending).
2. If questions are still pending: render the Edit button as disabled (grayed out, non-clickable) with a tooltip like "Answer all questions first"
3. If no questions pending (review screen): render Edit buttons as normal/active
4. CSS: add a `.confirmed-edit:disabled` or `.confirmed-edit.disabled` style that grays it out

This is simpler than trying to make Edit work mid-flow (which would require re-injecting the edited field back into the question queue without losing the remaining questions).

---

## Bug Fix: Consumables Field Mapping

### Problem
Every quote has `"consumables": []` and `"consumable_subtotal": 0`, but the actual consumable items (filler rod, gas, flap discs, paint, acetone, etc.) are ALL present — just in the `shop_stock` array instead.

Opus returns consumables correctly, but somewhere between Opus's response and the final quote output, they're landing in `shop_stock` instead of `consumables`. The `consumable_subtotal` stays at $0 while `shop_stock_subtotal` has the real number ($370-$807).

### What to fix
Trace the data flow from Opus's full-package response through the calculator/pricing engine to the final quote JSON. Find where consumables get routed to `shop_stock` instead of `consumables`. Options:

1. **If Opus returns them as `shop_stock`:** Update the full-package prompt to use `consumables` as the field name, OR add a mapping step that moves items from `shop_stock` to `consumables`.

2. **If the calculator renames them:** Fix the calculator to preserve the `consumables` key.

3. **If both fields are intentionally separate** (consumables = job-specific, shop_stock = things you already have on hand): Then `consumable_subtotal` should include `shop_stock_subtotal`, or the PDF/output should show shop stock items as consumables. Either way, the customer-facing quote should show these costs — they're real expenses.

**The subtotal math must include consumables in the final total regardless of which array they live in.** Right now the totals DO include shop_stock_subtotal, so the pricing is correct — it's just confusing to see "Consumables: $0" when there are $500+ in consumable items.

---

## Bug Fix: Sheet Nesting Across Different Stock Sizes

### Problem
On the circular Hacienda sign, Opus returns cut list pieces referencing DIFFERENT sheet stock sizes (60x120 for the discs, 48x96 for the side band strips). But they're all the same profile (`al_sheet_0.125`), so the calculator lumps them together and counts total sheets incorrectly.

Real math for the 5' circular sign:
- Sheet 1 (60x120): base disc + back disc (two 60" circles side by side)
- Sheet 2 (60x120): Layer 2 elements (letters, horse heads, etc.)
- Side band: two 5"×96" strips — comes from Sheet 2 remnant, NOT a separate sheet purchase

Result should be 2 sheets of 60x120, but calculator shows 3.

### What to fix
In `backend/calculators/base.py`, the `_build_materials_from_full_package()` method aggregates all pieces of the same profile into one bucket. When pieces have different `sheet_stock_size` values, they should be grouped into SEPARATE sub-buckets per stock size, and each sub-bucket should do its own area-based nesting calculation independently.

This way, 60x120 pieces get nested together on 60x120 stock, and 48x96 pieces get nested on 48x96 stock — instead of mixing them all together.

---

---

## Bug Fix: Laser Cut Drops ARE the Raised Layers (Critical)

### Problem
When Opus generates a cut list for a layered sign (like the Hacienda circular sign), it specs SEPARATE sheet stock for the raised layer elements (letters, horse heads, cactus, etc.). But those elements are laser cut OUT of the base disc — **the cutout drops ARE the raised layer pieces.** You don't buy a second or third sheet to re-cut them.

**Example:** 5' circular sign with 3 layers:
- Layer 1 = base disc (60" circle from 60x120 sheet)
- Layer 2 = letters, horse heads, horseshoes — these are the CUTOUTS from Layer 1
- Layer 3 = cactus, barrel — also CUTOUTS from Layer 1

Total sheet needed: ONE 60x120 sheet (plus one piece of flat bar for the side wall). NOT 2-3 sheets.

### What to fix
In the Opus full-package prompt (the system prompt that generates cut lists, build instructions, etc.), add this rule:

```
LASER CUT LAYER RULE:
When a design has elements laser cut from a base panel (letters, logos, shapes), 
the cutout drops ARE the raised layer pieces. Do NOT spec additional sheet stock 
for elements that come from the base panel cutouts. The base panel sheet yields 
BOTH the base layer (with negative space) AND all cutout elements for raised layers.
Only spec additional sheet stock if the design explicitly requires elements that 
are NOT cut from the base panel (e.g., a back panel, or elements larger than 
what fits in the base panel cutouts).
```

Also update the `sheets_needed` calculation to reflect this — pieces that are laser cut drops from another piece on the same sheet should have `sheets_needed: 0` in the cut list.

---

## Bug Fix: Frame/Structure Question Missing from Intake

### Problem
Opus assumes a full internal frame (frame rings, 12 cross braces, span braces) on every sign/cabinet project. For a 5' circular sign, a couple pieces of angle or tube tacked inside for rigidity might be all you need — NOT a full skeleton. The intake never asks about frame approach.

### What to fix
In `backend/question_trees/universal_intake.py`, add to the MANDATORY CATEGORIES in both `UNIVERSAL_INTAKE_PROMPT` and `FOLLOWUP_PROMPT`:

```
   - Internal structure/frame approach (for enclosed or cabinet-style pieces)
```

And in the TONE AND VOICE section, add an example:
```
   - "Internal structure?" → minimal bracing / cross braces only / full frame / none
```

This lets the fabricator specify their preferred approach instead of Opus over-engineering it every time.

---

## Material Catalog: Add Wide Flat Bar Profiles for Side Walls

### Problem
For sign side walls, the app specs cutting strips from full 4x8 or 5x10 sheets. But wide aluminum and steel flat bar stock exists in 4", 5", and 6" widths and is way cheaper than buying a full sheet and ripping strips.

### What to fix
Find the material/profile catalog (likely in `backend/calculators/` or a JSON/Python file that defines available profiles and prices). Add these profiles:

**Aluminum:**
- `al_flat_bar_4x0.125` — 4" × 1/8" aluminum flat bar
- `al_flat_bar_5x0.125` — 5" × 1/8" aluminum flat bar  
- `al_flat_bar_6x0.125` — 6" × 1/8" aluminum flat bar
- `al_flat_bar_4x0.1875` — 4" × 3/16" aluminum flat bar
- `al_flat_bar_5x0.1875` — 5" × 3/16" aluminum flat bar
- `al_flat_bar_6x0.1875` — 6" × 3/16" aluminum flat bar

**Steel:**
- `flat_bar_4x0.125` — 4" × 1/8" steel flat bar
- `flat_bar_5x0.125` — 5" × 1/8" steel flat bar
- `flat_bar_6x0.125` — 6" × 1/8" steel flat bar
- `flat_bar_4x0.25` — 4" × 1/4" steel flat bar
- `flat_bar_5x0.25` — 5" × 1/4" steel flat bar
- `flat_bar_6x0.25` — 6" × 1/4" steel flat bar

Price per foot: estimate based on weight (aluminum ~$2-4/ft for 1/8" widths, steel ~$1.50-3/ft). Standard stock lengths: 20' for steel, 12' or 20' for aluminum.

Also add a note in the Opus full-package prompt:
```
SIDE WALL MATERIAL:
For sign side walls, cabinet sides, or enclosure wraps, prefer flat bar stock 
in the appropriate width (4", 5", 6") over cutting strips from full sheets. 
Flat bar is sold by the foot, is cheaper, and comes in standard 12-20' lengths 
that can be rolled for curved applications.
```

---

## Do NOT Change
- The JSON response format (known_facts, questions, readiness)
- Question field structure (id, text, type, options, unit, required, hint)
- The readiness evaluation logic
- The frontend — it renders whatever text Opus returns (except Edit button disable fix)

## Verification
1. **Shop voice:** Questions should read like a shop foreman, not a sales website
2. **Edit button:** Disabled/grayed during question flow, active on review screen only
3. **Consumables:** `consumable_subtotal` is non-zero, `consumables` array has items
4. **Sheet nesting:** Separate sub-buckets per stock size; circular sign shows correct sheet count
5. **Laser cut drops:** Layered sign cut list shows `sheets_needed: 0` for elements cut from base panel drops; total sheets = 1 (plus side wall flat bar)
6. **Frame question:** Sign/cabinet jobs get an "Internal structure?" question during intake
7. **Wide flat bar:** Side walls spec flat bar stock (e.g., `al_flat_bar_5x0.125`) instead of sheet strips
