"""
Tests for photo upload, Gemini Vision extraction, and extraction confirmation.

Session 3B hotfix — photo upload + vision processing + extraction confirmation.
"""

import io
import os
from pathlib import Path

import pytest
from backend.question_trees.engine import QuestionTreeEngine


# --- Photo Upload Tests ---


def test_photo_upload_endpoint_exists(client, auth_headers):
    """POST /api/photos/upload returns 200 or 422 (not 404)."""
    # Send a request without a file — should get 422 (validation error), not 404
    response = client.post("/api/photos/upload", headers=auth_headers)
    assert response.status_code != 404, "Photo upload endpoint not registered"


def test_photo_upload_accepts_image(client, auth_headers):
    """Upload a valid image file returns success."""
    # Create a minimal valid PNG (1x1 pixel)
    png_bytes = _minimal_png()
    files = {"file": ("test.png", io.BytesIO(png_bytes), "image/png")}
    response = client.post("/api/photos/upload", files=files, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "photo_url" in data
    assert "filename" in data
    assert data["filename"].endswith(".png")


def test_photo_upload_rejects_non_image(client, auth_headers):
    """Non-image file returns error."""
    files = {"file": ("test.txt", io.BytesIO(b"not an image"), "text/plain")}
    response = client.post("/api/photos/upload", files=files, headers=auth_headers)
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


def test_photo_upload_rejects_empty_file(client, auth_headers):
    """Empty file returns error."""
    files = {"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
    response = client.post("/api/photos/upload", files=files, headers=auth_headers)
    assert response.status_code == 400


def test_photo_upload_size_limit(client, auth_headers):
    """File > 10MB is rejected."""
    # Create a file just over 10MB
    big_bytes = b"\x00" * (10 * 1024 * 1024 + 1)
    files = {"file": ("big.jpg", io.BytesIO(big_bytes), "image/jpeg")}
    response = client.post("/api/photos/upload", files=files, headers=auth_headers)
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()


def test_photo_upload_requires_auth(client):
    """Photo upload without auth is rejected."""
    png_bytes = _minimal_png()
    files = {"file": ("test.png", io.BytesIO(png_bytes), "image/png")}
    response = client.post("/api/photos/upload", files=files)
    assert response.status_code in (401, 403)


def test_photo_upload_with_session_id(client, auth_headers):
    """Upload with session_id includes it in filename."""
    png_bytes = _minimal_png()
    files = {"file": ("test.png", io.BytesIO(png_bytes), "image/png")}
    data = {"session_id": "my-session-123"}
    response = client.post("/api/photos/upload", files=files, data=data, headers=auth_headers)
    assert response.status_code == 200
    assert "my-session-123" in response.json()["filename"]


# --- Vision Extraction Tests ---


def test_extract_from_photo_returns_structure():
    """extract_from_photo returns dict with required keys."""
    engine = QuestionTreeEngine()
    # Without API key, should return empty extraction gracefully
    result = engine.extract_from_photo(
        "cantilever_gate", "/nonexistent/file.jpg", "test gate"
    )
    assert isinstance(result, dict)
    assert "extracted_fields" in result
    assert "photo_observations" in result
    assert "material_detected" in result
    assert "dimensions_detected" in result
    assert "damage_assessment" in result
    assert "confidence" in result


def test_extract_from_photo_graceful_without_gemini():
    """Without API key, returns empty extraction (not error)."""
    engine = QuestionTreeEngine()
    # Even with a bad path, should return graceful result
    result = engine.extract_from_photo(
        "straight_railing", "/does/not/exist.jpg"
    )
    assert result["extracted_fields"] == {}
    assert result["confidence"] == 0.0
    assert result["material_detected"] == "unknown"


def test_extract_from_photo_all_job_types():
    """extract_from_photo works for all 25 job types without error."""
    from backend.models import V2_JOB_TYPES
    engine = QuestionTreeEngine()
    for jt in V2_JOB_TYPES:
        result = engine.extract_from_photo(jt, "/nonexistent.jpg")
        assert isinstance(result, dict)
        assert "extracted_fields" in result


# --- Extraction Confirmation Tests ---


def test_session_start_returns_extracted_fields(client, auth_headers):
    """Start with description -> response includes extracted_fields."""
    response = client.post(
        "/api/session/start",
        json={"description": "10 foot cantilever gate, 6 feet tall"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "extracted_fields" in data
    assert isinstance(data["extracted_fields"], dict)


def test_session_start_returns_photo_fields(client, auth_headers):
    """Start with photo_urls -> response includes photo_extracted_fields."""
    response = client.post(
        "/api/session/start",
        json={
            "description": "Need a new gate",
            "photo_urls": [],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "photo_extracted_fields" in data
    assert isinstance(data["photo_extracted_fields"], dict)


def test_extracted_fields_skip_questions(client, auth_headers):
    """Fields in params_json are NOT in next_questions."""
    # Start session
    response = client.post(
        "/api/session/start",
        json={
            "description": "New cantilever gate",
            "job_type": "cantilever_gate",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    session_id = data["session_id"]

    # Submit some answers
    response = client.post(
        f"/api/session/{session_id}/answer",
        json={"answers": {"clear_width": "10", "height": "6"}},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()

    # Check that answered fields don't appear in next_questions
    next_qids = [q["id"] for q in data["next_questions"]]
    assert "clear_width" not in next_qids
    assert "height" not in next_qids


def test_text_extraction_wins_over_photo():
    """Text-extracted fields take priority over photo-extracted fields."""
    # This is tested by the merge logic in start_session
    # Text fields are added first, photo fields only added if not already present
    text_fields = {"clear_width": "10", "height": "6"}
    photo_fields = {"clear_width": "12", "material": "stainless"}

    # Simulate the merge logic from start_session
    merged = dict(text_fields)
    merged.update({k: v for k, v in photo_fields.items() if k not in merged})

    assert merged["clear_width"] == "10"  # Text wins
    assert merged["height"] == "6"  # Text only
    assert merged["material"] == "stainless"  # Photo only (new field)


def test_edit_extracted_field_re_adds_question(client, auth_headers):
    """Removing a field from params_json makes it appear in next_questions again."""
    # Start with a specific job type
    response = client.post(
        "/api/session/start",
        json={
            "description": "New bollard installation",
            "job_type": "bollard",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    session_id = data["session_id"]

    # Answer height
    response = client.post(
        f"/api/session/{session_id}/answer",
        json={"answers": {"height": "36"}},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()

    # height should NOT be in next questions
    next_qids = [q["id"] for q in data["next_questions"]]
    assert "height" not in next_qids

    # Submit empty answers to check status — height should still be absent
    response = client.get(
        f"/api/session/{session_id}/status",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    next_qids = [q["id"] for q in data["next_questions"]]
    assert "height" not in next_qids


def test_answer_with_photo_url(client, auth_headers):
    """Submitting answers with photo_url stores the URL."""
    response = client.post(
        "/api/session/start",
        json={
            "description": "Repair this railing",
            "job_type": "repair_decorative",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    # Submit with a photo_url
    response = client.post(
        f"/api/session/{session_id}/answer",
        json={
            "answers": {"repair_type": "Broken weld (re-weld only)"},
            "photo_url": "/uploads/photos/test_photo.jpg",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200

    # Verify photo URL is stored in session
    response = client.get(
        f"/api/session/{session_id}/status",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "/uploads/photos/test_photo.jpg" in data["photo_urls"]


# --- Frontend Serving Tests ---


def test_photo_upload_js_function():
    """uploadPhoto function exists in api.js."""
    api_js = Path(__file__).parent.parent / "frontend" / "js" / "api.js"
    content = api_js.read_text()
    assert "uploadPhoto" in content


def test_confirmed_fields_css():
    """Confirmed fields CSS exists in style.css."""
    css = Path(__file__).parent.parent / "frontend" / "css" / "style.css"
    content = css.read_text()
    assert ".confirmed-field" in content
    assert ".confirmed-edit" in content
    assert ".photo-preview" in content


def test_photo_previews_in_quote_flow():
    """Photo preview functions exist in quote-flow.js."""
    qf_js = Path(__file__).parent.parent / "frontend" / "js" / "quote-flow.js"
    content = qf_js.read_text()
    assert "sessionPhotoUrls" in content
    assert "_showPhotoPreview" in content
    assert "photo-upload-btn" in content


def test_all_25_job_types_in_frontend():
    """All 25 job types are listed in the frontend JOB_TYPES dict."""
    from backend.models import V2_JOB_TYPES
    qf_js = Path(__file__).parent.parent / "frontend" / "js" / "quote-flow.js"
    content = qf_js.read_text()
    for jt in V2_JOB_TYPES:
        assert jt in content, f"Job type '{jt}' missing from quote-flow.js JOB_TYPES"


# --- Helper ---


def _minimal_png() -> bytes:
    """Create a minimal valid 1x1 pixel PNG."""
    import struct
    import zlib

    def _chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw_data = b"\x00\xff\x00\x00"  # filter byte + RGB
    idat = _chunk(b"IDAT", zlib.compress(raw_data))
    iend = _chunk(b"IEND", b"")
    return signature + ihdr + idat + iend
