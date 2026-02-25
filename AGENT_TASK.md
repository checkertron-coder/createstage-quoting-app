# Agent Task: Redesign as Conversation Interface

## Context
CreateStage Fabrication is a Chicago-based metal fab shop (welding, CNC, steel, LEDs, custom builds).
This app currently works as a form-based quoting calculator. We need to evolve it into something groundbreaking.

## The Vision
Nobody in the fabrication quoting space has built a **conversation-first interface**. Every competitor (SecturaFAB, Paperless Parts, Costimator) uses forms, dropdowns, and spreadsheets. We're going to do something different.

**Core concept:** A fabricator describes their job in plain language — the way they'd explain it to a welder — and the AI parses it into a structured, accurate quote. Like this:

> "I need a 6x8 steel gate, 2 inch square tube frame, expanded metal infill, hinges and latch, powder coat black"

→ AI breaks that down into materials, labor hours, processes, and spits out a professional quote.

## What to Build

### Phase 1 — Conversation UI (do this now)
Redesign `frontend/index.html` as a **chat interface**:
- Clean, dark theme (think terminal meets Figma)
- Left panel: conversation thread (user input + AI responses)
- Right panel: live quote building in real-time as AI parses the job
- Bottom: text input with "Describe your job..." placeholder
- When user submits description → calls `/api/estimate` with the text
- AI response streams back the quote breakdown with line items
- "Generate PDF Quote" button appears when quote is complete

### Phase 2 — Backend Intelligence (after UI)
Update `backend/main.py` to:
- Accept natural language job descriptions via POST `/api/estimate`
- Use Gemini API to parse into structured quote components
- Return: materials list, labor hours, process breakdown, total cost
- Support follow-up questions ("make it stainless instead" → updates quote)

## Design Direction
- **Dark theme** — fabricators work in shops, dark UIs feel right
- **Fast and direct** — no loading spinners, no onboarding flow
- **Mobile-friendly** — quote from the shop floor
- **Professional output** — the PDF quote should look like it came from a real company

## Tech Stack
- Frontend: Vanilla HTML/CSS/JS (keep it simple, no framework bloat)
- Backend: FastAPI (Python)
- AI: Gemini API (key available as env var GEMINI_API_KEY)
- DB: PostgreSQL on Railway

## Start Here
1. Look at `frontend/index.html` — understand what exists
2. Look at `backend/main.py` — understand the current API
3. Redesign the frontend as the conversation interface described above
4. Update the backend `/api/estimate` endpoint to handle natural language input

Go build something that makes fabricators go "holy shit."
