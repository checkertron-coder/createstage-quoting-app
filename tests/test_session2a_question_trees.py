"""
Session 2A acceptance tests — question trees, engine, session API.

Tests:
1.  test_all_5_trees_load                    — All 5 JSON files parse without error
2.  test_cantilever_gate_has_min_18_questions — Count >= 18
3.  test_swing_gate_has_min_16_questions      — Count >= 16
4.  test_straight_railing_has_min_14_questions — Count >= 14
5.  test_stair_railing_has_min_16_questions   — Count >= 16
6.  test_repair_first_question_is_photo       — repair_decorative[0].type == "photo"
7.  test_branching_logic_motor                — cantilever: has_motor=Yes → motor_brand in next
8.  test_no_duplicate_questions               — After answering, get_next_questions skips those fields
9.  test_is_complete_when_all_required_filled  — Fill all required → is_complete True
10. test_stair_railing_includes_rake_angle    — Has stair angle question
11. test_straight_railing_code_branching      — commercial → ada_required shown
12. test_session_api_start                    — POST /session/start creates session
13. test_session_api_answer_flow              — Submit answers → get next questions
14. test_list_available_trees                 — Engine lists all 5 trees
"""

import json
from backend.question_trees.engine import QuestionTreeEngine


engine = QuestionTreeEngine()

PRIORITY_A_TYPES = [
    "cantilever_gate",
    "swing_gate",
    "straight_railing",
    "stair_railing",
    "repair_decorative",
]


def test_all_5_trees_load():
    """All 5 Priority A question tree JSON files parse without error."""
    for job_type in PRIORITY_A_TYPES:
        tree = engine.load_tree(job_type)
        assert tree["job_type"] == job_type
        assert "questions" in tree
        assert "required_fields" in tree
        assert len(tree["questions"]) > 0


def test_list_available_trees():
    """Engine lists all 5 Priority A trees."""
    available = engine.list_available_trees()
    for job_type in PRIORITY_A_TYPES:
        assert job_type in available, f"{job_type} not found in available trees"


def test_cantilever_gate_has_min_18_questions():
    """cantilever_gate has at least 18 questions."""
    questions = engine.get_all_questions("cantilever_gate")
    assert len(questions) >= 18, f"Expected >= 18, got {len(questions)}"


def test_swing_gate_has_min_16_questions():
    """swing_gate has at least 16 questions."""
    questions = engine.get_all_questions("swing_gate")
    assert len(questions) >= 16, f"Expected >= 16, got {len(questions)}"


def test_straight_railing_has_min_14_questions():
    """straight_railing has at least 14 questions."""
    questions = engine.get_all_questions("straight_railing")
    assert len(questions) >= 14, f"Expected >= 14, got {len(questions)}"


def test_stair_railing_has_min_16_questions():
    """stair_railing has at least 16 questions."""
    questions = engine.get_all_questions("stair_railing")
    assert len(questions) >= 16, f"Expected >= 16, got {len(questions)}"


def test_repair_decorative_has_min_12_questions():
    """repair_decorative has at least 12 questions."""
    questions = engine.get_all_questions("repair_decorative")
    assert len(questions) >= 12, f"Expected >= 12, got {len(questions)}"


def test_repair_first_question_is_photo():
    """repair_decorative's first question must be a photo upload."""
    questions = engine.get_all_questions("repair_decorative")
    assert questions[0]["type"] == "photo", f"First question type is {questions[0]['type']}, expected 'photo'"
    assert questions[0]["required"] is True


def test_branching_logic_motor():
    """cantilever_gate: answering has_motor=Yes should show motor_brand next."""
    answered = {"has_motor": "Yes"}
    next_qs = engine.get_next_questions("cantilever_gate", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "motor_brand" in next_ids, f"motor_brand not in next questions: {next_ids}"


def test_branching_motor_no_hides_brand():
    """cantilever_gate: answering has_motor=No should NOT show motor_brand."""
    answered = {"has_motor": "No — manual operation"}
    next_qs = engine.get_next_questions("cantilever_gate", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "motor_brand" not in next_ids, "motor_brand should be hidden when motor=No"


def test_no_duplicate_questions():
    """After answering a field, it should not appear in get_next_questions."""
    answered = {"clear_width": "12", "height": "6"}
    next_qs = engine.get_next_questions("cantilever_gate", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "clear_width" not in next_ids
    assert "height" not in next_ids


def test_is_complete_when_all_required_filled():
    """Fill all required fields → is_complete returns True."""
    required = engine.get_required_fields("cantilever_gate")
    # Fill all required with dummy values
    answered = {field: "dummy_value" for field in required}
    assert engine.is_complete("cantilever_gate", answered)


def test_not_complete_when_missing_required():
    """Missing even one required field → is_complete returns False."""
    required = engine.get_required_fields("cantilever_gate")
    # Fill all but one
    answered = {field: "dummy_value" for field in required[:-1]}
    assert not engine.is_complete("cantilever_gate", answered)


def test_stair_railing_includes_rake_angle():
    """stair_railing must have a stair angle or rise/run question."""
    questions = engine.get_all_questions("stair_railing")
    ids = [q["id"] for q in questions]
    has_angle = "stair_angle" in ids or "rake_angle" in ids
    has_rise_run = "stair_rise" in ids and "stair_run" in ids
    assert has_angle or has_rise_run, f"No stair angle or rise/run questions found: {ids}"


def test_straight_railing_code_branching():
    """Commercial application should unlock ada_required question."""
    answered = {"application": "Commercial / public building"}
    next_qs = engine.get_next_questions("straight_railing", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "ada_required" in next_ids, f"ada_required not shown for commercial: {next_ids}"


def test_get_quote_params_contract():
    """get_quote_params returns dict matching QuoteParams contract."""
    answered = {"clear_width": "12", "height": "6"}
    params = engine.get_quote_params(
        "cantilever_gate", answered,
        user_id=1, session_id="test-session",
        photos=["photo1.jpg"], notes="test notes",
    )
    assert params["job_type"] == "cantilever_gate"
    assert params["user_id"] == 1
    assert params["session_id"] == "test-session"
    assert params["fields"] == answered
    assert params["photos"] == ["photo1.jpg"]
    assert params["notes"] == "test notes"


def test_completion_status_details():
    """get_completion_status returns detailed status dict."""
    required = engine.get_required_fields("swing_gate")
    answered = {required[0]: "value1", required[1]: "value2"}
    status = engine.get_completion_status("swing_gate", answered)
    assert status["required_total"] == len(required)
    assert status["required_answered"] == 2
    assert len(status["required_missing"]) == len(required) - 2
    assert not status["is_complete"]
    assert status["completion_pct"] > 0


def test_all_trees_have_valid_schema():
    """All question trees follow the required JSON schema."""
    for job_type in PRIORITY_A_TYPES:
        tree = engine.load_tree(job_type)
        assert "job_type" in tree
        assert "version" in tree
        assert "display_name" in tree
        assert "required_fields" in tree
        assert "questions" in tree

        for q in tree["questions"]:
            assert "id" in q, f"Question missing 'id' in {job_type}"
            assert "text" in q, f"Question missing 'text' in {job_type}"
            assert "type" in q, f"Question missing 'type' in {job_type}"
            assert q["type"] in ("measurement", "choice", "multi_choice", "text", "photo", "number", "boolean"), \
                f"Invalid type '{q['type']}' for question {q['id']} in {job_type}"
            if q["type"] == "choice":
                assert "options" in q and q["options"], \
                    f"Choice question {q['id']} in {job_type} has no options"

        # All required_fields must correspond to a question id
        question_ids = {q["id"] for q in tree["questions"]}
        for rf in tree["required_fields"]:
            assert rf in question_ids, \
                f"Required field '{rf}' has no matching question in {job_type}"


# --- Session API tests (require test client + DB) ---

def test_session_api_start(client, auth_headers):
    """POST /api/session/start creates a session and returns questions."""
    resp = client.post("/api/session/start", json={
        "description": "I need a 12-foot cantilever gate, 6 feet tall",
        "job_type": "cantilever_gate",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"]
    assert data["job_type"] == "cantilever_gate"
    assert data["tree_loaded"] is True
    assert len(data["next_questions"]) > 0
    assert "completion" in data


def test_session_api_answer_flow(client, auth_headers):
    """Submit answers via API, verify next questions update."""
    # Start session
    start_resp = client.post("/api/session/start", json={
        "description": "Swing gate for my driveway",
        "job_type": "swing_gate",
    }, headers=auth_headers)
    session_id = start_resp.json()["session_id"]

    # Answer some questions
    answer_resp = client.post(f"/api/session/{session_id}/answer", json={
        "answers": {
            "clear_width": "8",
            "height": "5",
            "panel_config": "Single panel (one leaf)",
        },
    }, headers=auth_headers)
    assert answer_resp.status_code == 200
    data = answer_resp.json()
    assert data["answered_count"] >= 3
    # Answered fields should not appear in next questions
    next_ids = [q["id"] for q in data["next_questions"]]
    assert "clear_width" not in next_ids
    assert "height" not in next_ids


def test_session_api_status(client, auth_headers):
    """GET /api/session/{id}/status returns current state."""
    # Start session
    start_resp = client.post("/api/session/start", json={
        "description": "Repair my old iron railing",
        "job_type": "repair_decorative",
    }, headers=auth_headers)
    session_id = start_resp.json()["session_id"]

    # Check status
    status_resp = client.get(f"/api/session/{session_id}/status", headers=auth_headers)
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["job_type"] == "repair_decorative"
    assert data["stage"] in ("intake", "clarify")
    assert "completion" in data
    assert "answered_fields" in data
