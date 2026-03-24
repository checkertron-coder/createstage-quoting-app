# PROMPT 65C — NDA Flow Fix, Tier Limits, Invite Codes, Data Cleanup
*Spec-engineered using Nate B. Jones' 5 Primitives*

---

## 1. PROBLEM STATEMENT

Three problems are blocking beta testers from getting clean access to CreateQuote:

**Problem A — NDA fires for everyone.**
The NDA modal currently fires for ALL registrations. The NDA is a beta tester agreement — it has nothing to do with a public user signing up for the free tier. Showing a legal agreement to every new user is bad UX and legally unnecessary. It should only fire when an invite code is present.

**Problem B — Email verification isn't enforced for invite code users.**
Beta testers with invite codes are getting immediate app access without verifying their email. The correct flow is: NDA agreement → account created → verification email sent → verify → access. Right now the verification step is being skipped for invite code users.

**Problem C — Invite codes are leaking.**
BETA-CHECKER was used by an unauthorized email during testing. Test accounts were created with real emails that need to be reusable. The DB has dirty data that must be cleaned before real beta testers onboard.

---

## 2. ACCEPTANCE CRITERIA

**Beta tester flow (invite code present):**
- User enters email + password + invite code → clicks "Create Account"
- NDA modal fires BEFORE account is created
- "I Do Not Agree" → redirect to landing page, no account created
- "I Agree" → NDA acceptance logged to DB (email, IP, timestamp, nda_version="2026-03-16")
- Account is created, invite code locked to this email
- Verification email sent immediately
- User sees "Check your email" — NO app access until verified
- After clicking verification link → full professional tier access

**Public user flow (no invite code):**
- User enters email + password → clicks "Create Account"
- NO NDA modal — straight to registration
- Verification email sent
- User sees "Check your email" — NO app access until verified
- After verification → free tier access (5 quotes, blurred output, no dollar total shown)

**Tier limits (update these values):**
- Free tier: 5 quotes lifetime, blurred output, grand total hidden (shows upgrade CTA only — no number, no range)
- Starter tier: 5 quotes per month, full output

**New invite code:**
- BETA-JEROMY — professional tier, 1 use max, locked to first email that registers with it

**Both flows:**
- No auto-verify bypass in production under any circumstances
- `https://createquote.app/health` returns `{"status": "ok"}` after deploy

---

## 3. CONSTRAINT ARCHITECTURE

**In scope:**
- `frontend/js/auth.js` — NDA modal gating on invite code presence
- `backend/routers/auth.py` — email verification enforcement for all registration paths, invite code flow
- `backend/main.py` — auto_seed: add BETA-JEROMY, reset BETA-CHECKER, update tier limits, data cleanup on startup
- `backend/routers/auth.py` — TIER_QUOTE_LIMITS: free=5, starter=5

**Out of scope — do not touch:**
- NDA modal content, design, or acceptance logging endpoint — correct as-is
- Invite code validation logic beyond what's needed for email enforcement
- Any calculator, quote, PDF, or Stripe logic
- Tests unrelated to registration flow

**Must not break:**
- Burton's account (info@createstage.co) — already verified, must still log in normally
- All other existing verified users — sessions must not be invalidated
- The `_fmtRange()` function — keep it, just don't call it for free tier grand total

---

## 4. DECOMPOSITION

**Chunk 1 — NDA modal gating**
The NDA modal exists to create a legal record when a beta tester — someone in a trust relationship with CreateQuote — gains access. A public free tier user has no such relationship. The modal must only appear when the person registering has an invite code. The check happens at submit time: if the invite code field is empty, skip the modal entirely.

**Chunk 2 — Email verification for all paths**
Currently invite code users bypass email verification and get immediate access. This is wrong — invite code users are exactly the people we most need to verify, because they're getting real professional-tier access. Both registration paths must end the same way: verification email sent, access blocked until the link is clicked. The invite code grants professional tier and triggers the NDA — it does not grant a bypass on email verification.

**Chunk 3 — Tier limit updates**
Free tier lifetime quote limit needs to be 5. Starter monthly limit needs to be 5. The landing page pricing copy must reflect these values accurately. The free tier grand total must show no dollar amount — not a range, not a blurred number, nothing. An upgrade CTA only.

**Chunk 4 — Data cleanup and seed updates**
At startup, before the app serves any requests:
- Delete the following test accounts and all associated data (tokens, NDA records, quotes): ninetydias@gmail.com, burtonlmusic@gmail.com, burton@createstage.com, burton@createstage.co
- Reset any invite codes used by those accounts: set uses=0, used_by_email=NULL
- Reset BETA-CHECKER: set uses=0, used_by_email=NULL so the Checker test account can use it
- Add BETA-JEROMY to the seed list: professional tier, max_uses=1
- All cleanup must be idempotent — if accounts don't exist, nothing happens

**Chunk 5 — Tests**
Prove both flows end to end:
- Invite code path: NDA fires, email gate enforced, no immediate token, verification required
- No invite code path: no NDA, email gate enforced, no immediate token, verification required  
- Free tier: grand total shows no dollar amount
- Starter tier: 5 quote monthly limit enforced
- Data cleanup: test accounts absent, BETA-CHECKER reset, BETA-JEROMY exists
- Existing verified user (Burton) login unaffected

---

## 5. EVALUATION DESIGN

**Beta tester test:**
1. Incognito → createquote.app → Register
2. Enter email + password + BETA-JEROMY → "Create Account"
3. EXPECTED: NDA modal appears
4. Click "I Agree"
5. EXPECTED: "Check your email" screen — no app access
6. Click verification link in email
7. EXPECTED: access granted, professional tier

**Public user test:**
1. Incognito → Register with email + password, no invite code
2. EXPECTED: no NDA modal, "Check your email" screen
3. Verify email → free tier, 5 quote limit, grand total hidden

**Existing user test:**
1. Burton logs in with info@createstage.co → works normally

**Full test suite:**
```
python -m pytest tests/ -v
```
All existing tests pass. New tests pass.

---

## DEPLOYMENT — REQUIRED FINAL STEP

After all chunks complete and full test suite passes:

1. `git add -A`
2. `git commit -m "P65C: NDA invite-only, email verify all paths, tier limits, data cleanup"`
3. `git push origin main`

Verify `https://createquote.app/health` returns `{"status": "ok"}` after Railway deploys.

---

## BRAIN SYNC — REQUIRED AFTER DEPLOY

1. `cd ~/brain && git pull origin master`
2. Write session summary to `agents/cc-createquote/sessions/2026-03-23-p65c.md` covering: what changed, current registration flow state, tier limits, invite codes active
3. `git add -A && git commit -m "P65C: NDA invite-only + email verify + tier limits" && git push origin master`
