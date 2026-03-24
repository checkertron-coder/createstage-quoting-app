# PROMPT 65C — NDA Modal: Invite Code Users Only
*Spec-engineered using Nate B. Jones' 5 Primitives*

---

## 1. PROBLEM STATEMENT

The NDA modal currently fires for ALL registrations — invite code users and public users alike. This is wrong. The NDA is a beta tester agreement. Public users signing up for the free tier have no reason to sign an NDA — they're just customers. Showing a scary legal agreement to every person who tries to sign up is bad UX and legally unnecessary.

The intended flow:
- **Beta tester (has invite code):** Enter code → NDA modal fires → agree → email confirmation → verify → access
- **Public user (no invite code):** Register → email confirmation → verify → free tier access (no NDA)

Additionally, beta testers must confirm their email AFTER agreeing to the NDA. Currently email confirmation is either not firing or firing before the NDA. The full beta tester registration sequence must be locked down end to end.

---

## 2. ACCEPTANCE CRITERIA

**Beta tester flow (invite code present):**
- User enters email + password + invite code → clicks "Create Account"
- NDA modal fires BEFORE account is created
- User must click "I Agree — Continue Registration" to proceed
- Clicking "I Do Not Agree" returns them to the landing page, no account created
- After agreeing: NDA acceptance logged to DB (email, IP, timestamp, nda_version)
- Account is created, invite code is validated and locked to this email
- Verification email is sent to the registered address
- User cannot access the app until they click the verification link
- After verification: full access granted (professional tier per invite code)

**Public user flow (no invite code):**
- User enters email + password → clicks "Create Account"
- NO NDA modal — goes straight to registration
- Verification email is sent
- User cannot access the app until they click the verification link
- After verification: free tier access

**Both flows:**
- Email verification is enforced — no auto-verify, no bypass in production
- App is healthy after deploy: `https://createquote.app/health` returns `{"status": "ok"}`

---

## 3. CONSTRAINT ARCHITECTURE

**In scope:**
- `frontend/js/auth.js` — NDA modal trigger condition: only show modal when invite code field is non-empty
- `backend/routers/auth.py` — verify email confirmation fires for BOTH paths (invite code and non-invite-code)
- `backend/email_service.py` — confirm `is_configured()` logs correctly in Railway

**Out of scope — do not touch:**
- NDA modal content or design — correct as-is
- NDA acceptance logging endpoint — correct as-is
- Invite code validation logic — correct as-is
- Calculator, quote, PDF logic
- Any test not related to registration flow

**Must not break:**
- BETA-FOUNDER account (Burton's — already registered and verified)
- Existing paid/verified users — their sessions must not be invalidated

---

## 4. DECOMPOSITION

**Chunk 1 — Frontend: gate NDA modal on invite code presence**
In `auth.js`, the NDA modal currently fires for all registrations. Change the condition: only show the NDA modal if the invite code field contains a non-empty value when the user clicks "Create Account." If no invite code is entered, skip the modal entirely and proceed directly to form submission. The invite code field check should happen at the moment of submit, not on page load.

**Chunk 2 — Backend: confirm email verification fires for invite code users**
Currently invite code users are auto-verified (email_verified = True) and issued tokens immediately — this is the existing behavior. This must change: invite code users should receive a verification email and be held at the verification gate just like public users. The only difference is the NDA agreement happens first. Remove the auto-verify + immediate token issuance for invite code users. After invite code validation and NDA acceptance logging, send verification email and return `verification_required`.

**Chunk 3 — Backend: confirm email verification fires for non-invite-code users**
This was the P65B fix. Confirm it is working — non-invite-code registrations must go through the email gate. If P65B's fix is in place and working, no change needed here. Just verify and document.

**Chunk 4 — Tests**
- Invite code registration: NDA acceptance endpoint called, verification email sent, `verification_required` returned — NO immediate token
- Non-invite-code registration: no NDA, verification email sent, `verification_required` returned
- Both: clicking verification link → access granted
- Existing BETA-FOUNDER user (already verified) → login still works

---

## 5. EVALUATION DESIGN

**Beta tester test:**
1. Open incognito → go to createquote.app → Register
2. Enter email + password + valid invite code → click "Create Account"
3. EXPECTED: NDA modal fires
4. Click "I Agree"
5. EXPECTED: "Check your email to verify your account" — NO immediate app access
6. Check email → verification link arrives
7. Click link → EXPECTED: account activated, can now log in
8. Log in → EXPECTED: full professional tier access

**Public user test:**
1. Open incognito → Register with email + password only (no invite code)
2. EXPECTED: NO NDA modal — goes straight to "Check your email"
3. Verify email → free tier access

**Existing user test:**
1. Burton logs in with info@createstage.co → EXPECTED: works normally, no disruption

---

## DEPLOYMENT — REQUIRED FINAL STEP

After all chunks complete and full test suite passes:

1. `git add -A`
2. `git commit -m "P65C: NDA modal invite-code-only + email verify for all users"`
3. `git push origin main`

Verify `https://createquote.app/health` returns `{"status": "ok"}` after Railway deploys.

---

## BRAIN SYNC — REQUIRED AFTER DEPLOY

1. `cd ~/brain && git pull origin master`
2. Write session summary to `agents/cc-createquote/sessions/2026-03-23-p65c-nda-flow.md` covering what changed and current registration flow state
3. `git add -A && git commit -m "P65C: NDA invite-only + full email verify" && git push origin master`
