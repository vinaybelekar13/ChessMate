import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.coach.local_coach import (
    teach_section_locally, explain_concept_locally, ask_book_locally, explain_mistake_locally,
)


def test_teach_section_locally_uses_real_source_text_verbatim():
    out = teach_section_locally("1.1 Weak squares", ["A weak square cannot be defended by a pawn."])
    assert "LOCAL GROUNDED MODE" in out
    assert "A weak square cannot be defended by a pawn." in out


def test_teach_section_locally_handles_no_source_text_honestly():
    out = teach_section_locally("Empty section", [])
    assert "No extracted source text" in out


def test_teach_section_locally_quick_depth_uses_only_first_block():
    out = teach_section_locally("Section", ["first block", "second block"], depth="quick")
    assert "first block" in out
    assert "second block" not in out


def test_explain_concept_locally_lists_retrieved_passages():
    out = explain_concept_locally("outposts", ["A knight on an outpost is very strong."])
    assert "outposts" in out
    assert "A knight on an outpost is very strong." in out


def test_ask_book_locally_reports_no_results_honestly():
    out = ask_book_locally("what about zugzwang?", [])
    assert "didn't return anything" in out


def test_explain_mistake_locally_uses_author_explanation_when_present():
    result = explain_mistake_locally("Qxd4", "The knight was actually undefended after ...Qxd4.")
    assert result["mode"] == "local_grounded"
    assert "undefended" in result["message"]


def test_explain_mistake_locally_is_honest_when_no_explanation_exists():
    result = explain_mistake_locally("Qxd4", None)
    assert "can't reason about" in result["message"]
