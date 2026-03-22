# PROMPT-64: Fix All Stripe Checkout Entry Points
*Nate B. Jones 5-Primitive Format*
*Run in Claude Code on M4 — working directory: createstage-quoting-app*

---

## 1. PROBLEM STATEMENT

A logged-in free-tier user cannot upgrade to a paid plan. Every "Subscribe" button in the app either silently fails or routes to the wrong place. No Stripe checkout session is ever created. The user cannot pay.

Three broken entry points identified through live testing:

**Entry Point 1 — Purple upgrade banner in `/app`**
`frontend/js/auth.js` line ~116: banner link is `href="/#pricing"` — sends user to landing page instead of calling Stripe.

**Entry Point 2 — Quote preview CTA inside `/app`**
`frontend/js/quote-flow.js` line ~1611 and ~1619: "Subscribe — Starting at $49/mo" button and surrounding code redirect to `/#pricing` instead of calling Stripe.

**Entry Point 3 — Landing page pricing buttons**
`frontend/index.html` inline `handlePricingClick()` function: checks `localStorage.getItem('access_token')` and tries to call `/api/stripe/create-checkout` directly. This silently fails because `index.html` does NOT load `api.js` or `auth.js` — the CORS-safe fetch headers and token refresh logic don't exist here. The catch block redirects to `/app#register` → shop onboarding.

**Root cause of Entry Point 3:** The landing page is a standalone HTML file with no shared JS infrastructure. It should NOT attempt to call the backend directly. Instead, it should detect a logged-in user and redirect them into the app where the real checkout infrastructure exists.

---

## 2. ACCEPTANCE CRITERIA

1. A logged-in free-tier user who clicks any "Subscribe" button anywhere in the app gets redirected to a real Stripe checkout page.
2. No "Subscribe" button ever routes to shop onboarding or the landing page pricing section.
3. A logged-out user who clicks "Subscribe" on the landing page goes to `/app#register` (correct — they need to register first).
4. After successful payment, user lands on `/app?checkout=success` and their tier is upgraded.
5. After cancelled payment, user lands on `/app?checkout=cancelled` with no change to their account.
6. All existing tests pass.

---

## 3. CONSTRAINT ARCHITECTURE

**In scope:**
- `frontend/js/auth.js` — fix upgrade banner link
- `frontend/js/quote-flow.js` — fix quote preview CTA
- `frontend/index.html` — fix `handlePricingClick` to redirect into app instead of calling API directly
- `frontend/app.html` or wherever `/app` handles `?upgrade=` query param — add handler if needed

**Off limits:**
- Do NOT change backend — `POST /api/stripe/create-checkout` is working correctly
- Do NOT change `api.js` token logic
- Do NOT change `Auth.startCheckout()` in `auth.js` — it works, just isn't being called
- Do NOT change any auth flow, registration, or invite code logic
- Do NOT change any other routers or backend files

**Key constraint:**
The landing page (`index.html`) must NEVER call backend APIs directly. It has no token refresh, no error handling infrastructure, no `api.js`. All checkout must happen from within `/app` where `Auth.startCheckout()` and `API.headers()` are available.

---

## 4. DECOMPOSITION

### Chunk 1: Fix the upgrade banner (`frontend/js/auth.js`)
Find the free-tier upgrade banner HTML (around line 116). Change:
```
<a href="/#pricing">Subscribe to unlock full quotes &rarr;</a>
```
To call `Auth.startCheckout('professional')` directly:
```
<a href="#" onclick="Auth.startCheckout('professional');return false;">Subscribe to unlock full quotes &rarr;</a>
```

### Chunk 2: Fix the quote preview CTA (`frontend/js/quote-flow.js`)
Find all instances (~lines 1611, 1619) where free-tier preview routes to `/#pricing`. Change every one to call `Auth.startCheckout('professional')` instead:
- Any `window.location.href = '/#pricing'` in the upgrade context → `Auth.startCheckout('professional')`
- Any `<a href="/#pricing"` in the upgrade CTA → `<a href="#" onclick="Auth.startCheckout('professional');return false;"`

### Chunk 3: Fix landing page checkout (`frontend/index.html`)
The `handlePricingClick(tier)` function currently:
1. Checks for token in localStorage
2. If found: tries to fetch `/api/stripe/create-checkout` directly (WRONG — no api.js here)
3. If not found: follows href to `/app#register` (correct)

Replace the "logged in" path entirely. When a token exists in localStorage, redirect the user INTO the app with a query param instead of calling the API:

```javascript
function handlePricingClick(tier) {
    var token = localStorage.getItem('access_token');
    if (!token) return true; // Not logged in — follow href to /app#register
    // Logged in — redirect into app to handle checkout with full JS infrastructure
    window.location.href = '/app?upgrade=' + encodeURIComponent(tier);
    return false;
}
```

### Chunk 4: Handle `?upgrade=` param in the app (`frontend/app.html` or main app JS)
When `/app` loads with `?upgrade=professional` (or starter/shop) in the URL:
- Wait for auth to initialize (user must be logged in)
- If logged in: call `Auth.startCheckout(tier)` automatically
- If not logged in: clear the param and show login

Find where the app handles other URL params like `?checkout=success` and add `upgrade` handling in the same place.

---

## 5. EVALUATION DESIGN

### Test 1: Banner → Stripe (logged in, inside app)
Log in as free user. See purple banner. Click "Subscribe to unlock full quotes". Expected: browser redirects to `checkout.stripe.com` with a real session. Network tab shows `POST /api/stripe/create-checkout` returning `{"url": "https://checkout.stripe.com/..."}`.

### Test 2: Quote preview CTA → Stripe (logged in, inside app)
Run a quote as free user. See blurred results with "Subscribe — Starting at $49/mo". Click it. Expected: same as Test 1 — Stripe checkout page.

### Test 3: Landing page button → Stripe (logged in)
Go to `createquote.app`. Click any Subscribe button while logged in. Expected: redirects to `/app?upgrade=professional`, which then fires Stripe checkout automatically.

### Test 4: Landing page button → register (logged out)
Clear localStorage. Go to `createquote.app`. Click Subscribe. Expected: goes to `/app#register`. No API call attempted.

### Test 5: All existing tests pass
```bash
pytest tests/ -x -q
```
Expected: all pass.

---

## SAVE POINT
```
git add -A && git commit -m "P64: Fix all Stripe checkout entry points — banner, quote CTA, landing page"
git push
```

*After tests pass, write session summary to `~/brain/agents/cc-createquote/sessions/2026-03-22-p64-stripe-checkout.md` and push to checker-brain.*
