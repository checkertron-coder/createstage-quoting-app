# PROMPT 32 — Polish Client PDF + Customer Info + Logo Upload + Scope Rewrite

## Context

CS-2026-0040 has BOTH PDFs working — shop copy (11 pages, incredible detail) and client copy (2 pages, clean). The shop copy is a masterpiece. The client copy needs polish before it's customer-ready. This prompt is about making the client proposal something a property manager or homeowner opens and says "yes."

## WHAT'S WORKING (do not break)

The shop copy PDF is perfect. Do not touch it. Everything about it is correct:
- 44 individually itemized material pieces with correct prices
- Full detailed cut list with notes
- 15-step fab sequence with safety notes
- Stock order with remaining footage
- Labor breakdown by process
- Hardware with supplier alternatives
- Consumables with surface prep solvent

## PART 1: Fix Client PDF Issues

### 1A: Remove Markup from Client Copy

**Current:**
```
Subtotal        $13,307.23
Markup (15%)     $1,996.08
PROJECT TOTAL   $15,303.31
```

**Should be:**
```
PROJECT TOTAL   $15,303.31
```

The customer sees ONE number. The markup is baked into the total — they never know the percentage. Remove the Subtotal line and the Markup line entirely from the client PDF. Just show the final total.

If you want to show a breakdown, show it like this:
```
Materials & Hardware    $4,377.06    ← (original + markup portion)
Labor                  $10,413.25   ← (original + markup portion)  
Finishing                $513.02    ← (original + markup portion)
─────────────────────────────────
PROJECT TOTAL          $15,303.31
```

Each category has the markup distributed proportionally so the total is correct and no "markup" line exists. Pick whichever approach is simpler — either just the total, or the distributed breakdown. Either way: **no markup line, no subtotal line, no percentage visible.**

### 1B: Fix Double Percent Sign

**Current:** `50%% of labor + 100%% of materials`
**Should be:** `50% of labor + 100% of materials`

This is a Python string formatting bug. The template is using `%%` to escape percent signs (which is correct in old-style `%` formatting) but if using f-strings or `.format()`, just use `%`. Find the terms template and fix it.

```bash
grep -rn "50%\|100%\|%%\|payment\|Payment" backend/ --include="*.py" | grep -v __pycache__
```

### 1C: Remove Shop Details from "What's Included"

**Current:**
```
- All materials and steel as specified (44 items)
- Hardware: Top-mount roller carriage - standard, Gate stop/bumper, Gate latch - Gravity latch
- Welding consumables (wire, gas, grinding discs)
- Shop labor (70.5 hours)
- Paint finish
- Site installation and cleanup
```

**Should be:**
```
- Custom fabricated cantilever sliding gate (12 ft opening, 10 ft tall)
- Two fence sections (13 ft and 15 ft) with matching picket infill
- All structural steel, hardware, and fasteners
- Seven steel posts set in concrete footings
- Overhead support beam and top-hung roller carriage system
- Professional paint finish (black)
- Complete site installation including concrete, welding, and gate adjustment
- Final inspection and operational verification
```

No item counts, no hour counts, no consumable details, no specific hardware model names. Write it in terms the CUSTOMER understands — what they're getting, not how the shop builds it.

This list should be generated from the quote data, not hardcoded. Use the job type, fields, and material summary to build customer-friendly bullet points.

### 1D: Remove Specific Numbers from Terms

**Current:** `Payment: 50% of labor + 100% of materials due at signing.`

**Should be:** `Payment: 50% due at signing. Remaining 50% due upon completion.`

The customer doesn't need to know the split is labor vs materials. Just 50/50.

## PART 2: AI-Generated Scope of Work

The current scope of work just pastes the raw job description. That's contractor language. The client copy needs a professional, customer-friendly scope written by Claude.

### Implementation

Add a method that generates the scope text when the client PDF is requested. Cache it in `session.params_json["_client_scope"]` so it's not regenerated on every download.

**Prompt for scope generation:**
```python
def generate_client_scope(self, job_type, fields, priced_quote):
    """Generate customer-friendly scope of work."""
    prompt = f"""Write a professional scope of work for a client proposal from a metal fabrication company.

JOB TYPE: {job_type}
PROJECT DETAILS:
{json.dumps({k: v for k, v in fields.items() if not k.startswith('_')}, indent=2)}

PRICE TOTAL: ${priced_quote.get('total', 0):,.2f}

Write a professional 2-3 paragraph scope of work that:
1. Describes what will be built in plain English (no shop jargon, no gauge numbers, no profile codes)
2. Mentions key dimensions (opening width, height, fence lengths)
3. Describes the finish and installation
4. Sounds confident and professional — this is going to a homeowner or property manager
5. Does NOT mention pricing, hours, or internal processes

Example tone: "CreateStage Fabrication will design, fabricate, and install a custom cantilever 
sliding gate system for your property. The gate will span the full 12-foot opening with a 
top-hung roller mechanism that keeps the ground completely clear..."

Return ONLY the scope paragraphs, no headers or formatting."""
    
    text = call_fast(prompt, timeout=30)
    return text
```

Place this scope text in the client PDF between the header and the price summary, replacing the raw job description.

## PART 3: Customer Information

### 3A: Add Customer Fields to Quote Session

Add these fields to the quote creation flow. They should appear AFTER the question tree is complete and BEFORE the quote generates — or as editable fields on the quote results page.

Fields:
- **Customer Name** (text, required for client PDF)
- **Customer Phone** (text, optional)
- **Customer Email** (text, optional)
- **Customer Address** (text, optional — job site address may differ)

Store in `session.params_json["_customer"]`:
```json
{
    "name": "John Smith",
    "phone": "312-555-1234",
    "email": "john@example.com",
    "address": "1234 N Main St, Chicago, IL 60611"
}
```

### 3B: Frontend — Customer Info Form

Add a customer info section to the quote results page. It should appear above the download buttons:

```html
<div class="customer-info-section">
    <h3>Customer Information</h3>
    <p class="hint">Required for client proposal. You can update this anytime.</p>
    <div class="form-row">
        <label>Customer Name *</label>
        <input type="text" id="customer-name" placeholder="Property owner or company name">
    </div>
    <div class="form-row">
        <label>Phone</label>
        <input type="tel" id="customer-phone" placeholder="312-555-1234">
    </div>
    <div class="form-row">
        <label>Email</label>
        <input type="email" id="customer-email" placeholder="customer@email.com">
    </div>
    <div class="form-row">
        <label>Address</label>
        <input type="text" id="customer-address" placeholder="Job site or billing address">
    </div>
    <button class="btn btn-sm btn-secondary" onclick="QuoteFlow.saveCustomerInfo()">Save</button>
</div>
```

When "Save" is clicked, POST the customer data to a new endpoint that updates `session.params_json["_customer"]`.

When downloading the Client PDF, the "Prepared for:" section should show:
```
Prepared for: John Smith
312-555-1234 | john@example.com
1234 N Main St, Chicago, IL 60611
```

If no customer info is saved, show "Prepared for: [Customer Name]" as placeholder text.

### 3C: Client PDF Button Validation

The "Client Copy" download button should check if customer name is filled in. If not, highlight the customer name field and show a message: "Enter customer name to generate proposal."

## PART 4: Logo Upload in User Profile

### 4A: Add Logo Upload to Onboarding/Profile

The user profile already has a `logo_url` field (we saw it in `pdf.py` — `current_user.logo_url`). Add a file upload input to the profile page.

In the profile/onboarding section of the frontend (find it in `frontend/js/auth.js` or wherever the profile form lives):

```html
<div class="form-row">
    <label>Company Logo</label>
    <input type="file" id="logo-upload" accept="image/png,image/jpeg,image/svg+xml" 
           onchange="Profile.uploadLogo(this.files[0])">
    <p class="hint">PNG, JPG, or SVG. Appears on quotes and proposals.</p>
    <div id="logo-preview"></div>
</div>
```

### 4B: Logo Upload Endpoint

Add an endpoint to handle logo upload:
```python
@router.post("/profile/logo")
def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Validate file type (png, jpg, svg)
    # Save to static directory or cloud storage
    # Update current_user.logo_url
    # Return the URL
```

For simplicity, save logos to a `static/logos/` directory and serve them at `/static/logos/{filename}`. Or use Railway's ephemeral storage with a note that logos may need re-upload after deploys (better: store as base64 in the database in `current_user.logo_url`).

**Recommended: Store as base64 in the database.** Railway's filesystem is ephemeral. Save the logo as a data URI in `current_user.logo_url`:
```python
import base64
logo_b64 = base64.b64encode(file_bytes).decode()
current_user.logo_url = f"data:{content_type};base64,{logo_b64}"
```

### 4C: Render Logo in PDFs

Both shop and client PDFs should render the logo in the header. Check `backend/pdf_generator.py` — it already references `user_profile["logo_url"]`. Make sure it handles:
1. HTTP/HTTPS URLs (existing)
2. Data URIs (new — base64 encoded)
3. None/empty (show text-only header, which is current behavior)

## PART 5: Minor Fixes

### 5A: Overhead beam profile in detailed cut list shows hss_4x4_0.25 but materials show hss_6x4_0.25

In the CS-2026-0040 shop copy:
- Detailed cut list line 13: `Overhead support beam - HSS 4x4, hss_4x4_0.25, 240"`
- Materials line 13: `Overhead support beam - HSS 4x4, hss_6x4_0.25, $240.00`

The detailed cut list (from Claude) says 4x4. The materials (from post-processor?) says 6x4. These should match. The correct profile for residential under 800 lbs is `hss_4x4_0.25`.

Find where the materials section gets its profile for the overhead beam and make sure it uses the same profile as the cut list.

### 5B: `hss_4x4_0.25` "Unrecognized profile" warning still showing

This warning appears on every quote. Find the validation that generates it:
```bash
grep -rn "Unrecognized profile\|unrecognized.*profile\|VALID_PROFILES\|known_profiles" backend/ --include="*.py"
```

Add `hss_4x4_0.25` and `hss_6x4_0.25` to whatever dict/set is missing them.

## Decomposition

1. Fix client PDF — remove markup line, fix %%, rewrite What's Included, simplify terms
2. Add AI scope of work generation for client PDF
3. Add customer info fields (frontend form + backend storage + PDF rendering)
4. Add logo upload to profile (base64 storage + PDF rendering)
5. Fix overhead beam profile mismatch (materials vs cut list)
6. Fix hss_4x4_0.25 unrecognized profile warning
7. Verify shop copy PDF is unchanged

## Evaluation Design

```bash
# Markup not visible in client PDF generator:
grep -n "markup\|Markup" backend/pdf_generator*.py | head -10
# Should NOT appear in client PDF section

# Double percent fixed:
grep -n "%%" backend/pdf_generator*.py | head -5
# Should return zero results (or only in old-style % formatting that's correct)

# Customer info storage:
grep -n "_customer\|customer_name\|customer_phone" backend/routers/quote_session.py | head -5

# Logo upload endpoint:
grep -n "logo\|Logo" backend/routers/ -r --include="*.py" | head -5

# HSS profile in valid profiles:
grep -n "hss_4x4_0.25" backend/ -r --include="*.py" | head -10

# Runtime:
cd backend && python -c "from pdf_generator import generate_quote_pdf; print('OK')"
```
