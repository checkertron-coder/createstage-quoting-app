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

**Chunk 1 — Data layer**
The system needs two new things in the database: a permanent record of NDA acceptance (capturing who agreed, when, from what IP, and under which NDA version — before their account even exists), and a way to lock an invite code to the specific email that first used it. Design the schema, write the migration, make sure NDA acceptance records survive even if the associated user is later deleted.

**Chunk 2 — NDA acceptance backend**
Build an unauthenticated endpoint that records NDA acceptance before registration happens. The challenge: the user doesn't exist yet when they agree, but after registration completes, the system needs to be able to connect that acceptance record to the new user account. Figure out the right mechanism. The acceptance record must be written to the DB at agree-time, not at registration-time.

**Chunk 3 — Invite code hardening + data fix**
Add the one-email-per-code rule to the validation logic: a code that's already been used by one email must reject any different email. After a new user registers with a code, permanently record their email against that code. Then fix the existing data: BETA-FOUNDER must be locked to `info@createstage.co` with max 1 use. All other BETA-* codes must have max_uses=1. BETA-CHECKER must exist as a new code with professional tier and 1 use. This chunk is not done until the DB reflects these values in production.

**Chunk 4 — Free tier limit**
The free tier quote limit is currently 1. It needs to be 5. One-line change in `TIER_QUOTE_LIMITS` in `auth.py`. Simple, but verify the limit is enforced correctly after the change.

**Chunk 5 — NDA modal (frontend)**
Registration currently submits with a Terms checkbox. The NDA agreement must happen as a deliberate, unavoidable step before the form submits — not an afterthought checkbox. The experience should feel like signing something, not clicking through. Key NDA obligations must be visible in the modal itself (not hidden behind a link). The user has exactly two choices: agree or leave. Agreeing calls the backend acceptance endpoint and passes proof of acceptance through to the registration payload. Disagreeing sends them back to the landing page. After agreeing, the NDA state in the form is locked — they cannot uncheck it.

**Chunk 6 — Grand total lockdown (frontend)**
In `quote-flow.js`, the preview mode grand total currently shows `_fmtRange(pq.total)` — a ±20% band around the real number. That's too much information for a free user. Replace it with an upgrade prompt. No number, no range, no dollar sign of any kind. The `_fmtRange()` function itself stays intact — it may be used elsewhere. Just don't call it in the grand total for preview users.

**Chunk 7 — Tests**
Cover: NDA endpoint logs correctly, invite code email-lock enforcement, BETA-FOUNDER rejection for non-Burton emails, BETA-CHECKER one-use behavior, free tier 6th quote blocked, preview grand total contains no currency value.

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
