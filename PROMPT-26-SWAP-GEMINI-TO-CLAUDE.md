# PROMPT 26 — Swap Gemini → Claude API for All AI Generation

## Problem Statement

Gemini cannot reliably follow fabrication constraints. After 8 prompts of
fixes, it STILL:

- Reverts to "grind welds" language (fixed in P22, regressed in P24, P25)
- Picks random materials despite hard constraints in the prompt
- Ignores gate length formulas
- Generates wildly inconsistent output run-to-run
- Needs 500+ lines of banned term replacements and post-processing validators

We have $50 in Anthropic API credit and the key is already in Railway.
**Replace ALL Gemini generation calls with Claude API calls.**

The calculator guardrails from P24 stay as a safety net, but Claude should
get things right without needing them.

## Acceptance Criteria

1. `ANTHROPIC_API_KEY` is the ONLY required AI key. `GEMINI_API_KEY` becomes
   optional (kept for vision/extraction fallback if desired).
2. Cut list generation uses Claude (Sonnet by default, configurable).
3. Build instructions generation uses Claude.
4. Field extraction from descriptions uses Claude.
5. All existing prompts, constraints, and domain knowledge flow to Claude.
6. Same JSON output format — no changes to downstream parsers.
7. The "grind welds" regression is GONE.
8. Same inputs produce consistent outputs across runs.

## Constraint Architecture

**DO NOT rewrite the AI prompt system.** The prompts in `ai_cut_list.py` are
good — they contain hard-earned domain knowledge. Just swap the transport layer
from Gemini to Claude.

**Keep Gemini as optional fallback.** If `ANTHROPIC_API_KEY` is set, use Claude.
If not, fall back to Gemini. This way existing installs without an Anthropic key
still work.

## Decomposition

### Part 1: Create `backend/claude_client.py`
**New file — mirrors `gemini_client.py` interface exactly.**

```python
"""
Centralized Claude (Anthropic) API client.

Drop-in replacement for gemini_client.py. All AI generation calls can use
this module instead. Provides the same interface: call_fast, call_deep,
is_configured.

Model resolution:
  FAST:  CLAUDE_FAST_MODEL -> "claude-sonnet-4-20250514"
  DEEP:  CLAUDE_DEEP_MODEL -> "claude-sonnet-4-20250514"

Set ANTHROPIC_API_KEY in environment to enable.
"""

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_FAST = "claude-sonnet-4-20250514"
_DEFAULT_DEEP = "claude-sonnet-4-20250514"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def _resolve_model(tier: str) -> str:
    if tier == "fast":
        return os.getenv("CLAUDE_FAST_MODEL", _DEFAULT_FAST)
    return os.getenv("CLAUDE_DEEP_MODEL", _DEFAULT_DEEP)


def get_model_name(tier: str = "deep") -> str:
    return _resolve_model(tier)


def is_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def call_fast(prompt: str, temperature: float = 0.1, timeout: int = 60,
              json_mode: bool = True) -> Optional[str]:
    return _call_claude(prompt, tier="fast", temperature=temperature,
                        timeout=timeout, json_mode=json_mode)


def call_deep(prompt: str, temperature: float = 0.1, timeout: int = 120,
              json_mode: bool = True) -> Optional[str]:
    return _call_claude(prompt, tier="deep", temperature=temperature,
                        timeout=timeout, json_mode=json_mode)


def call_vision(prompt: str, image_b64: str, mime_type: str,
                temperature: float = 0.1, timeout: int = 60,
                json_mode: bool = True) -> Optional[str]:
    """Call Claude Vision with an image."""
    return _call_claude(prompt, tier="fast", temperature=temperature,
                        timeout=timeout, json_mode=json_mode,
                        image_b64=image_b64, image_mime=mime_type)


def _call_claude(prompt: str, tier: str = "deep", temperature: float = 0.1,
                 timeout: int = 120, json_mode: bool = True,
                 image_b64: str = None, image_mime: str = None) -> Optional[str]:
    """Execute a Claude API call via httpx."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.debug("No ANTHROPIC_API_KEY — skipping Claude call")
        return None

    model = _resolve_model(tier)

    # Build message content
    content = []
    if image_b64 and image_mime:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_mime,
                "data": image_b64,
            }
        })
    content.append({"type": "text", "text": prompt})

    # System prompt for JSON mode
    system = None
    if json_mode:
        system = (
            "You are a fabrication engineering AI. Respond ONLY with valid JSON. "
            "No markdown, no code blocks, no explanation — just the JSON object or array."
        )

    payload = {
        "model": model,
        "max_tokens": 16384,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        payload["system"] = system

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    start = time.time()

    try:
        import httpx
        with httpx.Client(timeout=timeout) as client:
            response = client.post(ANTHROPIC_API_URL, headers=headers,
                                    json=payload)
            response.raise_for_status()
            result = response.json()
            text = result["content"][0]["text"]
            elapsed = time.time() - start
            logger.info("claude %s [%s] %.1fs tokens_in=%d tokens_out=%d",
                        tier, model, elapsed,
                        result.get("usage", {}).get("input_tokens", 0),
                        result.get("usage", {}).get("output_tokens", 0))
            return text

    except httpx.TimeoutException:
        elapsed = time.time() - start
        logger.warning("Claude timeout after %.1fs (%s)", elapsed, model)
        return None
    except httpx.HTTPStatusError as e:
        logger.warning("Claude HTTP %d: %s", e.response.status_code,
                        e.response.text[:200])
        return None
    except ImportError:
        # httpx not installed — fall back to urllib
        return _call_claude_urllib(api_key, model, payload, headers, timeout)
    except Exception as e:
        logger.warning("Claude call failed: %s", e)
        return None


def _call_claude_urllib(api_key, model, payload, headers, timeout):
    """Fallback using urllib if httpx is not installed."""
    import urllib.request
    import urllib.error

    start = time.time()
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ANTHROPIC_API_URL, data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read())
            text = result["content"][0]["text"]
            elapsed = time.time() - start
            logger.info("claude(urllib) %s [%s] %.1fs", "deep", model, elapsed)
            return text
    except Exception as e:
        logger.warning("Claude urllib call failed: %s", e)
        return None
```

### Part 2: Create `backend/ai_client.py` — Unified Router
**New file — routes to Claude or Gemini based on config.**

```python
"""
Unified AI client — routes to Claude (preferred) or Gemini (fallback).

Import this instead of gemini_client or claude_client directly.
Precedence: ANTHROPIC_API_KEY → Claude, else GEMINI_API_KEY → Gemini.
"""

import logging

logger = logging.getLogger(__name__)

_provider = None  # cached after first call


def _get_provider():
    global _provider
    if _provider is not None:
        return _provider

    from . import claude_client, gemini_client

    if claude_client.is_configured():
        _provider = "claude"
        logger.info("AI provider: Claude (ANTHROPIC_API_KEY configured)")
        return _provider
    elif gemini_client.is_configured():
        _provider = "gemini"
        logger.info("AI provider: Gemini (GEMINI_API_KEY configured, no ANTHROPIC_API_KEY)")
        return _provider
    else:
        _provider = "none"
        logger.warning("No AI provider configured (no ANTHROPIC_API_KEY or GEMINI_API_KEY)")
        return _provider


def is_configured():
    return _get_provider() != "none"


def get_provider():
    return _get_provider()


def get_model_name(tier="deep"):
    provider = _get_provider()
    if provider == "claude":
        from . import claude_client
        return claude_client.get_model_name(tier)
    elif provider == "gemini":
        from . import gemini_client
        return gemini_client.get_model_name(tier)
    return "none"


def call_fast(prompt, temperature=0.1, timeout=60, json_mode=True):
    provider = _get_provider()
    if provider == "claude":
        from . import claude_client
        return claude_client.call_fast(prompt, temperature=temperature,
                                        timeout=timeout, json_mode=json_mode)
    elif provider == "gemini":
        from . import gemini_client
        return gemini_client.call_fast(prompt, temperature=temperature,
                                        timeout=timeout, json_mode=json_mode)
    return None


def call_deep(prompt, temperature=0.1, timeout=120, json_mode=True):
    provider = _get_provider()
    if provider == "claude":
        from . import claude_client
        return claude_client.call_deep(prompt, temperature=temperature,
                                        timeout=timeout, json_mode=json_mode)
    elif provider == "gemini":
        from . import gemini_client
        return gemini_client.call_deep(prompt, temperature=temperature,
                                        timeout=timeout, json_mode=json_mode)
    return None


def call_vision(prompt, image_b64, mime_type, temperature=0.1, timeout=60,
                json_mode=True):
    provider = _get_provider()
    if provider == "claude":
        from . import claude_client
        return claude_client.call_vision(prompt, image_b64, mime_type,
                                          temperature=temperature,
                                          timeout=timeout, json_mode=json_mode)
    elif provider == "gemini":
        from . import gemini_client
        return gemini_client.call_vision(prompt, image_b64, mime_type,
                                          temperature=temperature,
                                          timeout=timeout, json_mode=json_mode)
    return None
```

### Part 3: Update ALL Import References
**Every file that imports from `gemini_client` must switch to `ai_client`.**

Find all imports:
```bash
grep -rn "from.*gemini_client import\|import.*gemini_client" backend/ --include="*.py"
```

Replace each occurrence:

**`backend/calculators/ai_cut_list.py`** (line 17):
```python
# OLD:
from ..gemini_client import call_fast, is_configured

# NEW:
from ..ai_client import call_fast, is_configured
```

**`backend/question_trees/engine.py`** (wherever it imports gemini):
```python
# OLD:
from ..gemini_client import call_fast, call_vision, is_configured

# NEW:
from ..ai_client import call_fast, call_vision, is_configured
```

**Any other files** — search and replace all `gemini_client` imports with
`ai_client`. The interface is identical, so no other code changes needed.

**DO NOT delete `gemini_client.py`** — it's still used as a fallback by
`ai_client.py`.

### Part 4: Update `_call_gemini` Method Name
**File: `backend/calculators/ai_cut_list.py`**

Rename the internal method for clarity (optional but good hygiene):

```python
# OLD (line ~917):
def _call_gemini(self, prompt: str) -> str:
    """Call Gemini API. Raises RuntimeError on failure."""
    text = call_fast(prompt, timeout=180)

# NEW:
def _call_ai(self, prompt: str) -> str:
    """Call AI provider (Claude or Gemini). Raises RuntimeError on failure."""
    text = call_fast(prompt, timeout=180)
    if text is None:
        raise RuntimeError("AI provider returned no response")
    return text
```

Then update all internal references from `self._call_gemini(...)` to
`self._call_ai(...)`:

```bash
# In ai_cut_list.py, find:
self._call_gemini(prompt)
# Replace ALL occurrences with:
self._call_ai(prompt)
```

### Part 5: Update Logging and Model Name References
**File: `backend/calculators/ai_cut_list.py`**

Update the model name reference in the assumptions:

Find:
```python
"Labor hours estimated by AI (gemini-3.1-pro-preview) with domain guidance."
```

Replace with:
```python
from ..ai_client import get_model_name, get_provider
# ...
"Labor hours estimated by AI (%s via %s) with domain guidance."
% (get_model_name("fast"), get_provider())
```

### Part 6: Add `httpx` to Requirements
**File: `requirements.txt`**

Add `httpx` if not already present:
```
httpx>=0.27.0
```

This is used by `claude_client.py` for API calls. Falls back to `urllib`
if not available, but `httpx` is cleaner and handles timeouts better.

### Part 7: Update Railway Environment
**Already done by Burton.** Just verify:
- `ANTHROPIC_API_KEY` is set in Railway variables
- `GEMINI_API_KEY` can remain (used as fallback if Anthropic key is removed)

### Part 8: Also Fix the P25 Bugs That Didn't Land

While we're here, fix these from P25 that clearly didn't take effect:

**HSS profiles in material catalog** (`backend/calculators/material_lookup.py`):

Verify these exist. If not, add them:
```python
# In PRICE_PER_FOOT:
"hss_4x4_0.25": 8.25,
"hss_6x4_0.25": 12.00,

# In WEIGHT_PER_FOOT (or equivalent):
"hss_4x4_0.25": 12.21,
"hss_6x4_0.25": 15.62,

# In MATERIAL_TYPES (or equivalent profile→type mapping):
"hss_4x4_0.25": "hss_structural_tube",
"hss_6x4_0.25": "hss_structural_tube",
```

**Overhead beam duplication fix** (`backend/calculators/cantilever_gate.py`):

The post-processor adds an overhead beam even when Gemini/Claude already
included one. The `has_overhead` check must search BOTH `items` AND
`cut_list` for any overhead beam, and if found, validate its profile
rather than adding a duplicate:

```python
if is_top_hung:
    # Determine correct beam profile
    if total_weight < 800:
        correct_profile = "hss_4x4_0.25"
        correct_desc = "HSS 4×4×1/4\""
    else:
        correct_profile = "hss_6x4_0.25"
        correct_desc = "HSS 6×4×1/4\""

    # Find ALL existing overhead beams (items + cut_list)
    overhead_item_idxs = []
    for i, item in enumerate(items):
        desc_lower = item.get("description", "").lower()
        if "overhead" in desc_lower or "support beam" in desc_lower:
            overhead_item_idxs.append(i)

    overhead_cut_idxs = []
    for i, cut in enumerate(cut_list):
        desc_lower = (str(cut.get("description", "")) + " " +
                      str(cut.get("notes", ""))).lower()
        if "overhead" in desc_lower or "support beam" in desc_lower:
            overhead_cut_idxs.append(i)

    if overhead_item_idxs:
        # Keep only the FIRST, remove duplicates
        for idx in sorted(overhead_item_idxs[1:], reverse=True):
            items.pop(idx)
        # Fix profile on the remaining one
        first = items[overhead_item_idxs[0]]
        if first.get("profile") != correct_profile:
            beam_length_in = total_gate_length_in + 24
            beam_length_ft = self.inches_to_feet(beam_length_in)
            beam_price_ft = lookup.get_price_per_foot(correct_profile)
            first["profile"] = correct_profile
            first["unit_price"] = round(beam_length_ft * beam_price_ft, 2)
            first["description"] = (
                "Overhead support beam — %s (%.1f ft, qty 1)"
                % (correct_desc, beam_length_ft))
    else:
        # No overhead beam found — add one
        # (existing add code, using correct_profile)
        pass

    # Same dedup for cut_list
    if overhead_cut_idxs:
        for idx in sorted(overhead_cut_idxs[1:], reverse=True):
            cut_list.pop(idx)
        cut_list[overhead_cut_idxs[0]]["profile"] = correct_profile
        cut_list[overhead_cut_idxs[0]]["quantity"] = 1
```

**Post description format fix** — "Gate posts - 4 × 3" should read
"Gate posts — 3 × 4×4 (13.7 ft each)":

In `_post_process_ai_result`, the gate post description format:
```python
# OLD:
description="Gate posts — %s × %d (%.1f ft each, ...)"
            % (post_size, post_count, ...)

# NEW:
description="Gate posts — %d × %s (%s each, %.0f\" embed for Chicago frost line)"
            % (post_count, post_size,
               "%.1f ft" % self.inches_to_feet(post_total_length_in),
               post_concrete_depth_in)
```

## Evaluation Design

### Verification Steps

1. **Provider detection:**
   ```bash
   # In Railway logs after deploy, should see:
   # "AI provider: Claude (ANTHROPIC_API_KEY configured)"
   # NOT "AI provider: Gemini"
   ```

2. **Cut list uses Claude:**
   ```bash
   # In Railway logs during quote generation:
   # "claude fast [claude-sonnet-4-20250514] 12.3s tokens_in=4521 tokens_out=2100"
   # NOT "gemini fast [gemini-2.5-flash] ..."
   ```

3. **No grinding regression:**
   ```bash
   # In the generated PDF, Step 7 (or equivalent grind step):
   # MUST say "clean welds" or "deburr" or "remove spatter"
   # MUST NOT say "grind welds"
   # MUST NOT say "grind welds smooth" or "grind flush"
   ```

4. **Consistent output:**
   ```bash
   # Run the same cantilever gate quote 3 times
   # All 3 must have:
   #   - Same picket profile (sq_bar_0.625)
   #   - Same gate length (~18')
   #   - Same post count and length
   #   - No "grind welds" language
   ```

5. **No overhead beam duplication:**
   ```bash
   # Only ONE overhead beam in materials list
   # Profile = hss_4x4_0.25 for gates under 800 lbs
   ```

6. **HSS warnings gone:**
   ```bash
   # No "[WARNING] Unrecognized profile 'hss_4x4_0.25'" in quote
   # No "[WARNING] Unrecognized profile 'hss_6x4_0.25'" in quote
   ```

## File Change Summary

| File | Changes |
|------|---------|
| `backend/claude_client.py` | **NEW** — Claude API client (mirrors gemini_client interface) |
| `backend/ai_client.py` | **NEW** — Unified AI router (Claude preferred, Gemini fallback) |
| `backend/calculators/ai_cut_list.py` | Change import from `gemini_client` to `ai_client`; rename `_call_gemini` → `_call_ai`; update model name in assumptions |
| `backend/question_trees/engine.py` | Change import from `gemini_client` to `ai_client` |
| `backend/calculators/material_lookup.py` | Add hss_4x4_0.25 and hss_6x4_0.25 to all lookup dicts |
| `backend/calculators/cantilever_gate.py` | Fix overhead beam duplication; fix post description format |
| `requirements.txt` | Add `httpx>=0.27.0` |
| **Any other file importing gemini_client** | Change to `ai_client` |

## What NOT to Change

- **Do NOT modify the prompt text** in `ai_cut_list.py` — it works, just
  Gemini can't follow it. Claude will.
- **Do NOT remove `gemini_client.py`** — it's the fallback.
- **Do NOT remove the post-processing** in `cantilever_gate.py` — keep it
  as a safety net even with Claude. Belt and suspenders.
- **Do NOT remove `BANNED_TERM_REPLACEMENTS`** — keep them. If Claude ever
  slips, they'll catch it. But Claude probably won't need them.
