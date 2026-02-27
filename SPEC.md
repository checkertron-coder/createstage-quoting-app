# CreateStage Quoting App — Architecture Spec v2
*Built from real fabrication knowledge — Burton + Checker, Feb 2026*

## The Problem With v1
Single prompt → single AI response. AI is doing geometry, material takeoff, labor estimation, 
and pricing all at once. It's mediocre at all of them because it's doing too much.

## The Right Architecture
A pipeline where each stage does ONE job:

1. **PARSE** — extract structured parameters from job description
2. **CLARIFY** — ask only for genuinely missing info
3. **CALCULATE** — deterministic Python math (geometry, weights, cut lists)
4. **ESTIMATE** — AI applies judgment only where judgment is needed (labor hours)
5. **PRICE** — apply rates, markup, margin to solved line items
6. **REVIEW** — flag anything that looks off

AI only touches stages 2 and 4. Everything else is code.

---

## Stage 1 — Job Types
*What are the categories of work CreateStage does?*

[ TO BE FILLED IN ]

## Stage 2 — Required Inputs Per Job Type
*For each job type, what information is always needed to generate an accurate quote?*

[ TO BE FILLED IN ]

## Stage 3 — Geometry Engine
*What math functions need to exist in code?*

### Known patterns:
- Square/rectangular frame: inside clear dimension, miter cut lengths
- Nested pyramid flat bar: layer lengths, depths, piece counts
- [ MORE TO BE ADDED ]

## Stage 4 — Labor Logic
*How does labor actually work? What drives hours?*

### Known rules:
- Physical size drives hours more than complexity
- Vinegar bath only for aesthetic/clear coat finishes
- [ MORE TO BE ADDED ]

## Stage 5 — Finish Types + Their Process Steps
*What are all the finish options and what steps does each require?*

### Known finishes:
- Raw steel (no finish)
- Clear coat — polish to 320-400 grit, apply clear coat, flip/cure
- Powder coat — outsourced, $2.50-5.00/sqft
- Paint
- Galvanized
- [ MORE TO BE ADDED ]

## Stage 6 — Cut List Rules
*When does a piece get mitered vs square cut?*

### Known rules:
- Decorative/furniture/architectural frames → 45° miter
- Structural/hidden connections → square cut
- [ MORE TO BE ADDED ]

---

## Questions To Answer In This Spec Session

1. What are all the job types you regularly quote?
2. For each type — what are the MUST-HAVE inputs before you can even start estimating?
3. What geometry calculations come up over and over?
4. What are the labor rules of thumb you actually use in your head?
5. What finish types do you offer and what does each process look like?
6. What are the most common mistakes an estimator makes on each job type?

---
*This doc drives the v2 rebuild. Every answer Burton gives goes here.*
