# PROMPT-66 — Starter Tier Price Update: $49 → $79

## Problem Statement

The Starter tier is displayed as $49/mo in three places across the frontend, but the correct price is $79/mo. Additionally, the upgrade CTA copy references "Starting at $49/mo" which is now wrong. The Stripe price ID for Starter must also be replaced — Stripe does not allow editing existing prices, so a new $79/mo price must be created in the Stripe dashboard and the Railway env var updated to match.

This is a pricing correction only. No backend logic, no quota changes, no tier limits. The quote limits (free=5 lifetime, starter=5/mo, professional=25/mo, shop=unlimited) are already correct and must not be touched.

---

## Acceptance Criteria

1. The landing page pricing card for Starter shows **$79/mo** — not $49
2. The in-app upgrade CTA shows **$79/mo** — not $49
3. Any other hardcoded $49 references in the frontend are updated to $79
4. A new Stripe product/price at $79/mo (monthly, recurring) has been created in the Stripe dashboard
5. The `STRIPE_PRICE_STARTER` Railway env var has been updated to the new price ID
6. Existing subscribers on the old $49 price are not affected (Stripe grandfathers them automatically)
7. All existing tests pass — no regressions

---

## Constraint Architecture

**In scope:**
- `frontend/index.html` — Starter price card
- `frontend/landing.html` — Starter price card  
- `frontend/js/quote-flow.js` — upgrade CTA text
- Stripe dashboard — create new $79/mo price
- Railway env vars — update `STRIPE_PRICE_STARTER`

**Off limits — do not touch:**
- `backend/routers/auth.py` — TIER_QUOTE_LIMITS is correct, leave it
- `backend/stripe_service.py` — price ID resolution logic is correct
- Any migration files — no DB changes needed
- Any other tier prices ($149 Professional, $349 Shop) — those are already correct

**Must not break:**
- Stripe checkout flow for Professional and Shop tiers
- Existing subscriber sessions
- All passing tests (currently 1236+)

---

## Decomposition

### Part 1 — Frontend copy updates
Find every hardcoded `$49` reference in the frontend files listed above. Update each to `$79`. The upgrade CTA that reads "Starting at $49/mo" should be updated to reflect the correct Starter price.

### Part 2 — Stripe dashboard (manual step, Burton does this)
Create a new Stripe Price for the Starter product:
- Amount: $79.00 USD
- Interval: monthly, recurring
- Copy the new price ID (starts with `price_`)

### Part 3 — Railway env var update (manual step, Burton does this)
In Railway → Variables, update `STRIPE_PRICE_STARTER` to the new price ID from Part 2. Railway will redeploy automatically.

### Part 4 — Verification
Confirm no remaining `$49` references exist in any frontend files. Confirm `$79` appears correctly in the pricing cards on both `index.html` and `landing.html`. Confirm the upgrade CTA in `quote-flow.js` reflects the correct price.

---

## Evaluation Design

**Before:** Landing page and in-app upgrade CTA show $49/mo for Starter tier

**After:**
1. Open `createquote.app` — Starter card shows $79/mo
2. Log in as a free user, run a quote, hit the upgrade CTA — shows $79/mo
3. `grep -rn "\$49" frontend/` returns no results
4. All tests pass: `pytest tests/ -q` shows 0 failures

**Stripe manual verification:**
- Stripe dashboard → Products → Starter → Prices — new $79/mo price exists
- Railway `STRIPE_PRICE_STARTER` matches the new price ID
- Old $49 price still exists in Stripe (inactive/archived, not deleted — existing subscribers need it)

---

## Alembic Note
No migrations needed for this prompt. Do not create any migration files.

---

## CC Commit & Push
After all changes are made and tests pass:
1. Run `pytest tests/ -q` — confirm 0 failures before committing
2. `git add frontend/index.html frontend/landing.html frontend/js/quote-flow.js`
3. `git commit -m "P66: update Starter price display $49 → $79 across frontend"`
4. `git push origin main`

## Deployment
After CC pushes:
1. Burton creates new Stripe price ($79/mo recurring) in Stripe dashboard → copy the new `price_` ID
2. Burton updates Railway → Variables → `STRIPE_PRICE_STARTER` with the new price ID
3. Railway redeploys automatically
4. Test the full checkout flow with BETA-CHECKER account

## Brain Sync
After pushing code, write a session summary to the shared brain vault:

1. `cd ~/brain && git pull origin main`
2. Create `agents/cc-createquote/sessions/YYYY-MM-DD-HHMM.md` with:
   - What was accomplished (Starter price $49 → $79 in 3 frontend files)
   - Files changed: frontend/index.html, frontend/landing.html, frontend/js/quote-flow.js
   - Decisions: Stripe price ID rotation required — Burton creates new $79/mo price, updates STRIPE_PRICE_STARTER in Railway
   - Test result: all tests passing
   - Next steps: Burton creates Stripe price, updates Railway env var
3. `git add -A && git commit -m "cc-createquote session: P66 Starter price update $49→$79"`
4. `git push origin main`
