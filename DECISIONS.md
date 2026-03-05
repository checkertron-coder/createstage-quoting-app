# DECISIONS.md — Architectural Decision Log

**Purpose:** Why we built things the way we did. Prevents future AI sessions from re-litigating settled decisions. Tool-agnostic — any AI that reads this repo inherits the reasoning.

**Last updated:** Prompt 31 (March 5, 2026)

---

## D-001: Claude Opus over Sonnet for Generation (P28-P30)

**Decision:** Use `claude-opus-4-6` as the generation model (`CLAUDE_FAST_MODEL` on Railway).

**Context:** Sonnet 4.6 produced aggregated cut lists ("25 × picket @ 118"") and wrong quantities. It also kept reverting domain rules (grinding, beam duplication, HSS profiles). Opus generates individual pieces with correct counts, respects domain constraints, and follows the fab sequence rules.

**Constraint:** Review model must be ≥ generation model. If Opus generates, Opus reviews (or skip review). Sonnet reviewing Opus output is backwards.

**Cost:** Opus costs more per call. Acceptable tradeoff — a wrong quote costs more than API fees.

---

## D-002: Gemini Fully Replaced by Claude (P26-P27)

**Decision:** Remove all Gemini code. Claude is the sole AI provider for cut list generation, fab sequences, and labor estimation.

**Context:** Gemini kept reverting domain constraints across runs:
- Recommended "grind welds smooth" after being told not to
- Duplicated overhead beams
- Used wrong HSS profiles
- Generated bloated/repetitive fab sequences
- Couldn't maintain consistent picket material between gate and fence sections

Claude (Opus) follows constraints reliably. `gemini_client.py` deleted, `ai_client.py` router deleted. All imports go directly to `claude_client.py`.

---

## D-003: Post-Processor as Safety Net, Not Calculator (P28)

**Decision:** `_post_process_ai_result()` in `cantilever_gate.py` is a lightweight safety net that validates and supplements AI output. It is NOT a parallel calculation engine.

**Context:** The post-processor was becoming a second calculator — recalculating quantities, adding materials that duplicated AI output, and overriding AI decisions. This caused:
- Duplicate gate posts (AI pipe_4_sch40 × 3 + post-processor sq_tube_4x4_11ga × 3 = 6 posts)
- Duplicate overhead beams
- Conflicting material profiles for the same component

**Rule:** Post-processor checks:
1. **Existence** — are critical components present? (posts, beam, pickets)
2. **Sanity** — are quantities within reasonable bounds?
3. **Supplement** — add ONLY items the AI consistently misses (hardware, consumables)

It must NEVER recalculate quantities or override AI-generated materials.

---

## D-004: Calculator Enforces Hard Rules, AI Gets Dimensions (P24)

**Decision:** Hard geometric rules (gate panel length = opening × 1.5, post height = above grade + 2" + 42") are calculated deterministically and passed to the AI prompt. AI does NOT recalculate these.

**Context:** AI kept inventing its own gate lengths (324"/27' instead of 216"/18'). The calculator knows the formula. The AI just needs to be told "the gate panel is 216 inches long, use this for your cut list."

**Implementation:** `_build_field_context()` in `ai_cut_list.py` injects computed dimensions into the prompt as hard constraints.

---

## D-005: AI-First Path with Post-Processing (P23)

**Decision:** When a job description exists (which is always — Burton always types one), the calculator takes the AI path: `_try_ai_cut_list()` → `_build_from_ai_cuts()` → `_post_process_ai_result()` → return.

**Context:** The rule-based path (template math) was the original design. But AI cut lists from descriptions produce far better results — they capture the actual job scope, not a generic template. The rule-based path only executes when there's no description (rare) or when AI fails.

**Architecture:**
```
AI path:    description → AI prompt → cut list → post-process → return
Rule path:  fields only → template math → return (fallback only)
```

---

## D-006: Two PDF Versions — Shop Copy vs Client Copy (P31)

**Decision:** Single endpoint with `mode` query param (`shop` or `client`). Two download buttons in frontend.

**Context:** The shop needs full detail (cut list, fab sequence, labor breakdown, hourly rates). The client should see a professional summary (scope of work, consolidated materials, total price, warranty, payment terms). Sending the shop copy to clients exposes internal rates and makes the quote look like a spreadsheet, not a proposal.

**Shop Copy shows:** Everything — cut list, fab sequence, labor hours per process, hourly rates, stock order, consumable detail.

**Client Copy shows:** Scope summary (AI-generated), material categories (not individual cuts), total material cost, total labor cost (no hourly rate), hardware, markup, grand total, exclusions, payment terms.

---

## D-007: Scope Summary Cached in Session (P31)

**Decision:** AI-generated scope-of-work text is stored in `session.params_json["_scope_summary"]` after first generation.

**Context:** Generating scope text requires an AI call. We don't want to re-generate it every time someone downloads the client PDF. Cache it on first generation, reuse on subsequent downloads.

---

## D-008: Labor Rates Controlled via User Profile (P22)

**Decision:** Shop rate ($125/hr in-shop, $145/hr field) comes from the user's profile settings. NOT hardcoded in calculators.

**Context:** Every fabricator has different rates. The app is multi-tenant. Hardcoding rates means every shop gets the same price, which defeats the purpose.

**Implementation:** `rate_inshop` and `rate_onsite` fields on the User model. Labor processes reference these when calculating cost.

---

## D-009: TEACH Don't TELL for AI Constraints

**Decision:** Give the AI reasoning principles and domain knowledge, not brittle lookup rules.

**Context:** Early prompts tried to constrain Gemini with exact rules ("never output more than 1 overhead beam"). Gemini would follow the rule for one run, then ignore it. Teaching the AI *why* (one beam spans two carriage posts — you don't need two beams because the carriages are on the same track) produces more reliable behavior.

**Application:** KNOWLEDGE.md explains the reasoning behind every constraint. The AI prompt references this knowledge. When the AI understands *why* a rule exists, it follows it more consistently.

---

## D-010: Pre-Punched Channel for Mid-Rails (P23)

**Decision:** Use pre-punched U-channel as the standard mid-rail material for fences.

**Context:** Traditional approach: drill holes in flat bar or weld individual pickets to rails. Pre-punched channel is industry standard — pickets slide through pre-spaced holes. Dramatically faster assembly (~35% labor reduction for fit-and-tack). Self-spacing means fewer measurement errors.

**Profile keys:** `punched_channel_1x0.5_fits_0.5`, `punched_channel_1.5x0.5_fits_0.625`, `punched_channel_2x1_fits_0.75`

---

## D-011: Osorio + 10% Buffer for Material Pricing (P24)

**Decision:** Use Osorio Metals Supply invoices as baseline pricing, add 10% buffer for price fluctuations.

**Context:** Osorio is 25-30% cheaper than Wexler on common tube stock. We have actual invoices with real per-foot prices (see KNOWLEDGE.md §4). The 10% buffer accounts for price increases between invoice dates and actual purchase.

---

## D-012: Prompt Specs as Repo Artifacts (P18+)

**Decision:** Every Claude Code prompt is saved as `PROMPT-{N}-{DESCRIPTION}.md` at the repo root and committed to `main`.

**Context:** Prompts are the development history. They document what was wrong, what the fix is, why we chose that approach, and how to verify it worked. They're more valuable than commit messages because they contain the full reasoning chain.

**Workflow:** Checker (OpenClaw agent) writes the prompt → commits to `main` → Burton reviews via GitHub raw link → Burton runs the prompt in Claude Code on the M4.

---

## D-013: Model-Agnostic Memory via Repo Files

**Decision:** Domain knowledge lives in repo-root markdown files (`KNOWLEDGE.md`, `DECISIONS.md`, `CLAUDE.md`) that any AI tool can read.

**Context:** We use multiple AI tools (OpenClaw for diagnosis, Claude Code for implementation, potentially Codex/Cursor in future). Knowledge that lives in only one tool's memory is lost when switching tools. Knowledge in the repo travels with the code.

**Files:**
- `CLAUDE.md` — project architecture, file map, data contracts, integration rules
- `KNOWLEDGE.md` — fabrication domain knowledge, supplier pricing, labor calibration
- `DECISIONS.md` — this file; why we built things this way
- `PROMPT-*.md` — development history with full reasoning chains
