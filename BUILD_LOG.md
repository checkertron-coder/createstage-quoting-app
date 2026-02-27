# BUILD_LOG.md — CreateStage Quoting App

## MANDATORY: Read this at the start of every Claude Code session. Write to it at the end.

---

## Current Status: v1 deployed, v2 spec complete, v2 build not started

**Live URL:** createstage-quoting-app-production.up.railway.app
**Repo:** github.com/checkertron-coder/createstage-quoting-app
**Model:** Gemini 2.0 Flash (upgrade to Gemini 3.1 Pro or Opus 4.6 for v2)
**DB:** PostgreSQL on Railway (online, connected)

---

## v2 Spec
Full spec is at: `~/workspace/QUOTING-APP-SPEC.md`
Read it before starting any session. It is the ground truth.

**Open decisions that BLOCK Session 1:**
- O1: Bayern Software name and API access
- O2: Scope — all 12 job types or start with 5?
- O3: Multi-user auth in v2 or single-user?
- O4: Photo storage (Railway volume / Cloudflare R2 / pass-through only)
- O5: PDF branding (CreateStage-specific or white-labeled from day 1)
- O6: Additional pricing data from Burton before build starts?

---

## Session Log

### [NOT YET STARTED]
Sessions begin once open decisions are resolved.

---

## Architectural Decisions (append here when made)

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-02-27 | 6-stage pipeline (Intake→Clarify→Calculate→Estimate→Price→Output) | AI only in stages 2+4; everything else deterministic |
| 2026-02-27 | Vanilla HTML/CSS/JS frontend, FastAPI backend | Keep it simple, no framework overhead |
| 2026-02-27 | Bayern Software stubbed as interface, not implemented | Phase 3 — but architecture must accommodate |
| 2026-02-27 | Finishing is ALWAYS a separate line item | Most underquoted stage, must be visible |

