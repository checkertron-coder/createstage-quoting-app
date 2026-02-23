from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from .database import engine, Base
from .routers import quotes, customers, materials

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CreateStage Quoting App",
    description="Metal fabrication quoting tool for CreateStage Fabrication",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(quotes.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(materials.router, prefix="/api")

# Serve frontend
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/health")
def health():
    return {"status": "ok", "app": "createstage-quoting-app"}
