"""
Material specifications — every common structural/ornamental metal
with mechanical properties, weld compatibility, profiles, and cost ranges.

Sources: ASTM A36, A500, A513, A304, A316 specs; AISC Steel Construction
Manual 15th Ed; Lincoln Electric welding guide; distributor catalogs
(Metals Depot, Online Metals, McNichols, Ryerson).

Cost ranges are Chicago-area 2024-2026 averages. Actual prices vary
by supplier, quantity, and market conditions.
"""

# ---------------------------------------------------------------------------
# BASE MATERIALS
# ---------------------------------------------------------------------------
# Each material has:
#   name            — common name
#   spec            — ASTM or industry specification
#   yield_psi       — minimum yield strength (PSI)
#   ultimate_psi    — minimum ultimate tensile strength (PSI)
#   elongation_pct  — minimum elongation at break (%)
#   density_lb_in3  — density in lb/cubic inch
#   density_lb_ft3  — density in lb/cubic foot
#   weld_process    — recommended weld processes (ordered by preference)
#   weld_filler     — recommended filler metals
#   shield_gas      — recommended shielding gases
#   preheat         — preheat requirements
#   distortion_risk — "low" | "medium" | "high"
#   machinability   — relative difficulty to cut/drill/tap
#   cost_per_lb     — typical cost range (low, high) in $/lb
#   notes           — practical shop notes

MATERIALS = {

    "mild_steel_a36": {
        "name": "Mild Steel (A36)",
        "spec": "ASTM A36",
        "forms": ["plate", "bar", "angle", "channel", "wide flange", "sheet"],
        "yield_psi": 36000,
        "ultimate_psi": 58000,
        "elongation_pct": 20,
        "density_lb_in3": 0.2836,
        "density_lb_ft3": 490,
        "weld_process": ["mig", "tig", "stick", "flux_core"],
        "weld_filler": {
            "mig": "ER70S-6",
            "tig": "ER70S-2",
            "stick": "E7018 (structural), E6013 (light)",
            "flux_core": "E71T-1 (gas-shielded), E71T-11 (self-shielded)",
        },
        "shield_gas": {
            "mig": "75/25 Ar/CO2 (standard), 100% CO2 (budget, more spatter)",
            "tig": "100% Argon",
        },
        "preheat": "None required for thickness <= 1 inch in normal shop conditions (>50F). Preheat 200-400F for >1 inch, high restraint, or cold conditions (<32F).",
        "distortion_risk": "low_to_medium",
        "machinability": "good",
        "cost_per_lb": {"low": 0.50, "high": 0.85},
        "notes": (
            "Most common shop material. Excellent weldability. "
            "ER70S-6 wire handles light mill scale (triple deoxidized). "
            "No special precautions for most shop work."
        ),
    },

    "mild_steel_a500": {
        "name": "Structural Steel Tubing (A500)",
        "spec": "ASTM A500 Grade B/C",
        "forms": ["square tube", "rectangular tube", "round tube"],
        "yield_psi": 46000,   # Grade B
        "ultimate_psi": 58000,
        "elongation_pct": 23,
        "density_lb_in3": 0.2836,
        "density_lb_ft3": 490,
        "weld_process": ["mig", "tig", "stick"],
        "weld_filler": {
            "mig": "ER70S-6",
            "tig": "ER70S-2",
            "stick": "E7018",
        },
        "shield_gas": {
            "mig": "75/25 Ar/CO2",
            "tig": "100% Argon",
        },
        "preheat": "None for standard wall thicknesses (11ga-14ga).",
        "distortion_risk": "medium",
        "machinability": "good",
        "cost_per_lb": {"low": 0.65, "high": 1.10},
        "notes": (
            "Primary structural tube spec. Higher yield than A36 plate. "
            "ERW (Electric Resistance Welded) seam — orient seam away from "
            "visible surfaces for architectural work."
        ),
    },

    "mild_steel_a513": {
        "name": "Mechanical Steel Tubing (A513)",
        "spec": "ASTM A513",
        "forms": ["square tube", "rectangular tube", "round tube"],
        "yield_psi": 32000,
        "ultimate_psi": 45000,
        "elongation_pct": 25,
        "density_lb_in3": 0.2836,
        "density_lb_ft3": 490,
        "weld_process": ["mig", "tig"],
        "weld_filler": {
            "mig": "ER70S-6",
            "tig": "ER70S-2",
        },
        "shield_gas": {
            "mig": "75/25 Ar/CO2",
            "tig": "100% Argon",
        },
        "preheat": "None.",
        "distortion_risk": "medium",
        "machinability": "excellent",
        "cost_per_lb": {"low": 0.60, "high": 1.00},
        "notes": (
            "Ornamental/mechanical tube — tighter tolerances than A500. "
            "Lower yield but better surface finish. Common in furniture and railing."
        ),
    },

    "stainless_304": {
        "name": "Stainless Steel 304",
        "spec": "ASTM A240 (sheet/plate), A554 (tube), A276 (bar)",
        "forms": ["sheet", "plate", "tube", "bar", "angle"],
        "yield_psi": 30000,
        "ultimate_psi": 75000,
        "elongation_pct": 40,
        "density_lb_in3": 0.289,
        "density_lb_ft3": 499,
        "weld_process": ["tig", "mig"],
        "weld_filler": {
            "tig": "ER308L (standard), ER309L (dissimilar to mild steel)",
            "mig": "ER308LSi",
        },
        "shield_gas": {
            "tig": "100% Argon. Back-purge with argon for full-pen tube welds.",
            "mig": "98/2 Ar/CO2 or tri-mix (Ar/He/CO2)",
        },
        "preheat": "NONE — preheat sensitizes stainless (causes carbide precipitation and intergranular corrosion).",
        "distortion_risk": "high",
        "machinability": "poor",
        "cost_per_lb": {"low": 2.80, "high": 4.00},
        "notes": (
            "ALWAYS use stainless filler (ER308L) — mild steel filler will rust at weld. "
            "DEDICATE grinding wheels, wire brushes, clamps — carbon steel contamination causes rust. "
            "TIG preferred. Keep heat input LOW. "
            "Back-purge argon for full-pen welds on tube (prevents sugaring). "
            "Harder to cut — lower RPM, stainless-rated blades. "
            "Labor multiplier: 1.3-1.5x mild steel."
        ),
    },

    "stainless_316": {
        "name": "Stainless Steel 316 (Marine Grade)",
        "spec": "ASTM A240 (sheet/plate), A554 (tube), A276 (bar)",
        "forms": ["sheet", "plate", "tube", "bar"],
        "yield_psi": 30000,
        "ultimate_psi": 75000,
        "elongation_pct": 40,
        "density_lb_in3": 0.289,
        "density_lb_ft3": 499,
        "weld_process": ["tig", "mig"],
        "weld_filler": {
            "tig": "ER316L",
            "mig": "ER316LSi",
        },
        "shield_gas": {
            "tig": "100% Argon. Back-purge required.",
            "mig": "98/2 Ar/CO2",
        },
        "preheat": "NONE.",
        "distortion_risk": "high",
        "machinability": "poor",
        "cost_per_lb": {"low": 3.80, "high": 5.00},
        "notes": (
            "Molybdenum addition = better chloride/pitting resistance. "
            "Use for marine, coastal, chemical environments. "
            "Same welding rules as 304 but MUST use 316L filler (not 308L)."
        ),
    },

    "aluminum_6061": {
        "name": "Aluminum 6061-T6",
        "spec": "ASTM B221 (extrusion), B209 (sheet/plate)",
        "forms": ["sheet", "plate", "tube", "bar", "angle", "extrusion"],
        "yield_psi": 40000,   # T6 temper
        "ultimate_psi": 45000,
        "elongation_pct": 12,
        "density_lb_in3": 0.098,
        "density_lb_ft3": 169,
        "weld_process": ["tig", "mig"],
        "weld_filler": {
            "tig": "4043 (general), 5356 (structural, better color match for anodize)",
            "mig": "4043 or 5356 with spool gun",
        },
        "shield_gas": {
            "tig": "100% Argon (AC mode)",
            "mig": "100% Argon",
        },
        "preheat": "Not required but helpful for thick sections (150-200F max — T6 temper degrades at higher temps).",
        "distortion_risk": "high",
        "machinability": "excellent",
        "cost_per_lb": {"low": 1.50, "high": 2.50},
        "notes": (
            "TIG requires AC mode (DC won't clean oxide layer). "
            "HAZ (heat-affected zone) loses T6 temper — drops to ~T0 at weld (50% strength reduction). "
            "5356 filler for structural, 4043 for general/cosmetic. "
            "Labor multiplier: 1.2x mild steel."
        ),
    },

    "aluminum_5052": {
        "name": "Aluminum 5052-H32",
        "spec": "ASTM B209",
        "forms": ["sheet", "plate"],
        "yield_psi": 28000,   # H32 temper
        "ultimate_psi": 33000,
        "elongation_pct": 12,
        "density_lb_in3": 0.097,
        "density_lb_ft3": 168,
        "weld_process": ["tig", "mig"],
        "weld_filler": {
            "tig": "5356",
            "mig": "5356",
        },
        "shield_gas": {
            "tig": "100% Argon (AC mode)",
            "mig": "100% Argon",
        },
        "preheat": "Not required.",
        "distortion_risk": "high",
        "machinability": "good",
        "cost_per_lb": {"low": 1.30, "high": 2.20},
        "notes": (
            "Best aluminum alloy for forming and welding. "
            "Better corrosion resistance than 6061. "
            "Common for sheet metal enclosures and marine work. "
            "NEVER use 4043 filler on 5052 — causes cracking."
        ),
    },

    "dom_tube": {
        "name": "DOM Round Tube (Drawn Over Mandrel)",
        "spec": "ASTM A513 Type 5 (DOM)",
        "forms": ["round tube"],
        "yield_psi": 70000,   # cold-drawn
        "ultimate_psi": 80000,
        "elongation_pct": 10,
        "density_lb_in3": 0.2836,
        "density_lb_ft3": 490,
        "weld_process": ["mig", "tig"],
        "weld_filler": {
            "mig": "ER70S-6",
            "tig": "ER70S-2",
        },
        "shield_gas": {
            "mig": "75/25 Ar/CO2",
            "tig": "100% Argon",
        },
        "preheat": "None for standard wall.",
        "distortion_risk": "medium",
        "machinability": "good",
        "cost_per_lb": {"low": 2.00, "high": 3.20},
        "notes": (
            "Seamless appearance (no visible weld seam), tighter tolerances than ERW. "
            "Premium cost but required for decorative work where seam would show. "
            "Weld same as ERW — DOM is a manufacturing process, not a composition change."
        ),
    },
}


# ---------------------------------------------------------------------------
# STANDARD PROFILES
# ---------------------------------------------------------------------------
# Each profile has:
#   shape           — profile shape category
#   dimensions      — nominal size description
#   key             — lookup key matching material_lookup.py
#   weight_per_foot — weight in lb/ft
#   wall_thickness  — wall or material thickness (inches)
#   perimeter_inches — cross-section perimeter for weld length calc
#   cost_per_foot   — typical cost range (low, high)
#   common_material — typical material spec
#   common_uses     — what this profile is used for

PROFILES = {

    # --- Square Tube ---
    "sq_tube_1x1_14ga": {
        "shape": "square_tube",
        "dimensions": "1 x 1 x 14ga (0.075 wall)",
        "key": "sq_tube_1x1_14ga",
        "weight_per_foot": 0.68,
        "wall_thickness": 0.075,
        "outside_dimension": 1.0,
        "perimeter_inches": 4.0,
        "cost_per_foot": {"low": 0.80, "high": 1.50},
        "common_material": "A500 Grade B",
        "common_uses": ["small furniture", "light frames", "infill", "ornamental"],
    },
    "sq_tube_1.5x1.5_11ga": {
        "shape": "square_tube",
        "dimensions": "1.5 x 1.5 x 11ga (0.120 wall)",
        "key": "sq_tube_1.5x1.5_11ga",
        "weight_per_foot": 2.47,
        "wall_thickness": 0.120,
        "outside_dimension": 1.5,
        "perimeter_inches": 6.0,
        "cost_per_foot": {"low": 1.80, "high": 3.00},
        "common_material": "A500 Grade B",
        "common_uses": ["furniture frames", "railing posts", "gate frames", "general fab"],
    },
    "sq_tube_2x2_11ga": {
        "shape": "square_tube",
        "dimensions": "2 x 2 x 11ga (0.120 wall)",
        "key": "sq_tube_2x2_11ga",
        "weight_per_foot": 3.41,
        "wall_thickness": 0.120,
        "outside_dimension": 2.0,
        "perimeter_inches": 8.0,
        "cost_per_foot": {"low": 2.50, "high": 4.00},
        "common_material": "A500 Grade B",
        "common_uses": ["gate frames", "furniture legs", "railing top rail", "fence posts"],
    },
    "sq_tube_2x2_14ga": {
        "shape": "square_tube",
        "dimensions": "2 x 2 x 14ga (0.075 wall)",
        "key": "sq_tube_2x2_14ga",
        "weight_per_foot": 2.27,
        "wall_thickness": 0.075,
        "outside_dimension": 2.0,
        "perimeter_inches": 8.0,
        "cost_per_foot": {"low": 2.00, "high": 3.20},
        "common_material": "A500 Grade B",
        "common_uses": ["light frames", "sign frames", "furniture (non-structural)"],
    },
    "sq_tube_3x3_11ga": {
        "shape": "square_tube",
        "dimensions": "3 x 3 x 11ga (0.120 wall)",
        "key": "sq_tube_3x3_11ga",
        "weight_per_foot": 5.32,
        "wall_thickness": 0.120,
        "outside_dimension": 3.0,
        "perimeter_inches": 12.0,
        "cost_per_foot": {"low": 4.00, "high": 6.50},
        "common_material": "A500 Grade B",
        "common_uses": ["gate posts", "structural columns", "heavy frames"],
    },
    "sq_tube_4x4_11ga": {
        "shape": "square_tube",
        "dimensions": "4 x 4 x 11ga (0.120 wall)",
        "key": "sq_tube_4x4_11ga",
        "weight_per_foot": 7.22,
        "wall_thickness": 0.120,
        "outside_dimension": 4.0,
        "perimeter_inches": 16.0,
        "cost_per_foot": {"low": 5.50, "high": 9.00},
        "common_material": "A500 Grade B",
        "common_uses": ["cantilever gate posts", "structural columns", "bollard sleeves"],
    },

    # --- Rectangular Tube ---
    "rect_tube_2x3_11ga": {
        "shape": "rectangular_tube",
        "dimensions": "2 x 3 x 11ga (0.120 wall)",
        "key": "rect_tube_2x3_11ga",
        "weight_per_foot": 4.32,
        "wall_thickness": 0.120,
        "outside_dimension": 3.0,
        "perimeter_inches": 10.0,
        "cost_per_foot": {"low": 3.20, "high": 5.50},
        "common_material": "A500 Grade B",
        "common_uses": ["gate frames", "structural beams", "bumper structures"],
    },
    "rect_tube_2x4_11ga": {
        "shape": "rectangular_tube",
        "dimensions": "2 x 4 x 11ga (0.120 wall)",
        "key": "rect_tube_2x4_11ga",
        "weight_per_foot": 5.32,
        "wall_thickness": 0.120,
        "outside_dimension": 4.0,
        "perimeter_inches": 12.0,
        "cost_per_foot": {"low": 4.00, "high": 6.50},
        "common_material": "A500 Grade B",
        "common_uses": ["trailer frames", "heavy gate frames", "structural beams"],
    },

    # --- Round Tube ---
    "round_tube_1.5_14ga": {
        "shape": "round_tube",
        "dimensions": "1.5 OD x 14ga (0.075 wall)",
        "key": "round_tube_1.5_14ga",
        "weight_per_foot": 1.12,
        "wall_thickness": 0.075,
        "outside_dimension": 1.5,
        "perimeter_inches": 4.7,
        "cost_per_foot": {"low": 1.20, "high": 2.20},
        "common_material": "A513",
        "common_uses": ["handrail", "railing balusters", "decorative accents"],
    },
    "round_tube_2_11ga": {
        "shape": "round_tube",
        "dimensions": "2 OD x 11ga (0.120 wall)",
        "key": "round_tube_2_11ga",
        "weight_per_foot": 2.67,
        "wall_thickness": 0.120,
        "outside_dimension": 2.0,
        "perimeter_inches": 6.3,
        "cost_per_foot": {"low": 2.50, "high": 4.00},
        "common_material": "A500 Grade B",
        "common_uses": ["railing top rail", "structural round frames"],
    },

    # --- DOM Tube ---
    "dom_tube_1.75x0.120": {
        "shape": "dom_tube",
        "dimensions": "1.75 OD x 0.120 wall DOM",
        "key": "dom_tube_1.75x0.120",
        "weight_per_foot": 2.06,
        "wall_thickness": 0.120,
        "outside_dimension": 1.75,
        "perimeter_inches": 5.5,
        "cost_per_foot": {"low": 4.00, "high": 7.00},
        "common_material": "A513 Type 5 (DOM)",
        "common_uses": ["roll cages", "rock sliders", "offroad bumpers", "show-quality round work"],
    },

    # --- Flat Bar ---
    "flat_bar_1x0.125": {
        "shape": "flat_bar",
        "dimensions": "1 wide x 1/8 thick",
        "key": "flat_bar_1x0.125",
        "weight_per_foot": 0.425,
        "wall_thickness": 0.125,
        "outside_dimension": 1.0,
        "perimeter_inches": 2.25,
        "cost_per_foot": {"low": 0.80, "high": 1.40},
        "common_material": "A36 HR",
        "common_uses": ["decorative patterns", "pyramid layers", "ornamental infill"],
    },
    "flat_bar_1x0.1875": {
        "shape": "flat_bar",
        "dimensions": "1 wide x 3/16 thick",
        "key": "flat_bar_1x0.1875",
        "weight_per_foot": 0.638,
        "wall_thickness": 0.1875,
        "outside_dimension": 1.0,
        "perimeter_inches": 2.375,
        "cost_per_foot": {"low": 1.00, "high": 1.70},
        "common_material": "A36 HR",
        "common_uses": ["decorative patterns", "heavier ornamental work"],
    },
    "flat_bar_1x0.25": {
        "shape": "flat_bar",
        "dimensions": "1 wide x 1/4 thick",
        "key": "flat_bar_1x0.25",
        "weight_per_foot": 0.85,
        "wall_thickness": 0.25,
        "outside_dimension": 1.0,
        "perimeter_inches": 2.5,
        "cost_per_foot": {"low": 1.10, "high": 1.90},
        "common_material": "A36 HR",
        "common_uses": ["structural flat bar", "cross-bracing", "base plate strips"],
    },
    "flat_bar_1.5x0.25": {
        "shape": "flat_bar",
        "dimensions": "1.5 wide x 1/4 thick",
        "key": "flat_bar_1.5x0.25",
        "weight_per_foot": 1.28,
        "wall_thickness": 0.25,
        "outside_dimension": 1.5,
        "perimeter_inches": 3.5,
        "cost_per_foot": {"low": 1.50, "high": 2.60},
        "common_material": "A36 HR",
        "common_uses": ["fence picket tops", "heavy decorative", "structural ties"],
    },
    "flat_bar_2x0.25": {
        "shape": "flat_bar",
        "dimensions": "2 wide x 1/4 thick",
        "key": "flat_bar_2x0.25",
        "weight_per_foot": 1.70,
        "wall_thickness": 0.25,
        "outside_dimension": 2.0,
        "perimeter_inches": 4.5,
        "cost_per_foot": {"low": 1.90, "high": 3.30},
        "common_material": "A36 HR",
        "common_uses": ["wide flat bar work", "stair treads", "structural connections"],
    },
    "flat_bar_3x0.25": {
        "shape": "flat_bar",
        "dimensions": "3 wide x 1/4 thick",
        "key": "flat_bar_3x0.25",
        "weight_per_foot": 2.55,
        "wall_thickness": 0.25,
        "outside_dimension": 3.0,
        "perimeter_inches": 6.5,
        "cost_per_foot": {"low": 2.80, "high": 4.80},
        "common_material": "A36 HR",
        "common_uses": ["stair stringers", "base plates", "wide structural ties"],
    },

    # --- Angle Iron ---
    "angle_1.5x1.5x0.125": {
        "shape": "angle",
        "dimensions": "1.5 x 1.5 x 1/8",
        "key": "angle_1.5x1.5x0.125",
        "weight_per_foot": 1.23,
        "wall_thickness": 0.125,
        "outside_dimension": 1.5,
        "perimeter_inches": 6.0,
        "cost_per_foot": {"low": 1.20, "high": 2.00},
        "common_material": "A36",
        "common_uses": ["shelf brackets", "light framing", "edge trim"],
    },
    "angle_2x2x0.1875": {
        "shape": "angle",
        "dimensions": "2 x 2 x 3/16",
        "key": "angle_2x2x0.1875",
        "weight_per_foot": 2.44,
        "wall_thickness": 0.1875,
        "outside_dimension": 2.0,
        "perimeter_inches": 8.0,
        "cost_per_foot": {"low": 2.00, "high": 3.50},
        "common_material": "A36",
        "common_uses": ["frame reinforcement", "stair stringer support", "equipment mounts"],
    },
    "angle_2x2x0.25": {
        "shape": "angle",
        "dimensions": "2 x 2 x 1/4",
        "key": "angle_2x2x0.25",
        "weight_per_foot": 3.19,
        "wall_thickness": 0.25,
        "outside_dimension": 2.0,
        "perimeter_inches": 8.0,
        "cost_per_foot": {"low": 2.50, "high": 4.20},
        "common_material": "A36",
        "common_uses": ["structural angle", "cross-bracing", "equipment frames"],
    },

    # --- Square Bar ---
    "sq_bar_0.5": {
        "shape": "square_bar",
        "dimensions": "1/2 inch solid square",
        "key": "sq_bar_0.5",
        "weight_per_foot": 0.85,
        "wall_thickness": 0.5,   # solid
        "outside_dimension": 0.5,
        "perimeter_inches": 2.0,
        "cost_per_foot": {"low": 1.00, "high": 1.80},
        "common_material": "A36 HR or CR",
        "common_uses": ["pickets", "balusters", "ornamental elements"],
    },
    "sq_bar_0.625": {
        "shape": "square_bar",
        "dimensions": "5/8 inch solid square",
        "key": "sq_bar_0.625",
        "weight_per_foot": 1.33,
        "wall_thickness": 0.625,
        "outside_dimension": 0.625,
        "perimeter_inches": 2.5,
        "cost_per_foot": {"low": 1.50, "high": 2.50},
        "common_material": "A36 HR or CR",
        "common_uses": ["heavy pickets", "ornamental elements"],
    },
    "sq_bar_0.75": {
        "shape": "square_bar",
        "dimensions": "3/4 inch solid square",
        "key": "sq_bar_0.75",
        "weight_per_foot": 1.92,
        "wall_thickness": 0.75,
        "outside_dimension": 0.75,
        "perimeter_inches": 3.0,
        "cost_per_foot": {"low": 2.00, "high": 3.30},
        "common_material": "A36 HR or CR",
        "common_uses": ["heavy ornamental", "gate infill", "structural bars"],
    },

    # --- Round Bar ---
    "round_bar_0.5": {
        "shape": "round_bar",
        "dimensions": "1/2 inch solid round",
        "key": "round_bar_0.5",
        "weight_per_foot": 0.67,
        "wall_thickness": 0.5,
        "outside_dimension": 0.5,
        "perimeter_inches": 1.57,
        "cost_per_foot": {"low": 0.80, "high": 1.50},
        "common_material": "A36 HR or 1018 CR",
        "common_uses": ["round balusters", "handles", "decorative scrollwork"],
    },
    "round_bar_0.625": {
        "shape": "round_bar",
        "dimensions": "5/8 inch solid round",
        "key": "round_bar_0.625",
        "weight_per_foot": 1.04,
        "wall_thickness": 0.625,
        "outside_dimension": 0.625,
        "perimeter_inches": 1.96,
        "cost_per_foot": {"low": 1.10, "high": 2.00},
        "common_material": "A36 HR or 1018 CR",
        "common_uses": ["heavy balusters", "structural rods"],
    },

    # --- Channel ---
    "channel_4x5.4": {
        "shape": "channel",
        "dimensions": "C4 x 5.4 (4 inch, 5.4 lb/ft)",
        "key": "channel_4x5.4",
        "weight_per_foot": 5.4,
        "wall_thickness": 0.184,  # web
        "outside_dimension": 4.0,
        "perimeter_inches": 8.0,
        "cost_per_foot": {"low": 4.00, "high": 6.50},
        "common_material": "A36",
        "common_uses": ["stair stringers", "trailer frames", "structural beams"],
    },
    "channel_6x8.2": {
        "shape": "channel",
        "dimensions": "C6 x 8.2 (6 inch, 8.2 lb/ft)",
        "key": "channel_6x8.2",
        "weight_per_foot": 8.2,
        "wall_thickness": 0.200,
        "outside_dimension": 6.0,
        "perimeter_inches": 12.0,
        "cost_per_foot": {"low": 6.00, "high": 10.00},
        "common_material": "A36",
        "common_uses": ["heavy structural", "trailer main rails", "mezzanine beams"],
    },

    # --- Pipe ---
    "pipe_3_sch40": {
        "shape": "pipe",
        "dimensions": "3 inch Schedule 40 (3.500 OD x 0.216 wall)",
        "key": "pipe_3_sch40",
        "weight_per_foot": 7.58,
        "wall_thickness": 0.216,
        "outside_dimension": 3.5,
        "perimeter_inches": 11.0,
        "cost_per_foot": {"low": 5.50, "high": 9.00},
        "common_material": "A53 Grade B",
        "common_uses": ["bollards", "railing posts", "flag poles", "structural columns"],
    },
    "pipe_4_sch40": {
        "shape": "pipe",
        "dimensions": "4 inch Schedule 40 (4.500 OD x 0.237 wall)",
        "key": "pipe_4_sch40",
        "weight_per_foot": 10.79,
        "wall_thickness": 0.237,
        "outside_dimension": 4.5,
        "perimeter_inches": 14.1,
        "cost_per_foot": {"low": 8.00, "high": 13.00},
        "common_material": "A53 Grade B",
        "common_uses": ["heavy bollards", "structural pipe columns"],
    },
    "pipe_6_sch40": {
        "shape": "pipe",
        "dimensions": "6 inch Schedule 40 (6.625 OD x 0.280 wall)",
        "key": "pipe_6_sch40",
        "weight_per_foot": 18.97,
        "wall_thickness": 0.280,
        "outside_dimension": 6.625,
        "perimeter_inches": 20.8,
        "cost_per_foot": {"low": 14.00, "high": 22.00},
        "common_material": "A53 Grade B",
        "common_uses": ["spiral stair center column", "heavy structural pipe"],
    },

    # --- Sheet / Plate ---
    "sheet_11ga": {
        "shape": "sheet",
        "dimensions": "11ga (0.120 inch) sheet",
        "key": "sheet_11ga",
        "weight_per_foot": 5.0,     # per sq ft
        "wall_thickness": 0.120,
        "outside_dimension": None,
        "perimeter_inches": None,
        "cost_per_foot": {"low": 4.00, "high": 7.00},   # per sq ft
        "common_material": "A36 HR",
        "common_uses": ["enclosure panels", "tread plate", "sign backing"],
    },
    "sheet_14ga": {
        "shape": "sheet",
        "dimensions": "14ga (0.075 inch) sheet",
        "key": "sheet_14ga",
        "weight_per_foot": 3.125,
        "wall_thickness": 0.075,
        "outside_dimension": None,
        "perimeter_inches": None,
        "cost_per_foot": {"low": 3.00, "high": 5.50},
        "common_material": "A36 HR or CR",
        "common_uses": ["light enclosures", "sign boxes", "decorative panels"],
    },
    "sheet_16ga": {
        "shape": "sheet",
        "dimensions": "16ga (0.060 inch) sheet",
        "key": "sheet_16ga",
        "weight_per_foot": 2.5,
        "wall_thickness": 0.060,
        "outside_dimension": None,
        "perimeter_inches": None,
        "cost_per_foot": {"low": 2.50, "high": 4.50},
        "common_material": "A36 CR",
        "common_uses": ["light panels", "channel letter faces"],
    },
    "plate_0.25": {
        "shape": "plate",
        "dimensions": "1/4 inch plate",
        "key": "plate_0.25",
        "weight_per_foot": 10.2,
        "wall_thickness": 0.25,
        "outside_dimension": None,
        "perimeter_inches": None,
        "cost_per_foot": {"low": 7.00, "high": 12.00},
        "common_material": "A36",
        "common_uses": ["base plates", "gussets", "bumper plate", "structural connections"],
    },
    "plate_0.375": {
        "shape": "plate",
        "dimensions": "3/8 inch plate",
        "key": "plate_0.375",
        "weight_per_foot": 15.3,
        "wall_thickness": 0.375,
        "outside_dimension": None,
        "perimeter_inches": None,
        "cost_per_foot": {"low": 10.00, "high": 17.00},
        "common_material": "A36",
        "common_uses": ["heavy base plates", "structural connections", "wear plates"],
    },
    "plate_0.5": {
        "shape": "plate",
        "dimensions": "1/2 inch plate",
        "key": "plate_0.5",
        "weight_per_foot": 20.4,
        "wall_thickness": 0.5,
        "outside_dimension": None,
        "perimeter_inches": None,
        "cost_per_foot": {"low": 14.00, "high": 23.00},
        "common_material": "A36",
        "common_uses": ["heavy structural", "anchor plates", "machinery bases"],
    },
}


# ---------------------------------------------------------------------------
# LABOR MULTIPLIERS BY MATERIAL
# ---------------------------------------------------------------------------

LABOR_MULTIPLIERS = {
    "mild_steel": 1.0,
    "stainless_304": 1.5,
    "stainless_316": 1.5,
    "aluminum_6061": 1.2,
    "aluminum_5052": 1.2,
    "dom_tube": 1.0,     # same as mild steel — it's the same base alloy
}


# ---------------------------------------------------------------------------
# SKILL MULTIPLIERS BY POSITION
# ---------------------------------------------------------------------------

POSITION_MULTIPLIERS = {
    "flat_1f_1g": 1.0,
    "horizontal_2f_2g": 1.2,
    "vertical_3f_3g": 1.4,
    "overhead_4f_4g": 1.7,
}


# ---------------------------------------------------------------------------
# FINISHING TIER MULTIPLIERS
# ---------------------------------------------------------------------------

FINISHING_TIERS = {
    "industrial_textured": {
        "name": "Industrial / Textured",
        "description": "1 pass, texture IS the finish",
        "multiplier": 1.0,
    },
    "smooth_brushed": {
        "name": "Smooth Brushed",
        "description": "Consistent directional grain",
        "multiplier": 1.5,
    },
    "satin": {
        "name": "Satin",
        "description": "Minimal scratches, soft sheen",
        "multiplier": 2.5,
    },
    "mirror_polish": {
        "name": "Mirror Polish",
        "description": "Reflective, no visible marks",
        "multiplier": 4.0,
    },
}


# ---------------------------------------------------------------------------
# COMPLEXITY FACTORS
# ---------------------------------------------------------------------------

COMPLEXITY_FACTORS = {
    "simple_familiar": {"description": "Simple, familiar job type", "multiplier": 1.0},
    "first_time_build": {"description": "First time building this job type", "multiplier": 1.3},
    "complex_fitting": {"description": "Complex fitting with tight tolerances", "multiplier": 1.2},
    "small_parts_tight_spaces": {"description": "Very small parts, tight spaces", "multiplier": 1.3},
    "thin_material_16ga": {"description": "Very thin material (<=16ga)", "multiplier": 1.4},
    "stainless_any": {"description": "Stainless, any thickness", "multiplier": 1.5},
    "customer_revision": {"description": "Customer revision mid-project", "multiplier": 1.5},
}


# ---------------------------------------------------------------------------
# DISTORTION RISK BY JOB TYPE
# ---------------------------------------------------------------------------

DISTORTION_RISK = {
    "furniture_table": {"risk": "high", "control": "Alternate welds, backstep"},
    "furniture_other": {"risk": "high", "control": "Alternate welds, backstep"},
    "straight_railing": {"risk": "medium", "control": "Tack sequence, balanced welding"},
    "stair_railing": {"risk": "medium", "control": "Tack sequence, balanced welding"},
    "balcony_railing": {"risk": "medium", "control": "Tack sequence, balanced welding"},
    "cantilever_gate": {"risk": "high", "control": "Pre-set, weld toward center"},
    "swing_gate": {"risk": "high", "control": "Pre-set, weld toward center"},
    "ornamental_fence": {"risk": "medium", "control": "Panel jig, tack all before weld"},
    "complete_stair": {"risk": "medium", "control": "Heavy members, tack sequence"},
    "spiral_stair": {"risk": "medium", "control": "Center column fixture"},
    "sign_frame": {"risk": "high", "control": "TIG or intermittent MIG on thin material"},
    "led_sign_custom": {"risk": "high", "control": "Intermittent welds, backstep"},
    "structural_frame": {"risk": "low", "control": "Mass absorbs heat"},
    "trailer_fab": {"risk": "low", "control": "Heavy channel, mass absorbs heat"},
    "bollard": {"risk": "low", "control": "Pipe mass, short welds"},
    "utility_enclosure": {"risk": "high", "control": "Sheet metal — TIG or intermittent"},
    "window_security_grate": {"risk": "low", "control": "Bar stock mass"},
    "offroad_bumper": {"risk": "medium", "control": "Plate and tube mass"},
    "rock_slider": {"risk": "low", "control": "DOM/tube mass"},
    "roll_cage": {"risk": "medium", "control": "Tube bending pre-sets geometry"},
    "exhaust_custom": {"risk": "high", "control": "Thin wall pipe — TIG required"},
    "repair_decorative": {"risk": "medium", "control": "Match existing, tack carefully"},
    "repair_structural": {"risk": "low", "control": "Existing mass stabilizes"},
    "custom_fab": {"risk": "medium", "control": "Varies — assess per project"},
    "product_firetable": {"risk": "medium", "control": "Sheet panel — clamp and tack"},
}


# ---------------------------------------------------------------------------
# LOOKUP HELPERS
# ---------------------------------------------------------------------------

def get_material(key):
    """Get a material dict by key."""
    return MATERIALS.get(key)


def get_profile(key):
    """Get a profile dict by key."""
    return PROFILES.get(key)


def get_profiles_by_shape(shape):
    """Return all profiles of a given shape."""
    return {k: v for k, v in PROFILES.items() if v.get("shape") == shape}


def get_labor_multiplier(material_type):
    """Get labor multiplier for a material type."""
    return LABOR_MULTIPLIERS.get(material_type, 1.0)


def get_distortion_risk(job_type):
    """Get distortion risk info for a job type."""
    return DISTORTION_RISK.get(job_type, {"risk": "medium", "control": "Standard tack and weld sequence"})
