"""
Consumable usage rates and cost data — shielding gas, wire, electrodes,
grinding discs, and miscellaneous consumables with calculation formulas.

Sources: Lincoln Electric product catalogs, Miller Electric welding guides,
3M abrasives technical data, distributor catalogs (Airgas, Praxair/Linde,
McMaster-Carr), AWS Welding Handbook Vol 1-3.

Rates are per-unit-of-work (per linear inch, per square foot, per hour)
for direct calculation from cut list data.

Shop-specific overrides marked with # SHOP: CreateStage
"""

import math
from typing import Optional

# ---------------------------------------------------------------------------
# SHIELDING GAS
# ---------------------------------------------------------------------------
# Flow rates in CFH (cubic feet per hour), cylinder sizes, cost per fill

SHIELDING_GAS = {

    "argon_100": {
        "name": "100% Argon",
        "use_with": ["tig_all", "mig_aluminum", "mig_stainless_tri_mix"],
        "flow_rate_cfh": {
            "tig_mild_steel": 20,
            "tig_stainless": 20,
            "tig_aluminum": 25,
            "tig_back_purge": 10,      # back-purge flow rate
            "mig_aluminum": 30,
        },
        "cylinder_sizes": {
            "80cf": {"cost_fill": 35, "cost_rental_month": 15},
            "125cf": {"cost_fill": 45, "cost_rental_month": 20},
            "300cf": {"cost_fill": 85, "cost_rental_month": 30},
        },
        "notes": "Primary TIG gas. Asphyxiant — ventilate in enclosed spaces.",
    },

    "ar_co2_75_25": {
        "name": "75% Argon / 25% CO2",
        "use_with": ["mig_mild_steel"],
        "flow_rate_cfh": {
            "mig_standard": 35,
            "mig_light_duty": 25,
            "mig_heavy": 45,
        },
        "cylinder_sizes": {
            "80cf": {"cost_fill": 40, "cost_rental_month": 15},
            "125cf": {"cost_fill": 55, "cost_rental_month": 20},
            "300cf": {"cost_fill": 100, "cost_rental_month": 30},
        },
        "notes": "Standard MIG gas for mild steel. Good penetration, minimal spatter.",
    },

    "co2_100": {
        "name": "100% CO2",
        "use_with": ["mig_budget", "flux_core_dual_shield"],
        "flow_rate_cfh": {
            "mig_standard": 35,
            "flux_core_dual_shield": 45,
        },
        "cylinder_sizes": {
            "50lb": {"cost_fill": 25, "cost_rental_month": 10},
        },
        "notes": "Budget MIG gas. More spatter, deeper penetration. Good for structural hidden welds.",
    },

    "ar_co2_98_2": {
        "name": "98% Argon / 2% CO2",
        "use_with": ["mig_stainless"],
        "flow_rate_cfh": {
            "mig_stainless": 35,
        },
        "cylinder_sizes": {
            "125cf": {"cost_fill": 65, "cost_rental_month": 20},
        },
        "notes": "Stainless MIG gas. Minimal carbon pickup. Alternative: tri-mix (Ar/He/CO2).",
    },

    "oxygen": {
        "name": "Oxygen",
        "use_with": ["oxy_fuel_cutting"],
        "flow_rate_cfh": {
            "cutting_3_8_plate": 60,
            "cutting_1_4_plate": 45,
        },
        "cylinder_sizes": {
            "125cf": {"cost_fill": 30, "cost_rental_month": 15},
            "300cf": {"cost_fill": 55, "cost_rental_month": 25},
        },
        "notes": "Cutting gas. Pressure: 40-60 PSI for cutting.",
    },

    "acetylene": {
        "name": "Acetylene",
        "use_with": ["oxy_fuel_cutting", "oxy_fuel_heating"],
        "flow_rate_cfh": {
            "cutting_preheat": 10,
        },
        "cylinder_sizes": {
            "mc_tank": {"cost_fill": 50, "cost_rental_month": 15},
            "b_tank": {"cost_fill": 75, "cost_rental_month": 20},
        },
        "notes": "Fuel gas for oxy-fuel. NEVER exceed 15 PSI. Unstable above 15 PSI.",
    },
}


# ---------------------------------------------------------------------------
# WELDING WIRE AND FILLER
# ---------------------------------------------------------------------------

WELDING_WIRE = {

    "er70s6_035": {
        "name": "ER70S-6 MIG Wire 0.035 inch",
        "diameter": 0.035,
        "type": "mig_solid",
        "material": "mild_steel",
        "deposition_rate_lb_hr": {
            "200A_26V": 3.0,
            "250A_28V": 3.5,
            "300A_30V": 4.5,
        },
        "lb_per_linear_inch_weld": {
            "fillet_1_8": 0.002,
            "fillet_3_16": 0.004,
            "fillet_1_4": 0.007,
            "fillet_5_16": 0.012,
        },
        "spool_sizes": {
            "2lb": {"cost": 8},
            "11lb": {"cost": 30},
            "33lb": {"cost": 65},
            "44lb": {"cost": 80},
        },
        "notes": "Workhorse MIG wire. Triple deoxidized — handles light mill scale.",
    },

    "er70s6_045": {
        "name": "ER70S-6 MIG Wire 0.045 inch",
        "diameter": 0.045,
        "type": "mig_solid",
        "material": "mild_steel",
        "deposition_rate_lb_hr": {
            "250A_28V": 5.0,
            "300A_30V": 6.0,
            "350A_32V": 7.5,
        },
        "lb_per_linear_inch_weld": {
            "fillet_3_16": 0.005,
            "fillet_1_4": 0.009,
            "fillet_5_16": 0.014,
        },
        "spool_sizes": {
            "33lb": {"cost": 60},
            "44lb": {"cost": 75},
        },
        "notes": "Heavy-duty MIG wire. Higher deposition rate. For structural and thick material.",
    },

    "er70s2_tig_1_16": {
        "name": "ER70S-2 TIG Filler Rod 1/16 inch",
        "diameter": 0.0625,
        "type": "tig_filler",
        "material": "mild_steel",
        "deposition_rate_lb_hr": {
            "typical": 0.8,
        },
        "lb_per_linear_inch_weld": {
            "fillet_1_8": 0.002,
            "fillet_3_16": 0.003,
        },
        "pack_sizes": {
            "10lb_tube": {"cost": 45},
        },
        "notes": (
            "Triple-deox TIG filler for mild steel. "
            "Handles slightly dirty base metal better than ER70S-6 filler rod."
        ),
    },

    "er70s2_tig_3_32": {
        "name": "ER70S-2 TIG Filler Rod 3/32 inch",
        "diameter": 0.09375,
        "type": "tig_filler",
        "material": "mild_steel",
        "deposition_rate_lb_hr": {
            "typical": 1.2,
        },
        "lb_per_linear_inch_weld": {
            "fillet_3_16": 0.005,
            "fillet_1_4": 0.008,
        },
        "pack_sizes": {
            "10lb_tube": {"cost": 45},
        },
        "notes": "Larger TIG filler for thicker mild steel joints.",
    },

    "er308l_tig_1_16": {
        "name": "ER308L TIG Filler Rod 1/16 inch",
        "diameter": 0.0625,
        "type": "tig_filler",
        "material": "stainless_304",
        "deposition_rate_lb_hr": {
            "typical": 0.7,
        },
        "lb_per_linear_inch_weld": {
            "fillet_1_8": 0.002,
            "fillet_3_16": 0.003,
        },
        "pack_sizes": {
            "10lb_tube": {"cost": 85},
        },
        "notes": "Standard stainless TIG filler for 304. NEVER use on 5052 aluminum.",
    },

    "er316l_tig_1_16": {
        "name": "ER316L TIG Filler Rod 1/16 inch",
        "diameter": 0.0625,
        "type": "tig_filler",
        "material": "stainless_316",
        "deposition_rate_lb_hr": {
            "typical": 0.7,
        },
        "lb_per_linear_inch_weld": {
            "fillet_1_8": 0.002,
            "fillet_3_16": 0.003,
        },
        "pack_sizes": {
            "10lb_tube": {"cost": 95},
        },
        "notes": "Marine-grade stainless TIG filler for 316. Do NOT use 308L on 316.",
    },

    "er309l_tig_1_16": {
        "name": "ER309L TIG Filler Rod 1/16 inch (Dissimilar)",
        "diameter": 0.0625,
        "type": "tig_filler",
        "material": "dissimilar",
        "deposition_rate_lb_hr": {
            "typical": 0.7,
        },
        "lb_per_linear_inch_weld": {
            "fillet_3_16": 0.003,
        },
        "pack_sizes": {
            "10lb_tube": {"cost": 90},
        },
        "notes": "For welding mild steel to stainless steel. Higher alloy content bridges the gap.",
    },

    "4043_tig_3_32": {
        "name": "4043 Aluminum TIG Filler Rod 3/32 inch",
        "diameter": 0.09375,
        "type": "tig_filler",
        "material": "aluminum_6061",
        "deposition_rate_lb_hr": {
            "typical": 0.5,
        },
        "lb_per_linear_inch_weld": {
            "fillet_3_16": 0.002,
        },
        "pack_sizes": {
            "1lb_tube": {"cost": 12},
            "5lb_tube": {"cost": 45},
        },
        "notes": "General-purpose aluminum filler. Cosmetic (better color match after anodize). NOT for 5052.",
    },

    "5356_tig_3_32": {
        "name": "5356 Aluminum TIG Filler Rod 3/32 inch",
        "diameter": 0.09375,
        "type": "tig_filler",
        "material": "aluminum",
        "deposition_rate_lb_hr": {
            "typical": 0.5,
        },
        "lb_per_linear_inch_weld": {
            "fillet_3_16": 0.002,
        },
        "pack_sizes": {
            "1lb_tube": {"cost": 14},
            "5lb_tube": {"cost": 55},
        },
        "notes": "Structural aluminum filler. Required for 5052. Better strength than 4043.",
    },

    "e7018_stick_1_8": {
        "name": "E7018 Stick Electrode 1/8 inch",
        "diameter": 0.125,
        "type": "stick",
        "material": "mild_steel",
        "deposition_rate_lb_hr": {
            "typical": 1.5,
        },
        "lb_per_linear_inch_weld": {
            "fillet_3_16": 0.008,
            "fillet_1_4": 0.012,
        },
        "pack_sizes": {
            "10lb_can": {"cost": 35},
            "50lb_can": {"cost": 140},
        },
        "notes": (
            "Low hydrogen structural electrode. MUST store in rod oven (250-300F). "
            "Exposure to moisture > 4 hours = scrap or rebake."
        ),
    },

    "e71t1_flux_core_045": {
        "name": "E71T-1 Flux Core Wire 0.045 inch (Gas-Shielded)",
        "diameter": 0.045,
        "type": "flux_core",
        "material": "mild_steel",
        "deposition_rate_lb_hr": {
            "300A": 8.0,
            "350A": 10.0,
        },
        "lb_per_linear_inch_weld": {
            "fillet_1_4": 0.010,
            "fillet_5_16": 0.016,
        },
        "spool_sizes": {
            "33lb": {"cost": 75},
        },
        "notes": "Gas-shielded flux core. Better bead than E71T-11. Higher deposition rate than solid wire.",
    },
}


# ---------------------------------------------------------------------------
# TUNGSTEN ELECTRODES
# ---------------------------------------------------------------------------

TUNGSTEN = {
    "2pct_lanthanated": {
        "name": "2% Lanthanated Tungsten (Gold Band)",
        "use_with": ["dc_steel", "dc_stainless", "ac_aluminum"],
        "diameters": [0.040, 0.0625, 0.09375, 0.125],
        "tip_prep": {
            "dc_steel": "Grind to sharp point (2.5x diameter taper)",
            "dc_stainless": "Grind to sharp point",
            "ac_aluminum": "Grind to point, tip will ball during AC welding",
        },
        "life_hours": {
            "typical": 4,   # hours before regrind needed
            "contaminated": 0,  # must regrind immediately
        },
        "cost_each": {
            "1_16": 4.00,
            "3_32": 5.00,
            "1_8": 6.00,
        },
        "notes": (
            "Best all-around tungsten. Works DC and AC. "
            "Replaced thoriated (2% thorium is mildly radioactive). "
            "Grind on DEDICATED tungsten grinder — NO cross-contamination."
        ),
    },

    "pure_tungsten": {
        "name": "Pure Tungsten (Green Band)",
        "use_with": ["ac_aluminum"],
        "diameters": [0.0625, 0.09375, 0.125],
        "tip_prep": {
            "ac_aluminum": "Ball end forms naturally during AC welding",
        },
        "life_hours": {
            "typical": 3,
        },
        "cost_each": {
            "1_16": 2.50,
            "3_32": 3.50,
            "1_8": 4.50,
        },
        "notes": "Traditional aluminum TIG electrode. Being replaced by lanthanated in most shops.",
    },

    "2pct_ceriated": {
        "name": "2% Ceriated Tungsten (Gray Band)",
        "use_with": ["dc_steel", "dc_stainless", "low_amp"],
        "diameters": [0.040, 0.0625, 0.09375],
        "tip_prep": {
            "dc_all": "Grind to sharp point",
        },
        "life_hours": {
            "typical": 3,
        },
        "cost_each": {
            "1_16": 3.50,
            "3_32": 4.50,
        },
        "notes": "Good for low-amp DC work. Easy arc start. Not ideal for high-amp AC.",
    },
}


# ---------------------------------------------------------------------------
# GRINDING AND ABRASIVE CONSUMABLES
# ---------------------------------------------------------------------------

ABRASIVES = {

    "flap_disc_40_grit": {
        "name": "Flap Disc 4.5 inch — 40 Grit",
        "type": "flap_disc",
        "size": 4.5,
        "grit": 40,
        "life_sqft": 8,             # square feet of material before worn
        "life_linear_ft_weld": 15,  # linear feet of weld grinding
        "cost_each": 5.00,
        "cost_per_sqft": 0.63,      # 5.00 / 8
        "cost_per_ft_weld": 0.33,   # 5.00 / 15
        "use_for": [
            "heavy_stock_removal",
            "mill_scale_removal",
            "decorative_stock_prep",  # SHOP: CreateStage — 40 grit IS the finish
        ],
        "notes": "Primary finish tool for decorative stock prep at CreateStage.",  # SHOP: CreateStage
    },

    "flap_disc_80_grit": {
        "name": "Flap Disc 4.5 inch — 80 Grit",
        "type": "flap_disc",
        "size": 4.5,
        "grit": 80,
        "life_sqft": 12,
        "life_linear_ft_weld": 20,
        "cost_each": 5.50,
        "cost_per_sqft": 0.46,
        "cost_per_ft_weld": 0.28,
        "use_for": [
            "weld_blending",
            "general_surface_prep",
            "pre_paint_prep",
        ],
        "notes": "Standard weld blending disc. Most commonly used.",
    },

    "flap_disc_120_grit": {
        "name": "Flap Disc 4.5 inch — 120 Grit",
        "type": "flap_disc",
        "size": 4.5,
        "grit": 120,
        "life_sqft": 15,
        "life_linear_ft_weld": 25,
        "cost_each": 6.00,
        "cost_per_sqft": 0.40,
        "cost_per_ft_weld": 0.24,
        "use_for": [
            "finish_blending",
            "pre_clear_coat_prep",
            "pre_powder_coat_prep",
        ],
        "notes": "Fine finish disc. For pre-coating surface prep.",
    },

    "grinding_wheel_4_5": {
        "name": "Grinding Wheel 4.5 inch — Type 27",
        "type": "grinding_wheel",
        "size": 4.5,
        "life_linear_ft_weld": 30,
        "cost_each": 3.50,
        "cost_per_ft_weld": 0.12,
        "use_for": [
            "heavy_weld_removal",
            "weld_profile_correction",
            "aggressive_material_removal",
        ],
        "notes": "Fast removal but rough finish. Follow with flap disc.",
    },

    "cutoff_wheel_4_5": {
        "name": "Cut-Off Wheel 4.5 inch",
        "type": "cutoff_wheel",
        "size": 4.5,
        "life_cuts": 20,    # approximate cuts on 2" tube
        "cost_each": 3.00,
        "cost_per_cut": 0.15,
        "use_for": [
            "trimming",
            "notching",
            "slot_cutting",
        ],
        "notes": "Thin wheel for precise cuts. NOT for heavy grinding.",
    },

    "cutoff_wheel_14in": {
        "name": "Abrasive Cut-Off Wheel 14 inch (Chop Saw)",
        "type": "cutoff_wheel",
        "size": 14,
        "life_cuts": {
            "1in_tube": 80,
            "2in_tube": 50,
            "3in_tube": 30,
            "4in_tube": 20,
        },
        "cost_each": 8.00,
        "use_for": ["chop_saw_cutting"],
        "notes": "Standard chop saw consumable. Life varies dramatically with material size and hardness.",
    },

    "fiber_disc_36_grit": {
        "name": "Fiber Disc 4.5 inch — 36 Grit",
        "type": "fiber_disc",
        "size": 4.5,
        "grit": 36,
        "life_sqft": 6,
        "cost_each": 3.00,
        "cost_per_sqft": 0.50,
        "use_for": [
            "aggressive_stock_removal",
            "weld_flush_grinding",
        ],
        "notes": "Most aggressive disc. For heavy material removal. Requires backing pad.",
    },

    "roloc_disc_2in_80_grit": {
        "name": "Roloc Disc 2 inch — 80 Grit",
        "type": "roloc_disc",
        "size": 2,
        "grit": 80,
        "life_weld_areas": 5,  # number of constrained weld areas before worn
        "cost_each": 2.50,
        "cost_per_area": 0.50,
        "use_for": [
            "constrained_weld_cleanup",
            "between_layers",
            "inside_frames",
            "die_grinder_work",
        ],
        "notes": "For die grinder. Reaches where 4.5 inch grinder cannot.",
    },

    "wire_wheel_crimped": {
        "name": "Wire Wheel 4.5 inch — Crimped",
        "type": "wire_wheel",
        "size": 4.5,
        "life_hours": 20,
        "cost_each": 12.00,
        "cost_per_hour": 0.60,
        "use_for": [
            "weld_cleanup",
            "rust_removal_on_curves",
            "light_scale_removal",
        ],
        "notes": "Gentle removal. Good for cleaning welds and curved surfaces.",
    },

    "surface_conditioning_disc": {
        "name": "Surface Conditioning Disc 4.5 inch (Scotch-Brite Type)",
        "type": "surface_conditioning",
        "size": 4.5,
        "life_sqft": 25,
        "cost_each": 8.00,
        "cost_per_sqft": 0.32,
        "use_for": [
            "final_brush_finish",
            "directional_grain",
            "pre_clear_coat",
        ],
        "notes": "Establishes consistent directional grain for brushed finish.",
    },

    "sandpaper_220_grit": {
        "name": "Sandpaper 220 Grit Sheet",
        "type": "sandpaper",
        "grit": 220,
        "life_sqft": 4,
        "cost_each": 1.50,
        "cost_per_sqft": 0.38,
        "use_for": ["pre_paint_scuff", "between_primer_coats"],
        "notes": "Hand scuffing before paint. Promotes adhesion.",
    },

    "emery_cloth": {
        "name": "Emery Cloth (Assorted 150-320 Grit)",
        "type": "emery_cloth",
        "life_spots": 10,
        "cost_per_sheet": 2.00,
        "use_for": ["hand_finishing", "tight_spots", "final_touchup"],
        "notes": "Last resort for areas no power tool can reach. Slow but precise.",
    },
}


# ---------------------------------------------------------------------------
# COATING AND FINISHING CONSUMABLES
# ---------------------------------------------------------------------------

COATING_CONSUMABLES = {

    "clear_coat_spray": {
        "name": "Clear Coat (Spray Can or HVLP)",
        "coverage_sqft_per_can": 15,    # 12 oz spray can
        "coverage_sqft_per_quart": 50,  # HVLP spray
        "cost_per_can": 12.00,
        "cost_per_quart": 35.00,
        "cost_per_sqft": 0.80,          # spray can rate
        "use_for": ["clear_coat_finish", "permalac_finish"],
        "notes": "Lacquer: $8-12/can, not UV stable. Urethane: $25-35/qt. Permalac: $45-60/qt.",
    },

    "primer_self_etching": {
        "name": "Self-Etching Primer",
        "coverage_sqft_per_can": 20,
        "cost_per_can": 10.00,
        "cost_per_sqft": 0.50,
        "use_for": ["pre_paint_primer", "pre_topcoat"],
        "notes": "Spray can for small jobs. HVLP for large. Cure 1 hour before topcoat.",
    },

    "topcoat_paint": {
        "name": "Topcoat Paint (Enamel/Urethane)",
        "coverage_sqft_per_can": 15,
        "coverage_sqft_per_quart": 40,
        "cost_per_can": 8.00,
        "cost_per_quart": 30.00,
        "cost_per_sqft": 0.53,
        "use_for": ["paint_finish"],
        "notes": "Two light coats better than one heavy. Match customer's color spec.",
    },

    "acetone": {
        "name": "Acetone (Degreaser/Cleaner)",
        "coverage_sqft_per_gallon": 200,
        "cost_per_gallon": 15.00,
        "cost_per_sqft": 0.08,
        "use_for": ["degrease", "pre_clear_coat", "pre_paint", "pre_patina"],
        "notes": "Last prep step before any coating. Lint-free cloth application.",
    },

    "tack_rags": {
        "name": "Tack Rags",
        "cost_per_pack_12": 8.00,
        "life_sqft_per_rag": 20,
        "cost_per_sqft": 0.03,
        "use_for": ["dust_removal_before_coating"],
        "notes": "After acetone wipe, before spray. Picks up remaining dust.",
    },

    "patina_solution": {
        "name": "Patina Solution (Sculpt Nouveau / Ferric Chloride)",
        "coverage_sqft_per_bottle": 25,     # 16 oz bottle
        "cost_per_bottle": 25.00,
        "cost_per_sqft": 1.00,
        "use_for": ["patina_finish", "chemical_patina"],
        "notes": "Skill-sensitive application. Multiple coats for deeper effect.",
    },

    "patina_sealer": {
        "name": "Patina Sealer (Permalac / Museum Wax)",
        "coverage_sqft_per_pint": 30,
        "cost_per_pint": 45.00,
        "cost_per_sqft": 1.50,
        "use_for": ["patina_seal", "patina_finish"],
        "notes": "Applied after desired patina stage reached. Stops further oxidation.",
    },
}


# ---------------------------------------------------------------------------
# MISCELLANEOUS CONSUMABLES
# ---------------------------------------------------------------------------

MISC_CONSUMABLES = {

    "anti_spatter_spray": {
        "name": "Anti-Spatter Spray",
        "cost_per_can": 8.00,
        "life_hours": 8,
        "cost_per_hour": 1.00,
        "use_for": ["mig_welding"],
        "notes": "Apply to work surface and gun nozzle. Prevents spatter adhesion.",
    },

    "mig_contact_tips": {
        "name": "MIG Contact Tips",
        "cost_per_tip": 1.50,
        "life_hours": 4,
        "cost_per_hour": 0.38,
        "use_for": ["mig_welding"],
        "notes": "Replace when arc becomes erratic. Match wire diameter (0.035 or 0.045).",
    },

    "mig_nozzle": {
        "name": "MIG Gun Nozzle",
        "cost_each": 5.00,
        "life_hours": 40,
        "cost_per_hour": 0.13,
        "use_for": ["mig_welding"],
        "notes": "Clean spatter buildup regularly. Replace when bore is obstructed.",
    },

    "plasma_electrode": {
        "name": "Plasma Cutter Electrode",
        "cost_each": 5.00,
        "life_starts": 200,
        "cost_per_start": 0.025,
        "use_for": ["plasma_cutting"],
        "notes": "Replace at first sign of pit in hafnium insert.",
    },

    "plasma_nozzle": {
        "name": "Plasma Cutter Nozzle",
        "cost_each": 4.00,
        "life_starts": 150,
        "cost_per_start": 0.027,
        "use_for": ["plasma_cutting"],
        "notes": "Replace when cut quality drops or arc wanders.",
    },

    "cutting_fluid": {
        "name": "Cutting Fluid (Tap Magic or equivalent)",
        "cost_per_pint": 10.00,
        "life_cuts": 500,
        "cost_per_cut": 0.02,
        "use_for": ["cold_saw_cutting", "drilling", "tapping"],
        "notes": "Required for cold saw blade life. Always use on stainless.",
    },

    "drill_bits_hss": {
        "name": "HSS Drill Bits",
        "cost_per_bit_1_4": 3.00,
        "cost_per_bit_3_8": 5.00,
        "cost_per_bit_1_2": 8.00,
        "life_holes_mild_steel": 50,
        "use_for": ["drilling_mild_steel"],
        "notes": "NOT for stainless — use cobalt or carbide.",
    },

    "drill_bits_cobalt": {
        "name": "Cobalt Drill Bits (for Stainless)",
        "cost_per_bit_1_4": 8.00,
        "cost_per_bit_3_8": 12.00,
        "cost_per_bit_1_2": 18.00,
        "life_holes_stainless": 20,
        "use_for": ["drilling_stainless"],
        "notes": "Required for stainless. HSS will work-harden stainless on contact.",
    },

    "concrete_anchors": {
        "name": "Concrete Expansion Anchors (Hilti or equiv)",
        "cost_per_anchor_3_8": 2.50,
        "cost_per_anchor_1_2": 3.50,
        "cost_per_anchor_5_8": 5.00,
        "use_for": ["base_plate_anchoring", "railing_install", "bollard_install"],
        "notes": "Hilti HIT-HY 200 or Red Head for structural anchoring.",
    },

    "masking_tape": {
        "name": "Masking Tape (1 inch)",
        "cost_per_roll": 5.00,
        "life_ft_per_roll": 60,
        "use_for": ["masking_before_coating", "protecting_threads"],
        "notes": "Blue painter's tape for non-critical. Green (high-temp) for near welding.",
    },

    "white_vinegar": {
        "name": "White Vinegar (5% Acetic Acid)",
        "cost_per_gallon": 4.00,
        "gallons_per_bath_fill": 10,     # typical bath size
        "bath_reuses": 3,                 # before solution is spent
        "cost_per_bath_use": 13.33,       # 40 / 3
        "use_for": ["vinegar_bath_mill_scale_removal"],
        "notes": "Cheapest mill scale removal method. 20-30% solution (dilute with water).",
    },

    "scotch_brite_pads": {
        "name": "Scotch-Brite Pads (Medium Grit, Red)",
        "cost_per_pad": 3.00,
        "life_sqft": 10,
        "use_for": ["post_vinegar_cleanup", "light_surface_prep"],  # SHOP: CreateStage
        "notes": "Part of post-vinegar cleanup process.",  # SHOP: CreateStage
    },

    "dish_soap": {
        "name": "Dish Soap",
        "cost_per_bottle": 4.00,
        "life_baths": 20,
        "use_for": ["post_vinegar_cleanup"],  # SHOP: CreateStage
        "notes": "Used with scotch-brite for post-vinegar scrub.",  # SHOP: CreateStage
    },
}


# ---------------------------------------------------------------------------
# CONSUMABLE CALCULATION FORMULAS
# ---------------------------------------------------------------------------

def calc_wire_usage(weld_linear_inches, fillet_size="3_16", wire_type="er70s6_035"):
    # type: (float, str, str) -> dict
    """
    Calculate MIG/TIG wire consumption for a job.

    Args:
        weld_linear_inches: total linear inches of weld
        fillet_size: "1_8", "3_16", "1_4", or "5_16"
        wire_type: key from WELDING_WIRE dict

    Returns:
        dict with lbs_needed, cost, spool_recommendation
    """
    wire = WELDING_WIRE.get(wire_type)
    if not wire:
        return {"lbs_needed": 0, "cost": 0, "error": "Unknown wire type"}

    key = "fillet_" + fillet_size
    lb_per_inch = wire.get("lb_per_linear_inch_weld", {}).get(key, 0.004)
    lbs_needed = weld_linear_inches * lb_per_inch

    # Add 15% waste factor (start/stop, trim, test welds)
    lbs_with_waste = lbs_needed * 1.15

    # Find smallest spool that covers the need
    spool_key = "spool_sizes" if "spool_sizes" in wire else "pack_sizes"
    sizes = wire.get(spool_key, {})
    recommended = None
    cost = 0
    for size_name, info in sorted(sizes.items(), key=lambda x: x[1].get("cost", 0)):
        # Extract weight from size name
        weight = _extract_weight_from_name(size_name)
        if weight and weight >= lbs_with_waste:
            recommended = size_name
            cost = info["cost"]
            break
    if not recommended and sizes:
        # Use largest available
        last_key = list(sizes.keys())[-1]
        recommended = last_key
        cost = sizes[last_key]["cost"]
        # May need multiple
        weight = _extract_weight_from_name(last_key)
        if weight and weight > 0:
            spools_needed = math.ceil(lbs_with_waste / weight)
            cost = cost * spools_needed

    return {
        "lbs_needed": round(lbs_with_waste, 2),
        "wire_type": wire_type,
        "spool_size": recommended,
        "cost": round(cost, 2),
    }


def calc_gas_usage(weld_time_hours, gas_type="ar_co2_75_25", flow_key="mig_standard"):
    # type: (float, str, str) -> dict
    """
    Calculate shielding gas consumption for a job.

    Args:
        weld_time_hours: total arc-on welding time in hours
        gas_type: key from SHIELDING_GAS dict
        flow_key: key into the flow_rate_cfh dict

    Returns:
        dict with cf_needed, cylinder_recommendation, cost
    """
    gas = SHIELDING_GAS.get(gas_type)
    if not gas:
        return {"cf_needed": 0, "cost": 0, "error": "Unknown gas type"}

    flow_rate = gas.get("flow_rate_cfh", {}).get(flow_key, 35)
    cf_needed = weld_time_hours * flow_rate

    # Add 20% for pre-flow, post-flow, and purging
    cf_with_waste = cf_needed * 1.20

    # Find smallest cylinder
    cylinders = gas.get("cylinder_sizes", {})
    recommended = None
    cost = 0
    for cyl_name, info in sorted(cylinders.items(),
                                   key=lambda x: x[1].get("cost_fill", 0)):
        size = _extract_cf_from_name(cyl_name)
        if size and size >= cf_with_waste:
            recommended = cyl_name
            cost = info["cost_fill"]
            break
    if not recommended and cylinders:
        # Use largest
        last_key = list(cylinders.keys())[-1]
        recommended = last_key
        cost = cylinders[last_key]["cost_fill"]
        size = _extract_cf_from_name(last_key)
        if size and size > 0:
            cyls_needed = math.ceil(cf_with_waste / size)
            cost = cost * cyls_needed

    return {
        "cf_needed": round(cf_with_waste, 1),
        "gas_type": gas_type,
        "cylinder": recommended,
        "cost": round(cost, 2),
    }


def calc_disc_usage(weld_linear_feet=0, surface_sqft=0, finish_type="weld_cleanup"):
    # type: (float, float, str) -> dict
    """
    Calculate grinding disc consumption.

    Args:
        weld_linear_feet: total linear feet of weld to grind
        surface_sqft: total square feet of surface to prep
        finish_type: "weld_cleanup", "stock_prep", "brush_finish"

    Returns:
        dict with disc count, type, cost
    """
    if finish_type == "stock_prep":
        disc = ABRASIVES.get("flap_disc_40_grit", {})
        life = disc.get("life_sqft", 8)
        count = math.ceil(surface_sqft / life) if life > 0 else 1
        cost = count * disc.get("cost_each", 5.00)
        return {
            "disc_type": "flap_disc_40_grit",
            "count": max(count, 1),
            "cost": round(cost, 2),
        }
    elif finish_type == "brush_finish":
        disc = ABRASIVES.get("surface_conditioning_disc", {})
        life = disc.get("life_sqft", 25)
        count = math.ceil(surface_sqft / life) if life > 0 else 1
        cost = count * disc.get("cost_each", 8.00)
        return {
            "disc_type": "surface_conditioning_disc",
            "count": max(count, 1),
            "cost": round(cost, 2),
        }
    else:
        # Default: weld cleanup with 80-grit flap disc
        disc = ABRASIVES.get("flap_disc_80_grit", {})
        life = disc.get("life_linear_ft_weld", 20)
        count = math.ceil(weld_linear_feet / life) if life > 0 else 1
        cost = count * disc.get("cost_each", 5.50)
        return {
            "disc_type": "flap_disc_80_grit",
            "count": max(count, 1),
            "cost": round(cost, 2),
        }


def calc_coating_cost(surface_sqft, coating_type="clear_coat"):
    # type: (float, str) -> dict
    """
    Calculate coating material cost.

    Args:
        surface_sqft: total surface area to coat
        coating_type: "clear_coat", "primer", "paint", "patina"

    Returns:
        dict with product, quantity, cost
    """
    mapping = {
        "clear_coat": "clear_coat_spray",
        "primer": "primer_self_etching",
        "paint": "topcoat_paint",
        "patina": "patina_solution",
    }
    product_key = mapping.get(coating_type, "clear_coat_spray")
    product = COATING_CONSUMABLES.get(product_key, {})
    cost_per_sqft = product.get("cost_per_sqft", 1.00)
    total = surface_sqft * cost_per_sqft

    return {
        "product": product_key,
        "surface_sqft": round(surface_sqft, 1),
        "cost": round(total, 2),
    }


def estimate_consumables_for_job(weld_linear_inches, surface_sqft,
                                  material_type="mild_steel",
                                  weld_process="mig",
                                  finish_type="raw"):
    # type: (float, float, str, str, str) -> dict
    """
    Estimate all consumables for a complete job.

    Args:
        weld_linear_inches: total weld length
        surface_sqft: total surface area
        material_type: "mild_steel", "stainless_304", "aluminum_6061"
        weld_process: "mig" or "tig"
        finish_type: "raw", "clear_coat", "paint", "powder_coat", etc.

    Returns:
        dict with wire, gas, discs, coating subtotals and grand total
    """
    # Wire
    if weld_process == "mig":
        wire = calc_wire_usage(weld_linear_inches, "3_16", "er70s6_035")
    elif weld_process == "tig":
        if material_type == "stainless_304":
            wire = calc_wire_usage(weld_linear_inches, "3_16", "er308l_tig_1_16")
        elif material_type == "stainless_316":
            wire = calc_wire_usage(weld_linear_inches, "3_16", "er316l_tig_1_16")
        elif "aluminum" in material_type:
            wire = calc_wire_usage(weld_linear_inches, "3_16", "5356_tig_3_32")
        else:
            wire = calc_wire_usage(weld_linear_inches, "3_16", "er70s2_tig_1_16")
    else:
        wire = {"cost": 0}

    # Gas — estimate weld time from linear inches
    # MIG: ~15 in/min → weld_linear_inches / 15 / 60 hours
    # TIG: ~5 in/min → weld_linear_inches / 5 / 60 hours
    if weld_process == "mig":
        weld_hours = weld_linear_inches / 15.0 / 60.0
        gas = calc_gas_usage(weld_hours, "ar_co2_75_25", "mig_standard")
    elif weld_process == "tig":
        weld_hours = weld_linear_inches / 5.0 / 60.0
        if "stainless" in material_type:
            gas = calc_gas_usage(weld_hours, "argon_100", "tig_stainless")
        else:
            gas = calc_gas_usage(weld_hours, "argon_100", "tig_mild_steel")
    else:
        gas = {"cost": 0}

    # Grinding discs
    weld_linear_feet = weld_linear_inches / 12.0
    discs = calc_disc_usage(weld_linear_feet, surface_sqft, "weld_cleanup")

    # Coating
    coating = {"cost": 0}
    if finish_type in ("clear_coat", "clearcoat"):
        coating = calc_coating_cost(surface_sqft, "clear_coat")
    elif finish_type == "paint":
        primer = calc_coating_cost(surface_sqft, "primer")
        topcoat = calc_coating_cost(surface_sqft, "paint")
        coating = {"cost": primer["cost"] + topcoat["cost"]}
    elif finish_type == "patina":
        patina = calc_coating_cost(surface_sqft, "patina")
        sealer = {"cost": surface_sqft * 1.50}  # patina sealer
        coating = {"cost": patina["cost"] + sealer["cost"]}

    grand_total = (wire.get("cost", 0) + gas.get("cost", 0) +
                   discs.get("cost", 0) + coating.get("cost", 0))

    return {
        "wire": wire,
        "gas": gas,
        "discs": discs,
        "coating": coating,
        "total": round(grand_total, 2),
    }


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _extract_weight_from_name(name):
    # type: (str) -> Optional[float]
    """Extract weight in lbs from spool/pack size name like '11lb' or '10lb_tube'."""
    import re
    m = re.search(r'(\d+(?:\.\d+)?)lb', name)
    if m:
        return float(m.group(1))
    return None


def _extract_cf_from_name(name):
    # type: (str) -> Optional[float]
    """Extract cubic feet from cylinder name like '125cf' or '300cf'."""
    import re
    m = re.search(r'(\d+)cf', name)
    if m:
        return float(m.group(1))
    return None
