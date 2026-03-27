# PROMPT 74 — Brain Sync Protocol: Pull-First Across All Agents
*Run in Claude Code on M4 — working directory: createstage-quoting-app*
*Written by Checker — 2026-03-27*

---

## 1. PROBLEM STATEMENT

Checker pushes documentation updates (CLAUDE.md, PROMPT-*.md, brain decisions) to GitHub. But CC reads local files only. If the M4 hasn't pulled before a CC session starts, CC operates on stale instructions — missing rule updates, missing prompt context, missing Checker's notes. This creates communication gaps between Checker and CC that Burton has to manually bridge.

The same problem exists in reverse: when CC writes session summaries to ~/brain and pushes to GitHub, Checker's heartbeat pulls them — but only because Checker explicitly pulls. Neither agent has a guaranteed pull-first habit baked into their session start.

This is a coordination problem, not a code problem. The fix is a lightweight sync protocol that runs automatically before any agent reads its context files.

---

## 2. ACCEPTANCE CRITERIA

1. At the start of every CC session, both repos are current with GitHub before CC reads CLAUDE.md or any brain files
2. A single shell script (`bin/brain-sync.sh`) handles the pull for both repos — Burton can run it manually or it can be referenced in session start instructions
3. CLAUDE.md has a "Session Start Protocol" section at the top that makes `brain-sync.sh` step zero — before reading anything else
4. CC's `~/brain/agents/cc-createquote/AGENT.md` is updated to include pull-first as the mandatory first step
5. If either pull fails (offline, conflict), the script reports the failure clearly and CC proceeds with a warning rather than silently using stale data

---

## 3. CONSTRAINT ARCHITECTURE

**In scope:**
- `bin/brain-sync.sh` — new shell script, lives in repo root's bin/ folder
- `CLAUDE.md` — add Session Start Protocol section (top of file, before Section 0)
- `~/brain/agents/cc-createquote/AGENT.md` — update Reads From + session start steps

**Off limits:**
- No changes to any `.py`, `.js`, or app logic files
- Do not touch Railway config, Alembic migrations, or any deployment files
- Do not change CLAUDE.md's existing content — only prepend the new section

**Paths:**
- Quoting app repo: `/Users/CTron/Desktop/createstage-quoting-app/` (M4 local path)
- Brain vault: `~/brain/`
- Brain remote: `https://github.com/checkertron-coder/checker-brain`
- App remote: `https://github.com/checkertron-coder/createstage-quoting-app`

---

## 4. DECOMPOSITION

### Step 1: Create `bin/brain-sync.sh`
A shell script that:
- `git pull origin master` on `~/brain/`
- `git pull origin main` on the quoting app repo
- Reports success or failure for each pull with a timestamp
- Exits cleanly either way — a pull failure should warn, not block

### Step 2: Update CLAUDE.md — Session Start Protocol
Add a new section at the very top of CLAUDE.md (before the existing Section 0) called **"Session Start Protocol"** with:
- Step 1: Run `bin/brain-sync.sh` (or manually: `cd ~/brain && git pull origin master`)
- Step 2: Read CLAUDE.md (this file) fresh after the pull
- Step 3: Read the 3 most recent files in `~/brain/agents/cc-createquote/sessions/`
- Step 4: Begin work

This section should be short — 6 lines max. It's a checklist, not a tutorial.

### Step 3: Update `~/brain/agents/cc-createquote/AGENT.md`
Add a "Session Start" section at the top with the same pull-first steps. When CC checks its own AGENT.md, this is the first thing it reads.

### Step 4: Commit everything
- Commit `bin/brain-sync.sh` and updated `CLAUDE.md` to the quoting app repo → push to GitHub
- Commit updated `AGENT.md` to `~/brain/` → push to GitHub
- Both pushes must succeed before declaring done

---

## 5. EVALUATION DESIGN

**Test 1: Script runs clean**
- Run `bin/brain-sync.sh` from the M4
- Expected: both repos pull successfully, output shows timestamp + "up to date" or commit hash for each
- Expected: script exits 0

**Test 2: Script handles offline gracefully**
- Disconnect from network, run `bin/brain-sync.sh`
- Expected: clear error message per repo ("pull failed — proceeding with local"), script still exits without hanging

**Test 3: CLAUDE.md session start is visible**
- Open CLAUDE.md
- Expected: "Session Start Protocol" is the very first section — visible before scrolling

**Test 4: Brain in sync**
- After running the script, check `git log --oneline -3` on both repos
- Expected: both match their GitHub remotes

---

## NOTES FOR CC

This prompt only touches documentation and shell scripts — no app logic. The goal is eliminating the communication gap between Checker (on the Mac Mini) and CC (on the M4) caused by stale local files.

After completing this prompt, CC should write a session summary to `~/brain/agents/cc-createquote/sessions/` and push it. Checker will pull it on the next heartbeat.
