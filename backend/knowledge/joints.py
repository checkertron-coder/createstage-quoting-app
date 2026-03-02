"""
Joint types — every common fabrication joint with prep, weld process,
filler, time estimates, and consumable rates.

Sources: AWS D1.1 (Structural Welding Code — Steel), AWS D1.3 (Sheet Steel),
Lincoln Electric Procedure Handbook of Arc Welding, AISC Steel Construction
Manual 15th Ed, Blodgett's "Design of Welded Structures."

Shop-specific overrides marked with # SHOP: CreateStage
"""

from typing import Optional

# ---------------------------------------------------------------------------
# JOINT REGISTRY
# ---------------------------------------------------------------------------
# Each joint has:
#   name              — human-readable name
#   category          — fillet | groove | corner | lap | plug | tee | edge
#   aws_symbol        — AWS welding symbol reference
#   description       — what this joint looks like physically
#   prep_required     — surface/edge prep before welding
#   weld_process      — recommended process(es) by material
#   filler            — recommended filler by material
#   position_notes    — position considerations
#   min_fillet_chart  — AWS D1.1 minimum fillet size by base metal thickness
#   time_per_inch     — time in minutes per linear inch of weld by process
#   consumable_rates  — per linear inch consumption rates (keys into consumables.py)
#   strength_notes    — practical strength info
#   common_in         — job types where this joint appears
#   notes             — practical shop notes
#   NEVER             — things that must NEVER appear with this joint
# ---------------------------------------------------------------------------

JOINTS = {

    # ===================================================================
    # FILLET WELDS
    # ===================================================================

    "fillet_tee": {
        "name": "Fillet Weld — Tee Joint",
        "category": "fillet",
        "aws_symbol": "T-joint fillet",
        "description": (
            "One member perpendicular to another, welded along the intersection. "
            "Most common joint in structural and ornamental fabrication."
        ),
        "prep_required": {
            "mild_steel": "Clean mill scale at joint area. Tight fit-up (< 1/16 inch gap).",
            "stainless": "Degrease with acetone. Remove ALL contamination. Dedicated stainless tools.",
            "aluminum": "Wire brush with stainless brush (dedicated). Remove oxide immediately before welding.",
        },
        "weld_process": {
            "mild_steel_structural": "mig",
            "mild_steel_decorative": "tig",
            "stainless": "tig",
            "aluminum": "tig",
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
            "mild_steel_tig": "ER70S-2",
            "stainless_304": "ER308L",
            "stainless_316": "ER316L",
            "dissimilar_mild_to_stainless": "ER309L",
            "aluminum_6061": "4043 (cosmetic) or 5356 (structural)",
            "aluminum_5052": "5356 (NEVER use 4043 on 5052)",
        },
        "position_notes": (
            "1F (flat) is default. Horizontal (2F) adds 20% time. "
            "Vertical (3F) adds 40%. Overhead (4F) adds 70%."
        ),
        # AWS D1.1 Table 5.8 — minimum fillet weld size
        "min_fillet_chart": {
            "base_metal_up_to_0.25": 0.125,    # 1/8 inch fillet min
            "base_metal_0.25_to_0.5": 0.1875,   # 3/16 inch fillet min
            "base_metal_0.5_to_0.75": 0.25,     # 1/4 inch fillet min
            "base_metal_over_0.75": 0.3125,      # 5/16 inch fillet min
        },
        "fillet_rule_of_thumb": (
            "Fillet leg = 3/4 x thinner plate thickness. "
            "3/16 inch fillet sufficient for most furniture on 1 inch tube. "
            "Overwelding = wasted time + heat distortion."
        ),
        "time_per_inch": {
            "mig_fillet_3_16": 0.06,    # minutes per inch — ~4 sec/inch
            "mig_fillet_1_4": 0.08,     # slower for larger fillet
            "mig_fillet_5_16": 0.12,    # multi-pass
            "tig_fillet_mild": 0.15,    # ~10 sec/inch
            "tig_fillet_stainless": 0.20,  # ~12 sec/inch + purge considerations
            "tig_fillet_aluminum": 0.18,   # AC mode, faster puddle but tricky
            "stick_fillet_7018": 0.10,
            "stick_fillet_6011": 0.08,
        },
        "consumable_rates": {
            "mig_wire_lb_per_inch_3_16": 0.004,    # ~60 in/lb for 3/16 fillet
            "mig_wire_lb_per_inch_1_4": 0.007,      # ~140 in/lb — heavier deposit
            "mig_gas_cfh": 35,                        # cubic feet per hour flow rate
            "tig_filler_lb_per_inch": 0.003,          # manual feed, less deposit
            "tig_gas_cfh": 20,                         # argon flow rate
            "tig_tungsten_per_hour": 0.1,              # fraction of electrode per hour
        },
        "strength_notes": (
            "Throat = 0.707 x leg. A 3/16 fillet has 0.133 inch throat. "
            "Allowable shear on E70 filler = 21,000 PSI on throat area. "
            "A 3/16 fillet x 1 inch long carries 2,793 lbs shear capacity."
        ),
        "common_in": [
            "furniture_table", "furniture_other", "straight_railing",
            "stair_railing", "cantilever_gate", "swing_gate",
            "ornamental_fence", "structural_frame", "sign_frame",
            "window_security_grate", "utility_enclosure",
        ],
        "notes": (
            "Default joint for 90% of shop fabrication. "
            "Always tack all joints before continuous welding."
        ),
        "NEVER": [],
    },

    "fillet_lap": {
        "name": "Fillet Weld — Lap Joint",
        "category": "fillet",
        "aws_symbol": "Lap joint fillet",
        "description": (
            "Two overlapping members welded along the edge of the top member. "
            "Common for gussets, stiffeners, and plate reinforcement."
        ),
        "prep_required": {
            "mild_steel": "Clean joint area. Ensure tight contact (no gap between plates).",
            "stainless": "Degrease both mating surfaces.",
        },
        "weld_process": {
            "mild_steel": "mig",
            "stainless": "tig",
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
            "stainless_304": "ER308L",
        },
        "position_notes": "Usually welded flat (1F). Both edges accessible for double-sided weld.",
        "min_fillet_chart": {
            "base_metal_up_to_0.25": 0.125,
            "base_metal_0.25_to_0.5": 0.1875,
        },
        "fillet_rule_of_thumb": "Same as tee joint. Weld both sides when possible for balanced heat.",
        "time_per_inch": {
            "mig_fillet_3_16": 0.06,
            "tig_fillet_mild": 0.15,
        },
        "consumable_rates": {
            "mig_wire_lb_per_inch_3_16": 0.004,
            "mig_gas_cfh": 35,
        },
        "strength_notes": (
            "Minimum overlap = 5x thinner plate thickness (AWS D1.1). "
            "Weld both sides when structurally required."
        ),
        "common_in": [
            "structural_frame", "trailer_fab", "repair_structural",
            "offroad_bumper", "rock_slider",
        ],
        "notes": "If single-sided, weld the loaded side. Double-sided is standard for structural.",
        "NEVER": [
            "single-sided lap on structural loaded joint",
        ],
    },

    "fillet_corner_inside": {
        "name": "Fillet Weld — Inside Corner",
        "category": "fillet",
        "aws_symbol": "Corner joint inside fillet",
        "description": (
            "Two members meeting at an inside corner (like the inside of a box). "
            "Welded with fillet along the interior angle."
        ),
        "prep_required": {
            "mild_steel": "Clean joint area. Fit tight — gap control critical for corner aesthetics.",
            "stainless": "Degrease. Back-purge if full penetration required.",
        },
        "weld_process": {
            "mild_steel": "mig",
            "stainless": "tig",
            "thin_sheet": "tig",
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
            "mild_steel_tig": "ER70S-2",
            "stainless_304": "ER308L",
        },
        "position_notes": "Access can be limited on interior corners. May require die grinder cleanup.",
        "min_fillet_chart": {
            "base_metal_up_to_0.25": 0.125,
        },
        "fillet_rule_of_thumb": "Inside corners often ground flush for appearance on enclosures and boxes.",
        "time_per_inch": {
            "mig_fillet": 0.08,     # slightly slower due to access
            "tig_fillet": 0.18,     # tight corners require more care
        },
        "consumable_rates": {
            "mig_wire_lb_per_inch": 0.004,
            "mig_gas_cfh": 35,
        },
        "strength_notes": "Full-length fillet on inside corners provides adequate strength for most enclosures.",
        "common_in": [
            "utility_enclosure", "led_sign_custom", "furniture_other",
        ],
        "notes": "Sheet metal corners (16ga and thinner) — TIG to prevent burn-through.",
        "NEVER": [],
    },

    # ===================================================================
    # GROOVE (BUTT) WELDS
    # ===================================================================

    "butt_square": {
        "name": "Square Groove Butt Weld",
        "category": "groove",
        "aws_symbol": "B-U2a (square groove)",
        "description": (
            "Two members butted end-to-end with no bevel. "
            "Suitable for thin material where full penetration is achieved without prep."
        ),
        "prep_required": {
            "mild_steel": "Square cut ends. 0-1/16 inch gap for root opening.",
            "stainless": "Square cut, clean, tight gap. Back-purge with argon.",
        },
        "weld_process": {
            "mild_steel": "mig (material <= 3/16 inch), tig (thinner)",
            "stainless": "tig",
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
            "mild_steel_tig": "ER70S-2",
            "stainless_304": "ER308L",
        },
        "position_notes": "Best in flat (1G). Gap control is critical.",
        "max_thickness": 0.1875,  # 3/16 inch — beyond this, groove prep needed
        "time_per_inch": {
            "mig_square_butt": 0.08,
            "tig_square_butt": 0.20,
        },
        "consumable_rates": {
            "mig_wire_lb_per_inch": 0.005,
            "mig_gas_cfh": 35,
            "tig_filler_lb_per_inch": 0.004,
            "tig_gas_cfh": 20,
        },
        "strength_notes": (
            "Full penetration achievable on material <= 3/16 inch without bevel. "
            "Beyond 3/16 inch, groove prep required for full pen."
        ),
        "common_in": [
            "straight_railing", "stair_railing", "exhaust_custom",
        ],
        "notes": "Most common butt joint in ornamental work. Keep gap consistent.",
        "NEVER": [
            "use on material over 3/16 inch without groove prep",
        ],
    },

    "butt_single_v": {
        "name": "Single V-Groove Butt Weld",
        "category": "groove",
        "aws_symbol": "B-U2 (single V-groove)",
        "description": (
            "Two members butted with single V-groove bevel. "
            "Standard full-penetration joint for medium thickness material."
        ),
        "prep_required": {
            "mild_steel": (
                "Bevel both edges to 30 degrees each (60 degree included angle). "
                "Root face: 1/16 inch. Root gap: 1/16 inch. "
                "Use grinder or plasma for bevel, verify with protractor."
            ),
            "stainless": (
                "Same bevel geometry. Back-purge with argon. "
                "Machine or grind bevel — no torch on stainless."
            ),
        },
        "weld_process": {
            "mild_steel_root": "tig (open root) or mig (with backing)",
            "mild_steel_fill_cap": "mig or flux_core",
            "stainless": "tig (all passes)",
        },
        "filler": {
            "mild_steel_root_tig": "ER70S-2",
            "mild_steel_fill_mig": "ER70S-6",
            "mild_steel_stick": "E7018",
            "stainless_304": "ER308L",
        },
        "position_notes": "Flat (1G) preferred. Vertical (3G) requires weave technique.",
        "thickness_range": {"min": 0.25, "max": 0.75},
        "time_per_inch": {
            "mig_fill_cap": 0.15,     # minutes per inch per pass
            "tig_root_pass": 0.25,     # slow, precise root
            "stick_fill_7018": 0.12,   # per pass
            "passes_per_inch_thickness": 4,  # rough estimate
        },
        "consumable_rates": {
            "mig_wire_lb_per_inch_fill": 0.010,
            "mig_gas_cfh": 40,
            "tig_filler_lb_per_inch_root": 0.005,
            "tig_gas_cfh": 20,
            "stick_electrode_per_inch": 0.015,
        },
        "strength_notes": (
            "Full penetration = base metal strength at joint. "
            "Radiographic quality if spec requires. "
            "3x labor of fillet weld for same length."
        ),
        "common_in": [
            "structural_frame", "trailer_fab", "complete_stair",
            "repair_structural",
        ],
        "notes": (
            "For quoting: full-pen butt welds = ~3x labor of fillet weld of equal length. "
            "Back-gouge and reweld if radiographic inspection required."
        ),
        "NEVER": [
            "skip root pass inspection on critical structural",
            "use E6013 for structural groove welds",
        ],
    },

    "butt_double_v": {
        "name": "Double V-Groove Butt Weld",
        "category": "groove",
        "aws_symbol": "B-U3 (double V-groove)",
        "description": (
            "V-groove beveled from both sides. For thick plate where "
            "single-sided welding would cause excessive distortion."
        ),
        "prep_required": {
            "mild_steel": (
                "Bevel both edges from both sides. 30 degree each side. "
                "Root face 1/16 inch. Back-gouge after welding first side."
            ),
        },
        "weld_process": {
            "mild_steel": "mig or stick fill, tig root if open root",
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
            "mild_steel_stick": "E7018",
        },
        "position_notes": "Flat only practical. Requires flipping workpiece.",
        "thickness_range": {"min": 0.75, "max": 99},   # > 3/4 inch
        "time_per_inch": {
            "per_pass_mig": 0.15,
            "per_pass_stick": 0.12,
            "typical_passes_1in_plate": 8,
            "back_gouge_per_inch": 0.10,
        },
        "consumable_rates": {
            "mig_wire_lb_per_inch_fill": 0.015,
            "mig_gas_cfh": 45,
            "stick_electrode_per_inch": 0.020,
        },
        "strength_notes": "Full CJP (complete joint penetration). Base metal strength. Balanced welding reduces distortion.",
        "common_in": [
            "structural_frame", "trailer_fab",
        ],
        "notes": (
            "Rare in ornamental work. Primarily structural steel erection. "
            "Balanced welding (alternate sides) controls distortion on thick plate."
        ),
        "NEVER": [],
    },

    # ===================================================================
    # CORNER JOINTS
    # ===================================================================

    "corner_miter": {
        "name": "Corner Joint — Miter (Outside Corner)",
        "category": "corner",
        "aws_symbol": "C-L2 (outside corner)",
        "description": (
            "Two members meeting at a mitered outside corner. "
            "Common in tube frames, gate frames, and furniture."
        ),
        "prep_required": {
            "mild_steel": (
                "Miter cut both members at 45 degrees. "
                "Clean cut edges. Fit tight — visible gap is a defect on mitered corners."
            ),
        },
        "weld_process": {
            "mild_steel_structural": "mig",
            "mild_steel_decorative": "tig",
            "stainless": "tig",
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
            "mild_steel_tig": "ER70S-2",
            "stainless_304": "ER308L",
        },
        "position_notes": (
            "Corner miters require gap control. "
            "Tack in sequence to manage heat pull. "
            "Miter cuts add 1-2 min per cut vs square cuts."
        ),
        "time_per_inch": {
            "mig_corner_weld": 0.08,
            "tig_corner_weld": 0.20,
            "grind_flush_per_inch": 0.65,  # if grinding flush
        },
        "consumable_rates": {
            "mig_wire_lb_per_inch": 0.005,
            "mig_gas_cfh": 35,
            "flap_disc_per_foot_grind_flush": 0.1,  # fraction of disc life
        },
        "strength_notes": "Miter corner is weaker than coped/notched joint. Adequate for non-critical frames.",
        "common_in": [
            "cantilever_gate", "swing_gate", "furniture_table",
            "furniture_other", "sign_frame", "utility_enclosure",
        ],
        "notes": (
            "15-20% labor premium for layout + fitting vs simple butt joints. "
            "Mitered tube corners: weld inside and outside for strength if structural."
        ),
        "NEVER": [],
    },

    "corner_coped": {
        "name": "Corner Joint — Cope/Notch (Tube-to-Tube)",
        "category": "corner",
        "aws_symbol": "Coped tube joint",
        "description": (
            "One tube coped (fishmouth or notch) to fit against another tube. "
            "Common in roll cages, bumpers, and structural tube assemblies."
        ),
        "prep_required": {
            "mild_steel": (
                "Layout cope profile on tube end. "
                "Cut with plasma, band saw, or hole saw + grind. "
                "Fit tight against mating tube — gap < 1/16 inch."
            ),
        },
        "weld_process": {
            "mild_steel": "mig (structural), tig (show quality)",
            "dom_tube": "tig (always — show quality expected with DOM)",  # SHOP: CreateStage
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
            "mild_steel_tig": "ER70S-2",
        },
        "position_notes": "3D joint — requires multi-position welding (flat, horizontal, vertical in one joint).",
        "time_per_inch": {
            "mig_coped_joint": 0.10,     # slower due to 3D profile
            "tig_coped_joint": 0.25,     # show quality
            "cope_layout_and_cut": 15.0,  # minutes per cope (fixed, not per inch)
        },
        "consumable_rates": {
            "mig_wire_lb_per_inch": 0.006,
            "mig_gas_cfh": 35,
            "tig_filler_lb_per_inch": 0.004,
            "tig_gas_cfh": 20,
        },
        "strength_notes": (
            "Full-profile cope provides maximum contact area. "
            "Stronger than mitered tube joint. Required for roll cages and structural tube."
        ),
        "common_in": [
            "roll_cage", "offroad_bumper", "rock_slider",
            "structural_frame", "balcony_railing",
        ],
        "notes": (
            "Cope layout is the slow part — 10-20 min per end. "
            "Tube notcher jig speeds this up to 3-5 min but limits angles."
        ),
        "NEVER": [],
    },

    # ===================================================================
    # PLUG AND SLOT WELDS
    # ===================================================================

    "plug_weld": {
        "name": "Plug Weld",
        "category": "plug",
        "aws_symbol": "Plug weld",
        "description": (
            "Weld through a hole in the top member into the bottom member. "
            "Used to attach sheet/plate to structure without edge access."
        ),
        "prep_required": {
            "mild_steel": (
                "Drill or punch hole in top member. Min diameter = thickness + 5/16 inch. "
                "Clean both mating surfaces."
            ),
        },
        "weld_process": {
            "mild_steel": "mig",
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
        },
        "position_notes": "Flat only. Cannot be done overhead reliably.",
        "time_per_inch": {
            "per_plug": 3.0,  # minutes per plug weld
        },
        "consumable_rates": {
            "mig_wire_per_plug": 0.01,  # lbs per plug
            "mig_gas_cfh": 35,
        },
        "strength_notes": "Each plug carries shear across joint. Space per structural calc or 4 inch max center-to-center.",
        "common_in": [
            "utility_enclosure", "trailer_fab",
        ],
        "notes": "Alternative to continuous edge weld where edge access is blocked or distortion must be minimized.",
        "NEVER": [],
    },

    # ===================================================================
    # DECORATIVE / SPECIALTY JOINTS
    # ===================================================================

    # SHOP: CreateStage — flat bar decorative joints
    "flat_bar_face_weld": {
        "name": "Flat Bar Face Weld (Decorative)",
        "category": "decorative",
        "aws_symbol": "N/A — shop convention",
        "description": (
            "Flat bar welded face-down onto a surface (tube frame or another flat bar). "  # SHOP: CreateStage
            "Weld runs along the edge where flat bar meets the surface. "
            "Common in pyramid patterns, concentric squares, and ornamental infill."
        ),
        "prep_required": {
            "mild_steel": (
                "Flat bar must be pre-ground to finish surface BEFORE cutting. "  # SHOP: CreateStage
                "Cut ends deburred only. Surface is already finished. "
                "Position must be measured and verified before tacking."
            ),
        },
        "weld_process": {
            "mild_steel_decorative": "mig (tack) + mig (edge weld)",  # SHOP: CreateStage
            "mild_steel_show_quality": "tig",
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
            "mild_steel_tig": "ER70S-2",
        },
        "position_notes": (
            "Flat position typical (piece on table). "
            "Edge welds on both long sides for structural integrity."
        ),
        "time_per_inch": {
            "position_and_tack_per_piece": 5.0,    # minutes — with jig  # SHOP: CreateStage
            "position_and_tack_no_jig": 10.0,       # minutes — measuring each  # SHOP: CreateStage
            "edge_weld_both_sides_per_inch": 0.15,  # both edges
            "die_grinder_cleanup_per_joint": 3.0,   # post-weld blend
        },
        "consumable_rates": {
            "mig_wire_per_piece": 0.003,  # small welds
            "mig_gas_cfh": 30,
        },
        "strength_notes": "Not structural — decorative only. Edge fillets provide adequate adhesion.",
        "common_in": [
            "furniture_table", "furniture_other",
            "ornamental_fence", "cantilever_gate", "swing_gate",
        ],
        # SHOP: CreateStage — Burton's sequential assembly
        "notes": (
            "Each piece: measure → position → weld → next piece. "
            "NOT dry-fit entire pattern first. "
            "120 pieces at 5 min = 10 hrs. This dominates decorative furniture labor."
        ),
        "NEVER": [
            "dry-fit entire pattern before welding",  # SHOP: CreateStage
            "re-grind finished surfaces after assembly",  # SHOP: CreateStage
            "skip individual measurement per piece",  # SHOP: CreateStage
        ],
    },

    "flat_bar_cross_joint": {
        "name": "Flat Bar Crossing / Woven Joint",
        "category": "decorative",
        "aws_symbol": "N/A — shop convention",
        "description": (
            "Two flat bars crossing at an intersection, one passing over/under the other. "  # SHOP: CreateStage
            "Creates a woven or basket-weave appearance at corners of pyramid patterns."
        ),
        "prep_required": {
            "mild_steel": (
                "Both pieces pre-ground to finish. "
                "Sequencing matters — alternating layers go over/under at intersections."
            ),
        },
        "weld_process": {
            "mild_steel": "mig (tack and weld at intersection points)",
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
        },
        "position_notes": "Flat. Requires careful piece ordering during assembly.",
        "time_per_inch": {
            "per_intersection": 4.0,  # minutes — position + weld at crossing point
        },
        "consumable_rates": {
            "mig_wire_per_intersection": 0.002,
            "mig_gas_cfh": 30,
        },
        "strength_notes": "Decorative. Weld points at intersection provide adhesion, not structural strength.",
        "common_in": [
            "furniture_table", "furniture_other",
        ],
        # SHOP: CreateStage
        "notes": (
            "Each corner intersection = 2 weld points (face + overlap). "
            "Total welds for 8-layer pyramid: ~96 weld points. "
            "Cannot skip layers or weld out of sequence — intersections lock order."
        ),
        "NEVER": [
            "weld layers out of sequence",  # SHOP: CreateStage
        ],
    },

    # ===================================================================
    # PIPE / TUBE JOINTS
    # ===================================================================

    "pipe_butt_full_pen": {
        "name": "Pipe Butt Joint — Full Penetration",
        "category": "groove",
        "aws_symbol": "B-U2a or B-U2 depending on thickness",
        "description": (
            "End-to-end pipe or tube joint requiring full penetration. "
            "Common in exhaust, handrail, and spiral stair center columns."
        ),
        "prep_required": {
            "mild_steel": (
                "Bevel pipe ends (37.5 degree bevel, 75 degree included). "
                "Root gap 1/16 inch to 3/32 inch. Root face 1/16 inch."
            ),
            "stainless": (
                "Same bevel geometry. MUST back-purge with argon. "
                "Tape ends, fill with argon, maintain purge through root pass."
            ),
        },
        "weld_process": {
            "mild_steel_root": "tig",
            "mild_steel_fill_cap": "mig",
            "stainless_all_passes": "tig",
            "exhaust_thin_wall": "tig",
        },
        "filler": {
            "mild_steel_tig_root": "ER70S-2",
            "mild_steel_mig_fill": "ER70S-6",
            "stainless_304": "ER308L",
            "exhaust_mild": "ER70S-2",
        },
        "position_notes": (
            "Pipe welding requires all-position skill (5G or 6G). "
            "Fixed pipe = welder moves around pipe. "
            "Rolled pipe = rotate in positioner (faster, better quality)."
        ),
        "time_per_inch": {
            "tig_root_per_inch_circumference": 0.25,
            "mig_fill_per_inch_circumference": 0.10,
            "tig_all_passes_stainless_per_inch": 0.30,
        },
        "consumable_rates": {
            "tig_filler_lb_per_inch": 0.005,
            "tig_gas_cfh": 20,
            "tig_purge_gas_cfh": 10,    # back-purge on stainless
            "mig_wire_lb_per_inch": 0.008,
            "mig_gas_cfh": 35,
        },
        "strength_notes": "Full CJP — base metal strength at joint.",
        "common_in": [
            "exhaust_custom", "spiral_stair", "straight_railing",
            "stair_railing", "bollard",
        ],
        "notes": "Premium labor — pipe welding is a specialist skill. 5G/6G certification often required.",
        "NEVER": [
            "skip back-purge on stainless pipe welds",
        ],
    },

    # ===================================================================
    # ANCHOR / ATTACHMENT JOINTS
    # ===================================================================

    "base_plate_to_post": {
        "name": "Base Plate to Post/Tube Weld",
        "category": "fillet",
        "aws_symbol": "Fillet all-around",
        "description": (
            "Square or round tube welded to a flat base plate. "
            "Common in bollards, railing posts, gate posts."
        ),
        "prep_required": {
            "mild_steel": (
                "Square-cut tube end. Flat base plate. "
                "Fit tight to plate — tack all four sides before welding."
            ),
        },
        "weld_process": {
            "mild_steel": "mig",
        },
        "filler": {
            "mild_steel_mig": "ER70S-6",
        },
        "position_notes": "Usually welded with tube vertical, plate flat. All-around fillet.",
        "time_per_inch": {
            "mig_fillet_all_around": 0.08,  # per inch of perimeter
        },
        "consumable_rates": {
            "mig_wire_lb_per_inch": 0.005,
            "mig_gas_cfh": 35,
        },
        "strength_notes": (
            "Fillet size per AWS D1.1 minimum for base metal thickness. "
            "All-around weld for moment connection (lateral load resistance)."
        ),
        "common_in": [
            "bollard", "straight_railing", "stair_railing",
            "balcony_railing", "cantilever_gate", "swing_gate",
            "ornamental_fence",
        ],
        "notes": "Common standard joint. Drill base plate for anchor bolts BEFORE welding tube to plate.",
        "NEVER": [],
    },

    "stud_weld": {
        "name": "Stud Weld (Nelson Stud)",
        "category": "stud",
        "aws_symbol": "Stud weld",
        "description": (
            "Threaded stud or shear connector welded directly to plate using stud welding gun. "
            "Fast, consistent, structural."
        ),
        "prep_required": {
            "mild_steel": "Clean plate surface at stud location. No paint, scale, or oil.",
        },
        "weld_process": {
            "mild_steel": "stud_weld_gun",
        },
        "filler": {
            "mild_steel": "Integral — stud itself provides filler (drawn arc process).",
        },
        "position_notes": "Flat (downhand) only. Cannot stud weld overhead.",
        "time_per_inch": {
            "per_stud": 0.5,  # minutes per stud (very fast once set up)
            "setup": 15.0,     # minutes — load gun, test welds
        },
        "consumable_rates": {
            "stud_per_unit": 1,
            "ferrule_per_stud": 1,
        },
        "strength_notes": "Tensile capacity per stud spec. Common for composite deck connections.",
        "common_in": [
            "structural_frame",
        ],
        "notes": "Specialized equipment. Subcontract if not in house.",
        "NEVER": [],
    },
}


# ---------------------------------------------------------------------------
# JOINT TYPE SELECTION RULES
# ---------------------------------------------------------------------------
# Decision logic for which joint to use based on context

JOINT_SELECTION_RULES = {
    "tube_to_tube_90": {
        "structural": "fillet_tee",
        "decorative_show": "corner_coped",
        "roll_cage": "corner_coped",
    },
    "tube_frame_corner": {
        "gate_frame": "corner_miter",
        "furniture_frame": "corner_miter",
        "structural_heavy": "fillet_tee",
    },
    "flat_bar_to_surface": {
        "decorative_pattern": "flat_bar_face_weld",
        "structural_stiffener": "fillet_tee",
    },
    "plate_to_tube": {
        "base_plate": "base_plate_to_post",
        "gusset": "fillet_tee",
    },
    "pipe_end_to_end": {
        "handrail_continuous": "pipe_butt_full_pen",
        "exhaust": "pipe_butt_full_pen",
        "structural": "butt_single_v",
    },
    "sheet_to_frame": {
        "enclosure_panel": "fillet_corner_inside",
        "no_edge_access": "plug_weld",
    },
}


# ---------------------------------------------------------------------------
# LOOKUP HELPERS
# ---------------------------------------------------------------------------

def get_joint(name):
    """Get a joint dict by name. Returns None if not found."""
    return JOINTS.get(name)


def get_joints_by_category(category):
    """Return all joints in a category."""
    return {k: v for k, v in JOINTS.items() if v.get("category") == category}


def get_joint_time(joint_name, process_key):
    """Get time per inch for a specific joint and process."""
    joint = JOINTS.get(joint_name)
    if not joint:
        return None
    return joint.get("time_per_inch", {}).get(process_key)


def get_min_fillet_size(base_metal_thickness):
    # type: (float) -> float
    """
    AWS D1.1 Table 5.8 — minimum fillet weld size for base metal thickness.

    Args:
        base_metal_thickness: thickness in inches

    Returns:
        Minimum fillet leg size in inches
    """
    if base_metal_thickness <= 0.25:
        return 0.125     # 1/8 inch
    elif base_metal_thickness <= 0.5:
        return 0.1875    # 3/16 inch
    elif base_metal_thickness <= 0.75:
        return 0.25      # 1/4 inch
    else:
        return 0.3125    # 5/16 inch


def get_fillet_capacity_per_inch(fillet_leg_size, filler_strength_psi=21000):
    # type: (float, int) -> float
    """
    Calculate shear capacity of a fillet weld per linear inch.

    Args:
        fillet_leg_size: leg dimension in inches
        filler_strength_psi: allowable shear stress (default 21,000 PSI for E70xx)

    Returns:
        Capacity in pounds per linear inch
    """
    throat = 0.707 * fillet_leg_size
    return throat * 1.0 * filler_strength_psi


def select_joint(context, structural=True):
    # type: (str, bool) -> Optional[str]
    """
    Suggest a joint type name based on context string.

    Args:
        context: Description like "tube_to_tube_90", "flat_bar_to_surface"
        structural: True if structural, False if decorative

    Returns:
        Joint name string or None
    """
    rules = JOINT_SELECTION_RULES.get(context, {})
    if not rules:
        return None
    # Return first matching key
    if structural:
        for key in ["structural", "structural_heavy"]:
            if key in rules:
                return rules[key]
    else:
        for key in ["decorative_pattern", "decorative_show"]:
            if key in rules:
                return rules[key]
    # Fallback — return first value
    return next(iter(rules.values()), None)
