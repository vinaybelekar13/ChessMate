import chess
import pytest

from src.engine import stockfish as SF

pytestmark = pytest.mark.skipif(not SF.engine_available(), reason="Stockfish not installed")


@pytest.fixture(scope="module")
def eng():
    with SF.StockfishAnalyzer(depth=8, multipv=3) as e:
        yield e


def test_win_pct_and_value_mapping():
    assert SF.win_pct(0) == pytest.approx(50) and SF.win_pct(1000) > 95 and SF.win_pct(-1000) < 5
    assert SF.value_cp(None, 3) > 9900 and SF.value_cp(None, -3) < -9900 and SF.value_cp(35, None) == 35


def test_analysis_structure_and_labelling(eng):
    a = eng.analyze(chess.STARTING_FEN)
    assert a["kind"] == "engine_analysis" and len(a["lines"]) == 3 and a["best_move"]["uci"] == a["lines"][0]["move_uci"]
    b = chess.Board()
    for ln in a["lines"]:
        assert chess.Move.from_uci(ln["move_uci"]) in b.legal_moves and ln["score"]["perspective"] == "white"


def test_finds_mate_in_one(eng):
    a = eng.analyze("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
    assert a["best_move"]["uci"] == "a1a8" and a["evaluation"]["mate"] == 1


def test_finds_hanging_queen_capture(eng):
    a = eng.analyze("4k3/8/8/3q4/8/8/8/3RK3 w - - 0 1")
    assert a["best_move"]["uci"] == "d1d5" and a["evaluation"]["value_cp"] > 500


def test_deterministic_and_cached(eng):
    n = eng.calls
    a, b = eng.analyze("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"), eng.analyze("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    assert a is b and eng.calls == n + 1 and eng.cache_hits >= 1


def test_evaluate_move_uses_mover_perspective(eng):
    fen = "4k3/8/8/3q4/8/8/8/3RK3 w - - 0 1"
    good, bad = eng.evaluate_move(fen, "d1d5"), eng.evaluate_move(fen, "e1e2")
    assert good["score_for_mover"]["value_cp"] > bad["score_for_mover"]["value_cp"]
    assert good["score_for_mover"]["perspective"] == "white"
    mate = eng.evaluate_move("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1", "a1a8")
    assert mate["game_over"] and mate["score_for_mover"]["value_cp"] > 9000


def test_illegal_move_rejected_and_game_over_handled(eng):
    with pytest.raises(ValueError):
        eng.evaluate_move(chess.STARTING_FEN, "e2e5")
    a = eng.analyze("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert a["game_over"] and a["best_move"] is None


def test_missing_engine_path_fails_loudly(tmp_path):
    with pytest.raises(Exception):
        SF.StockfishAnalyzer(path=str(tmp_path / "nope"))


def test_unclosed_engine_does_not_block_interpreter_exit():
    """REGRESSION: python-chess's engine thread is non-daemon; a script that forgot close() hung forever."""
    import subprocess, sys
    code = ("import sys; sys.path.insert(0, '.')\nfrom src.engine.stockfish import StockfishAnalyzer\n"
            "e = StockfishAnalyzer(depth=4); e.analyze('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'); raise SystemExit(0)")
    r = subprocess.run([sys.executable, "-c", code], timeout=60, capture_output=True)
    assert r.returncode == 0
