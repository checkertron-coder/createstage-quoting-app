# PROMPT-35: Field Extraction Fix

## Problem Statement

When a customer describes a job in natural language (e.g., "20 foot cantilever gate, 6 feet tall, square tube frame, picket infill, paint black, full install"), the question tree should extract those values and skip asking questions the customer already answered. Currently it extracts only **2 out of 10+ fields** that are clearly stated in the description.

This means the customer gets asked 8+ questions they already answered. Burton has reported this bug 4 times today.

**Root causes (all three must be fixed):**

1. **Extraction prompt is too conservative.** The >90% confidence language + "do NOT guess" makes Opus skip fields that are clearly stated. If someone says "picket gate" that IS pickets — 100% confidence.

2. **No value normalization after extraction.** Opus might return `"Pickets"` but the branch key is `"Pickets (vertical bars)"`. The field registers as "answered" (dict key exists), but `get_next_questions` branch logic checks `answered_value in q["branches"]` — exact string match fails. Follow-up questions (picket_material, picket_spacing, picket_top) never appear. The calculator likely also breaks because it expects the exact option string.

3. **No logging.** When extraction fails, there's no way to diagnose what Opus returned, what got accepted, or what got dropped.

## Acceptance Criteria

### AC-1: Aggressive extraction with exact option matching
The extraction prompt must tell Opus to return the **exact option string** from the provided options list. Not a summary, not a synonym — the literal option text.

**Test:** Submit a cantilever gate with description "20 foot opening, 6 feet tall, 2x2 square tube 11 gauge frame, picket infill, paint black, full installation, 3 posts with new concrete." The extraction should return at minimum:
- `clear_width`: `"20"`
- `height`: `"6"`
- `frame_material`: `"Square tube (most common)"`
- `frame_gauge`: `"11 gauge (0.120\" - standard for gates)"`
- `frame_size`: `"2\" x 2\""`
- `infill_type`: `"Pickets (vertical bars)"`
- `finish`: `"Paint (in-house)"`
- `paint_color`: `"black"`
- `installation`: `"Full installation (gate + posts + concrete)"`
- `post_count`: `"3 posts (standard: 2 for track, 1 catch post)"`
- `post_concrete`: `"Yes - new footings needed"`

That's 11 fields from one sentence. Currently getting 2.

### AC-2: Post-extraction value normalization
After Opus returns extracted fields, normalize each choice-type value to the closest matching option from the question tree. This is a safety net — even if the prompt is perfect, the LLM might abbreviate.

**Algorithm:**
1. For each extracted field, look up the question definition
2. If it's a `choice` type with `options`, find the best match:
   - Exact match → use it
   - Case-insensitive match → use the canonical option
   - Substring match (extracted value is contained in an option, or vice versa) → use the canonical option
   - If no match found → **drop the field** (don't store a value that will break branching)
3. For `measurement` and `number` types, strip units and store just the numeric value
4. For `text` types, pass through as-is

**Test:** If Opus returns `{"infill_type": "Pickets"}`, normalization maps it to `"Pickets (vertical bars)"`. If Opus returns `{"frame_gauge": "11 gauge"}`, normalization maps it to `"11 gauge (0.120\" - standard for gates)"`.

### AC-3: Extraction logging
Add structured logging so failed extractions are diagnosable.

**Log these events:**
- `INFO` — "Field extraction: description length={n}, job_type={type}"
- `INFO` — "Field extraction: Opus returned {n} fields: {field_ids}"
- `INFO` — "Field extraction: normalized {field_id} from '{raw}' to '{canonical}'"
- `WARNING` — "Field extraction: dropped {field_id} — value '{raw}' matched no option in {options}"
- `WARNING` — "Field extraction: Opus returned 0 fields from description of length {n}"

## Constraint Architecture

### Files to modify:
1. **`backend/question_trees/engine.py`**
   - `_build_extraction_prompt()` (line ~308): Rewrite prompt to be assertive, require exact option strings
   - `extract_from_description()` (line ~58): Add normalization step after `_call_claude_extract()`, add logging
   - New function `_normalize_extracted_fields(extracted: dict, questions: list) -> dict`: The normalizer

2. **`backend/question_trees/engine.py`** — `_call_claude_extract()` (line ~344): Add logging for raw response

### Files NOT to modify:
- Question tree JSON files — the option strings are correct as-is
- `get_next_questions()` — the branching logic is correct, it just needs correct input values
- `claude_client.py` — the API call layer is fine
- Frontend — the question rendering is fine
- Any calculator files

### Critical constraints:
- Python 3.9 — no `str | None` union syntax
- The normalizer must handle all question types: `choice`, `multi_choice`, `measurement`, `number`, `text`, `photo`
- For `multi_choice` fields, normalize each selected value independently
- Don't break the existing `extract_from_photo` path — it merges into the same dict
- The extraction prompt must still tell Opus to return `{}` if the description is truly empty/vague — don't hallucinate fields that aren't mentioned

## Decomposition

### Step 1: Rewrite `_build_extraction_prompt()`
Replace the timid ">90% confidence" language with assertive extraction. Key changes:
- "Extract every field the customer mentioned or clearly implied"
- "For choice fields, return the EXACT option string from the options list below"
- "If the customer's words map to an option, use that option — don't require word-for-word match"
- Remove "do NOT guess from vague descriptions" — replace with "Don't extract fields the customer didn't mention at all"
- Keep unit normalization instructions (they work)
- Update examples to show exact option strings being returned

### Step 2: Write `_normalize_extracted_fields()`
```
def _normalize_extracted_fields(extracted, questions):
    """Normalize extracted values to match exact option strings from question tree."""
    normalized = {}
    for field_id, value in extracted.items():
        question = find question by field_id
        if not found: skip (might be 'description' or unknown)
        if choice type:
            match = find_best_option_match(value, question['options'])
            if match: normalized[field_id] = match
            else: log warning, skip field
        elif measurement/number:
            numeric = extract_numeric(value)
            if numeric: normalized[field_id] = numeric
        else:
            normalized[field_id] = value  # text, pass through
    return normalized
```

### Step 3: Wire normalization into `extract_from_description()`
After `_call_claude_extract(prompt)` returns, run `_normalize_extracted_fields()` on the result before returning.

### Step 4: Add logging
Import logger at top of engine.py. Add log lines per AC-3.

## Evaluation Design

### Test 1: Rich description → maximum extraction
Description: "20 foot cantilever gate, 6 feet tall, 2x2 square tube 11 gauge, picket infill with 4 inch spacing, paint it black, full install with new concrete footings, 3 posts, electric motor"

Expected: 12+ fields extracted. All choice values must exactly match option strings from `cantilever_gate.json`. Branch-dependent questions (picket_material, picket_spacing, motor_brand, paint_color, site_location) must appear as follow-up questions.

### Test 2: Minimal description → no hallucination
Description: "need a gate"

Expected: 0 fields extracted. All questions shown.

### Test 3: Partial description → partial extraction
Description: "cantilever gate, about 16 feet, with expanded metal"

Expected: `clear_width: "16"`, `infill_type: "Expanded metal"` extracted. `expanded_metal_gauge` follow-up question appears (branch activated). Height and other fields still asked.

### Test 4: Normalization safety net
If Opus returns `{"infill_type": "pickets", "frame_gauge": "11ga"}`:
- `infill_type` normalizes to `"Pickets (vertical bars)"`
- `frame_gauge` normalizes to `"11 gauge (0.120\" - standard for gates)"` (substring match on "11")
- Branch fires correctly → picket sub-questions appear

### Test 5: Verify no regression on branching
After extraction with `infill_type: "Pickets (vertical bars)"`, the questions `picket_material`, `picket_top`, `picket_spacing` must appear in `get_next_questions()`. They must NOT appear if `infill_type: "Expanded metal"`.
