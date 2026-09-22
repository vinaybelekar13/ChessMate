"""Exercises the "optional dependency missing" path via monkeypatching, so
this test's result doesn't depend on whether the machine running it happens
to have a Stockfish binary on PATH (the original version of this test
hardcoded that assumption, which broke as soon as Stockfish was installed
for the rest of this integrated build's own testing).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.chess import engine


def test_is_available_returns_false_when_no_stockfish_binary_present(monkeypatch):
    monkeypatch.setattr(engine, "_resolve_binary", lambda: None)
    assert engine.is_available() is False


def test_evaluate_fen_does_not_raise_and_is_labeled_unavailable(monkeypatch):
    monkeypatch.setattr(engine, "_resolve_binary", lambda: None)
    result = engine.evaluate_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    assert result["available"] is False
    assert "reason" in result
    # must never fabricate a score when unavailable
    assert "score_cp" not in result
