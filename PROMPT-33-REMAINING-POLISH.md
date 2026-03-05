# PROMPT 33 — Kill Sonnet, Trust Opus, Clean Up Remaining Bugs

## Context

CS-2026-0042 is 95% correct. Both PDFs generate, fab sequence is back, beam is fixed, materials are individually itemized. This prompt fixes the remaining 5% — six targeted bugs.

**CRITICAL PRINCIPLE:** Claude Opus 4.6 is the ONLY model for this app. Sonnet is dead. Every code path assumes Opus. Do NOT add defensive code to compensate for weaker models. If the AI prompt is clear, Opus follows it. Trust the model, keep the code simple.

**Reference quote:** CS-2026-0042 — shop copy (9 pages), client proposal (2 pages). Do NOT break what's working.

Read `KNOWLEDGE.md` and `DECISIONS.md` at the repo root before starting. They contain accumulated domain knowledge from 33 prompt iterations.

---

## Bug 1: Kill Sonnet Completely — Opus Is the Only Model

**Files:** `backend/claude_client.py`, `backend/pricing_engine.py`, and ANY file containing "sonnet"

**Current code in `claude_client.py` lines 21-22:**
```python
_DEFAULT_FAST = "claude-opus-4-6"
_DEFAULT_DEEP = "claude-sonnet-4-6"
```

**Problem:** Sonnet is still hardcoded as the "deep" model default. There is NO Sonnet variable in Railway. There should be NO Sonnet anywhere in this codebase. Sonnet produced aggregated cut lists, wrong quantities, and ignored domain constraints (see DECISIONS.md D-001). It's gone.

**Fix `claude_client.py`:**
```python
_DEFAULT_FAST = "claude-opus-4-6"
_DEFAULT_DEEP = "claude-opus-4-6"  # Opus for everything — Sonnet is removed
```

Better yet — collapse the two-tier system entirely. There's no reason for fast/deep distinction when both are Opus:

```python
_DEFAULT_MODEL = "claude-opus-4-6"

def get_model_name(tier="fast"):
    """Return model name. Tier parameter kept for API compatibility but always returns Opus."""
    if tier == "fast":
        return os.getenv("CLAUDE_FAST_MODEL", _DEFAULT_MODEL)
    return os.getenv("CLAUDE_DEEP_MODEL", os.getenv("CLAUDE_FAST_MODEL", _DEFAULT_MODEL))
```

**Fix `pricing_engine.py` line ~219:**
```python
assumptions.append(
    "Labor hours estimated by AI (%s via %s) with domain guidance."
    % (get_model_name("fast"), "Claude")
)
```

**Then purge the entire codebase:**
```bash
grep -rn "sonnet" backend/ --include="*.py" | grep -v __pycache__
```
Kill every result. Replace with opus or remove entirely. Zero Sonnet references should remain.

**Verification:**
```bash
grep -rn "sonnet" backend/ --include="*.py" | grep -v __pycache__
# Should return ZERO results
```

---

## Bug 2: Question Tree Asks About Things Already in the Job Description

**Problem:** The last several quotes have asked follow-up questions for fields that were clearly stated in the original text description. For example, the user types "12' wide, 10' tall, cantilever gate, paint finish, picket infill" and the question tree STILL asks about opening width, height, finish, and infill type.

**File:** `backend/question_trees/engine.py` — the field extraction logic

**Root cause:** Either:
1. The description → field extraction step isn't running, or
2. It's extracting the fields but the question tree isn't checking `already_answered` before asking, or
3. The extraction results aren't being stored in the session's answered fields

**Diagnosis steps:**
```bash
grep -n "extract\|already_answered\|skip.*answered\|pre.fill\|prefill" backend/question_trees/engine.py | head -20
grep -n "extract_fields\|description.*extract\|field_extraction" backend/routers/quote_session.py | head -20
```

**What should happen:**
1. User submits job description
2. Before the question tree starts, AI (Opus) extracts any fields that are clearly stated in the description
3. Extracted fields are stored as already-answered
4. Question tree only asks about fields that are NOT already answered

**Fix:** Trace the pipeline from description submission through field extraction to question tree evaluation. Make sure:
- `extract_fields_from_description()` (or equivalent) runs on every description
- Extracted values are saved to the session's answered fields
- `engine.py` checks answered fields before returning the next question
- The progress indicator reflects pre-filled fields (don't show "1/10" when 6 were already extracted from description)

Opus can extract fields reliably from natural language. Trust it. If the user said "12' opening" in their description, that's the opening_width — don't ask again.

**Verification:**
Generate a new quote with this description:
```
12' wide, cantilever sliding gate, 10' tall, with square tube frame and picket infill. Paint finish. Full site installation. 13' fence on one side, 15' fence on other, 4 fence posts.
```
The question tree should NOT ask about: opening width, height, frame type, infill type, finish, or installation type. It SHOULD only ask about things NOT in the description (latch type, motor, etc.).

---

## Bug 3: Grind & Clean Hours Way Too High (8.6 hrs → 2-3 hrs)

**File:** `backend/calculators/labor_calculator.py`

**Current behavior:** Grind & Clean shows 8.6 hours for an outdoor gate+fence job.

**Root cause (lines ~186-190):** Every cut list piece gets `qty * 2` joints for grind time. Pickets welded into pre-punched channel are TYPE B pieces and each gets 2 joints. With 141 pickets (55 gate + 40 fence1 + 46 fence2), that's 282 TYPE B joints × 1 min = 282 min just for pickets. Add TYPE A structural joints × 2 min + 15 min base + 90 min mill scale = 500+ minutes = 8.6 hours.

**The fix:** Pickets in pre-punched channel don't need individual joint cleanup. The channel holds them — you weld through the holes, cleanup is a quick pass down the channel, not per-picket.

Change the grind joint count for TYPE B picket items in the loop at line ~186:

```python
if _is_type_b(item):
    type_b_count += qty
    # Pickets in pre-punched channel: cleanup is per-channel-run, not per-picket
    # A channel run of 40-55 pickets takes ~15 min to clean, not 80-110 min
    desc_lower = str(item.get("description", "")).lower()
    is_picket = "picket" in desc_lower or "sq_bar" in profile
    if is_picket:
        # Count as 1 joint per ~10 pickets (channel run cleanup)
        type_b_joints += max(1, qty // 10)
    else:
        type_b_joints += qty * 2
```

**Expected result:** 141 pickets → ~14 TYPE B joints instead of 282. Grind time drops to ~2-3 hours for outdoor painted work.

**Verification:**
```bash
cd backend && python -c "
from calculators.labor_calculator import calculate_labor_hours
items = [{'profile': 'sq_bar_0.625', 'description': 'Gate pickets', 'quantity': 55, 'cut_type': 'square'}]
items += [{'profile': 'sq_bar_0.625', 'description': 'Fence pickets', 'quantity': 40, 'cut_type': 'square'}]
items += [{'profile': 'sq_bar_0.625', 'description': 'Fence pickets', 'quantity': 46, 'cut_type': 'square'}]
items += [{'profile': 'sq_tube_2x2_11ga', 'description': 'Gate top rail', 'quantity': 1, 'length_inches': 216, 'cut_type': 'square'}]
items += [{'profile': 'sq_tube_4x4_11ga', 'description': 'Gate post', 'quantity': 3, 'length_inches': 164, 'cut_type': 'square'}]
result = calculate_labor_hours('cantilever_gate', items, {'finish': 'paint'})
print(f'Grind & Clean: {result[\"grind_clean\"]:.1f} hours')
assert result['grind_clean'] <= 4.0, f'Grind too high: {result[\"grind_clean\"]}hrs'
print('PASS')
"
```

---

## Bug 4: Concrete Footing Appears in Cut List as Linear Stock

**Current behavior:** The cut list shows:
```
Post concrete - 3 holes × 12" dia ×    concrete_footing    42"    3    n/a
```

Concrete is not cut material. It doesn't belong in a cut list.

**File:** `backend/pdf_generator.py` (wherever the cut list table is rendered)

**Fix:** When rendering the cut list in the shop PDF, skip items where `material_type == "concrete"` or `profile.startswith("concrete")` or `cut_type == "n/a"`:

```python
# In the cut list rendering loop:
for item in cut_list:
    mat_type = item.get("material_type", "")
    profile = str(item.get("profile", ""))
    if mat_type == "concrete" or profile.startswith("concrete"):
        continue
    # ... render row
```

Apply the same filter to the Detailed Cut List section. Concrete should still appear in the Materials table and Assumptions — just not in Cut List.

**Verification:**
```bash
grep -n "concrete" backend/pdf_generator.py
# Should see skip logic in cut list rendering
```

---

## Bug 5: Pre-Punched Channel Using Wrong Profile Key

**Current behavior in CS-2026-0042:**
```
Pre-punched channel mid-rail    flat_bar_2x0.25    212"    2
```

Should be `punched_channel_1.5x0.5_fits_0.625` at $4.95/ft, not `flat_bar_2x0.25` at $1.28/ft. The AI describes the right part but picks the wrong profile key because the pre-punched channel profiles aren't listed in the AI prompt.

**File:** `backend/calculators/ai_cut_list.py` — in the AI prompt where available profiles are listed

**Fix:** Find the AVAILABLE PROFILES section in `_build_instructions_prompt()` (around line 747) or wherever profiles are listed for the AI. Add:

```
Pre-punched channel profiles (for picket mid-rails — NOT flat bar, NOT rect tube):
- punched_channel_1x0.5_fits_0.5 — for 1/2" pickets ($3.85/ft)
- punched_channel_1.5x0.5_fits_0.625 — for 5/8" pickets ($4.95/ft)  ← MOST COMMON
- punched_channel_2x1_fits_0.75 — for 3/4" pickets ($6.05/ft)

RULE: When the job uses pickets AND pre-punched channel mid-rails, the channel profile MUST match the picket size. 5/8" pickets → punched_channel_1.5x0.5_fits_0.625. Never use flat_bar or rect_tube for pre-punched channel.
```

Opus will use the right key once it sees the options. Trust the model.

**Verification:**
```bash
grep -n "punched_channel" backend/calculators/ai_cut_list.py
# Should show profile keys in the prompt text
```

---

## Bug 6: Fence Side 2 Rail Lengths Don't Add Up

**Current behavior in CS-2026-0042:**
```
Fence Side 2 (15ft) - top rail    56"    1
Fence Side 2 (15ft) - top rail    86"    2
```

56" + 86" + 86" = 228". But Fence Side 2 is 15' = 180". Rails are oversized.

**Fix:** Add a constraint to the AI prompt in `_build_field_context()` or `_build_instructions_prompt()`:

```
FENCE RAIL LENGTH RULES:
- Total rail length per fence side MUST NOT exceed the fence side length
- If fence side is 15' (180"), total rails fit within 180" minus post widths
- With posts at 4" each: usable span = fence_length - (num_posts × 4")
- Split into equal spans between posts
- Each span gets: 1 top rail, 1 bottom rail, 2 mid-rails — all same length per span
- Do NOT add extra rail pieces that cause total to exceed fence length
```

Opus can do this math. Just state the rule clearly.

**Verification:**
After generating a new quote, check:
- Fence Side 1 (13'): all rail lengths total ≤ 156"
- Fence Side 2 (15'): all rail lengths total ≤ 180"

---

## Decomposition (order of implementation)

1. **Kill Sonnet** — purge every reference, collapse fast/deep to Opus-only
2. **Fix question tree** — don't re-ask fields clearly stated in description
3. Fix grind hours — modify `labor_calculator.py` picket joint counting
4. Skip concrete in cut list PDF — add filter in `pdf_generator.py`
5. Add pre-punched channel profiles to AI prompt — edit `ai_cut_list.py`
6. Add fence rail length constraint to AI prompt — edit `ai_cut_list.py`

## Evaluation Design

After all changes, generate a new quote with this description:
```
12' wide, cantilever sliding gate, 10' tall, with square tube frame and picket infill. Paint finish. Full site installation. 13' fence on one side, 15' fence on other, 4 fence posts.
```

Check:
```bash
# 1. Zero Sonnet references
grep -rn "sonnet" backend/ --include="*.py" | grep -v __pycache__
# Should return ZERO results

# 2. Question tree should NOT ask about opening width, height, frame, infill, finish, or install
# Only asks about things NOT in the description

# 3. Grind hours ≤ 4.0 in shop PDF labor section

# 4. No concrete in cut list (still in materials table)

# 5. Pre-punched channel shows punched_channel_1.5x0.5_fits_0.625
# NOT flat_bar_2x0.25 or rect_tube_2x3_11ga

# 6. Fence Side 2 rail lengths add up to ≤ 180"

# 7. Client proposal unchanged — still clean, no shop details
# 8. Fab sequence still present in shop copy
# 9. Overhead beam still hss_4x4_0.25
# 10. Assumptions say "claude-opus-4-6" not "claude-sonnet-4-6"
```
