from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

from .database import engine, Base
from .routers import quotes, customers, materials, process_rates, ai_quote, auth, quote_session, pdf, bid_parser, photos

logger = logging.getLogger("createstage")

# Create tables (handles new tables but won't add columns to existing ones)
Base.metadata.create_all(bind=engine)


def _run_migrations():
    """Run pending Alembic migrations on startup.

    Handles production databases that were created by Base.metadata.create_all()
    before Alembic was introduced. If alembic_version table doesn't exist but
    application tables do, stamps the base migration as applied first.
    """
    try:
        from alembic.config import Config
        from alembic import command
        from sqlalchemy import inspect

        alembic_ini = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        if not os.path.exists(alembic_ini):
            logger.info("alembic.ini not found, skipping migrations")
            return

        alembic_cfg = Config(alembic_ini)

        # Override sqlalchemy.url from environment if DATABASE_URL is set
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            alembic_cfg.set_main_option("sqlalchemy.url", database_url)

        # Check if alembic_version table exists
        insp = inspect(engine)
        has_alembic = "alembic_version" in insp.get_table_names()
        has_quotes = "quotes" in insp.get_table_names()

        if not has_alembic and has_quotes:
            # Database was created by create_all() before Alembic — stamp base migration
            logger.info("Stamping base migration 82694c65cf42 (tables already exist)")
            command.stamp(alembic_cfg, "82694c65cf42")

        # Run any pending migrations
        logger.info("Running pending Alembic migrations...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations complete")

    except Exception as e:
        # Never let migration errors prevent app startup
        logger.warning(f"Alembic migration warning: {e}")

app = FastAPI(
    title="CreateStage Quoting App",
    description="Metal fabrication quoting tool for CreateStage Fabrication",
    version="2.0.0"
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
app.include_router(process_rates.router, prefix="/api")
app.include_router(ai_quote.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(quote_session.router, prefix="/api")
app.include_router(pdf.router, prefix="/api")
app.include_router(bid_parser.router, prefix="/api")
app.include_router(photos.router, prefix="/api")

# Serve uploaded photos (local fallback when R2 not configured)
uploads_path = os.path.join(os.path.dirname(__file__), "..", "uploads")
if os.path.exists(uploads_path):
    app.mount("/uploads", StaticFiles(directory=uploads_path), name="uploads")

# Serve frontend static files
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_path):
    css_path = os.path.join(frontend_path, "css")
    js_path = os.path.join(frontend_path, "js")

    if os.path.exists(css_path):
        app.mount("/css", StaticFiles(directory=css_path), name="css")
    if os.path.exists(js_path):
        app.mount("/js", StaticFiles(directory=js_path), name="js")

    # Legacy /static mount for any remaining references
    static_path = os.path.join(frontend_path, "static")
    if os.path.exists(static_path):
        app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/health")
def health():
    return {"status": "ok", "app": "createstage-quoting-app"}


@app.on_event("startup")
def auto_migrate():
    """Run pending Alembic migrations on startup."""
    _run_migrations()


@app.on_event("startup")
def auto_seed():
    """Auto-seed process rates and material prices on first run."""
    from .database import SessionLocal
    from .routers.process_rates import DEFAULT_RATES
    from .routers.materials import DEFAULT_PRICES
    from . import models
    db = SessionLocal()
    try:
        # Seed process rates
        for proc_type, data in DEFAULT_RATES.items():
            existing = db.query(models.ProcessRate).filter(
                models.ProcessRate.process_type == proc_type
            ).first()
            if not existing:
                db.add(models.ProcessRate(process_type=proc_type, **data))
        # Seed material prices
        for mat_type, price_data in DEFAULT_PRICES.items():
            existing = db.query(models.MaterialPrice).filter(
                models.MaterialPrice.material_type == mat_type
            ).first()
            if not existing:
                db.add(models.MaterialPrice(material_type=mat_type, **price_data))
        db.commit()
    finally:
        db.close()
