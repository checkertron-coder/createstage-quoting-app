# PROMPT 53D: Free Tier Preview Mode — Show the Sizzle, Not the Steak

*Read CLAUDE.md first. Depends on P53 + P53B + P53C being complete.*

---

## Problem Statement

Free tier users (no invite code, no payment) can currently see the full quote and download everything. This means anyone with throwaway emails can use the app for free forever. We need the free tier to be a PREVIEW — enough to make them say "I need this" but not enough to actually use it.

---

## Acceptance Criteria

### Free Tier Preview Mode

When a user's tier is "free" (no invite code, no active subscription), the quote results page shows a **teaser preview** instead of full results:

**What they CAN see (the hook):**
1. **Job type detected** — "Cantilever Sliding Gate" ✅
2. **First 3 items of the cut list** — real pieces with profiles, lengths, quantities. After item 3, show 2-3 more rows that are **blurred/grayed out** with a lock icon overlay.
3. **First 2 steps of the build sequence** — real instructions. Rest blurred.
4. **Section headers visible** — they can see "Materials (12 items)", "Labor (8 processes)", "Hardware (5 items)", "Consumables (4 items)" — the COUNT is visible but the content is blurred.
5. **Total shown as a range** — "Estimated Total: $8,200 – $10,800" (±15-20% of actual total, randomly varied). NOT the exact number.
6. **Material weight total** — show the total weight (e.g., "Total weight: 847 lbs") — it's useful context but doesn't give away pricing.

**What they CANNOT see/do:**
1. **All dollar amounts blurred** — unit prices, line totals, subtotals, labor costs. Visible structure, hidden numbers.
2. **No PDF downloads** — all download buttons show a lock icon + "Upgrade to unlock downloads"
3. **No markup slider** — grayed out with "Available on paid plans"
4. **Cannot copy text** — apply CSS `user-select: none` to the blurred sections (minor friction, not bulletproof)
5. **Labor hours hidden after first 2 processes** — they see "Layout & Setup: 1.5 hrs, Cut & Prep: 2.0 hrs" then the rest is blurred

**The upgrade CTA:**
- A prominent card/banner between the visible and blurred content:
  - **"Want the full quote?"**
  - "Unlock complete cut lists, build instructions, material orders, and professional PDF downloads."
  - **[Upgrade Now →]** button → goes to pricing section or Stripe checkout (once P54 is live)
  - Show the price: "Starting at $49/month"

### Visual Treatment for Blurred Content

Use CSS `filter: blur(4px)` on the restricted rows/sections. Overlay a semi-transparent gradient so it's obviously locked, not broken. Each blurred section has a small 🔒 icon.

```css
.preview-locked {
    position: relative;
    filter: blur(4px);
    user-select: none;
    pointer-events: none;
}
.preview-locked-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(to bottom, rgba(255,255,255,0) 0%, rgba(255,255,255,0.8) 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
}
.preview-lock-icon {
    font-size: 1.5rem;
    color: var(--text-secondary);
}
```

### Registration Form Updates — Capture Phone + Opt-In

Add these fields to the registration form (both Path A invite code and Path B public):

1. **Phone number field** (optional) — placeholder: "Phone number (optional — for text alerts)"
   - Store as `phone` on User model (string, nullable)
   - No validation beyond basic format for now

2. **Marketing opt-in checkbox** — "Send me text & email updates about new features and tips"
   - Store as `marketing_opt_in` (boolean, default false) on User model
   - Store `marketing_opt_in_at` (datetime, nullable) — timestamp for CAN-SPAM compliance
   - This is NOT the terms checkbox — separate opt-in

3. **Profile page** — also show phone number field and opt-in toggle so users can update later

### Email Sending — Resend Integration

Use **Resend** (https://resend.com) for transactional emails. Free tier: 3,000 emails/month.

1. Add `resend` Python package to requirements.txt
2. New env var: `RESEND_API_KEY`
3. New file: `backend/email_service.py` — thin wrapper around Resend API
   - `send_verification_email(to_email, token)` — sends verification link
   - `send_welcome_email(to_email, shop_name)` — sent after first quote generated
   - From address: `noreply@createquote.app` (configure in Resend dashboard with domain verification)
4. If `RESEND_API_KEY` is not set, log a warning and skip email sending (don't crash — allows local dev without Resend)

### Anti-Fraud (Lightweight)

1. **Email verification required** — before a free user can generate a quote, they must click a verification link sent to their email. Add:
   - New field on User model: `email_verified_at` (datetime, nullable)
   - Endpoint: `POST /api/auth/send-verification` — sends email with verification token via Resend
   - Endpoint: `GET /api/auth/verify-email?token=xxx` — verifies and sets timestamp
   - Verification token: URL-safe random token stored in a new `email_verification_tokens` table (token, user_id, expires_at — 24hr expiry)
   - `check_quote_access` blocks free-tier users who haven't verified email
   - Beta invite code users SKIP verification (they're already trusted)
   - Demo link users SKIP verification (they don't even have real emails)
   - After successful registration (free tier), auto-send verification email and show: "Check your email — we sent a verification link to [email]. Verify to start quoting."

2. **IP-based rate limit** — max 2 free account registrations per IP address per 30 days. Store in a simple table:
   - `registration_ips` table: `id`, `ip_address`, `registered_at`
   - Check on registration: if 2+ registrations from this IP in last 30 days AND no invite code → reject with "Registration limit reached. Use an invite code or contact info@CreateQuote.app"

### Implementation in quote-flow.js

The preview mode logic goes in the results rendering. When building the results view:

```javascript
const isPreview = Auth.currentUser?.tier === 'free' || 
                  Auth.currentUser?.subscription_status === 'cancelled';

if (isPreview) {
    // Render preview version with blurred sections
    renderPreviewResults(quoteData);
} else {
    // Render full results (existing code)
    renderFullResults(quoteData);
}
```

`renderPreviewResults()` uses the same data but:
- Shows first 3 material items normally, rest wrapped in `.preview-locked`
- Shows first 2 build steps normally, rest wrapped in `.preview-locked`
- Replaces all `$XX.XX` amounts with blurred placeholder
- Replaces exact total with range
- Disables download buttons
- Inserts the upgrade CTA card after the visible content

---

## Constraint Architecture

### Files to CREATE
- `backend/email_service.py` — Resend API wrapper (send_verification_email, send_welcome_email)
- `alembic/versions/xxx_add_email_verification_and_ip_tracking.py` — migration

### Files to MODIFY
- `backend/models.py` — add to User: `email_verified_at`, `phone`, `marketing_opt_in`, `marketing_opt_in_at`. Add `EmailVerificationToken` model. Add `RegistrationIP` model.
- `backend/routers/auth.py` — add verification endpoints, IP rate limit on registration, skip verification for invite code + demo users, accept phone + marketing_opt_in on register
- `backend/routers/quote_session.py` — `check_quote_access` blocks unverified free users
- `frontend/js/auth.js` — add phone number field + marketing opt-in checkbox to registration form + profile page
- `frontend/js/api.js` — pass phone + marketing_opt_in in register call
- `frontend/js/quote-flow.js` — add `renderPreviewResults()` function + preview mode detection
- `frontend/css/style.css` — add preview/blur styles, upgrade CTA card styles
- `requirements.txt` — add `resend`

### DO NOT TOUCH
- Landing page (P53C just polished it)
- AI pipeline, calculators, PDF generator
- Existing test files

---

## Decomposition

### Chunk 1: Models + Migration + Email Service → COMMIT
- Add User fields: `email_verified_at`, `phone`, `marketing_opt_in`, `marketing_opt_in_at`
- Add `EmailVerificationToken` model
- Add `RegistrationIP` model
- Create migration (idempotent)
- Create `backend/email_service.py` (Resend wrapper — graceful skip if no API key)
- Add `resend` to requirements.txt
- ✅ `pytest tests/ -v`

### Chunk 2: Auth Backend Updates → COMMIT
- Add send-verification and verify-email endpoints
- Add IP rate limiting to registration
- Accept phone + marketing_opt_in on register
- Skip verification for invite code + demo users
- Auto-send verification email on free registration
- Update `check_quote_access` to require email verification for free tier
- ✅ `pytest tests/ -v`

### Chunk 3: Frontend Registration + Profile Updates → COMMIT
- Add phone number field to registration form
- Add marketing opt-in checkbox
- Add phone number + opt-in toggle to profile page
- Pass new fields in API register call
- Show "Check your email" message after free registration
- ✅ App starts, manual test

### Chunk 4: Frontend Preview Mode → COMMIT
- Add `renderPreviewResults()` to quote-flow.js
- Preview blur CSS (first 3 materials, first 2 build steps visible, rest blurred)
- Blur all dollar amounts for free tier
- Total as range (±15-20%)
- Lock download buttons with "Upgrade to unlock"
- Upgrade CTA card between visible and blurred content
- ✅ App starts, manual test

### Chunk 5: Tests → COMMIT
- Test email verification flow (send, verify, expired token)
- Test IP rate limiting (2 per IP, 3rd blocked)
- Test free tier sees preview (blurred content, range total, locked downloads)
- Test paid tier sees full results
- Test beta code users skip verification
- Test demo users skip verification
- Test phone + marketing_opt_in stored on registration
- ✅ `pytest tests/ -v` — all pass

**Do NOT push until all 5 chunks pass.**

---

## Evaluation

### Manual Tests
1. Register free (no invite code) → email verification sent → must verify before quoting
2. Register free from same IP 3 times → 3rd registration blocked
3. Register with invite code → no verification needed, full access immediately
4. Register with demo link → no verification needed
5. Free user generates quote → sees 3 cut list items + 2 build steps, rest blurred
6. Free user sees total as range, not exact number
7. Free user clicks download → sees "Upgrade to unlock"
8. Paid user generates quote → sees everything, full downloads
9. Upgrade CTA visible between visible and blurred content
10. Phone number field shows on registration + profile
11. Marketing opt-in checkbox shows on registration
12. Profile page shows phone + opt-in toggle

### Automated Tests
- Minimum 15 new tests
