# FAB_KNOWLEDGE.md — CreateStage Fabrication Knowledge Base

**Purpose:** Reference knowledge for AI prompts in the CreateStage quoting app. Covers build sequences, welding processes, surface prep, material selection, and labor estimation rules for structural steel fabrication.

---

## 1. WELDING PROCESSES — When to Use What

### MIG (GMAW) — Primary Process for CreateStage Work
- **Wire:** ER70S-6 is the workhorse. Good wetting action, handles light mill scale and surface contamination better than ER70S-3.
- **Gas:** 75/25 (Ar/CO₂) standard for most steel. 100% CO₂ is cheaper but spatter is higher and penetration is more aggressive — good for thick material (≥3/8"), bad for thin sheet.
- **When to use MIG:**
  - Structural frames, furniture legs, railings, gates
  - Mild steel ≥12 gauge (0.105")
  - Long welds where TIG speed penalty would be prohibitive
  - Tack welds on all job types

### TIG (GTAW) — Precision and Aesthetics
- **Filler:** ER70S-2 for mild steel (triple-deox, handles dirty base better). ER308L for 304 stainless. ER309L for mild-to-stainless dissimilar welds.
- **When to use TIG:**
  - Stainless steel (any finish) — MIG spatter ruins stainless finish
  - Thin sheet (≤14 gauge / 0.075")
  - Visible welds that will be brushed or left raw (decorative railings, furniture accents)
  - Root pass on pipe/tube where full penetration is required
  - Any weld that will be ground flush and polished
- **When NOT to use TIG:**
  - Heavy structural (inefficient, no benefit over MIG on ≥1/4" with E71T or ER70S-6)
  - Outdoor work in wind (shield gas gets blown away)

### Stick (SMAW) — Field Repairs, Heavy Structural
- E6013 for sheet/light structural (easy slag, AC-compatible)
- E7018 for structural (requires dry rods, high strength, low hydrogen)
- E6011 for dirty/rusty/outdoor work (AC or DC, penetrates through contamination)
- **When to use Stick:**
  - Field repairs where gas cylinders aren't practical
  - Heavy plate (≥1/2") where MIG would require multiple passes
  - Gate posts being welded to already-installed concrete anchors

### Flux-Core (FCAW) — Not Standard at CreateStage, Know It for Bids
- E71T-11 is self-shielded (no gas) — good for outdoor structural, dirty metal
- E71T-1 is gas-shielded — better bead quality, less spatter than self-shielded
- **Deposition rate is higher than MIG** — factor this into labor if subbing out structural work

---

## 2. JOINT TYPES AND PENETRATION RULES

### Fillet Weld (Most Common)
- **Throat size = 0.707 × leg size**
- Minimum fillet size per AWS D1.1:
  - Base metal ≤1/4": min 1/8" fillet
  - Base metal 1/4" to 1/2": min 3/16" fillet
  - Base metal 1/2" to 3/4": min 1/4" fillet
  - Base metal >3/4": min 5/16" fillet
- **Rule of thumb:** Fillet size = 3/4 × thinner plate thickness (gives adequate strength without overwelding)
- **Overwelding = wasted time + heat distortion.** A 3/16" fillet is almost always sufficient for furniture legs on 1" tube.

### Butt Welds (Full Pen on Critical Structural)
- Single V-groove: base metal ≤3/4" (60-70° included angle, 1/16" root gap, 1/16" root face)
- Double V-groove: base metal >3/4" (back-gouge required)
- **For quoting purposes:** Full pen butt welds add ~3× the labor of a fillet weld of equal length.

### Corner Joints (Tube Frames)
- Inside corner: fillet weld, no prep needed
- Outside corner (miter): requires gap control, tack in sequence to manage pull
- Tube coped joints: add 15-20% labor premium for layout + fitting vs simple butt

---

## 3. DISTORTION CONTROL — CRITICAL FOR LABOR ACCURACY

### Sources of Distortion
- Heat from welding causes the base metal to expand during welding and contract during cooling
- **Contraction always wins** — parts pull toward the weld
- Thin material warps more than thick (less mass to resist)

### Mitigation Strategies (Affect Build Sequence)
1. **Backstep welding:** Weld in short segments opposite the direction of travel. Adds ~20% time but reduces distortion on long seams.
2. **Balanced welding:** Alternate welds on opposite sides of an assembly. Essential for flat bar and sheet panels.
3. **Pre-set (pre-bow):** Intentionally fixture parts slightly out-of-square, anticipating pull. Zero added time if fixturing is designed in.
4. **Clamp and tack sequence:** Tack all corners before any continuous welds. Standard practice, no premium.
5. **Intermittent welds:** Where full weld isn't structurally required, skip 2" every 4" (2"/4" skip). Cuts heat input and distortion. Code-compliant for many non-structural applications.

### Distortion Risk by Job Type
| Job Type | Risk | Primary Control |
|---|---|---|
| Furniture (flat bar top) | HIGH | Alternate welds, backstep |
| Railing (post-to-rail) | MEDIUM | Tack sequence, balanced |
| Gate (diagonal frame) | HIGH | Pre-set, weld toward center |
| Sign frame (thin sheet) | HIGH | TIG or intermittent MIG |
| Structural frame (heavy) | LOW | Mass absorbs heat |

---

## 4. SURFACE PREP AND FINISH — CONDITIONAL RULES

### Mill Scale
- **What it is:** Iron oxide layer that forms on hot-rolled steel during manufacturing. Blue-gray, hard, slippery.
- **Weld through it?** Yes, ER70S-6 is formulated to tolerate mill scale. But for best quality, remove at weld areas.
- **Remove mill scale ONLY when:**
  - Finish is clear coat, raw/waxed, brushed, or patina
  - Customer-specified (architectural/decorative work)
  - TIG welding (mill scale causes porosity with TIG — ALWAYS remove for TIG)
  - Powder coat adhesion specs require it (some coaters require near-white blast)
- **Do NOT include mill scale removal for:**
  - Powder coat (standard prep is clean + prime, not blast unless spec'd)
  - Paint (primer handles mill scale)
  - Galvanized (galvanizer does their own prep)

### Mill Scale Removal Methods
- **Vinegar bath (dilute acetic acid):** 20-30% white vinegar, submerge 12-24 hours. Zero cost for chemicals, high labor (handling, rinsing, neutralizing, drying). Best for small parts with complex geometry.

### Post-Vinegar Cleanup Method
1. Rinse under warm running water
2. Scrub with dish soap and a scotch-brite pad (red, medium grit)
3. Rinse again thoroughly
4. Dry with a clean towel

This is a CLEANING step, not a finishing step — surface finish comes from subsequent grinding. Do not introduce finishing operations (wire brushing, chemical neutralizers, compressed air) unless the specific finish calls for it.

- **Angle grinder + flap disc:** 80-grit first, then 120-grit for consistency. Fastest for flat stock and accessible areas. Use 40-grit for thick scale on old material.
- **Wire wheel:** Good for welds and transitions, not for large flat areas.
- **Phosphoric acid wash (Metal Prep, Ospho):** Converts scale to iron phosphate primer. Good for outdoor structural that will be painted. Not for stainless.
- **Sandblasting:** Commercial-grade removal. Required for structural coating specs (SSPC-SP6 or better). Subcontract cost, factor in.

### Clear Coat / Raw / Waxed Steel
- Remove mill scale entirely first
- Wipe with acetone or MEK, let dry completely
- Apply clear coat within 30-60 min of final cleaning (steel re-oxidizes fast, especially humid)
- Clear coat options: lacquer (cheapest, not UV stable), urethane, or Permalac (best for interior)
- Wax option: Carnuba or Renaissance Wax — zero rust protection but great look, requires reapplication

### Brushed Steel Finish
- Grind welds flush with 60-grit fiber disc on angle grinder
- Switch to 80-grit, then 120-grit, always in ONE DIRECTION
- Finish with scotch-brite or surface conditioning disc — establishes linear grain
- Wipe with acetone before any coating
- **Labor premium:** 2-4× weld finishing vs leaving welds visible

### Patina (Chemical)
- Remove mill scale first (flap disc or vinegar bath)
- Apply patina solution (commercial, e.g., Sculpt Nouveau, or DIY acid/salt)
- Let flash rust establish for desired look — could be 1 hour to several days
- Stop with Permalac or museum wax when desired stage is reached
- **Very skill-sensitive** — quote with artist's premium if customer-facing

### Powder Coat
- Prep: degrease (acetone or pre-wash), remove sharp edges (spatter, burn-through), prime if specified
- No vinegar bath required
- Send to powder coater pre-assembled (panels that can't go through oven separately)
- **Factor transport:** Round trip to coater = half-day labor minimum
- Colors: standard RAL colors off-the-shelf. Custom colors = premium, longer lead time.

### Paint / Rattle Can
- Degrease, scuff with 220-grit, prime with self-etching primer on bare steel
- Top coat when prime is fully cured (check product for cure time — typically 1 hour)
- Not suitable for structural or outdoor exposed work

---

## 5. BUILD SEQUENCE — BY JOB TYPE

### General Principles (Apply to All Jobs)
1. **Measure twice, cut once.** Layout before any cuts. Mark with silver marker on steel.
2. **Cut oversized, trim to fit.** Rough cut with chop saw or plasma, trim with cold saw or angle grinder for final fit.
3. **Deburr all cuts before fitting.** Sharp edges cause poor fit-up and weld defects.
4. **Tack before continuous welding.** Always. Allows adjustment before committing.
5. **Check square and level at every stage.** Not just at the end.
6. **Weld seams before cosmetic grinding.** Don't grind then weld — heat will re-warp.
7. **Surface prep after all welding is done.** Not before.

### Furniture (Tables, Benches, Shelving)

**Structural Frame:**
1. Layout and cut all tube stock
2. Deburr all cuts
3. Fixture and tack frame joints, check square
4. Complete frame welds (balanced)
5. Grind frame welds (if visible)

**Decorative Elements:**
6. Vinegar bath raw flat bar stock (full lengths — see Section 11)
7. Heavy grind stock to finish surface
8. Cut flat bar to final dimensions from prepped stock
9. Cut spacer pieces if applicable
10. Assemble spacers (stack and tack pairs)
11. Fit decorative elements — measure, position, clamp each piece
12. Tack, verify, weld
13. Light cleanup on weld areas only

**Final Finish:**
14. Check level and twist
15. Wipe with acetone
16. Apply finish
17. Install glass/wood elements
18. Install hardware

### Railings (Interior and Exterior)
1. Measure in-field — do not trust drawings alone for existing structures
2. Fabricate top rail and bottom plate as flat assemblies
3. Cut and fit balusters (pickets) — jig for spacing consistency
4. Tack all balusters before welding (critical — once welded, spacing is locked)
5. Weld balusters from center out to minimize accumulated spacing error
6. Weld top and bottom rail connections
7. Grind welds visible from walking side
8. Prime/paint before installation (touch up field welds after installation)
9. Install — lag or epoxy anchors per spec

### Gates (Driveway, Pedestrian)
1. Lay out frame on welding table — square is critical
2. Cut frame members with compound miter where needed
3. Tack and check diagonal — gates are LARGE, distortion is amplified
4. Weld frame with backstep technique on long members
5. Fit and weld infill (pickets, flat bar pattern, mesh, etc.)
6. Add hardware mounting plates (hinges, latch) BEFORE surface finishing
7. Mock-install hinges and check swing before powder coat
8. Surface prep and finish
9. Install hardware
10. Install gate — shim for level and plumb before final bolt torque

### Signs and LED Frames
1. Cut and fit outer frame first (sets all other dimensions)
2. Fit internal dividers or channel mounting points
3. Weld frame — intermittent welds on thin material to minimize heat
4. Test-fit LED channel in openings before welding closed any section
5. Drill and tap for mounting points
6. Install backs (sheet or panel) before finish if painting together
7. Surface prep and finish
8. Wire LED channels — use fish tape or pull strings before final assembly closes openings
9. Terminate wiring, test before install
10. Install

### Structural/Custom Fabrication
1. Review drawings for material callouts and weld symbols
2. Cut all stock to size — organize by assembly section
3. Lay out base plate or anchor points first (establishes datum)
4. Build up from datum — fit and tack in assembly sequence
5. Inspect fitment before welding
6. Weld in stages — intermediate inspections
7. Grind or treat welds per spec
8. Final inspection and dimension check
9. Prime and paint or send to coater

---

## 6. MATERIAL PROPERTIES — PRACTICAL QUICK REFERENCE

### Mild Steel (A36, A500, A513)
- Most common shop material. A36 is plate/structural. A500/A513 is tube.
- Yield: 36,000 PSI (A36). Ult: 58,000-80,000 PSI.
- Excellent weldability. No preheat required for material ≤1" thick in normal shop conditions.
- **Preheat required when:** Material ≥1" thick, temp below 32°F, high restraint joints, or high carbon/alloy content.

### Stainless Steel (304, 316)
- 304 is standard. 316 is marine grade (molybdenum addition = better chloride resistance).
- **ALWAYS use stainless filler wire on stainless** — mild steel filler will rust at the weld.
- **Avoid contamination:** Dedicate stainless grinding wheels, wire brushes, and clamps. Carbon steel particles embedded in stainless = rust.
- **Heat sensitive:** TIG preferred for thin material. Keep heat input low. Back-purge with argon for full-pen welds on pipe/tube (prevents "sugaring" on inside).
- Much harder to cut than mild steel — adjust chop saw RPM down, use blades rated for stainless.

### DOM Round Tube (Drawn Over Mandrel)
- Seamless appearance, tighter tolerances than ERW tube
- Premium cost but critical for decorative work where seam would show
- Weld the same as ERW. DOM designation is about the manufacturing process, not composition.

### Hot-Roll vs Cold-Roll Sheet
- Hot-roll (HR): scale present, slightly rough, dimensions less precise. Fine for structural.
- Cold-roll (CR): smoother, tighter tolerances, more expensive. Better for visual surfaces, powdercoat adhesion.
- **For furniture work visible surfaces: specify CR when quoting premium pieces.**

---

## 7. LABOR ESTIMATION RULES

### General Time Standards
| Operation | Time |
|---|---|
| Layout and mark cut | 2-5 min/piece (simple), 10-20 min/piece (complex) |
| Chop saw cut (1" tube) | 2-3 min/cut including setup |
| Chop saw cut (2" tube) | 3-5 min/cut |
| Plasma cut (straight) | 5-15 min setup + travel speed |
| Deburr/prep cut end | 1-2 min/end |
| Cope/notch tube end | 10-20 min/end |
| MIG tack weld | 1-2 min/tack (setup + tack) |
| MIG fillet weld (3/16") | 12-18 in/min travel speed → calc from length |
| TIG fillet weld | 4-6 in/min travel speed |
| Grind weld flush | 5-10 min/foot of weld |
| Brush finish | 15-30 min/sq ft |
| Vinegar bath | 0.75-1.25 hr active handling only. Soak time (12-24 hr) is UNATTENDED and must NOT be counted as labor hours. |
| Die grinder cleanup (tight access) | 3-5 min per weld area |
| Powder coat transport | 3-4 hr minimum (round trip) |

### Tooling and Access
A fabricator's ability to finish a weld area depends on what tool can physically REACH it. Common shop tooling ranges from large to small:
- 4.5" angle grinder: open, accessible surfaces. Fast removal.
- Die grinder with 2" roloc-style discs: constrained spaces, between layers, inside frames. Slower but reaches where angle grinders cannot.
- Hand files, emery cloth: very tight spots, final touch-up.

"Inaccessible" usually means "requires smaller tooling and more time," not "physically impossible." Adjust labor time rather than skipping the operation.

### Flat Bar Pyramid — TRUE 3D Design (Not Flat Concentric Squares)
The CreateStage flat bar pyramid is a 3D stepped pyramid, NOT flat concentric squares 
in one plane. Each layer steps both INWARD (horizontally) and DOWNWARD (vertically), 
creating a recessed pyramid effect visible from the side.

Additional complexity: flat bar pieces at the corners of adjacent layers CROSS/INTERSECT 
each other (woven corner detail). Pieces must be sequenced so alternating layers go 
over/under at intersections. This is NOT a simple tack at the corner — it's an 
overlapping joint requiring careful fit-up and sequencing.

Typical proportions from built examples:
- Step per layer: ~1" inward per side + ~0.5" vertical drop
- Layer count for 18-20" interior span: 7-10 layers
- Corner welds: each corner intersection = 2 weld points (face + overlap)
- Total welds for 8-layer pyramid: ~96 weld points (8 layers × 4 pieces × 3 welds each)

Build sequence for pyramid (cannot deviate):
1. Build and weld structural frame first, completely
2. Flip frame upside down on flat table
3. Place Layer 1 (outermost) using spacers for horizontal and vertical position
4. Tack Layer 1, verify position, weld corners
5. Place Layer 2, feed pieces UNDER or OVER Layer 1 corners per the pattern
6. Tack, verify, weld — continue inward
7. Do NOT skip layers or weld out of sequence — corner intersections lock order

### Precision Decorative Placement — A Separate Labor Category
Decorative elements that require measured positioning before each weld are fundamentally
different from structural assembly. Do NOT estimate these as fast tack welds.

**Examples:** Flat bar pyramids, concentric square patterns, evenly-spaced pickets,
ornamental grids, stepped inlays — anything where position accuracy is part of the finish.

**Per-piece workflow (cannot be skipped):**
1. Measure the step distance from the previous piece (e.g., 1/4" inward per layer)
2. Mark reference lines or use a spacer/jig
3. Position piece against spacer, check flush and level
4. Clamp or hold
5. Tack — check position hasn't shifted, adjust if needed
6. Weld both sides (face weld + edge weld on 1×1/8" flat bar)
7. Move to next piece — reset spacer, repeat

**Time standard:** 5-8 minutes per piece for skilled fabricator with a jig.
Without a jig (measuring each piece individually): 8-12 minutes per piece.
Multiply by qty — 120 pieces at 5 min = 10 hrs, at 8 min = 16 hrs.
Burton's shop with jig/spacer method runs ~3-4 min/piece for practiced patterns.

**Key insight for AI estimation:** A 30-layer × 4-piece flat bar pyramid = 120 precision
placements. This dominates the weld time on decorative furniture jobs. Do not
underestimate by treating these as simple tack welds.

### Stacked Spacer Fabrication
Cut list must show INDIVIDUAL pieces, not assembled spacers.
- Each spacer location = 2 pieces (if "two stacked")
- Example: 32 locations × 2 pieces = 64 individual cuts at 1/2" long
- Assembly time: pair, align, tack each set: 2-3 min per pair
- 32 pairs × 2.5 min = ~1.3 hours spacer assembly labor (separate line item)

### Weld Deposition Rate for Labor Calc
- MIG 0.035" wire, 250A, 28V: ~3.5 lb/hr deposition
- MIG 0.045" wire, 300A, 30V: ~6.0 lb/hr deposition
- TIG 1/16" filler: ~0.8 lb/hr deposition
- **For shop quoting:** Use weld length + joint type to estimate time, not deposition rate.

### Skill Multipliers
- Flat position (1F/1G): 1.0× base time
- Horizontal (2F/2G): 1.2×
- Vertical (3F/3G): 1.4×
- Overhead (4F/4G): 1.7×
- TIG vs MIG: 2.5-3× for same weld

### Finishing Tiers — Labor Multipliers
| Tier | Description | Multiplier |
|---|---|---|
| Industrial/Textured | 1 pass, texture IS the finish | 1.0× |
| Smooth Brushed | Consistent directional grain | 1.5× |
| Satin | Minimal scratches, soft sheen | 2.5× |
| Mirror Polish | Reflective, no visible marks | 4.0× |

Default: Industrial/Textured unless customer specifies otherwise.

### Complexity Factors (Apply to Total Estimate)
- Simple, familiar job type: 1.0×
- First time building job type: 1.3× (learning curve)
- Complex fitting with tight tolerances: 1.2×
- Very small parts, tight spaces: 1.3×
- Very thin material (≤16ga): 1.4×
- Stainless, any thickness: 1.5×
- Customer revision mid-project: 1.5× on affected sections minimum

---

## 8. FINISH SELECTION GUIDE (FOR QUOTING)

| Customer Need | Recommended Finish | Notes |
|---|---|---|
| Interior furniture, industrial look | Clear coat (Permalac) | Show the steel |
| Interior furniture, modern | Powder coat | Color options, durable |
| Exterior gate/railing | Powder coat | Best durability outdoors |
| Decorative/artistic piece | Patina or brushed + clear | High labor, high value |
| Commercial/institutional | Powder coat | Standard spec |
| Marine/outdoor coastal | Powder coat + 316SS or galvanize | Extra upsell |
| Budget | Oil-based paint | Client buys paint, you apply |

---

## 9. MILL SCALE REMOVAL — DECISION TREE

```
Is finish POWDER COAT or PAINT?
  → YES: Skip vinegar bath / acid wash. Clean + degrease only.
  → NO (raw/clear coat/brushed/patina):
      Is it TIG welding?
        → YES: Remove scale at ALL weld areas before welding (grind or flap disc)
        → NO: Remove scale AFTER all welding is done (vinegar bath or grind)
```

---

## 10. SHOP SAFETY (RELEVANT TO SEQUENCING AND LABOR)

- **Grind away from welds** — grinding sparks on a fresh weld bead can cause hydrogen cracking if bead is still hot. Wait for weld to cool (gray, not glowing) before grinding adjacent areas.
- **Plasma cut produces hexavalent chromium on stainless** — always use air-fed respirator or full ventilation.
- **Vinegar fumes** — work outdoors or with exhaust ventilation.
- **Galvanized steel welding** — produces zinc oxide fumes. ALWAYS outdoors + respirator. Never weld galvanized without full PPE.
- **Cutting fluid on cold saw** — required for clean cuts and blade life. Use Tap Magic or equivalent.

---

## 11. DECORATIVE STOCK PREP — PROCESS ORDER

### Why This Matters
You CANNOT grind tiny cut pieces to a furniture-grade finish. Small pieces move, flex, and are impossible to hold steady against a flap disc. The finish will be inconsistent and you'll waste hours fighting the material. The solution: do ALL finish work on full-length raw stock BEFORE cutting to size.

### The Correct Sequence (Decorative Flat Bar, Visible Steel)

**Phase 1 — Stock Prep (BEFORE any cutting)**
1. Vinegar bath full-length raw stock — submerge as much as fits in the bath
2. Soak 12-24 hours (UNATTENDED — this is not labor time)
3. Pull stock, rinse immediately with warm water
4. Scrub with dish soap and red scotch-brite pad (medium grit)
5. Rinse again thoroughly
6. Dry with a clean towel
7. Heavy grind with flap disc — 80 grit then 120 grit on ALL faces
6. This is where the BULK of grind time happens (60-70% of total grind hours)
7. Stock is now finish-ready — smooth, scale-free, consistent surface

**Phase 2 — Cut to Size**
8. Transfer cut list dimensions to the prepped stock
9. Cut all pieces to final length — chop saw or band saw
10. Light deburr on cut ends only (faces are already finished)

**Phase 3 — Assembly**
11. Fit, tack, and weld per build sequence
12. Light cleanup pass on WELD AREAS ONLY — die grinder or small flap disc
13. Do NOT re-grind entire pieces — only blend the weld spots

**Phase 4 — Final Finish**
14. Wipe entire assembly with acetone
15. Apply clear coat / paint / finish

### When This Applies vs When It Doesn't
- **APPLIES:** Any job with visible flat bar, clear coat/raw/brushed/patina finish, ornamental elements where surface consistency matters
- **DOES NOT APPLY:** Structural-only work, powder coat jobs (coater preps), tube/pipe frames

### Labor Split
Split grind hours into TWO line items:
- **Stock Prep & Grind:** Heavy grinding on raw stock before cutting. 60-70% of total grind time.
- **Post-Weld Cleanup:** Light blending of weld areas only after assembly. 1-2 hours max.

### Spacer and Shim Dimensions
When a design calls for spacers built from stacked material, the cut list shows individual PIECE dimensions, not the assembled unit or the gap they create. These are often three different numbers.

### Vinegar Bath Labor
Soak is NOT labor. Active handling only: setup/submersion 15-30 min + pull/rinse/neutralize/dry 30-45 min = 0.75-1.25 hours total.

---

## 12. FABRICATION REASONING PRINCIPLES

These are thinking patterns experienced fabricators use. They are NOT rules for specific jobs — they apply universally.

### Principle 1: Workability Drives Process Order
Before assigning any operation to a step, ask: "Can I physically perform this operation on this piece, at this size, in this context?"
- Can the piece be safely held against a grinder at its current size?
- Is there physical access to reach the work area at this stage of assembly?
- Will a later assembly step block access to something that needs finishing?
If an operation becomes impossible or impractical after a certain step, it MUST happen before that step.

### Principle 2: Access Decreases as Assembly Progresses
Physical access to interior areas DECREASES as pieces are added. Recognize when:
- Adding the next piece blocks access to grind, clean, or finish behind it
- Workspace is too constrained for clamps, grinders, or torch access
- A piece can't be independently held because there's nothing stable to brace against until adjacent pieces are fixed
When access decreases progressively, complete each area before it becomes unreachable. This may mean permanently fixing each piece as it's placed rather than positioning everything first.

### Principle 3: Component vs Assembly vs Spacing Dimensions
A description may reference multiple dimensions that sound similar but are physically different:
- Size of an INDIVIDUAL COMPONENT (what you cut)
- Size of an ASSEMBLED UNIT (multiple components joined)
- SPACING or GAP between elements (empty space, not a physical piece)
The cut list shows what the fabricator PHYSICALLY CUTS — individual component dimensions. Ask: "What does the saw actually cut?"

This distinction is especially critical for small components like spacers, shims, and standoffs. A description might reference a GAP dimension (space between elements), a PIECE dimension (what you physically cut), and an ASSEMBLED dimension (multiple pieces joined). All three may appear in the same sentence. The cut list must trace back to: what does the saw blade actually pass through? That is the piece dimension.

### Principle 4: Joint Design Determines Cut Geometry
Before specifying how to cut a piece, ask: "What happens where this piece meets the next one?"
- If two pieces form a CONTINUOUS PROFILE at a corner (eye sees one unbroken line) → cut must create that seamless meeting
- If two pieces CROSS, OVERLAP, LAP, or STACK → each piece needs its full cross-section visible at the intersection — that's the design
- If pieces BUTT end-to-end → joint is about fit and weld access
Same material can require different cut geometries depending on where it sits. Assign cut type by JOINT INTENT, not material.

### Principle 5: Surface Finish Is a Design Choice, Not Just Prep
Grinding isn't always about smoothness. Different grits create different TEXTURES, and the texture may BE the finish:
- Coarse abrasive = bold industrial texture with visible directional lines
- Fine abrasive = smooth refined surface
- Multiple progressively finer passes REMOVE texture toward polish
Ask: "Is the customer trying to CREATE a texture, or REMOVE one?" If a single pass IS the look, additional passes waste time and money. Only escalate when customer explicitly asks for smoother/polished.

### Principle 6: Constraints Propagate Forward
Every fabrication decision constrains later steps:
- Cutting to size constrains finishing (small pieces harder to hold/grind)
- Welding in place constrains access behind it
- Finish type determines which prep steps exist
- Assembly sequence determines which pieces can be independently positioned
Trace through each step and ask: "What does this step make impossible or harder later?" Reorder to avoid conflicts.

---

*Last updated: 2026-03-02 (Session 12 — reasoning sharpening, tooling access, post-vinegar cleanup)*
*Source: CreateStage shop practices + AWS D1.1 field experience + welding engineering fundamentals*
