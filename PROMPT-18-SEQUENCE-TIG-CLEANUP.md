# PROMPT 18 — Fix Vinegar Sequence, Enforce TIG for Decorative, Clean Up Remaining Issues

## INTEGRATION RULES (from CLAUDE.md)
Building a module is not done until it's CALLED in the pipeline. After any change, trace the full path. Verify with grep.

---

## ISSUE 1: Vinegar Bath Must Be Step 1 (CRITICAL — Shop Scheduling)

**Problem:** The build sequence puts vinegar bath at Step 8, after all frame cutting and welding. The vinegar soak takes 12-24 hours and is UNATTENDED. Putting it after frame work means the fabricator builds the frame, then waits an entire day doing nothing while the flat bar soaks. This is a wasted day of shop time.

**Correct sequence:** Start the vinegar soak FIRST. While it soaks (overnight/next day), cut and build the frame. When you come back, the flat bar is ready to pull, wash, grind, and cut.

**This is Principle 6 (Constraints Propagate Forward) applied to shop scheduling — unattended processes with long durations start FIRST so attended work happens in parallel.**

**Fix:** In the build instructions prompt in `backend/calculators/ai_cut_list.py`, inside `_build_instructions_prompt()`, add this rule to the RULES section (after the existing rules 1-7):

```
8. SCHEDULING: Unattended processes with long wait times (vinegar bath 12-24hr, paint cure, epoxy set) must be the FIRST step. Start the clock immediately. All attended work (cutting, welding, grinding) happens WHILE the unattended process runs. Never schedule an unattended long-duration process AFTER attended work — that wastes an entire day of shop time.
9. For jobs requiring vinegar bath / mill scale removal on stock that needs finish grinding before cutting: Step 1 is ALWAYS "Submerge stock in vinegar bath." Steps 2-N are frame/structural work done WHILE the bath runs. The step AFTER all frame work is "Pull stock from vinegar bath, wash, grind, cut."
```

Also add this to the `finish_context` block for bare metal jobs (the `needs_mill_scale_removal` section around line ~555):

```python
if needs_mill_scale_removal:
    finish_context = """
FINISH CONTEXT:
This job requires mill scale removal (bare metal finish: clear coat, raw, brushed, or patina).

CRITICAL SCHEDULING RULE: The vinegar bath takes 12-24 hours and is UNATTENDED.
- Step 1 MUST be: Submerge flat bar/decorative stock in vinegar bath (this takes 30 seconds of labor).
- Steps 2-N: Do ALL frame/structural work while the vinegar bath runs overnight.
- After frame work is done: Pull stock from bath, rinse with warm water, scrub with dish soap and red scotch-brite pad, dry with clean towel, then heavy grind with 40-grit flap disc.
- NEVER schedule the vinegar bath AFTER frame work. That wastes an entire day.

Apply Principles 1 (workability) and 2 (access) to determine WHEN mill scale removal happens based on the specific pieces and assembly in this project.
- Decorative flat bar / small pieces that will be hard to grind after cutting → remove on RAW STOCK before cutting.
- Large structural pieces / tube frames → remove AFTER all welding is done.
Think through which pieces need prep before cutting vs after assembly.
"""
```

## ISSUE 2: TIG for Decorative Flat Bar — Not MIG

**Problem:** V22 correctly used TIG for decorative flat bar layers. V24 regressed to MIG. The decorative flat bar pieces are 1" x 1/8" — thin, visible, furniture-grade joints. This is textbook TIG work. MIG on 1/8" flat bar risks burn-through, excessive spatter, and ugly welds that are hard to clean up in tight spaces between layers.

**Fix:** In the build instructions prompt (same `_build_instructions_prompt()` method), add to the RULES section:

```
10. WELD PROCESS SELECTION: Decorative flat bar work (1/8" or thinner, visible joints, furniture/ornamental pieces) MUST use TIG (GTAW), not MIG. TIG gives cleaner, more precise welds with less spatter and less heat input — critical for pre-finished decorative surfaces. MIG is for structural frame assembly (square tube joints, leg-to-frame connections). Spacer blocks can use either MIG (for speed) or TIG (for precision on small parts).
```

Also add this to the `weld_note` section (~line 400):

```python
# Force TIG for decorative elements
decorative_keywords = ["decorative", "flat bar", "ornamental", "pattern", "layered", "woven"]
has_decorative = any(k in all_fields_lower for k in decorative_keywords)
if has_decorative:
    weld_note += "\nCRITICAL: All decorative flat bar welding MUST use TIG (GTAW), not MIG. The flat bar is 1/8\" thick with pre-finished surfaces — MIG would cause burn-through, excess spatter, and damage the finish. Use MIG only for the structural square tube frame."
```

## ISSUE 3: Banned Term Replacement Ordering — Longest Match First

**Problem:** The `BANNED_TERM_REPLACEMENTS` dict in `ai_cut_list.py` is unordered. When Gemini generates "neutralize with a baking soda solution", the shorter match "baking soda" → "dish soap" fires before the longer match "baking soda solution" → "dish soap and warm water". Result: "dish soap solution" instead of the intended replacement.

**Fix:** In `_strip_banned_terms_from_steps()`, sort the replacements by length (longest first) before applying:

```python
def _strip_banned_terms_from_steps(steps):
    """Replace banned terms with correct shop terms. Longest match first."""
    # Sort by length of banned term (longest first) to prevent partial matches
    sorted_replacements = sorted(
        BANNED_TERM_REPLACEMENTS.items(),
        key=lambda x: len(x[0]),
        reverse=True
    )
    
    for step in steps:
        for field_name in ("description", "safety_notes"):
            text = step.get(field_name, "")
            if not text:
                continue
            for banned, replacement in sorted_replacements:
                pattern = re.compile(re.escape(banned), re.IGNORECASE)
                text = pattern.sub(replacement, text)
            step[field_name] = text

        # Clean tools list/string
        tools = step.get("tools", "")
        if isinstance(tools, list):
            cleaned = []
            for tool in tools:
                t = str(tool)
                for banned, replacement in sorted_replacements:
                    pattern = re.compile(re.escape(banned), re.IGNORECASE)
                    t = pattern.sub(replacement, t)
                cleaned.append(t)
            step["tools"] = cleaned
        elif isinstance(tools, str):
            for banned, replacement in sorted_replacements:
                pattern = re.compile(re.escape(banned), re.IGNORECASE)
                tools = pattern.sub(replacement, tools)
            step["tools"] = tools
```

## ISSUE 4: "Drill and tap" Still in Build Sequence for Leveler Feet

**Problem:** Step 11 in V24 still says "Drill a pilot hole, then tap a thread into the bottom center of each leg." The replacement dict has entries for "drill into tube" but not for "drill a pilot hole" or "drill and tap" in the context of legs/leveler feet.

**Fix:** Add these to `BANNED_TERM_REPLACEMENTS`:

```python
# Leveler installation — more patterns
"drill a pilot hole": "weld a threaded bung",
"drill and tap": "weld in a threaded bung and tap",
"drill a hole in the bottom": "weld a threaded bung into the bottom",
"drill a hole into the bottom": "weld a threaded bung into the bottom",
"tap a thread into the bottom": "weld a threaded bung into the bottom",
"drill press, hand drill, tap set, cutting fluid": "MIG welder, threaded bungs",
```

Also update the `BANNED_TERMS` in `backend/knowledge/validation.py` for the `leveler_install` context to catch these:

```python
"leveler_install": [
    "drill a hole in the tube",
    "drill into the tube",
    "drill a hole in the leg",
    "drill into the bottom of the leg",
    "drill a 3/8 hole",
    "drill a pilot hole",
    "drill and tap",
    "tap a thread into",
    "drill through tube wall",
    "self-tapping screw",
],
```

## ISSUE 5: Build Sequence Layer Count Still Doesn't Match Cut List

**Problem:** V24 cut list has 11 layers (20" → 5"). Build sequence Step 9 lists only 7 layers (20", 18", 16", 14", 12", 10", 8"). Step 13 says "Layers 2-7". The geometry summary from Prompt 17 is being generated but Gemini is still ignoring it.

**Fix:** Make the geometry enforcement MORE explicit in the prompt. In `_build_geometry_summary()`, change the output format to be more commanding:

After the geometry summary is built, add a hard constraint line:

```python
if layer_count > 0:
    lines.append("")
    lines.append("⚠️ HARD CONSTRAINT: The build sequence MUST install exactly %d decorative layers." % layer_count)
    lines.append("Each layer MUST use the EXACT dimensions from the cut list above.")
    lines.append("Do NOT consolidate layers. Do NOT skip layers. Do NOT change dimensions.")
    lines.append("If the cut list says 11 layers from 20\" to 5\", the build sequence must have 11 layers from 20\" to 5\".")
```

Also add a `layer_count` and `spacer_count` variable to the geometry block:

```python
# Count layers and spacers from cut list
layer_count = 0
spacer_count = 0
for item in cut_list:
    desc_lower = item.get("description", "").lower()
    qty = item.get("quantity", 1)
    if "layer" in desc_lower or "decorative" in desc_lower:
        if "spacer" not in desc_lower:
            layer_count += 1
    if "spacer" in desc_lower:
        spacer_count += qty
```

## ISSUE 6: "dish soap solution" False Positive in Validation

**Problem:** After stripping "baking soda" and replacing with "dish soap", the validation check sees "dish soap" and... wait, is "dish soap solution" actually flagged? Let me check — the validation checks for "baking soda" and "baking soda solution" in the BANNED_TERMS. If the stripping is working correctly (longest first), the output should have "dish soap and warm water" not "dish soap solution". 

If the false positive persists after Fix #3 (longest match first), then the validation is running BEFORE the stripping. 

**Fix:** Verify the order in `generate_build_instructions()`:
1. FIRST: `_strip_banned_terms_from_steps(steps)` 
2. THEN: `check_banned_terms()` on the stripped text

If the order is wrong, swap them. The validation should check the STRIPPED text, not the raw Gemini output. The banned term check should only catch things the stripping MISSED.

Check the current code order in `ai_cut_list.py` around line ~265-285. It should be:
```python
# 1. Strip banned terms from customer-facing text FIRST
_strip_banned_terms_from_steps(steps)

# 2. THEN check for any remaining banned terms the stripping missed
for context in ["vinegar_bath_cleanup", ...]:
    violations = check_banned_terms(full_text_after_stripping, context)
```

If the check happens BEFORE the strip, move it AFTER.

---

## VERIFICATION

1. `pytest tests/ -v` — all tests pass
2. Generate a test quote for a decorative flat bar table with clear coat finish
3. Verify:
   - Step 1 is vinegar bath / submerge stock (NOT frame cutting)
   - Frame work happens in Steps 2-N while vinegar soaks
   - Decorative flat bar welding specifies TIG, not MIG
   - Structural frame welding specifies MIG
   - No "baking soda", "compressed air", "drill a pilot hole" in any step
   - Layer count in build sequence matches cut list
   - No false positive validation warnings for "dish soap"
   - Shielding gas < $50

## COMMIT

```
git add -A && git commit -m "Fix: vinegar bath first, TIG for decorative, longest-match stripping, drill-to-bung, layer count enforcement

- Vinegar bath MUST be Step 1 — unattended 12-24hr process starts first, frame work during soak
- TIG enforced for all decorative flat bar welding (1/8\" visible joints)
- MIG for structural frame only  
- Banned term replacement now sorts longest-first (prevents 'dish soap solution' partial match)
- More drill/tap patterns caught and replaced with weld-in bung
- Geometry summary enforces exact layer count from cut list
- Validation runs AFTER stripping to prevent false positives" && git push
```
