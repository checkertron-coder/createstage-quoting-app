# PROMPT 20 — Compound Jobs, Top-Mount Cantilever, Bottom Guide Logic

## READ THIS FIRST — INTEGRATION RULES

From CLAUDE.md: Building a module is not done until it's CALLED in the pipeline. After any change, trace the full path from user input → AI generation → validation → PDF output. If your new code isn't in that path, it's not done.

**PATTERN TO AVOID:** Prompt 13 built 5,243 lines of structured knowledge + validation that was never wired in. DO NOT repeat this. Every function you create or modify MUST be called in the actual request flow. Verify with grep after every change.

---

## PROBLEM STATEMENT

A real customer quote exposed three systemic gaps in the pipeline. A fabricator described this job:

> "I am trying to build a fence, in the back of an alley, that connects the two sides of the properties fence together. The one side of the fence is 15' long, there is 12' opening, then there is a 13' fence. There will be 4 fence posts, two per each side of each fence portion. The customer wants a Cantilever gate, with the rollers on the top so there is nothing to obscure the bottom."

**What the app produced:** A cantilever gate quote with 3 posts, bottom guide rail, and zero fence sections. The 28 linear feet of fence (15' + 13') was completely dropped. The customer's explicit request for top-mount rollers was ignored — the calculator always generates a bottom guide rail regardless of the user's answer.

**Root cause analysis:**

1. **The system only supports single job types.** `detect_job_type()` picks ONE type (cantilever_gate). But this job is cantilever_gate + ornamental_fence. There is no concept of compound jobs, add-on sections, or multi-component quotes. The 28' of fence with 4 posts simply vanishes.

2. **The cantilever_gate calculator ignores the `bottom_guide` question tree answer.** The question tree asks "Bottom guide rail type?" with options including "No bottom guide (top-hung only)". The calculator (`cantilever_gate.py` lines 281-294) ALWAYS generates a bottom guide rail — it never reads `fields.get("bottom_guide")`. Additionally, selecting "top-hung only" has structural implications: posts need an overhead beam/track, roller carriages mount differently, and the fabrication sequence changes.

3. **AI cut list path drops question tree context.** When a description exists, `cantilever_gate.py` line 60-63 sends the job to Gemini via `_try_ai_cut_list()`. Gemini is told it's a "cantilever_gate" and generates only gate components. The fence sections in the description are outside Gemini's scope because it's been told "you're generating a cantilever gate cut list."

---

## ACCEPTANCE CRITERIA

### Issue 1: Compound Job Support — Adjacent Fence Sections

- [ ] Add a new question to the `cantilever_gate.json` question tree: `"adjacent_fence"` — "Are there fence sections connecting to this gate?"
  - Options: "Yes — fence on one side", "Yes — fence on both sides", "No — gate only"
  - When "Yes" is selected, branch to follow-up questions:
    - `fence_side_1_length`: "Length of fence section 1? (feet)"
    - `fence_side_2_length`: "Length of fence section 2? (feet)" (only if both sides)
    - `fence_post_count`: "How many fence posts total? (not counting gate posts)"
    - `fence_infill_match`: "Should the fence match the gate's infill style?" — Yes (default) / No — different style
- [ ] The `cantilever_gate.py` calculator reads these new fields and generates additional material items for the fence sections:
  - Fence rails (top + bottom) from the same frame material/size as the gate
  - Fence pickets/infill matching the gate's infill type (or different if specified)
  - Fence posts from the same post size as the gate
  - Post concrete for fence posts
- [ ] Fence materials appear as separate line items in the materials table (clearly labeled "Fence Section 1" / "Fence Section 2")
- [ ] Fence labor is estimated and added to the labor section
- [ ] The PDF shows fence sections as distinct items (not lumped into gate materials)
- [ ] If "No — gate only" is selected, no fence materials are generated (no behavior change from current)

### Issue 2: Bottom Guide / Top-Mount Logic

- [ ] The cantilever_gate calculator reads `fields.get("bottom_guide", "")` and respects the user's selection:
  - **"Surface mount guide roller"** (current default behavior): Generate the bottom guide rail material + guide roller hardware. This is what the calculator does today — keep this path.
  - **"Embedded track (flush with ground)"**: Generate a heavier guide channel (C4x5.4 or similar) instead of angle iron. Add an assumption about concrete channel pour.
  - **"No bottom guide (top-hung only)"**: Do NOT generate any bottom guide rail material or hardware. Instead:
    - Add an overhead support beam to the materials (a heavy tube or I-beam spanning between the two carriage posts, mounted at the top of the posts)
    - The roller carriages mount to this overhead beam (not at ground level)
    - Add an assumption: "Top-hung system — requires overhead clearance of [gate height + 6 inches] minimum"
    - Adjust the post specifications: top-hung posts may need to be heavier gauge or larger size since they're supporting the gate weight at the top
- [ ] The fabrication sequence (AI-generated build instructions) must reflect the mounting style. Add the mounting style to the Gemini prompt context so it generates appropriate steps.
- [ ] Hardware: For top-hung, the roller carriages should be listed as "Top-mount roller carriage" in the description (same pricing is fine for now, but the description must be accurate)

### Issue 3: AI Cut List Context Enrichment

- [ ] When `_try_ai_cut_list()` is called from any calculator, pass the FULL question tree answers (all fields) to the Gemini prompt, not just the description
- [ ] Specifically, the Gemini prompt for the AI cut list must include:
  - The user's original description (already included)
  - Key answered fields: dimensions, material choices, infill type, mounting style, adjacent fence info
  - A note about what the calculator has already determined (e.g., "This is a top-hung cantilever gate with adjacent fence sections")
- [ ] This ensures Gemini generates cuts for the COMPLETE job, including fence sections, and respects structural choices like top-mount vs bottom-mount
- [ ] The `_build_decorative_stock_prep()` and `_build_gemini_prompt()` methods in `ai_cut_list.py` should accept and incorporate these additional fields

---

## CONSTRAINT ARCHITECTURE

### What NOT to Change
- Do NOT modify the pricing engine — it already handles any materials/hardware the calculators produce
- Do NOT change the PDF generator — it renders whatever materials/labor the pipeline outputs
- Do NOT modify the hardware mapper from Prompt 19 — it works as a fallback; the cantilever calculator generates its own hardware
- Do NOT change the question tree engine — it already supports `depends_on` and `branches` for conditional questions
- Do NOT remove any existing cantilever_gate calculator logic — only ADD the fence section and bottom guide branches

### What to Be Careful With
- **Fence labor estimation:** Fence sections are simpler than a gate — mostly cut, weld pickets, install posts. Don't apply the same labor multipliers. A rough guide: 1 hour of cutting + welding per 4 linear feet of fence.
- **Weld inches for fence:** Calculate separately from the gate. Each picket gets 2 welds (top + bottom), each about 1.5" long. Rail-to-post connections are 4 welds per joint at ~3" each.
- **AI cut list scope:** When Gemini gets the enriched context, it needs clear instructions: "Generate cuts for BOTH the cantilever gate AND the adjacent fence sections." Otherwise it may still only generate gate cuts.
- **Question tree ordering:** The new fence questions should come AFTER the gate-specific questions but BEFORE finish/installation. Logically: gate specs → fence add-ons → finish → installation.
- **Top-hung overhead beam:** This is typically a W4x13 or W6x9 steel beam, or for residential, a 4x4x1/4" HSS tube. Size it based on gate weight. For gates under 800 lbs, 4x4x1/4" HSS is adequate. For heavier gates, use W6x9 or W8x10. Add this to the material catalog if not already present.
- **Stock lengths:** Fence rails (2x2 tube) come in 20' or 24' sticks. A 15' fence section uses one stick with waste. A 13' section uses one stick. Don't consolidate fence rail footage with gate rail footage — they're separate pieces on site.

### Performance Constraints
- The new question tree questions add 2-4 questions max when fence is selected — this is acceptable
- The additional material calculations are pure math — no performance impact
- The enriched Gemini prompt will be longer but within token limits

---

## DECOMPOSITION

### Step 1: Update Cantilever Gate Question Tree

In `backend/question_trees/data/cantilever_gate.json`, add the following questions AFTER `site_access` and BEFORE `decorative_elements`:

```json
{
    "id": "adjacent_fence",
    "text": "Are there fence sections connecting to this gate?",
    "type": "choice",
    "options": [
        "Yes — fence on both sides",
        "Yes — fence on one side only",
        "No — gate only"
    ],
    "required": false,
    "hint": "Many gate installations include connecting fence sections. We can quote the complete job.",
    "depends_on": null,
    "branches": {
        "Yes — fence on both sides": ["fence_side_1_length", "fence_side_2_length", "fence_post_count", "fence_infill_match"],
        "Yes — fence on one side only": ["fence_side_1_length", "fence_post_count", "fence_infill_match"]
    }
},
{
    "id": "fence_side_1_length",
    "text": "Length of fence section 1? (in feet)",
    "type": "number",
    "required": true,
    "hint": "Measure the total length of this fence run from the gate post to the end/corner.",
    "depends_on": "adjacent_fence"
},
{
    "id": "fence_side_2_length",
    "text": "Length of fence section 2? (in feet)",
    "type": "number",
    "required": true,
    "hint": "Measure the total length of the second fence run.",
    "depends_on": "adjacent_fence"
},
{
    "id": "fence_post_count",
    "text": "How many fence posts? (not counting the gate posts)",
    "type": "number",
    "required": false,
    "hint": "Typical: one post every 6-8 feet. For a 15' run, 2 posts is standard (one mid-span, one end). We'll calculate if you're not sure.",
    "depends_on": "adjacent_fence"
},
{
    "id": "fence_infill_match",
    "text": "Should the fence infill match the gate?",
    "type": "choice",
    "options": [
        "Yes — match the gate exactly",
        "No — simpler/different infill for fence"
    ],
    "required": false,
    "hint": "Matching infill looks best but costs more. Simpler infill (like vertical pickets at wider spacing) can save on material and labor.",
    "depends_on": "adjacent_fence"
}
```

### Step 2: Fix Bottom Guide Logic in Calculator

In `backend/calculators/cantilever_gate.py`, find the section that generates the bottom guide rail (currently around lines 281-294). Replace it with conditional logic:

```python
# 6. Bottom guide rail — CONDITIONAL based on user selection
bottom_guide = fields.get("bottom_guide", "Surface mount guide roller")

if "No bottom guide" in bottom_guide or "top-hung" in bottom_guide.lower():
    # TOP-HUNG SYSTEM: No bottom guide rail.
    # Instead, add an overhead support beam between carriage posts.
    overhead_span_in = total_gate_length_in * 0.6  # Tail section span
    overhead_beam_ft = self.inches_to_feet(overhead_span_in) + 2  # Extra for weld connections

    # Size beam based on estimated gate weight
    if estimated_gate_weight < 800:
        beam_profile = "hss_4x4_0.25"
        beam_desc = "4\"×4\"×1/4\" HSS"
    else:
        beam_profile = "hss_6x4_0.25"  # or W6x9 if available
        beam_desc = "6\"×4\"×1/4\" HSS"

    beam_price_ft = lookup.get_price_per_foot(beam_profile)
    beam_weight = self.get_weight_lbs(beam_profile, overhead_beam_ft)

    items.append(self.make_material_item(
        description=f"Overhead support beam — {beam_desc} ({overhead_beam_ft:.1f} ft)",
        material_type="structural_tube",
        profile=beam_profile,
        length_inches=overhead_span_in + 24,
        quantity=1,
        unit_price=round(overhead_beam_ft * beam_price_ft, 2),
        cut_type="square",
        waste_factor=self.WASTE_TUBE,
    ))
    total_weight += beam_weight
    assumptions.append(f"Top-hung system: overhead beam spans {overhead_beam_ft:.1f} ft between carriage posts. Minimum overhead clearance required: {self.inches_to_feet(height_in + 6):.1f} ft.")

elif "Embedded" in bottom_guide:
    # EMBEDDED TRACK: heavier channel instead of angle iron
    guide_rail_in = total_gate_length_in + 24
    guide_rail_ft = self.inches_to_feet(guide_rail_in)
    guide_profile = "channel_c4x5.4"  # Add to catalog if missing
    guide_price_ft = lookup.get_price_per_foot(guide_profile)
    guide_weight = self.get_weight_lbs(guide_profile, guide_rail_ft)

    items.append(self.make_material_item(
        description=f"Embedded guide channel — C4×5.4 ({guide_rail_ft:.1f} ft)",
        material_type="channel",
        profile=guide_profile,
        length_inches=guide_rail_in,
        quantity=1,
        unit_price=round(guide_rail_ft * guide_price_ft, 2),
        cut_type="square",
        waste_factor=self.WASTE_TUBE,
    ))
    total_weight += guide_weight
    assumptions.append(f"Embedded guide track: requires concrete channel pour {guide_rail_ft:.1f} ft long × 6\" wide × 6\" deep.")

else:
    # SURFACE MOUNT (default) — existing behavior
    guide_rail_in = total_gate_length_in + 24
    guide_rail_ft = self.inches_to_feet(guide_rail_in)
    guide_price_ft = lookup.get_price_per_foot("angle_2x2x0.25")
    guide_weight = self.get_weight_lbs("angle_2x2x0.25", guide_rail_ft)

    items.append(self.make_material_item(
        description=f"Bottom guide rail — 2\"×2\"×1/4\" angle ({guide_rail_ft:.1f} ft)",
        material_type="angle_iron",
        profile="angle_2x2x0.25",
        length_inches=guide_rail_in,
        quantity=self.linear_feet_to_pieces(guide_rail_ft),
        unit_price=round(guide_rail_ft * guide_price_ft, 2),
        cut_type="square",
        waste_factor=self.WASTE_TUBE,
    ))
    total_weight += guide_weight
```

Also update the roller carriage description for top-hung:

```python
# 7. Roller carriages (hardware)
carriage_count = 2
if "Heavy" in roller_type or "heavy" in roller_type:
    carriage_key = "roller_carriage_heavy"
else:
    carriage_key = "roller_carriage_standard"

# Adjust description for top-hung systems
is_top_hung = "No bottom guide" in bottom_guide or "top-hung" in bottom_guide.lower()
carriage_desc = "Top-mount roller carriage" if is_top_hung else "Roller carriage"
carriage_desc += f" — {'heavy duty' if 'heavy' in carriage_key else 'standard'}"

hardware.append(self.make_hardware_item(
    description=carriage_desc,
    quantity=carriage_count,
    options=lookup.get_hardware_options(carriage_key),
))
```

### Step 3: Add Fence Section Generation to Calculator

In `backend/calculators/cantilever_gate.py`, AFTER the gate hardware section and BEFORE the `return self.make_material_list(...)`, add fence section logic:

```python
# ── FENCE SECTIONS (if adjacent fence is requested) ──
adjacent_fence = fields.get("adjacent_fence", "No")
if "Yes" in str(adjacent_fence):
    fence_sections = []

    side_1_ft = float(fields.get("fence_side_1_length", 0) or 0)
    side_2_ft = float(fields.get("fence_side_2_length", 0) or 0)

    if side_1_ft > 0:
        fence_sections.append(("Section 1", side_1_ft))
    if side_2_ft > 0 and "both" in str(adjacent_fence).lower():
        fence_sections.append(("Section 2", side_2_ft))

    # Fence posts
    fence_post_count = int(fields.get("fence_post_count", 0) or 0)
    if fence_post_count == 0:
        # Auto-calculate: 1 end post + 1 per 6-8 feet
        for label, length in fence_sections:
            fence_post_count += 1 + max(1, int(length / 7))

    if fence_post_count > 0:
        fence_post_in = height_in + post_concrete_depth_in
        fence_post_total_ft = self.inches_to_feet(fence_post_in) * fence_post_count
        fp_price = lookup.get_price_per_foot(post_profile)
        fp_weight = self.get_weight_lbs(post_profile, fence_post_total_ft)

        items.append(self.make_material_item(
            description=f"Fence posts — {post_size} × {fence_post_count} ({self.inches_to_feet(fence_post_in):.1f} ft each)",
            material_type="structural_tube",
            profile=post_profile,
            length_inches=fence_post_in * fence_post_count,
            quantity=fence_post_count,
            unit_price=round(fence_post_total_ft * fp_price, 2),
            cut_type="square",
            waste_factor=0.0,
        ))
        total_weight += fp_weight

        # Fence post concrete
        if post_needs_concrete:
            fp_concrete_cu_yd = self._post_concrete_volume(fence_post_count, post_concrete_depth_in)
            items.append(self.make_material_item(
                description=f"Fence post concrete — {fence_post_count} holes",
                material_type="concrete",
                profile="concrete_60lb_bag",
                length_inches=0,
                quantity=int(fp_concrete_cu_yd * 40) + 1,  # ~40 bags per cu yd
                unit_price=round(fp_concrete_cu_yd * 180, 2),  # ~$180/cu yd
                cut_type="square",
                waste_factor=0.0,
            ))

    # Fence rails and infill per section
    fence_match_gate = "match" in str(fields.get("fence_infill_match", "Yes")).lower() or \
                       "Yes" in str(fields.get("fence_infill_match", "Yes"))

    for label, length_ft in fence_sections:
        length_in = length_ft * 12

        # Top and bottom rails (same material as gate frame)
        rail_total_ft = self.inches_to_feet(length_in) * 2  # top + bottom
        rail_price = lookup.get_price_per_foot(frame_profile)
        rail_weight = self.get_weight_lbs(frame_profile, rail_total_ft)

        items.append(self.make_material_item(
            description=f"Fence {label} rails — {frame_size} {frame_gauge} top + bottom ({length_ft:.0f}' run)",
            material_type="structural_tube",
            profile=frame_profile,
            length_inches=length_in * 2,
            quantity=2,
            unit_price=round(rail_total_ft * rail_price, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += rail_weight

        # Fence infill (pickets matching gate, or simplified)
        if fence_match_gate and infill_type in ("Vertical pickets", "Pickets"):
            fence_picket_spacing = float(fields.get("picket_spacing", "4").replace('"', '').split()[0] or 4)
            fence_picket_count = int(length_in / (infill_bar_width + fence_picket_spacing)) + 1
            fence_picket_height = height_in - (frame_size_in * 2)  # Inside frame height
            fence_picket_total_ft = self.inches_to_feet(fence_picket_height) * fence_picket_count

            infill_price = lookup.get_price_per_foot(infill_profile)
            infill_weight = self.get_weight_lbs(infill_profile, fence_picket_total_ft)

            items.append(self.make_material_item(
                description=f"Fence {label} pickets — {infill_desc} × {fence_picket_count} pcs ({length_ft:.0f}' run)",
                material_type="bar_stock",
                profile=infill_profile,
                length_inches=fence_picket_height * fence_picket_count,
                quantity=fence_picket_count,
                unit_price=round(fence_picket_total_ft * infill_price, 2),
                cut_type="square",
                waste_factor=self.WASTE_BAR,
            ))
            total_weight += infill_weight
            total_sq_ft += self.sq_ft_from_dimensions(length_in, height_in)

            # Weld inches for fence pickets: 2 welds per picket × 1.5" each
            total_weld_inches += fence_picket_count * 2 * 1.5
        else:
            # Non-matching or non-picket infill — use simplified picket calc
            fence_picket_count = int(length_in / 6) + 1  # ~6" spacing
            fence_picket_height = height_in - (frame_size_in * 2)
            fence_picket_total_ft = self.inches_to_feet(fence_picket_height) * fence_picket_count
            infill_price = lookup.get_price_per_foot(infill_profile)
            infill_weight = self.get_weight_lbs(infill_profile, fence_picket_total_ft)

            items.append(self.make_material_item(
                description=f"Fence {label} infill — {infill_desc} × {fence_picket_count} pcs ({length_ft:.0f}' run)",
                material_type="bar_stock",
                profile=infill_profile,
                length_inches=fence_picket_height * fence_picket_count,
                quantity=fence_picket_count,
                unit_price=round(fence_picket_total_ft * infill_price, 2),
                cut_type="square",
                waste_factor=self.WASTE_BAR,
            ))
            total_weight += infill_weight
            total_sq_ft += self.sq_ft_from_dimensions(length_in, height_in)
            total_weld_inches += fence_picket_count * 2 * 1.5

        # Rail-to-post weld inches: 4 welds per joint × 3" each × (posts per section)
        posts_per_section = max(2, int(length_ft / 7) + 1)
        total_weld_inches += posts_per_section * 4 * 3

    assumptions.append(f"Adjacent fence sections included: {' + '.join(f'{l[1]:.0f} ft' for l in fence_sections)} with {fence_post_count} fence posts.")
```

**IMPORTANT NOTES FOR IMPLEMENTATION:**

The code above references several variables that must already be in scope from the calculator's existing logic:
- `height_in` — gate height
- `post_concrete_depth_in` — from post concrete calc
- `post_profile` — e.g. "sq_tube_4x4_11ga"
- `post_size` — e.g. "4\"×4\""
- `frame_size`, `frame_gauge`, `frame_profile`, `frame_size_in` — from frame material setup
- `infill_type`, `infill_profile`, `infill_desc`, `infill_bar_width` — from infill setup
- `post_needs_concrete` — boolean from post concrete section

Read the existing calculator code carefully to understand where these variables are defined and make sure the fence section code runs AFTER all of them are set. The fence section MUST come after the infill section so infill variables are available.

### Step 4: Enrich AI Cut List Prompt with Full Context

In `backend/calculators/ai_cut_list.py`, find the `_build_gemini_prompt()` method (or wherever the Gemini prompt is assembled for AI cut lists). Add a section that includes key answered fields:

```python
# Build context from answered fields for richer AI generation
field_context_parts = []
if fields.get("bottom_guide"):
    field_context_parts.append(f"Mounting style: {fields['bottom_guide']}")
if fields.get("adjacent_fence") and "Yes" in str(fields.get("adjacent_fence")):
    parts = []
    if fields.get("fence_side_1_length"):
        parts.append(f"Side 1: {fields['fence_side_1_length']}' long")
    if fields.get("fence_side_2_length"):
        parts.append(f"Side 2: {fields['fence_side_2_length']}' long")
    field_context_parts.append(f"Adjacent fence sections: {', '.join(parts)}")
if fields.get("roller_carriages"):
    field_context_parts.append(f"Roller carriage: {fields['roller_carriages']}")

field_context = ""
if field_context_parts:
    field_context = "\n\nADDITIONAL CONTEXT FROM CUSTOMER ANSWERS:\n" + "\n".join(f"- {p}" for p in field_context_parts)
    field_context += "\n\nIMPORTANT: Generate cuts for the COMPLETE job including any adjacent fence sections. Label fence cuts clearly (e.g., 'Fence Section 1 — top rail')."
```

Then append `field_context` to the Gemini prompt string before sending it.

### Step 5: Add Missing Material Profiles to Catalog

Check `backend/calculators/material_lookup.py` for these profiles and add them if missing:
- `hss_4x4_0.25` — 4"×4"×1/4" wall HSS (for overhead beam)
- `hss_6x4_0.25` — 6"×4"×1/4" wall HSS (for heavy overhead beam)
- `channel_c4x5.4` — C4×5.4 channel (for embedded guide track)

Use real-world pricing:
- HSS 4x4x1/4: ~$12-15/ft, 12.21 lbs/ft, 24' sticks
- HSS 6x4x1/4: ~$14-18/ft, 14.53 lbs/ft, 24' sticks
- C4x5.4: ~$5-7/ft, 5.4 lbs/ft, 20' sticks

---

## EVALUATION DESIGN

### Test 1: The Original Job (Full Regression)

Run this exact description through the app:

> "I am trying to build a fence, in the back of an alley, that connects the two sides of the properties fence together. The one side of the fence is 15' long, there is 12' opening, then there is a 13' fence. There will be 4 fence posts, two per each side of each fence portion. The customer wants a Cantilever gate, with the rollers on the top so there is nothing to obscure the bottom."

**Verify:**
- [ ] Job type detected as `cantilever_gate` (correct)
- [ ] Question tree asks about adjacent fence sections
- [ ] When answered "Yes — fence on both sides" with 15' and 13' lengths:
  - Materials include fence rails for both sections
  - Materials include fence pickets for both sections
  - Materials include 4 fence posts (separate from gate posts)
  - Fence post concrete is included
- [ ] When "No bottom guide (top-hung only)" is selected:
  - NO bottom guide rail appears in materials
  - An overhead support beam appears instead
  - Roller carriages described as "Top-mount roller carriage"
  - Assumption mentions minimum overhead clearance
- [ ] Job description shows on the quote (Prompt 19 feature — verify still works)
- [ ] Hardware is not $0 (Prompt 19 feature — verify still works)
- [ ] Total price is higher than the gate-only quote ($11,949) due to fence sections

### Test 2: Gate Only (No Regression)

Run a cantilever gate quote with "No — gate only" for adjacent fence.

**Verify:**
- [ ] No fence materials appear
- [ ] Quote looks identical to pre-Prompt-20 behavior
- [ ] All existing features still work

### Test 3: Bottom Guide Options

Run three cantilever gate quotes with each bottom_guide option:

**A) Surface mount (default):**
- [ ] Bottom guide rail appears (angle iron) — same as current behavior

**B) Embedded track:**
- [ ] Channel appears instead of angle iron
- [ ] Assumption mentions concrete channel pour

**C) Top-hung only:**
- [ ] No bottom guide rail
- [ ] Overhead beam appears
- [ ] Roller carriages say "Top-mount"
- [ ] Posts may be sized up for top-hung weight

### Test 4: AI Cut List Enrichment

Run the original job description with fence sections and verify the AI-generated detailed cut list includes:
- [ ] Gate frame members (existing)
- [ ] Gate pickets (existing)
- [ ] Fence section rails (NEW)
- [ ] Fence section pickets (NEW)
- [ ] Items labeled clearly (e.g., "Fence Section 1 — top rail")

### Test 5: Edge Cases

- [ ] Fence with 0' length on side 2 — should not generate materials for side 2
- [ ] Fence with no post count specified — auto-calculates reasonable number
- [ ] Very long fence (50'+) — verify material quantity and stock length calculations
- [ ] Top-hung gate with fence sections — both features work together

---

## FILES TO MODIFY (Summary)

**Question Trees:**
- `backend/question_trees/data/cantilever_gate.json` — add adjacent_fence questions + bottom_guide already exists (no change needed to the question itself)

**Backend Calculators:**
- `backend/calculators/cantilever_gate.py` — bottom guide conditional logic + fence section generation
- `backend/calculators/material_lookup.py` — add hss_4x4_0.25, hss_6x4_0.25, channel_c4x5.4 if missing
- `backend/calculators/ai_cut_list.py` — enrich Gemini prompt with field context

**No Frontend Changes Required** — the frontend already renders whatever materials/hardware the pipeline produces. The new fence materials and overhead beam will appear automatically in the materials table.

---

## VERIFICATION CHECKLIST (run after ALL changes)

```bash
# 1. Question tree loads without errors
python -c "import json; json.load(open('backend/question_trees/data/cantilever_gate.json')); print('OK')"

# 2. New fields are in the question tree
python -c "
import json
d = json.load(open('backend/question_trees/data/cantilever_gate.json'))
ids = [q['id'] for q in d['questions']]
for f in ['adjacent_fence', 'fence_side_1_length', 'fence_side_2_length', 'fence_post_count', 'fence_infill_match']:
    status = 'OK' if f in ids else 'MISSING'
    print(f'{f}: {status}')
"

# 3. Bottom guide field is read in calculator
grep -n "bottom_guide" backend/calculators/cantilever_gate.py

# 4. Fence section generation exists
grep -n "adjacent_fence\|fence_section\|fence_side" backend/calculators/cantilever_gate.py

# 5. AI cut list enrichment exists
grep -n "adjacent_fence\|field_context\|ADDITIONAL CONTEXT" backend/calculators/ai_cut_list.py

# 6. New material profiles exist (if added)
python -c "
from backend.calculators.material_lookup import MaterialLookup
lookup = MaterialLookup()
for p in ['hss_4x4_0.25', 'channel_c4x5.4']:
    price = lookup.get_price_per_foot(p)
    print(f'{p}: \${price}/ft' if price else f'{p}: MISSING')
"

# 7. Integration test — run full cantilever_gate calculate endpoint
# (manual test via the app UI)
```


## ONE MORE THING

This prompt fixes the cantilever_gate specifically, but the COMPOUND JOB problem is systemic. Other job types will have similar issues:
- Stair railing + landing railing + grab bars
- Driveway gate + pedestrian gate + fence
- Fire table + wind guard + gas line

A future prompt should address a generic "add-on" or "multi-component" system. For now, solving it for the most common case (gate + fence) is the right move. We'll generalize later.
