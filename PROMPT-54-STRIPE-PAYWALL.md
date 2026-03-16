# PROMPT 54: Stripe Subscription Paywall

*Read CLAUDE.md first. Depends on PROMPT-53 being complete.*

---

## Problem Statement

CreateQuote needs real payment processing. Users who don't have a beta invite code need to pay for access. Stripe handles subscriptions, trials, and billing — we never touch card data directly.

---

## Acceptance Criteria

### Stripe Integration
1. Add `stripe` Python package to requirements.txt
2. New env vars: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`
3. Create Stripe Products + Prices (via seed script or manual setup):
   - Starter: $49/mo
   - Professional: $149/mo
   - Shop: $349/mo
4. Stripe Checkout Session flow:
   - User clicks "Subscribe" on pricing → backend creates Stripe Checkout Session → redirect to Stripe → Stripe redirects back to `/app?session_id=xxx`
   - Backend verifies session, updates user tier + subscription status
5. Stripe Webhook endpoint: `POST /api/stripe/webhook`
   - `checkout.session.completed` → activate subscription
   - `invoice.payment_succeeded` → keep subscription active
   - `invoice.payment_failed` → set status to "past_due"
   - `customer.subscription.deleted` → set status to "cancelled", downgrade tier to "free"
6. Billing portal: `GET /api/stripe/portal` → creates Stripe Customer Portal session for managing subscription (cancel, update payment method)

### User Model Updates (extends P53)
1. Add `stripe_customer_id` (string, nullable)
2. Add `stripe_subscription_id` (string, nullable)

### Frontend Updates
1. Pricing section buttons on landing page → hit backend to create Checkout Session → redirect to Stripe
2. In-app banner for free/trial users: "You're on the free plan. Upgrade to unlock unlimited quotes."
3. Profile page shows current plan + "Manage Billing" button (→ Stripe portal)

### Quote Access Enforcement (updated tiers)
1. Free tier: 1 quote total (preview mode — blurred results, no downloads, handled by P53D)
2. Starter ($49/mo): 3 quotes/month
3. Professional ($149/mo): 25 quotes/month
4. Shop ($349/mo): unlimited quotes
5. Trial (14 days from registration): full Professional access
6. Past due: read-only access to existing quotes, no new quotes
7. Cancelled: downgrade to free
8. Beta invite code users: Professional tier, no payment required

---

## Constraint Architecture

### Files to CREATE
- `backend/routers/stripe_billing.py` — Stripe checkout, webhook, portal endpoints
- `backend/stripe_service.py` — Stripe API wrapper (create customer, create checkout, handle webhook events)

### Files to MODIFY
- `backend/models.py` — add Stripe fields to User
- `backend/main.py` — mount stripe router
- `backend/routers/auth.py` — create Stripe customer on registration
- `frontend/index.html` — pricing buttons trigger checkout
- `frontend/js/app.js` — handle return from Stripe checkout
- `requirements.txt` — add `stripe>=8.0.0`

### DO NOT TOUCH
- Calculator files, AI pipeline, quote-flow.js, existing tests
- The quoting pipeline itself is unchanged

---

## Decomposition

**⚠️ SESSION DISCIPLINE:**
- Work through chunks sequentially. Commit after each.
- `pytest tests/ -v` after chunks 1, 2, and 4.
- **Do NOT push until all 4 chunks pass.**

### Chunk 1: Stripe Service Layer + Models → COMMIT
- Create `backend/stripe_service.py` — create customer, create checkout session, create portal session, handle webhook events
- All Stripe API calls go through this service (same pattern as `claude_client.py` for AI)
- Add `stripe_customer_id` and `stripe_subscription_id` to User model
- Create Alembic migration (idempotent)
- Add `stripe>=8.0.0` to requirements.txt
- ✅ `pytest tests/ -v`

### Chunk 2: Webhook + Endpoints → COMMIT
- Create `backend/routers/stripe_billing.py`
- Webhook endpoint with signature verification (`POST /api/stripe/webhook`)
- Checkout session creation endpoint (`POST /api/stripe/create-checkout`)
- Portal session creation endpoint (`GET /api/stripe/portal`)
- Return URL handling (`/app?session_id=xxx`)
- Mount router in main.py
- Create Stripe customer on registration in auth.py (if STRIPE_SECRET_KEY is set — graceful skip otherwise)
- ✅ `pytest tests/ -v`

### Chunk 3: Frontend Integration → COMMIT
- Landing page pricing buttons → hit backend to create Checkout Session → redirect to Stripe
- In-app upgrade banner for free/trial users
- Profile page: show current plan + "Manage Billing" button (→ Stripe portal)
- Handle return from Stripe checkout in app.js
- ✅ App starts, manual test

### Chunk 4: Tests → COMMIT
- Mock Stripe API calls (don't hit real Stripe in tests)
- Test webhook event handling (each event type)
- Test tier enforcement after subscription changes
- Test free → paid → cancelled flow
- ✅ `pytest tests/ -v` — all pass

---

## Evaluation Design

### Manual Tests
1. Register without invite code → free tier → 1 quote limit
2. Click "Upgrade" → Stripe Checkout → enter test card → redirected back → tier updated
3. Create quotes → limits enforced per tier
4. Go to Profile → "Manage Billing" → Stripe portal opens
5. Cancel subscription in Stripe portal → webhook fires → user downgraded

### Automated Tests
- Webhook signature verification
- Event handler for each Stripe event type
- User tier transitions (free→trial→paid→cancelled)
- Quote access enforcement per tier

---

## Notes

- Use Stripe test mode keys for development. Real keys only in Railway production env vars.
- **NEVER log Stripe keys, webhook secrets, or customer payment data.** (Section 21 rule)
- Stripe Checkout handles all PCI compliance — we never see card numbers.
- Webhook endpoint must be excluded from CSRF/auth middleware — Stripe calls it directly.
- Consider: Stripe test clock for simulating trial expiry in tests.
