# PROMPT-63: Email Verification Gate + Stripe Checkout Fix
*Nate B. Jones 5-Primitive Format*
*Run in Claude Code on M4 — working directory: createstage-quoting-app*

---

## 1. PROBLEM STATEMENT

Three critical bugs discovered during live testing on 2026-03-22 with a real email (`burtonlmusic@gmail.com`). The app is publicly live and being marketed. These bugs allow unauthorized access and break the payment flow.

**Bug 1 — Registration returns JWT tokens before email is verified**
In `backend/routers/auth.py`, the register endpoint calls `_issue_tokens(user, db)` and returns them immediately after sending the verification email. This means the user gets a valid access token and is logged into the app BEFORE they verify their email. The login endpoint correctly blocks unverified users, but registration bypasses it entirely by issuing tokens upfront. A user can register, skip verification, and use the app indefinitely on their registration token.

**Bug 2 — Stale verification link (already used)**
The user received a verification email but the link said "already used" when clicked. This means either: (a) a previous verification token existed for that email from an earlier attempt and was already consumed, or (b) the token is being marked used before the user clicks it. Either way, the resend verification flow is not generating a fresh token — it's resending a stale or already-consumed one.

**Bug 3 — Stripe checkout redirects to home instead of Stripe**
When a free-tier user clicks "Upgrade" or selects a plan, the checkout silently fails and redirects to the home/landing page. Root cause: Railway env vars for Stripe Price IDs use wrong names. Code in `backend/stripe_service.py` reads `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_PROFESSIONAL`, `STRIPE_PRICE_SHOP` — but Railway has them set as `STRIPE_STARTER_PRICE_ID`, `STRIPE_PRO_PRICE_ID`, `STRIPE_SHOP_PRICE_ID`. All three resolve to empty strings, causing silent failure.

---

## 2. ACCEPTANCE CRITERIA

1. **Registration no longer issues tokens to unverified users.** After registering without an invite code, the response tells the user to check their email. No JWT tokens issued. No app access. Period.
2. **Resend verification always generates a fresh token.** Old unused tokens for that email+type are invalidated before creating a new one. The user always gets a working link.
3. **Invite code users are exempt from email verification** — they already have verified intent. They get tokens immediately as before.
4. **Stripe checkout works.** A free-tier logged-in user who clicks Upgrade gets redirected to a real Stripe checkout page.
5. **Frontend handles the unverified state gracefully.** After registration without invite code, user sees a clear "Check your email" screen, not a broken app state.
6. All existing tests pass.

---

## 3. CONSTRAINT ARCHITECTURE

**In scope:**
- `backend/routers/auth.py` — registration token logic, resend verification logic
- `backend/stripe_service.py` — fix env var names for Price IDs
- `frontend/js/auth.js` or wherever registration response is handled — show "check your email" state
- `frontend/index.html` or relevant template — handle unverified user state on load

**Off limits:**
- Do NOT change the login endpoint — it already correctly blocks unverified users
- Do NOT change invite code flow — invite code users should still get tokens immediately
- Do NOT change models, migrations, or any other routers
- Do NOT change the Stripe webhook handler
- Do NOT change the admin bypass logic

**Critical constraint:**
The fix for Bug 1 must NOT break the existing beta invite code flow. Users registering WITH a valid invite code should still receive tokens immediately — they are trusted. Only users registering WITHOUT an invite code (standard public registration) must go through email verification before getting tokens.

---

## 4. DECOMPOSITION

### Chunk 1: Fix registration — no tokens until verified (non-invite users)
In `backend/routers/auth.py`, find the register endpoint. After `_send_verification_email(user, db)` is called:
- If user has NO invite code: return a response with NO tokens. Return `{"message": "verification_required", "email": user.email}` — no access_token, no refresh_token.
- If user HAS invite code: keep existing behavior — issue tokens immediately (these users are trusted).

The frontend must handle a registration response that has no tokens. It should show a "Check your email to verify your account" screen with the user's email displayed.

### Chunk 2: Fix resend verification — always fresh token
In `backend/routers/auth.py`, find `_send_verification_email` and the resend endpoint (`POST /api/auth/resend-verification`). Before creating a new token:
- Query the database for any existing unused (not yet consumed) verification tokens for this user + type "email_verification"
- Delete or invalidate them all
- Then create a fresh token and send it

This ensures the user always gets exactly one valid link. No stale tokens floating around.

### Chunk 3: Fix Stripe Price ID env var names
In `backend/stripe_service.py`, lines ~27-29, change the env var names to match what's in Railway:
```
STRIPE_PRICE_STARTER = os.environ.get("STRIPE_PRICE_STARTER", "")
STRIPE_PRICE_PROFESSIONAL = os.environ.get("STRIPE_PRICE_PROFESSIONAL", "")
STRIPE_PRICE_SHOP = os.environ.get("STRIPE_PRICE_SHOP", "")
```
These are already correct. The fix is: also accept the alternate naming as fallback:
```python
STRIPE_PRICE_STARTER = os.environ.get("STRIPE_PRICE_STARTER") or os.environ.get("STRIPE_STARTER_PRICE_ID", "")
STRIPE_PRICE_PROFESSIONAL = os.environ.get("STRIPE_PRICE_PROFESSIONAL") or os.environ.get("STRIPE_PRO_PRICE_ID", "")
STRIPE_PRICE_SHOP = os.environ.get("STRIPE_PRICE_SHOP") or os.environ.get("STRIPE_SHOP_PRICE_ID", "")
```
This accepts either naming convention so it works regardless of what's in Railway.

### Chunk 4: Frontend — handle verification_required response
In the frontend registration handler (wherever `fetch('/api/auth/register', ...)` is handled):
- If response contains `"message": "verification_required"` (no tokens): do NOT store any tokens, do NOT redirect to app. Show a "verification required" screen: "We sent a verification email to [email]. Click the link in your email to continue."
- Add a "Resend email" button that calls `POST /api/auth/resend-verification`
- Do NOT show the app UI, the quote flow, or any authenticated content

### Chunk 5: Frontend — handle unverified user on load
If somehow a user lands on `/app` without valid tokens (edge case from old sessions), redirect them to the login page cleanly. Do not show broken app state.

---

## 5. EVALUATION DESIGN

### Test 1: Registration without invite code — no app access
Register a new account with a fresh email, no invite code. Expected:
- Response has no `access_token` or `refresh_token`
- Frontend shows "check your email" screen
- Navigating to `/app` redirects to login
- No JWT in localStorage

### Test 2: Registration with invite code — immediate access
Register with a valid beta invite code. Expected:
- Response includes tokens as before
- User is logged in and taken to app/onboarding
- No verification email required

### Test 3: Resend verification — fresh link works
Register without invite code. Call `POST /api/auth/resend-verification` with the email. Click the link. Expected: verification succeeds, user can now log in. Call resend again — get a new link, old link is now invalid.

### Test 4: Stripe checkout — redirects to Stripe
Log in as a free-tier user. Click Upgrade → Professional. Expected: browser redirects to `checkout.stripe.com` with a real session. No redirect to home page.

### Test 5: All existing tests pass
```bash
pytest tests/ -x -q
```
Expected: all pass.

---

## SAVE POINT
```
git add -A && git commit -m "P63: Email verification gate fix + Stripe checkout fix"
git push
```

*After tests pass, write session summary to `~/brain/agents/cc-createquote/sessions/2026-03-22-p63-email-stripe-fix.md` and push to checker-brain.*
