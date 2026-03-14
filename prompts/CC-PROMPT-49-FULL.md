# CC Prompt 49: Full Cleanup — Tests, Calculator, Intake, Frontend

## Context
We just landed universal intake (P47/48) and a first pass at three fixes (sheet nesting, Other button, edit button). The app works on Railway but has **8 test failures + 71 test errors**, the sheet nesting calculator overcounts, consumables display is broken, questions sound like a customer form, and several fabrication knowledge gaps need fixing.

**Test summary:** `8 failed, 989 passed, 2 skipped, 71 errors`

Run `python3 -m pytest tests/ --tb=line -q` to see current state.

This is ONE prompt covering everything. Work through it in order — the test fixes (Part 1) unblock everything else.

---

# PART 1: TEST FIXES (do first)

## 1A: bcrypt/passlib Incompatibility (8 failed + 71 errors)

**Root cause:** `bcrypt==5.0.0` + `passlib` incompatibility. bcrypt 5.x removed the `__about__` module and changed password length enforcement. passlib's `CryptContext` breaks.

**Fix:** In `backend/auth.py`, replace passlib with direct bcrypt usage:

```python
import bcrypt

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8')[:72], bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8')[:72], hashed_password.encode('utf-8'))
```

Remove the `passlib` import and `pwd_context` entirely. Keep everything else in `auth.py` unchanged (JWT, refresh tokens, etc.).

Update `requirements.txt`: remove `passlib[bcrypt]`, keep `bcrypt>=4.0.0`.

**Verify:** All tests in `test_session1_schema.py` should pass, and all 71 `ERROR` tests should resolve.

## 1B: Vision Bug Check

After the passlib fix unblocks tests, re-run `test_photo_extraction.py`. If tests still fail, check `frontend/js/api.js` — the `startSession()` function must send `photo_urls` in the POST body to `/api/quote/start`.

---

# PART 2: BACKEND — CALCULATOR FIXES

## 2A: Sheet Nesting — Separate Buckets Per Stock Size

**File:** `backend/calculators/base.py`

**Problem:** Opus returns cut list pieces referencing DIFFERENT sheet stock sizes (60x120 for discs, 48x96 for side band strips). They're all the same profile (`al_sheet_0.125`), so the calculator lumps them together and overcounts.

**Fix:** In `_build_materials_from_full_package()`, when aggregating sheet pieces into `profile_totals`, sub-group by `sheet_stock_size`. Each sub-group does its own area-based nesting calculation independently. Then generate separate material line items per stock size.

## 2B: Sheet Nesting — Smarter Area Calculation

**Current problem:** The area-based nesting uses a flat 85% efficiency factor. For a 5' circular sign, two 60" circular panels = 7200 sq in, but one 60x120 sheet at 85% = 6120 sq in usable → result is 2 sheets when they clearly fit on 1.

**Fix options (in priority order):**
1. If Opus's full package response includes a top-level `total_sheets` or per-material `sheets_needed`, and `trust_opus` is True, use that directly.
2. Fall back to area-based nesting with first-fit-decreasing bin packing: sort pieces by largest dimension descending, place each on the first sheet that fits.
3. Safety rail: if calculated sheets > Opus's per-piece sum, use Opus's sum (it's already an overcount).

**Key constraint:** Don't break the existing tube/bar/angle material paths. Only change the `if is_sheet` branch.

## 2C: Consumables Field Mapping

**Problem:** Every quote has `"consumables": []` and `"consumable_subtotal": 0`, but actual consumable items are in `shop_stock` instead. The totals are correct (shop_stock_subtotal is included), but the display is confusing.

**Fix:** Trace the data flow from Opus's full-package response through the calculator/pricing engine. Find where consumables get routed to `shop_stock` instead of `consumables` and fix the routing. If Opus returns them as `shop_stock`, either update the prompt to use `consumables` or add a mapping step. The `consumable_subtotal` must reflect the real consumable costs.

---

# PART 3: OPUS PROMPT FIXES

## 3A: Laser Cut Drops ARE the Raised Layers (CRITICAL)

**Problem:** When Opus generates a cut list for a layered sign, it specs SEPARATE sheet stock for raised layer elements. But those elements are laser cut OUT of the base panel — **the cutout drops ARE the raised layer pieces.** You don't buy additional sheets to re-cut them.

**Example:** 5' circular sign with 3 layers:
- Layer 1 = base disc (60" circle from 60x120 sheet)
- Layer 2 = letters, horse heads, horseshoes — these are the CUTOUTS from Layer 1
- Layer 3 = cactus, barrel — also CUTOUTS from Layer 1
- Total sheet for face: ONE 60x120 sheet. NOT 2-3.

**Fix:** In the Opus full-package prompt (the system prompt that generates cut lists and build instructions), add:

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

Pieces that are laser cut drops should have `sheets_needed: 0` in the cut list.

## 3B: Side Wall Material — Use Flat Bar, Not Sheet Strips

**Problem:** For sign side walls, Opus specs cutting strips from full 4x8 or 5x10 sheets. Wide flat bar stock (4", 5", 6" widths) exists and is way cheaper.

**Fix:** Add to the Opus full-package prompt:

```
SIDE WALL MATERIAL:
For sign side walls, cabinet sides, or enclosure wraps, prefer flat bar stock 
in the appropriate width (4", 5", 6") over cutting strips from full sheets. 
Flat bar is sold by the foot, is cheaper, and comes in standard 12-20' lengths 
that can be rolled for curved applications.
```

---

# PART 4: UNIVERSAL INTAKE — QUESTION VOICE & NEW QUESTIONS

## 5A: Shop Voice (Question Tone)

**File:** `backend/question_trees/universal_intake.py`

### UNIVERSAL_INTAKE_PROMPT (line ~28)

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

Update the choice question rule:
```
   - For choice questions, provide 2-5 terse real-world options using trade terms.
```

### FOLLOWUP_PROMPT (line ~100)

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

### Multi-trade readiness
Don't hardcode "metal fabrication" — use "fabricators, welders, and contractors" or just "tradespeople." The app will expand to painters, carpenters, etc.

### Examples of Good vs Bad Questions

| ❌ Bad (customer voice) | ✅ Good (shop voice) |
|---|---|
| "What type of LED technology would you prefer for the sign?" | "LED type?" with options: WS2812B / WS2815 / SK6812 / other |
| "Will you be providing the power supply and controller?" | "Power supply — in scope or client-supplied?" |
| "Are you handling the programming yourself?" | "Programming scope?" → firmware only / full app / none / client-supplied |
| "What mounting method would you like?" | "Mount type?" → flush wall / standoff / monument / hanging |
| "What finish would you prefer for your sign?" | "Finish?" → powder coat / wet paint / clear coat / raw / galvanized |
| "How would you like the sign delivered and installed?" | "Install scope?" → shop pickup / deliver only / full install |

## 5B: Frame/Structure Question

Add to the MANDATORY CATEGORIES in both prompts:

```
   - Internal structure/frame approach (for enclosed or cabinet-style pieces)
```

And in the TONE AND VOICE examples:
```
   - "Internal structure?" → minimal bracing / cross braces only / full frame / none
```

---

# PART 5: FRONTEND FIXES

## 6A: Edit Button — Disable During Question Flow

**Problem:** Clicking "Edit" on a captured field before answering all AI-generated questions triggers quote processing, skipping remaining questions.

**Fix:** In `frontend/js/quote-flow.js`, in `_renderClarifyStep()`:
1. When rendering "Already captured" extracted fields, check if `next_questions` is non-empty
2. If questions pending: render Edit button as disabled with tooltip "Answer all questions first"
3. If no questions pending (review screen): render Edit buttons as normal/active
4. CSS: add `.confirmed-edit:disabled` or `.confirmed-edit.disabled` style that grays it out

## 6B: Verify "Other" Button Works

CC already added the Other button in commit `49d7519`. Verify it works:
1. Appears on every choice question
2. Clicking it highlights it and shows text input
3. Typed value collected in `_collectAnswers()` when `selected.dataset.value === '__other__'`
4. If broken, fix it. If working, leave it.

---

# VERIFICATION CHECKLIST

After all changes:

```bash
python3 -m pytest tests/ --tb=line -q
```

Target: **0 failures, 0 errors** (or only failures from missing external API keys).

```bash
cd backend && python3 -m uvicorn main:app --port 8000
```

Then verify:
1. ✅ Tests pass (bcrypt fix)
2. ✅ Sheet nesting: separate buckets per stock size, correct count
3. ✅ Consumables: `consumable_subtotal` non-zero, items in `consumables` array
4. ✅ Laser cut drops: layered sign shows `sheets_needed: 0` for cutout elements
5. ✅ Shop voice: questions read like shop talk, not sales form
6. ✅ Frame question: sign/cabinet jobs get "Internal structure?" question
7. ✅ Edit button: disabled during questions, active on review screen
8. ✅ Other button: works on choice questions

---

# DO NOT CHANGE
- Universal intake core logic (question loop, readiness gate)
- JSON response formats (known_facts, questions, readiness)
- Question field structure (id, text, type, options, unit, required, hint)
- Calculator logic for tubes/bars/angles (only change `if is_sheet` branch)
- Pricing formulas or markup calculations
- Frontend beyond Edit button disable + Other button verify
