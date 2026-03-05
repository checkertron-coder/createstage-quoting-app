# PROMPT 33 — Trust Opus: Materials Intelligence, Field Extraction, Output Polish

Read `KNOWLEDGE.md` and `DECISIONS.md` before starting.

---

## 1. Problem Statement

CS-2026-0042 produces a working quote with both PDFs, fab sequence, and correct cut list. But five categories of issues remain that make the output unprofessional and the UX frustrating:

- **The question tree re-asks everything** the fabricator already typed in the description
- **The materials list shows 30+ individual pieces** instead of a steel order you could hand to a distributor
- **Plate stock is treated like linear material** instead of sheet stock you buy and cut pieces from
- **Grind hours are 3x too high** because pickets are counted as individual grind joints
- **Sonnet is still in the codebase** despite being fully replaced by Opus
- **Dimensions lack units**, fence rail math is wrong, pre-punched channel uses wrong profile key, concrete appears in the cut list

---

## 2. Acceptance Criteria

A quote generated from the test description below must satisfy ALL of these:

**Test description:**
```
12' wide, cantilever sliding gate, 10' tall, with square tube frame and picket infill. Paint finish. Full site installation. 13' fence on one side, 15' fence on other, 4 fence posts.
```

- [ ] Question tree only asks about fields NOT stated in the description
- [ ] Materials section shows one row per profile — total footage and $/ft for linear stock
- [ ] Plate stock shows as sheet orders (half sheet, full sheet) not individual pieces
- [ ] Plate cutting labor is reflected in the labor hours
- [ ] Every dimension has its unit (inches or feet) — no naked numbers
- [ ] Grind & Clean ≤ 4 hours for outdoor painted gate+fence
- [ ] No concrete in cut list (still in materials as cubic yards)
- [ ] Pre-punched channel uses `punched_channel_1.5x0.5_fits_0.625` not `flat_bar`
- [ ] Fence rail lengths per side ≤ fence side length
- [ ] Zero "sonnet" references in codebase
- [ ] Assumptions say "claude-opus-4-6"
- [ ] Cut list unchanged — every individual piece with length and quantity
- [ ] Client proposal unchanged — clean, no shop details
- [ ] Fab sequence present in shop copy
- [ ] Overhead beam still `hss_4x4_0.25`

---

## 3. Constraint Architecture

**Opus is the only model.** Every code path assumes Opus. Do not add defensive code for weaker models. If the prompt is clear, Opus follows it.

**Trust the model, simplify the code.** Where previous prompts added post-processor overrides and validation layers to compensate for Gemini/Sonnet failures, Opus doesn't need them. State rules clearly in the AI prompt. Opus does the rest.

**Cut list = shop bible.** Every piece, every length, every quantity. Detailed. Individual.

**Materials list = steel order.** Aggregated by profile. Total footage. Price per foot. This is what you hand to your distributor.

**Plate stock = sheet orders.** You buy sheets, you cut pieces from them. The materials list shows sheets. The cut list shows what you cut from them.

---

## 4. Decomposition

### 4A: Kill Sonnet
Purge every "sonnet" reference from the codebase. `claude_client.py` defaults, `pricing_engine.py` assumption text, anywhere else. Opus only.

### 4B: AI Field Extraction
After job type detection, send the description + the question tree's field definitions (field IDs, labels, valid options) to Opus. Opus returns a JSON of confidently extracted fields. Pre-fill those as answered. Question tree only shows what's left. One Opus call, works for any job type, any description format. No regex, no keyword matching.

### 4C: Aggregate Materials by Profile
After the cut list is generated, build the materials summary:
- **Linear stock** (tube, bar, channel, angle, pipe, HSS): sum total inches per profile, convert to feet, show $/ft and line total
- **Plate stock** (1/4", 3/8", etc.): use smart purchasing logic (see below)
- **Concrete**: separate line with cubic yards and price — not in the cut list, not treated as linear stock

**Plate stock purchasing logic:** Not all plate pieces should come from sheet stock. The AI needs to evaluate the most cost-effective way to source plate for each job:

- **Many small pieces** (cap plates, bumper plates, latch plates — under ~8" × 8"): buy a half sheet or full sheet and cut them all from it. Show as sheet order in materials. Include cutting labor.
- **Few large pieces** (base plates, mounting plates — 10" × 10" and up): it may be cheaper and faster to buy pre-cut plate drops or stock pieces from the distributor than to buy a full sheet and waste most of it. Show as individual pre-cut pieces in materials. No cutting labor needed.
- **Mix of both**: split accordingly — sheet stock for the small stuff, pre-cut for the big stuff.

This is the same mental math every fabricator does at the distributor counter. Opus understands this — just tell it to evaluate and choose the smarter option per job. The materials list should reflect the actual purchasing decision, not a blanket rule.

### 4D: Plate Cutting Labor
When plate pieces ARE being cut from sheet stock, that's real labor — layout, cutting (plasma/torch/saw), and edge deburring. Account for this in the labor hours, roughly 2-5 min per piece. When plate is purchased pre-cut, no cutting labor is needed for those pieces.

### 4E: Units on Every Dimension
Add to the AI prompt rules: every dimension must include its unit. Inches = `"`, feet = `'`. No exceptions, anywhere in the output — cut list, materials, fab sequence, notes. This also future-proofs for metric conversion.

### 4F: Grind Hours Fix
In `labor_calculator.py`, pickets in pre-punched channel get counted as 1 grind joint per ~10 pickets instead of 2 per picket. Channel-run cleanup, not per-picket work.

### 4G: Output Cleanup
- Skip concrete in cut list rendering (filter by material_type or profile)
- Add pre-punched channel profiles to the AI prompt's available profiles list so Opus uses the correct key
- Add fence rail length constraint to AI prompt: total rail per side ≤ fence side length

---

## 5. Evaluation Design

Generate a quote with the test description from Section 2.

```bash
# Sonnet purged
grep -rn "sonnet" backend/ --include="*.py" | grep -v __pycache__
# Expect: ZERO results

# Field extraction working
# Expect: question tree skips fields clearly stated in description

# Materials aggregated
# Expect: one row per profile, footage × $/ft = total, plate as sheet stock

# Units present
# Expect: every dimension in output has " or ' suffix

# Grind hours
# Expect: ≤ 4.0 hours in labor section

# Cut list unchanged
# Expect: every individual piece still listed with length and qty

# Client PDF unchanged
# Expect: clean proposal, no shop internals

# Fab sequence present
# Expect: detailed step-by-step in shop copy
```
