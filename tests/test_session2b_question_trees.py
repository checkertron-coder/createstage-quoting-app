"""
Session 2B acceptance tests — 10 Priority B+C question trees.

Tests:
1.  test_all_10_trees_load                         — All 10 JSON files parse without error
2.  test_ornamental_fence_min_questions            — Count >= 14
3.  test_complete_stair_min_questions              — Count >= 14
4.  test_spiral_stair_min_questions                — Count >= 14
5.  test_window_security_grate_min_questions       — Count >= 10
6.  test_balcony_railing_min_questions             — Count >= 14
7.  test_furniture_table_min_questions             — Count >= 10
8.  test_utility_enclosure_min_questions           — Count >= 12
9.  test_bollard_min_questions                     — Count >= 8
10. test_repair_structural_min_questions           — Count >= 12
11. test_custom_fab_min_questions                  — Count >= 8
12. test_repair_structural_first_question_photo    — Photo-first
13. test_bollard_fixed_removable_branch            — Removable → sleeve_type
14. test_utility_enclosure_nema_branch             — Electrical → NEMA rating
15. test_furniture_stainless_branch                — Stainless → grade question
16. test_custom_fab_no_drawings_branch             — No drawings → design charge note
17. test_balcony_structural_branch                 — Structural frame → PE stamp
18. test_spiral_stair_stainless_branch             — Stainless → cost warning
19. test_all_10_valid_schema                       — JSON schema compliance for all 10
20. test_all_15_trees_in_engine                    — Engine lists all 15 job types
21. test_complete_stair_landing_trap_hint          — Landing count hint exists
22. test_window_grate_egress_branch                — Hinged → hinge_side + latch_type
"""

from backend.question_trees.engine import QuestionTreeEngine


engine = QuestionTreeEngine()

PRIORITY_B_TYPES = [
    "ornamental_fence",
    "complete_stair",
    "spiral_stair",
    "window_security_grate",
    "balcony_railing",
]

PRIORITY_C_TYPES = [
    "furniture_table",
    "utility_enclosure",
    "bollard",
    "repair_structural",
    "custom_fab",
]

ALL_SESSION_2B_TYPES = PRIORITY_B_TYPES + PRIORITY_C_TYPES

ALL_15_TYPES = [
    "cantilever_gate", "swing_gate", "straight_railing",
    "stair_railing", "repair_decorative",
] + ALL_SESSION_2B_TYPES


# --- Loading tests ---

def test_all_10_trees_load():
    """All 10 Priority B+C question tree JSON files parse without error."""
    for job_type in ALL_SESSION_2B_TYPES:
        tree = engine.load_tree(job_type)
        assert tree["job_type"] == job_type
        assert "questions" in tree
        assert "required_fields" in tree
        assert len(tree["questions"]) > 0


def test_all_15_trees_in_engine():
    """Engine lists all 15 job types from V2_JOB_TYPES."""
    available = engine.list_available_trees()
    for job_type in ALL_15_TYPES:
        assert job_type in available, f"{job_type} not found in available trees"


# --- Minimum question count tests ---

def test_ornamental_fence_min_questions():
    """ornamental_fence has at least 14 questions."""
    questions = engine.get_all_questions("ornamental_fence")
    assert len(questions) >= 14, f"Expected >= 14, got {len(questions)}"


def test_complete_stair_min_questions():
    """complete_stair has at least 14 questions."""
    questions = engine.get_all_questions("complete_stair")
    assert len(questions) >= 14, f"Expected >= 14, got {len(questions)}"


def test_spiral_stair_min_questions():
    """spiral_stair has at least 14 questions."""
    questions = engine.get_all_questions("spiral_stair")
    assert len(questions) >= 14, f"Expected >= 14, got {len(questions)}"


def test_window_security_grate_min_questions():
    """window_security_grate has at least 10 questions."""
    questions = engine.get_all_questions("window_security_grate")
    assert len(questions) >= 10, f"Expected >= 10, got {len(questions)}"


def test_balcony_railing_min_questions():
    """balcony_railing has at least 14 questions."""
    questions = engine.get_all_questions("balcony_railing")
    assert len(questions) >= 14, f"Expected >= 14, got {len(questions)}"


def test_furniture_table_min_questions():
    """furniture_table has at least 10 questions."""
    questions = engine.get_all_questions("furniture_table")
    assert len(questions) >= 10, f"Expected >= 10, got {len(questions)}"


def test_utility_enclosure_min_questions():
    """utility_enclosure has at least 12 questions."""
    questions = engine.get_all_questions("utility_enclosure")
    assert len(questions) >= 12, f"Expected >= 12, got {len(questions)}"


def test_bollard_min_questions():
    """bollard has at least 8 questions."""
    questions = engine.get_all_questions("bollard")
    assert len(questions) >= 8, f"Expected >= 8, got {len(questions)}"


def test_repair_structural_min_questions():
    """repair_structural has at least 12 questions."""
    questions = engine.get_all_questions("repair_structural")
    assert len(questions) >= 12, f"Expected >= 12, got {len(questions)}"


def test_custom_fab_min_questions():
    """custom_fab has at least 8 questions."""
    questions = engine.get_all_questions("custom_fab")
    assert len(questions) >= 8, f"Expected >= 8, got {len(questions)}"


# --- Photo-first tests ---

def test_repair_structural_first_question_photo():
    """repair_structural first question must be a photo upload (photo-first workflow)."""
    questions = engine.get_all_questions("repair_structural")
    assert questions[0]["type"] == "photo", \
        f"First question type is {questions[0]['type']}, expected 'photo'"
    assert questions[0]["required"] is True


# --- Branching logic tests ---

def test_bollard_fixed_removable_branch():
    """bollard: removable selection should show sleeve_type question."""
    answered = {"fixed_or_removable": "Removable — drop-in sleeve (can be pulled out)"}
    next_qs = engine.get_next_questions("bollard", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "sleeve_type" in next_ids, f"sleeve_type not in next questions: {next_ids}"


def test_utility_enclosure_nema_branch():
    """utility_enclosure: electrical enclosure should show NEMA rating question."""
    answered = {"enclosure_purpose": "Electrical panel / transformer enclosure"}
    next_qs = engine.get_next_questions("utility_enclosure", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "nema_rating" in next_ids, f"nema_rating not in next questions: {next_ids}"


def test_furniture_stainless_branch():
    """furniture_table: stainless material should show grade question."""
    answered = {"material": "Stainless steel"}
    next_qs = engine.get_next_questions("furniture_table", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "stainless_grade" in next_ids, f"stainless_grade not in next questions: {next_ids}"


def test_custom_fab_no_drawings_branch():
    """custom_fab: no drawings should show design charge note."""
    answered = {"has_drawings": "No — I need help with design"}
    next_qs = engine.get_next_questions("custom_fab", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "design_charge_note" in next_ids, \
        f"design_charge_note not in next questions: {next_ids}"


def test_balcony_structural_branch():
    """balcony_railing: structural frame scope should unlock PE stamp question."""
    answered = {"scope": "Structural frame + railing (full balcony fabrication)"}
    next_qs = engine.get_next_questions("balcony_railing", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "pe_stamp" in next_ids, f"pe_stamp not in next questions: {next_ids}"


def test_spiral_stair_stainless_branch():
    """spiral_stair: stainless steel should show cost warning note."""
    answered = {"material": "Stainless steel"}
    next_qs = engine.get_next_questions("spiral_stair", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "stainless_note" in next_ids, \
        f"stainless_note not in next questions: {next_ids}"


# --- Domain-specific content tests ---

def test_complete_stair_landing_trap_hint():
    """complete_stair landing_count question must have hint about underestimation."""
    questions = engine.get_all_questions("complete_stair")
    landing_q = next((q for q in questions if q["id"] == "landing_count"), None)
    assert landing_q is not None, "landing_count question not found"
    assert landing_q["hint"] is not None, "landing_count must have a hint"
    assert "landing" in landing_q["hint"].lower(), \
        "landing_count hint should mention landings"


def test_window_grate_egress_branch():
    """window_security_grate: hinged grate should show hinge_side and latch_type."""
    answered = {"fixed_or_hinged": "Hinged — swings open for cleaning/egress"}
    next_qs = engine.get_next_questions("window_security_grate", answered)
    next_ids = [q["id"] for q in next_qs]
    assert "hinge_side" in next_ids, f"hinge_side not in next questions: {next_ids}"
    assert "latch_type" in next_ids, f"latch_type not in next questions: {next_ids}"


# --- Schema validation for all 10 trees ---

def test_all_10_valid_schema():
    """All 10 question trees follow the required JSON schema."""
    valid_types = ("measurement", "choice", "multi_choice", "text", "photo", "number", "boolean")

    for job_type in ALL_SESSION_2B_TYPES:
        tree = engine.load_tree(job_type)
        assert "job_type" in tree, f"{job_type}: missing job_type"
        assert "version" in tree, f"{job_type}: missing version"
        assert "display_name" in tree, f"{job_type}: missing display_name"
        assert "required_fields" in tree, f"{job_type}: missing required_fields"
        assert "questions" in tree, f"{job_type}: missing questions"

        for q in tree["questions"]:
            assert "id" in q, f"Question missing 'id' in {job_type}"
            assert "text" in q, f"Question missing 'text' in {job_type}"
            assert "type" in q, f"Question missing 'type' in {job_type}"
            assert q["type"] in valid_types, \
                f"Invalid type '{q['type']}' for question {q['id']} in {job_type}"
            if q["type"] in ("choice", "multi_choice"):
                assert "options" in q and q["options"], \
                    f"Choice question {q['id']} in {job_type} has no options"

        # All required_fields must correspond to a question id
        question_ids = {q["id"] for q in tree["questions"]}
        for rf in tree["required_fields"]:
            assert rf in question_ids, \
                f"Required field '{rf}' has no matching question in {job_type}"


def test_all_10_have_category():
    """All 10 trees have a category field."""
    for job_type in ALL_SESSION_2B_TYPES:
        tree = engine.load_tree(job_type)
        assert "category" in tree, f"{job_type}: missing category"
        assert tree["category"] in ("architectural", "ornamental", "specialty"), \
            f"{job_type}: invalid category '{tree['category']}'"
