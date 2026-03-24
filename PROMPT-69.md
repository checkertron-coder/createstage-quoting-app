# PROMPT-69 — Session Persistence: Survive Navigation During Active Quote

## 1. PROBLEM STATEMENT

When a user is mid-quote — questions have been asked, some answers given — and they navigate away to check their past quotes (or anything else), the active session is lost entirely. Returning to the quote page shows a blank describe step. All prior answers are gone. The user must start over from scratch, which burns tokens, wastes time, and will make a paying customer furious.

The session data is NOT lost. It exists in the database with a `session_id`. The frontend simply has no mechanism to detect, store, or restore an in-progress session. This is purely a frontend persistence gap.

---

## 2. ACCEPTANCE CRITERIA

- **AC-1: Session survives navigation.** A user mid-clarify (questions answered, more remaining) can navigate away, return to the quote page, and land directly on the clarify step — all previously answered fields intact, remaining questions visible, progress bar accurate.

- **AC-2: Session survives page refresh.** Same as AC-1 but triggered by F5 / browser refresh.

- **AC-3: Processing state restored.** If the user navigates away while Opus is still processing intake (spinner showing), they return to a "Still analyzing your job..." message that continues polling until the session goes active, then renders the clarify step.

- **AC-4: Completed quotes not affected.** Sessions that have already been priced (status: completed, `quote_id` exists) continue to restore to the results step exactly as they do today via `cq_last_quote_id`. No regression.

- **AC-5: Stale sessions handled gracefully.** If a saved `session_id` returns a 404, 403, or error from the backend, silently clear it and show the fresh describe step. No error shown to user.

- **AC-6: Starting a new quote clears saved session.** Clicking "New Quote" or submitting a new job description clears the stored `session_id` from localStorage and starts fresh.

- **AC-7: All existing tests pass.** No regressions to the 1239 passing tests.

---

## 3. CONSTRAINT ARCHITECTURE

### In Scope
- `frontend/js/quote-flow.js` — where session state lives and navigation/restore logic goes
- `frontend/js/api.js` — if a helper is needed to call the status endpoint
- localStorage key naming: use `cq_active_session_id` (distinct from `cq_last_quote_id` which tracks completed quotes)

### Off Limits
- `backend/` — do not modify. The `/session/{id}/status` endpoint already returns everything needed (status, job_type, stage, extracted_fields, next_questions, completion, answered_fields). No backend changes required.
- Do not change any existing `cq_last_quote_id` logic — that handles completed quote restoration and must not regress.
- Do not add new backend routes or database columns.

### Guard Rails
- The restore attempt must be non-blocking — if it fails for any reason, fall through silently to the describe step.
- Do not restore if the session status is `"error"` — clear it and show describe.
- Do not restore if the session status is `"completed"` — `cq_last_quote_id` already handles that path.
- The restore check must run before `_tryRestoreLastQuote` or be merged into a single init flow that checks active session first, completed quote second.

---

## 4. DECOMPOSITION

### Step 1: Save session_id to localStorage when session starts
In `_startSession`, after `this.sessionId = data.session_id`, persist it:
`localStorage.setItem('cq_active_session_id', data.session_id)`

Also save it when the async polling path resolves (after `_pollForIntakeResult` succeeds).

Clear it in any "new quote" or reset path — wherever `this.sessionId = null` is set or `cq_last_quote_id` is removed.

### Step 2: Restore in-progress session on init
In `_tryRestoreLastQuote` (or a new `_tryRestoreActiveSession` called first), check for `cq_active_session_id` in localStorage. If found:

- Call `API.getSessionStatus(savedSessionId)`
- On error or non-2xx: clear the key, fall through
- On `status: "error"`: clear the key, fall through
- On `status: "completed"`: clear the key, let existing `cq_last_quote_id` logic handle it
- On `status: "processing"`: set `this.sessionId`, call `_pollForIntakeResult(savedSessionId)` — user sees "Still analyzing..." and it continues from where it left off
- On `status: "active"`: set `this.sessionId`, set `this._currentJobType`, call `_handleIntakeResult(statusData)` — user lands directly on the clarify step with prior answers shown

### Step 3: Show answered fields on restore
When restoring to clarify step from a saved session, the status endpoint returns `answered_fields` and `next_questions`. The clarify render must use these to pre-populate answered state and show only remaining questions.

Verify that `_renderClarifyStep` uses the data shape returned by the status endpoint (`extracted_fields`, `next_questions`, `completion`) — if the shape differs from what `_startSession` provides, normalize it before passing to the render function.

### Step 4: Write restore tests
Add tests covering:
- Restore when session is active → clarify step rendered
- Restore when session is processing → polling resumes
- Restore when session returns 404 → describe step shown, localStorage cleared
- Restore when session is completed → falls through to existing quote restore path

---

## 5. EVALUATION DESIGN

**Test A — Mid-clarify navigation:**
1. Start a new quote, enter a job description, wait for Opus to return questions
2. Answer 1-2 questions but do NOT submit
3. Open a new browser tab, go to the quotes list, come back to the quote tab
4. Expected: clarify step is visible, the questions you answered are marked answered, remaining questions are shown, progress bar reflects your progress

**Test B — Page refresh during clarify:**
1. Same as Test A steps 1-2
2. Hit F5
3. Expected: same as Test A step 4

**Test C — Navigate away during processing:**
1. Start a new quote, submit description
2. Immediately navigate to quotes list before questions appear (within the first 2 seconds)
3. Return to the quote page
4. Expected: "Still analyzing your job..." spinner, followed by questions appearing when Opus finishes

**Test D — New quote clears saved session:**
1. Complete Test A
2. Click "New Quote"
3. Refresh the page
4. Expected: fresh describe step, not the old session

**Test E — Stale session:**
1. Manually set `cq_active_session_id` in localStorage to a fake/expired UUID
2. Reload the page
3. Expected: fresh describe step, `cq_active_session_id` is cleared from localStorage

**Automated tests:** Run `pytest tests/ -q` — must show 1239+ passing, 0 failures.
