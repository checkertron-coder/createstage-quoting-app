"""
Fabrication processes — every shop operation with steps, tools, timing,
safety, and applicability rules.

Sources: AWS D1.1, D1.3, Lincoln Electric welding handbook, Miller
Electric application guides, OSHA 29 CFR 1910 Subpart Q, shop practice.

Shop-specific overrides marked with # SHOP: CreateStage
"""

# ---------------------------------------------------------------------------
# PROCESS REGISTRY
# ---------------------------------------------------------------------------
# Each process has:
#   name            — human-readable name
#   category        — grouping (prep, cutting, welding, finishing, assembly, install)
#   steps           — ordered list of actions
#   tools           — required tools/equipment
#   consumables     — materials consumed (keys into consumables.py)
#   applies_when    — list of conditions that trigger this process
#   skip_when       — list of conditions that exclude this process
#   labor_type      — "active" (all time is labor) | "setup_only" (soak/cure is unattended)
#                     | "per_piece" | "per_linear_inch" | "per_sqft"
#   time_minutes    — base time estimate (depends on labor_type)
#   notes           — additional context
#   safety          — PPE and hazard notes
#   NEVER           — things that must NEVER appear with this process
# ---------------------------------------------------------------------------

PROCESSES = {

    # ===================================================================
    # PREP PROCESSES
    # ===================================================================

    "vinegar_bath": {
        "name": "Vinegar Bath Mill Scale Removal",
        "category": "prep",
        "steps": [
            "Fill bath/tub with 20-30% white vinegar solution",
            "Submerge stock — full-length raw material preferred",
            "Soak 12-24 hours (UNATTENDED — NOT labor time)",
            "Pull stock immediately when done soaking",
            "Rinse under warm running water",  # SHOP: CreateStage
            "Scrub with dish soap and red scotch-brite pad (medium grit)",  # SHOP: CreateStage
            "Rinse again thoroughly",  # SHOP: CreateStage
            "Dry with clean towel",  # SHOP: CreateStage
        ],
        "tools": [
            "vinegar bath tub/container",
            "rubber gloves",
            "dish soap",  # SHOP: CreateStage
            "red scotch-brite pads (medium grit)",  # SHOP: CreateStage
            "clean towels",  # SHOP: CreateStage
        ],
        "consumables": ["white_vinegar", "dish_soap", "scotch_brite_pads"],
        "applies_when": [
            "bare_metal_finish",
            "clear_coat",
            "clearcoat",
            "brushed",
            "patina",
            "chemical_patina",
            "raw_steel",
            "waxed",
        ],
        "skip_when": [
            "powder_coat",
            "paint",
            "galvanized",
            "stainless_steel",
            "aluminum",
        ],
        "labor_type": "setup_only",
        "time_minutes": {
            "setup_submerge": 20,    # fill bath, load parts
            "pull_rinse_dry": 35,    # rinse, scrub, dry
            "total_active": 55,      # 0.75-1.25 hrs active only
            "soak_unattended": 960,  # 12-24 hrs, NOT labor
        },
        "notes": (
            "This is a CLEANING step, not a finishing step. "
            "Surface finish comes from subsequent grinding. "
            "Do full-length stock BEFORE cutting for decorative work."
        ),
        "safety": [
            "Work outdoors or with exhaust ventilation — acetic acid fumes",
            "Rubber gloves required — prolonged skin contact causes irritation",
            "Rinse immediately after pulling — steel flash-rusts within minutes",
        ],
        # SHOP: CreateStage — Burton's actual cleanup method
        "NEVER": [
            "baking soda",          # old textbook advice, not used at CreateStage
            "compressed air",       # blows acid residue, flash-rust risk
            "wire brush for cleanup",  # too aggressive for post-vinegar surface
            "chemical neutralizer",  # unnecessary with thorough rinse + soap
        ],
    },

    "degrease": {
        "name": "Degrease / Solvent Wipe",
        "category": "prep",
        "steps": [
            "Wipe all surfaces with acetone or MEK on clean lint-free cloth",
            "Let solvent evaporate completely (2-5 minutes)",
            "Do NOT touch degreased surfaces with bare hands (oils from skin)",
        ],
        "tools": ["lint-free rags", "solvent container"],
        "consumables": ["acetone"],
        "applies_when": [
            "before_welding_stainless",
            "before_clear_coat",
            "before_paint",
            "before_powder_coat_prep",
            "before_patina",
        ],
        "skip_when": [],
        "labor_type": "per_sqft",
        "time_minutes": {"per_sqft": 0.5, "minimum": 10},
        "notes": "Always the LAST prep step before coating. Steel re-oxidizes in 30-60 min in humid conditions.",
        "safety": [
            "Ventilation required — MEK and acetone are volatile",
            "No open flames within 20 feet",
            "Nitrile gloves — acetone dries skin rapidly",
        ],
        "NEVER": [],
    },

    "sandblast": {
        "name": "Abrasive Blasting (Sandblast)",
        "category": "prep",
        "steps": [
            "Mask areas that should not be blasted (threads, bearing surfaces)",
            "Set air pressure (80-100 PSI for structural, 40-60 for thin material)",
            "Blast in sweeping motion — maintain 6-12 inch standoff",
            "Inspect for SSPC-SP6 (commercial blast) or SP10 (near-white)",
            "Prime within 4 hours of blasting (flash rust risk)",
        ],
        "tools": [
            "blast cabinet or blast pot",
            "blast nozzle (No. 6 or 7)",
            "air compressor (175+ CFM)",
            "blast media (aluminum oxide, garnet, or glass bead)",
        ],
        "consumables": ["blast_media"],
        "applies_when": [
            "spec_requires_sspc_sp6",
            "spec_requires_sspc_sp10",
            "heavy_rust_removal",
            "structural_coating_spec",
        ],
        "skip_when": [
            "furniture_work",
            "thin_material_under_16ga",
        ],
        "labor_type": "per_sqft",
        "time_minutes": {"per_sqft": 3, "minimum": 30},
        "notes": "Usually subcontracted. Factor in transport cost (half-day minimum).",
        "safety": [
            "NIOSH-approved supplied-air respirator REQUIRED",
            "Blast suit, leather gloves, hearing protection",
            "Stainless steel blasting produces hexavalent chromium — HEPA ventilation",
        ],
        "NEVER": [],
    },

    "phosphoric_acid_wash": {
        "name": "Phosphoric Acid Wash (Metal Prep / Ospho)",
        "category": "prep",
        "steps": [
            "Apply phosphoric acid solution (Ospho, Metal Prep) with brush or spray",
            "Let dwell 15-30 minutes until surface turns gray-white",
            "Rinse with clean water",
            "Dry thoroughly",
            "Prime within 2 hours",
        ],
        "tools": ["acid-resistant brush or pump sprayer", "rinse water supply"],
        "consumables": ["phosphoric_acid_solution"],
        "applies_when": [
            "outdoor_structural_paint_prep",
            "light_rust_conversion",
        ],
        "skip_when": [
            "stainless_steel",
            "aluminum",
            "clear_coat_finish",
            "bare_metal_finish",
        ],
        "labor_type": "per_sqft",
        "time_minutes": {"per_sqft": 2, "minimum": 20},
        "notes": "Converts iron oxide to iron phosphate (natural primer). Not for stainless or aluminum.",
        "safety": [
            "Chemical splash goggles",
            "Acid-resistant gloves (nitrile or neoprene)",
            "Ventilation required",
        ],
        "NEVER": [],
    },

    # ===================================================================
    # CUTTING PROCESSES
    # ===================================================================

    "chop_saw_cut": {
        "name": "Chop Saw / Abrasive Cutoff",
        "category": "cutting",
        "steps": [
            "Measure and mark cut line (silver marker or soapstone)",
            "Clamp material securely in saw vise",
            "Set angle if miter cut (verify with speed square or protractor)",
            "Cut — steady feed, let blade do the work",
            "Deburr cut end with file or flap disc",
        ],
        "tools": [
            "abrasive chop saw (14 inch)",
            "measuring tape",
            "silver marker or soapstone",
            "speed square (for miters)",
            "file or flap disc",
        ],
        "consumables": ["cutoff_wheel_14in"],
        "applies_when": ["all_tube_and_bar_cuts"],
        "skip_when": ["sheet_plate_cuts"],
        "labor_type": "per_piece",
        "time_minutes": {
            "square_cut_1in_tube": 2.5,
            "square_cut_2in_tube": 4.0,
            "square_cut_3in_tube": 5.0,
            "square_cut_4in_tube": 6.0,
            "miter_cut_any": 5.0,     # add 2 min for angle setup
            "compound_cut": 8.0,       # two angle setups
            "cope_notch": 15.0,        # layout + hand work
            "deburr_per_end": 1.5,
        },
        "notes": "Miter cuts require angle setup — additional 1-2 min per cut. Compound cuts require two setups.",
        "safety": [
            "Safety glasses and face shield",
            "Hearing protection (>85 dB)",
            "Clamp material — NEVER hand-hold",
            "No loose clothing near rotating blade",
        ],
        "NEVER": [],
    },

    "band_saw_cut": {
        "name": "Band Saw Cut",
        "category": "cutting",
        "steps": [
            "Measure and mark",
            "Adjust blade guides and feed rate for material",
            "Clamp material in vise",
            "Cut — slow steady feed",
            "Deburr",
        ],
        "tools": [
            "horizontal or vertical band saw",
            "measuring tape",
            "bi-metal blade (appropriate TPI)",
        ],
        "consumables": ["bandsaw_blade"],
        "applies_when": [
            "precision_cuts",
            "thick_material_over_4in",
            "stainless_steel_cuts",
        ],
        "skip_when": [],
        "labor_type": "per_piece",
        "time_minutes": {
            "cut_1in": 3.0,
            "cut_2in": 5.0,
            "cut_4in": 8.0,
            "stainless_multiplier": 1.5,
        },
        "notes": (
            "Slower than chop saw but cleaner cut, less heat. "
            "Required for stainless (chop saw overheats and work-hardens stainless)."
        ),
        "safety": [
            "Keep fingers clear of blade path",
            "Use cutting fluid for stainless and thick material",
        ],
        "NEVER": [],
    },

    "plasma_cut": {
        "name": "Plasma Cutting",
        "category": "cutting",
        "steps": [
            "Mark cut line on plate/sheet",
            "Set amperage for material thickness",
            "Position torch at edge or pierce point",
            "Cut — maintain consistent standoff and travel speed",
            "Clean dross from cut edge (grinder or file)",
        ],
        "tools": [
            "plasma cutter (40-80A for shop work)",
            "straight edge or CNC table",
            "soapstone or silver marker",
        ],
        "consumables": ["plasma_electrode", "plasma_nozzle", "compressed_air_or_gas"],
        "applies_when": [
            "sheet_plate_cuts",
            "curved_cuts",
            "holes_in_plate",
        ],
        "skip_when": [
            "tube_bar_cuts",
            "precision_fits_under_1mm_tolerance",
        ],
        "labor_type": "per_piece",
        "time_minutes": {
            "setup": 5,
            "per_linear_foot_mild_steel": 2.0,
            "per_linear_foot_stainless": 3.0,
            "dross_cleanup_per_foot": 1.5,
        },
        "notes": "HAZ (heat-affected zone) is narrow but exists. Not suitable for finish edges without grinding.",
        "safety": [
            "Welding helmet with shade 5-8",
            "Hearing protection",
            "Ventilation — plasma on stainless produces hexavalent chromium",
            "Fire blanket or metal table — sparks travel 15+ feet",
        ],
        "NEVER": [],
    },

    "cold_saw_cut": {
        "name": "Cold Saw Cut",
        "category": "cutting",
        "steps": [
            "Measure and mark",
            "Clamp material in cold saw vise",
            "Apply cutting fluid",
            "Cut — blade RPM matched to material",
            "Light deburr only (cold saw leaves clean edge)",
        ],
        "tools": [
            "cold saw",
            "cutting fluid (Tap Magic or equivalent)",
        ],
        "consumables": ["cold_saw_blade", "cutting_fluid"],
        "applies_when": [
            "precision_square_cuts",
            "high_volume_repetitive_cuts",
        ],
        "skip_when": ["miter_cuts", "field_work"],
        "labor_type": "per_piece",
        "time_minutes": {
            "cut_1in": 2.0,
            "cut_2in": 3.0,
            "cut_3in": 4.0,
        },
        "notes": "Cleanest shop cut. Minimal burr, no heat distortion. Blade is expensive — use for high-value work.",
        "safety": ["Cutting fluid required for blade life", "Hearing protection"],
        "NEVER": [],
    },

    "torch_cut": {
        "name": "Oxy-Fuel Torch Cutting",
        "category": "cutting",
        "steps": [
            "Mark cut line",
            "Set regulator pressures (oxygen 40-60 PSI, fuel 5-10 PSI)",
            "Light torch, adjust to neutral flame",
            "Preheat leading edge to cherry red",
            "Depress oxygen lever and travel along cut line",
            "Grind slag from cut edge",
        ],
        "tools": [
            "oxy-fuel torch set",
            "cutting tip (appropriate size)",
            "striker/igniter",
            "straight edge or track torch",
        ],
        "consumables": ["oxygen_gas", "acetylene_or_propane"],
        "applies_when": [
            "heavy_plate_over_1in",
            "field_demolition_cuts",
            "rough_cuts_where_precision_not_needed",
        ],
        "skip_when": [
            "stainless_steel",
            "aluminum",
            "thin_material_under_10ga",
            "precision_work",
        ],
        "labor_type": "per_piece",
        "time_minutes": {
            "setup": 5,
            "per_linear_foot_mild_steel": 3.0,
            "slag_cleanup_per_foot": 2.0,
        },
        "notes": (
            "Only works on mild/carbon steel (oxidation reaction). "
            "Will NOT cut stainless, aluminum, or copper alloys."
        ),
        "safety": [
            "Shade 5 cutting goggles (NOT welding helmet shade)",
            "Leather gloves and apron",
            "Fire watch for 30 minutes after cutting",
            "Check all fittings for leaks before lighting",
        ],
        "NEVER": [],
    },

    # ===================================================================
    # WELDING PROCESSES
    # ===================================================================

    "mig_weld": {
        "name": "MIG Welding (GMAW)",
        "category": "welding",
        "steps": [
            "Set wire feed speed and voltage for material thickness",
            "Verify gas flow (30-40 CFH for 75/25 Ar/CO2)",
            "Clean weld area — remove paint, oil, heavy scale at joint",
            "Tack weld in sequence (corners first, center-out for long seams)",
            "Check alignment and square after tacking",
            "Run continuous welds (backstep for long seams to control distortion)",
            "Chip spatter if present",
        ],
        "tools": [
            "MIG welder (200-350A)",
            "MIG gun with correct contact tip",
            "welding helmet (auto-dark shade 10-13)",
            "welding gloves",
            "wire brush or chipping hammer",
        ],
        "consumables": ["mig_wire_er70s6", "shield_gas_75_25"],
        "applies_when": [
            "mild_steel",
            "material_12ga_or_thicker",
            "structural_welding",
            "long_welds",
            "tack_welding_all_materials",
        ],
        "skip_when": [
            "stainless_finish_welds",
            "thin_sheet_under_16ga_continuous",
            "aluminum_without_spool_gun",
        ],
        "labor_type": "per_linear_inch",
        "time_minutes": {
            "fillet_3_16_per_inch": 0.06,   # 12-18 in/min travel = ~4 sec/inch
            "fillet_1_4_per_inch": 0.08,     # slower for larger fillet
            "fillet_5_16_per_inch": 0.12,    # multi-pass
            "tack_per_joint": 1.5,           # position + tack
        },
        "notes": (
            "ER70S-6 is the workhorse wire — good wetting, handles light mill scale. "
            "75/25 Ar/CO2 is standard gas. 100% CO2 cheaper but more spatter."
        ),
        "safety": [
            "Welding helmet shade 10-13",
            "Leather welding gloves",
            "Flame-resistant clothing (no synthetics)",
            "Ventilation in enclosed spaces",
        ],
        "NEVER": [],
    },

    "tig_weld": {
        "name": "TIG Welding (GTAW)",
        "category": "welding",
        "steps": [
            "Select tungsten (2% lanthanated for steel, pure for aluminum AC)",
            "Set amperage (rule of thumb: 1 amp per 0.001 inch material thickness)",
            "Set gas flow (15-25 CFH argon — lower than MIG)",
            "Set post-flow (5-10 seconds to protect tungsten and weld pool)",
            "Prep tungsten — grind to point for DC (steel), ball for AC (aluminum)",
            "Clean weld area thoroughly — TIG is intolerant of contamination",
            "Tack in sequence",
            "Weld — feed filler rod with non-dominant hand, control puddle with torch",
            "Walk the cup or freehand depending on joint access",
        ],
        "tools": [
            "TIG welder (200-300A, AC/DC)",
            "TIG torch (air or water cooled)",
            "assorted tungsten electrodes",
            "filler rods (ER70S-2 mild, ER308L stainless, 4043/5356 aluminum)",
            "argon gas",
            "tungsten grinder (dedicated — NO cross-contamination)",
        ],
        "consumables": ["tig_filler_rod", "shield_gas_argon", "tungsten_electrode"],
        "applies_when": [
            "stainless_steel",
            "aluminum",
            "thin_material_under_14ga",
            "visible_decorative_welds",
            "ground_flush_joints",
            "show_quality_finish",
            "root_pass_pipe",
        ],
        "skip_when": [
            "heavy_structural_over_1_4in",
            "long_welds_over_3ft",
            "outdoor_wind",
        ],
        "labor_type": "per_linear_inch",
        "time_minutes": {
            "fillet_per_inch_mild_steel": 0.15,   # 4-6 in/min = ~10 sec/inch
            "fillet_per_inch_stainless": 0.20,     # 3-5 in/min = ~12 sec/inch + purge
            "fillet_per_inch_aluminum": 0.18,       # AC, faster puddle but tricky
            "tack_per_joint": 2.0,                  # slower setup per joint
        },
        "notes": (
            "TIG labor = 2.5-3x MIG for same weld length. "
            "ER70S-2 (triple-deox) handles slightly dirty base metal better than ER70S-6 filler rod. "
            "ER308L for 304 stainless, ER309L for dissimilar (mild to stainless)."
        ),
        "safety": [
            "Welding helmet shade 10-13",
            "Leather TIG gloves (thinner than MIG for dexterity)",
            "ARGON IS AN ASPHYXIANT — ventilation critical in enclosed spaces",
            "UV exposure higher with TIG — cover all exposed skin",
        ],
        "NEVER": [],
    },

    "stick_weld": {
        "name": "Stick Welding (SMAW)",
        "category": "welding",
        "steps": [
            "Select electrode for application",
            "Set amperage per electrode diameter and position",
            "Clean weld area (stick is more tolerant but cleaner = better)",
            "Strike arc and establish puddle",
            "Weld — maintain proper arc length (1 electrode diameter)",
            "Chip slag completely between passes",
            "Wire brush before next pass",
        ],
        "tools": [
            "stick welder (CC power source, 200-400A)",
            "electrode holder (stinger)",
            "ground clamp",
            "chipping hammer",
            "wire brush",
        ],
        "consumables": ["stick_electrodes"],
        "applies_when": [
            "field_repairs",
            "heavy_plate_over_1_2in",
            "outdoor_wind",
            "dirty_rusty_material",
            "no_gas_available",
        ],
        "skip_when": [
            "thin_material_under_12ga",
            "decorative_work",
            "production_shop_work",
        ],
        "labor_type": "per_linear_inch",
        "time_minutes": {
            "fillet_per_inch_7018": 0.10,
            "fillet_per_inch_6011": 0.08,
            "slag_chip_per_pass_per_foot": 1.0,
        },
        "notes": (
            "E6013: sheet/light structural (easy slag, AC). "
            "E7018: structural (low hydrogen, requires dry rods — use rod oven). "
            "E6011: dirty/rusty/outdoor (AC or DC, penetrates through contamination)."
        ),
        "safety": [
            "Welding helmet shade 10-14",
            "Leather gloves",
            "Electrode stubs are BURN HAZARD — dispose in metal container",
            "Slag chips are sharp and hot — safety glasses under helmet",
        ],
        "NEVER": [],
    },

    "flux_core_weld": {
        "name": "Flux-Core Arc Welding (FCAW)",
        "category": "welding",
        "steps": [
            "Select wire (E71T-11 self-shielded or E71T-1 gas-shielded)",
            "Set wire feed speed and voltage",
            "If gas-shielded: verify gas flow (40-50 CFH CO2 or 75/25)",
            "Weld — similar technique to MIG but drag angle is critical",
            "Chip slag between passes",
        ],
        "tools": [
            "MIG/FCAW welder (wire feeder capable)",
            "flux-core gun",
            "chipping hammer",
        ],
        "consumables": ["flux_core_wire"],
        "applies_when": [
            "outdoor_structural",
            "high_deposition_rate_needed",
            "heavy_plate",
        ],
        "skip_when": [
            "decorative_work",
            "thin_material",
            "stainless_aluminum",
        ],
        "labor_type": "per_linear_inch",
        "time_minutes": {
            "fillet_per_inch": 0.05,  # higher deposition rate than MIG
        },
        "notes": (
            "E71T-11 self-shielded (no gas) — good for outdoor. "
            "E71T-1 gas-shielded — better bead, less spatter. "
            "Deposition rate higher than MIG — factor into labor if subbing structural."
        ),
        "safety": [
            "More fume than MIG — ventilation critical",
            "Welding helmet shade 10-13",
        ],
        "NEVER": [],
    },

    # ===================================================================
    # GRINDING / FINISHING PROCESSES
    # ===================================================================

    "angle_grinder_grinding": {
        "name": "Angle Grinder — Weld Grinding and Surface Prep",
        "category": "grinding",
        "steps": [
            "Select disc type for application:",
            "  - Flap disc 40-grit: heavy stock removal, mill scale on raw stock",
            "  - Flap disc 80-grit: weld blending, general surface prep",
            "  - Flap disc 120-grit: finish blending, pre-paint prep",
            "  - Fiber disc 36-grit: aggressive material removal",
            "  - Grinding wheel: weld profile correction, heavy removal",
            "  - Wire wheel: weld cleanup, rust removal on curves",
            "  - Cut-off wheel: trimming, notching",
            "Grind in ONE direction for consistent finish (especially brushed look)",
            "Check surface with hand — feel for remaining high spots",
            "Progress through grits only if smoother finish required",
        ],
        "tools": [
            "4.5-inch angle grinder (primary)",
            "7-inch angle grinder (heavy removal on large surfaces)",
            "assorted flap discs (40, 60, 80, 120 grit)",
            "fiber discs",
            "grinding wheels",
            "wire wheels (crimped and knotted)",
            "cut-off wheels",
        ],
        "consumables": ["flap_disc", "grinding_wheel", "fiber_disc", "cutoff_wheel", "wire_wheel"],
        "applies_when": ["weld_cleanup", "surface_prep", "mill_scale_removal", "weld_flush_grinding"],
        "skip_when": [],
        "labor_type": "per_linear_inch",
        "time_minutes": {
            "grind_flush_per_foot": 8.0,          # visible welds ground flush
            "blend_per_foot": 5.0,                 # blend transition, not full flush
            "cleanup_per_foot": 3.0,               # light spatter/bead cleanup
            "mill_scale_per_sqft": 5.0,            # raw stock grinding
            "brush_finish_per_sqft": 25.0,         # directional grain finish
        },
        "notes": (
            "4.5\" grinder for open surfaces. "
            "Use die grinder for constrained spaces between layers or inside frames."
        ),
        "safety": [
            "Safety glasses AND face shield",
            "Leather gloves — disc fragments are hot",
            "Hearing protection (>90 dB)",
            "Never remove guard from grinder",
            "Grind away from welds while bead is still hot — hydrogen cracking risk",
        ],
        "NEVER": [],
    },

    "die_grinder_cleanup": {
        "name": "Die Grinder / Rotary Tool — Constrained Access Cleanup",
        "category": "grinding",
        "steps": [
            "Select 2-inch roloc-style disc or carbide burr for application",
            "Work in constrained spaces where angle grinder cannot reach",
            "Light touch — die grinder at high RPM removes material fast",
            "Blend weld spots only — do NOT re-grind finished surfaces",
        ],
        "tools": [
            "pneumatic or electric die grinder",
            "2-inch roloc discs (assorted grits)",
            "carbide burrs (assorted profiles)",
            "mandrels and backing pads",
        ],
        "consumables": ["roloc_disc_2in"],
        "applies_when": [
            "weld_cleanup_between_layers",
            "inside_frame_cleanup",
            "tight_access_areas",
        ],
        "skip_when": ["open_accessible_surfaces"],
        "labor_type": "per_piece",
        "time_minutes": {
            "per_weld_area": 4.0,  # 3-5 min per constrained weld area
        },
        "notes": (
            "Slower than angle grinder but reaches where 4.5-inch disc cannot. "
            "'Inaccessible' usually means 'requires smaller tooling and more time,' "
            "not 'physically impossible.' Adjust labor time, don't skip the operation."
        ),
        "safety": [
            "Safety glasses",
            "Die grinder bits can grab — firm grip required",
            "Hearing protection",
        ],
        "NEVER": [],
    },

    "hand_finishing": {
        "name": "Hand File / Emery Cloth Finishing",
        "category": "grinding",
        "steps": [
            "File edges and tight spots by hand",
            "Use emery cloth (150-320 grit) for final surface blending",
            "Work in consistent direction for uniform appearance",
        ],
        "tools": [
            "mill files (flat, half-round)",
            "needle files (for tight spots)",
            "emery cloth (assorted grits)",
        ],
        "consumables": ["emery_cloth"],
        "applies_when": [
            "very_tight_spots",
            "final_touchup",
            "thread_deburring",
        ],
        "skip_when": ["structural_only"],
        "labor_type": "per_piece",
        "time_minutes": {"per_spot": 5.0},
        "notes": "Last resort for areas where no power tool can reach. Slow but precise.",
        "safety": ["Gloves — file edges are sharp"],
        "NEVER": [],
    },

    # SHOP: CreateStage — decorative flat bar: grind IS the finish
    "decorative_stock_prep": {
        "name": "Decorative Stock Prep — Grind Before Cutting",
        "category": "grinding",
        "steps": [
            "Vinegar bath full-length raw stock (see vinegar_bath process)",
            "After vinegar cleanup: heavy grind with 40-grit flap disc on ALL faces",  # SHOP: CreateStage
            "This IS the finish — the 40-grit texture is the design intent",  # SHOP: CreateStage
            "Stock is now finish-ready — cut to final dimensions from prepped stock",
            "After cutting: light deburr on cut ends ONLY (faces already finished)",
            "After assembly: die grinder cleanup on WELD AREAS ONLY",
            "Do NOT re-grind entire pieces after welding",
        ],
        "tools": [
            "4.5-inch angle grinder",
            "40-grit flap discs (primary finish tool)",  # SHOP: CreateStage
            "die grinder with 2-inch roloc for post-weld cleanup",
        ],
        "consumables": ["flap_disc"],
        "applies_when": [
            "decorative_flat_bar",
            "visible_steel_furniture",
            "clear_coat_finish",
            "raw_steel_finish",
            "brushed_finish",
        ],
        "skip_when": [
            "structural_only",
            "powder_coat",
            "paint",
            "tube_frame_only",
        ],
        "labor_type": "per_sqft",
        "time_minutes": {
            "grind_per_sqft": 8.0,   # heavy grind on raw stock
            "post_weld_cleanup_per_joint": 3.0,
        },
        "notes": (
            "CRITICAL: Do ALL finish grinding on full-length raw stock BEFORE cutting. "
            "Small cut pieces cannot be held steady against a grinder — finish will be "
            "inconsistent and hours are wasted fighting the material. "
            "Split grind hours: 60-70% stock prep grind BEFORE cutting, "
            "30-35% post-weld cleanup AFTER assembly (capped at 2 hrs)."
        ),
        "safety": [
            "Face shield required for heavy grinding",
            "Respirator for extended grinding sessions",
        ],
        # SHOP: CreateStage — 40 grit on raw stock IS the look
        "NEVER": [
            "grind after cutting small pieces",
            "re-grind finished surfaces after assembly",
            "skip stock prep grinding",
            # Progressive grit sequences are wrong — 40 grit IS the finish
            "80 grit then 120 grit",
            "80-grit followed by 120-grit",
            "120 grit for final finish",
            "progressive grit sequence",
        ],
    },

    # ===================================================================
    # FINISHING / COATING PROCESSES
    # ===================================================================

    "clear_coat": {
        "name": "Clear Coat Application",
        "category": "finishing",
        "steps": [
            "Complete all grinding and surface prep",
            "Wipe entire surface with acetone — lint-free cloth",
            "Let acetone evaporate completely (5 min)",
            "Apply clear coat within 30-60 minutes of final cleaning",
            "Spray top surfaces, let cure (1-2 hours)",
            "Flip piece on lazy susan or padded surface",
            "Coat bottom and legs",
            "Final cure per product spec (typically 24 hours)",
        ],
        "tools": [
            "HVLP spray gun or rattle can",
            "lazy susan or padded flip surface",
            "lint-free rags",
            "acetone",
            "tack rags",
            "masking tape (if needed)",
        ],
        "consumables": ["clear_coat_product", "acetone", "tack_rags"],
        "applies_when": [
            "clear_coat_finish",
            "show_quality_steel",
            "industrial_look",
            "permalac_finish",
        ],
        "skip_when": [
            "powder_coat",
            "paint",
            "galvanized",
            "raw_no_finish",
        ],
        "labor_type": "per_sqft",
        "time_minutes": {
            "prep_wipe_per_sqft": 0.5,
            "spray_per_sqft": 1.5,
            "flip_and_recoat": 15,
            "minimum_total": 60,
        },
        "notes": (
            "Lacquer: cheapest, not UV stable (interior only). "
            "Urethane: mid-range, good outdoor durability. "
            "Permalac: best for interior — expensive but longest lasting. "
            "Materials cost: $25-40 per piece. Total process adds 3-5 hrs labor."
        ),
        "safety": [
            "Respirator with organic vapor cartridge",
            "Ventilation — spray in booth or outdoors",
            "No open flames — lacquer and urethane are flammable",
        ],
        "NEVER": [
            "apply over contaminated surface",
            "spray in humid conditions over 80% RH",
            "combine with powder coat line items",
        ],
    },

    "paint": {
        "name": "Paint Application (Primer + Topcoat)",
        "category": "finishing",
        "steps": [
            "Degrease with acetone or pre-paint cleaner",
            "Scuff with 220-grit sandpaper for adhesion",
            "Apply self-etching primer on bare steel",
            "Let primer cure (check product — typically 1 hour)",
            "Apply topcoat (2 light coats better than 1 heavy)",
            "Final cure per product spec",
        ],
        "tools": [
            "HVLP spray gun or rattle can",
            "220-grit sandpaper",
            "paint mixing cups",
        ],
        "consumables": ["primer", "topcoat_paint", "sandpaper_220"],
        "applies_when": [
            "paint_finish",
            "budget_finish",
            "color_required",
        ],
        "skip_when": [
            "powder_coat",
            "clear_coat",
            "galvanized",
            "raw",
        ],
        "labor_type": "per_sqft",
        "time_minutes": {
            "prep_scuff_per_sqft": 1.0,
            "prime_per_sqft": 1.5,
            "topcoat_per_sqft": 2.0,
            "cure_time_unattended": 60,
        },
        "notes": "Not suitable for structural outdoor exposed work. Rattle can for small jobs, HVLP for larger.",
        "safety": [
            "Respirator with organic vapor cartridge",
            "Ventilation",
            "No sparks or open flames",
        ],
        "NEVER": [],
    },

    "powder_coat": {
        "name": "Powder Coat (Outsourced)",
        "category": "finishing",
        "steps": [
            "Complete all welding, grinding, and hardware mounting",
            "Mock-install hardware (hinges, latches) to verify fit BEFORE sending",
            "Remove sharp edges and spatter (causes powder coat runs/thin spots)",
            "Degrease — acetone wipe",
            "Transport to powder coater",
            "Receive back — inspect for coverage, adhesion, color match",
        ],
        "tools": [],
        "consumables": [],
        "applies_when": [
            "powder_coat_finish",
            "exterior_durability",
            "commercial_spec",
            "color_options",
        ],
        "skip_when": [
            "clear_coat",
            "raw",
            "galvanized",
        ],
        "labor_type": "active",
        "time_minutes": {
            "prep_edges_and_degrease": 60,
            "transport_roundtrip": 240,  # 3-4 hrs minimum round trip
        },
        "notes": (
            "Outsourced process — in-house labor is only prep and transport. "
            "Cost: $2.50-5.00/sqft at coater. "
            "Standard RAL colors off-the-shelf. Custom colors = premium + longer lead. "
            "Send pre-assembled — panels that can't go through oven separately."
        ),
        "safety": [],
        "NEVER": [
            "include outsource cost as labor hours",
            "combine with in-house clear coat",
        ],
    },

    "galvanize": {
        "name": "Hot-Dip Galvanize (Outsourced)",
        "category": "finishing",
        "steps": [
            "Complete all welding and grinding",
            "Drill vent holes in closed sections (gas escapes during dipping)",
            "Remove all non-metallic items (rubber, plastic, paint)",
            "Transport to galvanizer",
            "Receive back — inspect for coverage and runs",
        ],
        "tools": [],
        "consumables": [],
        "applies_when": [
            "galvanized_finish",
            "outdoor_corrosion_resistance",
            "marine_environment",
        ],
        "skip_when": [
            "aesthetic_finish_required",
            "tight_tolerances",
        ],
        "labor_type": "active",
        "time_minutes": {
            "prep_vent_holes": 30,
            "transport_roundtrip": 240,
        },
        "notes": (
            "Galvanizer does all surface prep (acid pickle). "
            "MUST drill vent/drain holes in all closed tube ends — "
            "trapped air + molten zinc = EXPLOSION HAZARD. "
            "Warp risk on thin material from 840F zinc bath."
        ),
        "safety": [
            "NEVER weld galvanized without full PPE and ventilation",
            "Zinc oxide fumes cause metal fume fever",
        ],
        "NEVER": [
            "skip vent holes on closed sections",
            "include galvanizer surface prep as labor",
        ],
    },

    "patina": {
        "name": "Chemical Patina (Rust Finish)",
        "category": "finishing",
        "steps": [
            "Remove mill scale completely (vinegar bath or grind)",
            "Degrease thoroughly — any oil spots will reject patina",
            "Apply patina solution (Sculpt Nouveau, ferric chloride, or salt/vinegar spray)",
            "Let flash rust develop — 1 hour to several days depending on look",
            "When desired stage reached, seal with Permalac or museum wax",
        ],
        "tools": [
            "spray bottle or brush",
            "patina solution",
            "sealer (Permalac or wax)",
        ],
        "consumables": ["patina_solution", "patina_sealer"],
        "applies_when": [
            "patina_finish",
            "chemical_patina",
            "corten_look",
            "artistic_rust",
        ],
        "skip_when": [
            "stainless",
            "aluminum",
            "structural_only",
        ],
        "labor_type": "active",
        "time_minutes": {
            "prep_and_apply": 60,
            "monitor_and_seal": 30,
            "rust_development_unattended": 1440,  # 1-24 hrs, not labor
        },
        "notes": "Very skill-sensitive — quote with artist's premium if customer-facing.",
        "safety": [
            "Chemical goggles",
            "Nitrile gloves",
            "Ventilation for acid-based solutions",
        ],
        "NEVER": [],
    },

    "brushed_finish": {
        "name": "Brushed Steel Finish",
        "category": "finishing",
        "steps": [
            "Grind welds flush with 60-grit fiber disc",
            "Switch to 80-grit, then 120-grit — always in ONE DIRECTION",
            "Finish with scotch-brite or surface conditioning disc",
            "Wipe with acetone before clear coat or sealer",
        ],
        "tools": [
            "angle grinder",
            "fiber discs (60, 80, 120 grit)",
            "surface conditioning disc (scotch-brite type)",
        ],
        "consumables": ["fiber_disc", "surface_conditioning_disc"],
        "applies_when": [
            "brushed_finish",
            "directional_grain",
            "near_stainless_look",
        ],
        "skip_when": [],
        "labor_type": "per_sqft",
        "time_minutes": {
            "per_sqft": 25.0,  # 15-30 min/sqft
        },
        "notes": "Labor premium: 2-4x weld finishing vs leaving welds visible. Always ONE direction for consistent grain.",
        "safety": ["Face shield", "Hearing protection"],
        "NEVER": [],
    },

    # ===================================================================
    # ASSEMBLY PROCESSES
    # ===================================================================

    "fixture_and_tack": {
        "name": "Fixture, Fit, and Tack Assembly",
        "category": "assembly",
        "steps": [
            "Set up welding table — verify flat and clean",
            "Fixture primary members (clamps, magnets, jigs)",
            "Check square with framing square or diagonal measurement",
            "Tack weld in sequence — corners first for frames",
            "Verify square and alignment AFTER tacking (before continuous welds)",
            "Adjust if needed — break tacks and reposition",
        ],
        "tools": [
            "welding table",
            "clamps (C-clamps, bar clamps, quick-grip)",
            "magnetic squares and V-blocks",
            "framing square (24 inch minimum)",
            "level (48 inch for large work)",
            "measuring tape",
        ],
        "consumables": [],
        "applies_when": ["all_welded_assemblies"],
        "skip_when": [],
        "labor_type": "per_piece",
        "time_minutes": {
            "simple_frame_joint": 5,
            "precision_decorative": 8,     # measure, position, clamp, tack, verify
            "complex_multi_member": 12,
        },
        "notes": (
            "Always tack all corners before continuous welds. "
            "Check square at every stage, not just at the end. "
            "Weld seams before cosmetic grinding."
        ),
        "safety": [],
        "NEVER": [],
    },

    # SHOP: CreateStage — sequential assembly for decorative patterns
    "sequential_decorative_assembly": {
        "name": "Sequential Decorative Assembly",
        "category": "assembly",
        "steps": [
            "Measure step distance from previous piece",  # SHOP: CreateStage
            "Mark reference lines or use spacer/jig",  # SHOP: CreateStage
            "Position piece against spacer, check flush and level",  # SHOP: CreateStage
            "Clamp or hold",  # SHOP: CreateStage
            "Tack — check position hasn't shifted, adjust if needed",  # SHOP: CreateStage
            "Weld both sides (face weld + edge weld on flat bar)",  # SHOP: CreateStage
            "Move to next piece — reset spacer, repeat",  # SHOP: CreateStage
        ],
        "tools": [
            "measuring tape",
            "spacer jig or individual spacers",
            "clamps",
            "welder (MIG or TIG)",
        ],
        "consumables": [],
        "applies_when": [
            "flat_bar_pyramid",
            "concentric_square_pattern",
            "evenly_spaced_pickets",
            "ornamental_grids",
            "stepped_inlays",
        ],
        "skip_when": ["structural_frame"],
        "labor_type": "per_piece",
        "time_minutes": {
            "with_jig": 4.0,          # SHOP: CreateStage — Burton's practiced rate
            "without_jig": 10.0,       # measuring each piece individually
            "standard": 6.5,           # average skilled fabricator
        },
        "notes": (
            "Each piece: measure → position → weld → next piece. "  # SHOP: CreateStage
            "NOT dry-fit entire pattern first. "  # SHOP: CreateStage
            "Dominating labor category on decorative furniture jobs. "
            "120 pieces at 5 min = 10 hrs. At 8 min = 16 hrs."
        ),
        "safety": [],
        # SHOP: CreateStage — sequential, not dry-fit-then-weld
        "NEVER": [
            "dry-fit entire pattern before welding",
            "estimate as simple tack welds",
            "skip individual measurement per piece",
        ],
    },

    # ===================================================================
    # LAYOUT AND MEASUREMENT
    # ===================================================================

    "layout_and_mark": {
        "name": "Layout and Marking",
        "category": "layout",
        "steps": [
            "Review cut list and drawings",
            "Transfer dimensions to raw stock — measuring tape + marker",
            "Mark cut lines clearly — silver marker on dark steel, soapstone on bright",
            "Mark miter angles with speed square",
            "Number each piece for assembly reference",
            "Verify all dimensions before cutting",
        ],
        "tools": [
            "measuring tape (25 ft minimum)",
            "silver marker (Sharpie metallic)",
            "soapstone",
            "speed square",
            "combination square",
            "scribe (for precision marks)",
            "center punch (for drill locations)",
        ],
        "consumables": ["silver_markers", "soapstone"],
        "applies_when": ["all_jobs"],
        "skip_when": [],
        "labor_type": "per_piece",
        "time_minutes": {
            "simple_per_piece": 3,     # straight cut, one dimension
            "complex_per_piece": 12,   # multiple dimensions, angles, hole locations
        },
        "notes": "Measure twice, cut once. Layout before any cuts.",
        "safety": [],
        "NEVER": [],
    },

    # ===================================================================
    # HARDWARE AND INSTALL
    # ===================================================================

    "hardware_install": {
        "name": "Hardware Installation",
        "category": "install",
        "steps": [
            "Verify all hardware against cut list / BOM",
            "Test-fit before permanent installation where possible",
            "Install using appropriate fasteners and torque specs",
            "Verify operation (hinges swing, latches close, wheels roll)",
        ],
        "tools": [
            "drill / impact driver",
            "socket set",
            "wrenches",
            "level",
        ],
        "consumables": ["fasteners"],
        "applies_when": ["hardware_required"],
        "skip_when": [],
        "labor_type": "per_piece",
        "time_minutes": {
            "simple_item": 15,         # hinge, latch, handle
            "complex_item": 30,        # operator, motor, closer
            "gate_operator": 90,       # 1.5 hrs for motor install
        },
        "notes": "Always verify hardware fit BEFORE surface finishing. Mock-install before powder coat.",
        "safety": [],
        "NEVER": [],
    },

    "site_install": {
        "name": "Field / Site Installation",
        "category": "install",
        "steps": [
            "Transport finished product to site",
            "Verify site conditions match shop measurements",
            "Set and level — shim as needed",
            "Anchor per spec (lag bolts, epoxy anchors, concrete embed, weld)",
            "Final adjustments (gate swing, railing plumb, stair level)",
            "Touch up any field damage to finish",
            "Clean up site",
        ],
        "tools": [
            "transport vehicle / trailer",
            "level (48 inch)",
            "drill with masonry bits",
            "concrete anchors (Hilti or equivalent)",
            "shims",
            "field welder (if field welding required)",
            "touch-up paint or clear coat",
        ],
        "consumables": ["concrete_anchors", "touchup_materials"],
        "applies_when": ["installation_included"],
        "skip_when": ["shop_pickup", "no_install"],
        "labor_type": "active",
        "time_minutes": {
            "railing_per_10lf": 120,       # 2 hrs per 10 LF
            "gate_without_concrete": 180,   # 3 hrs
            "gate_with_concrete": 480,      # 8 hrs (posts, concrete, cure, hang)
            "stair_flight": 480,            # 8 hrs typical
            "bollard_each": 90,             # 1.5 hrs per bollard
            "furniture_delivery": 60,       # 1 hr deliver + place
        },
        "notes": "Field rate is ALWAYS higher than shop rate ($145+ vs $125). No discounts on field time.",
        "safety": [
            "Hard hat on construction sites",
            "Steel-toe boots",
            "High-viz vest if traffic is present",
            "Fall protection above 6 feet",
        ],
        "NEVER": [],
    },

    "final_inspection": {
        "name": "Final Inspection and QC",
        "category": "install",
        "steps": [
            "Visual inspection of all welds",
            "Check critical dimensions against drawings",
            "Verify finish coverage and consistency",
            "Test all moving parts (gates, doors, hinges)",
            "Document with photos for record",
            "Touch up any imperfections",
        ],
        "tools": [
            "measuring tape",
            "level",
            "flashlight (for weld inspection)",
            "fillet gauge (if spec requires)",
        ],
        "consumables": [],
        "applies_when": ["all_jobs"],
        "skip_when": [],
        "labor_type": "active",
        "time_minutes": {
            "minimum": 15,
            "standard": 30,
            "complex_assembly": 45,
        },
        "notes": "Always at least 0.25-0.5 hrs. Final walkthrough and touch-up.",
        "safety": [],
        "NEVER": [],
    },

    # ===================================================================
    # BENDING AND FORMING
    # ===================================================================

    "press_brake_bend": {
        "name": "Press Brake Bending",
        "category": "forming",
        "steps": [
            "Calculate bend allowance and deduction for material/thickness/radius",
            "Mark bend lines on flat stock",
            "Set press brake die and punch for desired radius",
            "Set backstop for bend location",
            "Test bend on scrap piece",
            "Bend production parts — verify angle with protractor after each",
        ],
        "tools": [
            "press brake",
            "V-die set (various widths)",
            "punch (various radii)",
            "angle protractor",
        ],
        "consumables": [],
        "applies_when": [
            "sheet_metal_enclosures",
            "formed_brackets",
            "custom_channels",
        ],
        "skip_when": ["tube_work", "bar_work"],
        "labor_type": "per_piece",
        "time_minutes": {
            "setup_first_bend": 15,
            "per_bend_production": 2,
            "complex_multi_bend": 5,
        },
        "notes": (
            "Bend allowance = pi/180 * angle * (radius + k_factor * thickness). "
            "K-factor for mild steel: 0.33 (air bend), 0.50 (bottom bend). "
            "Minimum bend radius = material thickness for mild steel."
        ),
        "safety": [
            "Keep fingers clear of die",
            "Two-hand operation or foot pedal",
            "Safety glasses — material can spring",
        ],
        "NEVER": [],
    },

    "tube_rolling": {
        "name": "Tube / Bar Rolling (Curved Bending)",
        "category": "forming",
        "steps": [
            "Calculate required radius from drawings",
            "Set roller positions for initial pass",
            "Feed material through rollers — multiple passes, incrementally tighter",
            "Check radius with template after each pass",
            "Final adjustment for springback",
        ],
        "tools": [
            "tube roller / ring roller",
            "radius template (plywood or cardboard)",
        ],
        "consumables": [],
        "applies_when": [
            "curved_railings",
            "arched_gates",
            "circular_frames",
            "spiral_elements",
        ],
        "skip_when": ["straight_work"],
        "labor_type": "per_piece",
        "time_minutes": {
            "setup": 15,
            "per_foot_of_curve": 5,
        },
        "notes": (
            "Springback varies by material and wall thickness. "
            "Always over-bend slightly and check against template. "
            "Rolled tube has slight egg-shaping — acceptable for most ornamental work."
        ),
        "safety": ["Keep fingers clear of rollers", "Material whips on exit — clear area"],
        "NEVER": [],
    },

    # ===================================================================
    # DRILLING
    # ===================================================================

    "drilling": {
        "name": "Drilling and Hole-Making",
        "category": "drilling",
        "steps": [
            "Center punch hole location",
            "Start with pilot drill if hole > 3/8 inch",
            "Drill to final size — use cutting fluid on steel",
            "Deburr both sides of hole",
            "Tap if threaded hole required",
        ],
        "tools": [
            "drill press (shop) or mag drill (field)",
            "drill bits (HSS or cobalt for stainless)",
            "center punch",
            "cutting fluid",
            "deburring tool or countersink",
            "taps and tap handle (if threading)",
        ],
        "consumables": ["drill_bits", "cutting_fluid", "taps"],
        "applies_when": ["bolt_holes", "mounting_holes", "drainage_holes"],
        "skip_when": [],
        "labor_type": "per_piece",
        "time_minutes": {
            "per_hole_mild_steel": 3,
            "per_hole_stainless": 5,
            "per_tapped_hole": 5,
            "setup_mag_drill_field": 10,
        },
        "notes": (
            "Cobalt or carbide bits for stainless — HSS work-hardens stainless on contact. "
            "Always use cutting fluid. Slow RPM for large holes."
        ),
        "safety": [
            "Clamp work — NEVER hand-hold while drilling",
            "Safety glasses — chips are hot",
            "Long hair tied back",
        ],
        "NEVER": [],
    },

    # ===================================================================
    # LEVELER / FURNITURE HARDWARE
    # ===================================================================

    # SHOP: CreateStage — correct method for threaded leveler feet on hollow tube
    "leveler_foot_install": {
        "name": "Leveler Foot Installation (Weld-In Threaded Bung)",
        "category": "install",
        "steps": [
            "Weld threaded bung (3/8-16) into bottom of each tube leg",
            "Bung sits flush with tube end — full fillet weld around perimeter",
            "Let cool, then thread leveling foot into bung",
            "Adjust all feet until table sits level on flat surface",
        ],
        "tools": [
            "MIG or TIG welder",
            "level",
            "adjustable wrench",
        ],
        "consumables": [],
        "applies_when": [
            "furniture_table",
            "furniture_other",
            "adjustable_feet",
            "leveling_feet",
        ],
        "skip_when": [
            "solid_bar_legs",
            "no_levelers",
        ],
        "labor_type": "per_piece",
        "time_minutes": {
            "weld_plate": 12,   # weld a flat plate with threaded hole — slower
            "weld_bung": 8,     # weld-in threaded bung — faster, preferred
        },
        "notes": (
            "Hollow square tube has NO MEAT to tap threads into. "
            "You MUST weld in a threaded bung or plate to accept leveling feet. "
            "3/8-16 is the standard thread for furniture levelers. "
            "Bung method preferred — faster, cleaner, stronger than plate method."
        ),
        "safety": [
            "Small weld area — good ventilation still required",
        ],
        "NEVER": [
            "drill into tube",
            "drill into the tube",
            "drill through tube wall",
            "drill and tap tube wall",
            "tap directly into tube",
            "self-tapping screw into tube",
        ],
    },
}


# ---------------------------------------------------------------------------
# PROCESS LOOKUP HELPERS
# ---------------------------------------------------------------------------

def get_process(name):
    """Get a process dict by name. Returns None if not found."""
    return PROCESSES.get(name)


def get_processes_by_category(category):
    """Return all processes in a category."""
    return {k: v for k, v in PROCESSES.items() if v.get("category") == category}


def get_applicable_processes(conditions):
    """Return processes where any condition in `conditions` matches `applies_when`."""
    result = {}
    conditions_set = set(c.lower() for c in conditions)
    for name, proc in PROCESSES.items():
        applies = set(a.lower() for a in proc.get("applies_when", []))
        if applies & conditions_set:
            result[name] = proc
    return result


def get_banned_terms(process_name):
    """Return the NEVER list for a process."""
    proc = PROCESSES.get(process_name, {})
    return proc.get("NEVER", [])
