# Prompt 38: Aluminum Awareness — Catalog Keys, Remove Steel Overrides, Fix Label Bug

## Problem Statement

When a job specifies aluminum, the app forces Opus to quote it like a steel job. Not because Opus doesn't know better — it does. The problem is structural: the material catalog has no aluminum entries, so Opus uses steel keys because those are the only ones available. On top of that, the code is injecting steel-specific consumable overrides that actively block Opus from applying its own aluminum fabrication knowledge. Finally, a hardcoded bug in the PDF generator maps "clear coat" to "Paint."

Opus already knows what filler rod aluminum TIG welding requires, how to estimate laser cutting costs, what size aluminum sheets come in, and how to reason about aluminum fabrication. We need to stop getting in its way — not add more instructions.

## Acceptance Criteria

Running the LoanDepot two-sign job (aluminum, clear coat, 38.5×128" and 38.5×138") produces:

1. Materials list uses aluminum profile catalog entries — not steel keys
2. Sheet stock reflects real aluminum sheet quantities with dimensions shown (the app should tell the user what size sheets to order, not just "1 pcs")
3. Hardware section includes a laser cutting line item — Opus estimates the cost from its knowledge of panel dimensions and cut complexity
4. Consumables reflect aluminum TIG fabrication — Opus determines the specifics
5. Finishing section reads "Clear Coat (in-house)" — not "Paint (in-house)"
6. A standard steel cantilever gate quote is completely unaffected

## Constraint Architecture

**Files to modify:**
- `backend/calculators/material_lookup.py` — add aluminum profile catalog entries with placeholder pricing
- `backend/calculators/ai_cut_list.py` — remove hardcoded steel consumable overrides; allow Opus to add laser cutting hardware line items; pass material type context
- `backend/pdf_generator.py` — fix clear coat finish label detection

**DO NOT modify:**
- Labor calculator (P37 grind fix stands)
- Question tree JSON files
- Gate or railing calculators
- Any rules that don't specifically override aluminum behavior

**Core principle:** Every fix in this prompt is about removing a constraint or filling a catalog gap — not adding instructions. If Opus can figure it out from its own knowledge, let it.

## Decomposition

### Fix 1: Add aluminum entries to the material catalog

`material_lookup.py` has no aluminum profiles. Add common aluminum sizes with placeholder pricing marked clearly for Burton to update with real Wexler/Osorio supplier quotes. The naming convention should be consistent and distinguishable from steel entries so Opus can select the correct key based on material type.

Include: common aluminum square tube sizes, flat bar, angle, and sheet stock. For sheet stock — include the real sheet dimensions in the catalog entry so the app can display them and Opus can reason about quantity correctly.

### Fix 2: Remove hardcoded steel consumable overrides

Find where the code is injecting steel consumables (ER70S-6 wire, 75/25 Ar/CO2 shielding gas) regardless of material type. When the job material is aluminum, these overrides should not fire. Remove the constraint and pass Opus the material type — it will apply the correct aluminum fabrication consumables from its own knowledge.

### Fix 3: Allow laser cutting as a hardware line item

When the job description mentions laser-cut or CNC-cut sheet panels, the hardware structure should allow Opus to add a subcontracted line item for laser cutting. The app currently may not pass Opus enough context about what hardware line items are valid to add. Confirm Opus can see the hardware section as an open field for subcontracted costs, and pass it the panel dimensions. Opus will estimate the cost.

### Fix 4: Fix the clear coat finish label

In `pdf_generator.py`, find the finish method label logic. "Clear coat," "clearcoat," and "clear_coat" should map to "Clear Coat (in-house)" — not "Paint (in-house)." This is a code bug, not an Opus issue. Fix the string matching.

## Evaluation Design

**Test 1: LoanDepot two-sign quote**
Run CS-2026-0056 description again: aluminum, clear coat, laser cut logo panels, ESP32 waterproof enclosure.
- Materials: aluminum catalog keys, real sheet dimensions and quantity
- Hardware: laser cutting line item present with a reasonable estimate
- Consumables: aluminum TIG — Opus determines specifics
- Finishing: "Clear Coat (in-house)"

**Test 2: Cantilever gate — nothing changes**
Run the standard steel gate job. Steel profiles, steel consumables, no laser cut line, unaffected labor.

**Test 3: Mixed check**
If a job is mild steel but mentions "clear coat," the finish label should still correctly read "Clear Coat (in-house)" — the label fix applies to all jobs, not just aluminum.
