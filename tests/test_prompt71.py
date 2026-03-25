"""
P71 — Async Pipeline Stages (Calculate, Estimate, Price)

Tests verify:
1. Sync fallback still works for calculate/estimate/price (no ANTHROPIC_API_KEY)
2. Status endpoint returns pipeline_stage when processing
3. Status endpoint returns stage_error on failed stages
4. Status endpoint returns quote data when pipeline is complete
5. Full sync pipeline end-to-end
"""

from backend import models
from sqlalchemy.orm.attributes import flag_modified


def _start_and_complete_intake(client, auth_headers, description=None,
                                job_type="cantilever_gate"):
    """Start a session and answer all required fields. Returns session_id."""
    resp = client.post("/api/session/start", json={
        "description": description or "10 foot cantilever gate, 6 feet tall, powder coat",
        "job_type": job_type,
    }, headers=auth_headers)
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    answers = {
        "clear_width": "10",
        "height": "6",
        "material_type": "Carbon steel (standard)",
        "frame_material": "Square tube (most common)",
        "frame_gauge": "11 gauge (0.120\" - standard for gates)",
        "infill_type": "Expanded metal",
        "post_count": "3 posts (standard)",
        "finish": "Powder coat (most durable, outsourced)",
        "installation": "Full installation (gate + posts + concrete)",
    }
    resp = client.post(f"/api/session/{session_id}/answer",
                       json={"answers": answers}, headers=auth_headers)
    assert resp.status_code == 200
    return session_id


# === 1. Sync calculate still works ===

def test_sync_calculate_returns_material_list(client, auth_headers):
    """POST /calculate returns material_list directly (sync fallback)."""
    session_id = _start_and_complete_intake(client, auth_headers)
    resp = client.post(f"/api/session/{session_id}/calculate",
                       headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "material_list" in data
    assert data["job_type"] == "cantilever_gate"
    assert data["session_id"] == session_id


# === 2. Sync estimate still works ===

def test_sync_estimate_returns_labor(client, auth_headers):
    """POST /estimate returns labor_estimate directly (sync fallback)."""
    session_id = _start_and_complete_intake(client, auth_headers)
    client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)

    resp = client.post(f"/api/session/{session_id}/estimate",
                       headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "labor_estimate" in data
    assert "finishing" in data
    assert "total_labor_hours" in data
    assert data["labor_estimate"]["processes"]


# === 3. Sync price still works ===

def test_sync_price_creates_quote(client, auth_headers):
    """POST /price returns quote_id and priced_quote (sync fallback)."""
    session_id = _start_and_complete_intake(client, auth_headers)
    client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    client.post(f"/api/session/{session_id}/estimate", headers=auth_headers)

    resp = client.post(f"/api/session/{session_id}/price",
                       headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "quote_id" in data
    assert "quote_number" in data
    assert "priced_quote" in data
    assert data["priced_quote"]["subtotal"] > 0


# === 4. Status endpoint returns pipeline_stage when processing ===

def test_status_shows_pipeline_stage_when_processing(client, auth_headers, db):
    """GET /status with status=processing returns pipeline_stage field."""
    session_id = _start_and_complete_intake(client, auth_headers)

    # Manually set session to processing+calculate to simulate async
    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    session.status = "processing"
    session.stage = "calculate"
    db.commit()

    resp = client.get(f"/api/session/{session_id}/status",
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processing"
    assert data["pipeline_stage"] == "calculate"
    assert data["stage"] == "calculate"


# === 5. Status endpoint returns stage_error on error ===

def test_status_shows_stage_error(client, auth_headers, db):
    """GET /status includes stage_error when _stage_error is in params_json."""
    session_id = _start_and_complete_intake(client, auth_headers)

    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    params = dict(session.params_json or {})
    params["_stage_error"] = "Calculate failed: test error"
    session.params_json = params
    session.status = "error"
    flag_modified(session, "params_json")
    db.commit()

    resp = client.get(f"/api/session/{session_id}/status",
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["stage_error"] == "Calculate failed: test error"


# === 6. Status endpoint returns quote data when complete ===

def test_status_shows_quote_data_on_complete(client, auth_headers, db):
    """GET /status includes quote_id and priced_quote when pipeline is complete."""
    session_id = _start_and_complete_intake(client, auth_headers)
    client.post(f"/api/session/{session_id}/calculate", headers=auth_headers)
    client.post(f"/api/session/{session_id}/estimate", headers=auth_headers)
    price_resp = client.post(f"/api/session/{session_id}/price",
                             headers=auth_headers)
    assert price_resp.status_code == 200
    quote_id = price_resp.json()["quote_id"]

    # Now check status
    resp = client.get(f"/api/session/{session_id}/status",
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stage"] == "output"
    assert data["status"] == "complete"
    assert data["quote_id"] == quote_id
    assert "priced_quote" in data
    assert data["priced_quote"]["subtotal"] > 0


# === 7. Full sync pipeline end-to-end ===

def test_full_sync_pipeline(client, auth_headers, db):
    """Start → answer → calculate → estimate → price → status shows complete."""
    session_id = _start_and_complete_intake(client, auth_headers)

    # Calculate
    calc = client.post(f"/api/session/{session_id}/calculate",
                       headers=auth_headers)
    assert calc.status_code == 200
    assert "material_list" in calc.json()

    # Estimate
    est = client.post(f"/api/session/{session_id}/estimate",
                      headers=auth_headers)
    assert est.status_code == 200
    assert "labor_estimate" in est.json()

    # Price
    price = client.post(f"/api/session/{session_id}/price",
                        headers=auth_headers)
    assert price.status_code == 200
    assert "quote_id" in price.json()
    assert "priced_quote" in price.json()
    quote_id = price.json()["quote_id"]

    # Verify via status endpoint
    status = client.get(f"/api/session/{session_id}/status",
                        headers=auth_headers)
    assert status.status_code == 200
    sdata = status.json()
    assert sdata["stage"] == "output"
    assert sdata["status"] == "complete"
    assert sdata["quote_id"] == quote_id
    assert sdata["quote_number"]

    # Verify Quote record in DB
    quote = db.query(models.Quote).filter(
        models.Quote.id == quote_id,
    ).first()
    assert quote is not None
    assert quote.session_id == session_id
    assert quote.outputs_json is not None
    assert quote.subtotal > 0


# === 8. Status pipeline_stage for estimate processing ===

def test_status_pipeline_stage_estimate(client, auth_headers, db):
    """GET /status with status=processing, stage=estimate shows pipeline_stage."""
    session_id = _start_and_complete_intake(client, auth_headers)

    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    session.status = "processing"
    session.stage = "estimate"
    db.commit()

    resp = client.get(f"/api/session/{session_id}/status",
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["pipeline_stage"] == "estimate"


# === 9. Status pipeline_stage for price processing ===

def test_status_pipeline_stage_price(client, auth_headers, db):
    """GET /status with status=processing, stage=price shows pipeline_stage."""
    session_id = _start_and_complete_intake(client, auth_headers)

    session = db.query(models.QuoteSession).filter(
        models.QuoteSession.id == session_id,
    ).first()
    session.status = "processing"
    session.stage = "price"
    db.commit()

    resp = client.get(f"/api/session/{session_id}/status",
                      headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["pipeline_stage"] == "price"
