# PROMPT-57: Email Infrastructure — Password Reset + Email Verification

## Problem Statement

CreateQuote has no email system. No password reset. No email verification on registration. This means a user who forgets their password is permanently locked out, and anyone can register with an email address they don't own. Real beta users will hit both of these walls immediately.

There is no email infrastructure in the codebase — no library, no config, no templates. It must be built from scratch.

---

## Acceptance Criteria

1. A user who forgets their password can request a reset link from the login page and receive it by email within 60 seconds
2. The reset link works exactly once and expires after 1 hour — a second click shows a clear error
3. After resetting, the user is immediately logged in
4. Every new registration triggers a verification email with a link the user must click before they can log in
5. Verification links expire after 48 hours
6. A user who has not verified their email cannot log in — they see a clear message explaining why, with a button to resend the verification email
7. All existing users are treated as unverified after this deploys — they must verify their email on next login
8. One admin account (configured via environment variable) bypasses the verification gate and can always log in
9. If no email API key is configured, the system logs a warning and continues without crashing — no silent failures, no broken boots
10. All existing tests pass

---

## Constraint Architecture

**In scope:**
- `backend/config.py` — new email env vars
- `backend/email_service.py` — new module, owns all email sending
- `backend/models.py` — new token table, new verified flag on User
- `alembic/versions/` — migration (all existing users start unverified)
- `backend/routers/auth.py` — new endpoints: forgot-password, reset-password, verify-email, resend-verification
- `frontend/` — forgot password link on login page, new forgot-password page, new reset-password page, verification error state on login

**Email provider: Resend**
Python SDK: `resend` package. Add to `requirements.txt`. Two new env vars: `RESEND_API_KEY` and `RESEND_FROM`. If `RESEND_API_KEY` is empty, skip sending and log a warning.

**Off limits:**
- Quote calculation logic — do not touch
- Stripe billing — do not touch
- Existing auth flow for login, register, token refresh — extend, do not replace
- Demo user / magic link flow — must continue to work

**Must not break:**
- Invite-code registration
- JWT token system
- Any existing passing test

---

## Decomposition

### Chunk 1: Email service

Create `backend/email_service.py` — a single module that owns all outbound email. It must handle three scenarios: password reset, email verification, and welcome on first registration.

Teach it the following about each email:
- **Password reset**: the user needs a link, knows it expires soon, and needs to act immediately
- **Email verification**: the user just registered and needs to confirm ownership before they can use the app
- **Welcome**: friendly first-touch after registration (optional, send alongside verification)

The emails should feel professional and minimal — no heavy HTML, no marketing fluff. The product is called CreateQuote. Sender identity comes from config.

Add `RESEND_API_KEY`, `RESEND_FROM`, `APP_URL`, and `APP_ADMIN_EMAIL` to `backend/config.py` with safe defaults.

### Chunk 2: Data model

The system needs to store time-limited, single-use tokens for both password reset and email verification. Design a token table that supports both use cases — consider how to distinguish token type, how to mark a token as used, and how to enforce expiry.

Add an `email_verified` boolean to the `User` model.

Write an Alembic migration. The migration must set `email_verified = FALSE` for all existing rows — this is intentional, not an oversight. Every existing user must verify on next login.

### Chunk 3: Backend endpoints

Extend `backend/routers/auth.py` with:

**Forgot password** — accepts an email address, sends a reset link if the account exists. Never reveals whether the email is registered.

**Reset password** — accepts the token from the reset link and a new password. Validates the token (unused, unexpired), updates the password, and returns fresh auth tokens so the user is immediately logged in.

**Verify email** — accepts the token from the verification link. Marks the user as verified. Redirects or returns a success response the frontend can act on.

**Resend verification** — accepts an email address, sends a new verification link if the account is unverified. Invalidates any previous unused verification tokens for that account. Never reveals whether the email is registered.

### Chunk 4: Login gate

In the login endpoint, after password verification succeeds, check whether the user is verified. If not — and if the account is not the configured admin account — refuse to issue tokens. Return a response the frontend can distinguish from a wrong-password error, so it can show the right message and the resend button.

### Chunk 5: Registration trigger

After a new user is successfully created, send a verification email. If the email service is not configured, skip silently — registration still succeeds.

### Chunk 6: Frontend

**Login page changes:**
- Add "Forgot password?" link below the form
- Handle the unverified-user response: show a message explaining verification is required, with a "Resend verification email" button that calls the resend endpoint

**New: forgot-password page** — email input, submit sends the request, confirmation message shown after. Match existing app visual style.

**New: reset-password page** — reads token from URL, shows new password + confirm fields, submits to reset endpoint. On success, redirects to app (auto-logged-in). On failure, shows that the link is expired or already used.

### Chunk 7: Tests

Cover the full lifecycle: request reset → use token → token consumed. Cover expiry and double-use. Cover the verification gate blocking login. Cover the admin bypass. Cover the resend flow. Cover that existing-user migration sets everyone to unverified.

---

## Evaluation Design

### Test 1: Full password reset flow
- Register → request reset → use token → login with new password succeeds
- Use the same token again → fails with clear error

### Test 2: Verification gate
- Register → attempt login → blocked (unverified)
- Click verify link → attempt login → succeeds

### Test 3: Resend verification
- Register → resend verification → old token invalidated, new token works

### Test 4: Admin bypass
- Set admin email in config → that account logs in without verifying

### Test 5: No email leak
- Forgot password with nonexistent email → same response as valid email

### Test 6: Existing users blocked
- After migration, all pre-existing users have `email_verified = FALSE`
- They cannot log in until they verify

### Test 7: Regression
- `pytest tests/ -x -q` — all existing tests pass, no new failures

---

## Railway Environment Variables

Set these in Railway before deploying:
- `RESEND_API_KEY` — from resend.com (free tier: 3,000 emails/month)
- `RESEND_FROM` — sending address (`onboarding@resend.dev` works on free tier without domain setup)
- `APP_URL` — production URL (used to build links in emails)
- `APP_ADMIN_EMAIL` — the one account that bypasses email verification (set to `info@createstage.co`)

---

## Save Point

```
git add -A && git commit -m "P57: Email infrastructure — password reset + email verification gate"
```
