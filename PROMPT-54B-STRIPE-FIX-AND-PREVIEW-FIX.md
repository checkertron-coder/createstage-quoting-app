# PROMPT 54B: Fix Stripe Checkout + Free Tier Preview + Loading Messages

*Read CLAUDE.md first. THIS IS CRITICAL — the payment flow is completely broken.*

---

## Problem Statement

Three broken things:

1. **Stripe checkout doesn't work.** The files `backend/routers/stripe_billing.py` and `backend/stripe_service.py` don't exist. The "Upgrade" and pricing buttons loop the user back to the pricing page in a circle. No actual Stripe Checkout session is ever created. Users CANNOT pay.

2. **Free tier quote vanishes.** After generating a free-tier quote, if the user clicks "Upgrade" and navigates to pricing, their quote is gone when they come back. Also the quote is 100% blurred — they can't see ANY content. Should show first 4 rows of each section (materials, labor, build instructions) with the rest blurred.

3. **Loading messages reference specific processes** ("calculating powder coat") even when the job doesn't involve powder coat. Messages should be generic funny fabrication jokes, not process-specific.

---

## Acceptance Criteria

### 1. Stripe Checkout — ACTUALLY WORKING

**Create these files that P54 should have created:**

**`backend/stripe_service.py`:**
- `create_customer(email)` → creates Stripe customer, returns customer ID
- `create_checkout_session(customer_id, price_id, success_url, cancel_url)` → creates Stripe Checkout Session, returns session URL
- `create_portal_session(customer_id, return_url)` → creates Stripe Customer Portal session, returns URL
- `handle_webhook_event(payload, sig_header)` → verifies signature, processes event, returns event type
- All calls wrapped in try/except — if STRIPE_SECRET_KEY not set, log warning and skip (don't crash)

**`backend/routers/stripe_billing.py`:**
- `POST /api/stripe/create-checkout` (auth required) — accepts `{ "price_id": "price_xxx" }`, creates Stripe customer if needed, creates checkout session, returns `{ "checkout_url": "https://checkout.stripe.com/..." }`
- `POST /api/stripe/webhook` (NO auth — Stripe calls this directly) — verifies webhook signature, handles events:
  - `checkout.session.completed` → find user by Stripe customer ID, set their tier based on which price they paid, set `subscription_status = "active"`, store `stripe_subscription_id`
  - `invoice.payment_succeeded` → keep subscription active
  - `invoice.payment_failed` → set `subscription_status = "past_due"`
  - `customer.subscription.deleted` → set `subscription_status = "cancelled"`, set `tier = "free"`
- `GET /api/stripe/portal` (auth required) — creates portal session, returns `{ "portal_url": "..." }`

**Price ID mapping** (env vars so they're configurable):
```
STRIPE_PRICE_STARTER=price_xxx   # $49/mo
STRIPE_PRICE_PRO=price_xxx       # $149/mo  
STRIPE_PRICE_SHOP=price_xxx      # $349/mo
```

The backend maps price IDs to tier names:
```python
PRICE_TO_TIER = {
    os.environ.get("STRIPE_PRICE_STARTER", ""): "starter",
    os.environ.get("STRIPE_PRICE_PRO", ""): "professional", 
    os.environ.get("STRIPE_PRICE_SHOP", ""): "shop",
}
```

**Frontend wiring:**
- Landing page pricing buttons: each "Subscribe" button calls `POST /api/stripe/create-checkout` with the correct price_id → redirect to the returned `checkout_url`
- If user is not logged in when clicking pricing, redirect to register first, then back to checkout
- In-app "Upgrade" button: same flow — calls create-checkout with selected price_id
- Profile page "Manage Billing" button: calls `GET /api/stripe/portal` → redirect to returned `portal_url`
- Return from Stripe: `/app?session_id=xxx` → frontend detects query param, calls `/api/auth/me` to refresh user tier, shows success message

**Mount the router in main.py:**
```python
from .routers import stripe_billing
app.include_router(stripe_billing.router, prefix="/api")
```

**Kill the free trial:**
- Remove ALL `trial_ends_at` logic from `check_quote_access` and registration
- Remove "Start Free Trial" text — buttons should say **"Subscribe"** on landing page and **"Upgrade Now"** in-app
- Free tier = 1 preview quote. Period. No trial period.

### 2. Free Tier Preview Fix

**Quote must persist:** The free-tier quote result must stay accessible after navigation. Store the quote ID in the user's session/localStorage. When they come back to the quote view, reload it from `/api/quotes/{id}/detail`.

**Show first 4 rows, blur the rest:**
- **Materials table:** First 4 line items fully visible (description, profile, length, quantity — but dollar amounts still blurred). Items 5+ blurred entirely.
- **Labor table:** First 4 processes fully visible (process name + hours visible, dollar rate blurred). Processes 5+ blurred.
- **Build instructions:** First 4 steps fully visible with full text. Steps 5+ blurred.
- **Hardware:** First 2 items visible, rest blurred.
- **Consumables:** First 2 items visible, rest blurred.
- **Total:** Still shown as range (±15-20%), not exact.
- **Client Quote PDF:** ONE download allowed — but generate a special "free tier" version where the total is shown as a range (±15-20%), not exact. All other line item prices are blurred/omitted. The PDF should still have their shop name/logo and look professional. This is the one freebie they can send to a client.
- **Shop Build Instructions PDF:** LOCKED — "Upgrade to unlock build instructions"
- **Material Order List PDF:** LOCKED — "Upgrade to unlock material orders"

**Upgrade CTA placement:** Put the upgrade card RIGHT AFTER the visible content, BEFORE the blurred content. Not at the bottom where they might not see it.

### 3. Loading Messages — Generic Fab Humor Only

Replace any process-specific loading messages (like "calculating powder coat" or "figuring out TIG vs MIG") with generic fabrication humor. The messages should be funny regardless of what job type is being quoted.

Check `frontend/js/quote-flow.js` for the LOADING_MESSAGES array. If there are process-specific ones mixed in, replace them. All messages should work for ANY quote — gate, railing, bumper, LED sign, anything.

Keep the famous-sayings-metal-fabricated jokes from P53C. Remove or replace anything that references a specific process, material, or finish type.

---

## Constraint Architecture

### Files to CREATE
- `backend/stripe_service.py` — Stripe API wrapper
- `backend/routers/stripe_billing.py` — checkout, webhook, portal endpoints
- `alembic/versions/xxx_add_stripe_fields.py` — migration for stripe_customer_id, stripe_subscription_id on User (if not already present)

### Files to MODIFY
- `backend/main.py` — mount stripe_billing router
- `backend/models.py` — add stripe_customer_id, stripe_subscription_id to User (if not already there)
- `backend/routers/auth.py` — remove trial_ends_at logic from registration + check_quote_access
- `frontend/index.html` — pricing buttons call create-checkout, change "Start Free Trial" to "Subscribe"
- `frontend/js/auth.js` — wire Upgrade and Manage Billing buttons, handle return from Stripe
- `frontend/js/api.js` — add createCheckout() and getPortalUrl() methods
- `frontend/js/quote-flow.js` — fix preview mode (4 rows visible), persist quote, fix loading messages
- `frontend/css/style.css` — adjust preview blur for 4-row visibility
- `requirements.txt` — add `stripe>=8.0.0` if not already there

### DO NOT TOUCH
- Calculator files, AI pipeline, PDF generator
- Landing page layout/design (P53C just polished it)

---

## Decomposition

**⚠️ SESSION DISCIPLINE:**
- Commit after each chunk. `pytest tests/ -v` after chunks 1 and 4.
- **Do NOT push until all chunks pass.**

### Chunk 1: Stripe Backend (the critical fix) → COMMIT
- Create `backend/stripe_service.py`
- Create `backend/routers/stripe_billing.py`
- Mount in main.py
- Migration if needed
- Remove trial_ends_at logic
- ✅ `pytest tests/ -v`

### Chunk 2: Frontend Stripe Wiring → COMMIT
- Pricing buttons → create-checkout → redirect to Stripe
- Upgrade button → create-checkout
- Manage Billing → portal
- Handle return from Stripe (refresh user tier)
- Change "Start Free Trial" to "Subscribe" everywhere
- ✅ App starts, manual test

### Chunk 3: Free Tier Preview Fix + Loading Messages → COMMIT
- Quote persists after navigation (localStorage quote ID)
- 4 rows visible per section, rest blurred
- Upgrade CTA between visible and blurred content
- Fix loading messages — generic only, no process-specific
- ✅ App starts, manual test

### Chunk 4: Tests → COMMIT
- Mock Stripe API calls
- Test checkout session creation
- Test webhook event handling (all 4 event types)
- Test tier transitions (free → starter, free → pro, pro → cancelled → free)
- Test preview mode shows correct number of visible rows
- ✅ `pytest tests/ -v` — all pass

---

## Evaluation

### Manual Tests
1. Register free account (no invite code) → generate 1 quote → see preview (4 rows visible, rest blurred, no downloads)
2. Click "Upgrade Now" → see pricing → click "Subscribe" on Pro → **redirected to Stripe Checkout page** (NOT a loop!)
3. Enter test card `4242 4242 4242 4242` → complete payment → redirected back to app → tier updated → full quote visible
4. Go to Profile → "Manage Billing" → Stripe Customer Portal opens
5. Navigate away from quote and come back → quote is still there
6. Loading messages during quote generation are funny and generic — no "calculating powder coat" on a gate quote
7. Landing page pricing buttons also go to Stripe Checkout (redirect to register first if not logged in)

### Automated Tests
- Minimum 10 new tests
