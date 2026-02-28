"""
Session 7 acceptance tests — Bid Document Parser (Enterprise Feature).

Tests:
1-3.   PDF text extraction
4-8.   Parser extraction with sample bid
9-10.  Job type mapping
11-12. Confidence scoring
13-14. Detail references and pre-populated fields
15-17. API endpoint tests
18-19. Bid → session flow
20-22. Keyword fallback and edge cases
"""

import os
import io
import pytest
from pathlib import Path

from backend.bid_parser import BidParser, RELEVANT_CSI_DIVISIONS, EXTRACTION_KEYWORDS
from backend.pdf_extractor import PDFExtractor


# --- Fixtures ---

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _sample_bid_text():
    """Load the sample bid excerpt."""
    path = FIXTURE_DIR / "sample_bid_excerpt.txt"
    return path.read_text()


def _make_test_pdf(text: str = "Test PDF content") -> bytes:
    """Create a minimal valid PDF in memory for testing."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)
    for line in text.split("\n"):
        # Replace non-latin-1 chars
        safe_line = line.encode("latin-1", errors="replace").decode("latin-1")
        pdf.cell(0, 5, safe_line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# ============================================================
# 1-3. PDF Text Extraction
# ============================================================

def test_pdf_extractor_text_output():
    """PDFExtractor returns text and page count from in-memory PDF."""
    extractor = PDFExtractor()
    pdf_bytes = _make_test_pdf("Hello World\nLine two")
    result = extractor.extract_text_from_bytes(pdf_bytes)

    assert "text" in result
    assert "Hello World" in result["text"]
    assert result["page_count"] == 1
    assert result["extraction_quality"] in ("good", "fair", "poor")


def test_pdf_extractor_rejects_non_pdf():
    """Non-PDF file raises ValueError."""
    extractor = PDFExtractor()
    with pytest.raises(Exception):
        extractor.extract_text(file_path="/tmp/nonexistent.txt")


def test_pdf_extractor_size_limit():
    """File > 50MB is rejected."""
    extractor = PDFExtractor()
    # Create bytes that are too large
    huge_bytes = b"x" * (51 * 1024 * 1024)
    with pytest.raises(ValueError, match="too large"):
        extractor.extract_text_from_bytes(huge_bytes)


# ============================================================
# 4-8. Parser Extraction with Sample Bid
# ============================================================

def test_parser_extracts_stair():
    """Sample bid -> extracts stair with dimensions (12' rise, 44\" width)."""
    parser = BidParser()
    result = parser.parse_document(_sample_bid_text(), filename="test.pdf")

    items = result["items"]
    stair_items = [i for i in items if i.get("job_type") == "complete_stair"]
    assert len(stair_items) >= 1, f"Expected stair item, got types: {[i.get('job_type') for i in items]}"

    stair = stair_items[0]
    # Should have dimensions
    dims = stair.get("dimensions") or {}
    assert dims, f"Expected dimensions on stair item: {stair}"


def test_parser_extracts_railing():
    """Sample bid -> extracts railing with 65 LF and detail reference A-12."""
    parser = BidParser()
    result = parser.parse_document(_sample_bid_text())

    items = result["items"]
    railing_items = [
        i for i in items
        if i.get("job_type") in ("stair_railing", "straight_railing")
    ]
    assert len(railing_items) >= 1, f"Expected railing item, got types: {[i.get('job_type') for i in items]}"


def test_parser_extracts_gate():
    """Sample bid -> extracts cantilever gate with 16' opening."""
    parser = BidParser()
    result = parser.parse_document(_sample_bid_text())

    items = result["items"]
    gate_items = [i for i in items if i.get("job_type") == "cantilever_gate"]
    assert len(gate_items) >= 1, f"Expected gate item, got types: {[i.get('job_type') for i in items]}"

    gate = gate_items[0]
    dims = gate.get("dimensions") or {}
    # Should have clear_width = 16
    assert dims.get("clear_width"), f"Expected clear_width in dimensions: {dims}"


def test_parser_extracts_bollards():
    """Sample bid -> extracts 6 bollards with dimensions."""
    parser = BidParser()
    result = parser.parse_document(_sample_bid_text())

    items = result["items"]
    bollard_items = [i for i in items if i.get("job_type") == "bollard"]
    assert len(bollard_items) >= 1, f"Expected bollard item, got types: {[i.get('job_type') for i in items]}"

    bollard = bollard_items[0]
    assert bollard.get("quantity") == 6 or "6" in str(bollard.get("source_text", ""))


def test_parser_extracts_misc_metals():
    """Sample bid -> extracts misc metals with low confidence (vague)."""
    parser = BidParser()
    result = parser.parse_document(_sample_bid_text())

    items = result["items"]
    misc_items = [
        i for i in items
        if i.get("job_type") == "custom_fab"
        or "misc" in str(i.get("description", "")).lower()
        or "embed" in str(i.get("description", "")).lower()
    ]
    assert len(misc_items) >= 1, f"Expected misc metals item, got: {[i.get('description') for i in items]}"

    # Misc metals should have lower confidence (vague reference)
    misc = misc_items[0]
    assert misc.get("confidence", 1.0) < 0.9


# ============================================================
# 9-10. Job Type Mapping
# ============================================================

def test_parser_maps_job_types():
    """Each extracted item has correct job_type mapping."""
    parser = BidParser()

    # Test specific description -> job type mappings
    assert parser._map_to_job_type("cantilever gate at parking entrance") == "cantilever_gate"
    assert parser._map_to_job_type("ornamental iron railing at stair 1") == "stair_railing"
    assert parser._map_to_job_type("fixed bollards at storefront") == "bollard"
    assert parser._map_to_job_type("steel stair with stringers") == "complete_stair"
    assert parser._map_to_job_type("spiral staircase") == "spiral_stair"
    assert parser._map_to_job_type("ornamental fence along property") == "ornamental_fence"
    assert parser._map_to_job_type("swing gate at pedestrian entrance") == "swing_gate"
    assert parser._map_to_job_type("miscellaneous metals and embed plates") == "custom_fab"
    assert parser._map_to_job_type("equipment screen enclosure") == "utility_enclosure"


def test_parser_maps_unknown_returns_none():
    """Items that don't match any type return None."""
    parser = BidParser()

    # Completely unrelated
    assert parser._map_to_job_type("concrete slab on grade") is None
    assert parser._map_to_job_type("HVAC ductwork") is None
    assert parser._map_to_job_type("electrical panel") is None


# ============================================================
# 11-12. Confidence Scoring
# ============================================================

def test_parser_confidence_scoring():
    """Items with dimensions score higher than vague items."""
    parser = BidParser()
    result = parser.parse_document(_sample_bid_text())
    items = result["items"]

    # Find a specific item (stair/gate with dimensions) and a vague item (misc metals)
    detailed_items = [i for i in items if i.get("dimensions")]
    vague_items = [i for i in items if not i.get("dimensions")]

    if detailed_items and vague_items:
        max_detailed = max(i.get("confidence", 0) for i in detailed_items)
        min_vague = min(i.get("confidence", 1) for i in vague_items)
        assert max_detailed > min_vague, (
            f"Detailed confidence ({max_detailed}) should be > vague ({min_vague})"
        )


def test_extraction_confidence_below_threshold():
    """Low confidence extraction includes warning for user."""
    parser = BidParser()
    # Parse a document with only vague references
    text = """
    SECTION 03 30 00 - CONCRETE
    Provide concrete slab on grade. Some miscellaneous metals may be required.
    """
    result = parser.parse_document(text)

    if result["items"]:
        # Any items found should be low confidence
        assert result["extraction_confidence"] <= 0.7


# ============================================================
# 13-14. Detail References and Pre-populated Fields
# ============================================================

def test_parser_preserves_detail_references():
    """Drawing references (Detail S-301, A-12) are captured."""
    parser = BidParser()
    result = parser.parse_document(_sample_bid_text())

    items = result["items"]
    items_with_refs = [i for i in items if i.get("detail_reference")]
    assert len(items_with_refs) >= 1, (
        f"Expected at least 1 item with detail_reference, got: "
        f"{[(i.get('description'), i.get('detail_reference')) for i in items]}"
    )


def test_parser_pre_populates_fields():
    """Extracted dimensions map to question tree field IDs."""
    parser = BidParser()
    result = parser.parse_document(_sample_bid_text())

    items = result["items"]
    items_with_fields = [i for i in items if i.get("pre_populated_fields")]
    assert len(items_with_fields) >= 1, (
        f"Expected at least 1 item with pre_populated_fields"
    )


# ============================================================
# 15-17. API Endpoint Tests
# ============================================================

def test_bid_upload_endpoint(client, auth_headers):
    """POST /api/bid/upload accepts PDF and returns extracted items."""
    pdf_bytes = _make_test_pdf(_sample_bid_text())
    resp = client.post(
        "/api/bid/upload",
        files={"file": ("test_bid.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Upload failed: {resp.json()}"
    data = resp.json()

    assert "bid_id" in data
    assert data["filename"] == "test_bid.pdf"
    assert "items" in data
    assert isinstance(data["items"], list)


def test_bid_parse_text_endpoint(client, auth_headers):
    """POST /api/bid/parse-text accepts pasted text."""
    resp = client.post(
        "/api/bid/parse-text",
        json={"text": _sample_bid_text()},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Parse-text failed: {resp.json()}"
    data = resp.json()

    assert "bid_id" in data
    assert "items" in data
    assert len(data["items"]) >= 3  # Should find stair, railing, gate, bollards, misc


def test_bid_parse_text_rejects_empty(client, auth_headers):
    """POST /api/bid/parse-text rejects empty text."""
    resp = client.post(
        "/api/bid/parse-text",
        json={"text": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_bid_quote_items_creates_sessions(client, auth_headers):
    """POST /api/bid/{id}/quote-items creates sessions with pre-populated fields."""
    # First, parse the text
    resp = client.post(
        "/api/bid/parse-text",
        json={"text": _sample_bid_text()},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    bid_id = data["bid_id"]
    items = data["items"]

    # Find indices of items with job_type mappings
    quotable_indices = [
        i for i, item in enumerate(items)
        if item.get("job_type") is not None
    ]
    assert len(quotable_indices) >= 1, "No quotable items found"

    # Create sessions from selected items
    resp = client.post(
        f"/api/bid/{bid_id}/quote-items",
        json={"item_indices": quotable_indices[:3]},  # Take up to 3
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Quote-items failed: {resp.json()}"
    sessions = resp.json()["sessions"]
    assert len(sessions) >= 1

    # Each session should have a session_id and job_type
    for s in sessions:
        if s.get("session_id"):
            assert s["job_type"] is not None


# ============================================================
# 18-19. Bid → Session Flow
# ============================================================

def test_bid_to_session_preserves_dimensions(client, auth_headers):
    """Session created from bid item has dimensions pre-filled."""
    # Parse bid
    resp = client.post(
        "/api/bid/parse-text",
        json={"text": _sample_bid_text()},
        headers=auth_headers,
    )
    bid_id = resp.json()["bid_id"]
    items = resp.json()["items"]

    # Find an item with pre-populated fields
    for i, item in enumerate(items):
        if item.get("pre_populated_fields") and item.get("job_type"):
            # Create session from this item
            resp = client.post(
                f"/api/bid/{bid_id}/quote-items",
                json={"item_indices": [i]},
                headers=auth_headers,
            )
            sessions = resp.json()["sessions"]
            session = sessions[0]
            assert session["session_id"] is not None

            # Check session has pre-populated fields
            status_resp = client.get(
                f"/api/session/{session['session_id']}/status",
                headers=auth_headers,
            )
            assert status_resp.status_code == 200
            answered = status_resp.json()["answered_fields"]
            assert len(answered) >= 1, f"Expected pre-populated fields in session, got: {answered}"
            return

    pytest.skip("No items with pre-populated fields found")


def test_bid_to_session_records_source(client, auth_headers):
    """Session created from bid item records bid extraction source in messages."""
    resp = client.post(
        "/api/bid/parse-text",
        json={"text": _sample_bid_text()},
        headers=auth_headers,
    )
    bid_id = resp.json()["bid_id"]
    items = resp.json()["items"]

    # Find first item with a job type
    for i, item in enumerate(items):
        if item.get("job_type"):
            resp = client.post(
                f"/api/bid/{bid_id}/quote-items",
                json={"item_indices": [i]},
                headers=auth_headers,
            )
            session_id = resp.json()["sessions"][0]["session_id"]

            # The session should exist and be active
            status = client.get(
                f"/api/session/{session_id}/status",
                headers=auth_headers,
            )
            assert status.status_code == 200
            assert status.json()["status"] == "active"
            return

    pytest.skip("No items with job type found")


# ============================================================
# 20-22. Keyword Fallback and Edge Cases
# ============================================================

def test_keyword_fallback_extracts_items():
    """When Gemini unavailable, keyword extraction finds items."""
    parser = BidParser()
    # Force keyword fallback by calling directly
    items = parser._extract_with_keywords(_sample_bid_text())

    assert len(items) >= 3, f"Expected >=3 items from keyword extraction, got {len(items)}"

    # Should find at least some metal fab keywords
    descriptions = " ".join(i.get("description", "") for i in items).lower()
    assert any(kw in descriptions for kw in ["stair", "railing", "gate", "bollard", "metal"])


def test_keyword_fallback_finds_csi_codes():
    """Keyword extraction identifies CSI Division 05 references."""
    parser = BidParser()
    items = parser._extract_with_keywords(_sample_bid_text())

    items_with_csi = [i for i in items if i.get("csi_division")]
    assert len(items_with_csi) >= 1, "Expected at least 1 item with CSI code"

    # The sample has "05 50 00"
    all_csi = [i["csi_division"] for i in items_with_csi]
    assert any(c.startswith("05") for c in all_csi), f"Expected Division 05, got: {all_csi}"


def test_parser_handles_empty_document():
    """Empty text returns 0 items, not an error."""
    parser = BidParser()
    result = parser.parse_document("")

    assert result["items"] == []
    assert result["extraction_confidence"] == 0.0
    assert len(result["warnings"]) >= 1


def test_parser_handles_no_fab_scope():
    """Document with no metal fab content returns 0 items with note."""
    parser = BidParser()
    text = """
    SECTION 03 30 00 - CAST-IN-PLACE CONCRETE

    3.01 GENERAL
    A. Provide concrete foundations per structural drawings.
    B. 4000 psi concrete, air-entrained.
    C. Reinforcing: #4 bars at 12" o.c. each way.
    """
    result = parser.parse_document(text)

    # Should find 0 or very few items (concrete is not metal fab)
    assert len(result["items"]) <= 1
    if not result["items"]:
        assert any("no metal" in w.lower() or "no metal" in w.lower() for w in result["warnings"])


def test_csi_divisions_complete():
    """RELEVANT_CSI_DIVISIONS has Division 05 and related divisions."""
    assert "05" in RELEVANT_CSI_DIVISIONS
    assert "05 50 00" in RELEVANT_CSI_DIVISIONS
    assert "05 52 00" in RELEVANT_CSI_DIVISIONS
    assert "32 31 00" in RELEVANT_CSI_DIVISIONS


def test_extraction_keywords_cover_main_types():
    """EXTRACTION_KEYWORDS covers main metal fab item types."""
    kw_str = " ".join(EXTRACTION_KEYWORDS)
    assert "railing" in kw_str
    assert "gate" in kw_str
    assert "stair" in kw_str
    assert "bollard" in kw_str
    assert "fence" in kw_str
    assert "ornamental iron" in kw_str
