# PROMPT 23 — Pre-Punched Channel Cross Braces + AI Path Must Not Skip Calculator Logic

## READ THIS FIRST — INTEGRATION RULES

From CLAUDE.md: Building a module is not done until it's CALLED in the pipeline. After any change, trace the full path from user input → AI generation → validation → PDF output.

**THE FUNDAMENTAL BUG:** The cantilever_gate calculator has TWO paths:
1. **AI path** (lines 75-79): When a description exists, calls `_try_ai_cut_list()` → `_build_from_ai_cuts()` and RETURNS. ALL calculator logic below line 80 is SKIPPED. This means fence posts, fence sections, overhead beam, bottom guide conditional — none of it runs.
2. **Rule-based path** (lines 82+): Contains all the fixes from Prompts 20-22 — fence sections, bottom guide, overhead beam, etc. But this path NEVER executes when there's a description.

This is why CS-2026-0029 is missing fence posts, has no overhead beam, and the AI makes up its own post dimensions. Every time Burton enters a job description (which is EVERY TIME), the AI path runs and bypasses everything we've built.

**THIS MUST BE FIXED FIRST. Everything else in this prompt depends on it.**

---

## PROBLEM STATEMENT

### Problem 1: AI Path Bypasses All Calculator Logic

When `_has_description(fields)` is True (which is always — Burton always types a description), the calculator:
1. Builds hardware (line 70-71) ✅ — this works because it's ABOVE the AI check
2. Calls `_try_ai_cut_list()` → gets Gemini's cut list
3. Calls `_build_from_ai_cuts()` → packages Gemini's cuts into materials
4. RETURNS — never executes fence section generation, bottom guide logic, overhead beam, post depth validation, mid-rail generation, or any other calculator logic

**Fix approach:** After `_build_from_ai_cuts()` returns its result, run a POST-PROCESSING step that adds any calculator-generated items that Gemini missed. Specifically:
- Fence posts (if `adjacent_fence` is answered)
- Fence post concrete
- Overhead beam (if top-hung)
- Fence section mid-rails (if height > 48")
- Validate that post lengths in AI cut list match calculator's computed `post_total_length_in`

### Problem 2: Pre-Punched Channel Cross Braces

Currently, fence and gate mid-rails are plain tube (2×2) that pickets are welded to — same as the frame rails. The industry standard for ornamental fence is **pre-punched U-channel** where pickets slide through punched holes. This is:
- Significantly faster to assemble (self-spacing, no measuring each picket)
- Produces a cleaner, more consistent result
- Standard practice for production fence fabrication

**Stock pre-punched channel sizes (from ACI Supply + Gonzato/Indital catalogs):**

| Channel Size | Hole Size | Fits Picket | Spacing Options | Weight/ft |
|---|---|---|---|---|
| 1" × 1/2" × 1/8" | 9/16" sq | 1/2" sq bar | 4", 5", 6" OC | 0.84 lbs/ft |
| 1-1/2" × 1/2" × 1/8" | 9/16" sq | 1/2" sq bar | 4", 5", 6" OC | 1.12 lbs/ft |
| 1-1/2" × 1/2" × 1/8" | 13/16" sq | 3/4" sq bar | 4", 5", 6" OC | 1.12 lbs/ft |
| 2" × 1" × 1/8" | 13/16" sq | 3/4" sq bar | 6" OC | 1.78 lbs/ft |

**5/8" pickets:** No stock pre-punched channel found online for 5/8" square bar. This is surprising since 5/8" is the most common residential picket. The app should flag this: "5/8" pickets require custom-punched channel (shop fab) or traditional weld-to-rail assembly." Likely exists from specialty suppliers — flag as "verify with local ornamental iron supplier."

### Problem 3: Remaining Issues from CS-2026-0029

- AI fab sequence says "4x4x129.3" posts" but cut list says 164" — Gemini still inventing dimensions
- Step 12 says "four post holes" — should be 7 (3 gate + 4 fence)
- No overhead beam in materials despite top-hung selection
- Field welding in Step 14 doesn't specify stick (SMAW) — still vague "field welding if specified"

---

## ACCEPTANCE CRITERIA

### Fix 1: AI Path Post-Processing (CRITICAL — DO THIS FIRST)

- [ ] After `_build_from_ai_cuts()` returns in `cantilever_gate.py`, DO NOT return immediately. Instead, run a post-processing function that:

  **A) Checks for missing fence posts:**
  - If `fields.get("adjacent_fence")` contains "Yes" AND the AI result's items don't include fence post material with sufficient footage:
    - Calculate required fence posts from `fence_post_count` field (or auto-calculate from fence lengths)
    - Calculate post total length: `height_in + 2 + 42` (above grade + clearance + Chicago frost line)
    - Add fence post material items to the result
    - Add fence post concrete items to the result

  **B) Checks for missing overhead beam (top-hung):**
  - If `is_top_hung` is True AND the AI result's items don't include an overhead beam profile:
    - Calculate overhead beam span (tail section length between carriage posts)
    - Add HSS 4×4×1/4" (or 6×4×1/4" for heavy gates) beam item
    - Add assumption about overhead clearance

  **C) Checks for missing fence mid-rails / cross braces:**
  - If fence sections exist AND height > 48":
    - Calculate mid-rail requirements (1 for 48-72", 2 for >72")
    - Add pre-punched channel items (or standard tube if picket size doesn't match stock channel)
    - The mid-rail material depends on picket size and assembly method (see Fix 2)

  **D) Validates post lengths:**
  - Scan the AI cut list for items containing "post" in the description
  - If any post length < calculator's computed `post_total_length_in`, add an assumption flagging the discrepancy: "⚠️ AI-generated post length ([X]") may be shorter than required. Chicago frost line requires 42" minimum embed depth. Calculated minimum post length: [Y]"."

- [ ] The post-processing function runs on the result dict BEFORE returning it from `calculate()`
- [ ] It adds items to the existing `items` list and assumptions to the `assumptions` list — it does NOT replace the AI-generated content, it SUPPLEMENTS it

**Implementation approach:**

```python
# In cantilever_gate.py calculate() method, replace:
        if self._has_description(fields):
            ai_cuts = self._try_ai_cut_list("cantilever_gate", fields)
            if ai_cuts is not None:
                return self._build_from_ai_cuts(
                    "cantilever_gate", ai_cuts, fields, assumptions,
                    hardware=hardware)

# With:
        if self._has_description(fields):
            ai_cuts = self._try_ai_cut_list("cantilever_gate", fields)
            if ai_cuts is not None:
                result = self._build_from_ai_cuts(
                    "cantilever_gate", ai_cuts, fields, assumptions,
                    hardware=hardware)
                # Post-process: add calculator items that AI missed
                result = self._post_process_ai_result(result, fields, is_top_hung)
                return result
```

Then implement `_post_process_ai_result()` as a method on the cantilever gate calculator.

### Fix 2: Pre-Punched Channel as Mid-Rail/Cross Brace

- [ ] Add a new question to `cantilever_gate.json` (after `picket_material` or `picket_spacing`):

```json
{
    "id": "mid_rail_type",
    "text": "How should mid-rails / cross braces be built?",
    "type": "choice",
    "options": [
        "Pre-punched channel (pickets slide through — fastest, cleanest)",
        "Standard tube rail (pickets welded to flat rail)",
        "Not sure — recommend based on picket size"
    ],
    "required": false,
    "hint": "Pre-punched channel has holes at your picket spacing — pickets slide through and get tack welded. Much faster than positioning each picket individually. Available for 1/2\" and 3/4\" pickets. 5/8\" may require custom punching.",
    "depends_on": null
}
```

- [ ] When "Pre-punched channel" is selected (or "Not sure" and picket size is 1/2" or 3/4"):
  - Mid-rail material is pre-punched U-channel instead of square tube
  - Use the appropriate channel size from the catalog:
    - 1/2" pickets → `punched_channel_1.5x0.5_fits_0.5` (1-1/2" × 1/2" × 1/8")
    - 3/4" pickets → `punched_channel_1.5x0.5_fits_0.75` (1-1/2" × 1/2" × 1/8" with 13/16" holes)
    - 5/8" pickets → flag: "Pre-punched channel for 5/8\" pickets — verify availability with local ornamental iron supplier. If unavailable, custom punch in shop or use standard tube rail."
  - Picket weld inches per mid-rail are REDUCED: tack weld only (0.75" per picket per mid-rail vs 1.5" for full weld to flat rail)
  - Fit-and-tack labor is REDUCED: pre-punched channel self-spaces pickets, so positioning time drops significantly

- [ ] When "Standard tube rail" is selected:
  - Current behavior (2×2 tube mid-rail, pickets welded to it)
  - Full weld inches per picket per mid-rail

- [ ] Add pre-punched channel profiles to `material_lookup.py`:

```python
# Pre-punched U-channel for ornamental fence mid-rails
"punched_channel_1x0.5_fits_0.5": {
    "price_per_ft": 3.50,      # ~$70/20' stick
    "weight_per_ft": 0.84,
    "stock_length_ft": 20,
    "description": "1\" × 1/2\" × 1/8\" punched channel, 1/2\" sq holes"
},
"punched_channel_1.5x0.5_fits_0.5": {
    "price_per_ft": 4.50,      # ~$90/20' stick  
    "weight_per_ft": 1.12,
    "stock_length_ft": 20,
    "description": "1-1/2\" × 1/2\" × 1/8\" punched channel, 1/2\" sq holes"
},
"punched_channel_1.5x0.5_fits_0.75": {
    "price_per_ft": 4.50,      # ~$90/20' stick
    "weight_per_ft": 1.12,
    "stock_length_ft": 20,
    "description": "1-1/2\" × 1/2\" × 1/8\" punched channel, 3/4\" sq holes"
},
"punched_channel_2x1_fits_0.75": {
    "price_per_ft": 7.50,      # ~$150/20' stick
    "weight_per_ft": 1.78,
    "stock_length_ft": 20,
    "description": "2\" × 1\" × 1/8\" punched channel, 3/4\" sq holes"
},
```

Pricing note: ACI Supply lists these at $149.87 for a 20' stick (which is ~$7.50/ft for the 2" channel). The 1-1/2" is typically $80-100/20' stick (~$4-5/ft). Adjust based on local pricing.

### Fix 3: AI Build Instructions — Post Lengths + Field Welding

- [ ] In the Gemini prompt for build instructions / fab sequence, add:
  - Pass the EXACT `post_total_length_in` value: "All posts must be cut to exactly [X] inches ([Y] feet). This includes [height] above ground + 2\" clearance + 42\" frost line embed. Do NOT calculate your own post length."
  - Pass the total post count: "There are [N] total posts: [gate_posts] for the gate + [fence_posts] for the fence sections."
  - "All field/site welding MUST use stick welding (SMAW) with E7018 electrodes. MIG cannot be used outdoors — wind disperses the shielding gas. State 'stick weld (SMAW)' explicitly in all site installation steps."

### Fix 4: Fence Section Validation in AI Cut List Prompt

- [ ] Add to the AI cut list prompt:
  - "This job includes adjacent fence sections: [section details]. You MUST generate cut list items for fence posts, fence rails, and fence pickets in ADDITION to the gate components."
  - "Fence posts are the SAME profile and length as gate posts: [post_profile] × [post_total_length_in] inches."
  - "Each fence section needs: top rail, bottom rail, [mid_rail_count] mid-rail(s), vertical pickets at [spacing] OC."

---

## CONSTRAINT ARCHITECTURE

### What NOT to Change
- Do NOT remove the AI cut list path — it's valuable for generating detailed cut descriptions and notes
- Do NOT change the hardware generation (it already runs before the AI check and works)
- Do NOT modify pricing_engine, pdf_generator, or frontend
- Do NOT change the rule-based calculator path — it's correct, just never reached

### Key Insight
The AI path and calculator path should not be mutually exclusive. The AI generates the cut list (detailed piece descriptions, notes, cutting instructions). The calculator ensures structural requirements are met (fence posts at correct depth, overhead beam for top-hung, mid-rails for tall fences). Both should contribute to the final output.

### Pre-Punched Channel vs Standard Tube
The question tree should make the tradeoff clear:
- Pre-punched = faster assembly, cleaner result, but limited to 1/2" and 3/4" picket sizes
- Standard tube = works with any picket size, but slower and requires more skilled labor
- The labor estimator should apply a multiplier: pre-punched channel reduces fit-and-tack time by ~40% for picket installation

---

## DECOMPOSITION

### Step 1: Fix the AI Path Bypass (CRITICAL — DO FIRST)

In `backend/calculators/cantilever_gate.py`:

1. Change the AI path to capture the result instead of returning immediately
2. Create `_post_process_ai_result(self, result, fields, is_top_hung)` method
3. The method scans the result's `items` list and adds missing components

```python
def _post_process_ai_result(self, result, fields, is_top_hung):
    """
    Supplement AI-generated materials with calculator items that Gemini missed.
    
    The AI generates great cut lists but frequently omits:
    - Fence posts (when adjacent fence sections are requested)
    - Fence post concrete
    - Overhead beams (for top-hung systems)
    - Mid-rails / cross braces (for tall fences)
    
    This method checks for these gaps and adds them.
    """
    from .material_lookup import MaterialLookup
    lookup = MaterialLookup()
    
    items = result.get("items", [])
    assumptions = result.get("assumptions", [])
    total_weight = result.get("total_weight_lbs", 0)
    total_sq_ft = result.get("total_sq_ft", 0)
    total_weld_inches = result.get("weld_linear_inches", 0)
    
    # Parse key dimensions
    height_ft = self.parse_feet(fields.get("height"), default=6.0)
    height_in = self.feet_to_inches(height_ft)
    post_concrete_depth_in = 42.0  # Chicago frost line
    above_grade_in = height_in + 2  # 2" clearance
    post_total_length_in = above_grade_in + post_concrete_depth_in
    
    post_size = fields.get("post_size", "4\" x 4\" square tube")
    post_profile = self._lookup_post(post_size)
    post_price_ft = lookup.get_price_per_foot(post_profile)
    
    # --- A: Fence Posts ---
    adjacent_fence = fields.get("adjacent_fence", "No")
    if "Yes" in str(adjacent_fence):
        fence_post_count = self.parse_int(fields.get("fence_post_count"), default=0)
        
        # Auto-calculate if not specified
        if fence_post_count == 0:
            side_1_ft = self.parse_feet(fields.get("fence_side_1_length"), default=0)
            side_2_ft = self.parse_feet(fields.get("fence_side_2_length"), default=0)
            if side_1_ft > 0:
                fence_post_count += max(1, round(side_1_ft / 7))
            if side_2_ft > 0 and "both" in str(adjacent_fence).lower():
                fence_post_count += max(1, round(side_2_ft / 7))
        
        if fence_post_count > 0:
            # Check if AI already generated enough fence post material
            existing_post_ft = 0
            for item in items:
                if "post" in item.get("description", "").lower() and post_profile in item.get("profile", ""):
                    existing_post_ft += item.get("length_inches", 0) / 12
            
            # Gate posts account for post_count * post_total_length_in
            gate_post_count = self._parse_post_count(fields.get("post_count", "3"))
            gate_post_ft = gate_post_count * self.inches_to_feet(post_total_length_in)
            fence_post_ft_needed = fence_post_count * self.inches_to_feet(post_total_length_in)
            total_post_ft_needed = gate_post_ft + fence_post_ft_needed
            
            # Only add if AI under-generated
            if existing_post_ft < total_post_ft_needed * 0.9:  # 10% tolerance
                fp_length_ft = self.inches_to_feet(post_total_length_in)
                fp_total_ft = fp_length_ft * fence_post_count
                fp_weight = self.get_weight_lbs(post_profile, fp_total_ft)
                
                items.append(self.make_material_item(
                    description=f"Fence posts — {post_size} × {fence_post_count} ({fp_length_ft:.1f} ft each, 42\" embed for frost line)",
                    material_type="structural_tube",
                    profile=post_profile,
                    length_inches=post_total_length_in * fence_post_count,
                    quantity=fence_post_count,
                    unit_price=round(fp_total_ft * post_price_ft, 2),
                    cut_type="square",
                    waste_factor=0.0,
                ))
                total_weight += fp_weight
                
                # Fence post concrete
                import math
                hole_diameter_in = 12
                cu_in_per_hole = math.pi * (hole_diameter_in / 2) ** 2 * post_concrete_depth_in
                total_cu_in = cu_in_per_hole * fence_post_count
                total_cu_yd = total_cu_in / 46656
                
                items.append(self.make_material_item(
                    description=f"Fence post concrete — {fence_post_count} holes × 12\" dia × 42\" deep ({total_cu_yd:.2f} cu yd)",
                    material_type="concrete",
                    profile="concrete_60lb_bag",
                    length_inches=0,
                    quantity=int(total_cu_yd * 40) + 1,
                    unit_price=round(total_cu_yd * 180, 2),
                    cut_type="square",
                    waste_factor=0.0,
                ))
                
                assumptions.append(f"Fence posts: {fence_post_count} × {post_size} at {fp_length_ft:.1f} ft each (42\" embed for Chicago frost line).")
    
    # --- B: Overhead Beam (top-hung) ---
    if is_top_hung:
        has_overhead_beam = any("overhead" in item.get("description", "").lower() or 
                                "beam" in item.get("description", "").lower() 
                                for item in items)
        if not has_overhead_beam:
            clear_width_ft = self.parse_feet(fields.get("clear_width"), default=10.0)
            tail_length_ft = clear_width_ft * 0.5
            beam_span_ft = tail_length_ft + 2  # Extra for connections
            
            beam_profile = "hss_4x4_0.25"
            beam_price_ft = lookup.get_price_per_foot(beam_profile)
            beam_weight = self.get_weight_lbs(beam_profile, beam_span_ft)
            
            items.append(self.make_material_item(
                description=f"Overhead support beam — HSS 4\"×4\"×1/4\" ({beam_span_ft:.1f} ft) for top-mount carriage system",
                material_type="structural_tube",
                profile=beam_profile,
                length_inches=beam_span_ft * 12,
                quantity=1,
                unit_price=round(beam_span_ft * beam_price_ft, 2),
                cut_type="square",
                waste_factor=0.05,
            ))
            total_weight += beam_weight
            assumptions.append(f"Top-hung system: overhead HSS beam spans {beam_span_ft:.1f} ft. Minimum overhead clearance: {self.inches_to_feet(height_in + 6):.1f} ft.")
    
    # --- C: Fence Mid-Rails / Cross Braces ---
    if "Yes" in str(adjacent_fence) and height_in > 48:
        mid_rail_count = 2 if height_in > 72 else 1
        
        # Determine mid-rail material based on picket size and user choice
        mid_rail_type = fields.get("mid_rail_type", "Not sure")
        picket_material = fields.get("picket_material", "")
        
        # Determine if pre-punched channel is appropriate
        use_punched = False
        channel_profile = None
        if "Pre-punched" in str(mid_rail_type) or "Not sure" in str(mid_rail_type):
            if "1/2\"" in picket_material or "1/2" in picket_material:
                use_punched = True
                channel_profile = "punched_channel_1.5x0.5_fits_0.5"
            elif "3/4\"" in picket_material or "3/4" in picket_material:
                use_punched = True
                channel_profile = "punched_channel_1.5x0.5_fits_0.75"
            elif "5/8" in picket_material:
                # 5/8" pre-punched not confirmed as stock item
                assumptions.append("⚠️ 5/8\" pickets: pre-punched channel may require custom shop punching or sourcing from specialty supplier. Verify availability before ordering.")
                use_punched = False
        
        # Check if AI already generated mid-rails for fence sections
        has_fence_mid_rails = any("mid" in item.get("description", "").lower() and 
                                   "fence" in item.get("description", "").lower()
                                   for item in items)
        
        if not has_fence_mid_rails:
            side_1_ft = self.parse_feet(fields.get("fence_side_1_length"), default=0)
            side_2_ft = self.parse_feet(fields.get("fence_side_2_length"), default=0)
            
            fence_sections = []
            if side_1_ft > 0:
                fence_sections.append(("Section 1", side_1_ft))
            if side_2_ft > 0 and "both" in str(adjacent_fence).lower():
                fence_sections.append(("Section 2", side_2_ft))
            
            for label, length_ft in fence_sections:
                if use_punched and channel_profile:
                    mr_total_ft = length_ft * mid_rail_count
                    mr_price = lookup.get_price_per_foot(channel_profile)
                    mr_weight = mr_total_ft * 1.12  # approximate
                    
                    items.append(self.make_material_item(
                        description=f"Fence {label} pre-punched channel mid-rail{'s' if mid_rail_count > 1 else ''} × {mid_rail_count} ({length_ft:.0f}' each)",
                        material_type="channel",
                        profile=channel_profile,
                        length_inches=length_ft * 12 * mid_rail_count,
                        quantity=mid_rail_count,
                        unit_price=round(mr_total_ft * mr_price, 2),
                        cut_type="square",
                        waste_factor=0.05,
                    ))
                    total_weight += mr_weight
                else:
                    # Standard tube mid-rail
                    frame_profile = self._lookup_frame(
                        fields.get("frame_size", "2\" x 2\""),
                        self._normalize_gauge(fields.get("frame_gauge", "11 gauge")))
                    mr_total_ft = length_ft * mid_rail_count
                    mr_price = lookup.get_price_per_foot(frame_profile)
                    mr_weight = self.get_weight_lbs(frame_profile, mr_total_ft)
                    
                    items.append(self.make_material_item(
                        description=f"Fence {label} mid-rail{'s' if mid_rail_count > 1 else ''} — 2\"×2\" × {mid_rail_count} ({length_ft:.0f}' each)",
                        material_type="structural_tube",
                        profile=frame_profile,
                        length_inches=length_ft * 12 * mid_rail_count,
                        quantity=mid_rail_count,
                        unit_price=round(mr_total_ft * mr_price, 2),
                        cut_type="square",
                        waste_factor=0.05,
                    ))
                    total_weight += mr_weight
            
            if fence_sections:
                assumptions.append(f"Fence mid-rails: {mid_rail_count} per section ({'pre-punched channel' if use_punched else 'standard tube'}).")
    
    # --- D: Post Length Validation ---
    cut_list = result.get("cut_list", [])
    for cut in cut_list:
        desc = (cut.get("description", "") + cut.get("piece_name", "")).lower()
        if "post" in desc:
            cut_length = cut.get("length_inches", 0)
            if cut_length > 0 and cut_length < post_total_length_in - 2:
                assumptions.append(
                    f"⚠️ AI post length ({cut_length:.0f}\") may be short. "
                    f"Chicago frost line requires 42\" embed. "
                    f"Minimum post length: {post_total_length_in:.0f}\" "
                    f"({self.inches_to_feet(post_total_length_in):.1f} ft)."
                )
                break  # Only flag once
    
    # Update result
    result["items"] = items
    result["assumptions"] = assumptions
    result["total_weight_lbs"] = total_weight
    result["total_sq_ft"] = total_sq_ft
    result["weld_linear_inches"] = total_weld_inches
    
    return result
```

### Step 2: Add Pre-Punched Channel Profiles to Material Catalog

In `backend/calculators/material_lookup.py`, add these to `_SEEDED_PRICES`:

```python
"punched_channel_1x0.5_fits_0.5": {
    "price_per_ft": 3.50,
    "weight_per_ft": 0.84,
    "stock_length_ft": 20,
},
"punched_channel_1.5x0.5_fits_0.5": {
    "price_per_ft": 4.50,
    "weight_per_ft": 1.12,
    "stock_length_ft": 20,
},
"punched_channel_1.5x0.5_fits_0.75": {
    "price_per_ft": 4.50,
    "weight_per_ft": 1.12,
    "stock_length_ft": 20,
},
"punched_channel_2x1_fits_0.75": {
    "price_per_ft": 7.50,
    "weight_per_ft": 1.78,
    "stock_length_ft": 20,
},
```

### Step 3: Add Mid-Rail Type Question to Tree

In `backend/question_trees/data/cantilever_gate.json`, add after `picket_spacing`:

```json
{
    "id": "mid_rail_type",
    "text": "How should mid-rails / cross braces be built?",
    "type": "choice",
    "options": [
        "Pre-punched channel (pickets slide through — fastest)",
        "Standard tube rail (pickets welded to flat rail)",
        "Not sure — recommend based on picket size"
    ],
    "required": false,
    "hint": "Pre-punched channel has holes at your picket spacing — pickets slide through and get tack welded. Much faster assembly. Stock channels available for 1/2\" and 3/4\" pickets.",
    "depends_on": "infill_type"
}
```

### Step 4: Enrich AI Prompts with Calculator Values

In `backend/calculators/ai_cut_list.py`, wherever the Gemini prompt is built, add these calculated values as context:

```
CALCULATOR-VERIFIED VALUES (use these exactly, do not recalculate):
- Post total length: {post_total_length_in}" ({post_total_length_in/12:.1f} ft) — includes {height_in}" above grade + 2" clearance + 42" Chicago frost line embed
- Gate post count: {gate_post_count}
- Fence post count: {fence_post_count}
- Total posts: {gate_post_count + fence_post_count}
- Fence sections: {fence_section_details}
- Gate mounting: {"Top-hung (overhead beam, no bottom guide)" if is_top_hung else "Standard (bottom guide rail)"}
- Welding: MIG (GMAW) for all SHOP work. Stick (SMAW) with E7018 for all FIELD/SITE work.
```

Pass these values from the calculator to the AI cut list generator. This requires modifying the `_try_ai_cut_list()` call to accept and forward additional context.

### Step 5: Labor Adjustment for Pre-Punched Channel

In `backend/calculators/labor_calculator.py`:

When pre-punched channel is used for mid-rails:
- Fit-and-tack time for pickets reduces by ~30-40% (channel self-spaces pickets)
- Weld inches at mid-rail intersections reduce (tack only vs full fillet)

Add a flag or multiplier:
```python
# Check if pre-punched channel is being used
uses_punched_channel = any("punched_channel" in item.get("profile", "") 
                           for item in material_items)
if uses_punched_channel:
    fit_tack_hours *= 0.65  # 35% reduction — pre-punched self-spaces pickets
```

---

## EVALUATION DESIGN

### Test 1: AI Path Post-Processing (Most Important Test)

Run Burton's exact job description with: top-hung, both fence sides (15' + 13'), 4 fence posts, gravity latch.

- [ ] Quote includes gate materials from AI cut list ✅
- [ ] Quote includes fence posts (4 × 4x4 @ 164") — from post-processing ✅
- [ ] Quote includes fence post concrete — from post-processing ✅
- [ ] Quote includes overhead beam (HSS 4×4×1/4") — from post-processing ✅
- [ ] Quote includes fence mid-rails — from post-processing ✅
- [ ] Hardware is correct (top-mount carriages ×2, stops ×2, latch) ✅
- [ ] Total price > $14,000 (complete job with all components)
- [ ] Assumptions mention Chicago frost line, top-hung clearance, fence posts

### Test 2: Pre-Punched Channel

Run a gate + fence job with 3/4" pickets and "Pre-punched channel" mid-rail selection.

- [ ] Mid-rail material shows as "pre-punched channel" not "2×2 tube"
- [ ] Profile is `punched_channel_1.5x0.5_fits_0.75`
- [ ] Fit-and-tack hours are lower than equivalent job with standard tube mid-rails

### Test 3: 5/8" Pickets with Pre-Punched

Run with 5/8" pickets and "Pre-punched channel" selected.

- [ ] Assumption warns about custom punching / specialty supplier needed
- [ ] Falls back to standard tube mid-rail (or flags for user decision)

### Test 4: Gate Only — No Regression

Run gate-only (no fence sections, standard bottom guide).

- [ ] Post-processing adds nothing (no fence posts, no overhead beam, no fence mid-rails)
- [ ] Quote matches previous gate-only behavior

### Test 5: Post Length Validation

- [ ] If AI cut list generates posts shorter than 164", assumption warns about it
- [ ] Fab sequence mentions correct post length (164" or 13.67')
- [ ] Fab sequence specifies stick welding (SMAW) for site installation steps

---

## FILES TO MODIFY

- `backend/calculators/cantilever_gate.py` — AI path post-processing, `_post_process_ai_result()` method
- `backend/calculators/material_lookup.py` — add pre-punched channel profiles
- `backend/question_trees/data/cantilever_gate.json` — add `mid_rail_type` question
- `backend/calculators/ai_cut_list.py` — pass calculator values to Gemini prompt
- `backend/calculators/labor_calculator.py` — pre-punched channel labor reduction

---

## VERIFICATION CHECKLIST

```bash
# 1. AI path no longer returns immediately
grep -A5 "_try_ai_cut_list" backend/calculators/cantilever_gate.py
# Should show: result = self._build_from_ai_cuts(...) followed by post-processing, NOT direct return

# 2. Post-processing method exists
grep -c "_post_process_ai_result" backend/calculators/cantilever_gate.py
# Expected: >= 2 (definition + call)

# 3. Pre-punched channel profiles exist
python3 -c "
from backend.calculators.material_lookup import MaterialLookup
lookup = MaterialLookup()
for p in ['punched_channel_1.5x0.5_fits_0.5', 'punched_channel_1.5x0.5_fits_0.75']:
    price = lookup.get_price_per_foot(p)
    print(f'{p}: \${price}/ft' if price else f'{p}: MISSING')"

# 4. Mid-rail question exists
python3 -c "
import json
d=json.load(open('backend/question_trees/data/cantilever_gate.json'))
ids=[q['id'] for q in d['questions']]
print('mid_rail_type:', 'OK' if 'mid_rail_type' in ids else 'MISSING')"

# 5. App starts clean
python -c "from backend.main import app; print('OK')"

# 6. Commit and push
git add -A && git commit -m 'Implement Prompt 23: AI path post-processing, pre-punched channel, fence posts fix' && git push
```

**IMPORTANT: The last line of the verification checklist commits and pushes. DO NOT SKIP THIS.**
