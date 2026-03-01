"""
In-memory job store for async AI quote processing.

Railway's proxy returns 503 after ~30s, but Gemini can take 60-120s.
This module lets endpoints return a job_id immediately and run Gemini
in a background thread. The frontend polls GET /api/ai/job/{job_id}.
"""

import threading
import time
import uuid
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger("createstage.quote_jobs")

# Thread-safe job store
_job_store: dict = {}
_lock = threading.Lock()

# Job TTL: 1 hour
_JOB_TTL_SECONDS = 3600

# Watchdog timeout for background tasks
_WATCHDOG_TIMEOUT_SECONDS = 180


def create_job(job_type: str, input_data: dict) -> str:
    """Create a new pending job. Returns job_id."""
    job_id = uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "job_type": job_type,  # "estimate" or "quote"
        "status": "pending",
        "input_data": input_data,
        "result": None,
        "error": None,
        "created_at": time.time(),
        "_db_saved": False,
    }
    with _lock:
        _job_store[job_id] = job
    logger.info(f"Job {job_id} created (type={job_type})")
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    """Get job by ID. Returns None if not found or expired."""
    with _lock:
        job = _job_store.get(job_id)
        if job is None:
            return None
        if time.time() - job["created_at"] > _JOB_TTL_SECONDS:
            del _job_store[job_id]
            return None
        # Return a copy to avoid race conditions on read
        return dict(job)


def update_job(job_id: str, status: str, result: Any = None, error: Optional[str] = None) -> None:
    """Update job status, result, or error."""
    with _lock:
        job = _job_store.get(job_id)
        if job is None:
            return
        job["status"] = status
        if result is not None:
            job["result"] = result
        if error is not None:
            job["error"] = error


def mark_db_saved(job_id: str) -> bool:
    """Mark a job's DB save as done. Returns True if this call did the marking (first caller wins)."""
    with _lock:
        job = _job_store.get(job_id)
        if job is None:
            return False
        if job["_db_saved"]:
            return False
        job["_db_saved"] = True
        return True


def run_in_background(job_id: str, target_fn: Callable, args: tuple = ()) -> None:
    """Spawn a daemon thread to run target_fn, with a watchdog timer."""

    def _worker():
        # Set status to running
        update_job(job_id, "running")

        # Watchdog timer — fires if target_fn takes too long
        def _timeout_handler():
            logger.warning(f"Job {job_id} timed out after {_WATCHDOG_TIMEOUT_SECONDS}s")
            update_job(job_id, "timeout", error=f"Timed out after {_WATCHDOG_TIMEOUT_SECONDS} seconds")

        watchdog = threading.Timer(_WATCHDOG_TIMEOUT_SECONDS, _timeout_handler)
        watchdog.daemon = True
        watchdog.start()

        try:
            result = target_fn(*args)
            watchdog.cancel()
            # Only update if not already timed out
            with _lock:
                job = _job_store.get(job_id)
                if job and job["status"] != "timeout":
                    job["status"] = "complete"
                    job["result"] = result
            logger.info(f"Job {job_id} completed successfully")
        except Exception as e:
            watchdog.cancel()
            logger.error(f"Job {job_id} failed: {e}")
            with _lock:
                job = _job_store.get(job_id)
                if job and job["status"] != "timeout":
                    job["status"] = "failed"
                    job["error"] = str(e)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def cleanup_expired() -> int:
    """Remove jobs older than TTL. Returns count of removed jobs."""
    now = time.time()
    removed = 0
    with _lock:
        expired_ids = [
            jid for jid, job in _job_store.items()
            if now - job["created_at"] > _JOB_TTL_SECONDS
        ]
        for jid in expired_ids:
            del _job_store[jid]
            removed += 1
    if removed:
        logger.info(f"Cleaned up {removed} expired jobs")
    return removed


def start_cleanup_cycle() -> None:
    """Start a periodic cleanup timer that runs every 5 minutes."""

    def _cycle():
        cleanup_expired()
        # Schedule next run
        t = threading.Timer(300, _cycle)
        t.daemon = True
        t.start()

    # First cleanup after 5 minutes
    t = threading.Timer(300, _cycle)
    t.daemon = True
    t.start()
    logger.info("Job cleanup cycle started (every 5 minutes)")
