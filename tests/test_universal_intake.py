"""
Tests for Universal Intake System.

Covers:
- AC-1: Universal intake module generates questions from description
- AC-2: Fallback questions when AI unavailable (test environment)
- AC-3: /start endpoint uses universal intake (not trees)
- AC-4: /answer endpoint uses followup prompt (not tree branching)
- AC-5: /calculate accepts sessions without tree-based completion
- AC-6: Response shapes match frontend expectations
- AC-7: Known facts extraction and QA history accumulation
"""

import pytest


# =====================================================================
# AC-1 — Universal intake module
# =====================================================================

class TestUniversalIntakeModule:
    def test_generate_intake_questions_returns_dict(self):
        """generate_intake_questions returns proper structure."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("10 foot cantilever gate with motor")
        assert isinstance(result, dict)
        assert "known_facts" in result
        assert "questions" in result
        assert "readiness" in result
        assert "readiness_reason" in result

    def test_generate_intake_questions_extracts_material(self):
        """Fallback extracts material keyword from description."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("aluminum railing for deck")
        assert result["known_facts"].get("material") == "aluminum"

    def test_generate_intake_questions_extracts_finish(self):
        """Fallback extracts finish keyword from description."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("gate with powder coat black finish")
        assert result["known_facts"].get("finish") == "powder coat"

    def test_generate_intake_questions_steel_detection(self):
        """Fallback detects mild steel."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("mild steel table frame")
        assert result["known_facts"].get("material") == "mild steel"

    def test_generate_intake_questions_stainless_detection(self):
        """Fallback detects stainless steel."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("stainless handrail")
        assert result["known_facts"].get("material") == "stainless steel"

    def test_questions_have_valid_structure(self):
        """Each question has required fields."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("sign frame")
        for q in result["questions"]:
            assert "id" in q
            assert "text" in q
            assert "type" in q
            assert q["type"] in ("choice", "measurement", "text", "number")

    def test_readiness_is_needs_questions_without_ai(self):
        """Without AI, fallback readiness is needs_questions."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("whatever")
        assert result["readiness"] == "needs_questions"


# =====================================================================
# AC-2 — Fallback questions
# =====================================================================

class TestFallbackQuestions:
    def test_fallback_includes_material_question(self):
        """Fallback includes material question when not in description."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("need a gate")
        q_ids = [q["id"] for q in result["questions"]]
        assert "material" in q_ids

    def test_fallback_skips_material_when_detected(self):
        """Fallback skips material question when material is in description."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("aluminum fence panels")
        q_ids = [q["id"] for q in result["questions"]]
        assert "material" not in q_ids
        assert result["known_facts"]["material"] == "aluminum"

    def test_fallback_includes_finish_question(self):
        """Fallback includes finish question when not in description."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("need a gate")
        q_ids = [q["id"] for q in result["questions"]]
        assert "finish" in q_ids

    def test_fallback_skips_finish_when_detected(self):
        """Fallback skips finish question when finish is in description."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("gate galvanized")
        q_ids = [q["id"] for q in result["questions"]]
        assert "finish" not in q_ids
        assert result["known_facts"]["finish"] == "galvanized"

    def test_fallback_includes_dimensions_question(self):
        """Fallback always asks for dimensions."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("something")
        q_ids = [q["id"] for q in result["questions"]]
        assert "overall_dimensions" in q_ids

    def test_fallback_includes_installation_question(self):
        """Fallback asks about installation scope."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("something")
        q_ids = [q["id"] for q in result["questions"]]
        assert "installation" in q_ids

    def test_fallback_includes_electronics_for_led(self):
        """Fallback adds electronics question for LED descriptions."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("LED channel letter sign")
        q_ids = [q["id"] for q in result["questions"]]
        assert "electronics_spec" in q_ids

    def test_fallback_no_electronics_for_gate(self):
        """Fallback does NOT add electronics for non-LED descriptions."""
        from backend.question_trees.universal_intake import generate_intake_questions
        result = generate_intake_questions("steel swing gate")
        q_ids = [q["id"] for q in result["questions"]]
        assert "electronics_spec" not in q_ids


# =====================================================================
# AC-3 — /start endpoint uses universal intake
# =====================================================================

class TestStartEndpointUniversalIntake:
    def test_start_returns_session_id(self, client, guest_headers):
        """POST /start returns session_id."""
        resp = client.post("/api/session/start", json={
            "description": "10 foot cantilever gate",
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["session_id"]

    def test_start_returns_job_type(self, client, guest_headers):
        """POST /start detects job type from description."""
        resp = client.post("/api/session/start", json={
            "description": "10 foot cantilever gate with motor",
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_type"] == "cantilever_gate"

    def test_start_returns_questions(self, client, guest_headers):
        """POST /start returns AI-generated questions."""
        resp = client.post("/api/session/start", json={
            "description": "need a railing",
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "next_questions" in data
        assert len(data["next_questions"]) > 0

    def test_start_returns_extracted_fields(self, client, guest_headers):
        """POST /start extracts known facts from description."""
        resp = client.post("/api/session/start", json={
            "description": "aluminum railing with powder coat",
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "extracted_fields" in data
        # Fallback should extract material and finish
        assert data["extracted_fields"].get("material") == "aluminum"
        assert data["extracted_fields"].get("finish") == "powder coat"

    def test_start_returns_completion(self, client, guest_headers):
        """POST /start returns completion status."""
        resp = client.post("/api/session/start", json={
            "description": "need a fence",
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "completion" in data
        completion = data["completion"]
        assert "is_complete" in completion
        assert "required_total" in completion
        assert "required_answered" in completion
        assert "completion_pct" in completion

    def test_start_tree_loaded_always_true(self, client, guest_headers):
        """tree_loaded is always True with universal intake."""
        resp = client.post("/api/session/start", json={
            "description": "something unusual",
        }, headers=guest_headers)
        assert resp.status_code == 200
        assert resp.json()["tree_loaded"] is True

    def test_start_with_explicit_job_type(self, client, guest_headers):
        """POST /start with explicit job_type uses it."""
        resp = client.post("/api/session/start", json={
            "description": "custom project",
            "job_type": "furniture_table",
        }, headers=guest_headers)
        assert resp.status_code == 200
        assert resp.json()["job_type"] == "furniture_table"
        assert resp.json()["detection_confidence"] == 1.0

    def test_start_stores_known_facts_in_params(self, client, guest_headers, db):
        """Session params_json stores _known_facts for followup."""
        from backend.models import QuoteSession
        resp = client.post("/api/session/start", json={
            "description": "aluminum table frame",
        }, headers=guest_headers)
        session_id = resp.json()["session_id"]
        session = db.query(QuoteSession).filter(
            QuoteSession.id == session_id).first()
        assert session is not None
        params = session.params_json
        assert "_known_facts" in params
        assert "_qa_history" in params
        assert "_readiness" in params
        assert params["_known_facts"].get("material") == "aluminum"


# =====================================================================
# AC-4 — /answer endpoint uses followup
# =====================================================================

class TestAnswerEndpointUniversalIntake:
    def _start_session(self, client, guest_headers, description="need a gate"):
        resp = client.post("/api/session/start", json={
            "description": description,
        }, headers=guest_headers)
        return resp.json()["session_id"]

    def test_answer_returns_completion(self, client, guest_headers):
        """POST /answer returns completion status."""
        sid = self._start_session(client, guest_headers)
        resp = client.post(f"/api/session/{sid}/answer", json={
            "answers": {"material": "Mild steel"},
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "completion" in data
        assert "is_complete" in data

    def test_answer_accumulates_known_facts(self, client, guest_headers, db):
        """Answers merge into _known_facts in params_json."""
        from backend.models import QuoteSession
        sid = self._start_session(client, guest_headers)
        client.post(f"/api/session/{sid}/answer", json={
            "answers": {"material": "Mild steel", "height": "6"},
        }, headers=guest_headers)
        session = db.query(QuoteSession).filter(
            QuoteSession.id == sid).first()
        known = session.params_json.get("_known_facts", {})
        assert known.get("material") == "Mild steel"
        assert known.get("height") == "6"

    def test_answer_builds_qa_history(self, client, guest_headers, db):
        """Answers are recorded in _qa_history."""
        from backend.models import QuoteSession
        sid = self._start_session(client, guest_headers)
        client.post(f"/api/session/{sid}/answer", json={
            "answers": {"material": "Mild steel"},
        }, headers=guest_headers)
        session = db.query(QuoteSession).filter(
            QuoteSession.id == sid).first()
        qa = session.params_json.get("_qa_history", [])
        assert len(qa) >= 1
        assert qa[0]["answer"] == "Mild steel"

    def test_answer_returns_next_questions(self, client, guest_headers):
        """POST /answer returns next_questions array."""
        sid = self._start_session(client, guest_headers)
        resp = client.post(f"/api/session/{sid}/answer", json={
            "answers": {"material": "Mild steel"},
        }, headers=guest_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "next_questions" in data
        assert isinstance(data["next_questions"], list)


# =====================================================================
# AC-5 — /calculate works with universal intake
# =====================================================================

class TestCalculateWithUniversalIntake:
    def test_calculate_succeeds_after_answers(self, client, guest_headers):
        """Calculate proceeds when answers have been provided."""
        resp = client.post("/api/session/start", json={
            "description": "10 foot swing gate, mild steel, powder coat black",
            "job_type": "swing_gate",
        }, headers=guest_headers)
        sid = resp.json()["session_id"]

        # Answer some questions
        client.post(f"/api/session/{sid}/answer", json={
            "answers": {
                "clear_width": "10",
                "height": "6",
                "material": "Mild steel",
                "finish": "Powder coat",
            },
        }, headers=guest_headers)

        calc = client.post(f"/api/session/{sid}/calculate",
                           headers=guest_headers)
        assert calc.status_code == 200
        data = calc.json()
        assert "material_list" in data

    def test_calculate_stores_material_list(self, client, guest_headers, db):
        """Calculate stores _material_list in session params."""
        from backend.models import QuoteSession
        resp = client.post("/api/session/start", json={
            "description": "steel bollard 4 feet tall",
            "job_type": "bollard",
        }, headers=guest_headers)
        sid = resp.json()["session_id"]
        client.post(f"/api/session/{sid}/answer", json={
            "answers": {"height": "4", "finish": "raw"},
        }, headers=guest_headers)
        client.post(f"/api/session/{sid}/calculate",
                    headers=guest_headers)
        session = db.query(QuoteSession).filter(
            QuoteSession.id == sid).first()
        assert "_material_list" in session.params_json


# =====================================================================
# AC-6 — Response shapes match frontend
# =====================================================================

class TestResponseShapes:
    def test_start_response_has_all_fields(self, client, guest_headers):
        """POST /start response has all fields the frontend expects."""
        resp = client.post("/api/session/start", json={
            "description": "need a table",
        }, headers=guest_headers)
        data = resp.json()
        expected_keys = {
            "session_id", "job_type", "detection_confidence", "ambiguous",
            "tree_loaded", "extracted_fields", "photo_extracted_fields",
            "photo_observations", "next_questions", "completion",
        }
        assert expected_keys.issubset(set(data.keys())), \
            "Missing keys: %s" % (expected_keys - set(data.keys()))

    def test_question_shape_matches_frontend(self, client, guest_headers):
        """Questions have id, text, type — frontend rendering fields."""
        resp = client.post("/api/session/start", json={
            "description": "something",
        }, headers=guest_headers)
        questions = resp.json()["next_questions"]
        for q in questions:
            assert "id" in q
            assert "text" in q
            assert "type" in q

    def test_completion_shape_matches_frontend(self, client, guest_headers):
        """Completion has is_complete, required_total, etc."""
        resp = client.post("/api/session/start", json={
            "description": "something",
        }, headers=guest_headers)
        comp = resp.json()["completion"]
        assert "is_complete" in comp
        assert "required_total" in comp
        assert "required_answered" in comp
        assert "completion_pct" in comp

    def test_answer_response_has_all_fields(self, client, guest_headers):
        """POST /answer response has all fields the frontend expects."""
        resp = client.post("/api/session/start", json={
            "description": "gate",
        }, headers=guest_headers)
        sid = resp.json()["session_id"]
        ans = client.post(f"/api/session/{sid}/answer", json={
            "answers": {"material": "Mild steel"},
        }, headers=guest_headers)
        data = ans.json()
        expected_keys = {
            "session_id", "answered_count", "required_total",
            "next_questions", "is_complete", "completion",
        }
        assert expected_keys.issubset(set(data.keys())), \
            "Missing keys: %s" % (expected_keys - set(data.keys()))


# =====================================================================
# AC-7 — Helpers
# =====================================================================

class TestHelperFunctions:
    def test_build_completion_ready(self):
        """readiness=ready produces is_complete=True."""
        from backend.question_trees.universal_intake import (
            build_completion_from_readiness,
        )
        comp = build_completion_from_readiness(
            "ready", {"a": "1", "b": "2"}, []
        )
        assert comp["is_complete"] is True
        assert comp["completion_pct"] == 100.0

    def test_build_completion_needs_questions(self):
        """readiness=needs_questions produces is_complete=False."""
        from backend.question_trees.universal_intake import (
            build_completion_from_readiness,
        )
        qs = [{"id": "q1", "text": "?", "type": "text", "required": True}]
        comp = build_completion_from_readiness(
            "needs_questions", {"a": "1"}, qs
        )
        assert comp["is_complete"] is False
        assert comp["completion_pct"] == 50.0

    def test_build_extracted_fields_filters_internal(self):
        """build_extracted_fields_from_known strips _ prefixed keys."""
        from backend.question_trees.universal_intake import (
            build_extracted_fields_from_known,
        )
        result = build_extracted_fields_from_known({
            "material": "steel",
            "_readiness": "ready",
            "_internal": True,
        })
        assert "material" in result
        assert "_readiness" not in result
        assert "_internal" not in result

    def test_validate_questions_deduplicates_ids(self):
        """_validate_questions ensures unique IDs."""
        from backend.question_trees.universal_intake import _validate_questions
        qs = [
            {"id": "q1", "text": "First?", "type": "text"},
            {"id": "q1", "text": "Second?", "type": "text"},
        ]
        result = _validate_questions(qs)
        ids = [q["id"] for q in result]
        assert len(ids) == len(set(ids))

    def test_validate_questions_drops_invalid(self):
        """_validate_questions drops questions without text or type."""
        from backend.question_trees.universal_intake import _validate_questions
        qs = [
            {"id": "good", "text": "Valid?", "type": "text"},
            {"id": "bad1", "text": "", "type": "text"},
            {"id": "bad2", "text": "No type"},
            "not a dict",
        ]
        result = _validate_questions(qs)
        assert len(result) == 1
        assert result[0]["id"] == "good"

    def test_parse_ai_response_handles_markdown(self):
        """_parse_ai_response strips markdown code fences."""
        from backend.question_trees.universal_intake import _parse_ai_response
        text = '```json\n{"known_facts": {}, "questions": []}\n```'
        result = _parse_ai_response(text)
        assert result is not None
        assert result["known_facts"] == {}

    def test_parse_ai_response_handles_plain_json(self):
        """_parse_ai_response handles plain JSON."""
        from backend.question_trees.universal_intake import _parse_ai_response
        text = '{"known_facts": {"x": "1"}, "questions": []}'
        result = _parse_ai_response(text)
        assert result["known_facts"]["x"] == "1"

    def test_parse_ai_response_returns_none_on_invalid(self):
        """_parse_ai_response returns None for invalid JSON."""
        from backend.question_trees.universal_intake import _parse_ai_response
        result = _parse_ai_response("not json at all")
        assert result is None
