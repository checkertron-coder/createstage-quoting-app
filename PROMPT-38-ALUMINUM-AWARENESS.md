# Prompt 38: Aluminum Job Awareness — Material Cascade, Sheet Stock Reality, Laser Cut Costing

## Problem Statement

When a job description specifies aluminum, the quoting app generates a structurally correct cut list but wraps it in steel assumptions throughout. A two-sign LoanDepot LED quote comes back with steel catalog profile keys, ER70S-6 MIG wire (steel-only consumable), "1 pcs" of a generic "14ga Sheet" with no dimensions, zero laser cutting cost, and a finish label of "Paint." The shop would look at this and not know what to order or what it costs.

Three compounding gaps:
1. The material catalog has no aluminum entries — so every aluminum job gets priced as steel
2. Sheet stock is calculated by square footage with no awareness that real aluminum sheets come in 4×8 or 5×10 ft — a 128"-wide panel physically cannot come from a 4×8 sheet
3. Laser cutting is a real subcontracted cost (easily $400–800 for logo cutouts on two large panels) and doesn't appear anywhere in the quote

Additionally, the clear coat → "Paint (in-house)" label bug from P37 Fix 3 did not land and needs to be resolved here.

## Acceptance Criteria

Running the LoanDepot two-sign job (aluminum, clear coat, 38.5×128" and 38.5×138") produces:

1. Materials list uses aluminum profile catalog entries with aluminum pricing — not steel keys
2. Sheet stock shows real sheet dimensions (4×8 or 5×10) with correct quantity — not "1 pcs" of a dimensionless entry
3. Hardware section includes a laser cutting line item in the $400–800 range for two logo-cut aluminum panels
4. Consumables show aluminum TIG filler (ER4043 or ER5356) and pure argon — not ER70S-6 MIG wire and CO2 mix
5. Finishing section reads "Clear Coat (in-house)" — not "Paint (in-house)"
6. Total materials + laser cut hardware lands in the $800–1,200 range for this specific job
7. A standard steel cantilever gate or railing quote is completely unaffected — no aluminum profiles appear, consumables unchanged

## Constraint Architecture

**Files to modify:**
- `backend/calculators/material_lookup.py` — add aluminum profile entries with placeholder pricing
- `backend/calculators/ai_cut_list.py` — material type cascade: aluminum profiles, sheet size logic, consumable mapping
- `backend/pdf_generator.py` — fix finish label detection (clear coat → "Clear Coat (in-house)")

**DO NOT modify:**
- `backend/calculators/labor_calculator.py` — P37 fixed grind for sign jobs, leave it
- Any question tree JSON files
- Gate or railing calculators
- The main AI cut list prompt rules unrelated to material type

**Scope constraint:** This is a MATERIAL TYPE AWARENESS fix. The goal is to make "material = aluminum" cascade correctly through materials, consumables, sheet sizing, and finish labeling. Do not attempt to solve all job types at once. Build the cascade so Opus can apply its own knowledge once it has the right context.

**Pricing note:** All aluminum prices added in this prompt are placeholders based on market estimates (~2.5–3× mild steel). Burton will replace these with real Wexler and Osorio quotes. Mark all aluminum entries with a `# PLACEHOLDER — update with supplier quote` comment so they're easy to find.

## Decomposition

### Fix 1: Add aluminum profiles to the material catalog

`material_lookup.py` currently has steel profiles only. Add aluminum equivalents for the sizes that appear in LED sign and aluminum fab jobs. Common sizes needed: square tube (1×1, 1.5×1.5, 2×2), flat bar (1×1/8, 1.5×1/8, 2×1/4), angle (1×1, 2×2), and sheet stock.

Naming convention: follow the existing pattern but use `_al` suffix to distinguish from steel (e.g., `sq_tube_1x1_14ga_al`). This suffix is what the AI will use to select the right material — it must be consistent.

For sheet stock, add entries for the two standard aluminum sheet sizes the shop will actually order: 4×8 ft (48"×96") and 5×10 ft (60"×120"). Price these per sheet, not per square foot — the shop buys sheets, not fractional square footage. Include the dimensions explicitly in the catalog so the AI can reason about whether a given panel fits.

### Fix 2: Teach the AI to use aluminum catalog keys and real sheet sizing

In `ai_cut_list.py`, when the material field or job description contains "aluminum," "6061," "5052," or "aluminium," pass a material context flag that tells Opus:

- Use `_al` profile keys from the catalog, not steel keys
- For sheet panels, reason from real sheet dimensions: a 4×8 sheet is 48"×96", a 5×10 sheet is 60"×120". If a panel is wider than 96", it requires a 5×10 sheet or a seamed joint between two 4×8 sheets — plan accordingly and count real sheets needed, not total square footage divided by an average
- Aluminum is sold by the sheet. Quantity in the materials list should reflect actual sheets to order, including realistic waste

Teach the theory, not the lookup. Opus knows that a 128"-wide panel doesn't fit on a 48"-wide sheet — give it the sheet dimensions and let it calculate. Don't hardcode a formula.

### Fix 3: Make consumables material-aware

The consumables section currently generates steel MIG consumables regardless of job material. When material is aluminum:

- Filler rod: ER4043 (general aluminum TIG) or ER5356 (higher strength) — not ER70S-6
- Shielding gas: pure argon — not 75/25 Ar/CO2 (CO2 contaminates aluminum welds)
- Flap discs: aluminum-rated (non-loading, zirconia or ceramic) — standard steel discs load up and contaminate the weld zone
- No standard grinding discs — aluminum doesn't need them for weld prep

The right approach: when material type is aluminum, Opus should generate consumables based on TIG welding aluminum, not MIG welding steel. Pass the material type and let Opus apply its knowledge of aluminum fabrication consumables. Do not hardcode specific quantities — let it calculate from weld length and piece count as it does for steel.

### Fix 4: Add laser cutting as a hardware line item

When the job description contains "laser cut," "laser-cut," "laser cutting," or "CNC plasma cut" in reference to sheet panels:

Add a hardware line item for laser cutting. Label it "Laser Cut Panels (subcontracted)."

Teach Opus to estimate cost from the panel dimensions and cut complexity. For reference: professional laser cutting of aluminum sheet at Chicago-area shops runs approximately $3–6 per linear inch of cut path. A logo cutout on a large panel with moderate complexity (silhouette logo, not fine detail) generates roughly 150–400 linear inches of cut path. A full perimeter cut adds the panel's perimeter. Use these reference ranges to reason an estimate — not to hardcode a number.

Quantity should equal the number of panels being laser cut (face panels and backer panels are separate cuts). This line item should appear in the Hardware section, not consumables.

### Fix 5: Clear coat finish label (carry from P37 Fix 3)

In `pdf_generator.py`, find where the finishing method label is set. The current logic maps "clear coat" to "Paint (in-house)." Fix the detection to correctly map:

- "clear coat," "clearcoat," "clear_coat," "2k urethane," "automotive clear" → "Clear Coat (in-house)"
- "powder coat," "powdercoat," "powder_coat" → "Powder Coat (outsourced)"
- "paint," "painted," "epoxy paint" → "Paint (in-house)"
- "brushed," "brushed stainless," "brushed aluminum" → "Brushed Finish (in-house)"
- Unrecognized → use the raw finish field value

## Evaluation Design

**Test 1: LoanDepot two-sign quote — the broken case**

Run the same description as CS-2026-0056: two aluminum LED signs, 38.5×128" and 38.5×138", clear coat, ESP32 waterproof enclosure, laser cut logo panels.

Expected output:
- Materials: aluminum sq tube and aluminum sheet entries (keys end in `_al`), NOT `sq_tube_1x1_14ga` or `sheet_14ga`
- Sheet stock: 5×10 aluminum sheets (panels are 128" and 138" wide — won't fit on 4×8), quantity ≥ 2 per sign face panel + backer
- Hardware: laser cutting line item present, estimate in $400–800 range
- Consumables: ER4043 filler rod, pure argon — no ER70S-6, no CO2 mix
- Finishing: "Clear Coat (in-house)"
- Total materials + laser cut hardware: $800–1,400

**Test 2: Cantilever gate quote — nothing changes**

Run the standard 12' wide × 10' tall cantilever gate with painted finish.

Expected output:
- All steel profile keys unchanged
- Consumables: ER70S-6, 75/25 Ar/CO2 — unchanged
- No laser cut line item
- Finishing: "Paint (in-house)"
- Labor hours: within normal range for steel gate

**Test 3: Mild steel sign frame with painted finish**

Run a mild steel LED sign frame with painted finish (not aluminum, not clear coat).

Expected output:
- Steel profile keys
- Steel consumables
- Laser cutting line item if description mentions laser cut panels
- Finishing: "Paint (in-house)"
- No aluminum entries appear
