# PROMPT-62: Security Hardening — Pre-Launch
*Nate B. Jones 5-Primitive Format*
*Run in Claude Code on M4 — working directory: createstage-quoting-app*

---

## 1. PROBLEM STATEMENT

CreateQuote is days away from beta launch with paying users. A security audit found three real vulnerabilities that must be fixed before any money changes hands:

**Vulnerability 1 — CORS wide open**
`backend/main.py` has `allow_origins=["*"]`. Any website on the internet can make authenticated API calls to the backend. A malicious site could trick a logged-in user's browser into making API requests on their behalf.

**Vulnerability 2 — Hardcoded fallback secrets**
`backend/config.py` has `SECRET_KEY: str = "dev-secret-key"` and `JWT_SECRET: str = ""` with no hard failure if missing. `backend/routers/admin.py` has `ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "createstage-admin-2026")` — a publicly guessable default. If Railway env vars are ever missing, the app runs with known-weak secrets.

**Vulnerability 3 — No rate limiting on high-value endpoints**
The login endpoint (`POST /api/auth/login`) has no brute-force protection. The AI quote endpoint (`POST /ai/quote` and `POST /ai/estimate`) has no per-user request throttling — a single user or bot could hammer Anthropic API and cause unbounded cost.

---

## 2. ACCEPTANCE CRITERIA

1. CORS is locked to `https://createquote.app` and `https://www.createquote.app` only. Local dev still works via env var override.
2. App startup fails loudly (raises an exception, refuses to start) if `SECRET_KEY`, `JWT_SECRET`, or `ADMIN_SECRET` are missing or still set to their known-weak defaults.
3. Login endpoint is rate-limited: max 10 attempts per IP per minute. Exceeding returns HTTP 429.
4. AI quote endpoints are rate-limited: max 20 requests per user per hour. Exceeding returns HTTP 429 with a clear message.
5. `slowapi` is added to `requirements.txt` and wired into the FastAPI app.
6. All existing tests pass.
7. A Railway env var checklist comment is added to `backend/config.py` listing every required production secret.

---

## 3. CONSTRAINT ARCHITECTURE

**In scope:**
- `backend/main.py` — CORS fix, slowapi middleware wiring
- `backend/config.py` — startup validation, env var checklist comment
- `backend/routers/admin.py` — remove hardcoded fallback default for ADMIN_SECRET
- `backend/routers/auth.py` — rate limit login endpoint
- `backend/routers/ai_quote.py` — rate limit estimate and quote endpoints
- `requirements.txt` — add `slowapi>=0.1.9`

**Off limits:**
- Do NOT change any business logic, models, or database schema
- Do NOT change auth token logic, JWT structure, or session handling
- Do NOT touch frontend files
- Do NOT change any other routers
- Do NOT modify alembic migrations

**Important — local dev must still work:**
CORS allowed origins should read from an env var `ALLOWED_ORIGINS` that defaults to include `http://localhost:*` and `http://127.0.0.1:*` for local development. In production Railway sets `ALLOWED_ORIGINS=https://createquote.app,https://www.createquote.app`.

---

## 4. DECOMPOSITION

### Chunk 1: Add slowapi to requirements
Add `slowapi>=0.1.9` to `requirements.txt`.

### Chunk 2: Fix CORS in main.py
Replace `allow_origins=["*"]` with a dynamic list read from env var `ALLOWED_ORIGINS`. Parse it as a comma-separated string. If not set, default to `["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:3000", "http://127.0.0.1:8000"]` for local dev safety. Wire in the slowapi `_rate_limit_exceeded_handler` and `Limiter` to the FastAPI app here.

### Chunk 3: Startup validation in config.py
In `backend/config.py`, after the settings class is defined, add a validation function that runs at import time. It should:
- Check that `SECRET_KEY` is not `"dev-secret-key"` or empty in production
- Check that `JWT_SECRET` is not empty in production
- "Production" = when a `PRODUCTION` env var is set to `true` (note: do NOT use `RAILWAY_ENVIRONMENT` — that is a reserved Railway internal Postgres variable)
- If validation fails, raise a `RuntimeError` with a clear message listing which secrets are missing
- Add a comment block listing ALL required Railway env vars: `SECRET_KEY`, `JWT_SECRET`, `ADMIN_SECRET`, `ANTHROPIC_API_KEY`, `DATABASE_URL`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `RESEND_API_KEY`, `APP_URL`, `ALLOWED_ORIGINS`

### Chunk 4: Fix admin secret fallback
In `backend/routers/admin.py`, change:
```python
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "createstage-admin-2026")
```
To read from env with NO fallback. If `ADMIN_SECRET` is not set, the value should be `None`, and the `_require_admin` function should reject ALL requests (return 503 Service Unavailable with message "Admin not configured"). Never a guessable default.

### Chunk 5: Rate limit auth endpoints
In `backend/routers/auth.py`, add slowapi rate limiting:
- `POST /api/auth/login` → 10 per minute per IP
- `POST /api/auth/register` → 5 per minute per IP
- `POST /api/auth/forgot-password` → 5 per minute per IP

Use IP-based key for these (unauthenticated endpoints).

### Chunk 6: Rate limit AI endpoints
In `backend/routers/ai_quote.py`, add slowapi rate limiting:
- `POST /ai/estimate` → 20 per hour per authenticated user (key by user ID from JWT)
- `POST /ai/quote` → 20 per hour per authenticated user

Use user ID as the rate limit key so each paying user gets their own quota, not shared per IP.

---

## 5. EVALUATION DESIGN

### Test 1: CORS locked
Start the app locally. Using curl or httpx, send a request with `Origin: https://evil.com` header. Expected: response does NOT include `Access-Control-Allow-Origin: https://evil.com`.

Send with `Origin: http://localhost:3000`. Expected: response includes `Access-Control-Allow-Origin: http://localhost:3000`.

### Test 2: Startup validation
Temporarily set `PRODUCTION=true` and `SECRET_KEY=dev-secret-key` in local env. Run:
```bash
python3 -c "from backend.config import settings"
```
Expected: raises `RuntimeError` mentioning the weak secret. App refuses to start.

### Test 3: Admin lockout without secret
Unset `ADMIN_SECRET` env var locally. Hit `GET /admin/invite-codes` with any header value. Expected: HTTP 503, not HTTP 403 or 200.

### Test 4: Rate limit login
Send 11 rapid POST requests to `/api/auth/login`. Expected: first 10 return 401 (wrong credentials), 11th returns 429 Too Many Requests.

### Test 5: All existing tests pass
```bash
pytest tests/ -x -q
```
Expected: all pass, no new failures.

---

## Railway Env Var Checklist (do this after code is deployed)

After the code is merged and Railway redeploys, verify ALL of these are set in Railway Variables:
- `SECRET_KEY` — random 32+ char string
- `JWT_SECRET` — random 32+ char string  
- `ADMIN_SECRET` — random string, not guessable
- `ALLOWED_ORIGINS` — `https://createquote.app,https://www.createquote.app`
- `PRODUCTION` — `true` (triggers startup validation — do NOT use RAILWAY_ENVIRONMENT, that's a reserved Postgres internal var)
- `ANTHROPIC_API_KEY` — live key
- `DATABASE_URL` — Railway postgres URL
- `STRIPE_SECRET_KEY` — live `sk_live_...`
- `STRIPE_PUBLISHABLE_KEY` — live `pk_live_...`
- `STRIPE_WEBHOOK_SECRET` — from Stripe dashboard
- `RESEND_API_KEY` — from Resend dashboard
- `APP_URL` — `https://createquote.app`

---

## SAVE POINT

```
git add -A && git commit -m "P62: Security hardening — CORS lockdown, rate limiting, secret validation"
```

*After tests pass and commit is made, write a session summary to `~/brain/agents/cc-createquote/sessions/2026-03-22-p62-security.md` and push to GitHub.*
