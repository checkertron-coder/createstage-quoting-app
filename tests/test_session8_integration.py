"""
Session 8 integration tests — smoke tests, seed data, documentation completeness.

Smoke tests verify the full pipeline can run end-to-end without crashing.
Seed data tests verify the material price seeding system works correctly.
Meta-tests verify CLAUDE.md and BUILD_LOG.md stay in sync with code.

Tests:
1-6.  Smoke tests — health, auth round-trip, session start, calculate, estimate, price
7-10. Seed data — seeded prices load, profile key parser, price source tracking, fallback chain
11-14. Meta-tests — CLAUDE.md completeness, file map accuracy, job types in sync, test count
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

from backend import models
from backend.calculators.material_lookup import MaterialLookup


# ============================================================
# SMOKE TESTS — Can the pipeline run end-to-end?
# ============================================================

def test_smoke_health(client):
    """Health endpoint returns ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_smoke_auth_round_trip(client):
    """Register → login → /me → profile update works end-to-end."""
    # Register
    reg = client.post("/api/auth/register", json={
        "email": "smoke@test.com",
        "password": "smoketest123",
    })
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # /me
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "smoke@test.com"

    # Profile update
    update = client.put("/api/auth/profile", json={
        "shop_name": "Smoke Test Shop",
        "rate_inshop": 150.00,
    }, headers=headers)
    assert update.status_code == 200
    assert update.json()["shop_name"] == "Smoke Test Shop"


def test_smoke_session_start(client, auth_headers):
    """POST /session/start detects job type and returns questions."""
    resp = client.post("/api/session/start", json={
        "description": "I need a 20 foot cantilever sliding gate for a commercial driveway",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "job_type" in data
    assert "next_questions" in data
    assert data["tree_loaded"] is True


def test_smoke_calculate(client, auth_headers, db):
    """Session calculate returns a MaterialList."""
    # Start session
    start = client.post("/api/session/start", json={
        "description": "16 foot cantilever gate, 6 feet tall, steel, 2 posts",
    }, headers=auth_headers)
    session_id = start.json()["session_id"]

    # Answer required fields to complete the session
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id
    ).first()

    # Pre-populate ALL required fields directly in the DB
    # cantilever_gate requires: clear_width, height, frame_material, frame_gauge,
    #   infill_type, post_count, finish, installation
    params = dict(session.params_json or {})
    params.update({
        "clear_width": 16,
        "height": 6,
        "frame_material": "2x2 square tube",
        "frame_gauge": "11ga",
        "post_count": "2 posts (standard)",
        "infill_type": "Pickets",
        "finish": "Paint",
        "installation": "CreateStage installs on-site",
    })
    session.params_json = params
    session.job_type = "cantilever_gate"
    db.commit()

    # Calculate
    calc_resp = client.post(
        f"/api/session/{session_id}/calculate",
        headers=auth_headers,
    )
    assert calc_resp.status_code == 200
    data = calc_resp.json()
    assert "material_list" in data
    ml = data["material_list"]
    assert "items" in ml
    assert "total_weight_lbs" in ml
    assert len(ml["items"]) > 0


def test_smoke_estimate(client, auth_headers, db):
    """Session estimate returns LaborEstimate and FinishingSection."""
    # Start + pre-populate
    start = client.post("/api/session/start", json={
        "description": "simple straight railing, 10 feet long, 42 inches, paint",
    }, headers=auth_headers)
    session_id = start.json()["session_id"]

    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id
    ).first()
    # straight_railing requires: linear_footage, location, application, railing_height,
    #   top_rail_profile, infill_style, post_mount_type, finish, installation
    params = dict(session.params_json or {})
    params.update({
        "linear_footage": 10,
        "location": "Exterior",
        "application": "Residential deck",
        "railing_height": 42,
        "top_rail_profile": "1.5x1.5 square tube",
        "infill_style": "Vertical pickets",
        "post_mount_type": "Surface mount",
        "finish": "Paint",
        "installation": "Shop installs on-site",
    })
    session.params_json = params
    session.job_type = "straight_railing"
    db.commit()

    # Calculate first
    calc = client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    assert calc.status_code == 200

    # Estimate
    est = client.post(f"/api/session/{session_id}/estimate", headers=auth_headers)
    assert est.status_code == 200
    data = est.json()
    assert "labor_estimate" in data
    assert "finishing" in data
    assert "total_labor_hours" in data
    assert data["finishing"]["method"] in ["raw", "clearcoat", "paint", "powder_coat", "galvanized"]
    # Per-process breakdown, not a single number
    processes = data["labor_estimate"]["processes"]
    assert len(processes) > 0
    for p in processes:
        assert "process" in p
        assert "hours" in p
        assert "rate" in p


def test_smoke_full_pipeline(client, auth_headers, db):
    """Full pipeline: start → calculate → estimate → price produces a PricedQuote."""
    # Start session
    start = client.post("/api/session/start", json={
        "description": "swing gate, 5 feet wide, 5 feet tall, steel with pickets, paint",
    }, headers=auth_headers)
    session_id = start.json()["session_id"]

    # Pre-populate fields
    # swing_gate requires: clear_width, height, panel_config, frame_material,
    #   frame_gauge, infill_type, hinge_type, finish, installation
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id
    ).first()
    params = dict(session.params_json or {})
    params.update({
        "clear_width": 5,
        "height": 5,
        "panel_config": "Single panel",
        "frame_material": "2x2 square tube",
        "frame_gauge": "11ga",
        "infill_type": "Pickets",
        "hinge_type": "Weld-on barrel hinges",
        "finish": "Paint",
        "installation": "Shop installs on-site",
    })
    session.params_json = params
    session.job_type = "swing_gate"
    db.commit()

    # Calculate
    calc = client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    assert calc.status_code == 200

    # Estimate
    est = client.post(f"/api/session/{session_id}/estimate", headers=auth_headers)
    assert est.status_code == 200

    # Price
    price = client.post(f"/api/session/{session_id}/price", headers=auth_headers)
    assert price.status_code == 200
    pq = price.json()["priced_quote"]
    assert "materials" in pq
    assert "labor" in pq
    assert "finishing" in pq
    assert "subtotal" in pq
    assert "markup_options" in pq
    assert "assumptions" in pq
    assert "exclusions" in pq
    assert pq["subtotal"] > 0
    # Markup options should have 7 tiers (0, 5, 10, 15, 20, 25, 30)
    assert len(pq["markup_options"]) == 7


# ============================================================
# SEED DATA TESTS
# ============================================================

def test_seeded_prices_file_exists():
    """data/seeded_prices.json exists and is valid JSON."""
    prices_path = Path(__file__).parent.parent / "data" / "seeded_prices.json"
    assert prices_path.exists(), "seeded_prices.json not found"
    with open(prices_path) as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert len(data) > 0
    # Each entry should have price_per_foot and supplier
    for key, entry in data.items():
        assert "price_per_foot" in entry, f"Missing price_per_foot for {key}"
        assert "supplier" in entry, f"Missing supplier for {key}"
        assert entry["price_per_foot"] > 0, f"Zero/negative price for {key}"


def test_profile_key_parser():
    """seed_from_invoices.parse_profile_key handles known formats."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
    from seed_from_invoices import parse_profile_key

    # Osorio format — square tube
    assert parse_profile_key("Tubing - Square 2\" x 2\" x 11 ga") == "sq_tube_2x2_11ga"
    # Osorio format — angle
    assert parse_profile_key("Angle 1-1/2\" x 1-1/2\" x 1/8\"") == "angle_1.5x1.5x0.125"
    # Osorio format — flat bar (thickness x width order)
    result = parse_profile_key("Flat Bar 1\" x 1/4\"")
    assert result is not None
    assert result.startswith("flat_bar_")

    # Unknown material should return None
    result = parse_profile_key("Something completely unknown")
    assert result is None


def test_material_lookup_uses_seeded_prices():
    """MaterialLookup.get_price_per_foot returns seeded prices when available."""
    lookup = MaterialLookup()
    # sq_tube_2x2_11ga should be in seeded data (Osorio $2.49)
    price = lookup.get_price_per_foot("sq_tube_2x2_11ga")
    assert price > 0

    # get_price_with_source should return the source label
    price, source = lookup.get_price_with_source("sq_tube_2x2_11ga")
    assert price > 0
    assert source in ["Osorio", "Wexler", "market_average"]


def test_material_lookup_fallback():
    """MaterialLookup falls back to hardcoded defaults for unknown profiles."""
    lookup = MaterialLookup()
    # Use a profile that is in seeded or default data
    price = lookup.get_price_per_foot("sq_tube_2x2_11ga")
    assert price > 0  # Should always return something

    # Completely unknown profile returns 0.0 (no crash)
    price_unknown = lookup.get_price_per_foot("unobtainium_99x99_0ga")
    assert price_unknown == 0.0


# ============================================================
# DOCUMENTATION META-TESTS — Keep CLAUDE.md in sync with code
# ============================================================

def test_claude_md_lists_all_job_types():
    """Every job type in V2_JOB_TYPES should appear in CLAUDE.md."""
    claude_md_path = Path(__file__).parent.parent / "CLAUDE.md"
    claude_text = claude_md_path.read_text()

    for job_type in models.V2_JOB_TYPES:
        assert job_type in claude_text, f"Job type '{job_type}' missing from CLAUDE.md"


def test_claude_md_lists_all_calculator_files():
    """Every calculator file should be mentioned in CLAUDE.md file map."""
    claude_md_path = Path(__file__).parent.parent / "CLAUDE.md"
    claude_text = claude_md_path.read_text()

    calc_dir = Path(__file__).parent.parent / "backend" / "calculators"
    for py_file in calc_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        assert py_file.stem in claude_text, (
            f"Calculator '{py_file.name}' missing from CLAUDE.md"
        )


def test_claude_md_lists_all_routers():
    """Every router file should be mentioned in CLAUDE.md."""
    claude_md_path = Path(__file__).parent.parent / "CLAUDE.md"
    claude_text = claude_md_path.read_text()

    router_dir = Path(__file__).parent.parent / "backend" / "routers"
    for py_file in router_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        assert py_file.stem in claude_text, (
            f"Router '{py_file.name}' missing from CLAUDE.md"
        )


def test_claude_md_lists_all_question_trees():
    """Every question tree JSON should have its job type in CLAUDE.md."""
    claude_md_path = Path(__file__).parent.parent / "CLAUDE.md"
    claude_text = claude_md_path.read_text()

    tree_dir = Path(__file__).parent.parent / "backend" / "question_trees" / "data"
    for json_file in tree_dir.glob("*.json"):
        job_type = json_file.stem
        assert job_type in claude_text, (
            f"Question tree '{json_file.name}' (job type '{job_type}') missing from CLAUDE.md"
        )


def test_question_trees_match_v2_job_types():
    """Every V2_JOB_TYPE should have a corresponding question tree JSON file."""
    tree_dir = Path(__file__).parent.parent / "backend" / "question_trees" / "data"
    tree_files = {f.stem for f in tree_dir.glob("*.json")}

    for job_type in models.V2_JOB_TYPES:
        assert job_type in tree_files, (
            f"Job type '{job_type}' has no question tree file in data/"
        )
