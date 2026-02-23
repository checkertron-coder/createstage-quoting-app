# CreateStage Quoting App

Metal fabrication quoting tool for CreateStage Fabrication.

Built and maintained by Checker 🏁 (checkertron-coder)

## Stack
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL (Railway)
- **Frontend:** Vanilla HTML/JS (no framework bloat)
- **Deploy:** Railway

## Features
- Material cost calculator (steel, aluminum, stainless, etc.)
- Labor estimation by process type
- PDF quote generation
- Customer management
- Quote history

## Local Dev
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

## Deploy
Connected to Railway — push to main to deploy.
