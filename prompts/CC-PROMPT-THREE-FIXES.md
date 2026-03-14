# CC Prompt: Three Fixes — Sheet Nesting, Other Option, Edit Button

## Problem

Three bugs need fixing in one pass:

### Bug 1: Sheet Nesting Calculator (BACKEND)
The sheet material calculator in `backend/calculators/base.py` sums `sheets_needed` from EVERY cut list piece independently. If Opus returns 5 cut list pieces that each say `sheets_needed: 1`, the calculator charges for 5 sheets — even though multiple pieces nest onto the same sheet. For a 5' diameter sign, Opus's own assumptions say "front face + back panel from one 60x120 sheet" but the calculator counts them as 2 separate sheets.

**Root cause:** Lines ~300-303 in `base.py`:
```python
profile_totals[profile]["sheets_needed"] += (
    cut.get("sheets_needed", 0) * quantity
)
```
This blindly sums every piece's `sheets_needed`. Then line ~329 trusts this inflated sum.

### Bug 2: "Other" Option on Choice Questions (FRONTEND)
When the AI generates choice questions with predefined options, sometimes none of the options match the user's situation. Users need an "Other" button that reveals a text input field so they can type a custom answer.

**Location:** `frontend/js/quote-flow.js`, the `_renderQuestions()` method, specifically the `case 'choice':` block (~line 332).

### Bug 3: Edit Button Broken (FRONTEND)
Clicking the "Edit" button on a confirmed/extracted field deletes it from `this.extractedFields` and re-renders — but the field disappears and "All questions answered!" shows up instead of letting the user re-answer.

**Location:** `frontend/js/quote-flow.js`, the `editExtractedField()` method (~line 297).

---

## Acceptance Criteria

### Bug 1 — Sheet Nesting
- [ ] Sheet count is calculated from TOTAL PIECE AREA with nesting efficiency, NOT by summing per-piece `sheets_needed`
- [ ] For sheet profiles in the `trust_opus` path: use the already-accumulated `total_piece_area` divided by usable sheet area (75% nesting efficiency) to determine sheets needed — same logic as the legacy path
- [ ] Per-piece `sheets_needed` is STILL stored on individual cut list items for display purposes (so the cut list shows which pieces go on which sheet conceptually)
- [ ] The materials summary `sheets_needed` reflects the area-based calculation, not the sum
- [ ] A 5' diameter aluminum sign with front face (60x60), back panel (60x60), side bands (5x95 x2), internal rings, and standoffs should calculate 3-4 sheets of 60x120, NOT 5+
- [ ] Existing tests still pass

### Bug 2 — "Other" Option
- [ ] Every `choice` type question renders an additional "Other" button after all AI-generated options
- [ ] Clicking "Other" deselects any selected choice button and reveals a text input below the choices
- [ ] The text input has placeholder "Type your answer..."
- [ ] If the user types in the "Other" field, `_collectAnswers()` picks up that text value for the question ID
- [ ] If the user clicks a regular choice after clicking "Other", the text input hides and the choice is selected
- [ ] Style the "Other" button to match existing `.choice-btn` but with a subtle visual difference (dashed border or lighter shade)

### Bug 3 — Edit Button
- [ ] Clicking Edit on a confirmed field removes it from `extractedFields` AND re-renders it as an answerable question in the questions container
- [ ] The question should appear with the same type/options it originally had (or as a text input if original question metadata isn't available)
- [ ] "All questions answered!" should NOT appear while there are editable fields pending
- [ ] After the user re-answers and submits, the field returns to confirmed state with new value

---

## Steps

### Step 1: Fix Sheet Nesting in `backend/calculators/base.py`

In the material consolidation section (~line 325-335), change the `trust_opus` sheet path to use area-based nesting instead of summed `sheets_needed`:

**Replace the trust_opus sheet block** (the `if is_sheet and trust_opus and info["sheets_needed"] > 0:` block) with area-based calculation:

```python
if is_sheet and info.get("total_piece_area", 0) > 0:
    import math
    stock = info["sheet_stock_size"]
    if stock:
        sheet_area_sqin = stock[0] * stock[1]
        sheet_sqft = sheet_area_sqin / 144.0
    else:
        sheet_area_sqin = 48 * 96  # fallback 4x8
        sheet_sqft = 32.0
    usable_area = sheet_area_sqin * 0.85  # 85% nesting efficiency for laser-cut parts
    sheets_needed = max(1, int(math.ceil(
        info["total_piece_area"] / usable_area
    )))
    info["sheets_needed"] = sheets_needed
    line_total = round(sheets_needed * sheet_sqft * info["price_ft"], 2)
    wasted_ft = raw_ft
    waste_factor = 0.0
```

Key changes:
- Remove the separate `trust_opus` sheet path — unify with the area-based path
- Use 85% nesting efficiency (up from 75%) — laser-cut parts nest tighter than manual cuts
- The `import math` should be moved to top of file if not already there

Also remove the now-duplicate legacy sheet path (the `elif is_sheet and info.get("total_piece_area", 0) > 0:` block) since we unified them.

### Step 2: Add "Other" Option in `frontend/js/quote-flow.js`

In the `_renderQuestions()` method, modify the `case 'choice':` block:

```javascript
case 'choice':
    input = `<div class="choice-group" data-qid="${q.id}">
        ${(q.options || []).map(opt => `
            <button class="choice-btn" onclick="QuoteFlow.selectChoice(this, '${q.id}')" data-value="${opt}">
                ${opt}
            </button>
        `).join('')}
        <button class="choice-btn choice-btn-other" onclick="QuoteFlow.selectOther(this, '${q.id}')" data-value="__other__">
            Other
        </button>
        <input type="text" id="q-other-${q.id}" class="text-input other-input" placeholder="Type your answer..." style="display:none; margin-top: 8px;">
    </div>`;
    break;
```

Add `selectOther` method:

```javascript
selectOther(btn, qid) {
    const group = btn.closest('.choice-group');
    group.querySelectorAll('.choice-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    const otherInput = document.getElementById(`q-other-${qid}`);
    if (otherInput) otherInput.style.display = 'block';
},
```

Modify `selectChoice` to hide "Other" input when a regular choice is selected:

```javascript
selectChoice(btn, qid) {
    const group = btn.closest('.choice-group');
    group.querySelectorAll('.choice-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    // Hide "Other" input if it exists
    const otherInput = document.getElementById(`q-other-${qid}`);
    if (otherInput) {
        otherInput.style.display = 'none';
        otherInput.value = '';
    }
},
```

Update `_collectAnswers()` — in the choice group collection, check for "Other":

```javascript
// Choice groups
container.querySelectorAll('.choice-group').forEach(group => {
    const qid = group.dataset.qid;
    const selected = group.querySelector('.choice-btn.selected');
    if (selected) {
        if (selected.dataset.value === '__other__') {
            const otherInput = document.getElementById(`q-other-${qid}`);
            if (otherInput && otherInput.value.trim()) {
                answers[qid] = otherInput.value.trim();
            }
        } else {
            answers[qid] = selected.dataset.value;
        }
    }
});
```

Add CSS for the "Other" button in `frontend/css/styles.css`:

```css
.choice-btn-other {
    border-style: dashed !important;
    opacity: 0.8;
}
.choice-btn-other.selected {
    opacity: 1;
    border-style: solid !important;
}
.other-input {
    width: 100%;
}
```

### Step 3: Fix Edit Button in `frontend/js/quote-flow.js`

Replace the `editExtractedField()` method:

```javascript
editExtractedField(fieldId) {
    // Remove from extracted fields
    const oldValue = this.extractedFields[fieldId];
    delete this.extractedFields[fieldId];

    // Re-render the clarify step — the field should now appear as a question
    if (this.sessionId) {
        API.getSessionStatus(this.sessionId).then(data => {
            // Find if this field has a matching question in next_questions
            let questions = data.next_questions || [];

            // If the field isn't in the returned questions, create a generic text question for it
            const hasQuestion = questions.some(q => q.id === fieldId);
            if (!hasQuestion) {
                questions.unshift({
                    id: fieldId,
                    text: `${fieldId.replace(/_/g, ' ')}:`,
                    type: 'text',
                    required: false,
                    hint: `Previously: ${oldValue}`
                });
            }

            this._renderClarifyStep({
                job_type: document.querySelector('.clarify-header h2')?.textContent || '',
                completion: data.completion || {},
                extracted_fields: this.extractedFields,
                photo_extracted_fields: data.photo_extracted_fields || {},
                next_questions: questions,
            });
            this._showStep('clarify');
        }).catch(err => {
            console.error('Edit field error:', err);
            // Fallback: just create a text input for the field
            const container = document.getElementById('questions-container');
            if (container) {
                container.innerHTML = `
                    <div class="question-card" data-qid="${fieldId}">
                        <div class="q-header">
                            <label class="q-label">${fieldId.replace(/_/g, ' ')}:</label>
                        </div>
                        <input type="text" id="q-${fieldId}" class="text-input" 
                            placeholder="Enter new value" value="${oldValue || ''}">
                    </div>
                `;
            }
        });
    }
},
```

### Step 4: Tests

Add tests for the sheet nesting fix:

```python
# In tests/test_session3_calculators.py or a new test file

def test_sheet_nesting_multiple_pieces_same_profile():
    """Multiple cut list pieces sharing the same sheet profile should nest, not sum sheets."""
    # Simulate a sign with: front face (60x60), back panel (60x60), side bands (5x95 x2)
    # All using al_sheet_0.125 with 60x120 stock
    # Total piece area: 60*60 + 60*60 + 5*95*2 = 3600 + 3600 + 950 = 8150 sq in
    # Sheet area: 60*120 = 7200 sq in, usable at 85% = 6120 sq in
    # Sheets needed: ceil(8150 / 6120) = 2
    # NOT 5 (which is what happens when summing per-piece sheets_needed)
    pass  # Implement with actual calculator call
```

---

## Constraints

- Do NOT change backend API response shapes — frontend depends on them
- Do NOT modify the Opus prompt or extraction logic — those are separate concerns
- Do NOT touch calculator routing, labor estimation, or pricing engine
- The `import math` should be at the top of `base.py`, not inside the function
- Keep per-piece `sheets_needed` in cut list items for informational display
- All existing tests must pass
- The "Other" text input must work with the existing `_collectAnswers()` → `submitAnswers()` → `/answer` API flow

---

## Verification

1. Run `python -m pytest tests/ -x -q` — all tests pass
2. Start a new quote session for a 5' diameter aluminum sign — materials should show 3-4 sheets, not 5+
3. During clarify step, choice questions should show an "Other" button
4. Clicking "Other" reveals a text input; typing and submitting sends the custom text
5. Clicking Edit on a confirmed field shows it as an editable question, not "All questions answered!"
6. After re-answering an edited field and submitting, it returns to confirmed state
