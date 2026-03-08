# Prompt 36B: Add Gauge/Thickness to Missing Question Trees (Simple Backup)

## Problem Statement
16 of 25 question trees are missing a material gauge/thickness question. When a customer asks for an aluminum LED sign, the app never asks what gauge aluminum — Opus has to guess.

## Acceptance Criteria
All 16 trees listed below have a `material_gauge` or equivalent question added. The question should branch off the material choice when one exists, or be a standalone required question. The options should be appropriate for each job type (not every job needs the same gauge options).

## Trees to Update
1. balcony_railing.json
2. bollard.json
3. complete_stair.json
4. exhaust_custom.json
5. furniture_other.json
6. led_sign_custom.json
7. ornamental_fence.json
8. product_firetable.json
9. repair_decorative.json
10. repair_structural.json
11. roll_cage.json
12. sign_frame.json
13. spiral_stair.json
14. structural_frame.json
15. trailer_fab.json
16. window_security_grate.json

## Constraint Architecture
- ONLY modify the JSON files listed above in `backend/question_trees/data/`
- Follow the existing pattern from `cantilever_gate.json` field `frame_gauge` as a template
- Gauge options should be appropriate to each job type (e.g., exhaust uses different gauges than structural frame)
- If a tree already has a `material` choice question, make gauge `depends_on` that material question
- Add gauge to `required_fields` array in each tree
- DO NOT touch any Python code

## Evaluation
- Run the LED sign flow — gauge question should now appear
- Run a bollard flow — gauge question should appear
- Run a cantilever gate flow — should be unchanged (already has gauge)
