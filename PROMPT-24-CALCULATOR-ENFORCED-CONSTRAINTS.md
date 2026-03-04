# PROMPT 24 — Calculator-Enforced Constraints + Real Pricing

## Problem Statement

The AI cut list path (`_build_from_ai_cuts`) returns Gemini's output directly with
no calculator validation. This means:

1. **Gemini picks random materials** — same input produces `sq_bar_0.625` one run,
   `sq_tube_1x1_14ga` the next. The user answered "Pickets (vertical bars)" but
   the question tree never asks WHAT the pickets are made of — so Gemini guesses.

2. **Gemini ignores gate geometry** — user says 12' opening with 15' available for
   tail, Gemini makes a 27' panel (opening + available space) instead of 18'
   (opening × 1.5). The hint text on the UI even says "needs about 18 ft total"
   but Gemini doesn't read hints.

3. **Question tree skips page 2** — `picket_material` and `picket_spacing` are
   NOT in `required_fields`, so once the 8 required fields are answered, the
   frontend calls `_runPipeline()` and branch-activated picket questions never show.

4. **Material prices are wrong** — catalog has made-up averages. We have real
   supplier quotes from D. Wexler & Sons and Osorio Metals Supply (Chicago).

5. **Prompt 23 was never implemented** — the spec was pushed but Claude Code never
   ran it. There is NO `_post_process_ai_result` function. CS-2026-0030 showing
   fence posts was Gemini luck, not enforcement. CS-2026-0031 proves it — different
   run, no fence posts, wrong picket material, wrong gate length.

6. **Field welding still says MIG** — fab sequence says "MIG welder with generator"
   for site work. Should be Stick (SMAW) or self-shielded flux core (FCAW-S).

7. **Overhead beam is oversized** — HSS 6×4×1/4" for a residential gate under 800 lbs.
   And qty=2 when it should be qty=1 spanning between carriage posts.

## Acceptance Criteria

After this prompt is implemented:

1. Running the same cantilever gate quote 5 times produces the same material list
   (profiles, quantities, gate length) — Gemini only controls the DETAILED cut list
   arrangement, not the material selection or quantities.

2. `picket_material` and `picket_spacing` appear as questions in the UI before
   the quote generates.

3. Gate panel length = `clear_width × 1.5` regardless of available tail space.

4. Material prices match real Chicago supplier quotes (Osorio + 10% buffer).

5. Field welding steps say STICK (SMAW) or self-shielded flux core (FCAW-S).

6. Overhead beam is HSS 4×4×1/4" qty=1 for gates under 800 lbs.

7. Fence posts, overhead beam, and mid-rails appear on EVERY run (calculator-
   enforced, not AI-optional).

## Constraint Architecture

### What Gemini Controls (AI decisions)
- Detailed cut list arrangement (which pieces to cut from which sticks)
- Fab sequence step descriptions and tool lists
- Duration estimates for each fab step
- Cut types (miter vs square vs cope) for specific joints

### What the Calculator Controls (hard rules — Gemini cannot override)
- **Gate panel length** = `clear_width_ft × 1.5`
- **Picket material** = from `picket_material` field answer
- **Picket spacing** = from `picket_spacing` field answer
- **Picket count** = `gate_face_width / spacing + 1`
- **Picket height** = `gate_height - frame_allowance` (height_in - 4 for top/bottom rail)
- **Post count, length, and concrete** = from field answers + frost line
- **Overhead beam** = 1 beam, HSS 4×4×1/4" for <800 lbs, HSS 6×4×1/4" for ≥800 lbs
- **Fence posts, rails, mid-rails, pickets** = from field answers
- **Mid-rail count** = 0 for ≤48", 1 for 49-72", 2 for >72"
- **Pre-punched channel for mid-rails** when `mid_rail_type` = pre-punched channel
- **Field welding process** = SMAW or FCAW-S (never MIG/GMAW outdoors)
- **Material prices** = from catalog (Osorio-based)

## Decomposition

### Part 1: Fix Question Tree Required Fields
**File: `backend/question_trees/data/cantilever_gate.json`**

Add `picket_material` and `picket_spacing` to the `required_fields` array.
This ensures the frontend won't skip to pipeline until these are answered.

```json
"required_fields": [
    "clear_width", "height", "frame_material", "frame_gauge",
    "infill_type", "picket_material", "picket_spacing",
    "post_count", "finish", "installation"
]
```

**BUT** — `picket_material` and `picket_spacing` have `"depends_on": "infill_type"`
and are only activated when the branch "Pickets (vertical bars)" fires. If the user
picks "Expanded metal" or "Open frame", these fields will never be answerable and
`is_complete` will never be true.

Fix: make them conditionally required. Update `is_complete` and
`get_completion_status` in `engine.py`:

```python
def is_complete(self, job_type: str, answered_fields: dict) -> bool:
    """Are all required fields answered? Conditional fields that are
    blocked by branching are considered satisfied."""
    tree = self.load_tree(job_type)
    questions = tree.get("questions", [])
    required = self.get_required_fields(job_type)

    # Build branch-activated set
    branch_activated = set()
    for q in questions:
        if q.get("branches"):
            answered_value = answered_fields.get(q["id"])
            if answered_value and answered_value in q["branches"]:
                for activated_id in q["branches"][answered_value]:
                    branch_activated.add(activated_id)

    for field in required:
        if field in answered_fields:
            continue
        # Check if this field is branch-dependent and NOT activated
        q = _find_question(questions, field)
        if q and q.get("depends_on"):
            parent = _find_question(questions, q["depends_on"])
            if parent and parent.get("branches"):
                # This field requires a specific parent answer to activate
                if field not in branch_activated:
                    continue  # Not activated = not required for this path
        return False  # Required, not answered, not branch-blocked
    return True
```

Apply the same logic to `get_completion_status` — don't count branch-blocked
fields as "missing".

### Part 2: Add `_post_process_ai_result` to CantileverGateCalculator
**File: `backend/calculators/cantilever_gate.py`**

After `_build_from_ai_cuts` returns, the calculator must validate and supplement
the result. Change the AI path block (currently around line 75-79):

```python
# Try AI cut list for custom/complex designs
if self._has_description(fields):
    ai_cuts = self._try_ai_cut_list("cantilever_gate", fields)
    if ai_cuts is not None:
        ai_result = self._build_from_ai_cuts(
            "cantilever_gate", ai_cuts, fields, assumptions,
            hardware=hardware)
        return self._post_process_ai_result(ai_result, fields, assumptions)
```

Then add the `_post_process_ai_result` method:

```python
def _post_process_ai_result(self, ai_result: dict, fields: dict,
                             assumptions: list) -> dict:
    """
    Validate and supplement AI-generated material list with calculator-
    enforced items. Gemini handles the detailed cut list arrangement,
    but the calculator enforces quantities, dimensions, and profiles
    for critical structural items.

    Items added here appear in the MATERIALS section (what you buy from
    the supplier) alongside Gemini's consolidated profiles. They also
    appear in the cut list with calculator-verified dimensions.
    """
    items = list(ai_result.get("items", []))
    cut_list = list(ai_result.get("cut_list", []))
    existing_profiles = {item.get("profile") for item in items}

    # --- Parse fields ---
    clear_width_ft = self.parse_feet(fields.get("clear_width"), default=10.0)
    height_ft = self.parse_feet(fields.get("height"), default=6.0)
    clear_width_in = self.feet_to_inches(clear_width_ft)
    height_in = self.feet_to_inches(height_ft)
    total_gate_length_in = clear_width_in * 1.5  # ENFORCED: opening × 1.5

    post_size = fields.get("post_size", "4\" x 4\" square tube")
    post_count = self._parse_post_count(fields.get("post_count", "3 posts (standard)"))
    post_profile_key = self._lookup_post(post_size)
    post_price_ft = lookup.get_price_per_foot(post_profile_key)
    post_concrete_depth_in = 42.0  # Chicago frost line
    if "No" in str(fields.get("post_concrete", "Yes")):
        post_concrete_depth_in = 0.0

    above_grade_in = height_in + 2  # 2" clearance
    post_total_length_in = above_grade_in + post_concrete_depth_in

    bottom_guide_type = fields.get("bottom_guide", "Surface mount guide roller")
    is_top_hung = (
        "No bottom guide" in bottom_guide_type
        or "top-hung" in bottom_guide_type.lower()
    )

    infill_type = fields.get("infill_type", "Pickets (vertical bars)")
    infill_spacing_in = self._parse_spacing(
        fields.get("picket_spacing",
                    fields.get("flat_bar_spacing", "4\" on-center")))
    picket_profile = _resolve_picket_profile(fields, infill_type)

    frame_size = fields.get("frame_size", "2\" x 2\"")
    frame_gauge_raw = fields.get("frame_gauge", "11 gauge (0.120\" - standard for gates)")
    frame_gauge = self._normalize_gauge(frame_gauge_raw)
    frame_key = self._lookup_frame(frame_size, frame_gauge)
    frame_price_ft = lookup.get_price_per_foot(frame_key)

    total_weight = ai_result.get("total_weight_lbs", 0.0)
    total_sq_ft = ai_result.get("total_sq_ft", 0.0)
    total_weld_inches = ai_result.get("weld_linear_inches", 0.0)

    # ========================================================
    # ENFORCE: Gate post count and length
    # ========================================================
    # Check if AI included gate posts with correct dimensions
    has_gate_posts = False
    for item in items:
        desc_lower = item.get("description", "").lower()
        if ("post" in desc_lower and "fence" not in desc_lower
                and item.get("profile") == post_profile_key):
            has_gate_posts = True
            break

    if not has_gate_posts:
        post_total_ft = self.inches_to_feet(post_total_length_in) * post_count
        post_weight = self.get_weight_lbs(post_profile_key, post_total_ft)

        items.append(self.make_material_item(
            description=f"Gate posts — {post_size} × {post_count} "
                        f"({self.inches_to_feet(post_total_length_in):.1f} ft each, "
                        f"{post_concrete_depth_in:.0f}\" embed for Chicago frost line)",
            material_type="square_tubing",
            profile=post_profile_key,
            length_inches=post_total_length_in,
            quantity=post_count,
            unit_price=round(self.inches_to_feet(post_total_length_in) * post_price_ft, 2),
            cut_type="square",
            waste_factor=0.0,
        ))
        cut_list.append({
            "description": f"Structural posts for the cantilever gate",
            "piece_name": "gate_post",
            "group": "posts",
            "material_type": "mild_steel",
            "profile": post_profile_key,
            "length_inches": post_total_length_in,
            "quantity": post_count,
            "cut_type": "square",
            "cut_angle": 90.0,
            "weld_process": "mig",
            "weld_type": "fillet",
            "notes": f"Given post length: {post_total_length_in:.0f}\" "
                     f"({above_grade_in:.0f}\" above grade + "
                     f"{post_concrete_depth_in:.0f}\" embed). "
                     f"Chicago frost line requires 42\" minimum embed.",
        })
        total_weight += post_weight
        assumptions.append(
            f"Gate posts: {post_count} × {post_size} at "
            f"{self.inches_to_feet(post_total_length_in):.1f} ft each "
            f"({post_concrete_depth_in:.0f}\" embed for Chicago frost line)."
        )

    # ========================================================
    # ENFORCE: Post concrete
    # ========================================================
    has_concrete = any("concrete" in item.get("description", "").lower()
                       and "fence" not in item.get("description", "").lower()
                       for item in items)
    if not has_concrete and post_concrete_depth_in > 0:
        import math
        hole_diameter_in = 12.0
        cu_in_per_hole = math.pi * (hole_diameter_in / 2) ** 2 * post_concrete_depth_in
        total_cu_in = cu_in_per_hole * post_count
        total_cu_yd = total_cu_in / 46656.0
        concrete_price = lookup.get_unit_price("concrete_per_cuyd")

        items.append(self.make_material_item(
            description=f"Gate post concrete — {post_count} holes × "
                        f"{hole_diameter_in:.0f}\" dia × {post_concrete_depth_in:.0f}\" deep",
            material_type="concrete",
            profile="concrete_footing",
            length_inches=post_concrete_depth_in,
            quantity=post_count,
            unit_price=round(total_cu_yd * concrete_price / post_count, 2),
            cut_type="n/a",
            waste_factor=0.0,
        ))

    # ========================================================
    # ENFORCE: Overhead support beam (top-hung only)
    # ========================================================
    if is_top_hung:
        has_overhead = any("overhead" in item.get("description", "").lower()
                           or "support beam" in item.get("description", "").lower()
                           for item in items)
        if not has_overhead:
            estimated_gate_weight = total_weight
            if estimated_gate_weight < 800:
                beam_profile = "hss_4x4_0.25"
                beam_desc = "HSS 4×4×1/4\""
            else:
                beam_profile = "hss_6x4_0.25"
                beam_desc = "HSS 6×4×1/4\""
            # ONE beam spanning between carriage posts
            beam_length_in = total_gate_length_in + 24  # +12" overhang each side
            beam_length_ft = self.inches_to_feet(beam_length_in)
            beam_price_ft = lookup.get_price_per_foot(beam_profile)
            beam_weight = self.get_weight_lbs(beam_profile, beam_length_ft)
            if beam_weight == 0.0:
                beam_weight = beam_length_ft * 12.0

            items.append(self.make_material_item(
                description=f"Overhead support beam — {beam_desc} "
                            f"({beam_length_ft:.1f} ft, qty 1)",
                material_type="hss_structural_tube",
                profile=beam_profile,
                length_inches=beam_length_in,
                quantity=1,  # ONE beam
                unit_price=round(beam_length_ft * beam_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            cut_list.append({
                "description": f"Overhead {beam_desc} beam for top-hung cantilever gate",
                "piece_name": "overhead_beam",
                "group": "structure",
                "material_type": "mild_steel",
                "profile": beam_profile,
                "length_inches": beam_length_in,
                "quantity": 1,
                "cut_type": "square",
                "cut_angle": 90.0,
                "weld_process": "mig",
                "weld_type": "fillet",
                "notes": f"Beam spans {total_gate_length_in:.0f}\" gate length + "
                         f"24\" overhang = {beam_length_in:.0f}\". "
                         f"Supports roller carriages and gate travel.",
            })
            total_weight += beam_weight
            min_clearance_in = height_in + 6
            assumptions.append(
                f"Top-hung system: 1 × {beam_desc} overhead beam "
                f"spans {beam_length_ft:.1f} ft. "
                f"Minimum overhead clearance: {min_clearance_in:.0f}\" "
                f"({self.inches_to_feet(min_clearance_in):.1f} ft)."
            )

    # ========================================================
    # ENFORCE: Adjacent fence sections
    # ========================================================
    adjacent_fence = fields.get("adjacent_fence", "No")
    if "Yes" in str(adjacent_fence):
        # Check if AI already included fence posts
        has_fence_posts = any("fence" in item.get("description", "").lower()
                              and "post" in item.get("description", "").lower()
                              for item in items)
        if not has_fence_posts:
            fence_result = self._generate_fence_sections(
                fields, height_in, infill_type, infill_spacing_in,
                frame_key, frame_size, frame_gauge, frame_price_ft,
                post_profile_key, post_price_ft, post_concrete_depth_in,
            )
            items.extend(fence_result["items"])
            total_weight += fence_result["weight"]
            total_sq_ft += fence_result["sq_ft"]
            total_weld_inches += fence_result["weld_inches"]
            assumptions.extend(fence_result["assumptions"])

        # Check if fence mid-rails are present
        has_fence_midrails = any("mid-rail" in item.get("description", "").lower()
                                  and "fence" in item.get("description", "").lower()
                                  for item in items)
        if not has_fence_midrails and height_in > 48:
            # Add mid-rails for each fence section
            fence_mid_rail_count = 2 if height_in > 72 else 1
            side_1_ft = self.parse_feet(fields.get("fence_side_1_length"), default=0.0)
            side_2_ft = self.parse_feet(fields.get("fence_side_2_length"), default=0.0)

            # Use pre-punched channel if available, otherwise frame tube
            mid_rail_profile = frame_key  # default to frame tube
            mid_rail_price = frame_price_ft
            mid_rail_label = f"tube × {fence_mid_rail_count}"

            # Check if pre-punched channel should be used
            mid_rail_type = fields.get("mid_rail_type", "")
            if "punched" in str(mid_rail_type).lower():
                # Map picket size to channel profile
                picket_size = _resolve_picket_profile(fields, infill_type)
                if "0.5" in picket_size and "0.625" not in picket_size:
                    mid_rail_profile = "punched_channel_1.5x0.5_fits_0.5"
                elif "0.625" in picket_size:
                    mid_rail_profile = "punched_channel_1.5x0.5_fits_0.625"
                elif "0.75" in picket_size:
                    mid_rail_profile = "punched_channel_1.5x0.5_fits_0.75"
                mid_rail_price = lookup.get_price_per_foot(mid_rail_profile)
                mid_rail_label = f"pre-punched channel × {fence_mid_rail_count}"

            for side_name, length_ft in [("Section 1", side_1_ft), ("Section 2", side_2_ft)]:
                if length_ft <= 0:
                    continue
                length_in = self.feet_to_inches(length_ft)
                mid_rail_total_ft = self.inches_to_feet(length_in) * fence_mid_rail_count

                items.append(self.make_material_item(
                    description=f"Fence {side_name} mid-rails — {mid_rail_label}",
                    material_type="square_tubing",
                    profile=mid_rail_profile,
                    length_inches=length_in,
                    quantity=fence_mid_rail_count,
                    unit_price=round(length_ft * mid_rail_price, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_TUBE,
                ))

    # ========================================================
    # ENFORCE: Validate AI gate length — override if wrong
    # ========================================================
    enforced_gate_length_in = clear_width_in * 1.5
    assumptions.append(
        f"Cantilever gate panel: {self.inches_to_feet(enforced_gate_length_in):.1f} ft total "
        f"({clear_width_ft:.0f} ft opening × 1.5 ratio). "
        f"Counterbalance tail: {self.inches_to_feet(enforced_gate_length_in - clear_width_in):.1f} ft."
    )

    # ========================================================
    # ENFORCE: Post length validation
    # ========================================================
    min_post_length_in = height_in + 2 + 42  # above grade + clearance + frost line
    assumptions.append(
        f"Fence posts: {post_size} at {self.inches_to_feet(min_post_length_in):.1f} ft each "
        f"({min_post_length_in:.0f}\" = {height_in:.0f}\" + 2\" clearance + 42\" embed "
        f"for Chicago frost line)."
    )

    # Rebuild the result with enforced items
    ai_result["items"] = items
    ai_result["cut_list"] = cut_list
    ai_result["total_weight_lbs"] = total_weight
    ai_result["total_sq_ft"] = total_sq_ft
    ai_result["weld_linear_inches"] = total_weld_inches
    ai_result["assumptions"] = assumptions
    return ai_result
```

### Part 3: Inject Calculator Constraints into Gemini Prompt
**File: `backend/calculators/ai_cut_list.py`**

In `_build_field_context` for cantilever_gate, add hard constraints that
Gemini must follow. These go BEFORE the cut list generation so Gemini
builds from correct dimensions:

Add this block inside the `if job_type == "cantilever_gate":` section,
after the existing POST DIMENSIONS block:

```python
# Gate length constraint
clear_width = fields.get("clear_width", "")
if clear_width:
    try:
        cw_ft = float(str(clear_width).split()[0])
        gate_total_ft = cw_ft * 1.5
        tail_ft = gate_total_ft - cw_ft
        blocks.append(
            "GATE PANEL LENGTH (HARD CONSTRAINT — DO NOT CHANGE):\n"
            "  Total gate panel = %.1f ft (%.0f\")\n"
            "  Gate face (opening) = %.1f ft (%.0f\")\n"
            "  Counterbalance tail = %.1f ft (%.0f\")\n"
            "  Formula: opening × 1.5. The 'available space' field is the MAXIMUM, "
            "not the required tail length. Never make the tail longer than 50%% of the opening."
            % (gate_total_ft, gate_total_ft * 12,
               cw_ft, cw_ft * 12,
               tail_ft, tail_ft * 12)
        )
    except (ValueError, IndexError):
        pass

# Picket material constraint
picket_material = fields.get("picket_material", "")
infill_type = fields.get("infill_type", "")
if "Picket" in str(infill_type):
    from .cantilever_gate import _resolve_picket_profile
    profile = _resolve_picket_profile(fields, infill_type)
    spacing = fields.get("picket_spacing", "4\" on-center")
    blocks.append(
        "PICKET MATERIAL (HARD CONSTRAINT — DO NOT CHANGE):\n"
        "  Profile: %s\n"
        "  Spacing: %s\n"
        "  Use EXACTLY this profile for all pickets. Do NOT substitute "
        "square tube, round tube, or any other material for pickets."
        % (profile, spacing)
    )

# Overhead beam constraint
bottom_guide = str(fields.get("bottom_guide", ""))
if "No bottom guide" in bottom_guide or "top-hung" in bottom_guide.lower():
    blocks.append(
        "OVERHEAD BEAM (HARD CONSTRAINT):\n"
        "  Quantity: 1 (ONE beam spanning between the two rear carriage posts)\n"
        "  Profile: hss_4x4_0.25 for gates under 800 lbs, hss_6x4_0.25 for heavier\n"
        "  Length: gate panel length + 24\" (12\" overhang each side)\n"
        "  Do NOT use qty 2. It is ONE continuous beam."
    )
```

Also add to the FIELD WELDING block (replace the existing one):

```python
# Field welding context
installation = str(fields.get("installation", ""))
if "install" in installation.lower() and "no" not in installation.lower():
    blocks.append(
        "FIELD WELDING (HARD CONSTRAINT):\n"
        "  ALL site/field welds = Stick (SMAW, E7018) or self-shielded flux core (FCAW-S).\n"
        "  NEVER specify MIG (GMAW) or TIG (GTAW) for outdoor field work.\n"
        "  Wind disperses shielding gas — cannot maintain gas coverage outdoors.\n"
        "  MIG/TIG is for SHOP FABRICATION ONLY.\n"
        "  In the fab sequence, any step done on-site must specify stick or flux core."
    )
```

### Part 4: Update Material Prices
**File: `backend/calculators/material_lookup.py`**

Replace `PRICE_PER_FOOT` with real Chicago supplier pricing (Osorio Metals
Supply + 10% buffer, verified against D. Wexler & Sons quotes 2024-2025):

```python
# FALLBACK PRICES — Real Chicago-area pricing
# Source: Osorio Metals Supply + D. Wexler & Sons quotes (2024-2025)
# Buffer: +10% over Osorio baseline for market fluctuation
# Last updated: March 2026
PRICE_PER_FOOT = {
    # Square tube — Osorio + 10%
    "sq_tube_1x1_11ga": 1.27,      # Osorio $1.15/ft (Jan 2025)
    "sq_tube_1x1_14ga": 0.95,      # Estimated from 11ga ratio
    "sq_tube_1x1_16ga": 0.80,      # Estimated
    "sq_tube_1.25x1.25_11ga": 1.51, # Osorio $1.37/ft (Jan 2025)
    "sq_tube_1.5x1.5_11ga": 1.74,  # Osorio $1.58/ft (Oct 2024)
    "sq_tube_1.5x1.5_14ga": 1.22,  # Osorio $1.11/ft (Jan 2025)
    "sq_tube_1.5x1.5_16ga": 1.00,  # Estimated
    "sq_tube_1.75x1.75_11ga": 2.64, # Osorio $2.40/ft (Jan 2025)
    "sq_tube_2x2_11ga": 2.75,      # Osorio $2.49-2.88/ft (2024) +10%
    "sq_tube_2x2_14ga": 1.67,      # Osorio $1.52/ft (receipt)
    "sq_tube_2x2_16ga": 1.40,      # Estimated from 14ga ratio
    "sq_tube_2.5x2.5_11ga": 3.86,  # Osorio $3.51/ft (Nov 2023) +10%
    "sq_tube_3x3_11ga": 5.61,      # Osorio $5.10/ft (Feb 2025) +10%
    "sq_tube_3x3_7ga": 8.25,       # Osorio $7.50/ft (Feb 2025, 1/4" wall) +10%
    "sq_tube_4x4_11ga": 4.95,      # Extrapolated: ~5.41 lb/ft × $0.83/lb (Osorio avg)
    "sq_tube_6x6_7ga": 14.96,      # Osorio $13.60/ft (Jun 2024) +10%
    # Rectangular tube
    "rect_tube_2x4_11ga": 3.76,    # Wexler $3.42/ft (Jun 2024) +10%
    "rect_tube_2x3_11ga": 3.10,    # Estimated between 2x2 and 2x4
    "rect_tube_2x1_11ga": 2.00,    # Estimated
    # Round tube
    "round_tube_1.5_11ga": 5.07,   # Wexler $4.61/ft DOM (Jan 2025) +10%
    "round_tube_1.5_14ga": 3.85,   # Estimated
    "round_tube_1.25_14ga": 3.30,  # Estimated
    "round_tube_2_11ga": 6.05,     # Estimated
    # Square bar / pickets — extrapolated from tube $/lb ratios
    # Solid bar ~$0.90-1.00/lb at Osorio; sq bar is cheap commodity stock
    "sq_bar_0.5": 0.75,            # 0.85 lb/ft × $0.90/lb ≈ $0.77 → round
    "sq_bar_0.625": 1.10,          # 1.33 lb/ft × $0.90/lb ≈ $1.20 → conservative
    "sq_bar_0.75": 1.55,           # 1.91 lb/ft × $0.90/lb ≈ $1.72 → +buffer
    "sq_bar_1.0": 2.75,            # 3.40 lb/ft × $0.90/lb ≈ $3.06 → conservative
    # Round bar
    "round_bar_0.5": 0.70,         # 0.67 lb/ft × $0.95/lb
    "round_bar_0.625": 1.00,       # 1.04 lb/ft × $0.95/lb
    "round_bar_0.75": 1.40,        # 1.50 lb/ft × $0.95/lb
    # Flat bar — Osorio + 10%
    "flat_bar_1x0.125": 0.90,      # Estimated
    "flat_bar_1x0.25": 1.41,       # Osorio $1.28/ft (Jan 2025, 1/4"×2") +10%
    "flat_bar_1.5x0.25": 1.66,     # Osorio $1.51/ft (Jan 2025, 3/16"×3") +10%
    "flat_bar_1x0.1875": 1.10,     # Estimated
    "flat_bar_0.75x0.25": 1.10,    # Estimated
    "flat_bar_2x0.25": 2.80,       # Estimated
    "flat_bar_3x0.25": 4.57,       # Osorio $4.15/ft (Nov 2023, 1/4"×5") +10%
    # Angle iron — Osorio + 10%
    "angle_1.5x1.5x0.125": 1.06,   # Osorio $0.96/ft (receipt) +10%
    "angle_2x2x0.125": 1.42,       # Osorio $1.29/ft (receipt) +10%
    "angle_2x2x0.1875": 2.02,      # Osorio $1.84/ft (Jan 2025) +10%
    "angle_2x2x0.25": 2.50,        # Estimated from 3/16" ratio
    "angle_3x3x0.1875": 2.61,      # Osorio $2.37/ft (Feb 2025) +10%
    # Channel
    "channel_6x8.2": 8.20,         # No supplier data — keep estimate
    "channel_4x5.4": 5.40,         # No supplier data — keep estimate
    # Pre-punched channel (fence mid-rails)
    "punched_channel_1x0.5_fits_0.5": 3.85,      # Estimated + 10%
    "punched_channel_1.5x0.5_fits_0.5": 4.95,    # Estimated + 10%
    "punched_channel_1.5x0.5_fits_0.625": 4.95,  # Estimated + 10%
    "punched_channel_1.5x0.5_fits_0.75": 4.95,   # Estimated + 10%
    "punched_channel_2x1_fits_0.75": 8.25,        # Estimated + 10%
    # Pipe (posts)
    "pipe_4_sch40": 6.60,          # No Osorio data — estimated + 10%
    "pipe_6_sch40": 13.20,         # No Osorio data — estimated + 10%
    "pipe_3.5_sch40": 5.50,
    "pipe_3_sch40": 4.40,
    # HSS (structural tube)
    "hss_4x4_0.25": 8.25,          # Extrapolated from 3×3×1/4 ($7.50) + size premium
    "hss_6x4_0.25": 12.00,         # No supplier data — keep estimate
}
```

### Part 5: Add `mid_rail_type` Question
**File: `backend/question_trees/data/cantilever_gate.json`**

Add a question for mid-rail type, activated when adjacent fence is selected.
Insert after `fence_infill_match`:

```json
{
    "id": "mid_rail_type",
    "text": "What type of mid-rails for the fence sections?",
    "type": "choice",
    "options": [
        "Pre-punched channel (pickets slide through — faster assembly)",
        "Standard tube (weld each picket to rail)"
    ],
    "required": false,
    "hint": "Pre-punched U-channel is industry standard for fence mid-rails. Pickets slide through pre-drilled holes for self-spacing. Dramatically faster assembly.",
    "depends_on": "adjacent_fence",
    "branches": null
}
```

Also add `"mid_rail_type"` to the branch arrays for `adjacent_fence`:
```json
"Yes — fence on both sides": ["fence_side_1_length", "fence_side_2_length", "fence_post_count", "fence_infill_match", "mid_rail_type"],
"Yes — fence on one side only": ["fence_side_1_length", "fence_post_count", "fence_infill_match", "mid_rail_type"]
```

### Part 6: Add `hss_4x4_0.25` Profile to AI Profile List
**File: `backend/calculators/ai_cut_list.py`**

Update `_PROFILE_GROUPS["hss"]`:
```python
"hss": "  HSS (structural tube): hss_4x4_0.25, hss_6x4_0.25",
```
(Already correct — just verify it's there.)

### Part 7: Update Build Instructions Field Welding Rule
**File: `backend/calculators/ai_cut_list.py`**

The build instructions prompt rule 13 already says "Field/site welding = Stick
(SMAW, E7018)". Strengthen it to include flux core:

Find:
```
13. WELDING PROCESS: Shop fabrication = MIG (GMAW). Field/site welding = Stick (SMAW, E7018). Never specify MIG for outdoor field installation (wind disrupts gas shielding). Never use "file" for deburring — use "flap disc" or "die grinder."
```

Replace with:
```
13. WELDING PROCESS: Shop fabrication = MIG (GMAW). Field/site welding = Stick (SMAW, E7018) or self-shielded flux core (FCAW-S). NEVER specify MIG (GMAW) or TIG (GTAW) for outdoor field installation — wind disperses shielding gas. Dual-shield flux core is strongest/fastest for structural field work but not needed for fence/gate. Never use "file" for deburring — use "flap disc" or "die grinder."
```

## Evaluation Design

### Verification Steps (run after implementation)

1. **Question tree test:**
   ```bash
   # Start a new cantilever gate session, select "Pickets (vertical bars)"
   # for infill → picket_material and picket_spacing questions MUST appear
   # before the quote generates.
   # Start another session, select "Expanded metal" for infill → 
   # picket questions should NOT appear, and quote should still generate.
   ```

2. **Determinism test:**
   ```bash
   # Generate the same cantilever gate quote 3 times with identical inputs:
   # 12' wide, 10' tall, 2x2 11ga frame, 5/8" square bar pickets,
   # 4" spacing, top-hung, 3 posts, paint, full install,
   # fence both sides 15' + 13', 4 fence posts
   # ALL THREE quotes must have:
   #   - Picket profile = sq_bar_0.625 (not sq_tube_anything)
   #   - Gate panel ≈ 18' (not 27')
   #   - Fence posts present
   #   - Overhead beam present, qty=1
   #   - Post length ≈ 164"
   ```

3. **Price verification:**
   ```bash
   grep -n "sq_tube_2x2_11ga" backend/calculators/material_lookup.py
   # Should show 2.75 (not 3.50)
   grep -n "sq_bar_0.625" backend/calculators/material_lookup.py
   # Should show 1.10
   grep -n "hss_4x4_0.25" backend/calculators/material_lookup.py
   # Should show 8.25
   ```

4. **Field welding verification:**
   ```bash
   # In the generated PDF, search for "MIG" in site install steps
   # Should find ZERO instances of MIG/GMAW in any field/site step
   # Should find "Stick (SMAW)" or "flux core (FCAW-S)" instead
   ```

5. **Overhead beam verification:**
   ```bash
   # In the generated PDF, overhead beam should be:
   #   - HSS 4×4×1/4" (not 6×4)
   #   - Quantity: 1 (not 2)
   #   - Length: ~19.5 ft (18' gate + 24" overhang)
   ```

## File Change Summary

| File | Changes |
|------|---------|
| `backend/question_trees/data/cantilever_gate.json` | Add `picket_material`, `picket_spacing` to `required_fields`; add `mid_rail_type` question; update `adjacent_fence` branches |
| `backend/question_trees/engine.py` | Update `is_complete` and `get_completion_status` for conditional required fields |
| `backend/calculators/cantilever_gate.py` | Add `_post_process_ai_result` method; change AI path to call it |
| `backend/calculators/ai_cut_list.py` | Add gate length, picket material, overhead beam, field welding constraints to `_build_field_context`; update rule 13 |
| `backend/calculators/material_lookup.py` | Replace `PRICE_PER_FOOT` with Osorio-based pricing + 10% buffer |

## What This Does NOT Fix (Future Prompts)

- Pre-punched channel profile recognition in AI output (Gemini still uses "channel")
- Grind hours regression (10.3 hrs in CS-2026-0031 vs 5.8 in CS-2026-0029)
- Labor rate should be $145/hr everywhere (some show $125/hr)
- Square bar pricing needs real supplier verification (extrapolated, not from quotes)
- Seeded prices from `data/seeded_prices.json` not yet populated
- Reprocess/regenerate button should preserve original field answers
