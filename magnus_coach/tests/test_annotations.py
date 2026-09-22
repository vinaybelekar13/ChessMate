import chess
import pytest

from src.chess_core import tactics as T
from src.coach import annotations as A

START = chess.STARTING_FEN


def test_valid_arrow_and_highlight_roundtrip():
    a = A.arrow("e2", "e4", "best-move", START, "engine", "why")
    h = A.highlight("e5", "threat", START, "board")
    assert A.validate_annotations([a, h])["valid"]
    import json
    assert json.loads(json.dumps(a)) == a


@pytest.mark.parametrize("bad", [
    lambda: A.arrow("e2", "e9", "best-move", START, "engine"),
    lambda: A.arrow("e2", "e4", "nonsense", START, "engine"),
    lambda: A.arrow("e2", "e4", "best-move", START, "oracle"),
    lambda: A.highlight("z1", "threat", START, "board"),
    lambda: A.arrow("e2", "e4", "best-move", "bad fen", "engine"),
])
def test_construction_rejects_invalid_input(bad):
    with pytest.raises(ValueError):
        bad()


def test_move_arrows_must_be_legal_in_their_position():
    assert A.problems({"type": "arrow", "from": "e2", "to": "e5", "category": "user-move", "fen": START, "source": "user", "reason": ""})
    assert A.problems({"type": "arrow", "from": "e7", "to": "e5", "category": "best-move", "fen": START, "source": "engine", "reason": ""})  # black piece, white to move
    assert not A.problems(A.arrow("g1", "f3", "best-move", START, "engine"))


def test_capture_arrow_needs_enemy_piece():
    fen = "4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1"
    assert not A.problems(A.arrow("d1", "d5", "capture", fen, "board"))
    assert A.problems(A.arrow("d1", "d4", "capture", fen, "board"))          # empty square


def test_threat_arrow_must_follow_attack_geometry():
    fen = "4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1"
    assert not A.problems(A.arrow("d1", "d5", "threat", fen, "board"))
    assert A.problems(A.arrow("d1", "h5", "threat", fen, "board"))            # rook cannot reach h5
    assert A.problems(A.arrow("a1", "a2", "threat", fen, "board"))            # empty start square


def test_target_highlight_needs_a_piece():
    assert A.problems(A.highlight("e4", "target", START, "board"))
    assert not A.problems(A.highlight("e2", "target", START, "board"))


def test_from_tactic_produces_valid_annotations():
    fen = "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1"
    forks = [t for t in T.opportunities(chess.Board(fen)) if t["motif"] == "fork"]
    ann = A.from_tactic(forks[0], fen)
    assert A.validate_annotations(ann)["valid"] and {a["category"] for a in ann} >= {"threat", "target"}


def test_dedupe():
    a = A.highlight("e2", "target", START, "board")
    assert len(A.dedupe([a, dict(a), A.highlight("e2", "threat", START, "board")])) == 2
