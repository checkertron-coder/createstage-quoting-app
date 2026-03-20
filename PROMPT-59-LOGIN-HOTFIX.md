# PROMPT-59: Login Hotfix — Show/Hide Password + Auth Debug

## Problem Statement

Three issues blocking the owner from logging into CreateQuote:

**1. No password visibility toggle**
The password field on the login page has no show/hide toggle. Users cannot see what they're typing. This makes debugging login issues impossible and is standard UX that should have been there from day one.

**2. Session expires and user cannot log back in without clearing browser**
The JWT access token expires after 15 minutes. When it expires, the frontend should silently use the refresh token to get a new access token. Instead, the app fails with "invalid email or password" or just stops working. The user logs in once successfully, then cannot get back in on the next visit or after the token expires. The refresh token flow exists in the backend but the frontend is not using it correctly.

**3. Login intermittently returns "invalid email or password" for valid credentials**
After P57 deployed (email verification), users who have verified their email and know their correct password are getting rejected on login. The error message "invalid email or password" is a catch-all that hides the real cause. This needs to be diagnosed and fixed.

Suspected causes:
- The `email_verified` flag may be getting reset to `False` unexpectedly
- The password hash may be getting corrupted or reset during password reset flows
- The `APP_ADMIN_EMAIL` env var bypass may not be working correctly

---

## Acceptance Criteria

1. The login page has a show/hide toggle on the password field (eye icon, toggles between `type="password"` and `type="text"`)
2. The same toggle exists on the register page and reset-password page
3. A user with verified email and correct password can log in successfully every time
4. If login fails due to unverified email, the error message clearly says "Please verify your email" — not "invalid email or password"
5. If login fails due to wrong password, the error says "invalid email or password"
6. Add a diagnostic log line on every login attempt in the backend: log the email, whether the user was found, whether password matched, and whether email_verified is True/False — this goes to Railway logs for debugging
7. All existing tests pass

---

## Constraint Architecture

**In scope:**
- `frontend/js/auth.js` — show/hide toggle, fix token refresh flow
- `frontend/css/style.css` — eye icon styling
- `backend/routers/auth.py` — login endpoint: better error distinction + diagnostic logging
- `frontend/login.html` (or wherever login form lives) — add toggle button to password input

**Off limits:**
- Do not change password hashing logic
- Do not change the verification gate logic — just improve the error message
- Do not change any other endpoints

---

## Decomposition

### Chunk 1: Fix token refresh flow

In `frontend/js/auth.js`, find where API calls are made. When any API call returns 401:
- Automatically call `POST /api/auth/refresh` with the stored refresh token
- On success: store the new access token, retry the original request
- On failure (refresh token also expired): redirect to login page

This must be a global interceptor — every API call goes through it. A user should never see "invalid email or password" because their token silently expired. They should only ever be redirected to login if their refresh token has also expired (30 days).

Also extend the access token lifetime in `backend/config.py` from 15 minutes to 60 minutes — 15 minutes is too aggressive for a tool that people use actively.

### Chunk 2: Show/hide password toggle
Add an eye icon button inside the password input wrapper on login, register, and reset-password pages. Clicking it toggles the input between `type="password"` and `type="text"`. Standard pattern. Use an inline SVG or a simple text toggle if no icon library is available.

### Chunk 2: Diagnostic logging in login endpoint
In `backend/routers/auth.py` login function, add a log line after each decision point:
- User lookup: found or not found
- Password check: matched or failed
- Email verified check: True or False
- Admin bypass: triggered or not

These go to `logger.info()` so they appear in Railway logs. Never log the actual password.

### Chunk 3: Improve error message for unverified email
Currently the frontend may be showing "invalid email or password" even when the real issue is unverified email (the backend returns 403 with a different detail). Make sure the frontend correctly reads the 403 response and shows the verification message + resend button — not the generic password error.

### Chunk 4: Check for email_verified reset bug
In the login endpoint, after successful password verification, before the email_verified check — add a log line showing the current value of `user.email_verified` from the database. This will confirm whether the flag is actually False in the DB or whether something else is causing the failure.

---

## Evaluation Design

### Test 1: Show/hide toggle
- Open login page
- Type password — characters are hidden
- Click eye icon — characters are visible
- Click again — characters are hidden again

### Test 2: Login with valid credentials
- Use verified account with correct password
- Login succeeds, redirected to app

### Test 3: Login with unverified email
- Use account with `email_verified = FALSE`
- Login shows verification message + resend button (not "invalid email or password")

### Test 4: Railway log check
- Attempt login
- Check Railway logs — see the diagnostic line showing email, found=True, password_match=True, email_verified=True/False

### Test 5: Regression
- `pytest tests/ -x -q` — all existing tests pass

---

## Save Point

```
git add -A && git commit -m "P59: Login hotfix — show/hide password toggle + auth diagnostic logging"
```
