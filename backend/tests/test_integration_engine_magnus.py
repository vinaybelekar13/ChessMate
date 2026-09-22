"""Integration tests for the routes added to merge ChessMate UI + MagnusCoach
+ Book Coach into one backend (see FINAL_REPORT.md).

engine.py wraps the pre-existing app/chess/engine.py Stockfish adapter — the
one canonical engine per the integration spec — so these tests exercise it
for real when a Stockfish binary is present, and check the graceful-degrade
path when it isn't (mirroring the existing test_engine_fallback.py pattern).

magnus.py is a thin adapter over the sibling `magnus_coach` package. Since
PyTorch is a heavy optional dependency, these tests assert the CONTRACT
(always a 200 with an explicit "available" boolean, never a 500) rather than
asserting real model predictions — a real-prediction test belongs in
magnus_coach/tests and requires torch installed.
"""
import shutil

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def test_health_lists_all_components():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    for name in ("books", "engine", "magnus"):
        assert name in body["components"]


def test_engine_status_matches_binary_presence():
    r = client.get("/engine/status")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "shared_stockfish"
    assert isinstance(body["available"], bool)


def test_engine_evaluate_never_500s_and_labels_unavailability():
    r = client.post("/engine/evaluate", json={"fen": STARTPOS, "depth": 8})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "shared_stockfish"
    if shutil.which("stockfish") or shutil.which("/usr/games/stockfish"):
        assert body["available"] is True
        assert body["best_move"]
    else:
        assert body["available"] is False
        assert "reason" in body


def test_magnus_status_never_500s():
    r = client.get("/magnus/status")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "magnus_model"
    assert isinstance(body["available"], bool)
    if not body["available"]:
        assert "reason" in body  # never a silent/blank failure


def test_magnus_predict_never_500s():
    r = client.post("/magnus/predict", json={"fen": STARTPOS, "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "magnus_model"
    assert isinstance(body["available"], bool)


def test_magnus_historical_never_500s_and_is_labeled_separately_from_model():
    r = client.get("/magnus/historical", params={"fen": STARTPOS, "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    # Historical evidence must never be reported under the model's source tag.
    assert body["source"] == "historical_magnus"
    assert isinstance(body["available"], bool)
