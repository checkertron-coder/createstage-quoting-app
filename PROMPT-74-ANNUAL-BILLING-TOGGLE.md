# PROMPT 74 — Annual Billing Toggle + Stripe Annual Price Support
*Run in Claude Code on M4 — working directory: createstage-quoting-app*
*Written by Checker (Opus) — 2026-03-27*

---

## 1. PROBLEM STATEMENT

CreateQuote only supports monthly billing. Burton has added annual pricing to Stripe and Railway environment variables, but the app has no way to send annual price IDs to Stripe checkout. Users can't choose annual billing, and there's no toggle on the pricing page.

---

## 2. ACCEPTANCE CRITERIA

From the user's perspective:

1. The pricing page (index.html and landing.html) shows a Monthly / Annual pill toggle at the top of the pricing section
2. When "Annual" is selected, all three tier prices update to show the annual price with a green savings badge (e.g. "$790/yr — Save $158")
3. When "Monthly" is selected, prices revert to monthly display, savings badges hidden
4. Clicking any "Get Started" or upgrade button on annual mode sends the correct annual price ID to Stripe checkout
5. A user who subscribes on annual gets billed annually by Stripe — no monthly charges
6. Existing monthly subscribers are NOT affected — they manage billing period changes through the Stripe billing portal, not this toggle

---

## 3. CONSTRAINT ARCHITECTURE

**Files in scope (exact paths):**
- `backend/stripe_service.py` — add annual env vars, build annual price map, update `create_checkout_session()` signature
- `backend/routers/stripe_billing.py` — add `billing_period` to `CreateCheckoutRequest` model, pass it through to `create_checkout_session()`
- `frontend/index.html` — add toggle pill to pricing section, dynamic price display
- `frontend/landing.html` — same toggle changes as index.html
- `frontend/js/quote-flow.js` — update upgrade CTAs to pass `billing_period` to checkout endpoint

**Off limits:**
- Do not change the Stripe webhook handler or `_handle_checkout_completed()`
- Do not change tier feature sets, quota limits, or any non-pricing UI
- Do not touch any calculator, PDF, or quote generation code
- Do not change existing monthly subscription behavior for current subscribers

**Existing code to understand before editing:**

In `backend/stripe_service.py`:
```python
STRIPE_PRICE_STARTER = os.environ.get("STRIPE_PRICE_STARTER") or os.environ.get("STRIPE_STARTER_PRICE_ID", "")
STRIPE_PRICE_PROFESSIONAL = os.environ.get("STRIPE_PRICE_PROFESSIONAL") or os.environ.get("STRIPE_PRO_PRICE_ID", "")
STRIPE_PRICE_SHOP = os.environ.get("STRIPE_PRICE_SHOP") or os.environ.get("STRIPE_SHOP_PRICE_ID", "")

TIER_TO_PRICE_ID = {
    "starter": STRIPE_PRICE_STARTER,
    "professional": STRIPE_PRICE_PROFESSIONAL,
    "shop": STRIPE_PRICE_SHOP,
}
```

In `backend/routers/stripe_billing.py`:
```python
class CreateCheckoutRequest(BaseModel):
    tier: str  # 'starter' | 'professional' | 'shop'
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None
```

The `create_checkout_session()` function in `stripe_service.py` currently takes `(customer_id, tier, success_url, cancel_url)` and looks up `TIER_TO_PRICE_ID[tier]`.

**Railway environment variables already set by Burton:**
- Monthly (existing): `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PROFESSIONAL`, `STRIPE_PRICE_SHOP`
- Annual (new): `STRIPE_PRICE_STARTER_ANNUAL`, `STRIPE_PRICE_PROFESSIONAL_ANNUAL`, `STRIPE_PRICE_SHOP_ANNUAL`

**Pricing for frontend display:**
| Tier | Monthly | Annual | Savings |
|------|---------|--------|---------|
| Starter | $79/mo | $790/yr | Save $158 |
| Professional | $149/mo | $1,490/yr | Save $298 |
| Shop | $349/mo | $3,490/yr | Save $698 |

---

## 4. DECOMPOSITION

### Step 1: Backend — Add annual price map to stripe_service.py
Read three new env vars: `STRIPE_PRICE_STARTER_ANNUAL`, `STRIPE_PRICE_PROFESSIONAL_ANNUAL`, `STRIPE_PRICE_SHOP_ANNUAL`.

Build `TIER_TO_ANNUAL_PRICE_ID` map alongside the existing `TIER_TO_PRICE_ID`. Same pattern.

Update `create_checkout_session()` to accept an optional `billing_period` parameter (default `"monthly"`). When `billing_period == "annual"`, look up from `TIER_TO_ANNUAL_PRICE_ID` instead of `TIER_TO_PRICE_ID`. If the annual price ID is missing or empty, fall back to the monthly price ID and log a warning — do not throw an error.

### Step 2: Backend — Update CreateCheckoutRequest in stripe_billing.py
Add `billing_period: Optional[str] = "monthly"` to `CreateCheckoutRequest`.

Pass `request.billing_period` through to `stripe_service.create_checkout_session()`.

Update the diagnostic log on line ~79 to reflect which price map was used (monthly vs annual).

Both the initial checkout call AND the retry path (stale customer recreation) must pass `billing_period` through.

### Step 3: Frontend — Monthly/Annual toggle pill
Add a toggle pill component to the pricing section in both `index.html` and `landing.html`:
- Two pill buttons side-by-side: "Monthly" / "Annual"
- Active state visually highlighted (filled background)
- Placed directly above the pricing cards, centered
- Monthly selected by default
- Style should match the existing design language (colors, border-radius, fonts)

### Step 4: Frontend — Dynamic price display
When toggle switches to Annual:
- Each tier card's price text updates (e.g. "$790 / year")
- A green savings badge appears below the price (e.g. "Save $158")
When toggle switches back to Monthly:
- Prices revert to monthly (e.g. "$79 / month")
- Savings badges hidden

All done via JavaScript DOM manipulation — no page reload.

### Step 5: Frontend — Pass billing_period to checkout
All "Get Started", "Upgrade", and checkout buttons must include `billing_period` in the POST body to `/api/stripe/create-checkout`. Read the current toggle state at click time:
- Toggle on Monthly → send `billing_period: "monthly"`
- Toggle on Annual → send `billing_period: "annual"`

Check `quote-flow.js` and any inline scripts in `index.html`/`landing.html` for checkout button handlers. All paths must be updated.

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
- Expected: Backend receives `billing_period: "annual"`, uses `STRIPE_PRICE_STARTER_ANNUAL` env var value, Stripe checkout session created with annual price

**Test 5: Monthly checkout unchanged**
- Select Monthly toggle (or leave default), click "Get Started" on any tier
- Expected: Checkout behavior identical to current pre-prompt behavior

**Test 6: Missing annual env var handled gracefully**
- If `STRIPE_PRICE_STARTER_ANNUAL` is empty/missing, and user selects Annual + Starter
- Expected: Falls back to monthly price ID, logs a warning, checkout still works

**Test 7: All existing tests still pass**
- Run full test suite
- Expected: all tests pass (count ≥ current passing count)

---

## NOTES FOR CC
- Do a git pull on ~/brain before starting (brain-sync protocol)
- Pre-prompt save point: `git add . && git commit -m "pre-P74 save point"`
- Save point after backend changes, before frontend changes
- Run brain-save.sh after completing and pushing
- Annual toggle is for NEW subscriptions only — existing subscribers use the Stripe billing portal to change billing period
