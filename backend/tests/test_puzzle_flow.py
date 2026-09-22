"""Pure-Python tests for puzzle detection + move checking — no DB, no chess lib
required for the move-checking string-comparison test (python-chess-backed
legality checks are NOT covered here since python-chess isn't installed).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ingestion.mineru_adapter import RawBlock
from app.ingestion.chess_extractor import find_puzzle_candidates, find_move_text_blocks
from app.chess.validation import check_move_against_solution


def test_find_puzzle_candidates_matches_known_prompts():
    blocks = [
        RawBlock(10, "paragraph", "White to move. Find the winning continuation.", None, 0),
        RawBlock(10, "paragraph", "This is just ordinary explanatory prose.", None, 1),
        RawBlock(11, "caption", "Exercise 3", None, 0),
    ]
    candidates = find_puzzle_candidates(blocks)
    assert len(candidates) == 2
    assert candidates[0].block.page_number == 10
    assert candidates[1].block.text == "Exercise 3"


def test_find_move_text_blocks_requires_multiple_moves():
    blocks = [
        RawBlock(1, "paragraph", "1.e4 e5 2.Nf3 Nc6 3.Bb5 a6", None, 0),
        RawBlock(1, "paragraph", "A single reference like 1.e4 isn't a game.", None, 1),
    ]
    move_blocks = find_move_text_blocks(blocks)
    assert len(move_blocks) == 1
    assert move_blocks[0].order_index == 0


def test_check_move_against_solution_correct():
    result = check_move_against_solution("Nf5", ["Nf5", "Kg8", "Qh5#"])
    assert result.correct is True


def test_check_move_against_solution_incorrect():
    result = check_move_against_solution("Qxd4", ["Nf5", "Kg8", "Qh5#"])
    assert result.correct is False
    assert result.attempted_idea_note is not None


def test_check_move_against_solution_ignores_check_and_mate_symbols():
    result = check_move_against_solution("Qh5", ["Qh5#"])
    assert result.correct is True
