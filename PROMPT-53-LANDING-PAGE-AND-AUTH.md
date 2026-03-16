# PROMPT 53: Landing Page + Auth Overhaul — From Dev Tool to Commercial Product

*Read CLAUDE.md first. This prompt follows the Nate B. Jones 5-Primitive framework.*

---

## Problem Statement

CreateQuote.app currently drops visitors directly into a login/register form with a "Start Quoting Now" guest button. There's no landing page, no product explanation, no pricing, no contact info. This was fine for development — it's unacceptable for a commercial product.

Users need to understand what CreateQuote is, see pricing, have contact info (info@CreateQuote.app), and register with an account before they can access anything. Guest access must be removed entirely. Beta testers need invite codes for free access.

**What the user experiences now:** Blank login box with no context.
**What they should experience:** Professional landing page → Registration (with invite code option) → NDA/Terms acceptance → Shop profile setup → Start quoting.

---

## Acceptance Criteria

### Landing Page (new — loads before any auth)
1. Hero section with:
   - Product name: **CreateQuote**
   - Tagline: "AI-Powered Metal Fabrication Quoting"
   - Subtitle: "Get accurate, itemized quotes in minutes — not hours. Built by fabricators, for fabricators."
   - Primary CTA button: "Get Started" → scrolls to pricing or goes to register
   - Secondary CTA: "See How It Works" → scrolls to features section
2. Features section (3-4 cards):
   - "Describe Your Job" — plain English or upload photos
   - "AI Does the Math" — cut lists, materials, labor, hardware — calculated from real fab knowledge
   - "Professional Quotes in Minutes" — branded PDFs with your shop name and logo
   - "Built for the Shop Floor" — 25+ job types, from gates to LED signs to roll cages
3. How It Works section (3 steps):
   - Step 1: Describe your project
   - Step 2: Answer a few smart questions
   - Step 3: Download your professional quote PDF
4. Pricing section:
   - **Starter** — $49/mo — 10 quotes/month, PDF downloads, 1 user
   - **Professional** — $149/mo — Unlimited quotes, PDF + branding, bid parser, 3 users
   - **Shop** — $349/mo — Everything + API access, priority support, unlimited users
   - All tiers show "Start Free Trial" button (14-day trial, no credit card for beta testers with invite code)
   - Note: Prices are placeholder — Burton will adjust. Build the structure so prices are easily configurable (env vars or config table).
5. Footer:
   - Contact: info@CreateQuote.app
   - Company: CreateStage Fabrication
   - Links: Terms of Service, Privacy Policy, NDA
   - © 2026 CreateStage Fabrication

### Auth Overhaul
1. **Remove guest access entirely.** Delete the `handleGuest()` flow and "Start Quoting Now" button. Every user must register.
2. Registration flow:
   - Email + Password (min 8 chars)
   - **Invite Code field** (optional) — if valid beta code entered, user gets Professional tier free for the beta period
   - Checkbox: "I agree to the [Terms of Service] and [Non-Disclosure Agreement]" — both links open in new tabs. **Registration blocked until checkbox is checked.**
   - On submit: create account → redirect to profile setup → then to quoting
3. Login flow stays the same (email + password).
4. **NDA/Terms pages:** Create static HTML pages at `/terms` and `/nda` served by FastAPI. Content will be placeholder text for now — Burton will add the real legal text later. Structure them with clear sections and professional formatting.

### Invite Code System (Beta Testers)
1. New database table: `invite_codes`
   - `id` (int, PK)
   - `code` (string, unique, indexed) — e.g. "BETA-KEVIN-2026", "BETA-FIRSTWAVE"
   - `tier` (string) — what tier the code grants (default: "professional")
   - `max_uses` (int, nullable) — null = unlimited
   - `uses` (int, default 0)
   - `expires_at` (datetime, nullable)
   - `created_by` (string) — who created it (admin tracking)
   - `created_at` (datetime)
   - `is_active` (boolean, default true)
2. New endpoint: `POST /api/auth/validate-code` — checks if code is valid (exists, active, not expired, not maxed out)
3. Registration endpoint updated: if `invite_code` provided and valid, set user tier accordingly and increment `uses`
4. Admin endpoint: `POST /api/admin/invite-codes` — create new invite codes (protected, admin-only for now — can be a simple shared secret in env var `ADMIN_SECRET`)
5. Seed 3 default codes on first run:
   - `BETA-FOUNDER` — unlimited uses, professional tier, no expiry
   - `BETA-KEVIN` — 1 use, professional tier
   - `BETA-TESTER` — 50 uses, professional tier, expires 90 days from creation

### User Model Updates
1. Add to `users` table:
   - `subscription_tier` (string, default "free") — "free" | "starter" | "professional" | "shop"
   - `subscription_status` (string, default "trial") — "trial" | "active" | "past_due" | "cancelled"
   - `trial_ends_at` (datetime, nullable) — set to 14 days from registration
   - `invite_code_used` (string, nullable) — which code they used
   - `terms_accepted_at` (datetime, nullable) — when they accepted terms
   - `nda_accepted_at` (datetime, nullable) — when they accepted NDA
   - `quotes_this_month` (int, default 0) — for tier-based usage limits
   - `billing_cycle_start` (datetime, nullable)
2. Add middleware/dependency: `check_quote_access(user)` — verifies user can create a new quote based on tier + usage. Returns 403 with clear message if limit reached.
3. Quote limits:
   - Free (no invite code): 1 quote total (demo), then paywall message
   - Starter: 10/month
   - Professional: unlimited
   - Shop: unlimited

### Frontend Structure Change
1. `index.html` becomes the landing page (public, no auth required)
2. New `app.html` — the actual quoting application (requires auth)
3. FastAPI serves:
   - `/` → landing page (`index.html`)
   - `/app` → quoting app (`app.html`) — redirects to `/` if not authenticated
   - `/terms` → Terms of Service page
   - `/nda` → NDA page
   - `/api/*` → all API endpoints (unchanged)

---

## Constraint Architecture

### Files to CREATE
- `frontend/index.html` — new landing page (replaces current login-page version)
- `frontend/app.html` — the quoting application (moved from current index.html logic)
- `frontend/css/landing.css` — landing page specific styles
- `frontend/terms.html` — Terms of Service page
- `frontend/nda.html` — NDA page (placeholder text, professional formatting)
- `backend/routers/admin.py` — admin endpoints (invite code management)
- `alembic/versions/xxx_add_subscription_and_invite.py` — migration

### Files to MODIFY
- `backend/models.py` — add InviteCode model, update User model
- `backend/routers/auth.py` — remove guest, add invite code validation, add terms acceptance
- `backend/routers/quote_session.py` — add `check_quote_access` dependency to `/start`
- `backend/main.py` — add routes for landing, app, terms, nda pages; mount admin router
- `frontend/js/auth.js` — remove guest flow, add invite code field, add terms checkbox
- `frontend/js/app.js` — handle redirect if not authenticated on /app
- `frontend/css/style.css` — may need minor updates for app.html context

### Files NOT to touch
- All calculator files, `ai_cut_list.py`, `claude_client.py`, `labor_estimator.py`
- `quote-flow.js`, `bid-upload.js` — quoting pipeline is untouched
- `weights.py`, `database.py`, `pricing_engine.py`
- Test files (we'll add new tests, not modify existing)

### Hard Rules
- Landing page must load fast — no heavy JS frameworks, no 3D yet (Phase 2)
- Landing page is 100% static HTML/CSS — no API calls until user clicks Register/Login
- Mobile-responsive from day one
- All existing tests must still pass
- The quoting pipeline itself is UNCHANGED — this prompt only touches auth + landing + invite codes

---

## Decomposition

**⚠️ SESSION DISCIPLINE — MANDATORY FOR THIS PROMPT:**
- **Do NOT one-shot this.** Work through chunks sequentially, one at a time.
- **Commit after EACH chunk** with a descriptive message: `git add . && git commit -m "P53 chunk N: description"`
- **Run `pytest tests/ -v` after chunks 1, 2, and 6** to catch regressions early.
- **Verify the app starts (`uvicorn backend.main:app --reload`) after chunk 4** before moving to chunk 5.
- If context gets long after ~30 exchanges, summarize progress and start a fresh session. Read the git log + this file to pick up where you left off.

### Chunk 1: Database + Models → COMMIT
- Add `InviteCode` model to `models.py`
- Add subscription fields to `User` model
- Create Alembic migration
- Seed default invite codes
- ✅ `pytest tests/ -v` — all existing tests still pass

### Chunk 2: Backend Auth Updates → COMMIT
- Remove guest endpoint logic (keep the route but return 410 Gone for backward compat)
- Add invite code validation endpoint
- Update register to accept `invite_code` + `terms_accepted` + `nda_accepted`
- Add `check_quote_access` dependency
- Add admin router for invite code CRUD
- ✅ `pytest tests/ -v` — all existing tests still pass

### Chunk 3: Landing Page → COMMIT
- Create `index.html` with hero, features, how-it-works, pricing, footer
- Create `landing.css`
- Make it look professional — dark header section, clean typography, fabrication-themed

### Chunk 4: App Shell + Auth UI → COMMIT
- Move quoting app into `app.html`
- Update `auth.js` — remove guest, add invite code, add terms checkbox
- Update `app.js` for /app route
- Update `main.py` routing
- ✅ Verify app starts: `uvicorn backend.main:app --reload`

### Chunk 5: Legal Pages → COMMIT
- Create `/terms` and `/nda` pages with professional placeholder text
- NDA page should have prominent language about confidentiality (testers will see this)

### Chunk 6: Tests → COMMIT
- Test invite code CRUD (create, validate, use, expire, max uses)
- Test registration with/without invite code
- Test quote access limits per tier
- Test guest endpoint returns 410
- Test landing page loads (200 on /)
- Test app page requires auth

---

## Evaluation Design

### Manual Tests
1. Visit `createquote.app` → see landing page, not login form
2. Click "Get Started" → goes to registration
3. Register without invite code → gets "free" tier, 1 demo quote
4. Register with `BETA-FOUNDER` → gets "professional" tier, unlimited quotes
5. Try to register without checking terms → blocked
6. After registration → profile setup → quoting works as before
7. Free user creates 1 quote → tries to create another → sees paywall message
8. `/terms` and `/nda` pages load with formatted content
9. Mobile: landing page is fully responsive

### Automated Tests
- `pytest tests/ -v` → all existing 384+ tests still pass
- New test file: `tests/test_landing_and_auth.py` — minimum 15 new tests
- Invite code edge cases: expired code, maxed out code, invalid code, reused code

---

## Design Direction (for the landing page)

- **Color scheme:** Dark hero section (#1a1a2e or similar dark blue/charcoal), white content sections, accent color stays blue (#3b82f6)
- **Typography:** System font stack (already in CSS), hero text large and bold
- **Vibe:** Professional but not corporate. This is a tool for real fabricators, not a Silicon Valley toy. Think: clean, modern, industrial. No stock photos of people in hard hats.
- **Copy tone:** Direct. "Get accurate quotes in minutes" not "Leverage our AI-powered solution to optimize your quoting workflow"
- **Logo:** Just the text "CreateQuote" for now — Burton will add a real logo later

---

## Notes for the AI Builder

- The `tier` field already exists on the User model (line 110: `tier = Column(String, default="basic")`). Rename it to `subscription_tier` for clarity, or keep `tier` and just update the values. Your call — just be consistent.
- Python 3.9 — use `Optional[str]` not `str | None`
- Railway auto-deploys from main. The migration needs to run automatically or be added to the start command.
- info@CreateQuote.app is real — use it in the footer and contact sections.
- Pricing amounts are PLACEHOLDERS. Make them easy to change (config dict at top of a file, or env vars, or a pricing table in the DB).
