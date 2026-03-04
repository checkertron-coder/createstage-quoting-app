# PROMPT 27 — Switch to Opus + Simplify Everything

## Problem Statement

After 26 prompts of accumulated fixes, the system is over-engineered.
The post-processor fights the AI output. Banned term replacements inject
wrong terminology. The AI prompt has 1000+ lines of rules that contradict
each other. The review loop reports issues but doesn't fix them.

Result: 35 quotes generated, none are right. A basic gate and fence quote
still has wrong surface prep, duplicate beams, wrong profile keys, and
fabrication steps that don't match how a real shop operates.

**The fix is to simplify, not add more layers.**

## Acceptance Criteria

1. Opus generates cut lists and fab sequences (not Sonnet).
2. The post-processor is a SAFETY NET — it only adds items Claude
   completely omitted. It NEVER overrides, duplicates, or contradicts
   what Claude produced.
3. `BANNED_TERM_REPLACEMENTS` is stripped to only terms that are
   ALWAYS wrong regardless of context (max 5-10 entries).
4. Surface prep for outdoor mild steel: wipe with surface prep solvent
   and shop rags. NOT scotch-brite. NOT degreaser spray. Just wipe down.
5. Scotch-brite pads: ONLY for TIG prep (aluminum oxide removal),
   stainless steel heat tint, and filler rod cleaning. Never for
   outdoor mild steel paint prep.
6. Mill scale removal after cuts: flap disc on the grinder, 1-2" from
   cut ends. Mill scale on the stock surface washes off with water.
7. Field welding: Stick (SMAW, E7018) OR self-shielded flux core (FCAW-S).
   Always list BOTH options.
8. The review loop applies corrections automatically — not just reports.

## Decomposition

### Part 1: Switch to Opus
**File: `backend/claude_client.py`**

Change the default models:

```python
_DEFAULT_FAST = "claude-sonnet-4-20250514"    # Keep for cheap operations
_DEFAULT_DEEP = "claude-opus-4-0520"  # Use for cut lists and fab sequences
```

**File: `backend/calculators/ai_cut_list.py`**

The cut list and build instructions are the DEEP calls. Change the
`_call_ai` method to use `call_deep` instead of `call_fast`:

```python
def _call_ai(self, prompt: str) -> str:
    """Call AI provider with the DEEP model for cut list generation."""
    text = call_deep(prompt, timeout=180)  # Changed from call_fast
    if text is None:
        raise RuntimeError("AI provider returned no response")
    return text
```

This means cut list generation and fab sequences use Opus.
Field extraction and vision can stay on Sonnet (call_fast).

### Part 2: Simplify the Post-Processor
**File: `backend/calculators/cantilever_gate.py`**

The `_post_process_ai_result` method currently:
- Adds gate posts if missing ✓ (KEEP)
- Adds concrete if missing ✓ (KEEP)
- Adds overhead beam if missing ✓ (KEEP)
- Adds fence posts if missing ✓ (KEEP)
- Adds fence mid-rails if missing ✓ (KEEP)
- OVERRIDES beam profile even when Claude got it right ✗ (REMOVE)
- ADDS a second beam when one exists ✗ (FIX)

**Replace the overhead beam section** with this simpler logic:

```python
# ENFORCE: Overhead support beam (top-hung only)
if is_top_hung:
    # Check if AI already included an overhead beam
    has_overhead = any(
        "overhead" in item.get("description", "").lower()
        or "support beam" in item.get("description", "").lower()
        for item in items
    )
    also_in_cuts = any(
        "overhead" in str(cut.get("description", "")).lower()
        or "support beam" in str(cut.get("description", "")).lower()
        for cut in cut_list
    )

    if has_overhead or also_in_cuts:
        # AI included it — TRUST the AI. Don't add another one.
        # Just add an assumption note.
        assumptions.append(
            "Top-hung system: overhead beam included by AI. "
            "Verify profile is appropriate for gate weight."
        )
    else:
        # AI missed it entirely — add one
        if total_weight < 800:
            beam_profile = "hss_4x4_0.25"
            beam_desc = "HSS 4×4×1/4\""
        else:
            beam_profile = "hss_6x4_0.25"
            beam_desc = "HSS 6×4×1/4\""
        beam_length_in = total_gate_length_in + 24
        beam_length_ft = self.inches_to_feet(beam_length_in)
        beam_price_ft = lookup.get_price_per_foot(beam_profile)

        items.append(self.make_material_item(
            description="Overhead support beam — %s (%.1f ft)"
                        % (beam_desc, beam_length_ft),
            material_type="hss_structural_tube",
            profile=beam_profile,
            length_inches=beam_length_in,
            quantity=1,
            unit_price=round(beam_length_ft * beam_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        assumptions.append(
            "Top-hung system: overhead beam was missing from AI output — "
            "added %s (%.1f ft)." % (beam_desc, beam_length_ft)
        )
```

**Same approach for ALL post-processor sections:** check if AI included
the item. If yes, TRUST IT. If no, ADD IT. Never override, never duplicate.

### Part 3: Strip BANNED_TERM_REPLACEMENTS
**File: `backend/calculators/ai_cut_list.py`**

Replace the entire `BANNED_TERM_REPLACEMENTS` dict with ONLY universally
wrong terms:

```python
BANNED_TERM_REPLACEMENTS = {
    # Tools that don't exist in a metal fab shop
    "file": "flap disc",
    "hand file": "flap disc",
    "metal file": "flap disc",
    # Process terms that are always wrong
    "grind welds smooth": "clean welds — remove spatter, sharp edges, high spots only",
    "grind welds flush": "clean welds — remove spatter, sharp edges, high spots only",
    "grind all welds": "clean all welds — remove spatter, sharp edges, and high spots",
    "polish welds": "clean welds — remove spatter and high spots",
    # Drill into hollow tube is structurally wrong
    "drill into tube": "weld in threaded bung",
    "drill hole in tube": "weld in threaded bung",
}
```

**Remove ALL scotch-brite replacements.** Remove all vinegar/baking soda
replacements. Remove all grit sequence replacements. Remove all dry-fit
replacements. These are context-dependent and Opus can handle context.

### Part 4: Fix the AI Prompt — Surface Prep Rules
**File: `backend/calculators/ai_cut_list.py`**

In the `_build_instructions_prompt` method, find the fabrication rules
section and update/add these rules:

```
SURFACE PREP FOR PAINT (OUTDOOR MILD STEEL):
  Step 1: Flap disc — knock down weld spatter, sharp edges, high spots. Do NOT grind welds smooth.
  Step 2: Wipe down all surfaces with surface prep solvent and clean shop rags.
  Step 3: Prime with rust-inhibiting metal primer. Allow to dry per manufacturer specs.
  Step 4: Paint. Two coats for outdoor exposure. Allow dry time between coats.
  That's it. No scotch-brite pads. No degreaser spray. No elaborate cleaning sequence.
  The primer is designed to bond to clean dry steel.

SCOTCH-BRITE PADS — WHEN TO USE (and when NOT to):
  USE for: TIG weld prep on aluminum (remove oxide layer), stainless steel heat tint
  removal between TIG passes, cleaning filler rods, architectural/decorative finish work.
  DO NOT USE for: outdoor gate/fence paint prep, general mild steel cleaning,
  surface prep before primer on structural or ornamental outdoor work.

MILL SCALE:
  After cutting: use angle grinder with flap disc to remove 1-2" of mill scale from
  each cut end. This prevents weld porosity.
  On stock surfaces: mill scale on the body of the stock washes off with water and
  a rag. It does not need grinding.

FIELD WELDING:
  ALL field/site welds = Stick (SMAW, E7018) OR self-shielded flux core (FCAW-S).
  Always list BOTH options. Never specify just one.
  NEVER specify MIG (GMAW) or TIG (GTAW) for outdoor field work.
```

### Part 5: Add HSS Profiles to Material Catalog (ACTUALLY DO IT)
**File: `backend/calculators/material_lookup.py`**

This was specced in P25 and P26 and never implemented. The profile
recognition code needs these entries. Find the PRICE_PER_FOOT dict
and VERIFY these entries exist. If not, ADD them:

```python
# In PRICE_PER_FOOT:
"hss_4x4_0.25": 8.25,
"hss_6x4_0.25": 12.00,
```

Find WEIGHT_PER_FOOT (or equivalent) and add:
```python
"hss_4x4_0.25": 12.21,
"hss_6x4_0.25": 15.62,
```

Find MATERIAL_TYPES (or the profile → type mapping) and add:
```python
"hss_4x4_0.25": "hss_structural_tube",
"hss_6x4_0.25": "hss_structural_tube",
```

If these dicts don't exist by those exact names, search the file for
where profiles are mapped to types and weights, and add HSS entries there.

**This is the THIRD time this has been specced.** It must be implemented.
Grep the file after changes to verify:
```bash
grep "hss_4x4" backend/calculators/material_lookup.py
grep "hss_6x4" backend/calculators/material_lookup.py
# Both must return results
```

### Part 6: Fix Post Description Format
**File: `backend/calculators/cantilever_gate.py`**

In `_post_process_ai_result`, the gate post description currently reads
"Gate posts - 4 × 3" which looks like 4×3 inch posts.

Change:
```python
# OLD pattern (produces "Gate posts — 4\" x 4\" square tube × 3"):
description="Gate posts — %s × %d (%.1f ft each, ...)"
            % (post_size, post_count, ...)

# NEW (produces "3 × 4×4 gate posts (13.7 ft each, ...)"):
description="%d × %s gate posts (%.1f ft each, %.0f\" embed for Chicago frost line)"
            % (post_count, post_size,
               self.inches_to_feet(post_total_length_in),
               post_concrete_depth_in)
```

### Part 7: Review Loop — Apply Fixes Automatically
**File: `backend/claude_reviewer.py`**

If this file exists from P25, update it. If not, create it.

The reviewer should:
1. Take the completed quote
2. Send it to Claude (Opus) for review
3. If issues are found, apply the fixes directly to the quote data
4. Return the corrected quote + a list of what was changed

```python
def review_and_fix(quote_data: dict, fields: dict) -> dict:
    """
    Review a completed quote and apply corrections automatically.

    Returns the corrected quote_data with a '_corrections' key listing
    what was changed.
    """
    review = review_quote(quote_data, fields)

    corrections = []
    if not review.get("reviewed"):
        return quote_data

    for issue in review.get("issues", []):
        fix = issue.get("fix", "")
        if not fix:
            continue

        # Apply automated fixes for known categories
        category = issue.get("category", "")
        severity = issue.get("severity", "")

        if severity in ("critical", "major"):
            corrections.append({
                "category": category,
                "description": issue.get("description", ""),
                "fix_applied": fix,
                "severity": severity,
            })

    quote_data["_corrections"] = corrections
    quote_data["_review"] = review
    return quote_data
```

For now, the auto-fix is limited to flagging — true auto-correction
(modifying material lists, swapping profiles) is complex and should
be a future prompt. The key change is that corrections are ATTACHED
to the quote data so the frontend can show them.

## Environment Variables

```
ANTHROPIC_API_KEY=sk-ant-...     # Already set
CLAUDE_DEEP_MODEL=claude-opus-4-0520   # NEW — forces Opus for generation
CLAUDE_FAST_MODEL=claude-sonnet-4-20250514  # Keep Sonnet for cheap ops
```

Add `CLAUDE_DEEP_MODEL=claude-opus-4-0520` to Railway environment variables.

## Evaluation Design

### Verification Steps

1. **Opus is running:**
   ```bash
   # Railway logs should show:
   # "claude deep [claude-opus-4-0520] XX.Xs"
   # NOT "claude fast [claude-sonnet-4-20250514]"
   ```

2. **No duplicate overhead beams:**
   ```bash
   # Materials list should have exactly ONE overhead beam entry
   # NOT two (one from AI + one from post-processor)
   ```

3. **Surface prep is correct:**
   ```bash
   # Fab sequence surface prep step should say:
   # "wipe down with surface prep solvent and shop rags"
   # NOT "scotch-brite" or "degreaser"
   ```

4. **No "grind welds" anywhere:**
   ```bash
   # Fab sequence should say "clean welds" not "grind welds"
   ```

5. **Field welding lists both options:**
   ```bash
   # Site install steps should say "stick (SMAW) or flux core (FCAW-S)"
   # NOT just one or the other
   ```

6. **HSS warnings gone:**
   ```bash
   # Zero warnings about hss_4x4_0.25 or hss_6x4_0.25
   ```

7. **Post description readable:**
   ```bash
   # "3 × 4×4 gate posts" NOT "Gate posts - 4 × 3"
   ```

## File Change Summary

| File | Changes |
|------|---------|
| `backend/claude_client.py` | Change `_DEFAULT_DEEP` to `claude-opus-4-0520` |
| `backend/calculators/ai_cut_list.py` | Change `_call_ai` to use `call_deep`; strip `BANNED_TERM_REPLACEMENTS` to ~7 entries; update surface prep rules in instructions prompt |
| `backend/calculators/cantilever_gate.py` | Simplify post-processor: trust AI output, only add missing items; fix post description format |
| `backend/calculators/material_lookup.py` | Add hss_4x4_0.25 and hss_6x4_0.25 to ALL lookup dicts (THIRD TIME — MUST BE DONE) |
| `backend/claude_reviewer.py` | Update to apply corrections, not just report |
| Railway env vars | Add `CLAUDE_DEEP_MODEL=claude-opus-4-0520` |

## Philosophy Change

**TRUST THE AI. STOP BABYSITTING.**

Opus is the most capable model available. Give it clear domain knowledge
in the prompt, then TRUST its output. The post-processor is a safety net
for missing items, not a second-guesser. If Opus gets something wrong,
fix the PROMPT, don't add another layer of code that fights the output.

The banned term list should have fewer than 10 entries — only things that
are ALWAYS wrong in ANY context. Everything else, Opus can figure out.
