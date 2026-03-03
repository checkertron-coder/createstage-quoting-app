# PROMPT 17 — The Big One: Fix Every Outstanding Issue

## READ THIS FIRST — INTEGRATION RULES

From CLAUDE.md: Building a module is not done until it's CALLED in the pipeline. After any change, trace the full path from user input → AI generation → validation → PDF output. If your new code isn't in that path, it's not done.

**PATTERN TO AVOID:** Prompt 13 built 5,243 lines of structured knowledge + validation that was never wired in. DO NOT repeat this. Every function you create or modify MUST be called in the actual request flow. Verify with grep after every change.

---

## THE ISSUES (all must be fixed in this prompt)

### ISSUE 1: Baking Soda Still Generated — Strip It, Don't Just Flag It

**Current state:** Validation catches "baking soda" and flags it with `[REVIEW: contains banned term]`. Good. But the banned text is still IN the output and IN the PDF. A customer should never see "baking soda" in any quote.

**Fix:** After flagging banned terms in `backend/calculators/ai_cut_list.py` (lines ~148-165), add a STRIP step that replaces the banned content with the correct process:

```python
# After checking for banned terms, REPLACE them in the output
REPLACEMENTS = {
    # pattern → replacement
    "neutralize with a baking soda solution": "scrub with dish soap and a red scotch-brite pad",
    "neutralize with a baking soda/water solution": "scrub with dish soap and a red scotch-brite pad",
    "neutralize with baking soda": "scrub with dish soap and a red scotch-brite pad",
    "baking soda solution": "dish soap and red scotch-brite pad",
    "baking soda/water": "dish soap and red scotch-brite pad",
    "baking soda": "dish soap",
    "dry instantly with compressed air": "dry with a clean towel",
    "dry completely with compressed air": "dry with a clean towel",
    "blow dry with compressed air": "dry with a clean towel",
    "compressed air": "clean towel",
}

for step in steps:
    desc = step.get("description", "")
    for bad, good in REPLACEMENTS.items():
        desc = re.sub(re.escape(bad), good, desc, flags=re.IGNORECASE)
    # Also strip the tools line
    tools = step.get("tools", "")
    if isinstance(tools, str):
        for bad_tool in ["baking soda", "compressed air"]:
            tools = re.sub(r',?\s*' + re.escape(bad_tool), '', tools, flags=re.IGNORECASE)
        step["tools"] = tools.strip().rstrip(",").strip()
    step["description"] = desc
```

Put this AFTER the banned term check but BEFORE the return. The validation warnings should still be logged and included in `validation_warnings`, but the actual text the customer sees is corrected.

### ISSUE 2: FAB_KNOWLEDGE.md Still Has Baking Soda (Lines 439-440)

**Current state:** `FAB_KNOWLEDGE.md` line 439 says "neutralize with baking soda/water" and line 440 says "Dry instantly with compressed air". These get injected into the Gemini prompt via `_build_decorative_stock_prep()` which STILL returns the old prose (the fallback override bug from Prompt 15).

**Fix both problems at once:**

In `FAB_KNOWLEDGE.md`, find this block (around lines 437-442):
```
1. Vinegar bath full-length raw stock — submerge as much as fits in the bath
2. Soak 12-24 hours (UNATTENDED — this is not labor time)
3. Pull stock, rinse immediately, neutralize with baking soda/water
4. Dry instantly with compressed air (prevents flash rust)
5. Heavy grind with flap disc — 80 grit then 120 grit on ALL faces
```

Replace with:
```
1. Vinegar bath full-length raw stock — submerge as much as fits in the bath
2. Soak 12-24 hours (UNATTENDED — this is not labor time)
3. Pull stock, rinse immediately with warm water
4. Scrub with dish soap and red scotch-brite pad (medium grit) — removes residue
5. Rinse again thoroughly, dry with clean towel
6. Heavy grind with 40-grit flap disc on ALL four faces — this IS the final finish
7. DO NOT use 80→120 grit progression for brushed steel. 40-grit texture is the desired finish.
```

Also fix `_build_decorative_stock_prep()` in `backend/calculators/fab_knowledge.py` — the function currently tries to build from structured data, then OVERRIDES it by returning FAB_KNOWLEDGE.md prose if that section exists. Fix the logic so structured data wins and FAB_KNOWLEDGE.md prose is supplemental only (for spacer dimension context). Specifically:

```python
def _build_decorative_stock_prep():
    """Build decorative stock prep from structured process data.
    Structured data is source of truth. FAB_KNOWLEDGE.md supplements only."""
    proc = get_process("decorative_stock_prep")
    if not proc:
        raw = _find_section("DECORATIVE STOCK PREP")
        if raw:
            lines = raw.strip().split("\n")
            kept = [l for l in lines if l.strip()]
            return "DECORATIVE STOCK PREP — PROCESS ORDER:\n" + "\n".join(kept[:50])
        return ""

    # Build from structured data (source of truth)
    steps_list = proc.get("steps", [])
    never = proc.get("NEVER", [])
    notes = proc.get("notes", "")
    
    result = "DECORATIVE STOCK PREP — PROCESS ORDER:\n"
    if notes:
        result += notes + "\n\n"
    result += "Steps:\n"
    for i, s in enumerate(steps_list, 1):
        result += "%d. %s\n" % (i, s)
    if never:
        result += "\nNEVER do any of these during this process:\n"
        for term in never:
            result += "- %s\n" % term

    # Append ONLY spacer/dimension context from FAB_KNOWLEDGE.md
    raw = _find_section("DECORATIVE STOCK PREP")
    if raw:
        for line in raw.split("\n"):
            ll = line.lower()
            if any(k in ll for k in ["spacer", "0.75", "0.50", "gap between",
                                       "why this matters", "cannot grind"]):
                result += "\n" + line.strip()

    return result
```

### ISSUE 3: Shielding Gas Wildly Over-Estimated

**Root cause:** `backend/hardware_sourcer.py` line ~437:
```python
weld_hours = weld_linear_inches / 10.0  # ~10 in/hr
```

This assumes a welding speed of 10 inches per hour. That's absurdly slow — less than 1 inch per minute. MIG welding on mild steel furniture runs 60-120 inches per hour (1-2 inches per minute travel speed).

**Fix:** Change line ~437 to:
```python
weld_hours = weld_linear_inches / 80.0  # ~80 in/hr MIG travel speed on mild steel
```

This brings gas usage from 1,620 cu ft ($129) down to ~200 cu ft ($16) for a typical table — which is realistic. A 125 cu ft cylinder costs ~$30-40 and lasts several furniture jobs.

Also update the comment on line 310 to match:
```python
"usage_cu_ft_per_weld_hour": 25.0,  # CFH at standard flow rate
```

**Verify:** After this change, a decorative flat bar table should show $15-40 in shielding gas, not $100+.

### ISSUE 4: Build Sequence Dimensions Don't Match Cut List

**Current state:** The cut list generates precise dimensions (e.g., 9 layers from 20" to 4" stepping 2"). The build sequence receives a SUMMARY of the cut list but then makes up its own dimensions (7 layers with different measurements).

**Root cause:** In `_build_instructions_prompt()` (~line 360), the cut list is summarized as text descriptions:
```python
cut_lines.append('  - %s (qty %d, %s, cut: %s)' % (desc, qty, length_str, weld))
```

The descriptions are truncated and Gemini reconstructs geometry from these summaries instead of using exact numbers.

**Fix:** After the `cuts_text` assembly (~line 390), add a structured geometry summary that Gemini CANNOT misinterpret:

```python
# Build explicit geometry summary for Gemini
geometry_summary_parts = []
layer_count = 0
spacer_count = 0
for item in cut_list:
    desc_lower = item.get("description", "").lower()
    qty = item.get("quantity", 1)
    length = item.get("length_inches", 0)
    if "layer" in desc_lower or "decorative" in desc_lower:
        layer_count += 1
        geometry_summary_parts.append(
            "Layer %d: %d pieces @ %.1f\"" % (layer_count, qty, length)
        )
    elif "spacer" in desc_lower:
        spacer_count += qty

if geometry_summary_parts or spacer_count > 0:
    geometry_block = "\n\nEXACT GEOMETRY FROM CUT LIST (DO NOT DEVIATE):\n"
    geometry_block += "Total decorative layers: %d\n" % layer_count
    geometry_block += "Total spacers: %d\n" % spacer_count
    for part in geometry_summary_parts:
        geometry_block += part + "\n"
    geometry_block += "\nThe build sequence MUST reference these exact layer counts, piece counts, and dimensions.\n"
    geometry_block += "Do NOT invent different dimensions or layer counts.\n"
else:
    geometry_block = ""
```

Then inject `geometry_block` into the prompt string, right after `cuts_text` and before the TASK instruction.

### ISSUE 5: Non-Canonical Process Names (stock_prep_grind, post_weld_cleanup)

**Current state:** The labor estimator outputs process names like `stock_prep_grind` and `post_weld_cleanup` but the validation in `backend/knowledge/validation.py` line ~658 only recognizes 11 canonical names.

**Fix:** Add the missing process names to `CANONICAL_PROCESSES` in `validate_labor_processes()`:

```python
CANONICAL_PROCESSES = {
    "layout_setup", "cut_prep", "fit_tack", "full_weld", "grind_clean",
    "finish_prep", "clearcoat", "paint", "powder_coat",
    "hardware_install", "site_install", "final_inspection",
    "stock_prep_grind", "post_weld_cleanup",  # Added: common in furniture/decorative jobs
}
```

### ISSUE 6: "Unrecognized material type 'square_tubing'" Warning

**Current state:** The validation fires a warning about `square_tubing` not being recognized.

**Fix:** Find where material types are validated in `backend/knowledge/validation.py` and add `square_tubing` (and `flat_bar`, `round_tubing`, `angle_iron`, `channel`, `sheet`, `plate`, `pipe`) to the recognized types list.

### ISSUE 7: Flat Bar Cut Type Should Be Square, Not Miter

**Current state:** CS-2026-0022 shows ALL flat bar layers with `miter_45` cut type. Flat bar decorative layers are SQUARE cut — only the frame rails get mitered.

**Root cause:** The AI is defaulting to miter cuts for everything. The cut list prompt doesn't distinguish clearly enough.

**Fix:** In the cut list prompt (`_build_prompt()` in `ai_cut_list.py`), add explicit guidance in the RULES section:

```
- Decorative flat bar pieces in concentric/pyramid patterns are ALWAYS square cut. Only frame rails that form miter joints get miter_45 cuts.
- Spacers are ALWAYS square cut.
```

### ISSUE 8: Grind Spec Wrong — 40 Grit, Not 80→120

**Current state:** Some build sequences say "80-grit flap disc, followed by 120-grit flap disc" for the decorative stock prep. Burton's actual process: 40-grit grind IS the finish. No progression.

**Fix:** In `backend/knowledge/processes.py`, find the `decorative_stock_prep` process entry and update the steps to specify 40-grit only:

```python
"steps": [
    "Submerge full-length raw stock in vinegar bath (20-30% white vinegar)",
    "Soak 12-24 hours (unattended — NOT labor time)",
    "Pull stock, rinse immediately with warm water",
    "Scrub with dish soap and red scotch-brite pad (medium grit)",
    "Rinse again thoroughly",
    "Dry with clean towel",
    "Heavy grind ALL FOUR FACES with 40-grit flap disc on angle grinder",
    "40-grit texture IS the final brushed finish — do NOT follow with finer grits",
    "Stock is now finish-ready — cut to size from here",
],
```

Also add to the NEVER list:
```python
"NEVER": [
    "baking soda",
    "compressed air",
    "wire brush for cleanup",
    "chemical neutralizer",
    "80 grit then 120 grit",  # SHOP: CreateStage uses 40-grit as final finish
    "80-grit followed by 120-grit",
    "120 grit for final finish",
    "progressive grit sequence",
],
```

### ISSUE 9: Leveler Foot Installation — Two Valid Methods

**Current state:** Build sequence says "drill a hole" into square tube for leveler feet. You can't drill into 14ga tube reliably. Two correct methods exist:

**Method A — Weld-in plate (shop tools):**
Cut a 1" square piece of flat bar stock. Center punch, drill and tap to 3/8"-16. Weld this plate into the bottom of the tube leg, flush. Thread leveler foot in.

**Method B — Weld-in threaded bung (purchased):**
Purchase a 3/8"-16 weld-in threaded bung. Weld into the bottom of the tube leg. Thread leveler foot in.

**Fix:**
1. Add both methods to `backend/knowledge/processes.py` as a new process entry:
```python
"leveler_foot_install": {
    "name": "Leveler Foot Installation",
    "category": "hardware_install",
    "methods": {
        "weld_plate": {
            "description": "Cut 1\" square piece of flat bar. Center punch, drill 5/16\" pilot, drill 3/8\", tap 3/8\"-16. Weld plate into bottom of tube leg flush.",
            "tools": ["chop saw", "drill press", "5/16\" drill bit", "3/8\" drill bit", "3/8\"-16 tap", "tap handle", "MIG welder"],
            "materials_needed": ["flat bar scrap (shop stock)"],
            "time_per_leg_minutes": 15,
        },
        "weld_bung": {
            "description": "Insert 3/8\"-16 weld-in threaded bung into bottom of tube leg. MIG weld in place, flush with tube end.",
            "tools": ["MIG welder"],
            "materials_needed": ["3/8\"-16 weld-in threaded bung"],
            "time_per_leg_minutes": 5,
        },
    },
    "NEVER": [
        "drill directly into tube wall",
        "drill a hole in the tube",
        "drill into the bottom of the leg",
    ],
    "notes": "For hollow tube legs (square/round tube), you CANNOT just drill and tap the tube wall. Either weld in a solid plate and tap it, or use a purchased weld-in bung.",
},
```

2. Add threaded bungs to `backend/calculators/furniture_table.py` hardware list:
```python
{
    "description": "3/8\"-16 weld-in threaded bung",
    "quantity": 4,
    "options": [
        {"supplier": "Amazon", "unit_price": 2.50, "url": "https://www.amazon.com/s?k=3/8-16+weld+in+threaded+bung"},
        {"supplier": "McMaster-Carr", "unit_price": 3.75, "url": "https://www.mcmaster.com/weld-in-bungs"},
    ],
},
```

3. Add "drill directly into tube" to the BANNED_TERMS in `backend/knowledge/validation.py`:
```python
"leveler_install": [
    "drill a hole in the tube",
    "drill into the tube",
    "drill a hole in the leg",
    "drill into the bottom of the leg",
    "drill a 3/8 hole",
],
```

### ISSUE 10: Wall Thickness Not Asked When Missing

**Current state:** User says "1 inch square tube" without specifying gauge. AI assumes 14ga. This could mean 14ga ($X/ft), 11ga (2x the price), or even 3/16" wall (structural).

**Fix:** In `backend/question_trees/data/furniture_table.json`, add a conditional question that fires when the user's description mentions tubing without a gauge:

Find the materials-related questions and add:
```json
{
    "id": "wall_thickness",
    "text": "What wall thickness for the square tube?",
    "type": "select",
    "options": [
        {"value": "14ga", "label": "14 gauge (0.075\") — standard furniture weight"},
        {"value": "11ga", "label": "11 gauge (0.120\") — heavy duty"},
        {"value": "3/16", "label": "3/16\" wall — structural"},
        {"value": "1/4", "label": "1/4\" wall — heavy structural"},
        {"value": "other", "label": "Other (specify)"}
    ],
    "required": true,
    "condition": "materials contain tubing without gauge specification"
}
```

If the question tree system doesn't support conditional logic this complex, add it as a REQUIRED question in the furniture table flow that always shows up — it's always relevant and takes 2 seconds to answer.

---

## VERIFICATION CHECKLIST (run ALL of these)

1. `pytest tests/ -v` — all tests pass (existing + any new ones)
2. `grep -ri "baking soda" FAB_KNOWLEDGE.md` — should appear ONLY in a "DO NOT" or corrected context
3. `grep -ri "baking soda" backend/knowledge/processes.py` — should appear ONLY in NEVER lists
4. `python3 -c "from backend.calculators.fab_knowledge import _build_decorative_stock_prep; t = _build_decorative_stock_prep(); assert 'baking soda' not in t or 'NEVER' in t.split('baking soda')[0], 'FAIL'; print('PASS: structured data wins')"` 
5. `grep -n "weld_linear_inches / " backend/hardware_sourcer.py` — should show `/ 80.0`, NOT `/ 10.0`
6. Generate a test quote for a decorative flat bar table. Verify:
   - NO "baking soda" in build sequence text (stripped, not just flagged)
   - Shielding gas < $50
   - Build sequence layer count matches cut list layer count
   - Flat bar pieces show `square` cut type, not `miter_45`
   - Grind spec says "40-grit" not "80-grit then 120-grit"
   - No "drill a hole in the tube" in leveler step
   - Validation warnings section is clean (no errors, maybe a few info-level notes)
7. `grep -rn "validate_full_output\|check_banned_terms" backend/calculators/ backend/routers/ | grep -v __pycache__ | grep -v import` — should show at least 2 CALL SITES

## COMMIT

```
git add -A && git commit -m "The Big One: strip banned terms, fix gas calc, sync geometry, fix grind spec, add leveler methods, wall thickness question

Fixes 10 outstanding issues in one prompt:
1. Banned terms (baking soda, compressed air) now STRIPPED from output, not just flagged
2. FAB_KNOWLEDGE.md corrected — no more baking soda/compressed air in process steps
3. _build_decorative_stock_prep() now uses structured data as source of truth
4. Shielding gas calculation fixed — 80 in/hr travel speed, not 10 (was 6-12x over)
5. Cut list geometry explicitly passed to build sequence prompt — layer/spacer counts enforced
6. Non-canonical process names added to validation whitelist
7. Material type 'square_tubing' added to recognized types
8. Flat bar cuts forced to square (not miter) in cut list prompt rules
9. Grind spec corrected: 40-grit IS the finish, no 80→120 progression
10. Leveler foot installation: two methods (weld plate + weld bung), drill-into-tube banned
11. Wall thickness question added to furniture table question tree" && git push
```
