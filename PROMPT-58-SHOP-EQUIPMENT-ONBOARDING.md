# PROMPT-58: Shop Equipment Profile — Conversational Onboarding

## Problem Statement

Every quote CreateQuote generates today is shop-agnostic. Opus doesn't know if the shop has a TIG welder or only flux core. It doesn't know if they have a plasma table or a torch. It doesn't know if they send out for powder coat or do it in-house.

This means quotes suggest processes the shop can't actually perform, miss outsourcing costs when they apply, and ignore capabilities the shop has that could save money. A mobile welder with stick only should get a completely different quote than a full fab shop with a plasma table and press brake.

The fix is a shop equipment profile — built through a short conversational onboarding flow — that Opus reads before generating every quote. From that point forward, every quote is specific to THIS shop's actual capabilities.

---

## Acceptance Criteria

1. A new user who completes registration is prompted to set up their shop profile before their first quote
2. The onboarding is conversational — a short series of plain-language questions, not a form with dropdowns
3. The questions cover three areas: welding & cutting processes, forming & fabrication equipment, and finishing capabilities
4. When the user answers, Opus interprets the free-text responses and stores a structured equipment profile
5. A user can update their shop profile at any time from their account settings
6. When Opus generates a quote, it receives the shop's equipment profile as context
7. A shop with only flux core MIG gets quotes that reflect flux core labor rates and limitations — not TIG assumptions
8. A shop that sends out for finishing gets outsource cost estimates — not in-house finishing labor
9. A shop with a plasma table gets plasma cut times — a shop without one gets torch or saw alternatives
10. The profile is visible to the user — they can see what the system thinks they have and correct it
11. All existing tests pass

---

## Constraint Architecture

**In scope:**
- `backend/models.py` — new `ShopEquipment` table linked to User
- `alembic/versions/` — migration for new table
- `backend/routers/shop_profile.py` — new router: GET/POST/PUT equipment profile
- `backend/shop_context.py` — new module: builds Opus-readable shop context string from DB
- `backend/routers/quote_session.py` — inject shop context into Opus prompt at quote time
- `frontend/` — onboarding flow UI (shown after first login if profile incomplete), settings page section to view/edit profile

**Off limits:**
- Do not change the quote calculation logic
- Do not change existing Opus prompts — ADD shop context as a prepended block, do not restructure existing prompts
- Do not change auth, billing, or PDF generation
- Do not build a fixed list of equipment — the system should handle any equipment a user describes

**Must not break:**
- Existing quote flow — if a user has no equipment profile, quotes continue to work exactly as before (Opus uses its general fabrication knowledge)
- Any existing passing test

---

## Decomposition

### Chunk 1: Data model

The shop equipment profile needs to store what processes and capabilities a shop has. Design the model to be flexible — not a fixed list of equipment types, but a structure that can represent any combination of welding processes, cutting tools, forming equipment, and finishing capabilities.

Key things to capture per shop:
- Welding processes available (and for each: whether it's the primary process, any limitations)
- Cutting capabilities — and critically: distinguish between a hand plasma cutter (handheld torch, operator-guided) vs. a CNC plasma table (machine-guided, programmatic cuts, dramatically different speed, precision, and nesting capability). A shop with a CNC plasma table can also use the torch by hand, but the table changes everything about cut time estimates and part complexity. A "plasma table" with no CNC is just a flat slat table used as a cutting surface — it does NOT have automated cutting capability.
- Forming equipment (press brake with tonnage/bed length/die count, tube bender, etc.)
- Finishing (in-house spray, powder coat oven, media blast, or sends out)
- Fixture table, clamps, any noteworthy shop infrastructure
- A free-text "shop notes" field for anything that doesn't fit categories
- `onboarding_complete` boolean on User

Add `onboarding_complete` to the User model. Create a `ShopEquipment` table. Write the Alembic migration.

### Chunk 2: Onboarding conversation flow

Create a new onboarding UI that appears after first login when `onboarding_complete` is False.

The flow asks three conversational questions — one at a time, not all at once:

**Question 1 — Welding & Cutting:**
"What welding and cutting processes do you have in your shop? (For example: MIG with flux core, TIG, stick, oxy-acetylene torch, hand plasma cutter, CNC plasma table, cold saw — or just tell us what you've got)"

**Question 2 — Forming & Fabrication:**
"What forming equipment do you work with? (Press brake, tube bender, fixture table, anything for shaping metal)"

**Question 3 — Finishing:**
"How do you handle finishing? (In-house spray paint, powder coat oven, media blaster — or do you send out for coating?)"

Each answer is free text. After all three answers are collected, send them to a new endpoint that passes them to Opus for structured interpretation and storage. Show the user a summary of what was captured and let them confirm or edit before saving.

### Chunk 3: Opus interprets the answers

New endpoint `POST /api/shop/onboarding` accepts the three free-text answers. Sends them to Opus with a prompt that teaches it:

- What the three question areas cover
- That it should extract structured capabilities from the free-text answers
- That missing information is fine — don't invent capabilities the user didn't mention
- That the output should be stored as a structured equipment profile

Opus returns a structured profile. Store it in `ShopEquipment`. Set `onboarding_complete = True` on the user.

### Chunk 4: Shop context builder

Create `backend/shop_context.py` with a single function `build_shop_context(user_id, db)`.

This function reads the user's equipment profile from DB and formats it into a concise, Opus-readable context block. Example output:

```
SHOP CAPABILITIES:
- Welding: MIG (flux core only), no TIG, no stick
- Cutting: Hand plasma cutter (no CNC table), angle grinder, cold saw
- Forming: No press brake — outsource bending
- Finishing: Sends out for powder coat, no in-house spray
- Notes: Mobile-capable, single operator
```

If no profile exists, return an empty string — Opus falls back to general knowledge.

### Chunk 5: Inject shop context into quotes

In `backend/routers/quote_session.py`, before the Opus prompt is sent for quote generation, call `build_shop_context()` and prepend the result to the Opus prompt as a context block.

Teach the prompt: this shop's capabilities define what processes are realistic. If a process is unavailable in-house, Opus should note outsourcing and estimate outsource cost rather than in-house labor. If a process IS available, use the shop's actual equipment to estimate setup and run time.

### Chunk 6: Profile settings UI

Add a "Shop Equipment" section to the account settings page. Shows the current profile in a readable format. Allows the user to edit any field or redo the onboarding conversation entirely. Uses the same Opus interpretation endpoint as onboarding.

### Chunk 7: Tests

- Onboarding endpoint stores profile correctly
- `build_shop_context()` returns correct formatted string for a known profile
- `build_shop_context()` returns empty string when no profile exists
- Quote session with shop context injects the context block into the Opus prompt
- Existing quote tests still pass (no profile = no change in behavior)

---

## Evaluation Design

### Test 1: Onboarding happy path
- New user completes onboarding with answers about their shop
- Profile saved in DB with correct capabilities extracted by Opus
- `onboarding_complete` set to True
- User sees accurate summary of what was captured

### Test 2: Context injection
- User has a profile with "flux core MIG only, no TIG"
- Generate a quote for a job that would normally suggest TIG welding
- Verify the Opus prompt contains the shop context block
- Verify the quote reflects flux core assumptions, not TIG

### Test 3: Outsource path
- User profile has "sends out for powder coat"
- Generate a quote for a job requiring powder coat finishing
- Quote should include outsource line item for finishing, not in-house labor

### Test 4: No profile fallback
- User with no equipment profile generates a quote
- Quote generates normally — no errors, Opus uses general knowledge

### Test 5: Profile edit
- User edits their profile in settings
- New quote reflects updated profile

### Test 6: Regression
- `pytest tests/ -x -q` — all existing tests pass

---

## Save Point

```
git add -A && git commit -m "P58: Shop equipment profile — conversational onboarding + Opus context injection"
```
