# PROMPT 65B — Email Verification Gate Fix
*Spec-engineered using Nate B. Jones' 5 Primitives*

---

## 1. PROBLEM STATEMENT

Users who register WITHOUT an invite code are supposed to receive an email verification link before gaining access. Instead, they are being granted immediate access with no email sent.

The root cause is a dev-mode fallback in `backend/routers/auth.py` that unconditionally sets `email_verified = True` and issues tokens if `email_service.is_configured()` returns False. In production on Railway, `RESEND_API_KEY` IS set and `is_configured()` should return True — but the fallback is still running. This means either: (a) `is_configured()` is returning False in production for an unknown reason, or (b) the fallback is being reached before the `is_configured()` check.

The result: every user who registers without an invite code gets in immediately, the NDA acceptance record exists but is never tied to a verified email, and the email gate is completely non-functional in production.

---

## 2. ACCEPTANCE CRITERIA

- A user who registers without an invite code receives a verification email and cannot log in until they verify
- A user who registers WITH a valid invite code is auto-verified and logs in immediately (this behavior is intentional — do not change it)
- The dev-mode fallback (`email_verified = True` on line ~458) is removed entirely or guarded such that it NEVER runs in production (`PRODUCTION=1`)
- If `RESEND_API_KEY` is set and `email_service.is_configured()` returns True but email sending fails (exception), the user sees an error — not silent auto-verify
- Add logging at every branch of the registration path so future failures are visible in Railway logs
- Existing verified users are not affected

---

## 3. CONSTRAINT ARCHITECTURE

**In scope:**
- `backend/routers/auth.py` — the registration endpoint, specifically the block starting at "Standard registration — require email verification before granting access"
- `backend/email_service.py` — add debug logging so `is_configured()` result is visible in Railway logs on every registration attempt
- `backend/config.py` — confirm PRODUCTION env var is accessible and check if it can be used as a secondary guard

**Out of scope — do not touch:**
- Invite code auto-verify path (lines ~445-450) — intentional, leave it alone
- NDA modal, invite code hardening — P65 work is correct
- Any calculator, quote, or PDF logic
- Frontend

**Must not break:**
- Invite code users: auto-verify + immediate token issuance
- Password reset email flow
- Existing logged-in sessions

---

## 4. DECOMPOSITION

**Chunk 1 — Diagnose why is_configured() may be returning False in production**
Add a log statement at the top of the registration endpoint that logs: `is_configured()` result, whether `RESEND_API_KEY` env var is present (bool, not the value), and the `PRODUCTION` env var value. Deploy and trigger a registration to see what Railway logs show. This tells us whether Resend is truly configured from the app's perspective at runtime.

**Chunk 2 — Remove the unconditional dev bypass**
The fallback block (lines ~457-461) that sets `email_verified = True` when email service is not configured must be replaced with a hard error in production. The logic should be: if email is configured → send verification email and require it. If email is NOT configured AND we're in production → raise a 500 with a clear error ("Email service not configured — cannot complete registration"). If email is NOT configured AND we're NOT in production → dev mode auto-verify is acceptable. This eliminates the silent bypass in production.

**Chunk 3 — Harden the email send path**
Currently if `_send_verification_email()` fails (exception), the registration silently succeeds without sending the email. The user gets no email and no error. Fix this: if `_send_verification_email()` returns False or raises, return an error to the user ("Failed to send verification email — please try again") rather than silently proceeding or auto-verifying.

**Chunk 4 — Tests**
- Test: non-invite-code registration with email configured → returns `verification_required`, no token issued
- Test: non-invite-code registration with email NOT configured + PRODUCTION=0 → dev auto-verify (existing behavior preserved for local dev)
- Test: non-invite-code registration with email NOT configured + PRODUCTION=1 → 500 error
- Test: invite code registration → immediate token, email_verified=True (unchanged)

---

## 5. EVALUATION DESIGN

1. Register a new account on createquote.app WITHOUT an invite code
2. EXPECTED: "Check your email to verify your account" message — no access granted
3. EXPECTED: Verification email arrives at the registered address
4. Log into Railway → check deployment logs → confirm `is_configured()` logged as True
5. Click verification link in email → EXPECTED: account activated, can now log in
6. Register WITH a valid invite code → EXPECTED: immediate access, no email required
7. Run full test suite: `python -m pytest tests/ -v` → all pass

---

## ADDENDUM — Invite Code Lock Not Working in Live DB

### Additional Problem Found After P65 Deploy

The `used_by_email` lock logic is correct in code but failed silently for codes that already existed in the DB before P65 ran. The `auto_seed()` function uses `if not existing: db.add(...)` — so pre-existing codes like BETA-CHECKER were skipped entirely. Their `used_by_email` was never set after first use, meaning the lock never fired.

### Additional Acceptance Criteria

- After a code is used for the first time, `used_by_email` is immediately set to that email — verified in the DB
- A code that has `uses >= max_uses` AND `used_by_email` already set must reject any new registration attempt regardless of email
- The `auto_seed()` hardening block must run on EVERY deploy (not just first-time), updating `used_by_email` for all codes that have `uses > 0` but `used_by_email = NULL` — backfill from the `invite_code_used` field on the User model
- BETA-CHECKER specifically: if it has `uses=1` and `used_by_email=NULL` in the live DB, backfill `used_by_email` from the user who used it

### Additional Decomposition Chunk

**Chunk 5 — Backfill used_by_email for existing codes**
In `auto_seed()`, after the new-code creation block, add a backfill pass: query all InviteCodes where `used_by_email IS NULL` and `uses > 0`. For each, find the User record where `invite_code_used = code.code` and set `code.used_by_email = user.email`. This repairs the live DB state without a migration.

### Additional Evaluation

1. After deploy: check DB — BETA-CHECKER should have `used_by_email` set to the email that used it
2. Try registering with BETA-CHECKER using any email → EXPECTED: "This invite code has already been used"
3. Try with a fresh unused code → works once, locked on second attempt with different email

---

## DEPLOYMENT — REQUIRED FINAL STEP

After all chunks are complete and the full test suite passes:

1. `git add -A`
2. `git commit -m "P65B: email verification gate fix + invite code backfill"`
3. `git push origin main`

Do not consider this prompt done until the push is confirmed and Railway deploys successfully. Verify by checking `https://createquote.app/health` returns `{"status": "ok"}`.

## BRAIN SYNC — REQUIRED AFTER DEPLOY

After Railway confirms healthy:

1. `cd ~/brain && git pull origin master`
2. Write a session summary to `agents/cc-createquote/sessions/2026-03-23-p65b-email-verify.md` covering:
   - What was broken and why
   - What was changed (files + line numbers)
   - Current state of email verification in production
   - Current state of invite code locking in production
3. `git add -A && git commit -m "P65B: email verify fix + invite code backfill" && git push origin master`

---

## ADDENDUM — BETA-CHECKER Code Reset

BETA-CHECKER was used by an unauthorized email during testing. It must be reset so the Checker test account can use it.

In `auto_seed()`, after the backfill pass, add a specific reset for BETA-CHECKER:
- Find the BETA-CHECKER invite code record
- Set `uses = 0`
- Set `used_by_email = NULL`

This runs on every deploy (idempotent is fine — if uses=0 and used_by_email=NULL already, no change). After this reset, BETA-CHECKER is clean and ready for the Checker test account to use once.
