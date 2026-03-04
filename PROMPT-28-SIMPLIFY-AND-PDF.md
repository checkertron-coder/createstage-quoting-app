# PROMPT 28 — Simplify Post-Processor + Fix Duplicates + PDF Upload + Surface Prep Solvent

## Problem Statement

CS-2026-0036 (the first quote on Claude Sonnet 4.6 after Prompt 27) shows that **Claude is generating good output but the post-processor is fighting it**. The result is duplicate posts (6 instead of 3), duplicate overhead beams (2 instead of 1), conflicting picket counts, and a fab sequence that hallucinates 27' gate panels because it doesn't receive calculator-enforced dimensions.

Specific problems in CS-2026-0036:
1. **Duplicate gate posts**: Claude generated 3 posts as `pipe_4_sch40`. Post-processor checked for `sq_tube_4x4_11ga`, didn't find it, added 3 MORE. Result: 6 posts, 2 different materials.
2. **Duplicate overhead beam**: Claude generated `hss_4x4_0.25` (correct). Post-processor searched for "overhead" or "support beam" in the description, didn't find it in Claude's generic line (`hss_4x4_0.25 - 23.1 ft`), added `hss_6x4_0.25`. Result: 2 beams.
3. **Fab sequence says 324" (27') gate panel**: The fab sequence prompt receives the raw AI cut list, not the calculator-enforced 216" (18'). Claude recalculated gate length from the job description and got it wrong.
4. **Three different picket counts per side**: Claude's cut list says 44/38, post-processor's `_generate_fence_sections` says 46/40, `apply_waste()` bumps to 49/42. Fabricator doesn't know which number to use.
5. **No surface prep solvent in consumables**: Burton wipes down with surface prep solvent before painting — it's a real consumable that needs to be on the quote.
6. **Grind/clean step is over-specified**: For outdoor painted steel, it's just "clean up spatter and sharp edges before surface prep" — 30 minutes, done right before the wipe-down. Not a multi-hour operation with progressive grits.
7. **No way to upload PDFs in the frontend**: Backend bid parser exists (`POST /api/bid/upload`) but no UI. Burton needs to drop in architectural plans and bid documents.

**Root cause**: The post-processor was designed when Gemini was unreliable. Claude Sonnet 4.6 is significantly better. The post-processor needs to become a lightweight safety net, not a parallel calculation engine that contradicts the AI.

## Acceptance Criteria

1. **Zero duplicate items** on the same quote — no material type should appear from both AI and post-processor
2. **Fab sequence uses calculator-enforced dimensions** — gate panel length, post length, picket count passed explicitly
3. **One picket count per side** — post-processor defers to Claude's count if Claude generated fence items, only adds if Claude omitted them entirely
4. **Surface prep solvent** appears in consumables as a line item
5. **Grind/clean for outdoor painted work** described as quick cleanup (30-60 min for this scope), not multi-hour progressive gritting
6. **PDF upload UI** in the frontend — user can drag-drop or click-to-upload a PDF, see extracted items
7. **Gate posts use consistent material** — if user selected "4×4 square tube," posts must be `sq_tube_4x4_11ga`, not `pipe_4_sch40`
8. All existing quote generation still works — no regressions

## Constraint Architecture

### PART 1: Simplify `_post_process_ai_result()` in `backend/calculators/cantilever_gate.py`

The current method is ~350 lines starting at line 482. It needs to be restructured around this principle: **check if Claude already handled it. If yes, validate but don't duplicate. If Claude completely omitted it, add it.**

#### 1A. Fix duplicate gate posts (line ~540)

**Current logic** (broken):
```python
has_gate_posts = any(
    "post" in item.get("description", "").lower()
    and "fence" not in item.get("description", "").lower()
    and item.get("profile") == post_profile_key  # <-- THIS IS THE BUG
    for item in items
)
```

The check matches on `profile == post_profile_key` (which is `sq_tube_4x4_11ga`). But Claude used `pipe_4_sch40` for gate posts. Profile doesn't match → check returns False → post-processor adds 3 more posts.

**Fix**: Check for ANY item with "post" in description that ISN'T a fence post, regardless of profile:
```python
has_gate_posts = any(
    "post" in item.get("description", "").lower()
    and "fence" not in item.get("description", "").lower()
    for item in items
)
```

If gate posts exist but use the wrong profile, **correct the profile in-place** instead of adding duplicates:
```python
if has_gate_posts:
    # Fix profile if Claude used wrong material for gate posts
    for item in items:
        desc_lower = item.get("description", "").lower()
        if "post" in desc_lower and "fence" not in desc_lower:
            if item.get("profile") != post_profile_key:
                old_profile = item["profile"]
                item["profile"] = post_profile_key
                # Recalculate price with correct profile
                length_ft = self.inches_to_feet(item.get("length_inches", 164))
                item["unit_price"] = round(length_ft * post_price_ft, 2)
                assumptions.append(
                    "Gate post profile corrected: %s → %s (per user selection)."
                    % (old_profile, post_profile_key))
```

#### 1B. Fix duplicate overhead beam (line ~620)

**Current logic** (broken):
```python
overhead_item_idxs = []
for idx, item in enumerate(items):
    desc_lower = item.get("description", "").lower()
    if "overhead" in desc_lower or "support beam" in desc_lower:
        overhead_item_idxs.append(idx)
```

Claude's line is `hss_4x4_0.25 - 23.1 ft` — no "overhead" or "support beam" keywords. The check misses it.

**Fix**: Search for ANY `hss_` profile item in addition to keyword matching:
```python
overhead_item_idxs = []
for idx, item in enumerate(items):
    desc_lower = item.get("description", "").lower()
    profile = item.get("profile", "")
    is_overhead_by_keyword = "overhead" in desc_lower or "support beam" in desc_lower
    is_overhead_by_profile = profile.startswith("hss_") and item.get("quantity", 1) <= 2
    if is_overhead_by_keyword or is_overhead_by_profile:
        overhead_item_idxs.append(idx)
```

Then the existing dedup logic (keep first, remove rest, fix profile if needed) handles the rest correctly.

#### 1C. Fix fence item duplication (line ~730)

**Current logic**: The `has_fence_posts` check looks for items with both "fence" and "post" in the description. If Claude generated fence posts with slightly different wording, the check might miss them.

**Fix**: Also check by profile + quantity pattern. If Claude generated items with `sq_tube_4x4_11ga` at 164" that mention "Side 1" or "Side 2" or "fence", those are fence posts:
```python
has_fence_posts = any(
    ("fence" in item.get("description", "").lower()
     and "post" in item.get("description", "").lower())
    or ("side" in item.get("description", "").lower()
        and item.get("profile", "") == post_profile_key
        and abs(item.get("length_inches", 0) - post_total_length_in) < 5)
    for item in items
)
```

#### 1D. Fence picket count — defer to Claude if Claude generated them

**Current logic**: Post-processor always runs `_generate_fence_sections()` which calculates its own picket count. If Claude also generated fence pickets, you get two sets of numbers.

**Fix**: Before calling `_generate_fence_sections()`, check if Claude already generated fence items. If Claude included fence posts, rails, AND pickets for a given side, skip `_generate_fence_sections()` for that side entirely:
```python
# Check what Claude already generated for fence
claude_has_fence_side1 = any(
    "side 1" in item.get("description", "").lower()
    and ("picket" in item.get("description", "").lower()
         or "rail" in item.get("description", "").lower())
    for item in items
)
claude_has_fence_side2 = any(
    "side 2" in item.get("description", "").lower()
    and ("picket" in item.get("description", "").lower()
         or "rail" in item.get("description", "").lower())
    for item in items
)

# Only generate fence sections that Claude completely omitted
if not claude_has_fence_side1 and not claude_has_fence_side2:
    # Claude omitted fence entirely — generate both sides
    fence_result = self._generate_fence_sections(...)
    items.extend(fence_result["items"])
    ...
elif not claude_has_fence_side1:
    # Claude only did side 2 — generate side 1 only
    # (modify _generate_fence_sections to accept a sides filter, or handle inline)
    ...
elif not claude_has_fence_side2:
    # Claude only did side 1 — generate side 2 only
    ...
else:
    # Claude handled both sides — just validate picket profile matches
    resolved_picket = _resolve_picket_profile(fields, infill_type)
    for item in items:
        if "picket" in item.get("description", "").lower() and "fence" in item.get("description", "").lower():
            if item.get("profile") != resolved_picket:
                item["profile"] = resolved_picket
                assumptions.append("Fence picket profile corrected to %s." % resolved_picket)
```

The same check applies to fence mid-rails — skip adding them if Claude already included them.

### PART 2: Pass enforced dimensions to fab sequence prompt

In `backend/calculators/ai_cut_list.py`, method `_build_instructions_prompt()` starting at line 747.

**Add a new parameter** `enforced_dimensions` (dict) and inject it at the top of the prompt:

In `backend/routers/quote_session.py` around line 479 where `generate_build_instructions` is called, pass the enforced dimensions:
```python
# Build enforced dimensions from calculator output
enforced_dims = {}
fields_for_instructions = {k: v for k, v in current_params.items() if not k.startswith("_")}

# Extract calculator-enforced values if available
job_type = session.job_type
if job_type == "cantilever_gate":
    clear_width = float(fields_for_instructions.get("clear_width", "10").split("'")[0].split("ft")[0].strip() or 10)
    enforced_dims = {
        "gate_panel_length_inches": clear_width * 12 * 1.5,
        "gate_panel_length_ft": clear_width * 1.5,
        "post_length_inches": 164,  # standard for 10' gate + 42" embed
        "post_embed_inches": 42,
        "gate_height_inches": float(fields_for_instructions.get("height", "10").split("'")[0].split("ft")[0].strip() or 10) * 12,
    }

build_instructions = ai_gen.generate_build_instructions(
    session.job_type,
    fields_for_instructions,
    material_list.get("items", []),
    enforced_dimensions=enforced_dims,  # NEW PARAMETER
)
```

In `_build_instructions_prompt()`, add the enforced dimensions block right before the RULES section:
```python
# Add enforced dimensions block
enforced_block = ""
if enforced_dimensions:
    lines = ["ENFORCED DIMENSIONS (use these EXACT values — do NOT recalculate from job description):"]
    for key, val in enforced_dimensions.items():
        label = key.replace("_", " ").title()
        if "inches" in key:
            lines.append("  - %s: %.0f\" (%.1f ft)" % (label, val, val / 12.0))
        elif "ft" in key:
            lines.append("  - %s: %.1f ft (%.0f\")" % (label, val, val * 12.0))
        else:
            lines.append("  - %s: %s" % (label, val))
    enforced_block = "\n".join(lines) + "\n\nCRITICAL: The gate panel length is %.0f\" (%.1f ft). Do NOT use any other number for gate rail lengths.\n" % (
        enforced_dimensions.get("gate_panel_length_inches", 0),
        enforced_dimensions.get("gate_panel_length_ft", 0),
    )
```

Update the method signature:
```python
def _build_instructions_prompt(self, job_type: str, fields: dict,
                                cut_list: List[Dict],
                                enforced_dimensions: dict = None) -> str:
```

And update `generate_build_instructions` to accept and pass through the parameter:
```python
def generate_build_instructions(self, job_type: str, fields: dict,
                                 cut_list: List[Dict],
                                 enforced_dimensions: dict = None) -> Optional[List[Dict]]:
```

### PART 3: Fix grind/clean for outdoor painted work

In `backend/calculators/ai_cut_list.py`, the fab sequence prompt Rule 14 (around line 900) already says "DO NOT grind welds smooth or flat" but the AI is still adding progressive gritting in Step 10.

**Strengthen Rule 14:**

**Current:**
```
14. GRINDING FOR OUTDOOR WORK: Gates, fences, railings with paint/powder finish — clean spatter, remove sharp edges, knock down high spots. DO NOT grind welds smooth or flat. Save smooth grinding for indoor/furniture/decorative work.
```

**Change to:**
```
14. GRINDING FOR OUTDOOR PAINTED WORK: For gates, fences, and railings that will be painted or powder coated: The ONLY grind work is a quick pass to clean weld spatter, remove sharp edges, and knock down any obvious high spots. This is done right before the surface prep wipe-down. Total time for this step on a typical gate+fence project: 30-60 minutes. Do NOT use progressive grits (no 80-grit, no 120-grit). Do NOT grind welds smooth or flat. Do NOT include "finish prep" as a separate step — it's part of the pre-paint cleanup. A 36-grit flap disc is the only disc needed. Save smooth/progressive grinding for indoor furniture, decorative work, or clear-coated finishes.
```

### PART 4: Add surface prep solvent to consumables

In `backend/knowledge/consumables.py`, add a new consumable entry:
```python
"surface_prep_solvent": {
    "name": "Surface Prep Solvent (1 quart)",
    "type": "solvent",
    "unit": "quart",
    "price": 12.00,
    "use_for": ["pre_paint_wipedown", "degreasing", "surface_prep"],
    "notes": "Wipe-down solvent applied with clean rags before priming. "
             "Removes oils, dust, and contaminants. One quart covers ~400 sq ft.",
},
```

Then in whatever consumable calculation function generates the consumables list for a quote, include surface prep solvent when the finish type is paint or powder coat. Search for where primer and paint gallons are calculated — that's where surface prep solvent should be added alongside them.

Search for the consumable generation:
```bash
grep -rn "primer\|paint.*gallon\|consumable.*append\|consumable.*list" backend/calculators/ --include="*.py" | head -20
```

Find the function that builds the consumables list and add:
```python
# Surface prep solvent — 1 quart per ~400 sq ft
if finish_type in ("paint", "powder_coat"):
    solvent_qty = max(1, math.ceil(total_sq_ft / 400.0))
    consumables.append({
        "description": "Surface prep solvent - %d quart(s)" % solvent_qty,
        "quantity": solvent_qty,
        "unit_price": 12.00,
        "line_total": round(solvent_qty * 12.00, 2),
    })
```

### PART 5: PDF Upload Frontend UI

Add a new page/section to the frontend that allows PDF upload. This connects to the existing `POST /api/bid/upload` endpoint.

#### 5A. Add a "Plans & Bids" button to the main navigation

In `frontend/index.html` (or wherever the nav lives), add a nav item:
```html
<button onclick="BidUpload.show()" class="nav-btn">📄 Plans & Bids</button>
```

#### 5B. Create `frontend/js/bid-upload.js`

New file with a `BidUpload` class/module:

```javascript
const BidUpload = {
    show() {
        // Show the upload UI — either a modal or replace main content
        const container = document.getElementById('main-content') || document.body;
        container.innerHTML = `
            <div class="bid-upload-page">
                <h2>📄 Upload Plans & Bid Documents</h2>
                <p>Drop a PDF here or click to browse. We'll extract the metal fab scope.</p>
                <div class="upload-dropzone" id="bid-dropzone"
                     ondragover="event.preventDefault(); this.classList.add('drag-over')"
                     ondragleave="this.classList.remove('drag-over')"
                     ondrop="BidUpload.handleDrop(event)">
                    <input type="file" id="bid-file-input" accept=".pdf,application/pdf"
                           hidden onchange="BidUpload.handleFile(this.files[0])">
                    <button class="btn btn-primary" onclick="document.getElementById('bid-file-input').click()">
                        Choose PDF
                    </button>
                    <p class="hint">or drag and drop</p>
                </div>
                <div id="bid-results" style="display: none;">
                    <h3>Extracted Items</h3>
                    <div id="bid-items-list"></div>
                    <div id="bid-warnings"></div>
                </div>
                <div id="bid-loading" style="display: none;">
                    <p>Extracting scope from PDF...</p>
                </div>
            </div>
        `;
    },

    handleDrop(event) {
        event.preventDefault();
        event.target.classList.remove('drag-over');
        const file = event.dataTransfer.files[0];
        if (file && file.type === 'application/pdf') {
            this.handleFile(file);
        }
    },

    async handleFile(file) {
        if (!file) return;

        document.getElementById('bid-loading').style.display = 'block';
        document.getElementById('bid-results').style.display = 'none';

        const formData = new FormData();
        formData.append('file', file);

        try {
            const resp = await fetch(`${API.base}/bid/upload`, {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + API._accessToken },
                body: formData,
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Upload failed');
            }

            const result = await resp.json();
            this.showResults(result);
        } catch (err) {
            alert('Upload failed: ' + err.message);
        } finally {
            document.getElementById('bid-loading').style.display = 'none';
        }
    },

    showResults(result) {
        const resultsDiv = document.getElementById('bid-results');
        const itemsList = document.getElementById('bid-items-list');
        const warningsDiv = document.getElementById('bid-warnings');

        resultsDiv.style.display = 'block';

        // Show warnings
        if (result.warnings && result.warnings.length > 0) {
            warningsDiv.innerHTML = result.warnings.map(w =>
                `<div class="warning-banner">⚠️ ${w}</div>`
            ).join('');
        }

        // Show extracted items
        if (result.items && result.items.length > 0) {
            itemsList.innerHTML = result.items.map((item, idx) => `
                <div class="bid-item" data-index="${idx}">
                    <div class="bid-item-header">
                        <strong>${item.description || 'Item ' + (idx + 1)}</strong>
                        <span class="badge">${item.job_type || 'unknown'}</span>
                        <span class="confidence">${Math.round((item.confidence || 0) * 100)}% confidence</span>
                    </div>
                    ${item.quantity ? '<p>Qty: ' + item.quantity + '</p>' : ''}
                    ${item.dimensions ? '<p>Dimensions: ' + JSON.stringify(item.dimensions) + '</p>' : ''}
                    <button class="btn btn-sm btn-primary"
                            onclick="BidUpload.createQuote(${idx})">
                        Create Quote →
                    </button>
                </div>
            `).join('');
        } else {
            itemsList.innerHTML = '<p>No metal fabrication items found in this document.</p>';
        }

        // Store for creating quotes
        this._lastResult = result;
    },

    async createQuote(itemIndex) {
        // Future: call POST /api/bid/{bid_id}/quote-items to create a quote session
        // For now, show the pre-populated fields
        const item = this._lastResult.items[itemIndex];
        alert('Quote creation from bid items coming soon.\n\nJob type: ' + item.job_type +
              '\nDescription: ' + item.description);
    }
};
```

#### 5C. Add the script tag to `frontend/index.html`

```html
<script src="js/bid-upload.js"></script>
```

#### 5D. Add basic CSS for the upload UI

In the existing stylesheet (find it with `ls frontend/css/` or check `index.html` for `<link rel="stylesheet">`):

```css
.bid-upload-page { max-width: 800px; margin: 2rem auto; padding: 1rem; }
.upload-dropzone {
    border: 2px dashed #666; border-radius: 8px; padding: 3rem;
    text-align: center; margin: 1.5rem 0; transition: border-color 0.2s;
}
.upload-dropzone.drag-over { border-color: #4a9eff; background: rgba(74, 158, 255, 0.05); }
.bid-item {
    border: 1px solid #333; border-radius: 6px; padding: 1rem;
    margin: 0.75rem 0; background: #1a1a1a;
}
.bid-item-header { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
.confidence { font-size: 0.8rem; color: #888; }
.warning-banner { background: #332200; border: 1px solid #665500; padding: 0.5rem 1rem; border-radius: 4px; margin: 0.5rem 0; }
```

### PART 6: Gate post material enforcement in AI prompt

The AI prompt in `_build_cut_list_prompt()` (in `ai_cut_list.py`) needs to explicitly tell Claude what profile to use for gate posts. Currently the available profiles are listed but the AI picks freely.

Find where the prompt lists the available profiles (around lines 100-110 in `_PROFILE_GROUPS`) and where the field context is built. In the field context section, add:

```python
# If user selected post size, enforce it in the prompt
post_size = fields.get("post_size", "")
if post_size:
    field_lines.append("ENFORCED: Gate posts MUST use profile matching '%s'. "
                        "Do NOT use pipe for gate posts unless specifically requested." % post_size)
```

## Decomposition (execution order)

1. **Fix `_post_process_ai_result()` in `cantilever_gate.py`** — gate post dedup (1A), overhead beam dedup (1B), fence dedup (1C, 1D)
2. **Add `enforced_dimensions` to fab sequence pipeline** — update `generate_build_instructions()` signature, `_build_instructions_prompt()`, and the call site in `quote_session.py`
3. **Strengthen Rule 14** in fab sequence prompt (ai_cut_list.py)
4. **Add surface prep solvent** to consumables system
5. **Add gate post profile enforcement** to AI cut list prompt
6. **Create frontend PDF upload UI** — `bid-upload.js`, nav button, CSS, script tag
7. Test that existing quote generation still works without regressions

## Evaluation Design

### Grep checks:
```bash
# Post-processor should NOT have profile-specific gate post check anymore:
grep -n "post_profile_key" backend/calculators/cantilever_gate.py | head -5
# Verify it's used for CORRECTION, not for the existence check

# Verify enforced_dimensions parameter exists:
grep -n "enforced_dimensions" backend/calculators/ai_cut_list.py
grep -n "enforced_dimensions" backend/routers/quote_session.py

# Verify surface prep solvent exists:
grep -n "surface_prep_solvent" backend/knowledge/consumables.py

# Verify bid upload JS exists:
test -f frontend/js/bid-upload.js && echo "bid-upload.js exists ✅" || echo "FAIL"

# Verify Rule 14 is updated:
grep -A3 "GRINDING FOR OUTDOOR" backend/calculators/ai_cut_list.py
```

### Runtime verification:
```bash
cd backend && python -c "from calculators.cantilever_gate import CantileverGateCalculator; print('cantilever OK')"
cd backend && python -c "from calculators.ai_cut_list import AICutListGenerator; print('ai_cut_list OK')"
```


