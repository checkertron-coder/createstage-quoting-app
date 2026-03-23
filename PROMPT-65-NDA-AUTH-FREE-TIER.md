# PROMPT 65 — NDA Modal, Invite Code Hardening, Free Tier Protection
*Spec-engineered using Nate B. Jones' 5 Primitives*

---

## 1. PROBLEM STATEMENT

Three compounding problems are putting CreateQuote at risk before it has a single paying customer:

**Problem A — NDA is not being acknowledged.**
The registration form has a Terms checkbox. There is no NDA acknowledgment. Beta testers can register, use the platform, and share proprietary AI pricing logic with competitors — with zero legal record of having agreed to confidentiality. The NDA page exists at `/nda` but no user is ever forced to read or acknowledge it.

**Problem B — Invite codes can be shared and abused.**
BETA-FOUNDER has unlimited uses. Other BETA-* codes have `max_uses` set in the model but there is no guarantee they were created with `max_uses=1`. There is no `used_by_email` field — once a code is used once by the right person, nothing stops that person from sharing the code for others to use their remaining quota. BETA-FOUNDER should be locked to Burton's email only (one account, one email, forever).

**Problem C — Free tier exposes real pricing data.**
The grand total on a free quote currently renders as `_fmtRange(pq.total)` — a ±20% range around the actual Opus-computed total. That range is still close enough to the real number that a contractor could use it to price a job without paying. The entire value of CreateQuote is the precision of the estimate. Giving away a ±20% band on a real estimate — even blurred — is giving away the product.

---

## 2. ACCEPTANCE CRITERIA

**NDA Modal:**
- A user attempting to register sees a full-screen modal before the registration form submits
- The modal contains the key NDA language (not a link — the actual text, excerpted)
- There are two and only two buttons: "I Agree — Continue Registration" and "I Do Not Agree — Exit"
- Clicking "I Do Not Agree" closes the modal and returns to the landing page
- Clicking "I Agree" logs the acceptance and proceeds with registration
- After agreeing, the NDA checkbox in the registration form is pre-checked and non-interactive (visually locked)
- The database records: `user_id` (once created), `email`, `ip_address`, `accepted_at` (UTC timestamp), `nda_version` ("2026-03-16"), `user_agent`
- NDA acceptance is logged BEFORE the user account is created (capture IP + timestamp at modal confirm)
- The acceptance record is permanent and non-deletable (no cascade delete from user)

**Invite Code Hardening:**
- A new column `used_by_email` (String, nullable) is added to the `InviteCode` model
- When an invite code is redeemed, `used_by_email` is set to the registering user's email
- Once `used_by_email` is set, the code is rejected for any different email address — error: "This invite code has already been used."
- BETA-FOUNDER is updated: `max_uses = 1`, `used_by_email = "info@createstage.co"` — permanently locked to Burton's account
- All other BETA-* codes (BETA-KEVIN, BETA-JIM, BETA-JASON, BETA-TJ, BETA-ISSAM, and any others) are updated to `max_uses = 1` if not already
- A new invite code `BETA-CHECKER` is created: `max_uses = 1`, `tier = "professional"`, `used_by_email = NULL` (open for first use)

**Free Tier — Hide Real Total:**
- Free tier users (tier="free", subscription_status != "active") no longer see ANY dollar estimate in the grand total area
- Replace the `_fmtRange()` output with a static locked message: "**Upgrade to See Your Full Estimate**"
- The grand total row in preview mode shows no number — only the upgrade CTA
- All other blurred line items ($--- for materials, labor, etc.) remain as-is
- Subtotals and line item breakdowns remain blurred as currently implemented
- Free tier quote limit is updated to **5 quotes** (currently set to 1 in `TIER_QUOTE_LIMITS`)

---

## 3. CONSTRAINT ARCHITECTURE

**In scope:**
- `frontend/js/auth.js` — NDA modal UI, pre-check NDA checkbox after agreement
- `frontend/js/quote-flow.js` — replace `_fmtRange()` call with locked upgrade message in grand total
- `backend/routers/auth.py` — NDA acceptance logging at registration, invite code `used_by_email` enforcement, free tier limit update
- `backend/models.py` — new `NdaAcceptance` table, `used_by_email` column on `InviteCode`
- `backend/alembic/versions/` — migration for new table and column
- Database seed/update script for BETA-FOUNDER lock and BETA-CHECKER creation

**Out of scope — do not touch:**
- NDA content itself (`/nda` route and `nda.html`) — content is correct, do not modify
- Stripe checkout or subscription logic
- Quote generation engine, Opus calls, calculators
- Any existing test that does not cover NDA or invite code behavior
- Existing beta tester accounts already registered — do not retroactively block them

**Must not break:**
- Existing invite code flow for invite_code_record users (auto-verify + immediate token still applies)
- Standard registration flow (no invite code) — verification email path unchanged
- BETA-FOUNDER account (Burton's — already registered, must still work, just block future re-use)
- The `_fmtRange()` function itself — keep it, just don't call it in the grand total for preview users

---

## 4. DECOMPOSITION

**Chunk 1 — Database: NDA acceptance table + invite code column**
Add a `NdaAcceptance` model with: `id`, `email` (indexed), `ip_address`, `user_agent`, `accepted_at`, `nda_version`, `user_id` (nullable FK to users — nullable because acceptance is logged before account creation). Add `used_by_email` (String, nullable) to `InviteCode`. Write and test the Alembic migration.

**Chunk 2 — Backend: NDA acceptance endpoint**
Create `POST /api/auth/nda-accept` — accepts `{email, nda_version}`, reads IP from request, writes to `NdaAcceptance` table, returns `{accepted: true, token: <short-lived acceptance token>}`. This token is passed by the frontend when the registration form submits, so the backend can link the acceptance record to the new user_id after account creation. No auth required (user doesn't exist yet).

**Chunk 3 — Backend: Invite code hardening**
In `_validate_invite_code()`: after confirming code exists and is not expired/max-used, check if `used_by_email` is set and does not match `body.email` — raise 400 "This invite code has already been used." In the registration completion path, after user is created, set `invite_code_record.used_by_email = user.email`. Write a one-time script (or admin endpoint) to: set BETA-FOUNDER `max_uses=1` and `used_by_email="info@createstage.co"`, set all other BETA-* codes to `max_uses=1` if currently NULL or >1, create `BETA-CHECKER` code.

**Chunk 4 — Backend: Free tier limit update**
In `TIER_QUOTE_LIMITS`, update `"free": 1` → `"free": 5`.

**Chunk 5 — Frontend: NDA modal**
In `auth.js`, before the registration form submits (intercept the submit handler), show a full-screen modal overlay. Modal structure:
- Header: "Non-Disclosure Agreement — Required Before Continuing"
- Warning banner (amber/red): "This is a legally binding agreement. Violations will result in legal action."
- Excerpted NDA text block (key sections: Purpose, Obligations, what's prohibited) — enough to read, not the full document. Link to full `/nda` at bottom.
- "I Agree — Continue Registration" button (primary, green)
- "I Do Not Agree — Exit" button (secondary, red/gray)
On agree: call `POST /api/auth/nda-accept`, store the acceptance token in memory, pre-check and disable the NDA checkbox, proceed with form submission (include acceptance token in registration payload).
On disagree: close modal, redirect to `/`.

**Chunk 6 — Frontend: Grand total lockdown for free tier**
In `quote-flow.js`, in `_renderResults()`, where the grand total currently renders `this._fmtRange(pq.total)` for preview mode: replace with a locked element showing "Upgrade to See Your Full Estimate" with a button that calls `Auth.startCheckout('professional')`. No dollar amount, no range, no number of any kind.

**Chunk 7 — Tests**
Write tests covering:
- NDA acceptance endpoint: valid call logs record, returns token
- Invite code `used_by_email` enforcement: second use with different email → 400
- BETA-FOUNDER cannot be used by any email other than info@createstage.co
- BETA-CHECKER can be used once, then blocked
- Free tier quota: 6th quote attempt → 403
- Preview mode grand total: no dollar amount in rendered HTML

---

## 5. EVALUATION DESIGN

**NDA Modal:**
1. Open an incognito window, go to createquote.app, click Register
2. Fill in email + password + invite code → click "Create Account"
3. EXPECTED: NDA modal appears BEFORE account is created
4. Read the modal — key NDA language visible without clicking any link
5. Click "I Do Not Agree" → EXPECTED: redirected to landing page, no account created
6. Repeat, click "I Agree" → EXPECTED: registration proceeds, account created
7. Check DB: `nda_acceptances` table has a row with correct email, IP, timestamp, nda_version="2026-03-16"

**Invite Code Hardening:**
1. Register with BETA-CHECKER → succeeds
2. Try to register again with BETA-CHECKER using a different email → EXPECTED: "This invite code has already been used."
3. Try to register with BETA-FOUNDER using any email other than info@createstage.co → EXPECTED: blocked
4. Burton's existing account still works normally

**Free Tier Grand Total:**
1. Log in as a free tier account (tier=free, no active subscription)
2. Run any quote to completion
3. EXPECTED: grand total area shows "Upgrade to See Your Full Estimate" — no number, no range, no dollar sign
4. Log in as a paid account → grand total shows real number ✅

**Free Tier Quota:**
1. Run 5 quotes on a free account → all succeed
2. Attempt 6th quote → EXPECTED: quota exceeded error / upgrade gate

**Run full test suite after all chunks complete:**
```
python -m pytest tests/ -v
```
All existing tests must pass. New tests must pass.
