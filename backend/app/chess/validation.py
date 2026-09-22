"""Wraps python-chess for legality/FEN/puzzle-move checking (spec §7F, §39).

UNTESTED: `pip install python-chess` failed in the build sandbox (package
allowlist proxy blocked it — confirmed directly, this isn't a guess). The
logic below is written against python-chess's well-documented, stable API
but has not been executed. Install the real package before trusting this.
"""
from __future__ import annotations
from dataclasses import dataclass

try:
    import chess
except ImportError:  # keeps the rest of the app importable without the dependency
    chess = None


@dataclass
class MoveCheckResult:
    correct: bool
    attempted_idea_note: str | None = None


def is_valid_fen(fen: str) -> bool:
    if chess is None:
        raise RuntimeError("python-chess not installed")
    try:
        chess.Board(fen)
        return True
    except ValueError:
        return False


def is_legal_move(fen: str, move_san: str) -> bool:
    if chess is None:
        raise RuntimeError("python-chess not installed")
    board = chess.Board(fen)
    try:
        board.parse_san(move_san)
        return True
    except ValueError:
        return False


def is_valid_movetext(text: str) -> bool:
    """Best-effort check that `text` is a legal sequence of moves from the
    starting position (book move-text rarely includes a FEN header, so this
    assumes a standard game start). Raises RuntimeError if python-chess isn't
    installed — callers must catch that and store the raw text unvalidated
    rather than silently claiming it was checked (see ingestion/pipeline.py
    _persist_games).
    """
    if chess is None:
        raise RuntimeError("python-chess not installed")
    board = chess.Board()
    # Strip move numbers like "12." before feeding to parse_san.
    tokens = [t for t in re_split_moves(text) if t]
    try:
        for tok in tokens:
            board.push_san(tok)
        return True
    except ValueError:
        return False


def re_split_moves(text: str) -> list[str]:
    import re
    # Drop move-number labels ("1.", "12...") and split on whitespace.
    no_numbers = re.sub(r"\d+\.(\.\.)?", " ", text)
    return no_numbers.split()


def check_move_against_solution(move_san: str, solution_line_san: list[str]) -> MoveCheckResult:
    """Compares only the first move of the solution line against the user's
    move — book puzzles often have multi-move solutions, but the interactive
    check is per-ply; the caller advances through solution_line_san move by
    move across successive submit_puzzle_move calls in a fuller
    implementation (not modeled here: this scaffold checks only the first
    ply, extend to a per-ply cursor stored on the Attempt/session).
    """
    if not solution_line_san:
        return MoveCheckResult(correct=False, attempted_idea_note=None)
    expected = solution_line_san[0]
    correct = _normalize_san(move_san) == _normalize_san(expected)
    return MoveCheckResult(
        correct=correct,
        attempted_idea_note=None if correct else "unclassified — needs board context to explain",
    )


def _normalize_san(san: str) -> str:
    return san.strip().rstrip("!?+#")
