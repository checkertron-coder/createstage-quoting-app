# PROMPT 74 — Annual Billing Toggle + Stripe Annual Price Support
*Run in Claude Code on M4 — working directory: createstage-quoting-app*
*Written by Checker — 2026-03-27*

---

## 1. PROBLEM STATEMENT

CreateQuote only supports monthly billing. Burton has added annual pricing to Stripe and Railway, but the app has no way to send annual price IDs to Stripe checkout. Users can't choose annual billing, and there's no toggle on the pricing page. Money is being left on the table — annual subscribers are worth 10x monthly, and there's no way to capture them.

---

## 2. ACCEPTANCE CRITERIA

From the user's perspective:

1. The pricing page (index.html and landing.html) shows a Monthly / Annual pill toggle at the top of the pricing section
2. When "Annual" is selected, all three tier prices update to show the annual price (e.g. "$790/yr") with a green savings badge showing the dollar savings vs monthly (e.g. "Save $158")
3. When "Monthly" is selected, prices revert to monthly display
4. Clicking "Get Started" or any upgrade button on annual mode sends the correct annual price ID to Stripe checkout
5. The backend reads the annual price IDs from Railway environment variables
6. A user who subscribes on annual gets billed annually by Stripe — no monthly charges

---

## 3. CONSTRAINT ARCHITECTURE

**In scope:**
- `backend/stripe_service.py` — add annual price ID env vars, update price_map logic
- `backend/routers/billing.py` or wherever checkout session is created — accept `billing_period` param (`monthly` or `annual`)
- `frontend/index.html` — add toggle pill to pricing section, update price display, update checkout button logic
- `frontend/landing.html` — same toggle changes as index.html
- `frontend/js/quote-flow.js` — update any upgrade CTAs to pass billing_period to checkout

**Off limits:**
- Do not change the Stripe webhook handler or subscription management logic
- Do not change tier feature sets, quota limits, or any non-pricing UI
- Do not touch any calculator, PDF, or quote generation code

**Railway environment variables already set by Burton (exact names):**
- `STRIPE_PRICE_STARTER_ANNUAL`
- `STRIPE_PRICE_PROFESSIONAL_ANNUAL`
- `STRIPE_PRICE_SHOP_ANNUAL`

**Existing monthly variables (already in stripe_service.py):**
- `STRIPE_PRICE_STARTER`
- `STRIPE_PRICE_PROFESSIONAL`
- `STRIPE_PRICE_SHOP`

**Pricing for display (hardcoded in frontend only — not in backend logic):**
| Tier | Monthly | Annual | Savings |
|------|---------|--------|---------|
| Starter | $79/mo | $790/yr | Save $158 |
| Professional | $149/mo | $1,490/yr | Save $298 |
| Shop | $349/mo | $3,490/yr | Save $698 |

---

## 4. DECOMPOSITION

### Step 1: Backend — Add annual price IDs to stripe_service.py
Read the three new Railway env vars:
- `STRIPE_PRICE_STARTER_ANNUAL`
- `STRIPE_PRICE_PROFESSIONAL_ANNUAL`
- `STRIPE_PRICE_SHOP_ANNUAL`

Add an `annual_price_map` alongside the existing `price_map`. Both maps should follow the same pattern as the existing monthly map.

### Step 2: Backend — Accept billing_period in checkout
In the checkout session creation endpoint, accept an optional `billing_period` parameter (`"monthly"` or `"annual"`, default `"monthly"`). Use it to select the correct price ID from either `price_map` or `annual_price_map` before creating the Stripe checkout session.

### Step 3: Frontend — Monthly/Annual toggle pill
Add a toggle pill component to the pricing section in both `index.html` and `landing.html`. Style: two pill buttons side-by-side ("Monthly" / "Annual"), with active state visually highlighted. Place it directly above the pricing cards.

### Step 4: Frontend — Dynamic price display
When toggle switches to Annual:
- Update each tier's displayed price to the annual amount (e.g. "$790 / year")
- Show a green savings badge below or beside the price (e.g. "Save $158 vs monthly")
- When toggle switches back to Monthly, revert to monthly display, hide savings badge

Use JavaScript to handle the toggle state and DOM updates — no page reload.

### Step 5: Frontend — Pass billing_period to checkout
All "Get Started", "Upgrade", and checkout buttons must pass `billing_period: "annual"` or `billing_period: "monthly"` to the backend checkout endpoint based on current toggle state. Update all relevant button handlers in `quote-flow.js` and inline scripts.

---

## 5. EVALUATION DESIGN

**Test 1: Toggle renders**
- Open pricing page
- Expected: Monthly/Annual pill toggle visible above pricing cards, Monthly selected by default

**Test 2: Annual prices display correctly**
- Click Annual toggle
- Expected: Starter shows "$790 / year" + "Save $158", Professional shows "$1,490 / year" + "Save $298", Shop shows "$3,490 / year" + "Save $698"

**Test 3: Monthly prices revert**
- Click Monthly toggle after being on Annual
- Expected: All prices revert to monthly display, savings badges hidden

**Test 4: Annual checkout sends correct price ID**
- Select Annual toggle, click "Get Started" on Starter tier
- Expected: Backend receives `billing_period: "annual"`, uses `STRIPE_PRICE_STARTER_ANNUAL` env var, Stripe checkout session created with annual price

**Test 5: Monthly checkout unchanged**
- Select Monthly toggle, click "Get Started" on any tier
- Expected: Checkout behavior identical to pre-prompt behavior

**Test 6: Missing env var handled gracefully**
- If an annual price ID env var is missing/empty, checkout should fall back to monthly price ID and log a warning — do not throw a 500

**Test 7: All existing tests still pass**
- Run full test suite
- Expected: all tests pass (count should be ≥ current passing count)

---

## NOTES FOR CC
- Do a git pull on ~/brain before starting (brain-sync protocol)
- Save point after backend changes, before frontend changes
- Run brain-save.sh after completing and pushing
- Burton confirmed annual prices are already live in Stripe and Railway — this is purely a code + UI wiring job
