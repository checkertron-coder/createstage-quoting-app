# Session 2A — Question Trees for Priority A Job Types (Top 5)

## Before You Start
1. Read `CLAUDE.md` — architecture bible, data contracts, question tree JSON schema
2. Read `BUILD_LOG.md` — what Session 1 completed
3. Run `cd /Users/createstage/Desktop/createstage-quoting-app && source .venv/bin/activate && pytest tests/ -v` — fix anything failing before you touch code
4. Read `backend/models.py` — understand the v2 schema from Session 1

---

## Your Mission This Session

Build the question tree system and create trees for the 5 highest-priority job types.

### Deliverable 1 — Question Tree Engine

Create the system that loads, processes, and walks through question trees.

**Files to create:**
- `backend/question_trees/` directory
- `backend/question_trees/__init__.py`
- `backend/question_trees/engine.py` — the core logic

**Engine behavior:**
```python
class QuestionTreeEngine:
    def load_tree(self, job_type: str) -> dict:
        """Load question tree JSON for a job type"""

    def extract_from_description(self, job_type: str, description: str) -> dict:
        """
        Use Gemini to parse a natural language description and extract
        any fields that were already answered.
        Returns: {field_id: extracted_value} for fields found in description.
        THIS IS CRITICAL — do not re-ask questions the user already answered.
        """

    def get_next_questions(self, job_type: str, answered_fields: dict) -> list:
        """
        Given what's already answered, return the next unanswered questions.
        Respects branching logic (e.g., if motor=Yes, ask motor_brand next).
        Returns only questions whose dependencies are met and aren't answered yet.
        """

    def is_complete(self, job_type: str, answered_fields: dict) -> bool:
        """Are all required fields answered?"""

    def get_quote_params(self, job_type: str, answered_fields: dict) -> dict:
        """Convert answered fields into a QuoteParams dict matching CLAUDE.md contract"""
```

**The extraction prompt for Gemini must:**
- Receive the user's description + the list of field IDs and their descriptions
- Return ONLY fields it is confident about (>90% confidence)
- Never guess measurements — if the user said "about 10 feet" extract 10, if they said "big gate" do NOT guess a width
- Return a JSON object: `{"field_id": "value", ...}`

### Deliverable 2 — Question Tree API Endpoint

**Files to create/modify:**
- `backend/routers/quote_session.py` — new router for the conversation flow

**Endpoints:**
```
POST /api/session/start
    Body: { "description": str, "job_type": str | null, "photos": list[str] | null }
    → Creates a quote_session record
    → If job_type not provided, uses Gemini to detect it from description
    → Runs extract_from_description on the initial text
    → Returns: { session_id, job_type, extracted_fields, next_questions }

POST /api/session/{session_id}/answer
    Body: { "answers": { "field_id": "value", ... } }
    → Stores answers in the session's params_json
    → Checks branching logic, returns next questions
    → Returns: { answered_count, total_required, next_questions, is_complete }

GET /api/session/{session_id}/status
    → Returns current state: answered fields, remaining questions, completion %
```

**Rules:**
- Session records persist in the `quote_sessions` table from Session 1
- Messages are logged in `messages_json` for conversation replay
- The engine NEVER asks a question whose answer is already in `params_json`

### Deliverable 3 — Question Trees for Priority A Job Types

Create JSON files in `backend/question_trees/data/` following the EXACT schema from CLAUDE.md.

**The 5 trees to build:**

#### 1. `cantilever_gate.json`
Minimum 18 questions covering:
- Clear opening width, gate height
- Frame material + gauge (with common options: 2" sq tube 11ga, 2" sq tube 14ga, etc.)
- Infill type (expanded metal / flat bar / pickets / solid panel / open)
  → Branch: if flat bar, ask spacing + orientation
  → Branch: if pickets, ask style + spacing + decorative elements
- Counterbalance tail clearance (critical — if insufficient, recommend swing gate instead)
- Number of posts (typically 3), post material + size, concrete depth
- Roller carriages (quantity, heavy duty vs standard)
- Electric motor (yes/no/unsure)
  → Branch: if yes, ask brand (LiftMaster LA412, US Automatic Patriot, Viking, Bull Dog, other)
  → Branch: if unsure, display info about options then ask
- Bottom guide rail (surface mount or embedded)
- Hinges: N/A for cantilever — but include a latch/lock question
- Finish (raw / clear coat / powder coat / paint / galvanized)
  → Branch: if powder coat, ask color + in-house or outsourced
- Installation included? (shop pickup / delivery / full install)
  → Branch: if install, ask site location for on-site rate
- Decorative elements or design reference photos?
- Site access constraints (for install quoting)

#### 2. `swing_gate.json`
Minimum 16 questions covering:
- Clear opening width, gate height
- Single panel or double panel
- Frame material + gauge
- Infill type (same branches as cantilever)
- Number of posts (typically 2 for single, 3 for double), post material + size, concrete depth
- Hinges: weld-on or bolt-on? Heavy duty? How many? (MUST match gate weight)
- Latch type (gravity / magnetic / keyed / electric strike / none)
- Electric motor (yes/no — swing gate operators are different from cantilever)
  → Branch: if yes, ask brand + arm type (linear arm, articulated arm, underground)
- Finish
- Installation included?
- Decorative elements or reference photos?
- Auto-close mechanism? (spring hinge, hydraulic closer)

#### 3. `straight_railing.json`
Minimum 14 questions covering:
- Linear footage (total run)
- Location: interior/exterior
- Application: residential/commercial (changes code requirements)
  → Branch: if commercial, note IBC 1015 — 42" min height, 4" max baluster spacing
  → Branch: if residential, note IRC R312 — 36" min height
- Railing height (present code minimums, let customer choose within range)
- ADA compliance required? (changes rail profile — must be graspable 1.25-2" diameter)
- Top rail profile (round tube, square tube, flat bar cap, wood cap)
- Baluster/infill style (round bar, square bar, flat bar, cable, glass, horizontal bar, none)
  → Branch: if cable, ask cable diameter + tensioner hardware
  → Branch: if glass, ask tempered panel or clamp system
- Baluster spacing (default 4" for code, but ask)
- Post type (surface mount flange, core drill, side mount, embedded)
- Post spacing (6-8 ft typical)
- Number of transitions (corners, returns, stair-to-flat, end caps)
- Finish
- Installation included?
- Design reference photos?

#### 4. `stair_railing.json`
Minimum 16 questions — ALL of straight_railing PLUS:
- Stair rake angle OR rise/run dimensions (to calculate angle)
- Number of risers
- Top newel post and bottom newel post included?
- Continuous top rail or post-to-post?
- Balusters plumb (vertical) or parallel to stair rake?
- Does the railing continue on a landing at top/bottom? (adds straight section)
- Wall-mounted handrail on opposite side needed? (commercial code often requires both sides)
- Stair width (affects if railing is one side or both)

#### 5. `repair_decorative.json`
Minimum 12 questions — PHOTO-FIRST workflow:
- Photo upload (REQUIRED — mark as first question, type: "photo")
- What needs repair? (broken weld, bent/damaged section, rust-through, missing piece, other)
- Is this a gate, fence, railing, or other? (helps scope)
- Material type if known (mild steel, wrought iron, aluminum, stainless)
  → If unknown: "Can you see any rust? (Orange rust = mild steel/iron. No rust = possibly aluminum, stainless, or galvanized)"
- Approximate dimensions of damaged area
- Is this structural or cosmetic? (structural = load-bearing, safety-critical)
- Will matching finish be required? (matching patina/paint is harder than new finish)
- Age of existing work if known (affects material condition, hidden damage risk)
- Can the piece be removed and brought to shop, or is it on-site only?
  → Branch: if on-site, ask access constraints (height, tight space, indoor/outdoor)
- Is there surrounding damage beyond the primary repair? (scope creep flag)
- Do you need a site visit to assess before quoting? (charge 1-1.5 hrs)
- Budget range if any? (helps calibrate repair vs. replacement recommendation)

---

## Question Tree JSON Schema (from CLAUDE.md — follow EXACTLY)

```json
{
    "job_type": "cantilever_gate",
    "version": "1.0",
    "display_name": "Cantilever Sliding Gate",
    "category": "ornamental",
    "required_fields": ["clear_width", "height", "frame_material", ...],
    "questions": [
        {
            "id": "clear_width",
            "text": "What is the clear opening width?",
            "type": "measurement",
            "unit": "feet",
            "required": true,
            "hint": "Measure from post to post, or the driveway width",
            "depends_on": null,
            "branches": null
        },
        {
            "id": "has_motor",
            "text": "Will this gate have an electric operator?",
            "type": "choice",
            "options": ["Yes", "No", "Not sure — show me options"],
            "required": true,
            "hint": null,
            "depends_on": null,
            "branches": {
                "Yes": ["motor_brand"],
                "Not sure — show me options": ["motor_info", "motor_brand"]
            }
        }
    ]
}
```

Field types: `"measurement"` | `"choice"` | `"multi_choice"` | `"text"` | `"photo"` | `"number"` | `"boolean"`

---

## Acceptance Tests

Create `tests/test_session2a_question_trees.py`:
```python
def test_all_5_trees_load()                    # All 5 JSON files parse without error
def test_cantilever_gate_has_min_18_questions() # Count >= 18
def test_swing_gate_has_min_16_questions()      # Count >= 16
def test_repair_first_question_is_photo()       # repair_decorative[0].type == "photo"
def test_branching_logic_motor()               # cantilever: has_motor=Yes → motor_brand appears in next
def test_extract_from_description()            # "10-foot cantilever gate, 6 feet tall, 2\" sq tube" → extracts clear_width, height, frame_material
def test_no_duplicate_questions()              # After extraction, get_next_questions skips extracted fields
def test_is_complete_when_all_required_filled() # Fill all required → is_complete returns True
def test_stair_railing_includes_rake_angle()   # Has rake angle or rise/run question
def test_straight_railing_code_branching()     # commercial → 42" min noted; residential → 36"
```

---

## What NOT To Build This Session
- Material calculators (Session 3)
- Labor estimator (Session 4)
- Hardware sourcing (Session 5)
- Frontend UI (Session 6)
- PDF output (Session 6)

---

## When You're Done

Update `BUILD_LOG.md` with:
- What was completed
- Test results
- Any deviations from CLAUDE.md
- Update CLAUDE.md if any architectural decisions were made
