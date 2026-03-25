"""
P72 — Free Tier Output Fixes: Hardware Lines + Ballpark Total

Tests verify:
1. Ballpark range math: lower = round(total * 0.80 / 50) * 50,
                        upper = round(total * 1.25 / 50) * 50
2. Client PDF for free tier: generates without error, contains range text
3. Client PDF for paid tier: generates without error, contains exact total
4. PDF endpoint passes is_preview for free vs paid tier users
"""

import io
import pdfplumber
from backend.pdf_generator import generate_client_pdf, _fmt


def _extract_pdf_text(pdf_bytes):
    """Extract all text from PDF bytes using pdfplumber."""
    with pdfplumber.open(io.BytesIO(bytes(pdf_bytes))) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


# ── 1. Ballpark range math ──

def test_ballpark_range_math():
    """Verify the range formula: x0.80 rounded to $50, x1.25 rounded to $50."""
    total = 5000
    lower = round(total * 0.80 / 50) * 50
    upper = round(total * 1.25 / 50) * 50
    assert lower == 4000  # 5000 * 0.80 = 4000, /50 = 80, *50 = 4000
    assert upper == 6250  # 5000 * 1.25 = 6250, /50 = 125, *50 = 6250


def test_ballpark_range_rounds_to_50():
    """Verify rounding to nearest $50 for non-round totals."""
    total = 3777
    lower = round(total * 0.80 / 50) * 50
    upper = round(total * 1.25 / 50) * 50
    # 3777 * 0.80 = 3021.6, /50 = 60.432, round = 60, *50 = 3000
    assert lower == 3000
    # 3777 * 1.25 = 4721.25, /50 = 94.425, round = 94, *50 = 4700
    assert upper == 4700


# ── Helpers ──

def _make_priced_quote(total=5000):
    """Build a minimal priced_quote dict for PDF tests."""
    return {
        "job_type": "cantilever_gate",
        "job_description": "10 foot cantilever gate",
        "quote_number": "CQ-TEST-001",
        "material_subtotal": total * 0.4,
        "hardware_subtotal": total * 0.1,
        "consumable_subtotal": total * 0.05,
        "shop_stock_subtotal": 0,
        "labor_subtotal": total * 0.3,
        "finishing_subtotal": total * 0.15,
        "subtotal": total,
        "total": total,
        "selected_markup_pct": 0,
        "materials": [
            {"description": "2x2 sq tube 11ga", "qty": 3, "unit_cost": 40,
             "total": 120, "source": "seeded"},
        ],
        "hardware": [
            {"description": "Hinge", "qty": 2, "unit_cost": 15, "total": 30},
        ],
        "consumables": [],
        "labor": {"processes": [
            {"name": "cut_prep", "hours": 2.0, "rate": 85, "cost": 170},
        ]},
        "finishing": {"method": "powder_coat", "cost": total * 0.15},
        "assumptions": ["Standard installation"],
        "exclusions": ["Permits"],
    }


def _make_user_profile(is_preview=False):
    """Build a minimal user_profile dict."""
    return {
        "shop_name": "Test Fab Shop",
        "shop_address": "123 Main St",
        "shop_phone": "555-1234",
        "shop_email": "test@fab.com",
        "logo_url": None,
        "deposit_labor_pct": 50,
        "deposit_materials_pct": 100,
        "is_preview": is_preview,
    }


# ── 2. Client PDF for free tier — shows range, no category breakdowns ──

def test_client_pdf_free_tier_has_range():
    """Free tier client PDF contains ballpark range, not exact total."""
    total = 5000
    pq = _make_priced_quote(total=total)
    profile = _make_user_profile(is_preview=True)
    result = generate_client_pdf(pq, profile, {})
    assert isinstance(result, (bytes, bytearray))
    assert len(result) > 100

    text = _extract_pdf_text(result)
    assert "ESTIMATED PRICE RANGE" in text

    # Range values should be present
    lower = round(total * 0.80 / 50) * 50
    upper = round(total * 1.25 / 50) * 50
    assert _fmt(lower).replace("$", "") in text or str(lower) in text
    assert _fmt(upper).replace("$", "") in text or str(upper) in text


def test_client_pdf_free_tier_no_project_total():
    """Free tier client PDF must NOT contain 'PROJECT TOTAL' label."""
    pq = _make_priced_quote(total=5000)
    profile = _make_user_profile(is_preview=True)
    result = generate_client_pdf(pq, profile, {})
    text = _extract_pdf_text(result)
    assert "PROJECT TOTAL" not in text


def test_client_pdf_free_tier_no_category_breakdowns():
    """Free tier client PDF must NOT show Materials & Hardware / Labor / Finishing lines."""
    pq = _make_priced_quote(total=5000)
    profile = _make_user_profile(is_preview=True)
    result = generate_client_pdf(pq, profile, {})
    text = _extract_pdf_text(result)
    # The category breakdown labels should not appear
    assert "Materials & Hardware" not in text


# ── 3. Client PDF for paid tier — shows real total ──

def test_client_pdf_paid_tier_has_exact_total():
    """Paid tier client PDF contains PROJECT TOTAL with the real amount."""
    total = 5000
    pq = _make_priced_quote(total=total)
    profile = _make_user_profile(is_preview=False)
    result = generate_client_pdf(pq, profile, {})
    assert isinstance(result, (bytes, bytearray))

    text = _extract_pdf_text(result)
    assert "PROJECT TOTAL" in text
    assert "PRICE SUMMARY" in text


def test_client_pdf_paid_tier_has_category_breakdowns():
    """Paid tier client PDF shows Materials & Hardware, Labor, Finishing lines."""
    pq = _make_priced_quote(total=5000)
    profile = _make_user_profile(is_preview=False)
    result = generate_client_pdf(pq, profile, {})
    text = _extract_pdf_text(result)
    assert "Materials & Hardware" in text


# ── 4. PDF endpoint integration — is_preview flag ──

def _run_full_pipeline(client, headers):
    """Run the full sync pipeline and return quote_id."""
    resp = client.post("/api/session/start", json={
        "description": "10 foot cantilever gate, 6 feet tall, powder coat",
        "job_type": "cantilever_gate",
    }, headers=headers)
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
    client.post(f"/api/session/{session_id}/answer",
                json={"answers": answers}, headers=headers)
    client.post(f"/api/session/{session_id}/calculate", headers=headers)
    client.post(f"/api/session/{session_id}/estimate", headers=headers)
    price_resp = client.post(f"/api/session/{session_id}/price", headers=headers)
    assert price_resp.status_code == 200
    return price_resp.json()["quote_id"]


def test_pdf_endpoint_free_tier_preview(client, guest_headers):
    """Free tier user downloading client PDF gets preview mode (range)."""
    quote_id = _run_full_pipeline(client, guest_headers)

    token = guest_headers["Authorization"].replace("Bearer ", "")
    resp = client.get(
        f"/api/quotes/{quote_id}/pdf?mode=client&token={token}",
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"

    text = _extract_pdf_text(resp.content)
    assert "ESTIMATED PRICE RANGE" in text
    assert "PROJECT TOTAL" not in text


def test_pdf_endpoint_paid_tier_full(client, auth_headers):
    """Paid tier user downloading client PDF gets full pricing."""
    quote_id = _run_full_pipeline(client, auth_headers)

    token = auth_headers["Authorization"].replace("Bearer ", "")
    resp = client.get(
        f"/api/quotes/{quote_id}/pdf?mode=client&token={token}",
    )
    assert resp.status_code == 200

    text = _extract_pdf_text(resp.content)
    assert "PROJECT TOTAL" in text
    assert "PRICE SUMMARY" in text
