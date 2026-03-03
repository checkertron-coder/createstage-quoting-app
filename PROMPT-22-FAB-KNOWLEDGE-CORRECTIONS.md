# PROMPT 22 — Fabrication Knowledge Corrections + Picket Options + Cross Braces + Labor Calibration

## READ THIS FIRST — INTEGRATION RULES

From CLAUDE.md: Building a module is not done until it's CALLED in the pipeline. After any change, trace the full path from user input → AI generation → validation → PDF output. If your new code isn't in that path, it's not done.

---

## PROBLEM STATEMENT

CS-2026-0028 was a huge step forward — fence sections, top-mount carriages, gravity latch all landed. But a fabricator review exposed knowledge gaps and labor calibration issues that make the quote feel like it was written by someone who's read about fabrication but never stood at the table. This prompt fixes the shop-floor accuracy.

**Burton's exact feedback (paraphrased for clarity):**

1. No grinding welds smooth on an outdoor gate or fence — you clean up spatter and sharp edges, you don't make it furniture-grade. 17.8 hours of grinding is insane.
2. Never use a file — ever. Angle grinder + flap disc only. A file would take six years.
3. You MUST remove mill scale at the end of each cut tube before welding. Mill scale in the weld pool causes porosity. Standard practice.
4. MIG weld in the shop, stick weld in the field. Possibly dual-shield flux core for structural, but not needed for fence/gate.
5. Fit and tack at 1.5 hours is laughably low — should be 3-4 hours minimum for this job.
6. Paint at 1.5 hours is wrong — always prime AND paint for outdoor steel, 3-4 hours.
7. A 10' tall fence/gate NEEDS horizontal cross braces (mid-rails) to break up the picket span. Usually 1 or 2 depending on height.
8. Cross braces can be pre-fabbed C-channel with pre-punched holes for the pickets (much faster than welding each picket individually to rails + cross braces).
9. Picket options are way too limited — only 3/4" square bar and 5/8" round bar. Real options include: 1/2" square solid, 5/8" square solid, 3/4" square solid, 1" square tube 16ga, 1" square tube 14ga, 5/8" round solid, 3/4" round solid, and spear-top pre-punched versions. Residential vs commercial grade matters.
10. Post depth needs to be past the frost line. Chicago code is 42" minimum. The calculator already does 42" but the AI cut list overrode it with 156" posts (only 36" embed instead of 42").

---

## ACCEPTANCE CRITERIA

### Fix 1: Grinding/Finishing Rules for Outdoor Work

- [ ] In `FAB_KNOWLEDGE.md` (or wherever the Gemini prompt guidance lives), add a clear rule:
  > **Outdoor gates and fences: DO NOT grind welds smooth.** Clean up spatter, remove sharp edges, knock down any high spots that would show through paint. That's it. Save smooth grinding for indoor/decorative/furniture work. Outdoor structural welding gets cleaned, not ground flat.
- [ ] In the labor estimator, add a context flag for indoor vs outdoor work. Outdoor grind hours should be ~30-40% of indoor grind hours for the same weld volume.
- [ ] Remove all references to "file" from fabrication sequences. The tool is ALWAYS an angle grinder with a flap disc. A die grinder with a roloc disc for tight spots. Never a file.
- [ ] The AI build instruction prompt must include this rule so Gemini doesn't generate "grind all welds smooth" for outdoor work.

### Fix 2: Mill Scale Removal

- [ ] Add to the fabrication knowledge: after EVERY cut, the fabricator must remove 1-2" of mill scale from the cut end of the tube using a flap disc or grinding wheel. This is mandatory before welding — mill scale in the weld pool causes porosity.
- [ ] The AI build instruction prompt must include: "After each cut, grind off mill scale 1-2 inches from each cut end using a flap disc. This prevents porosity in the weld."
- [ ] This applies to ALL tube/bar stock cuts, not just specific job types.

### Fix 3: Welding Process Specification

- [ ] Add welding process logic to the build instructions:
  - **Shop work:** MIG (GMAW) — standard for all shop fabrication on gates, fences, railings
  - **Field work (installation):** Stick (SMAW) — standard for site welding where wind/weather affect shielding gas
  - **Structural field work:** Dual-shield flux core (FCAW) — strongest and fastest for structural connections in the field
  - **The fab sequence must specify the welding process per step** — "MIG weld in shop" vs "Stick weld on site"
- [ ] The Gemini prompt for build instructions must include this guidance so it generates appropriate welding process per step.

### Fix 4: Labor Calibration

- [ ] **Grind & Clean:** For outdoor gate + fence (this job), should be ~4-6 hours MAX, not 17.8. The labor estimator needs to differentiate:
  - Interior/decorative: full grind hours (current calculation may be OK)
  - Exterior/paint finish: 30-40% of full grind hours — you're cleaning, not polishing
- [ ] **Fit & Tack:** For this job (gate frame + 137 pickets + 2 fence frames + fence pickets + posts), 1.5 hours is absurdly low. This is the most skill-intensive step — positioning everything, checking square, tacking in sequence. Should be 3-5 hours for this scope. Review the labor estimator's fit-and-tack calculation — it's likely based only on joint count without considering the time to position, space, and verify each picket.
- [ ] **Paint:** Always prime + paint for outdoor steel. Minimum 3-4 hours for this job scope (~786 sq ft of surface area). The current 1.5 hours doesn't even cover primer dry time + second coat. Update the labor estimator's paint hours calculation.
- [ ] **Hardware Install:** 2.0 hours seems reasonable for mounting carriages + latch + stops. Keep this.
- [ ] **Site Install:** 12 hours is in the range for setting 7 posts + hanging gate + mounting fence sections. Keep this.
- [ ] After calibration, total labor hours for this job should land in the 55-70 hour range, not 63.

### Fix 5: Cross Braces / Mid-Rails for Fence Sections

- [ ] The cantilever gate calculator already adds mid-rails to the gate (lines 136-152) — 1 mid-rail if height ≤ 72", 2 if taller. **This same logic must apply to fence sections.**
- [ ] For fence sections, add mid-rails based on height:
  - Height ≤ 48" (4'): No mid-rail needed
  - Height 48-72" (4-6'): 1 mid-rail (centered)
  - Height > 72" (6'+): 2 mid-rails (at 1/3 and 2/3 height)
- [ ] Mid-rail material: Same frame profile as the fence rails (2x2 tube). This is the simple approach.
- [ ] **FUTURE ENHANCEMENT (not this prompt):** Pre-fabbed C-channel cross braces with punched holes for pickets. This is a more advanced manufacturing approach — for now, use standard tube mid-rails welded in place.
- [ ] The mid-rails must appear in the materials list and cut list.
- [ ] The AI build instructions must include a step for fitting and welding mid-rails.
- [ ] Additional weld inches: 2 welds per picket at each mid-rail intersection (adds significant weld volume for tall fences with 2 mid-rails).

### Fix 6: Picket Size Options

- [ ] Update the `picket_style` question in `cantilever_gate.json` to include size AND style:

Replace the current `picket_style` question with TWO questions:

**New question 1: `picket_material`**
```json
{
    "id": "picket_material",
    "text": "What picket material and size?",
    "type": "choice",
    "options": [
        "1/2\" square solid bar (light residential)",
        "5/8\" square solid bar (standard residential)",
        "3/4\" square solid bar (heavy residential / light commercial)",
        "1\" square tube 16ga (standard commercial)",
        "1\" square tube 14ga (heavy commercial / industrial)",
        "5/8\" round solid bar (standard residential)",
        "3/4\" round solid bar (heavy residential)"
    ],
    "required": true,
    "hint": "5/8\" square bar is the most common residential fence picket. 3/4\" square is heavy-duty residential or light commercial. 1\" square tube is commercial grade. Round bar gives a softer traditional look.",
    "depends_on": "infill_type"
}
```

**New question 2: `picket_top`**
```json
{
    "id": "picket_top",
    "text": "Picket top style?",
    "type": "choice",
    "options": [
        "Plain (flat cut top)",
        "Pressed spear point (pre-punched — fastest)",
        "Welded-on spear finial (+$2-4 per picket)",
        "Ball top cap (+$1-2 per picket)",
        "Quad flare (decorative)"
    ],
    "required": false,
    "hint": "Pressed spear is the industry standard for ornamental fence — it's one piece, no welding. Welded finials look more traditional but add significant labor.",
    "depends_on": "infill_type"
}
```

- [ ] Remove the old `picket_style` question
- [ ] Update the calculator to read `picket_material` instead of `picket_style` and map to the correct profile key:
  - "1/2\" square solid bar" → `sq_bar_0.5`
  - "5/8\" square solid bar" → `sq_bar_0.625`
  - "3/4\" square solid bar" → `sq_bar_0.75`
  - "1\" square tube 16ga" → `sq_tube_1x1_16ga`
  - "1\" square tube 14ga" → `sq_tube_1x1_14ga`
  - "5/8\" round solid bar" → `rd_bar_0.625`
  - "3/4\" round solid bar" → `rd_bar_0.75`
- [ ] Add ANY missing profiles to `material_lookup.py` `_SEEDED_PRICES`. Use these approximate prices:
  - `sq_bar_0.5`: ~$0.75/ft, 0.85 lbs/ft
  - `sq_bar_0.625`: ~$1.10/ft, 1.33 lbs/ft
  - `sq_bar_0.75`: ~$1.50/ft, 1.91 lbs/ft (already exists?)
  - `sq_tube_1x1_16ga`: ~$1.20/ft, 0.84 lbs/ft
  - `sq_tube_1x1_14ga`: ~$1.50/ft, 1.04 lbs/ft (may already exist)
  - `rd_bar_0.625`: ~$0.90/ft, 1.04 lbs/ft
  - `rd_bar_0.75`: ~$1.25/ft, 1.50 lbs/ft
- [ ] Also update the `ornamental_fence.json` question tree with the same picket_material options (if it has a picket question)

### Fix 7: AI Cut List Must Not Override Calculator Dimensions

- [ ] The AI cut list currently overrides post lengths. CS-2026-0028 shows 156" posts but the calculator computes 164" (120" gate + 2" clearance + 42" embed = 164"). The AI is making up its own number.
- [ ] In the AI cut list prompt, add this rule:
  > "For POST lengths: the post must be [height above ground] + [embed depth below frost line]. Chicago frost line is 42 inches minimum. A 10' tall gate needs posts that are at least 10' + 3.5' = 13.5' (162 inches). Do NOT shorten posts. If in doubt, round UP."
- [ ] Better yet: pass the calculator's computed `post_total_length_in` value INTO the AI cut list prompt so Gemini uses the correct number instead of computing its own.

---

## CONSTRAINT ARCHITECTURE

### What NOT to Change
- Do NOT change the pricing engine
- Do NOT change the frontend
- Do NOT change the hardware mapper or hardware sourcer
- Do NOT remove any working features from Prompts 18-21

### Key Files to Modify
- `backend/calculators/cantilever_gate.py` — fence mid-rails, picket material mapping
- `backend/question_trees/data/cantilever_gate.json` — picket_material, picket_top questions
- `backend/question_trees/data/ornamental_fence.json` — same picket options (if applicable)
- `backend/calculators/material_lookup.py` — add missing picket profiles
- `backend/calculators/ai_cut_list.py` — grinding rules, mill scale, welding process, post length passthrough, mid-rail instructions
- `backend/calculators/labor_calculator.py` — grind calibration (indoor vs outdoor), fit-and-tack calibration, paint hours
- `backend/FAB_KNOWLEDGE.md` — grinding rules, mill scale, welding process (if this feeds into Gemini prompts)

### Labor Calibration Guidelines

For a job like CS-2026-0028 (cantilever gate + 28' fence, 10' tall, ~137 pickets, 7 posts, paint finish):

| Process | Current Hours | Target Range | Notes |
|---------|--------------|--------------|-------|
| Layout & Setup | 4.4 | 3-5 | Reasonable |
| Cut & Prep | 10.3 | 8-12 | Reasonable (lots of pickets to cut) |
| Fit & Tack | 1.5 | **3-5** | Way too low — 137 pickets to position/space/tack |
| Full Weld | 12.0 | 10-14 | Reasonable |
| Grind & Clean | 17.8 | **4-6** | Outdoor paint finish, not furniture-grade |
| Finish Prep | 1.0 | 1-2 | Reasonable |
| Paint | 1.5 | **3-4** | Prime + paint, 786 sq ft |
| Hardware Install | 2.0 | 1.5-2.5 | Reasonable |
| Site Install | 12.0 | 10-14 | Reasonable (7 posts + gate + fence) |
| Final Inspection | 0.5 | 0.5-1 | Reasonable |
| **TOTAL** | **63.0** | **55-70** | Current total is actually close but distribution is wrong |

The total hours may end up similar, but the DISTRIBUTION matters:
- Grind goes way down (outdoor → cleanup only)
- Fit & Tack goes up (positioning 137 pickets is meticulous work)
- Paint goes up (prime + paint + dry time)

---

## DECOMPOSITION

### Step 1: Add Picket Material + Top Questions

In `cantilever_gate.json`:
1. Remove the `picket_style` question
2. Add `picket_material` and `picket_top` questions (see Fix 6 above)
3. Update the `infill_type` branches — "Pickets (vertical bars)" should now branch to `["picket_material", "picket_top", "picket_spacing"]`

In `ornamental_fence.json`:
1. Check if it has a picket style/size question — if so, update it with the same options

### Step 2: Add Missing Material Profiles

In `material_lookup.py`, add any missing profiles to `_SEEDED_PRICES`:
- `sq_bar_0.5`, `sq_bar_0.625`, `sq_bar_0.75`
- `rd_bar_0.625`, `rd_bar_0.75`
- `sq_tube_1x1_16ga`

Check what already exists before adding duplicates.

### Step 3: Update Calculator Picket Material Mapping

In `cantilever_gate.py`, wherever picket material is determined, read `fields.get("picket_material", "")` and map to the correct profile key. Create a mapping dict:

```python
PICKET_PROFILES = {
    '1/2" square solid': ("sq_bar_0.5", 0.5, "square bar"),
    '5/8" square solid': ("sq_bar_0.625", 0.625, "square bar"),
    '3/4" square solid': ("sq_bar_0.75", 0.75, "square bar"),
    '1" square tube 16ga': ("sq_tube_1x1_16ga", 1.0, "square tube"),
    '1" square tube 14ga': ("sq_tube_1x1_14ga", 1.0, "square tube"),
    '5/8" round solid': ("rd_bar_0.625", 0.625, "round bar"),
    '3/4" round solid': ("rd_bar_0.75", 0.75, "round bar"),
}
```

Each tuple: (profile_key, picket_width_inches, material_type). Use `picket_width_inches` for spacing calculations.

### Step 4: Add Fence Section Mid-Rails

In `cantilever_gate.py`, wherever fence sections are generated (the code added in Prompt 21), add mid-rail generation:

```python
# Fence mid-rails — same logic as gate mid-rails
fence_mid_rail_count = 0
if height_in > 72:
    fence_mid_rail_count = 2
elif height_in > 48:
    fence_mid_rail_count = 1

if fence_mid_rail_count > 0:
    for label, length_ft in fence_sections:
        mr_length_in = length_ft * 12  # rail spans the section
        mr_total_ft = self.inches_to_feet(mr_length_in) * fence_mid_rail_count
        mr_weight = self.get_weight_lbs(frame_profile, mr_total_ft)
        items.append(self.make_material_item(
            description=f"Fence {label} mid-rail{'s' if fence_mid_rail_count > 1 else ''} — {frame_size} × {fence_mid_rail_count}",
            ...
        ))
        total_weight += mr_weight
        # Additional weld inches: 2 welds per picket per mid-rail × 1.5" each
        total_weld_inches += picket_count_per_section * fence_mid_rail_count * 2 * 1.5
```

### Step 5: Labor Calibration

In `backend/calculators/labor_calculator.py`:

**Grind hours — add indoor/outdoor multiplier:**
```python
# Determine if this is outdoor work (gates, fences, railings with paint finish)
outdoor_job_types = ["swing_gate", "cantilever_gate", "ornamental_fence", "straight_railing",
                     "stair_railing", "balcony_railing", "bollard", "window_security_grate"]
grind_multiplier = 0.35 if job_type in outdoor_job_types else 1.0
grind_hours *= grind_multiplier
```

**Fit & Tack — account for picket positioning time:**
The current calculation likely only counts weld joints. But fit-and-tack for pickets includes:
- Measuring and marking spacing for each picket
- Positioning each picket (checking plumb)
- Tacking top and bottom

Add a picket-specific time estimate:
```python
# Pickets take ~2-3 minutes each to position, check plumb, and tack
picket_count = sum(1 for item in material_items if "picket" in item.get("description", "").lower())
picket_fit_hours = picket_count * 2.5 / 60  # 2.5 min per picket
```

**Paint hours — minimum based on surface area:**
```python
# Outdoor prime + paint: minimum 0.5 hours per 100 sq ft (spray application)
# Plus setup + cleanup + dry time between coats
paint_hours = max(
    current_paint_hours,
    (total_sq_ft / 100) * 0.5 + 1.5  # 1.5 hours for setup/cleanup/dry time
)
```

### Step 6: AI Build Instruction Prompt Enrichment

In `backend/calculators/ai_cut_list.py`, wherever the Gemini prompt is built for fabrication sequence / build instructions, add these rules:

```
FABRICATION RULES (MANDATORY — violating these produces an incorrect and potentially dangerous quote):

1. MILL SCALE: After EVERY cut on tube or bar stock, grind off 1-2 inches of mill scale from each cut end using a flap disc. Mill scale in the weld pool causes porosity. This is not optional.

2. GRINDING FOR OUTDOOR WORK: For gates, fences, and railings that will be painted:
   - DO NOT grind welds smooth or flat. Only clean up spatter, remove sharp edges, and knock down high spots.
   - The only tools are angle grinder + flap disc, and die grinder + roloc disc for tight spots.
   - NEVER mention a file. Files are not used in structural/ornamental fabrication.

3. WELDING PROCESS:
   - All SHOP fabrication: MIG (GMAW) with ER70S-6 wire and 75/25 Ar/CO2 shielding gas.
   - All FIELD/SITE welding: Stick (SMAW) with E7018 electrodes — wind and weather prevent reliable gas shielding on site.
   - Specify the correct process in each step based on whether it's shop or field work.

4. PAINT FOR OUTDOOR STEEL: Always prime first, then topcoat. Two separate steps with dry time between. Do not combine into one step. Minimum coverage: all surfaces including inside corners and undersides.

5. POST LENGTHS: Posts must extend below the frost line. For Chicago, the frost line is 42 inches (3.5 feet) minimum. A 10' tall fence/gate needs posts of at least: 10' above ground + 2" clearance + 42" below grade = ~13.5 feet (162 inches). Do NOT use 36 inches for embed depth in Chicago — that is below code.

6. CROSS BRACES / MID-RAILS: Fences and gates taller than 6 feet MUST have at least one horizontal mid-rail to prevent picket flex. Gates/fences over 8 feet need two mid-rails. Mention these in the assembly steps.

7. CUT LIST DIMENSIONS: Use the EXACT dimensions from the provided cut list. Do not estimate, round, or recalculate dimensions. The cut list is the source of truth.
```

### Step 7: Pass Calculator Values to AI Prompt

When the AI cut list / build instruction generator is called, pass these values from the calculator into the prompt context:
- `post_total_length_in` — exact post length including embed
- `post_concrete_depth_in` — embed depth (42" for Chicago)
- `height_in` — above-ground height
- `mid_rail_count` — how many mid-rails per section
- `fence_sections` — list of (label, length_ft) if applicable
- `job_type` + `finish` — so Gemini knows outdoor vs indoor

---

## EVALUATION DESIGN

### Test 1: Grinding Hours Calibration
Run the same cantilever gate + fence job.
- [ ] Grind & Clean hours are 4-6, not 17+
- [ ] Fit & Tack hours are 3-5, not 1.5
- [ ] Paint hours are 3-4, not 1.5
- [ ] Total labor is in the 55-70 hour range

### Test 2: No Files in Fab Sequence
- [ ] `grep -i "file" output_fab_sequence` returns nothing
- [ ] All deburring/grinding steps mention "angle grinder + flap disc" only

### Test 3: Mill Scale Mentioned
- [ ] Fab sequence includes "remove mill scale" or "grind off mill scale" after cutting steps

### Test 4: Welding Process Correct
- [ ] Shop steps say "MIG" or "GMAW"
- [ ] Field/installation steps say "stick" or "SMAW" 
- [ ] No MIG welding specified for outdoor field installation

### Test 5: Picket Options
Start a new cantilever gate session.
- [ ] Picket material question shows all 7 options
- [ ] Selecting "5/8\" square solid bar" generates materials with `sq_bar_0.625` profile
- [ ] Selecting "1\" square tube 14ga" generates materials with `sq_tube_1x1_14ga` profile

### Test 6: Cross Braces on Fence
Run a 10' tall cantilever gate with 15' fence section.
- [ ] Gate has 2 mid-rails (already working)
- [ ] Fence section has 2 mid-rails (NEW)
- [ ] Mid-rails appear in cut list and materials

### Test 7: Post Depth Correct
- [ ] Posts are 164" (122" above grade + 42" embed), not 156"
- [ ] Fab sequence mentions 42" embed depth, not 36"

### Test 8: Paint Steps
- [ ] Fab sequence has separate prime step and paint step
- [ ] Not combined into "prime & paint in one step"

---

## VERIFICATION CHECKLIST

```bash
# 1. New picket questions exist
python3 -c "
import json
d=json.load(open('backend/question_trees/data/cantilever_gate.json'))
ids=[q['id'] for q in d['questions']]
for f in ['picket_material','picket_top']:
    print(f'{f}: {\"OK\" if f in ids else \"MISSING\"}')"

# 2. Old picket_style removed (or replaced)
python3 -c "
import json
d=json.load(open('backend/question_trees/data/cantilever_gate.json'))
ids=[q['id'] for q in d['questions']]
print('picket_style:', 'STILL EXISTS (remove it!)' if 'picket_style' in ids else 'removed OK')"

# 3. New material profiles exist
python3 -c "
from backend.calculators.material_lookup import MaterialLookup
lookup = MaterialLookup()
for p in ['sq_bar_0.5','sq_bar_0.625','sq_bar_0.75','rd_bar_0.625','rd_bar_0.75','sq_tube_1x1_16ga']:
    price = lookup.get_price_per_foot(p)
    print(f'{p}: \${price}/ft' if price else f'{p}: MISSING')"

# 4. Fab rules in AI prompt
grep -c "mill scale\|MILL SCALE" backend/calculators/ai_cut_list.py
# Expected: >= 1

grep -c "file" backend/calculators/ai_cut_list.py
# Check for "never use a file" type rule

# 5. Grind multiplier exists
grep -c "grind_multiplier\|outdoor" backend/calculators/labor_calculator.py
# Expected: >= 1

# 6. App starts clean
python -c "from backend.main import app; print('OK')"
```

---

## FILES TO MODIFY

- `backend/question_trees/data/cantilever_gate.json` — replace picket_style with picket_material + picket_top
- `backend/question_trees/data/ornamental_fence.json` — update picket options if applicable
- `backend/calculators/cantilever_gate.py` — picket material mapping, fence mid-rails
- `backend/calculators/material_lookup.py` — add missing picket material profiles
- `backend/calculators/labor_calculator.py` — grind calibration, fit-and-tack calibration, paint hours
- `backend/calculators/ai_cut_list.py` — fab rules (mill scale, grinding, welding process, post depth, no files), pass calculator values to prompt
- `backend/FAB_KNOWLEDGE.md` — update with grinding/welding/mill scale rules (if this feeds into prompts)
