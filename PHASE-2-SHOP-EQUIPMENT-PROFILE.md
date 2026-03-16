# PHASE 2: Shop Equipment Profile — "What's In Your Shop?"

*Design document — not a build prompt yet. This defines the vision for the next major feature after P53/P54.*

---

## The Problem

Every fab shop is different. Kevin has a press brake with 60 dies but only uses 4 because he can't think through which die to use for each project. A shop with a CNC plasma table can cut base plates in-house for $0; a shop without one needs to outsource that to a laser cutting service at $X per plate. The app currently has no idea what equipment the user has.

**This is THE differentiator.** No other quoting tool knows your shop's capabilities and adjusts accordingly.

---

## The Vision

When a fabricator sets up their shop profile, they tell the app:
1. **What equipment they have** (press brake, plasma table, TIG welder, lathe, etc.)
2. **What tooling/attachments** (press brake dies, torch tips, grinding wheels)
3. **Their capacity** (max bend length, max sheet size for plasma, etc.)

The AI then uses this profile to:
- **Route processes correctly** — "You have a CNC plasma table, so base plates are cut in-house (0.5 hrs setup + cut time). Your neighbor who doesn't? Outsource line item at $X."
- **Optimize setup time** — Kevin's press brake with 60 dies: the app knows which die to use for each bend, calculates setup/changeover time, and tells him "Use die #14 (2" V-groove) for the 11ga channel, then swap to die #37 (1/2" radius) for the handrail bends — 2 setups, estimated 45 min changeover"
- **Make vs. Buy decisions** — "You could bend this in-house with your press brake (2 hrs labor) or order pre-bent from a service center ($85 delivered). Here are both options."
- **Realistic labor times** — Setup time is one of the hardest things to quote. Knowing the actual tooling eliminates guessing.

---

## Data Model Concept

### ShopEquipment (new table)
```
id, user_id, equipment_type, make, model, year,
capabilities_json, tooling_json, max_capacity_json,
notes, is_active, created_at
```

### Equipment Types (initial set)
- `cnc_plasma_table` — cut capacity (sheet size, max thickness per material)
- `press_brake` — tonnage, max bend length, die inventory
- `tig_welder` — amperage range, AC/DC, pulse capability
- `mig_welder` — wire feed, gas type, spray transfer capable
- `stick_welder` — amperage
- `band_saw` — horizontal/vertical, max cut size
- `cold_saw` — max diameter
- `chop_saw` — max cut size
- `drill_press` — max hole size, table size
- `mag_drill` — portable, max hole size
- `lathe` — swing, between centers
- `mill` — table size, travel
- `ironworker` — tonnage, punch/shear/notch capacity
- `tube_roller` — max tube size, min radius
- `pipe_threader` — max pipe size
- `sandblast_cabinet` — cabinet size
- `powder_coat_oven` — internal dimensions, max temp
- `paint_booth` — dimensions, ventilation type
- `crane_hoist` — capacity (tons), span, hook height
- `forklift` — capacity, fork length

### Die/Tooling Inventory (for press brake specifically)
```
id, equipment_id, die_number, die_type (v_groove/radius/gooseneck/etc),
opening_width, angle, radius, max_tonnage_per_foot,
material_compatibility, notes
```

### How Opus Uses This

The shop equipment profile gets injected into the AI prompt as context (just like fab knowledge):

```
SHOP EQUIPMENT PROFILE:
- CNC Plasma Table: Hypertherm XPR300, 5x10 table, cuts up to 1.5" mild steel, 1" stainless
- Press Brake: 150-ton Amada, 10' bed, dies: #14 (2" V-groove), #22 (1" V-groove), #37 (1/2" radius), #41 (gooseneck)
- TIG Welder: Miller Dynasty 350, AC/DC, pulse
- No powder coat oven (outsource finishing)
- No tube roller (outsource or hand-bend small radius)

Given this equipment, determine:
1. Which processes can be done in-house vs outsourced
2. Which dies/tooling to use for each bend operation
3. Setup time for tooling changes
4. Whether any process would benefit from outsourcing even if equipment exists
```

Opus then returns the quote with:
- In-house processes with accurate setup + run times
- Outsource line items where equipment is missing
- Die selection recommendations (Kevin's use case)
- Make vs. buy analysis for borderline cases

---

## Kevin's Press Brake Use Case (Specific)

Kevin has:
- 150-ton press brake
- 60 dies (but only uses 4 regularly)
- No easy way to look up which die works for which material/thickness/bend

With shop equipment profiles:
1. Kevin enters his die inventory once (die number, type, opening, max tonnage)
2. When quoting a job that requires bending, Opus:
   - Looks at the material type + thickness + desired bend radius
   - Matches against Kevin's actual die inventory
   - Recommends specific die numbers
   - Calculates setup time (how many die changes needed)
   - Sequences the bends to minimize changeovers (batch all 2" V-groove bends first, then swap)
3. Kevin's quote now includes:
   - "Press brake setup: 30 min (2 die changes)"
   - "Bending: 1.5 hrs (18 bends using die #14 → #37)"
   - Instead of his old guess: "Bending: ??? hours"

**This alone could be worth the subscription for shops with complex bending operations.**

---

## Implementation Phases

### Phase 2A: Equipment Profile UI + Storage
- Add equipment tables + migration
- Profile page: "My Shop Equipment" section
- Simple form: add equipment by type, enter key specs
- Store in DB, load into user context

### Phase 2B: AI Integration
- Inject equipment profile into Opus prompts
- Opus returns in-house vs outsource routing
- Setup time calculations based on actual tooling

### Phase 2C: Die/Tooling Intelligence
- Detailed die inventory for press brakes
- Die selection recommendations
- Bend sequencing optimization
- Setup time minimization

### Phase 2D: Make vs. Buy Engine
- Cost comparison: in-house labor + consumables vs outsource quote
- Automatic suggestion based on shop capabilities
- Track outsource vendor pricing over time

---

## Why This Wins

1. **No competitor has this.** Generic quoting tools don't know your shop.
2. **Reduces quoting errors** — the #1 problem in fab is underquoting setup time
3. **Scales to every trade** — painters have spray rigs vs rollers, carpenters have CNC routers vs hand tools, HVAC has plasma tables vs manual cutting
4. **Sticky product** — once a shop enters their equipment profile, switching cost is high
5. **Data moat** — aggregate anonymized equipment data across shops = industry intelligence

---

## Notes

- This is NOT prompt 55. This is a design document.
- Build prompts will be written when P53+P54 are live and tested.
- Kevin's feedback will shape the press brake die feature specifically.
- Equipment profile could eventually integrate with equipment financing/leasing partners (revenue opportunity).
