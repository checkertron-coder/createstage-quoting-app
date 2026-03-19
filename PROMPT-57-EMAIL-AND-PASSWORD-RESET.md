# PROMPT-57: Email Infrastructure — Password Reset + Email Verification

## Problem Statement

CreateQuote has no email system whatsoever. No password reset. No email verification on registration. This means:

- A user who forgets their password is permanently locked out — no recovery path exists
- A user can register with any email address they don't own — no proof of ownership
- Admin (Burton) cannot reset any user's password without direct database access

This is a production blocker. Real beta users will forget passwords. Real users need to own their email. This must be built before any non-beta users are onboarded.

There is currently zero email infrastructure in the codebase — no SMTP config, no email library, no email templates. We're building it from the ground up.

---

## Acceptance Criteria

1. A user can click "Forgot Password" on the login page, enter their email, and receive a password reset link within 60 seconds
2. The password reset link is valid for 1 hour and single-use — clicking it twice shows an error
3. After clicking the reset link, the user sets a new password and is immediately logged in
4. New registrations trigger a verification email — the user gets a "Verify your email" link
5. Verification links are valid for 48 hours
6. Unverified accounts can still log in and use the app (don't block access — just nudge)
7. The email sender is configurable via environment variable (`SMTP_FROM` or equivalent)
8. The system degrades gracefully when no email config is present — log a warning, don't crash
9. All existing tests pass

---

## Constraint Architecture

**In scope:**
- `backend/config.py` — add SMTP/email env vars
- `backend/email_service.py` — new file, handles all email sending
- `backend/models.py` — add `PasswordResetToken` table, add `email_verified` boolean to `User`
- `alembic/versions/` — migration for new table + new column
- `backend/routers/auth.py` — new endpoints for forgot-password, reset-password, verify-email
- `frontend/` — forgot password link on login page, password reset page, email verification nudge

**Email provider: Resend**
Use the Resend API (https://resend.com) — it's the simplest modern email API, Python SDK available (`resend` package). Add to `requirements.txt`. Config variable: `RESEND_API_KEY`. If not set, log a warning and skip sending.

**Off limits:**
- Do not change quote calculation logic
- Do not change Stripe billing
- Do not change any existing auth flow (login, register, refresh tokens still work exactly as before)
- Do not add email verification as a hard gate — users can use the app without verifying

**Must not break:**
- Existing invite-code registration flow
- Demo user / magic link flow
- JWT token system

---

## Decomposition

### Chunk 1: Email service layer

Create `backend/email_service.py`. This module owns all email sending.

It reads `RESEND_API_KEY` from settings. If the key is missing or empty, every send function logs a warning and returns `False` instead of crashing.

Implement three functions:
- `send_password_reset(email, reset_url)` — sends a reset link with 1-hour expiry notice
- `send_email_verification(email, verify_url)` — sends a verification link with 48-hour expiry notice
- `send_welcome(email, shop_name)` — simple welcome email on first registration (optional but nice)

Email design: plain, professional. No heavy HTML. The app is called CreateQuote. Sender name: "CreateQuote" from whatever address the `RESEND_FROM` env var specifies (default: `noreply@createquote.app`).

Add `RESEND_API_KEY` and `RESEND_FROM` to `backend/config.py` with empty string defaults.
Add `resend` to `requirements.txt`.

### Chunk 2: Database — password reset tokens + email_verified flag

In `backend/models.py`:
- Add `email_verified: bool` column to `User` (default `False` for new users, `True` for existing — migration should set existing rows to `True` so current users aren't broken)
- Add a new `PasswordResetToken` table with: `id`, `user_id` (FK), `token_hash` (String, the hashed token — never store plain), `expires_at` (DateTime), `used_at` (DateTime, nullable), `created_at` (DateTime)

Generate a new Alembic migration. Existing users get `email_verified = True`.

### Chunk 3: Forgot password + reset password endpoints

In `backend/routers/auth.py`, add three new endpoints:

**POST `/api/auth/forgot-password`**
- Body: `{ "email": "user@example.com" }`
- Behavior: Look up the user. If found, generate a secure random token (32 bytes, URL-safe), hash it, store in `PasswordResetToken` with 1-hour expiry. Send reset email via `email_service.send_password_reset()`. Always return 200 with a generic message ("If that email exists, a reset link was sent") — never confirm or deny whether the email exists.

**POST `/api/auth/reset-password`**
- Body: `{ "token": "...", "new_password": "..." }`
- Behavior: Hash the incoming token, look up matching `PasswordResetToken` where `used_at` is null and `expires_at` is in the future. If valid, update the user's `password_hash`, mark the token `used_at = now()`, issue new access + refresh tokens, return them. If invalid/expired, return 400.

**GET `/api/auth/verify-email?token=...`**
- Behavior: Similar token lookup (use a separate token type or a flag on PasswordResetToken — implementer's choice). Mark user `email_verified = True`. Return 200 with a redirect hint or success message.

### Chunk 4: Trigger emails at the right moments

In the registration flow (`POST /api/auth/register`):
- After successfully creating a user, generate a verification token and call `send_email_verification()`
- If email service isn't configured, skip silently

In the forgot-password endpoint (Chunk 3):
- Already covered — just connect it

### Chunk 5: Frontend — forgot password flow

On the login page (`frontend/login.html` or wherever login lives):
- Add a "Forgot password?" link below the login form
- Link to a `/forgot-password` page (new HTML page)

New page `frontend/forgot-password.html`:
- Simple form: email input + submit button
- On submit, POST to `/api/auth/forgot-password`
- Show: "If that email is registered, a reset link has been sent."
- Match the existing app visual style

New page `frontend/reset-password.html`:
- Reads `?token=` from the URL
- Shows: new password input + confirm password input + submit
- On submit, POST to `/api/auth/reset-password` with the token + new password
- On success: redirect to login (or auto-login if tokens are returned)
- On error: show "This reset link has expired or already been used."

### Chunk 6: Email verification nudge (non-blocking)

After login, if `user.email_verified` is `False`, show a dismissible banner at the top of the app:
- "Please verify your email address. [Resend verification email]"
- Clicking "Resend" calls a new endpoint `POST /api/auth/resend-verification` which generates a new token and sends the email
- Do NOT block the app or any features — this is a nudge only

### Chunk 7: Tests

Add tests covering:
- Forgot password with unknown email returns 200 (no leak)
- Forgot password with known email creates a token in DB
- Reset password with valid token succeeds and marks token used
- Reset password with expired token returns 400
- Reset password with already-used token returns 400
- Email verify endpoint marks `email_verified = True`

---

## Evaluation Design

### Test 1: Password reset happy path
- Register a new account
- POST `/api/auth/forgot-password` with that email → 200
- Find the reset token in the DB (for testing, return it in response only in test mode, or query directly)
- POST `/api/auth/reset-password` with token + new password → 200, returns access token
- Login with new password → succeeds

### Test 2: Reset token single-use
- Use the same token twice
- Second use returns 400

### Test 3: Reset token expiry
- Manually set `expires_at` to the past in DB
- Attempt reset → 400

### Test 4: Email not found — no leak
- POST `/api/auth/forgot-password` with nonexistent email
- Returns 200 with generic message (same as valid email)

### Test 5: Email verification
- Register → `email_verified` is False
- Hit verify endpoint with valid token → `email_verified` is True

### Test 6: Regression
- `pytest tests/ -x -q` — all existing tests pass

---

## Railway Environment Variables Needed

After deploying, Burton needs to set in Railway:
- `RESEND_API_KEY` — from https://resend.com (free tier: 3,000 emails/month)
- `RESEND_FROM` — verified sender address (e.g., `noreply@createquote.app` or `noreply@createstage.com`)

---

## Save Point

```
git add -A && git commit -m "P57: Email infrastructure — password reset + email verification (Resend)"
```
