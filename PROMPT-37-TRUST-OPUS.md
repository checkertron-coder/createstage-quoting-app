# Prompt 37: Trust Opus — Remove Bad Rules, Fix Grind Bug, Fix Finish Detection

## Problem Statement

Three compounding bugs are producing wrong quotes for aluminum and sign jobs:

1. **Vinegar bath on aluminum** — `_build_instructions_prompt()` detects "clear coat" or "brushed" in the description and injects a "Step 1 MUST be vinegar bath" instruction. Vinegar bath removes mill scale from mild steel. Aluminum has no mill scale. We are literally overriding Opus's correct knowledge with a wrong rule.

2. **Grind hours explosion** — The labor calculator uses an "indoor full grind" formula (`type_a_joints × 6 min`) for any job that isn't outdoor+coated. A two-sign LED project with 50+ structural pieces calculates 33+ hours of grinding. For a clear coat aluminum sign, the real grind time is 6-10 hours max (weld cleanup + brushed texture pass). The formula doesn't account for material (aluminum grinds faster), job type (signs aren't furniture), or finish reality (clear coat over brushed texture ≠ show-quality furniture grind).

3. **Finish detection wrong** — "Clear coat" and "clear_coat" are in the `bare_metal_keywords` list, triggering mill scale logic. They're also not in the `coating_kw` list, so the job is never classified as "has_coating = True." A clear coat finish is a protective coating — it should suppress mill scale removal, not trigger it.

The root cause of all three: we wrote rules that assume mild steel and applied them universally. Opus already knows the correct behavior for aluminum, signs, and clear coat finishes. We are getting in its way.

## Acceptance Criteria

1. An aluminum LED sign quote with "clear coat" finish produces ZERO vinegar bath steps in the fabrication sequence
2. Grind & Clean hours for the two-sign LED project land between 6-12 hours (not 30+)
3. The finishing section correctly identifies "clear coat" as the method — not "paint"
4. A mild steel flat bar ornamental fence with clear coat finish STILL triggers mill scale removal (vinegar bath IS correct for that job)
5. Mild steel jobs with paint or powder coat are unaffected

## Constraint Architecture

**Files to modify:**
- `backend/calculators/ai_cut_list.py` — `_build_instructions_prompt()` method
- `backend/calculators/labor_calculator.py` — grind hour calculation (Step 3)
- `backend/pdf_generator.py` — finish method label detection

**DO NOT modify:**
- `fab_knowledge.py` — leave as-is for now
- Any question tree JSON files
- The cut list generation prompt (`_build_prompt()`)
- Pricing or materials logic
- P36 dynamic questions code

## Decomposition

### Fix 1: Make mill scale removal material-aware (ai_cut_list.py)

In `_build_instructions_prompt()`, the `needs_mill_scale_removal` flag currently fires when the finish contains bare metal keywords like "clear coat" — regardless of material. 

Add a material check: if the job description or material field contains "aluminum" or "6061" or "5052", set `needs_mill_scale_removal = False` unconditionally. Aluminum does not have mill scale. The oxide layer on aluminum is handled differently (acetone wipe + dedicated stainless wire brush just before welding) — but Opus already knows this. Do NOT inject aluminum-specific prep instructions. Just stop injecting the wrong ones.

Also add "clear_coat", "clear coat", "clearcoat", "2k urethane", "automotive clear" to the coating detection logic so they suppress mill scale removal for steel jobs too. Clear coat IS a protective coating.

### Fix 2: Add sign/panel job type to grind logic (labor_calculator.py)

The current logic has two paths: outdoor+coated (light cleanup) and everything else (full furniture grind). Sign and panel jobs fall into "everything else" and get massively overcounted.

Add a third path for panel/sheet-dominant jobs: if the cut list is primarily sheet material (>40% of pieces are sheet profile) OR job_type is "led_sign_custom" or "sign_frame", use a surface-area-based grind estimate instead of joint-count formula:
- Base: 20 minutes
- Per sheet piece: 8 minutes (one pass with flap disc per face)
- Per structural tube joint: 1.5 minutes (cleanup only — not furniture grade)
- If clear coat finish: multiply by 0.5 (clear coat over brushed texture needs less prep than painted)

This will produce 6-12 hours for the two-sign project instead of 33+.

### Fix 3: Fix finish label in PDF (pdf_generator.py)

Find where the finishing method label is set (where "Paint (in-house)" appears). The finish type detection should map:
- "clear coat", "clear_coat", "clearcoat", "2k urethane", "automotive clear" → "Clear Coat (in-house)"
- "powder coat", "powder_coat", "powdercoat" → "Powder Coat (outsourced)"
- "paint", "painted" → "Paint (in-house)"
- "brushed stainless", "brushed" → "Brushed Finish (in-house)"
- Everything else → use the raw field value or "Standard Finish"

## Evaluation Design

**Test 1: Aluminum LED sign — the broken case**
Run the LoanDepot two-sign description (aluminum, clear coat, ESP32, 38.5×128" and 38.5×138").
- Expected: NO vinegar bath in fabrication sequence
- Expected: Grind & Clean between 6-12 hours
- Expected: Finishing section says "Clear Coat (in-house)" not "Paint"

**Test 2: Mild steel ornamental fence with raw/clear coat — vinegar bath should survive**
Run a mild steel flat bar ornamental fence job with "clear coat" or "raw steel" finish.
- Expected: Vinegar bath step IS present (correct for mild steel)
- Expected: Grind hours are reasonable for flat bar work

**Test 3: Standard painted gate — nothing changes**
Run the cantilever gate quote with powder coat finish.
- Expected: No vinegar bath, normal grind hours, "Powder Coat (outsourced)"
