"""
Tests for async AI quote processing — job store + polling endpoints.

Covers: job lifecycle, expiry, cleanup, POST/GET endpoints, background
completion, timeout handling. All AI calls are mocked.
"""

import time
import threading
from unittest.mock import patch, MagicMock
import pytest

from backend.quote_jobs import (
    create_job, get_job, update_job, mark_db_saved,
    cleanup_expired, _job_store, _lock, _JOB_TTL_SECONDS,
)


@pytest.fixture(autouse=True)
def clear_job_store():
    """Clear the global job store before each test."""
    with _lock:
        _job_store.clear()
    yield
    with _lock:
        _job_store.clear()


@pytest.fixture(autouse=True)
def clear_prompt_cache():
    """Clear the prompt cache before each test."""
    from backend.routers.ai_quote import _prompt_cache, _cache_lock
    with _cache_lock:
        _prompt_cache.clear()
    yield
    with _cache_lock:
        _prompt_cache.clear()


# ---- Job store unit tests ----

def test_job_lifecycle():
    """Create → get → update → get returns updated state."""
    job_id = create_job("estimate", {"prompt": "test"})
    assert job_id is not None

    job = get_job(job_id)
    assert job is not None
    assert job["status"] == "pending"
    assert job["job_type"] == "estimate"

    update_job(job_id, "running")
    job = get_job(job_id)
    assert job["status"] == "running"

    update_job(job_id, "complete", result={"some": "data"})
    job = get_job(job_id)
    assert job["status"] == "complete"
    assert job["result"] == {"some": "data"}


def test_job_expiry():
    """Expired jobs return None from get_job."""
    job_id = create_job("estimate", {"prompt": "test"})

    # Backdate the job
    with _lock:
        _job_store[job_id]["created_at"] = time.time() - _JOB_TTL_SECONDS - 1

    assert get_job(job_id) is None


def test_job_not_found():
    """Non-existent job returns None."""
    assert get_job("nonexistent123") is None


def test_cleanup_expired():
    """Cleanup removes expired jobs, keeps active ones."""
    active_id = create_job("estimate", {"prompt": "active"})
    expired_id = create_job("estimate", {"prompt": "expired"})

    # Backdate the expired job
    with _lock:
        _job_store[expired_id]["created_at"] = time.time() - _JOB_TTL_SECONDS - 1

    removed = cleanup_expired()
    assert removed == 1
    assert get_job(active_id) is not None
    assert get_job(expired_id) is None


def test_mark_db_saved():
    """mark_db_saved returns True on first call, False on subsequent."""
    job_id = create_job("quote", {"prompt": "test"})
    assert mark_db_saved(job_id) is True
    assert mark_db_saved(job_id) is False


def test_mark_db_saved_nonexistent():
    """mark_db_saved returns False for non-existent job."""
    assert mark_db_saved("nonexistent") is False


# ---- API endpoint tests ----

MOCK_ESTIMATE = {
    "job_summary": "Test steel frame",
    "job_type": "structural",
    "confidence": "high",
    "assumptions": ["Standard A36 steel"],
    "warnings": [],
    "labor_rate_fallback": 125,
    "waste_factor": 0.05,
    "material_markup_pct": 15,
    "stainless_multiplier": 1.0,
    "contingency_pct": 0,
    "profit_margin_pct": 20,
    "line_items": [
        {
            "description": "Steel frame",
            "material_type": "mild_steel",
            "process_type": "welding",
            "quantity": 1,
            "unit": "ea",
            "material_cost": 100.0,
            "labor_hours": 4.0,
            "outsourced": False,
        }
    ],
    "cut_list": [],
    "build_order": [],
}


def test_estimate_returns_pending(client):
    """POST /api/ai/estimate returns pending + job_id (no cache hit)."""
    with patch("backend.routers.ai_quote.call_claude_background") as mock_ai:
        mock_ai.return_value = MOCK_ESTIMATE

        res = client.post("/api/ai/estimate", json={
            "job_description": "Build a steel frame for a mezzanine"
        })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "pending"
    assert "job_id" in data


def test_estimate_cache_hit_returns_complete(client):
    """POST /api/ai/estimate returns complete immediately on cache hit."""
    from backend.routers.ai_quote import _cache_set

    prompt = "Build a steel frame for a mezzanine"
    _cache_set(prompt[:100], MOCK_ESTIMATE)

    res = client.post("/api/ai/estimate", json={
        "job_description": prompt
    })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "complete"
    assert "raw_estimate" in data
    assert data["job_summary"] == "Test steel frame"


def test_job_poll_not_found(client):
    """GET /api/ai/job/invalid returns 404."""
    res = client.get("/api/ai/job/nonexistent123")
    assert res.status_code == 404


def test_job_poll_pending(client):
    """GET /api/ai/job returns pending status for queued job."""
    job_id = create_job("estimate", {"prompt": "test"})

    res = client.get("/api/ai/job/%s" % job_id)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "pending"
    assert data["job_id"] == job_id


def test_job_poll_complete(client):
    """GET /api/ai/job returns result for completed estimate job."""
    job_id = create_job("estimate", {"prompt": "test"})
    result = {
        "job_summary": "Test",
        "job_type": "custom",
        "estimated_cost": 100,
        "estimated_total": 120,
    }
    update_job(job_id, "complete", result=result)

    res = client.get("/api/ai/job/%s" % job_id)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "complete"
    assert data["result"]["job_summary"] == "Test"


def test_job_poll_failed(client):
    """GET /api/ai/job returns error for failed job."""
    job_id = create_job("estimate", {"prompt": "test"})
    update_job(job_id, "failed", error="Gemini API error: quota exceeded")

    res = client.get("/api/ai/job/%s" % job_id)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "failed"
    assert "quota exceeded" in data["error"]


def test_quote_with_precomputed_is_synchronous(client):
    """POST /api/ai/quote with pre_computed_estimate stays synchronous."""
    # Create a customer first
    cust_res = client.post("/api/customers/", json={
        "name": "Test Customer",
        "email": "test@example.com",
    })
    assert cust_res.status_code == 200
    customer_id = cust_res.json()["id"]

    res = client.post("/api/ai/quote", json={
        "job_description": "Steel table",
        "customer_id": customer_id,
        "pre_computed_estimate": MOCK_ESTIMATE,
    })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "complete"
    assert "quote" in data
    assert data["quote"]["quote_number"] is not None


def test_quote_without_precomputed_returns_pending(client):
    """POST /api/ai/quote without pre_computed returns pending + job_id."""
    # Create a customer first
    cust_res = client.post("/api/customers/", json={
        "name": "Test Customer 2",
        "email": "test2@example.com",
    })
    assert cust_res.status_code == 200
    customer_id = cust_res.json()["id"]

    with patch("backend.routers.ai_quote.call_claude_background") as mock_ai:
        mock_ai.return_value = MOCK_ESTIMATE

        res = client.post("/api/ai/quote", json={
            "job_description": "Build a custom steel table",
            "customer_id": customer_id,
        })

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "pending"
    assert "job_id" in data


def test_background_task_completion():
    """Background task completes and updates job status."""
    from backend.quote_jobs import run_in_background

    def fast_task():
        return {"result": "done"}

    job_id = create_job("estimate", {"prompt": "test"})
    run_in_background(job_id, fast_task)

    # Wait for background thread
    time.sleep(0.5)

    job = get_job(job_id)
    assert job is not None
    assert job["status"] == "complete"
    assert job["result"] == {"result": "done"}


def test_background_task_failure():
    """Background task failure sets job status to failed."""
    from backend.quote_jobs import run_in_background

    def failing_task():
        raise RuntimeError("Something went wrong")

    job_id = create_job("estimate", {"prompt": "test"})
    run_in_background(job_id, failing_task)

    # Wait for background thread
    time.sleep(0.5)

    job = get_job(job_id)
    assert job is not None
    assert job["status"] == "failed"
    assert "Something went wrong" in job["error"]


def test_background_task_timeout():
    """Background task exceeding watchdog timeout gets marked as timeout."""
    from backend.quote_jobs import run_in_background, _WATCHDOG_TIMEOUT_SECONDS
    import backend.quote_jobs as qj

    # Temporarily reduce timeout for testing
    original_timeout = qj._WATCHDOG_TIMEOUT_SECONDS
    qj._WATCHDOG_TIMEOUT_SECONDS = 0.3  # 300ms

    event = threading.Event()

    def slow_task():
        event.wait(5)  # Wait up to 5s (will be interrupted by test)
        return {"result": "too late"}

    try:
        job_id = create_job("estimate", {"prompt": "test"})
        run_in_background(job_id, slow_task)

        # Wait for watchdog to fire
        time.sleep(1.0)

        job = get_job(job_id)
        assert job is not None
        assert job["status"] == "timeout"
        assert "Timed out" in job["error"]
    finally:
        qj._WATCHDOG_TIMEOUT_SECONDS = original_timeout
        event.set()  # Unblock the slow task thread
