# PROMPT 53B: Demo Magic Links + Frictionless Beta Onboarding

*Read CLAUDE.md first. Depends on PROMPT-53 being complete.*

---

## Problem Statement

P53 added registration, invite codes, and landing page. But onboarding is still too heavy for two critical use cases:

1. **"Hey Jim, try my app"** — Burton needs to text someone a link and they're IN. No forms, no registration. Click → quoting.
2. **Beta testers (Kevin, Jason)** — requiring a password on first registration is unnecessary friction. Email + invite code should be enough.

Also: the NDA checkbox in registration is overkill — NDAs for testers are handled separately via DocuSign. Remove it from the registration gate.

---

## Acceptance Criteria

### Demo Links (48-Hour Magic Links)
1. New model: `DemoLink` in `models.py`
   - `id` (int, PK)
   - `token` (string, unique, indexed) — URL-safe random token
   - `created_by_user_id` (int, FK to users)
   - `label` (string, nullable) — "For Jim Lai", "Investor demo" (internal tracking)
   - `tier` (string, default "professional")
   - `max_quotes` (int, default 3)
   - `expires_at` (datetime) — default 48 hours from creation
   - `is_used` (boolean, default false)
   - `used_at` (datetime, nullable)
   - `demo_user_id` (int, FK to users, nullable) — provisional user created on click
   - `created_at` (datetime)
2. Admin endpoint: `POST /api/admin/demo-links`
   - Body: `{ "label": "For Jim Lai", "max_quotes": 3, "expires_hours": 48 }`
   - Returns: `{ "url": "https://createquote.app/demo/<token>", "expires_at": "..." }`
3. Redemption route: `GET /demo/{token}`
   - Validates token (exists, not expired, not used beyond max)
   - Creates provisional user automatically (no email, no password, no forms)
   - Sets JWT cookie/token
   - Redirects to `/app`
4. Demo user experience:
   - Subtle banner at top of app: "Demo Mode — X quotes remaining | [Register for full access →]"
   - Can generate quotes, download PDFs, see the full pipeline
   - After `max_quotes` reached → show "Demo limit reached — register for full access"
   - After 48 hours → token expired message with register CTA
5. Quote transfer: if demo user later registers with a real account, all demo quotes transfer to the new account

### Frictionless Beta Registration
1. When an invite code is entered, password becomes OPTIONAL
   - Show password field but with placeholder: "Set a password (optional — you can do this later)"
   - If no password provided, account is created as provisional (like current guest flow, but with email + tier set)
   - User can set password later in Profile
2. Flow: email → invite code → terms checkbox → click "Get Started" → in the app. 10 seconds max.

### Remove NDA Gate
1. Remove NDA checkbox from registration form
2. Remove `nda_accepted_at` field from User model if P53 added it
3. Keep `/nda` page live (it's useful as a reference) but it's not a registration blocker
4. Terms checkbox stays — that's standard legal protection

---

## Constraint Architecture

### Files to CREATE
- `alembic/versions/xxx_add_demo_links.py` — migration for demo_links table

### Files to MODIFY
- `backend/models.py` — add DemoLink model, remove nda_accepted_at if present
- `backend/routers/admin.py` — add demo link CRUD endpoints
- `backend/routers/auth.py` — make password optional when invite code is valid, add demo token redemption
- `backend/routers/quote_session.py` — check_quote_access must respect demo link limits
- `backend/main.py` — add /demo/{token} route
- `frontend/js/auth.js` — password optional when invite code entered, remove NDA checkbox
- `frontend/app.html` (or index.html) — demo banner component

### DO NOT TOUCH
- Landing page (P53 just built it)
- Calculator files, AI pipeline, quote-flow.js
- Stripe (that's P54)
- Any existing test files

---

## Decomposition

### Chunk 1: DemoLink Model + Migration → COMMIT
- Add DemoLink to models.py
- Create migration
- Remove nda_accepted_at if it exists
- ✅ `pytest tests/ -v`

### Chunk 2: Demo Link Backend → COMMIT
- Admin endpoint to create demo links
- Redemption endpoint (token → provisional user → JWT → redirect)
- Quote access check respects demo limits
- ✅ `pytest tests/ -v`

### Chunk 3: Frontend Updates → COMMIT
- Demo banner in app ("Demo Mode — X quotes remaining")
- Password optional when invite code entered
- Remove NDA checkbox from registration
- ✅ App starts, manual click-through

### Chunk 4: Tests → COMMIT
- Test demo link creation
- Test demo link redemption (valid, expired, maxed)
- Test demo user quote limit enforcement
- Test quote transfer on registration
- Test passwordless beta registration
- ✅ `pytest tests/ -v` — all tests pass

---

## Evaluation Design

### Manual Tests
1. Create demo link via admin endpoint → get URL
2. Open URL in incognito → land directly in app, no forms
3. Generate 3 quotes → try 4th → "Demo limit reached" message
4. Register with real email → demo quotes appear in new account
5. Register with invite code, skip password → account works
6. Set password later in Profile → works

### Automated Tests
- Minimum 10 new tests in `tests/test_demo_links.py`
