# PROMPT 34 — Labor Reality Check & Shop PDF Materials

## 1. Problem Statement

Three things are broken in the quoting output. All three stem from the same root: the system was built to handle pieces individually, but fabrication doesn't work that way.

### Labor: Cut & Prep (13 hrs on CS-2026-0044 — should be ~3)
The calculator charges 4 minutes per piece regardless of context. A fabricator doesn't measure and set up a new stop for every identical picket. You set the fence once, then feed stock — 127 pickets takes maybe 45 minutes, not 8.5 hours. The system needs to understand **batch cutting**: identical pieces (same profile, same length, same cut type) share setup time.

### Labor: Grind & Clean (7.1 hrs — should be ~2-2.5)
The calculator counts every weld joint and charges grind time per joint. This is correct for indoor furniture or bare metal work where you actually grind welds smooth. But outdoor painted steel? You're just doing a cleanup pass — knock off spatter, hit sharp edges, flatten any high spots. One guy with a flap disc walks the assembly. The system needs to understand the **difference between full grind (indoor/bare metal) and cleanup pass (outdoor painted)**.

### Shop PDF: Materials Section
The materials section lists 28 individual pieces with individual prices. Nobody orders steel this way. A fabricator needs: "How many sticks of 2x2 do I need? How much does it weigh? What's it cost?" The per-piece detail already exists in the Cut List section — there's no reason to duplicate it in Materials. The system needs to **aggregate materials by profile** for the shop PDF, including weight so the fabricator knows what they're picking up or having delivered.

## 2. Acceptance Criteria

### AC-1: Cut & Prep reflects batch cutting reality
- Identical pieces in the cut list share setup time — only the first piece in a batch needs full measure/setup
- Different pieces still get individual setup time
- Miter cuts take longer than square cuts regardless of batching
- The math should produce ~2-3 hrs for the CS-2026-0044 job (was 13 hrs)
- Reasoning line explains how batches were identified and counted

### AC-2: Grind hours reflect finish type
- **Outdoor painted/primed work**: Flat cleanup rate that scales with project size, not per-joint. Think "how long does it take one guy with a flap disc to walk this entire assembly?" Add time for miters (more cleanup needed at miter joints). Add time for mill scale removal if applicable.
- **Indoor/furniture/bare metal/polished**: Keep existing per-joint formula — these genuinely get ground smooth
- The finish type is already available in the job parameters (finishing field)
- Reasoning line explains which grind path was taken and why

### AC-3: Shop PDF Materials = aggregated by profile
Replace the per-piece materials table in the shop PDF with a profile-grouped summary showing:
- Profile name and human-readable description
- Total linear footage for that profile
- Number of sticks to order (based on stock lengths)
- Estimated weight (use weight-per-foot from material catalog × total footage)
- Total material cost for that profile
- **Plates and sheets**: Show piece count, not linear footage (they're area-sold)
- **Concrete**: Separate summary line below the steel table (concrete isn't steel stock)
- **Material subtotal must equal the existing number to the penny** — this is display aggregation, not recalculation
- The Cut List section keeps all per-piece detail (unchanged)
- The Stock Order Summary section stays as-is (shows remainder/leftover)

## 3. Constraint Architecture

### Files to modify:
- **`backend/calculators/labor_calculator.py`** — Cut prep calculation (~line 278) and grind calculation (~lines 229-233). The punched_channel grind fix from P33 (lines 298-310) becomes irrelevant for outdoor work but doesn't need removal.
- **`backend/pdf_generator.py`** — Shop PDF materials rendering (~lines 430-453). Replace per-piece loop with aggregated-by-profile table. Add weight column.
- **`backend/pricing_engine.py`** — `_aggregate_materials()` method. Add `weight_lbs` and `total_cost` fields to the aggregated output.

### Files NOT to modify:
- `ai_cut_list.py`, `pdf.py` router, `frontend/`, client PDF

### Hard rules:
- Python 3.9 — no `str | None` union syntax
- Don't break `priced_quote["materials"]` per-piece data — other code uses it
- Material subtotal must be mathematically identical after aggregation
- All existing tests must pass

## 4. Decomposition

### Batch cut logic
Look at the cut list. Group by (profile, length, cut_type). Each group is a batch. First piece in a batch takes longer (measure, set stop). Additional identical pieces are just feed-and-cut. Figure out sensible times for each — you're a fabricator at a chop saw, not a robot. Write reasoning that explains the batch groupings.

### Outdoor grind logic
Check the finish type from job parameters. If it's paint, primer, or any outdoor coating — this is cleanup work, not grinding. Scale the time based on overall project size (more steel = more surface to walk). Account for miters (they need more cleanup). Account for mill scale removal. If it's indoor, bare metal, polished, or furniture — keep the existing per-joint math because those welds DO get ground smooth.

### Materials aggregation
`_aggregate_materials()` in pricing_engine.py already groups by profile and calculates sticks. Add weight (WEIGHT_PER_FOOT × total_feet) and total cost (sum of line_totals for that profile). Then update the shop PDF renderer to use this aggregated data instead of looping through individual pieces. Handle plates/sheets as piece counts and concrete as a separate line.

### Tests
- Batch cut: 127 identical pickets should take dramatically less than 127 × 4 minutes
- Outdoor grind: 160-piece outdoor painted project should be ~2-3 hrs, not 7+
- Indoor grind: still uses per-joint formula (unchanged behavior)
- Materials aggregation: sum of profile costs equals material subtotal exactly
- Plates show as piece count, concrete below the table

## 5. Evaluation Design

### Run CS-2026-0044 equivalent and check:
- **Cut & Prep**: Should drop from 13 hrs to ~2-3 hrs
- **Grind & Clean**: Should drop from 7.1 hrs to ~2-2.5 hrs
- **Shop PDF Materials**: Should show ~5-6 profile rows with weight column, not 28 per-piece rows
- **Material subtotal**: Must match previous value exactly
- **Cut List section**: Unchanged — still shows every piece
- **All existing tests pass**: `pytest tests/ -v`
