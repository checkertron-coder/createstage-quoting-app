# PROMPT-61: Fix Alembic Migration Conflict

## Problem Statement

The app is crash-looping on Railway with this error on every startup:

```
FAILED: Multiple head revisions are present for given argument 'head'; 
please specify a specific target revision, '<branchname>@head' to narrow 
to a specific head, or 'heads' for all heads
```

Multiple migration files were added in quick succession (P57, P58, P59 hotfixes) and Alembic now has multiple "head" migrations with no merge revision tying them together. The app cannot start because `alembic upgrade head` fails.

## Acceptance Criteria

1. `alembic upgrade head` runs without error
2. The app starts cleanly on Railway — no crash loop
3. All existing tables and columns are preserved — no data loss
4. All existing tests pass

## Constraint Architecture

**In scope:**
- `alembic/versions/` — create a merge migration that resolves the multiple heads
- `backend/main.py` — if the migration runner uses `upgrade("head")`, change to `upgrade("heads")` as a fallback

**Off limits:**
- Do not delete or modify existing migration files
- Do not change any models or business logic
- Do not touch requirements.txt, config, or routers

## Decomposition

### Chunk 1: Identify the conflicting heads
Run `alembic heads` to list all current head revisions. There will be two or more.

### Chunk 2: Create a merge migration
Run `alembic merge heads -m "merge_migration_heads"` — this creates a new migration file that combines all heads into a single head. No schema changes, just a merge point.

### Chunk 3: Verify
Run `alembic upgrade head` — should complete without error. Run `alembic heads` — should show exactly one head.

### Chunk 4: Update main.py if needed
In `backend/main.py`, find the `_run_migrations` function. If it runs `command.upgrade(alembic_cfg, "head")`, add a fallback: try `"head"` first, if it fails with multiple heads error, run `"heads"` instead.

## Evaluation Design

### Test 1: Single head
```bash
alembic heads
```
Expected: exactly one revision listed

### Test 2: Clean upgrade
```bash
alembic upgrade head
```
Expected: completes without error

### Test 3: App starts
```bash
python3 -c "from backend.main import app; print('OK')"
```
Expected: prints OK

### Test 4: Regression
`pytest tests/ -x -q` — all existing tests pass

## Save Point

```
git add -A && git commit -m "P61: Fix Alembic multiple heads — merge migration"
```
