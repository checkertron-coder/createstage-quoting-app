# PROMPT 16 — Frontend: Full Quote View + Hourly Rate Input + Missing Spec Prompts

## CONTEXT — READ FIRST

The quoting app backend is generating good data: materials, cut list, detailed cut list, build sequence, labor, consumables, hardware, finishing, validation warnings. But the frontend only renders materials, hardware, consumables, labor, finishing, and totals. The cut list, detailed cut list, build sequence, and validation warnings are ONLY visible in the downloaded PDF. Users can't see 60% of the quote on screen.

Additionally, the hourly rate is stored in the user profile (rate_inshop, rate_onsite) but there's no way to set or change it in the quote flow. It defaults to $125 silently.

## INTEGRATION RULES (from CLAUDE.md)
Remember: building a feature is not done until it's in the hot path. After adding any render function, verify it's actually called in `_renderResults()`. After adding any input field, verify it's wired to the API call.

## CHANGES NEEDED

### 1. Render the full quote on screen (frontend/js/quote-flow.js)

In `_renderResults()`, add these sections BETWEEN the existing Materials section and the Labor section:

**a. Cut List Summary** — show the consolidated cut list (material, total length, qty)

**b. Detailed Cut List** — show every piece: description, profile, length, qty, cut type, notes. Use a responsive table or card layout. This is critical — fabricators need to see every cut.

**c. Build Sequence / Fabrication Steps** — render each step as a card or numbered list:
- Step number + title
- Full description
- Tools
- Duration (minutes → show as "X hr Y min" if over 60 min)
- Any validation flags (⚠️ REVIEW notes) should be highlighted in yellow/orange

**d. Validation Warnings** — if `pq.validation_warnings` exists and has items, render a prominent warning box at the TOP of the results (before materials) with each warning listed. Use red/orange styling. This tells the user "review these items before sending this quote."

### 2. Hourly Rate Input

**a. Add rate input to the quote flow** — In the FIRST step of the quote flow (before or alongside job description), add:
```
Shop Rate: $[___]/hr    (default: pull from user profile, or $125)
```

This should be a simple number input that:
- Pre-fills from `current_user.rate_inshop` (already in the profile API response)
- Can be changed per-quote
- Gets passed to the pricing API call
- Updates the labor calculations in real-time when changed on the results screen

**b. On the results screen**, make the rate editable:
- Show the rate next to the Labor header
- When changed, recalculate all labor line items and the total immediately (client-side math — hours × new rate)
- This is a live calculator, not a page reload

### 3. Ask for Missing Specs

In the question tree flow, if the user's job description mentions materials but doesn't specify:
- **Wall thickness / gauge** for tubing (e.g., "1 inch square tube" without "14ga" or "11ga")
- **Material type** when ambiguous (mild steel vs stainless vs aluminum)

...add a follow-up question before generating the quote:
```
"You mentioned 1" square tube — what wall thickness?
○ 14 gauge (0.075") — most common for furniture
○ 11 gauge (0.120") — heavier duty
○ 3/16" wall — structural
○ Other: [___]"
```

Check if this can be added to the question tree JSON files in `backend/question_trees/data/`. If the question tree system already supports conditional questions based on detected materials, use that. If not, add a material clarification step after Stage 1 (job type detection) and before Stage 2 (question tree).

### 4. Material Ordering in Full Sticks

Materials come in standard lengths (typically 20', 24', or supplier-specific). The quote currently shows "17.5 ft needed" but you actually buy a full 20' stick.

In the materials section of the results:
- Show: "1x1 14ga sq tube — 17.5 ft needed → 1 stick @ 20' ($X.XX) — 2.5 ft remaining"
- Standard stock lengths should be in `backend/knowledge/materials.py` — check if they're there. If not, add them.

### 5. Don't Break Anything

- All existing 384+ tests must pass
- The quote generation pipeline (backend) should NOT be modified except for:
  - Accepting hourly rate as a parameter in the pricing API
  - Adding material clarification questions to question trees
- Focus changes on frontend rendering + UX flow

### COMMIT

```
git add -A && git commit -m "Frontend: full quote view with cut list, build sequence, validation warnings, live rate calculator

- Render cut list, detailed cut list, and build sequence on screen (not just PDF)
- Validation warnings shown prominently at top of results
- Hourly rate input: editable per-quote, live recalculation
- Material clarification: ask wall thickness when not specified
- Material ordering: show full stick quantities with remaining stock" && git push
```
