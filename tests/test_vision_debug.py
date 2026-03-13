"""
Vision debugging tests — isolate exactly where the photo extraction pipeline fails.

Tests run without an API key (unit-level) plus one integration test that requires
ANTHROPIC_API_KEY to be set (skipped otherwise).
"""

import base64
import io
import os
import struct
import zlib
import tempfile

import pytest


def _minimal_png():
    """Create a minimal valid 1x1 red pixel PNG."""
    def _chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw_data = b"\x00\xff\x00\x00"  # filter byte + RGB (red pixel)
    idat = _chunk(b"IDAT", zlib.compress(raw_data))
    iend = _chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


# ---- Unit tests (no API key needed) ----

def test_read_image_local_file():
    """_read_image should read a local file successfully."""
    from backend.question_trees.engine import _read_image

    png_bytes = _minimal_png()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(png_bytes)
        f.flush()
        tmp_path = f.name

    try:
        result = _read_image(tmp_path)
        assert result is not None, "_read_image returned None for existing file"
        assert len(result) == len(png_bytes), \
            "Read %d bytes, expected %d" % (len(result), len(png_bytes))
    finally:
        os.unlink(tmp_path)


def test_read_image_missing_file():
    """_read_image should return None (not crash) for missing file."""
    from backend.question_trees.engine import _read_image

    result = _read_image("/nonexistent/path/photo.png")
    assert result is None, "Should return None for missing file"


def test_read_image_local_uploads_path():
    """_read_image should handle /uploads/photos/xxx.png paths (Railway local storage)."""
    from backend.question_trees.engine import _read_image

    png_bytes = _minimal_png()
    # Simulate the path that _save_locally produces: /uploads/photos/filename.png
    upload_dir = os.path.join(os.getcwd(), "uploads", "photos")
    os.makedirs(upload_dir, exist_ok=True)
    test_file = os.path.join(upload_dir, "test_vision_debug.png")
    with open(test_file, "wb") as f:
        f.write(png_bytes)

    try:
        # This is the path format returned by _save_locally
        result = _read_image("/uploads/photos/test_vision_debug.png")
        assert result is not None, \
            "_read_image returned None for /uploads/photos/ path — path resolution broken"
        assert len(result) == len(png_bytes)
    finally:
        os.unlink(test_file)


def test_base64_encoding_valid():
    """Base64 encoding of a PNG produces valid base64 string."""
    png_bytes = _minimal_png()
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    assert len(b64) > 0, "Base64 encoding produced empty string"
    # Verify it round-trips
    decoded = base64.b64decode(b64)
    assert decoded == png_bytes, "Base64 round-trip failed"


def test_call_vision_rejects_empty_image():
    """call_vision should return None and log error for empty image."""
    from backend.claude_client import call_vision

    result = call_vision("test prompt", "", "image/png")
    assert result is None, "Should return None for empty image_b64"


def test_call_vision_rejects_empty_mime():
    """call_vision should return None and log error for empty mime type."""
    from backend.claude_client import call_vision

    result = call_vision("test prompt", "abc123", "")
    assert result is None, "Should return None for empty mime_type"


def test_call_vision_payload_structure():
    """Verify the API payload structure matches Anthropic's expected format."""
    import json as json_mod

    # Build the same payload that _call_claude builds for vision
    png_bytes = _minimal_png()
    image_b64 = base64.b64encode(png_bytes).decode("utf-8")
    mime_type = "image/png"

    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": image_b64,
            }
        },
        {"type": "text", "text": "What is in this image?"}
    ]

    payload = {
        "model": "claude-opus-4-6",
        "max_tokens": 16384,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": content}],
        "system": "You are a fabrication engineering AI. Respond ONLY with valid JSON.",
    }

    # Verify it serializes to valid JSON
    serialized = json_mod.dumps(payload)
    assert len(serialized) > 0

    # Verify image block has all required fields
    img_block = payload["messages"][0]["content"][0]
    assert img_block["type"] == "image"
    assert img_block["source"]["type"] == "base64"
    assert img_block["source"]["media_type"] == "image/png"
    assert len(img_block["source"]["data"]) > 10


def test_empty_photo_result_format():
    """_empty_photo_result should have all expected keys."""
    from backend.question_trees.engine import _empty_photo_result

    result = _empty_photo_result()
    assert "extracted_fields" in result
    assert "photo_observations" in result
    assert "material_detected" in result
    assert "dimensions_detected" in result
    assert "confidence" in result
    assert result["confidence"] == 0.0


# ---- Integration test (requires ANTHROPIC_API_KEY) ----

@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live vision test"
)
def test_call_vision_live_with_tiny_image():
    """Live test: send a 1x1 PNG to Claude Vision and verify we get a response.

    This isolates whether the API call itself works, separate from
    _read_image() or the question tree engine.
    """
    from backend.claude_client import call_vision

    png_bytes = _minimal_png()
    image_b64 = base64.b64encode(png_bytes).decode("utf-8")

    prompt = (
        "This is a tiny 1x1 pixel test image. "
        "Respond with exactly this JSON: "
        '{"status": "ok", "description": "1x1 pixel test image"}'
    )

    result = call_vision(
        prompt=prompt,
        image_b64=image_b64,
        mime_type="image/png",
        temperature=0.0,
        timeout=30,
    )

    assert result is not None, (
        "call_vision returned None — check logs for API error. "
        "Common causes: invalid model ID, wrong API version, "
        "image payload format issue, or API key permissions."
    )
    assert len(result) > 0, "call_vision returned empty string"
    # Should be parseable JSON
    import json
    parsed = json.loads(result)
    assert isinstance(parsed, dict), "Response should be a JSON object"


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live vision test"
)
def test_extract_from_photo_live():
    """Live test: full extract_from_photo pipeline with a local file.

    Tests _read_image → base64 → call_vision → parse response.
    """
    from backend.question_trees.engine import QuestionTreeEngine

    png_bytes = _minimal_png()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(png_bytes)
        f.flush()
        tmp_path = f.name

    try:
        engine = QuestionTreeEngine()
        result = engine.extract_from_photo(
            job_type="straight_railing",
            photo_url_or_path=tmp_path,
            description="test image",
        )
        # Should NOT be the empty fallback
        assert result["confidence"] >= 0, "Should return a result dict"
        # If vision is working, photo_observations should not be the fallback message
        if result["photo_observations"] == "Photo received — vision processing unavailable. Photo stored for reference.":
            pytest.fail(
                "Got fallback 'vision processing unavailable' — "
                "the pipeline is failing silently somewhere. Check logs."
            )
    finally:
        os.unlink(tmp_path)
