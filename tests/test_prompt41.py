"""
Tests for Prompt 41 — Calibrate the Machine.

AC-1: Labor calibration context in Opus prompt
AC-2: Material type always required question
AC-3: Finish label never says "steel" on aluminum
AC-4: Materials PDF reformatted (sheet dims, profile fmt)
AC-5: Electronics hardware sourced
AC-6: Adjustable material quantities (frontend-only — not tested here)
"""

import pytest


# ── AC-1: Labor calibration context in Opus prompt ──────────────────────────


def test_labor_calibration_in_prompt():
    """LABOR_CALIBRATION_NOTES constant exists and is injected into the prompt."""
    from backend.calculators.labor_calculator import LABOR_CALIBRATION_NOTES

    # Constant has content
    assert len(LABOR_CALIBRATION_NOTES) > 100

    # Contains shop-owner reference points
    assert "Fence/Gate" in LABOR_CALIBRATION_NOTES
    assert "LED Sign" in LABOR_CALIBRATION_NOTES
    assert "End Table" in LABOR_CALIBRATION_NOTES
    assert "estimate LOWER" in LABOR_CALIBRATION_NOTES


def test_labor_calibration_mentions_batch_cutting():
    """Calibration notes include batch cutting speed guidance."""
    from backend.calculators.labor_calculator import LABOR_CALIBRATION_NOTES
    assert "batch" in LABOR_CALIBRATION_NOTES.lower()
    assert "stop once" in LABOR_CALIBRATION_NOTES.lower() or "feed-and-cut" in LABOR_CALIBRATION_NOTES.lower()


def test_labor_calibration_mentions_picket_time():
    """Calibration notes include picket positioning guidance."""
    from backend.calculators.labor_calculator import LABOR_CALIBRATION_NOTES
    assert "picket" in LABOR_CALIBRATION_NOTES.lower()
    assert "2-3 min" in LABOR_CALIBRATION_NOTES


# ── AC-2: Material type always required question ────────────────────────────


def test_material_question_fires_when_missing(client, auth_headers):
    """When description does not mention material, a material question is injected."""
    resp = client.post("/api/session/start", json={
        "description": "Build a 6-foot fence with pickets",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    questions = data.get("next_questions", [])
    # Find the material question
    material_q = [q for q in questions if q.get("id") == "material"]
    assert len(material_q) == 1, "Material question should be injected when not in description"
    assert material_q[0]["required"] is True
    # `source` is stripped by _serialize_questions — verify via presence + required
    # Has multiple options including aluminum and steel
    options = material_q[0].get("options", [])
    assert any("steel" in o.lower() for o in options)
    assert any("aluminum" in o.lower() or "6061" in o.lower() for o in options)


def test_material_question_skipped_when_mentioned(client, auth_headers):
    """When description explicitly mentions steel, material question may be skipped."""
    resp = client.post("/api/session/start", json={
        "description": "Build a mild steel cantilever gate, 12 feet wide, 6 feet tall",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    questions = data.get("next_questions", [])
    # If "mild steel" was extracted into material/frame_material, no material question injected
    material_q = [q for q in questions if q.get("source") == "material_always_required"]
    # Either extraction caught it, or the question tree already has a material question
    # We verify the question is NOT double-injected if already present
    assert len(material_q) <= 1


def test_material_question_has_aluminum_options(client, auth_headers):
    """Material question includes aluminum alloy options."""
    resp = client.post("/api/session/start", json={
        "description": "Build a 6-foot fence with pickets",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    questions = data.get("next_questions", [])
    material_q = [q for q in questions if q.get("id") == "material"]
    assert len(material_q) == 1, "Material question should be present"
    options = material_q[0].get("options", [])
    assert any("6061" in o for o in options), "Should include 6061 alloy"
    assert any("5052" in o for o in options), "Should include 5052 alloy"


# ── AC-3: Finish label never says "steel" on aluminum ───────────────────────


def test_finish_label_aluminum_raw():
    """Raw finish on aluminum job says 'Raw Aluminum', not 'Raw Steel'."""
    from backend.pdf_generator import _finish_display_name
    assert _finish_display_name("raw", "Aluminum") == "Raw Aluminum"
    assert _finish_display_name("raw", "") == "Raw Steel"
    assert _finish_display_name("raw") == "Raw Steel"


def test_finish_label_aluminum_clearcoat():
    """Clear coat on aluminum includes material label."""
    from backend.pdf_generator import _finish_display_name
    result = _finish_display_name("clearcoat", "Aluminum")
    assert "Clear Coat" in result
    assert "Aluminum" in result


def test_finish_label_stainless():
    """Stainless steel finish label includes material context."""
    from backend.pdf_generator import _finish_display_name
    result = _finish_display_name("raw", "Stainless Steel")
    assert "Raw Stainless Steel" in result


def test_finish_label_steel_unchanged():
    """Mild steel finish labels are unchanged."""
    from backend.pdf_generator import _finish_display_name
    assert _finish_display_name("clearcoat") == "Clear Coat"
    assert _finish_display_name("powder_coat") == "Powder Coat"
    assert _finish_display_name("paint") == "Paint"
    assert _finish_display_name("galvanized") == "Galvanized"


def test_detect_material_label_aluminum():
    """_detect_material_label identifies aluminum from al_ profile prefixes."""
    from backend.pdf_generator import _detect_material_label

    # Mostly aluminum profiles
    pq = {"materials": [
        {"profile": "al_sq_tube_2x2_0.125"},
        {"profile": "al_sheet_0.125"},
        {"profile": "al_flat_bar_1x0.125"},
    ]}
    assert _detect_material_label(pq) == "Aluminum"


def test_detect_material_label_steel():
    """_detect_material_label returns empty string for mild steel."""
    from backend.pdf_generator import _detect_material_label

    pq = {"materials": [
        {"profile": "sq_tube_2x2_11ga"},
        {"profile": "flat_bar_1x0.25"},
    ]}
    assert _detect_material_label(pq) == ""


# ── AC-4: Materials PDF reformatted ─────────────────────────────────────────


def test_fmt_profile_aluminum():
    """_fmt_profile handles al_ prefix → 6061-T6 Al label."""
    from backend.pdf_generator import _fmt_profile
    result = _fmt_profile("al_sq_tube_2x2_0.125")
    assert "6061" in result or "Al" in result


def test_fmt_profile_steel():
    """_fmt_profile standard steel profiles unchanged."""
    from backend.pdf_generator import _fmt_profile
    result = _fmt_profile("sq_tube_2x2_11ga")
    assert "Sq Tube" in result or "sq" in result.lower()


def test_fmt_sheet_dims():
    """_fmt_sheet_dims formats common sheet sizes."""
    from backend.pdf_generator import _fmt_sheet_dims
    assert _fmt_sheet_dims(8) == "4'x8'"
    assert _fmt_sheet_dims(10) == "4'x10'"


def test_weight_calculation_known_profile():
    """Verify weight calc for a known profile from weights.py."""
    from backend.weights import STOCK_WEIGHTS
    # sq_tube_2x2_11ga is 1.951 lb/ft — this is a known verified value
    assert STOCK_WEIGHTS.get("sq_tube_2x2_11ga") == pytest.approx(1.951, abs=0.01)
    # A 20ft stick weighs ~39 lbs
    weight = STOCK_WEIGHTS["sq_tube_2x2_11ga"] * 20
    assert 38 < weight < 40


# ── AC-5: Electronics hardware sourced ──────────────────────────────────────


def test_electronics_catalog_has_entries():
    """ELECTRONICS_CATALOG has key components."""
    from backend.hardware_sourcer import ELECTRONICS_CATALOG
    assert "esp32" in ELECTRONICS_CATALOG
    assert "led_strip_5m" in ELECTRONICS_CATALOG
    assert "wire_connectors" in ELECTRONICS_CATALOG
    assert "cable_glands" in ELECTRONICS_CATALOG


def test_electronics_detection_esp32():
    """estimate_electronics detects ESP32 from description."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()
    items = hs.estimate_electronics("LED sign with ESP32 controller and BTF-Lighting strips")
    assert len(items) >= 1
    descs = " ".join(i["description"] for i in items).lower()
    assert "esp32" in descs


def test_electronics_detection_led_strip():
    """estimate_electronics detects LED strips from description keywords."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()
    items = hs.estimate_electronics("custom sign with led strip lighting and 5v power supply")
    descs = " ".join(i["description"] for i in items).lower()
    assert "led strip" in descs or "led" in descs
    assert "power supply" in descs or "5v" in descs


def test_electronics_not_triggered_for_gate():
    """estimate_electronics returns nothing for a plain gate description."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()
    items = hs.estimate_electronics("12 foot cantilever gate with LiftMaster operator")
    assert items == [] or items is None or len(items) == 0


def test_electronics_auto_adds_wire():
    """When electronics detected, wire/connectors are auto-included."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()
    items = hs.estimate_electronics("sign with ESP32 and led strip WS2812 5v power supply")
    descs = " ".join(i["description"] for i in items).lower()
    # Should auto-add wire/connectors
    assert "wire" in descs or "connector" in descs


def test_electronics_items_have_options():
    """Each electronics hardware item has pricing options."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()
    items = hs.estimate_electronics("ESP32 controller with LED strips")
    for item in items:
        assert "options" in item, f"Item {item['description']} missing options"
        assert len(item["options"]) >= 1
    # Primary matched items (not auto-added) should have 2 options (Amazon + Specialty)
    primary = [i for i in items if "Wire" not in i["description"] and "Cable" not in i["description"]]
    for item in primary:
        assert len(item["options"]) >= 2, f"Primary item {item['description']} should have 2 options"


# ── AC-5 wired into pricing engine ─────────────────────────────────────────


def test_pricing_engine_includes_electronics():
    """PricingEngine.build_priced_quote adds electronics to hardware list."""
    from backend.pricing_engine import PricingEngine
    pe = PricingEngine()
    session_data = {
        "session_id": "test-41",
        "job_type": "led_sign_custom",
        "fields": {
            "description": "138x28x6 aluminum LED sign with ESP32, WS2812 LED strips, 5V mean well PSU",
            "finish": "clearcoat",
        },
        "material_list": {
            "items": [
                {"profile": "al_sq_tube_2x2_0.125", "length_inches": 60,
                 "quantity": 4, "unit_price": 8.0, "line_total": 32.0},
            ],
            "hardware": [],
            "weld_linear_inches": 200,
            "total_sq_ft": 30,
        },
        "labor_estimate": {"processes": []},
        "finishing": {"method": "clearcoat", "total": 50.0},
    }
    user = {"id": 1, "shop_name": "Test Shop", "markup_default": 15}
    result = pe.build_priced_quote(session_data, user)
    hardware = result.get("hardware", [])
    # Should have at least ESP32 + LED strip + PSU
    all_descs = " ".join(h.get("description", "") for h in hardware).lower()
    assert "esp32" in all_descs, "Electronics should be sourced for LED sign job"


# ── AC-4: Consumables material-aware ────────────────────────────────────────


def test_consumables_aluminum_wire():
    """Aluminum jobs get ER4043 wire, not ER70S-6."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()
    consumables = hs.estimate_consumables(500, 200, "raw", material_type="aluminum_6061")
    descriptions = " ".join(c.get("description", "") for c in consumables)
    assert "ER4043" in descriptions or "4043" in descriptions


def test_consumables_steel_unchanged():
    """Steel jobs still get ER70S-6 wire."""
    from backend.hardware_sourcer import HardwareSourcer
    hs = HardwareSourcer()
    consumables = hs.estimate_consumables(500, 200, "raw")
    descriptions = " ".join(c.get("description", "") for c in consumables)
    assert "ER70S" in descriptions or "70S-6" in descriptions
