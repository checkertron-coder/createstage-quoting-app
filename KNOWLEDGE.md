# KNOWLEDGE.md — CreateStage Fabrication Domain Knowledge

**Purpose:** Accumulated domain knowledge from 31 prompt iterations. This file is tool-agnostic — any AI that reads this repo (Claude Code, Codex, Cursor, Copilot) inherits the full context. Update this file after every prompt that teaches us something new.

**Last updated:** Prompt 31 (March 5, 2026)

---

## 1. Metal Fabrication — Hard Rules

These are non-negotiable. Violating any of these produces a quote a fabricator would laugh at.

### Welding
- **MIG (GMAW) in shop only.** Wind disperses shielding gas. Period.
- **Field welding = Stick (SMAW, E7018).** Always. No exceptions for gates/fences.
- **Dual-shield flux core (FCAW-S)** — strongest/fastest for structural field work, but overkill for fence/gate.
- **TIG (GTAW)** — thin material (<14ga), visible joints, stainless, aluminum. Never outdoors.
- **Mill scale removal mandatory** — grind 1-2" from each cut end before welding. Prevents porosity. Every. Single. Cut.

### Grinding & Cleanup
- **Never grind welds smooth on outdoor gates/fences.** Cleanup only — remove spatter, sharp edges, high spots.
- **36-grit flap disc ONLY** for outdoor painted steel cleanup. No progressive gritting (60/80/120). That's for stainless or polished work.
- **Never use a hand file.** Only angle grinder + flap disc, or die grinder + Roloc disc.
- **Grind & Clean labor for outdoor painted work: 2-3 hours**, not 8+. You're cleaning, not polishing.

### Surface Prep & Finishing
- **Always prime + paint separately** for outdoor steel. Two distinct operations.
- **Surface prep solvent** (not "degreaser") before priming — listed as consumable, not labor.
- **Minimum 3-4 hours** for prime + paint on ~786 sq ft of surface area.
- **Red scotch-brite pad** for scuffing between coats (shop term).

### Concrete & Foundations
- **Chicago frost line = 42"** per Municipal Code 13-132-100.
- **Post embed depth** = above-grade height + 2" ground clearance + 42" embed.
- Example: 10' fence → 120" + 2" + 42" = 164" total post (13.67').
- **Concrete footings are NOT linear stock.** They don't come in 20' sticks. Never show "1 × 20' concrete footing" in a stock order.

### Structural Rules
- **Cross braces/mid-rails required** on fences >6' tall (1 mid-rail for 4-6', 2 for >6').
- **Pre-punched U-channel is industry standard** for fence mid-rails. Pickets slide through holes. Dramatically faster assembly. Labor drops ~35% for fit-and-tack vs drilling/welding individual pickets.
- **Gate panel length = opening × 1.5** — hard rule for cantilever gates. Calculator enforces this, not AI.
- **Overhead support beam qty = 1** — one beam spans the carriage posts. Never 2.

---

## 2. Pre-Punched Channel Specifications

Source: ACI Supply + Gonzato/Indital catalogs

| Picket Size | Hole Size | Channel Size | Profile Key | $/ft |
|---|---|---|---|---|
| 1/2" sq | 9/16" | 1" × 1/2" × 1/8" | `punched_channel_1x0.5_fits_0.5` | $3.50 |
| 5/8" sq | 11/16" | 1-1/2" × 1/2" × 1/8" | `punched_channel_1.5x0.5_fits_0.625` | $4.50 |
| 3/4" sq | 13/16" | 1-1/2" × 1" × 1/8" or 2" × 1" × 1/8" | `punched_channel_2x1_fits_0.75` | $5.50 |

- Sold in 20' sticks.
- AI must use exact profile keys above, not generic "channel" or "u-channel".

---

## 3. Picket Size Standards

| Size | Application |
|---|---|
| 1/2" sq solid | Light residential |
| **5/8" sq solid** | **Standard residential (most common)** |
| 3/4" sq solid | Heavy residential / light commercial |
| 1" sq tube 16ga | Standard commercial |
| 1" sq tube 14ga | Heavy commercial / industrial |

Apache/punched pickets (3/4" × 16ga tube with pressed spear) from Steel Supply LP.

---

## 4. Real Supplier Pricing (Chicago Area)

**Baseline:** Osorio Metals Supply — use these prices + 10% buffer.

**Suppliers:**
- **Osorio Metals Supply** — best prices on common tube stock
- **D. Wexler & Sons** — 4821 S. Aberdeen St, Chicago 60609. 25-30% more expensive than Osorio on tube.

### Square Tube (HR, per foot)
| Size | $/ft | Source | Date |
|---|---|---|---|
| 1" × 1" × 11ga | $1.15 | Osorio #62296 | Jan 2025 |
| 1-1/4" × 1-1/4" × 11ga | $1.37 | Osorio #62296 | Jan 2025 |
| 1-1/2" × 1-1/2" × 14ga | $1.11 | Osorio #62028 | Jan 2025 |
| 1-1/2" × 1-1/2" × 11ga | $1.58 | Osorio #53211 | Oct 2024 |
| 1-3/4" × 1-3/4" × 11ga | $2.40 | Osorio #62028 | Jan 2025 |
| 2" × 2" × 14ga | $1.52 | Osorio receipt | — |
| 2" × 2" × 11ga | $2.49-2.88 | Osorio #42057/#30572 | Jun/Mar 2024 |
| 2-1/2" × 2-1/2" × 11ga | $3.51 | Osorio #22829 | Nov 2023 |
| 3" × 3" × 3/16" | $5.10 | Osorio #63816 | Feb 2025 |
| 3" × 3" × 1/4" | $7.50 | Osorio #63816 | Feb 2025 |
| 5" × 5" × 3/16" | $8.85 | Wexler #108902 | Jun 2024 |
| 6" × 6" × 3/16" | $13.60 | Osorio #39980 | Jun 2024 |

### Angle Iron (per foot)
| Size | $/ft | Source |
|---|---|---|
| 1-1/2" × 1-1/2" × 1/8" | $0.96 | Osorio |
| 2" × 2" × 1/8" | $1.29 | Osorio |
| 2" × 2" × 3/16" | $1.84 | Osorio #62296 |
| 3" × 3" × 3/16" | $2.37 | Osorio #63816 |

### Flat Bar (per foot)
| Size | $/ft | Source |
|---|---|---|
| 1" × 1/8" | $1.10 | Added P10 hotfix |
| 3/16" × 3" | $1.51 | Osorio #62296 |
| 1/4" × 2" | $1.28 | Osorio #62296 |
| 1/4" × 5" | $4.15 | Osorio #22829 |

### Rect Tube
| Size | $/ft | Source |
|---|---|---|
| 4" × 2" × 11ga | $3.42 | Wexler #108902 |

### Pricing Gaps (not yet sourced)
- Square bar (1/2", 5/8", 3/4") — picket stock, Burton orders it but no invoices on file
- 4×4 square tube — fence post material
- Round bar
- HSS profiles (4×4×1/4", 6×4×1/4") — overhead beam stock

---

## 5. Hardware Catalog

### Cantilever Gate
- **Top-mount roller carriages × 2** — gate rides on these, mounted on carriage posts
- **Gravity latch × 1** — self-closing catch at receive post
- **Guide rollers** — top and bottom at receive post, keep gate aligned
- **Motor (optional)** — LiftMaster, DoorKing, etc.

### Fence
- **Post caps** — one per post, decorative/weather seal

---

## 6. Labor Calibration

**Shop rate: $125/hr in-shop, $145/hr field** — controlled via user profile, NOT code.

### Process Hours Reference (10' cantilever gate + 28' fence)
| Process | Correct Range | Notes |
|---|---|---|
| Layout & Setup | 1-2 hrs | Measuring, marking, jigging |
| Cut & Prep | 3-4 hrs | Cutting + mill scale removal |
| **Fit & Tack** | **6-8 hrs** | **Most labor-intensive** — positioning/spacing 137+ pickets |
| Full Weld | 4-6 hrs | Complete all structural + decorative welds |
| Grind & Clean | **2-3 hrs** | Outdoor painted = cleanup only, not polishing |
| Finish Prep | 1-2 hrs | Solvent wipe, masking |
| Prime & Paint | 3-4 hrs | Two separate operations with dry time |
| Hardware Install | 1-2 hrs | Carriages, latch, guide rollers |
| Site Install | 4-6 hrs | Field welding (SMAW), set posts, level, plumb |
| Final Inspection | 0.5-1 hr | Touch-up, operation check |

**Key insight:** Fit & tack is the most expensive step because you're positioning and spacing every picket by hand before welding. Pre-punched channel cuts this by ~35%.

---

## 7. Profile Key Format

Pattern: `{shape}_{dimensions}_{gauge_or_thickness}`

Examples:
- `sq_tube_2x2_11ga` — 2" × 2" square tube, 11 gauge
- `sq_bar_0.625` — 5/8" solid square bar
- `flat_bar_1x0.125` — 1" wide × 1/8" thick flat bar
- `pipe_4_sch40` — 4" pipe, schedule 40
- `hss_4x4_0.25` — HSS 4" × 4" × 1/4" wall
- `punched_channel_1.5x0.5_fits_0.625` — pre-punched channel for 5/8" pickets
- `angle_3x3x0.1875` — 3" × 3" × 3/16" angle iron

**Critical:** AI must output exact profile keys from the catalog. Generic terms like "channel", "tube", or "HSS beam" cause lookup failures.

---

## 8. Consumables (per job)

Standard consumables for a gate + fence job:
- **Welding wire** (ER70S-6, 0.035") — 10-15 lbs
- **Grinding discs** (36-grit flap, 4.5") — 4-6 discs
- **Welding gas** (75/25 Ar/CO2) — refill or partial tank
- **E7018 stick electrodes** — for field welding, 10 lb box
- **Surface prep solvent** — 1 gallon
- **Primer** (zinc-rich or rust-inhibitive) — 2-3 gallons
- **Paint** (exterior DTM enamel) — 2-3 gallons
- **Masking tape/paper** — misc

---

## 9. Common AI Mistakes (Lessons from P18-P31)

These are failure patterns we've seen repeatedly. Any AI generating cut lists or fab sequences MUST avoid these:

1. **Aggregated cut lists** — "25 × picket @ 118"" instead of individual pieces with specific lengths. Sonnet does this. Opus doesn't (when prompted correctly).
2. **Progressive gritting** — recommending 60/80/120 grit progression for outdoor painted steel. Wrong. 36-grit flap disc only.
3. **MIG outdoors** — recommending MIG/TIG for field welding. Always Stick (SMAW, E7018).
4. **Duplicate materials** — AI outputs posts + post-processor adds posts = double count. Post-processor must check before adding.
5. **Wrong gate panel length** — AI calculating its own gate length instead of using `opening × 1.5` from calculator.
6. **Overhead beam × 2** — one beam spans carriage posts, not two.
7. **"Grind welds smooth"** — never for outdoor. Cleanup only.
8. **Generic profile keys** — "channel" instead of `punched_channel_1.5x0.5_fits_0.625`.
9. **Concrete as linear stock** — "1 × 20' concrete footing" in stock order. Concrete isn't sold by the foot.
10. **Height parsing errors** — reading fence height as 15' when description says 10'. Must parse carefully.

---

## 10. Quote Number Reference

The canonical correct quote is **CS-2026-0039**: material subtotal $2,973.77, total ~$13,316.82 at 15% markup. Generated by Claude Opus 4.6. Individual cut list pieces, correct heights, correct quantities.

### Full Progression
| Quote | Total | AI | Key Milestone |
|---|---|---|---|
| CS-2026-0025 | $8,222 | Gemini | Gate only, $0 hardware |
| CS-2026-0026 | $11,949 | Gemini | P19: hardware working |
| CS-2026-0027 | $12,423 | Gemini | P20: fence in AI (not calc) |
| CS-2026-0028 | $14,218 | Gemini | P21: top-mount, carriages |
| CS-2026-0029 | $13,427 | Gemini | P22: labor calibrated |
| CS-2026-0030 | $17,640 | Gemini | P23: post-processing adds fence |
| CS-2026-0031 | $19,275 | Gemini | Wrong pickets (1x1 tube) |
| CS-2026-0034 | $15,083 | Gemini | P24+25: consumables, but regressions |
| CS-2026-0035 | $17,180 | **Claude** | P26: first Claude quote, clean |
| CS-2026-0036 | — | Claude | Critical bugs: duplicate posts/beams |
| CS-2026-0037 | — | Claude | Aggregated cut list (Sonnet) |
| CS-2026-0038 | — | Claude | Double-count bug |
| **CS-2026-0039** | **$13,316.82** | **Opus** | **✅ FIRST CORRECT QUOTE** |
