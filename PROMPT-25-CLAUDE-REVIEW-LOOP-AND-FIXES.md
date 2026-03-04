# PROMPT 25 — Claude Review Loop + Bug Fixes + Rate Fix

## Problem Statement

CS-2026-0033 is the best quote we've produced, but still has issues that
need fixing before it's hand-to-customer ready:

1. **Fence pickets use wrong profile** — `sq_bar_0.75` instead of `sq_bar_0.625`.
   The `_resolve_picket_profile` function correctly maps `'5/8" square bar'` →
   `sq_bar_0.625`, but the fence_infill_match field or Gemini extraction may
   override the user's explicit picket_material choice. The fence section
   generator must ALWAYS use the same picket profile as the gate when
   `fence_infill_match` contains "match" or when infill_type is "Pickets".

2. **Overhead beam is still HSS 6×4×1/4"** — The post-processor checks
   `has_overhead` and skips if Gemini already included one. But it doesn't
   validate the PROFILE. For gates under 800 lbs, it should be `hss_4x4_0.25`,
   not `hss_6x4_0.25`. The check needs to validate profile, not just existence.

3. **71 primer spray cans = $603.50** — Consumable calculation is broken.
   A typical residential gate+fence job needs 2-4 gallons of primer and 2-4
   gallons of paint (spray or brush), not 71 aerosol cans. The consumable
   builder needs a sanity cap.

4. **Shop rate defaults to $125/hr** — `quote_session.py` line 435 uses
   `current_user.rate_inshop or 125.00`. Burton's rate is $145/hr for all
   work. The default should be $145 for both shop and field, or better yet,
   the user profile should be updated. Currently the only place that says
   $145 is `rate_onsite`.

5. **HSS profiles not in catalog** — `hss_4x4_0.25` and `hss_6x4_0.25` both
   trigger "unrecognized profile" warnings on every quote. They need proper
   entries in the material catalog.

6. **Gemini is non-deterministic** — Same inputs produce different outputs.
   We need a post-generation review step that catches errors before the
   quote reaches the customer. This is the Claude feedback loop.

## Acceptance Criteria

After this prompt is implemented:

1. Fence pickets ALWAYS match gate pickets when `fence_infill_match` says "match"
   or when no separate fence infill question exists.
2. Overhead beam profile is validated — downgraded to `hss_4x4_0.25` when
   gate weight < 800 lbs, regardless of what Gemini specified.
3. Consumables are capped at reasonable quantities (max 8 cans primer, 8 cans
   paint for spray; or gallons-based if using brush/roller).
4. Default labor rates are $145/hr for ALL processes (shop and field).
5. HSS profile warnings eliminated.
6. A new `/api/session/{session_id}/review` endpoint exists that sends the
   completed quote to Claude API for fabrication review.

## Decomposition

### Part 1: Fix Fence Picket Profile
**File: `backend/calculators/cantilever_gate.py`**

The `_generate_fence_sections` method calls `_resolve_picket_profile(fields, infill_type)`.
This should work. The bug is likely that the `picket_material` field value doesn't
match the profile map labels on some runs (Gemini extraction vs user selection).

Fix: make `_resolve_picket_profile` more robust. Also add explicit fence picket
override — if `fence_infill_match` says "match", force fence pickets to use
the SAME resolved profile as the gate.

In `_post_process_ai_result`, before calling `_generate_fence_sections`,
resolve the gate picket profile ONCE and pass it as a parameter:

```python
# Resolve gate picket profile ONCE
gate_picket_profile = _resolve_picket_profile(fields, infill_type)

# ...later when calling _generate_fence_sections:
fence_result = self._generate_fence_sections(
    fields, height_in, infill_type, infill_spacing_in,
    frame_key, frame_size, frame_gauge, frame_price_ft,
    post_profile_key, post_price_ft, post_concrete_depth_in,
    gate_picket_profile=gate_picket_profile,  # NEW PARAM
)
```

Update `_generate_fence_sections` signature to accept `gate_picket_profile=None`.
Then in the fence picket section:

```python
elif use_pickets:
    # Force match with gate picket profile
    fence_match = fields.get("fence_infill_match", "Yes — match")
    if gate_picket_profile and "match" in str(fence_match).lower():
        picket_profile = gate_picket_profile
    else:
        picket_profile = _resolve_picket_profile(fields, infill_type)
```

Also update `_resolve_picket_profile` to be more forgiving:
```python
def _resolve_picket_profile(fields, infill_type):
    """Resolve picket profile from picket_material field."""
    picket_material = str(fields.get("picket_material", "")).strip().lower()
    if not picket_material:
        return INFILL_PROFILES.get(infill_type, "sq_bar_0.75")

    # Try exact-ish match
    for label, profile in PICKET_MATERIAL_PROFILES.items():
        if label.lower() in picket_material or picket_material in label.lower():
            return profile

    # Try extracting size fraction
    import re
    fraction_match = re.search(r'(\d+/\d+)"?\s*(square|round|sq|rd)?', picket_material)
    if fraction_match:
        size = fraction_match.group(1)
        shape = "square" if not fraction_match.group(2) or "sq" in fraction_match.group(2) else "round"
        for label, profile in PICKET_MATERIAL_PROFILES.items():
            if size in label and shape in label.lower():
                return profile

    return INFILL_PROFILES.get(infill_type, "sq_bar_0.75")
```

Also apply the same fix in the TEMPLATE path (line ~211 and ~251) — resolve
once and reuse.

### Part 2: Validate Overhead Beam Profile
**File: `backend/calculators/cantilever_gate.py`**

In `_post_process_ai_result`, change the overhead beam check from
"does one exist?" to "does one exist with the correct profile?":

```python
if is_top_hung:
    estimated_gate_weight = total_weight
    if estimated_gate_weight < 800:
        correct_beam_profile = "hss_4x4_0.25"
        correct_beam_desc = "HSS 4×4×1/4\""
    else:
        correct_beam_profile = "hss_6x4_0.25"
        correct_beam_desc = "HSS 6×4×1/4\""

    # Find existing overhead beam (if AI included one)
    overhead_idx = None
    for i, item in enumerate(items):
        desc_lower = item.get("description", "").lower()
        if "overhead" in desc_lower or "support beam" in desc_lower:
            overhead_idx = i
            break

    if overhead_idx is not None:
        existing = items[overhead_idx]
        existing_profile = existing.get("profile", "")
        # Override if wrong profile
        if existing_profile != correct_beam_profile:
            beam_length_in = total_gate_length_in + 24
            beam_length_ft = self.inches_to_feet(beam_length_in)
            beam_price_ft = lookup.get_price_per_foot(correct_beam_profile)
            items[overhead_idx] = self.make_material_item(
                description="Overhead support beam — %s (%.1f ft, qty 1)"
                            % (correct_beam_desc, beam_length_ft),
                material_type="hss_structural_tube",
                profile=correct_beam_profile,
                length_inches=beam_length_in,
                quantity=1,
                unit_price=round(beam_length_ft * beam_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            )
            # Also fix in cut_list
            for cut in cut_list:
                if "overhead" in str(cut.get("description", "")).lower():
                    cut["profile"] = correct_beam_profile
                    cut["length_inches"] = beam_length_in
                    cut["quantity"] = 1
                    break
            assumptions.append(
                "Overhead beam downsized from %s to %s (gate under 800 lbs)."
                % (existing_profile, correct_beam_profile))
    else:
        # No overhead beam — add one (existing code)
        beam_length_in = total_gate_length_in + 24
        # ... (keep existing add logic but use correct_beam_profile)
```

### Part 3: Fix Consumable Calculation
**File: `backend/calculators/consumable_calculator.py` (or wherever consumables are calculated)**

Find where primer/paint quantities are computed. The current formula seems to
be multiplying sq_ft by some per-sqft rate and getting aerosol can count.

For paint finishing, the calculation should be:

```python
# Paint consumables for gates/fences (outdoor steel)
total_paint_sq_ft = total_sq_ft  # both sides of steel = roughly 2× footprint
gallon_coverage = 350  # sq ft per gallon (typical for steel primer/paint)

primer_gallons = math.ceil(total_paint_sq_ft / gallon_coverage)
paint_gallons = math.ceil(total_paint_sq_ft / gallon_coverage)

# Sanity caps
primer_gallons = min(primer_gallons, 10)  # Max 10 gallons primer
paint_gallons = min(paint_gallons, 10)    # Max 10 gallons paint

# Pricing
primer_price_per_gallon = 35.00  # Industrial metal primer
paint_price_per_gallon = 45.00   # Industrial DTM paint

# OR if using spray cans:
primer_cans = math.ceil(total_paint_sq_ft / 20)  # ~20 sq ft per 15oz can
primer_cans = min(primer_cans, 12)  # Hard cap
```

For the CS-2026-0033 job (~1418 sq ft finish area):
- At 350 sqft/gal: 4 gallons primer + 4 gallons paint = ~$320
- NOT 71 spray cans at $8.50 each = $603

### Part 4: Fix Default Labor Rates
**File: `backend/routers/quote_session.py`**

Change the default rates:

Find (around line 435):
```python
user_rates = {
    "rate_inshop": current_user.rate_inshop or 125.00,
    "rate_onsite": current_user.rate_onsite or 145.00,
}
```

Replace with:
```python
user_rates = {
    "rate_inshop": current_user.rate_inshop or 145.00,
    "rate_onsite": current_user.rate_onsite or 145.00,
}
```

Also update the default seed rates in `process_rates.py`:
- Layout: $75 → $145 (it's Burton's time, same rate)
- Cutting: $85 → $145
- Welding: $125 → $145
- Grinding: $75 → $145
- Assembly: $100 → $145
- Paint: $75 → $145

The only rates that should differ:
- TIG Welding: $150 (premium process)
- Design/CAD: $150 (premium process)
- Field Install: $145 (same as shop — Burton doesn't charge more for field)
- CNC Plasma: $145
- CNC Router: $145

Everything is $145/hr unless it's a premium skill (TIG, CAD).

### Part 5: Add HSS Profiles to Material Catalog
**File: `backend/calculators/material_lookup.py`**

Verify these entries exist in `PRICE_PER_FOOT`:
```python
"hss_4x4_0.25": 8.25,   # Extrapolated from 3×3×1/4 ($7.50) + size premium
"hss_6x4_0.25": 12.00,  # Estimated — no supplier data
```

Also add them to `MATERIAL_TYPES` (or whatever dict maps profile → type):
```python
"hss_4x4_0.25": "hss_structural_tube",
"hss_6x4_0.25": "hss_structural_tube",
```

And add to `WEIGHT_PER_FOOT`:
```python
"hss_4x4_0.25": 12.21,  # lbs/ft for HSS 4×4×1/4"
"hss_6x4_0.25": 15.62,  # lbs/ft for HSS 6×4×1/4"
```

This eliminates the "Unrecognized profile" and "Unrecognized material type"
warnings.

### Part 6: Claude Review Loop (New Feature)
**New file: `backend/claude_reviewer.py`**

Create a Claude API integration that reviews completed quotes for fabrication
accuracy. This runs AFTER pricing (Stage 5) and returns a list of issues.

```python
"""
Claude fabrication quote reviewer.

Sends the completed quote to Claude API for expert review.
Returns a structured list of issues, warnings, and suggestions.
"""
import os
import json
import httpx

CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_REVIEW_MODEL", "claude-sonnet-4-20250514")
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


def review_quote(quote_data: dict, fields: dict) -> dict:
    """
    Send a completed quote to Claude for fabrication review.

    Args:
        quote_data: The full priced quote (materials, labor, consumables, etc.)
        fields: The user's answered fields from the question tree

    Returns:
        {
            "issues": [...],       # Critical errors that need fixing
            "warnings": [...],     # Things that look off but might be intentional
            "suggestions": [...],  # Optimization opportunities
            "score": 0-100,        # Confidence score
            "reviewed": true
        }
    """
    if not CLAUDE_API_KEY:
        return {
            "issues": [],
            "warnings": ["Claude API key not configured — review skipped"],
            "suggestions": [],
            "score": 0,
            "reviewed": False,
        }

    system_prompt = _build_system_prompt()
    user_prompt = _build_review_prompt(quote_data, fields)

    try:
        response = httpx.post(
            CLAUDE_API_URL,
            headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=60.0,
        )
        response.raise_for_status()
        result = response.json()
        text = result["content"][0]["text"]

        # Parse structured response
        return _parse_review(text)

    except Exception as e:
        return {
            "issues": [],
            "warnings": [f"Claude review failed: {str(e)}"],
            "suggestions": [],
            "score": 0,
            "reviewed": False,
        }


def _build_system_prompt() -> str:
    return """You are a senior metal fabrication estimator reviewing quotes for accuracy.
You have 20+ years of experience in structural and ornamental metalwork.

Your job is to review a fabrication quote and identify:
1. ISSUES — errors that will cause the quote to be wrong (wrong material, wrong dimensions, missing items)
2. WARNINGS — things that look suspicious but might be intentional
3. SUGGESTIONS — ways to optimize the quote (cheaper material alternatives, better processes)

DOMAIN KNOWLEDGE:
- Chicago frost line = 42" minimum embed depth (Municipal Code 13-132-100)
- Cantilever gate panel length = opening × 1.5 (not opening + available space)
- Standard residential pickets: 5/8" square bar at 4" on-center
- Pre-punched U-channel for mid-rails: pickets slide through holes, dramatically faster assembly
- Fence posts must extend: above_grade_height + 2" clearance + 42" embed
- MIG (GMAW) in shop only. Field work = Stick (SMAW, E7018) or self-shielded flux core (FCAW-S)
- Never grind welds smooth on outdoor gates/fences — cleanup only (spatter, sharp edges, high spots)
- Always prime + paint separately for outdoor steel (minimum 3-4 hours dry time between coats)
- Mill scale removal mandatory: grind 1-2" from each cut end before welding
- Never use a "file" — angle grinder + flap disc or die grinder + roloc disc
- Pre-punched channel hole sizes: 9/16" for 1/2" pickets, 11/16" for 5/8", 13/16" for 3/4"
- One primer gallon covers ~350 sq ft on steel. One paint gallon covers ~400 sq ft.
- Consumable spray cans: ~15-20 sq ft coverage each. A gate+fence job should NOT need 70+ cans.
- For gates under 800 lbs: HSS 4×4×1/4" overhead beam. Over 800 lbs: HSS 6×4×1/4".
- Overhead beam is ONE beam spanning between carriage posts, not two.

Respond ONLY with valid JSON in this format:
{
  "issues": [
    {"severity": "critical|major|minor", "category": "material|dimension|labor|process|pricing",
     "description": "...", "fix": "..."}
  ],
  "warnings": [
    {"category": "...", "description": "..."}
  ],
  "suggestions": [
    {"category": "...", "description": "...", "estimated_savings": "..."}
  ],
  "score": 85,
  "summary": "One-paragraph overall assessment"
}"""


def _build_review_prompt(quote_data: dict, fields: dict) -> str:
    """Build the review prompt with the full quote data."""
    return """Review this fabrication quote for accuracy.

## User Inputs
%s

## Quote Data
%s

Check for:
1. Do material profiles match what the user selected?
2. Are dimensions correct (gate length, post length, picket count)?
3. Are fence sections included if specified?
4. Is the overhead beam sized correctly for the gate weight?
5. Are consumable quantities reasonable?
6. Does the fab sequence use correct welding processes (MIG shop, stick/flux core field)?
7. Are labor hours in a realistic range?
8. Is the overall price in the right ballpark?

Return your review as JSON.""" % (
        json.dumps(fields, indent=2, default=str),
        json.dumps(quote_data, indent=2, default=str),
    )


def _parse_review(text: str) -> dict:
    """Parse Claude's review response."""
    # Try to extract JSON from the response
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown code blocks
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    try:
        result = json.loads(text)
        result["reviewed"] = True
        return result
    except json.JSONDecodeError:
        return {
            "issues": [],
            "warnings": ["Could not parse Claude review response"],
            "suggestions": [],
            "score": 0,
            "reviewed": False,
            "raw_response": text[:1000],
        }
```

**New endpoint: `backend/routers/quote_session.py`**

Add a review endpoint after the price endpoint:

```python
@router.post("/{session_id}/review")
def review_quote_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Run Stage 6: Claude AI review on a completed quote.

    Requires: session has been fully priced (stage == "complete" or "priced").
    Returns: list of issues, warnings, and suggestions from Claude review.
    """
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    current_params = dict(session.params_json or {})
    quote_data = current_params.get("_priced_quote") or current_params.get("_material_list")
    if not quote_data:
        raise HTTPException(
            status_code=400,
            detail="Quote not yet priced. Run /calculate, /estimate, /price first.",
        )

    fields = {k: v for k, v in current_params.items() if not k.startswith("_")}

    from ..claude_reviewer import review_quote
    review = review_quote(quote_data, fields)

    # Store review in session
    from sqlalchemy.orm.attributes import flag_modified
    current_params["_review"] = review
    session.params_json = current_params
    flag_modified(session, "params_json")
    db.commit()

    return {
        "session_id": session_id,
        "review": review,
    }
```

**Frontend integration (optional — can be done in a future prompt):**

Add a "Review Quote" button on the quote results page that calls
`/api/session/{id}/review` and displays the results as a card with
issues/warnings/suggestions.

**Environment variable:**

Add `ANTHROPIC_API_KEY` to Railway environment variables.
Default review model: `claude-sonnet-4-20250514` (fast + cheap for review).
Can be overridden with `CLAUDE_REVIEW_MODEL` env var.

### Part 7: Auto-Review in Pipeline (Optional)
**File: `backend/routers/quote_session.py`**

After the `/price` endpoint succeeds, automatically trigger a review if
the Claude API key is configured:

```python
# At the end of the /price endpoint, after storing results:
if os.environ.get("ANTHROPIC_API_KEY"):
    from ..claude_reviewer import review_quote
    review = review_quote(priced_quote, fields)
    current_params["_review"] = review
    flag_modified(session, "params_json")
    db.commit()
```

This makes the review transparent — every quote gets reviewed, and the
review results are available in the session data. The frontend can show
a "Review" tab or badge if there are issues.

## Evaluation Design

### Verification Steps

1. **Fence picket match:**
   ```bash
   # Generate cantilever gate quote with:
   #   picket_material = "5/8\" square bar"
   #   fence_infill_match = "Yes — match the gate exactly"
   # BOTH gate and fence pickets must show sq_bar_0.625
   grep -c "sq_bar_0.625" <quote_output>  # Should be > 0
   grep -c "sq_bar_0.75" <quote_output>   # Should be 0 (or only if user selected 3/4")
   ```

2. **Overhead beam profile:**
   ```bash
   # For a 12' × 10' gate (well under 800 lbs):
   # Beam must be hss_4x4_0.25, not hss_6x4_0.25
   # No "Unrecognized profile" warnings for HSS
   ```

3. **Consumable sanity:**
   ```bash
   # For a gate+fence job with ~1400 sq ft finish area:
   # Primer: 4-5 gallons (not 71 cans)
   # Total consumable cost: ~$200-350 (not $600+)
   ```

4. **Labor rates:**
   ```bash
   # All processes should show $145/hr (except maybe TIG at $150)
   # Site Install should show $145/hr
   ```

5. **Claude review:**
   ```bash
   curl -X POST https://createstage-quoting-app-production.up.railway.app/api/session/{id}/review \
     -H "Authorization: Bearer {token}"
   # Should return JSON with issues, warnings, suggestions, score
   ```

## File Change Summary

| File | Changes |
|------|---------|
| `backend/calculators/cantilever_gate.py` | Fix fence picket profile; add `gate_picket_profile` param to `_generate_fence_sections`; validate overhead beam profile in post-processor; improve `_resolve_picket_profile` robustness |
| `backend/calculators/material_lookup.py` | Add `hss_4x4_0.25` and `hss_6x4_0.25` to MATERIAL_TYPES and WEIGHT_PER_FOOT |
| `backend/calculators/consumable_calculator.py` | Fix primer/paint quantity calculation; add sanity caps |
| `backend/routers/quote_session.py` | Change default rate to $145; add `/review` endpoint; auto-review after pricing |
| `backend/routers/process_rates.py` | Update seed rates to $145/hr baseline |
| `backend/claude_reviewer.py` | NEW — Claude API integration for quote review |
| `requirements.txt` | Add `httpx` if not already present (for Claude API calls) |

## Environment Variables Needed

```
ANTHROPIC_API_KEY=sk-ant-...   # Burton's Anthropic API key ($50 balance)
CLAUDE_REVIEW_MODEL=claude-sonnet-4-20250514  # Default review model (optional)
```

## What This Does NOT Fix (Future Prompts)

- Gate length override in AI cut list (post-processor validates but doesn't rewrite Gemini's cut list dimensions)
- Pre-punched channel profile recognition in AI output (Gemini still uses "channel")
- PDF upload for construction plans (needs PDF-to-image conversion)
- Stairs question tree and calculator
- Local embedding/memory system (ollama + nomic-embed-text)
- Frontend "Review" tab/badge for displaying Claude review results
- Reprocess/regenerate preserving original field answers
