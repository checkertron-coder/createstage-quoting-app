# PROMPT 27 — Complete Gemini Removal + Claude Model Update

## Problem Statement

The CreateStage quoting app was built on Gemini as its AI engine. Prompt 26 added a Claude client and an `ai_client.py` router that prefers Claude but falls back to Gemini. However, Gemini code is still embedded in **6 separate files** with direct Gemini calls, Gemini-named functions, and `GEMINI_API_KEY` references. The `ai_client.py` router adds unnecessary indirection.

Additionally, the Claude model defaults are set to `claude-sonnet-4-20250514` (which resolves to Sonnet 4.5 — an older model). They must be updated to `claude-sonnet-4-6`.

Gemini was the source of repeated regressions across 8+ quotes: grinding welds (reverted 3× to "grind all welds smooth"), duplicate overhead beams, wrong material profiles, and fabrication hallucinations. It must be fully removed — no fallback, no references, no dead code.

**This prompt also fixes 3 lingering bugs** that P25/P26 specced but never landed on the M4:
1. HSS profiles missing from the material catalog (causes $0.00 pricing and "profile not found" warnings)
2. Channel profile key mismatch (Claude outputs `channel_1.5x0.125`, catalog expects `punched_channel_1.5x0.5_fits_0.625`)
3. Stale comments/docstrings referencing Gemini throughout the codebase

## Acceptance Criteria

1. **`backend/gemini_client.py` — DELETED.** This file must not exist after implementation.
2. **`backend/ai_client.py` — DELETED.** The router layer is removed. All files that imported from `ai_client` now import directly from `claude_client`.
3. **Every `.py` file in `backend/`** that references `gemini`, `GEMINI`, `ai_client`, or `claude-sonnet-4-20250514` has been updated.
4. Default model IDs in `claude_client.py` and `claude_reviewer.py` are `claude-sonnet-4-6`.
5. HSS profiles (`hss_4x4_0.25`, `hss_6x4_0.25`) exist in `PRICE_PER_FOOT` in `material_lookup.py` with correct pricing.
6. Channel profile key mapping handles Claude outputting non-catalog keys like `channel_1.5x0.125`.
7. The app starts without import errors when only `ANTHROPIC_API_KEY` is set (no `GEMINI_API_KEY` needed).
8. If `ANTHROPIC_API_KEY` is missing, the app still starts — AI features return graceful fallbacks, app does not crash.
9. **Zero results** from these grep commands after implementation:
   ```bash
   grep -rn "gemini_client" backend/ --include="*.py"
   grep -rn "ai_client" backend/ --include="*.py"
   grep -rn "GEMINI" backend/ --include="*.py"
   grep -rn "claude-sonnet-4-20250514" backend/ --include="*.py"
   ```
   (Exception: the word "gemini" in lowercase may appear in comments explaining the migration, e.g., "Replaced Gemini with Claude in March 2026". But NO functional code, NO imports, NO function names containing "gemini".)

## Constraint Architecture

### What Claude Code MUST understand before touching anything:

The app has a 5-stage pipeline:
- Stage 1 (Intake): `question_trees/engine.py` — asks questions, extracts fields from descriptions and photos using AI
- Stage 2 (Clarify): Same engine, follow-up questions
- Stage 3 (Calculate): `calculators/*.py` — generates cut lists and material lists using AI via `ai_cut_list.py`
- Stage 4 (Estimate): `labor_estimator.py` — estimates labor hours using AI
- Stage 5 (Price): `routers/quote_session.py` — applies pricing, generates PDF
- Post-Stage 5: `claude_reviewer.py` — reviews completed quote (already uses Claude directly)
- Separate endpoint: `routers/ai_quote.py` — standalone AI quoting endpoint (legacy, but still active)
- Separate feature: `bid_parser.py` — parses uploaded bid documents using AI

**Every one of these stages calls AI.** After this prompt, every AI call goes through `claude_client.py`. No exceptions.

### FILES TO DELETE (2 files)

#### 1. `backend/gemini_client.py` — DELETE ENTIRELY
The Gemini API client. No longer needed.

#### 2. `backend/ai_client.py` — DELETE ENTIRELY
The router that picked Claude vs Gemini. No longer needed — Claude is the only provider.

### FILES TO MODIFY (7 files)

---

#### File 1: `backend/claude_client.py`

**Current (line 4):**
```python
Drop-in replacement for gemini_client.py. All AI generation calls can use
this module instead. Provides the same interface: call_fast, call_deep,
call_vision, is_configured, get_model_name.
```

**Change to:**
```python
Centralized AI client for the CreateStage quoting app. All AI generation
calls use this module. Provides: call_fast, call_deep, call_vision,
is_configured, get_model_name.
```

**Current (lines 23-24):**
```python
_DEFAULT_FAST = "claude-sonnet-4-20250514"
_DEFAULT_DEEP = "claude-sonnet-4-20250514"
```

**Change to:**
```python
_DEFAULT_FAST = "claude-sonnet-4-6"
_DEFAULT_DEEP = "claude-sonnet-4-6"
```

No other changes to this file.

---

#### File 2: `backend/claude_reviewer.py`

**Current (line 22):**
```python
CLAUDE_REVIEW_MODEL = os.environ.get("CLAUDE_REVIEW_MODEL", "claude-sonnet-4-20250514")
```

**Change to:**
```python
CLAUDE_REVIEW_MODEL = os.environ.get("CLAUDE_REVIEW_MODEL", "claude-sonnet-4-6")
```

No other changes to this file.

---

#### File 3: `backend/calculators/ai_cut_list.py`

**Current docstring (lines 1-10):**
```python
"""
AI-assisted cut list generator for custom/complex jobs.

Uses Claude (preferred) or Gemini (fallback) to interpret freeform designs
into detailed cut lists. Called by ALL 25 calculators when a user provides
a design description. The AI thinks through design first, then generates
precise cut lists.

Fallback: if the AI fails or returns invalid JSON, the calling calculator
uses its own template-based output. Never crashes.
"""
```

**Change to:**
```python
"""
AI-assisted cut list generator for custom/complex jobs.

Uses Claude API to interpret freeform designs into detailed cut lists.
Called by ALL 25 calculators when a user provides a design description.
The AI thinks through design first, then generates precise cut lists.

Fallback: if Claude fails or returns invalid JSON, the calling calculator
uses its own template-based output. Never crashes.
"""
```

**Current import (line 18):**
```python
from ..ai_client import call_fast, is_configured
```

**Change to:**
```python
from ..claude_client import call_fast, is_configured
```

**Current method name and docstring (around line 917-920):**
```python
    def _call_ai(self, prompt: str) -> str:
        """Call AI provider (Claude or Gemini). Raises RuntimeError on failure."""
        text = call_fast(prompt, timeout=180)
```

**Change to:**
```python
    def _call_ai(self, prompt: str) -> str:
        """Call Claude API. Raises RuntimeError on failure."""
        text = call_fast(prompt, timeout=180)
```

---

#### File 4: `backend/routers/ai_quote.py`

This file has its own `call_gemini()` and `call_gemini_background()` functions (lines 199-253) plus a `/test-gemini` endpoint (line 529). These all route through `ai_client.call_deep` already, so the actual API call will work once imports are fixed. But the function names and docstrings are wrong.

**Current docstring (lines 1-10):**
```python
"""
AI-powered quoting endpoint — powered by Gemini.

User describes a job in plain English.
Gemini interprets it, returns structured line items.
The app calculates all the math using real Osario/Wexler pricing.
...
"""
```

**Change to:**
```python
"""
AI-powered quoting endpoint — powered by Claude.

User describes a job in plain English.
Claude interprets it, returns structured line items.
The app calculates all the math using real Osorio/Wexler pricing.
...
"""
```

**Current import (line 21):**
```python
from ..ai_client import call_deep, get_model_name, is_configured
```

**Change to:**
```python
from ..claude_client import call_deep, get_model_name, is_configured
```

**Rename functions:**
- `call_gemini(prompt)` (line 199) → `call_claude(prompt)`
- `call_gemini_background(prompt)` (line 228) → `call_claude_background(prompt)`
- Update ALL references to these functions within the file (lines 260, 279, 531)
- Update error messages from `"GEMINI_API_KEY not configured"` → `"ANTHROPIC_API_KEY not configured"`
- Update error messages from `"Gemini call failed"` → `"Claude call failed"`

**Rename endpoint (line 529):**
```python
def test_gemini():
```
→
```python
def test_claude():
```
And update the route decorator above it from `/test-gemini` to `/test-claude` (if it has one — check the `@router` decorator).

**Update `_run_estimate` docstring (around line 259):**
```python
"""Background task: call Gemini and return formatted estimate result."""
```
→
```python
"""Background task: call Claude and return formatted estimate result."""
```

---

#### File 5: `backend/bid_parser.py`

**Current import (line 19):**
```python
from .ai_client import call_deep, is_configured
```

**Change to:**
```python
from .claude_client import call_deep, is_configured
```

**Rename method (line 193):**
```python
def _extract_with_gemini(self, text: str) -> list:
```
→
```python
def _extract_with_claude(self, text: str) -> list:
```

**Update the call site (line 145):**
```python
items = self._extract_with_gemini(text)
extraction_method = "gemini"
```
→
```python
items = self._extract_with_claude(text)
extraction_method = "claude"
```

**Update the warning message (line 199):**
```python
logger.warning("No GEMINI_API_KEY — using keyword-based fallback for bid parsing")
```
→
```python
logger.warning("No ANTHROPIC_API_KEY — using keyword-based fallback for bid parsing")
```

---

#### File 6: `backend/labor_estimator.py`

**Current import (line 18):**
```python
from .ai_client import call_deep
```

**Change to:**
```python
from .claude_client import call_deep
```

**Rename method (line 402):**
```python
def _call_gemini(self, prompt: str) -> str:
    """Call Gemini API. Raises RuntimeError on failure."""
    text = call_deep(prompt, timeout=90)
    if text is None:
        raise RuntimeError("Gemini returned no response")
    return text
```
→
```python
def _call_claude(self, prompt: str) -> str:
    """Call Claude API. Raises RuntimeError on failure."""
    text = call_deep(prompt, timeout=90)
    if text is None:
        raise RuntimeError("Claude returned no response")
    return text
```

**Find and update ALL call sites** within the file that reference `self._call_gemini(` → `self._call_claude(`. Search the entire file.

**Update the `_parse_response` docstring (around line 410):**
```python
"""
Parse Gemini JSON response into LaborEstimate.
...
"""
```
→
```python
"""
Parse Claude JSON response into LaborEstimate.
...
"""
```

Also update any comment that says "Gemini" or "AI total" to reference Claude.

---

#### File 7: `backend/question_trees/engine.py`

**Current import (line 15):**
```python
from ..ai_client import call_fast, call_vision as _gemini_vision
```

**Change to:**
```python
from ..claude_client import call_fast, call_vision as _claude_vision
```

**Rename functions:**
- `_call_gemini_extract` (line 332) → `_call_claude_extract`
- `_call_gemini_vision` (line 440) → `_call_claude_vision`

**Update ALL call sites within the file:**
- Line 88: `extracted = _call_gemini_extract(prompt)` → `extracted = _call_claude_extract(prompt)`
- Line 140: `result = _call_gemini_vision(vision_prompt, image_b64, mime_type)` → `result = _call_claude_vision(vision_prompt, image_b64, mime_type)`

**Inside `_call_claude_vision` (was `_call_gemini_vision`):**
```python
text = _gemini_vision(prompt, image_b64, mime_type, timeout=60)
```
→
```python
text = _claude_vision(prompt, image_b64, mime_type, timeout=60)
```

---

#### File 8: `backend/config.py`

**Current (lines 12-16):**
```python
GEMINI_API_KEY: str = ""
GEMINI_MODEL: str = "gemini-2.5-flash"
GEMINI_CUTLIST_MODEL: str = "gemini-2.5-flash"
GEMINI_FAST_MODEL: str = ""
GEMINI_DEEP_MODEL: str = ""
```

**Remove all 5 lines.** The Claude env vars are already handled in `claude_client.py` via `os.getenv()`. The config class doesn't need them.

If other Claude config lines don't exist in this file yet, add:
```python
ANTHROPIC_API_KEY: str = ""
CLAUDE_FAST_MODEL: str = "claude-sonnet-4-6"
CLAUDE_DEEP_MODEL: str = "claude-sonnet-4-6"
CLAUDE_REVIEW_MODEL: str = "claude-sonnet-4-6"
```

---

### MATERIAL CATALOG FIX: `backend/calculators/material_lookup.py`

The HSS profiles are already in `PRICE_PER_FOOT` (lines ~99-101):
```python
"hss_4x4_0.25": 8.25,
"hss_6x4_0.25": 12.00,
```

These are present — **do NOT duplicate them.** But verify they also exist in any `WEIGHT_PER_FOOT` dict or `MATERIAL_TYPES` dict if those exist in this file or in `base.py`. If `WEIGHT_PER_FOOT` exists, add:
```python
"hss_4x4_0.25": 12.21,   # lb/ft
"hss_6x4_0.25": 15.62,   # lb/ft
```

Search the file for `WEIGHT_PER_FOOT` and `MATERIAL_TYPES` — if they exist, make sure HSS entries are present. If they don't exist in this file, check `base.py` for these dicts.

### CHANNEL PROFILE KEY MAPPING

In `backend/calculators/cantilever_gate.py`, inside `_post_process_ai_result()`, after the existing overhead beam dedup logic and BEFORE the "ENFORCE: Adjacent fence sections" section (around line 730), add a channel profile key normalizer:

```python
# ========================================================
# NORMALIZE: Channel profile keys from AI output
# ========================================================
# Claude may output generic channel keys. Map them to the
# correct pre-punched channel profile based on picket size.
resolved_picket = _resolve_picket_profile(fields, infill_type)
_CHANNEL_KEY_MAP = {
    "channel_1.5x0.125": {
        "sq_bar_0.5": "punched_channel_1.5x0.5_fits_0.5",
        "sq_bar_0.625": "punched_channel_1.5x0.5_fits_0.625",
        "sq_bar_0.75": "punched_channel_1.5x0.5_fits_0.75",
    },
    "channel_1x0.125": {
        "sq_bar_0.5": "punched_channel_1x0.5_fits_0.5",
    },
    "channel_2x0.125": {
        "sq_bar_0.75": "punched_channel_2x1_fits_0.75",
    },
}

for item in items:
    profile = item.get("profile", "")
    if profile in _CHANNEL_KEY_MAP:
        mapping = _CHANNEL_KEY_MAP[profile]
        correct_key = mapping.get(resolved_picket, list(mapping.values())[0])
        item["profile"] = correct_key
        # Update unit price to match correct profile
        new_price = lookup.get_price_per_foot(correct_key)
        if new_price > 0:
            length_ft = self.inches_to_feet(item.get("length_inches", 0))
            item["unit_price"] = round(length_ft * new_price, 2)
```

## Decomposition (execution order)

1. Delete `backend/gemini_client.py`
2. Delete `backend/ai_client.py`
3. Update `backend/claude_client.py` — model defaults + docstring
4. Update `backend/claude_reviewer.py` — model default
5. Update `backend/config.py` — remove Gemini vars, add Claude vars
6. Update `backend/calculators/ai_cut_list.py` — import + docstring + method docstring
7. Update `backend/routers/ai_quote.py` — import + rename functions + update error messages + rename endpoint
8. Update `backend/bid_parser.py` — import + rename method + update call site + update warning
9. Update `backend/labor_estimator.py` — import + rename method + update call sites + update docstrings
10. Update `backend/question_trees/engine.py` — import + rename functions + update call sites + update variable name
11. Add HSS entries to `WEIGHT_PER_FOOT` / `MATERIAL_TYPES` if those dicts exist
12. Add channel key mapping to `cantilever_gate.py` `_post_process_ai_result()`
13. Search ENTIRE `backend/` for any remaining references

## Evaluation Design

### MUST-PASS grep checks (all must return ZERO results):
```bash
grep -rn "gemini_client" backend/ --include="*.py" | grep -v __pycache__
grep -rn "from.*ai_client" backend/ --include="*.py" | grep -v __pycache__
grep -rn "import.*ai_client" backend/ --include="*.py" | grep -v __pycache__
grep -rn "GEMINI" backend/ --include="*.py" | grep -v __pycache__
grep -rn "_call_gemini" backend/ --include="*.py" | grep -v __pycache__
grep -rn "_gemini_vision" backend/ --include="*.py" | grep -v __pycache__
grep -rn "claude-sonnet-4-20250514" backend/ --include="*.py" | grep -v __pycache__
```

### MUST-PASS grep checks (all must return results):
```bash
grep -rn "from ..claude_client import" backend/calculators/ai_cut_list.py
grep -rn "from ..claude_client import" backend/routers/ai_quote.py
grep -rn "from ..claude_client import" backend/question_trees/engine.py
grep -rn "from .claude_client import" backend/bid_parser.py
grep -rn "from .claude_client import" backend/labor_estimator.py
grep -rn "claude-sonnet-4-6" backend/claude_client.py
grep -rn "claude-sonnet-4-6" backend/claude_reviewer.py
```

### Runtime verification:
```bash
cd backend && python -c "from calculators.ai_cut_list import AICutListGenerator; print('ai_cut_list OK')"
cd backend && python -c "from routers.ai_quote import router; print('ai_quote OK')"
cd backend && python -c "from bid_parser import BidParser; print('bid_parser OK')"
cd backend && python -c "from labor_estimator import LaborEstimator; print('labor_estimator OK')"
cd backend && python -c "from question_trees.engine import QuestionTreeEngine; print('engine OK')"
cd backend && python -c "from claude_reviewer import review_quote; print('reviewer OK')"
```

### File existence verification:
```bash
# These files must NOT exist:
test ! -f backend/gemini_client.py && echo "gemini_client.py deleted ✅" || echo "FAIL: gemini_client.py still exists"
test ! -f backend/ai_client.py && echo "ai_client.py deleted ✅" || echo "FAIL: ai_client.py still exists"
```
