# PROMPT 33 — Trust Opus: Materials Intelligence, Field Extraction, Output Polish

Read `KNOWLEDGE.md`, `DECISIONS.md`, and `CLAUDE.md` before starting. They contain accumulated domain knowledge from 33 prompt iterations, architectural decisions, and the full system architecture.

---

## 1. Problem Statement

CS-2026-0042 produces a working quote with both PDFs (shop copy and client proposal), a full fab sequence, and a correct detailed cut list. The system has come a long way — individual pieces, correct dimensions, proper hardware, consumables, and a professional client proposal.

But five categories of issues remain that make the output unprofessional, the UX frustrating, and the materials section useless for actually ordering steel:

### The Question Tree UX Problem
A fabricator types a detailed job description: "12' wide, cantilever sliding gate, 10' tall, with square tube frame and picket infill. Paint finish. Full site installation. 13' fence on one side, 15' fence on other, 4 fence posts." The system currently ignores everything in that description and asks the fabricator to manually re-enter every single field — opening width, height, frame material, infill type, finish, installation type, fence lengths, fence posts. That's 20+ questions when the description already answered 10+ of them. This is a terrible user experience. A fabricator will abandon the app after the second quote if they have to re-type everything they already wrote.

### The Materials List Problem
The materials section currently shows 30+ individual line items:
```
Gate top rail - 2x2 sq tube, 216"    sq_tube_2x2_11ga    1    $44.90
Gate bottom rail - 2x2 sq tube, 216"    sq_tube_2x2_11ga    1    $44.90
Gate leading stile - 2x2 sq tube, 116"    sq_tube_2x2_11ga    1    $24.11
Fence Side 1 - top rail, 2x2 sq tube    sq_tube_2x2_11ga    1    $16.21
...and 25 more lines like this...
```

This is not how you order steel. Nobody walks into Osorio Metals and says "I need one 216-inch piece of 2x2 at $44.90 and one 116-inch piece of 2x2 at $24.11." You walk in and say "I need 345 feet of 2x2 11ga." The materials list should be a steel order — aggregated by profile with total linear footage and a price per foot. You should be able to hand this list to your distributor and get a quote back.

The detailed cut list is where individual pieces belong — that's the shop bible. The materials list is the purchasing document.

### The Plate Stock Problem
When a quote includes plate pieces (mounting plates, cap plates, gusset plates, bumper plates, latch plates), they're currently listed as individual items with per-inch pricing that makes no sense. In reality:

- You don't buy "6 inches of 1/4 plate." You buy a half sheet (24" × 48") or full sheet (48" × 96") and cut your pieces from it.
- BUT — if you need a few large pieces (like 10" × 10" × 1/4" base plates for railing posts), it might be cheaper and faster to buy pre-cut plate drops or stock pieces from the distributor rather than buying a whole sheet and wasting 90% of it.
- Cutting plate pieces from sheet stock is real labor (layout, plasma/torch cut, edge deburring) that needs to be in the labor hours.
- This is the same mental math every fabricator does at the distributor counter.

### The Grind Hours Problem
Grind & Clean shows 8.6 hours for an outdoor painted gate+fence job. It should be 2-3 hours. The root cause: every picket is counted as 2 individual grind joints. With 141 pickets, that's 282 joints × 1 min = 282 minutes just for pickets. But pickets welded into pre-punched channel don't need per-picket cleanup — you weld through the holes and do a quick pass down the channel run.

### The Sonnet Ghost Problem
Claude Sonnet is still hardcoded as the "deep" model default in `claude_client.py` despite being fully replaced by Opus. The assumptions section of every quote says "claude-sonnet-4-6" even though Opus is generating. There should be zero Sonnet references anywhere in the codebase.

### The Output Polish Problems
- Dimensions appear without units ("1/4 plate" instead of "1/4\" plate", "116" instead of "116\"")
- Concrete footings appear in the cut list as if they're linear steel stock
- Pre-punched channel uses the wrong profile key (`flat_bar_2x0.25` instead of `punched_channel_1.5x0.5_fits_0.625`)
- Fence Side 2 rail lengths add up to 228" for a 180" fence

---

## 2. Acceptance Criteria

A quote generated from the test description below must satisfy ALL of these:

**Test description:**
```
12' wide, cantilever sliding gate, 10' tall, with square tube frame and picket infill. Paint finish. Full site installation. 13' fence on one side, 15' fence on other, 4 fence posts.
```

### Question Tree
- [ ] Fields clearly stated in the description are pre-filled and not re-asked
- [ ] Only fields NOT in the description appear as questions (latch type, motor, picket size, picket spacing, picket top style, mid-rail type, paint color, post size, bottom guide, counterbalance space, roller carriage, gauge/thickness, tubing size, site access, decorative elements)
- [ ] Progress indicator reflects pre-filled fields accurately

### Materials Section (Shop PDF + Website)
- [ ] One row per profile type — not one row per piece
- [ ] Linear stock (tube, bar, channel, angle, pipe, HSS) shows: material description, total footage, $/ft, line total
- [ ] Total footage × $/ft = line total (math checks out)
- [ ] Plate stock shows smart purchasing: sheet orders for many small pieces, pre-cut pieces for few large pieces, or a mix — whichever is more cost-effective for the specific job
- [ ] Plate cutting labor is included in labor hours when pieces are being cut from sheet stock
- [ ] Concrete shows as a separate summary line with cubic yards — not in the cut list, not treated as linear stock
- [ ] Material subtotal is the sum of all line totals

### Cut List (Unchanged)
- [ ] Every individual piece still listed with its specific length and quantity
- [ ] Detailed cut list with notes still present
- [ ] This is the shop's fabrication reference — do not aggregate or simplify

### Dimensions & Units
- [ ] Every dimension in the entire output has its unit explicitly shown
- [ ] Inches = `"`, feet = `'` — no exceptions anywhere (cut list, materials, fab sequence, notes, descriptions)
- [ ] No naked numbers without units

### Labor
- [ ] Grind & Clean hours reflect outdoor painted cleanup theory (not indoor furniture-grade grinding), with picket cleanup counted per channel run not per picket, and scaling proportionally to project size
- [ ] Plate cutting labor reflected when applicable

### AI & Model
- [ ] Zero "sonnet" references in entire codebase
- [ ] Assumptions say "claude-opus-4-6"

### Materials List Download
- [ ] "Materials List" download button appears alongside Shop Copy and Client Copy
- [ ] Materials list contains only: material descriptions, total footage, stock lengths, number of sticks/sheets needed
- [ ] NO estimated prices, NO labor, NO markup, NO job details
- [ ] Clean enough to email directly to a steel distributor for a real quote

### Existing Features (Do Not Break)
- [ ] Client proposal unchanged — clean, professional, no shop details
- [ ] Fab sequence present in shop copy with full step-by-step detail
- [ ] Overhead beam is `hss_4x4_0.25` (not overridden to 6x4)
- [ ] Hardware section unchanged
- [ ] Consumables section unchanged

---

## 3. Constraint Architecture

### Opus Is the Only Model
Every code path assumes Claude Opus 4.6. Do not add defensive code, fallback logic, or validation layers to compensate for weaker models. If the AI prompt is clear, Opus follows it. Previous prompts added post-processor overrides and validation layers to compensate for Gemini and Sonnet failures — Opus doesn't need them.

### Trust the Model, Simplify the Code
The field extraction doesn't need regex or keyword matching. Send Opus the description and the field list — it extracts what it can. The plate purchasing logic doesn't need a decision tree — Opus knows that 17 small pieces come from a sheet but 2 large base plates are cheaper as pre-cut. The fence rail math doesn't need a validator — Opus can add numbers.

State rules clearly in the AI prompt. Opus does the rest.

### Two Documents, Two Purposes
- **Cut list = shop bible.** Every piece, every length, every quantity. Individual. Detailed. This is what the welder works from.
- **Materials list = steel order.** Aggregated by profile. Total footage. Price per foot. Plate as sheet stock or pre-cut. This is what you hand to your distributor to get a quote or place an order.

### Plate Stock Intelligence
Not all plate pieces should come from sheet stock. The AI must evaluate the most cost-effective purchasing approach for each job:

- **Many small pieces** (cap plates 4" × 4", bumper plates 4" × 4", latch plates 6" × 4" — under ~8" × 8"): Buy a half sheet or full sheet and cut them. Include cutting labor (layout, cut, deburr — ~2-5 min per piece).
- **Few large pieces** (base plates 10" × 10"+, large mounting plates): May be cheaper and faster to buy pre-cut plate from the distributor. No cutting labor needed.
- **Mix of both**: Split accordingly — sheet stock for the small stuff, pre-cut for the big stuff.

This is the same mental math every fabricator does at the distributor counter. Opus understands this trade-off — just tell it to evaluate and choose.

### Units Are Non-Negotiable
Every dimension everywhere in the output must have its unit. This future-proofs for metric conversion (swap `"` for `mm`, `'` for `m`) and eliminates ambiguity. A cut list that says "116" could mean inches, millimeters, or centimeters. A cut list that says `116"` or `9'-8"` is unambiguous.

---

## 4. Decomposition

### 4A: Kill Sonnet

Purge every "sonnet" reference from the entire codebase.

**What to find and fix:**
- `backend/claude_client.py` — `_DEFAULT_DEEP = "claude-sonnet-4-6"` on line 22. Both defaults should be Opus. Consider collapsing the fast/deep two-tier system to a single model since both are Opus now.
- `backend/pricing_engine.py` — line ~219 calls `get_model_name("deep")` which returns the sonnet default for the assumption text. Should call `get_model_name("fast")` or just reference the single model.
- Anywhere else: `grep -rn "sonnet" backend/ --include="*.py" | grep -v __pycache__` — kill every result.

### 4B: AI Field Extraction from Job Description

After job type detection and question tree loading, but BEFORE the first question is returned to the user:

1. Send the user's job description + the full list of question tree fields (field IDs, labels, types, valid options for each) to Opus
2. Opus returns a JSON of `{field_id: value}` for every field it can confidently extract from the description
3. Merge extracted fields into the session's answered fields (don't overwrite anything the user already manually provided)
4. The question tree engine evaluates against the now-populated answered fields and only returns unanswered questions
5. Update the progress indicator to reflect pre-filled fields

**Key points:**
- This must work for ANY job type, not just cantilever gates. The field extraction prompt receives the actual field definitions from the loaded question tree, so it automatically adapts.
- No regex, no keyword matching, no per-field mapping rules. Opus reads natural language. "12' wide" → `opening_width: 12`. "Paint finish" → `finish: "Paint (in-house)"`. "Full installation" → `installation: "Full installation (gate + posts + concrete)"`.
- If Opus isn't confident about a field, it should omit it — the user will answer it manually. Safe by default.
- One API call, ~30 seconds. Saves the user 2-3 minutes of clicking through fields they already specified.

**Where to integrate:** Find where the session is created or where the question tree is first evaluated in `backend/routers/quote_session.py`. The extraction needs to happen after job type detection (so we know which question tree to load) but before the frontend receives the first batch of questions.

### 4C: Aggregate Materials by Profile

After the cut list is generated and priced, build a materials summary that represents an actual steel order:

**Linear stock** (tube, bar, channel, angle, pipe, HSS, flat bar):
- Group all cut list items by profile key
- Sum total linear inches per profile, convert to feet
- Look up $/ft from `material_lookup.py` PRICE_PER_FOOT
- Display: human-readable material description, total footage, $/ft, line total
- Example: `2" × 2" sq tube 11ga — 345 ft @ $2.49/ft = $859.05`

**Plate stock** (1/4" plate, 3/8" plate, etc.):
- Group all plate cut list items by thickness
- For each thickness, sum the total plate pieces and their sizes
- Apply the purchasing logic from Section 3 (sheet stock vs pre-cut)
- Display the actual purchasing decision:
  - Sheet: `1/4" plate — half sheet (24" × 48") — 1 @ $XX.XX`
  - Pre-cut: `1/4" plate — 10" × 10" pre-cut — 4 @ $XX.XX`

**Concrete:**
- Separate summary line: `Concrete (3 post footings, 12" dia × 42" deep) — 0.58 cu yd @ $XXX/yd = $XX.XX`
- NOT in the cut list
- NOT treated as linear stock

**The cut list remains exactly as-is** — every individual piece with its specific length, quantity, cut type, and notes. The materials summary is a SEPARATE section derived from the cut list, not a replacement for it.

### 4D: Plate Cutting Labor

When the materials summary determines that plate pieces will be cut from sheet stock:
- Add plate cutting labor to the labor calculation
- Layout + cut + deburr ≈ 2-5 minutes per piece depending on size and complexity
- This should show up in the Cut & Prep labor process or as a recognizable part of the fab sequence
- When plate is purchased pre-cut from the distributor, no additional cutting labor is needed for those pieces

### 4E: Units on Every Dimension

Add a clear rule to the AI prompt (in `ai_cut_list.py` where the cut list and fab sequence are generated):

```
UNITS RULE: Every dimension in your output MUST include its unit.
- Inches: use the " symbol (e.g., 116", 6" × 4", 1/4" plate)
- Feet: use the ' symbol (e.g., 12', 20' stick)
- Combined: 9'-8" for 116 inches when more readable
- NEVER output a naked number without a unit. "116" is wrong. "116\"" is correct.
```

This applies to: cut list lengths, detailed cut list notes, material descriptions, fab sequence steps, plate dimensions, everything.

### 4F: Grind Hours — Teach the Theory, Not a Number

In `backend/calculators/labor_calculator.py`, the grind time calculation counts every picket as 2 individual grind joints (lines ~186-190). With 141 pickets across gate + both fence sides, that's 282 TYPE B joints. This is the root cause of the inflated hours.

**The theory Opus and the labor calculator need to understand:**

There are two fundamentally different kinds of grind/cleanup work:

**Indoor / bare metal / stainless / furniture-grade:**
Grind welds smooth. Blend joints. Progressive gritting (60 → 80 → 120). Every weld gets individual attention. This is slow, precision work — 3-6 minutes per joint depending on visibility and finish requirements. A furniture piece with 20 visible joints might take 2-3 hours of grinding alone.

**Outdoor / painted steel:**
You are NOT grinding welds smooth. You are cleaning up — knocking off spatter, removing sharp edges, hitting high spots with a 36-grit flap disc. That's it. One quick pass per weld, maybe 30 seconds to 1 minute per structural joint. The paint covers everything.

**Pickets in pre-punched channel are even faster:**
The channel holds pickets in position. You weld through the pre-punched holes. Cleanup is a pass down the channel run — not per-picket work. A channel run of 40-55 pickets takes maybe 10-15 minutes to clean, not 80-110 minutes.

**The fix should reflect this scaling:**
- Pickets in pre-punched channel: count grind work per channel run, not per picket
- Outdoor structural joints: fast cleanup pass, not full grind
- Indoor/furniture joints: full grind time per joint

This means a small gate+fence (like our test case) might be 2-3 hours of grind. A project 10× the size would scale proportionally — maybe 15-20 hours. The per-joint time is low for outdoor painted work, but it's still per-joint — it just doesn't artificially inflate because of picket counting.

**Do NOT hardcode a maximum.** Let the math scale naturally based on the actual joint count with corrected per-joint times.

### 4G: Downloadable Materials List for Distributor

Add a third download button alongside "Shop Copy" and "Client Copy": **"📦 Materials List"**

This generates a clean, one-page PDF (or CSV — even better, offer both) that the fabricator sends directly to their steel distributor for a real quote. It contains ONLY:

- Material description (human-readable, e.g., "2" × 2" sq tube 11ga")
- Total footage or quantity needed
- Stock length (e.g., "20' sticks")
- Number of sticks needed (total footage ÷ stock length, rounded up)

**What it does NOT include:**
- No estimated prices (the distributor provides their own)
- No labor, no markup, no job description
- No cut list details (the distributor doesn't need to know what you're building)
- No company branding beyond a simple header with shop name and date

**Example output:**
```
MATERIALS ORDER — CreateStage Fabrication
Date: March 5, 2026
Quote Ref: CS-2026-0042

Material                              Need      Stock    Sticks
─────────────────────────────────────────────────────────
2" × 2" sq tube 11ga                 345 ft    20' ea    18
5/8" square bar                       500 ft    20' ea    25
4" × 4" sq tube 11ga                 96 ft     20' ea    5
Pre-punched channel (5/8" picket)     36 ft     20' ea    2
HSS 4" × 4" × 1/4"                   20 ft     20' ea    1
1/4" plate                            1 half sheet (24" × 48")
3/8" plate                            1 quarter sheet (24" × 24")
Flat bar 2" × 1/4"                    18 ft     20' ea    1
```

This is the kind of feature that makes a fabricator say "holy shit this app just saved me 30 minutes." They download it, email it to their distributor, get a real quote back, and now they have actual material costs instead of estimates.

**Implementation:** Add a `mode=materials` option to the existing PDF endpoint (same pattern as `mode=shop` and `mode=client`). Or generate a CSV alongside the PDF — CSV is even easier for distributors who want to paste into their own systems. Offer both buttons if feasible: "📦 Materials PDF" and "📦 Materials CSV".

### 4H: Output Cleanup

**Concrete in cut list:** Skip items where `material_type == "concrete"` or `profile.startswith("concrete")` when rendering the cut list sections in the PDF. Concrete stays in the materials summary and assumptions — just not the cut list.

**Pre-punched channel profile:** The AI prompt's available profiles list doesn't include the pre-punched channel profiles, so Opus picks the closest thing it knows (flat_bar or rect_tube). Add to the available profiles in `ai_cut_list.py`:

```
Pre-punched channel profiles (for picket mid-rails — NOT flat bar, NOT rect tube):
- punched_channel_1x0.5_fits_0.5 — for 1/2" pickets ($3.85/ft)
- punched_channel_1.5x0.5_fits_0.625 — for 5/8" pickets ($4.95/ft)  ← MOST COMMON
- punched_channel_2x1_fits_0.75 — for 3/4" pickets ($6.05/ft)

RULE: Match channel profile to picket size. 5/8" pickets → punched_channel_1.5x0.5_fits_0.625. Never use flat_bar or rect_tube for pre-punched channel mid-rails.
```

**Fence rail lengths:** Add to the AI prompt constraints:

```
FENCE RAIL LENGTH RULES:
- Total rail length per fence side MUST NOT exceed the fence side length
- Usable span = fence_length - (num_posts × post_width)
- Split into equal spans between posts
- Each span gets: 1 top rail, 1 bottom rail, 2 mid-rails — all the same length per span
- Do NOT create extra rail pieces that cause the total to exceed fence length
```

---

## 5. Evaluation Design

Generate a new quote with the test description from Section 2. Then verify:

### Automated Checks
```bash
# Sonnet fully purged
grep -rn "sonnet" backend/ --include="*.py" | grep -v __pycache__
# Expect: ZERO results

# Pre-punched channel in AI prompt
grep -n "punched_channel" backend/calculators/ai_cut_list.py
# Expect: profile keys listed in prompt text

# Concrete skipped in cut list rendering
grep -n "concrete" backend/pdf_generator.py
# Expect: skip/filter logic in cut list section

# Field extractor exists
ls backend/field_extractor.py
# Expect: file exists
```

### Manual Verification on Generated Quote

**Question tree:** Count how many questions appear. With the test description, at least 10 fields should be pre-filled. The user should see roughly 10-12 remaining questions, not 20+.

**Materials section (shop PDF):**
- One row per material profile, not 30+ individual pieces
- Linear stock shows total footage and $/ft
- Plate shows as sheet stock or pre-cut (whichever makes sense for the pieces in this quote)
- Concrete shows as cubic yards
- Math checks out: footage × $/ft = line total for each row
- Material subtotal = sum of all line totals

**Cut list (shop PDF):**
- Still shows every individual piece — unchanged from CS-2026-0042
- Every dimension has its unit (inches or feet)

**Labor (shop PDF):**
- Grind & Clean hours reflect outdoor painted cleanup theory — picket cleanup per channel run, not per picket — and scale proportionally with project size
- Plate cutting labor present if plate pieces are being cut from sheet stock

**Materials list download:**
- "Materials List" button appears alongside Shop Copy and Client Copy
- Downloads a clean distributor-ready document (PDF and/or CSV)
- Contains only: material descriptions, total footage, stock lengths, sticks/sheets needed
- No prices, no labor, no markup, no job details
- Clean enough to email directly to a steel distributor

**Client proposal:**
- Unchanged from CS-2026-0042 — clean, professional, no shop internals visible

**Fab sequence (shop PDF):**
- Present, detailed, step-by-step — unchanged in quality from CS-2026-0042
- Units on every dimension
- Plate cutting step included if applicable

**Assumptions:**
- Says "claude-opus-4-6" not "claude-sonnet-4-6"
- Overhead beam is `hss_4x4_0.25`
- No beam profile override warnings
