# PROMPT 15 — Audit Your Own Mistakes, Then Fix Them

## PART 1 — READ THIS FIRST. UNDERSTAND WHAT WENT WRONG.

You've made the same class of error across Prompts 13 and 14. Before you touch any code, understand the pattern:

### Mistake 1: You built a system and didn't wire it in.
Prompt 13 asked you to create a structured knowledge base with validation. You created 5,243 lines of excellent structured data in `backend/knowledge/`. You wrote `validate_full_output()`, `check_banned_terms()`, and dozens of validation rules. All correct. All tested.

**Then you never called any of it in the actual quote pipeline.**

Zero calls to `validate_full_output()` in `ai_cut_list.py`, `quote_session.py`, or `pdf_generator.py`. The functions exist. They work. They're imported. But they sit there doing nothing while Gemini's hallucinated output goes straight to the customer's PDF.

This is like building a smoke detector, testing the battery, mounting it on the wall — and never connecting it to the alarm.

### Mistake 2: Your fallback logic overrides the fix.
In `_build_decorative_stock_prep()`, you wrote this:

```python
# Try structured data first
proc = get_process("decorative_stock_prep")
if proc:
    result = "..."  # Correct output, no baking soda ✅

# Supplement with FAB_KNOWLEDGE.md prose
raw = _find_section("DECORATIVE STOCK PREP")
if raw:
    return "..." + old prose  # ← Returns OLD prose WITH baking soda ❌

if proc:
    return result  # ← NEVER REACHED because FAB_KNOWLEDGE.md has the section
```

You built the correct answer from structured data, then threw it away and returned the old prose that still contains "baking soda" on line 439 of FAB_KNOWLEDGE.md. The structured data you spent an entire session building is literally never used for this section.

### Mistake 3: You didn't verify the integration end-to-end.
You ran `pytest` and all 384 tests passed. But those tests don't test whether a real quote contains "baking soda" or whether validation actually runs during quote generation. Passing tests ≠ working product. The only real test is: generate a quote and check the output.

### The Pattern:
Every prompt, you build something correct in isolation, then fail to integrate it into the existing system. The individual pieces are good. The wiring is where it breaks. From now on:

**RULE: After any change, trace the full path from user input → AI generation → validation → PDF output. If your new code isn't in that path, it's not done.**

### Add this to CLAUDE.md under a new section "## Integration Rules":

```markdown
## Integration Rules (Learned from Prompts 13-15)

1. **Building a module is not done until it's CALLED in the pipeline.** After creating any new function, grep the codebase to verify it's called in the actual request flow (not just imported). If `grep -rn "function_name" backend/routers/ backend/calculators/` shows zero calls, you're not done.

2. **Fallback logic must not override the fix.** If you build a new data source to replace an old one, the old source must be REMOVED or SUBORDINATED. Never write `if old_source: return old_data` after building new_data — the old source will always exist and will always win.

3. **FAB_KNOWLEDGE.md is SUPPLEMENTAL, not primary.** Structured data in `backend/knowledge/` is the source of truth. FAB_KNOWLEDGE.md provides prose context for build sequences only. If structured data and FAB_KNOWLEDGE.md contradict, structured data wins. Always.

4. **Test integration, not just units.** After any change, the real test is: generate a quote and verify the output. Unit tests passing means nothing if the integration is broken.

5. **Validation must be in the hot path.** `validate_full_output()` must run on every quote before it reaches PDF generation. If validation isn't in the hot path, it doesn't exist.
```

---

## PART 2 — THE SURGICAL FIXES

Now fix the actual problems. These are exact changes — do not improvise.

### Fix 1: Delete baking soda from FAB_KNOWLEDGE.md

In `FAB_KNOWLEDGE.md`, find lines 439-440:
```
3. Pull stock, rinse immediately, neutralize with baking soda/water
4. Dry instantly with compressed air (prevents flash rust)
```

Replace them with:
```
3. Pull stock, rinse immediately with warm water
4. Scrub with dish soap and red scotch-brite pad (medium grit)
5. Rinse again thoroughly
6. Dry with a clean towel
```

Also verify line 119 already says the correct process (it does — don't change it).

### Fix 2: Fix `_build_decorative_stock_prep()` in `backend/calculators/fab_knowledge.py`

Replace the entire function with:

```python
def _build_decorative_stock_prep():
    """Build decorative stock prep from structured process data.
    
    Structured data in backend/knowledge/processes.py is the source of truth.
    FAB_KNOWLEDGE.md prose about spacer dimensions is appended as supplemental
    context, but NEVER overrides the structured process steps or NEVER list.
    """
    proc = get_process("decorative_stock_prep")
    if not proc:
        # Fall back to FAB_KNOWLEDGE.md only if structured data missing
        raw = _find_section("DECORATIVE STOCK PREP")
        if raw:
            lines = raw.strip().split("\n")
            kept = [l for l in lines if l.strip()]
            return "DECORATIVE STOCK PREP — PROCESS ORDER:\n" + "\n".join(kept[:50])
        return ""

    # Build from structured data (source of truth)
    steps = proc.get("steps", [])
    never = proc.get("NEVER", [])
    notes = proc.get("notes", "")
    
    result = "DECORATIVE STOCK PREP — PROCESS ORDER:\n"
    if notes:
        result += notes + "\n\n"
    result += "Steps:\n"
    for i, step in enumerate(steps, 1):
        result += "%d. %s\n" % (i, step)
    if never:
        result += "\nNEVER do any of these during this process:\n"
        for term in never:
            result += "- %s\n" % term
    
    # Append spacer dimension context from FAB_KNOWLEDGE.md (supplemental only)
    raw = _find_section("DECORATIVE STOCK PREP")
    if raw:
        # Extract only the spacer/dimension paragraphs, not the process steps
        for line in raw.split("\n"):
            line_lower = line.lower()
            if any(k in line_lower for k in ["spacer", "0.75", "0.50", "gap between", "why this matters"]):
                result += "\n" + line
    
    return result
```

### Fix 3: Wire validation into the quote pipeline

Find where build instructions are returned in `backend/calculators/ai_cut_list.py` — the `generate_build_instructions()` method, around line 145:

```python
if steps and len(steps) > 0:
    return steps
```

Change it to:

```python
if steps and len(steps) > 0:
    # Validate build sequence before returning
    from ..knowledge.validation import check_banned_terms, validate_full_output
    full_text = " ".join(s.get("description", "") for s in steps)
    
    # Check for banned terms
    for context in ["vinegar_bath_cleanup", "decorative_stock_prep", "decorative_assembly"]:
        violations = check_banned_terms(full_text, context)
        if violations:
            logger.warning("BUILD SEQUENCE VALIDATION FAILED — banned terms found [%s]: %s", context, violations)
            for step in steps:
                desc = step.get("description", "")
                for v in violations:
                    if v.lower() in desc.lower():
                        step["description"] = desc + " ⚠️ REVIEW: contains banned term '%s'" % v
    
    return steps
```

### Fix 4: Wire validation into quote output

Find where the final quote is assembled in `backend/routers/quote_session.py` or `backend/routers/ai_quote.py` — wherever the quote dict is built before being returned to the frontend/PDF. Add a validation summary:

```python
from backend.knowledge.validation import validate_full_output

# After build sequence and cut list are generated:
validation_result = validate_full_output(
    job_type=job_type,
    cut_list_items=cut_list_items,
    labor_processes=labor_data.get("processes", []) if labor_data else [],
    build_sequence_text=" ".join(
        s.get("description", "") for s in build_instructions
    ) if build_instructions else "",
    consumables=consumables_data if consumables_data else {}
)

if not validation_result.get("passed", True):
    quote_data["validation_warnings"] = validation_result.get("failures", [])
    logger.warning("Quote validation failures: %s", validation_result.get("failures"))
```

### Fix 5: Verify end-to-end

After making all changes:
1. `pytest tests/ -v` — all tests pass
2. `python3 -c "from backend.calculators.fab_knowledge import _build_decorative_stock_prep; text = _build_decorative_stock_prep(); assert 'baking soda' not in text.lower() or 'NEVER' in text.split('baking soda')[0], 'Baking soda appears outside NEVER list!'; print('PASS: baking soda only in NEVER list or absent')"` 
3. `grep -rn "validate_full_output\|check_banned_terms" backend/calculators/ backend/routers/ | grep -v __pycache__ | grep -v "^.*:.*import"` — should show at least 2 CALL SITES (not just imports)

### Commit:

```
git add -A && git commit -m "Fix: wire validation into pipeline, fix fallback override, kill baking soda

Root cause: Prompt 13 built 5,243 lines of structured knowledge + validation
but never wired validation into the quote pipeline. The _build_decorative_stock_prep()
function built correct output from structured data, then threw it away and
returned old FAB_KNOWLEDGE.md prose containing baking soda.

Fixes:
- _build_decorative_stock_prep() now uses structured data as source of truth
- FAB_KNOWLEDGE.md lines 439-440 corrected (baking soda → dish soap + scotch pads)
- check_banned_terms() called on every build sequence before return
- validate_full_output() called on assembled quote before PDF
- CLAUDE.md updated with integration rules to prevent repeat of this class of error

Verified: baking soda cannot appear in output except in NEVER list" && git push
```
