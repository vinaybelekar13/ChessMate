import json
import random
import re
from pathlib import Path

import chess
import pytest

import src.api as api
from src.coach import llm as L
from src.coach import annotations as A
from src.coach.orchestrator import ChessMateCoach
from src.coach.player import JsonPlayerStore
from src.coach.services import Services
from src.engine.stockfish import engine_available
from src.history.database import DEFAULT_DB, MagnusDB
from src.inference import api as inf
from src.model.checkpoint import load_checkpoint

ROOT = Path(__file__).resolve().parents[1]
MODEL_OK = inf.DEFAULT_MODEL.exists()
FULL = engine_available() and DEFAULT_DB.exists() and MODEL_OK
needs_model = pytest.mark.skipif(not MODEL_OK, reason="final model not present")
needs_all = pytest.mark.skipif(not FULL, reason="needs Stockfish, database and model")
NXE5 = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
STALEMATE = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
CHECKMATE = "R5k1/5ppp/8/8/8/8/8/6K1 b - - 0 1"


def random_fens(n, seed=11):
    rng, out = random.Random(seed), []
    while len(out) < n:
        b = chess.Board()
        for _ in range(rng.randint(2, 120)):
            ms = list(b.legal_moves)
            if not ms:
                break
            b.push(rng.choice(ms))
        if any(b.legal_moves):
            out.append(b.fen())
    return out


# ---------------------------------------------------------------- illegal-move prevention
@needs_model
def test_predictions_are_always_legal_across_random_positions_including_checks():
    checks = 0
    for fen in random_fens(120):
        b = chess.Board(fen)
        allm = inf.predict_moves(fen, top_k=1000)
        legal = {m.uci() for m in b.legal_moves}
        assert {m["uci"] for m in allm} == legal and all(m["legal"] for m in allm)
        assert abs(sum(m["probability"] for m in allm) - 1.0) < 1e-4
        assert [m["rank"] for m in allm] == list(range(1, len(allm) + 1))
        checks += b.is_check()
    assert checks > 0                                                      # the sample really contained checks


@needs_model
@pytest.mark.parametrize("fen", [STALEMATE, CHECKMATE])
def test_no_prediction_in_finished_games(fen):
    with pytest.raises(ValueError):
        inf.predict_moves(fen)


@needs_model
@pytest.mark.parametrize("fen", ["not a fen", "", "8/8/8/8/8/8/8/8 w - - 0 1x"])
def test_invalid_fen_raises_not_guesses(fen):
    with pytest.raises(ValueError):
        inf.predict_moves(fen)


@needs_model
def test_special_moves_are_scored_and_legal():
    promo = inf.predict_moves("1n5k/P7/8/8/8/8/8/K7 w - - 0 1", top_k=100)
    assert {"a7a8q", "a7a8n", "a7b8q", "a7b8n"} <= {m["uci"] for m in promo}
    ep = inf.predict_moves("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3", top_k=100)
    assert "e5f6" in {m["uci"] for m in ep}
    castle = inf.predict_moves("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", top_k=100)
    assert {"e1g1", "e1c1"} <= {m["uci"] for m in castle}
    evasion = inf.predict_moves("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1", top_k=100)           # king in check: only evasions
    assert {m["uci"] for m in evasion} == {m.uci() for m in chess.Board("4k3/8/8/8/8/8/4r3/4K3 w - - 0 1").legal_moves}


# ---------------------------------------------------------------- determinism / checkpoints
@needs_model
def test_inference_is_deterministic_and_independent_of_call_history():
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
    a = inf.predict_moves(fen, 5)
    inf.predict_moves(chess.STARTING_FEN, 3)
    inf.predict_moves(NXE5, 3, time_control="60+0")
    assert a == inf.predict_moves(fen, 5)


@needs_model
def test_final_checkpoint_reloads_and_matches_cached_model():
    model, meta = load_checkpoint(inf.DEFAULT_MODEL)
    cached, _ = inf.load_magnus_model()
    assert meta["trained_steps"] > 0 and not meta.get("smoke") and model.parameter_count() == cached.parameter_count() == 448771
    import torch
    for (k1, v1), (k2, v2) in zip(model.state_dict().items(), cached.state_dict().items()):
        assert k1 == k2 and torch.equal(v1, v2)


@needs_model
def test_time_control_is_used_by_the_deployed_model():
    a = inf.predict_moves(NXE5, 20, time_control="15+0")
    b = inf.predict_moves(NXE5, 20, time_control="1800+0")
    assert [m["score"] for m in a] != [m["score"] for m in b]


# ---------------------------------------------------------------- test set never used for selection
def test_trainer_never_reads_test_data_except_for_the_leakage_id_check():
    src = (ROOT / "src" / "model" / "train.py").read_text()
    uses = [l.strip() for l in src.splitlines() if "test_path" in l]
    assert all(("paths[" in l or "cfg.test_path" in l and "paths" in l or "test_path:" in l or "test_path" in l and "--test" in l
                or "dest=\"test_path\"" in l or "if cfg.test_path" in l) for l in uses), uses
    assert "PositionDataset(cfg.test_path" not in src and "evaluate(model, test" not in src


def test_evaluation_reports_test_only_and_tuned_on_validation():
    rep = json.loads((ROOT / "outputs" / "test_evaluation.json").read_text())
    base = json.loads((ROOT / "outputs" / "baselines.json").read_text())
    assert rep["used_for_selection"] is False and "VALIDATION" in base["tuning_data"]
    hist = json.loads((ROOT / "outputs" / "runs" / "stage3_full_epoch" / "training_history.json").read_text())
    assert hist["best"]["tag"].startswith("epoch") and hist["best"]["n"] == hist["epochs"][-1]["val_headline"]["n"]   # chosen on validation


@pytest.mark.skipif(not (ROOT / "data/splits/train.jsonl").exists(), reason="dataset not built")
def test_no_game_leakage_in_real_splits():
    from src.model.dataset import assert_no_game_overlap
    c = assert_no_game_overlap({s: ROOT / f"data/splits/{s}.jsonl" for s in ("train", "validation", "test")})
    assert c == {"train": 13015, "validation": 1665, "test": 1588}


# ---------------------------------------------------------------- orchestrator + API
class Liar(L.LLMProvider):
    name = "liar"
    def generate(self, system, payload):
        return "Magnus played Qh8 and it is mate in 7 with +999 centipawns."


@pytest.fixture(scope="module")
def coach(tmp_path_factory):
    c = ChessMateCoach(Services(engine_depth=8), JsonPlayerStore(tmp_path_factory.mktemp("players")))
    yield c
    c.close()


@needs_all
def test_orchestrator_keeps_sources_separate_and_is_json(coach):
    r = coach.review_move(NXE5, "Nxe5", player_id="u1", game_id="G", ply=5)
    assert r["separation"] == ["engine_truth", "magnus_model", "historical_evidence", "player_history", "knowledge", "coach_interpretation"]
    assert r["engine_truth"]["kind"] == "engine_analysis" and r["magnus_model"]["kind"] == "model_prediction"
    assert r["historical_evidence"]["kind"] == "historical_fact" and r["coach_interpretation"]["grounding"]["grounded"]
    assert r["player_history"]["new_training_items"] and r["knowledge"][0]["provenance"]["type"]
    json.dumps(r)


@needs_all
def test_hallucinating_llm_cannot_reach_the_user(coach):
    c = ChessMateCoach(coach.services, coach.store, llm=L.CoachLLM(Liar()))
    r = c.review_move(NXE5, "Nxe5", record=False)
    ci = r["coach_interpretation"]
    assert ci["fallback_used"] and "Qh8" not in ci["text"] and "999" not in ci["text"] and ci["grounding"]["grounded"]


@needs_all
def test_hint_only_session_via_router_never_reveals(coach):
    s = coach.route({"task": "socratic_start", "fen": NXE5, "move": "Nxe5", "hint_only": True})
    seen = [s] + [coach.route({"task": "socratic_next", "session_id": s["session_id"]}) for _ in range(5)]
    best = coach.services.engine.analyze(NXE5)["best_move"]["san"]
    assert not any(best in (h.get("text") or "") for h in seen) and any(h.get("refused") for h in seen)


@needs_all
def test_router_reports_errors_as_data(coach):
    assert coach.route({"task": "review_move", "fen": NXE5, "move": "Ke5"})["kind"] == "error"
    assert coach.route({"task": "nope"})["kind"] == "error"
    assert coach.route({"task": "analyze_position"})["kind"] == "error"                # missing fen


@needs_all
def test_analysis_degrades_gracefully_when_engine_missing(monkeypatch):
    import src.coach.services as S
    monkeypatch.setattr(S, "engine_available", lambda: False)
    c = ChessMateCoach(Services(engine_depth=8))
    r = c.analyze_position(NXE5)
    assert r["engine_truth"]["error"] == "engine_unavailable" and r["magnus_model"]["moves"] and r["historical_evidence"]["examples"]


@needs_all
def test_analyze_position_in_finished_game_is_handled(coach):
    r = coach.analyze_position(CHECKMATE)
    assert r["engine_truth"] is None and r["magnus_model"] is None and "game over" in r["note"]
    assert r["historical_evidence"]["examples"] is not None   # historical retrieval still works, it needs no legal moves


@needs_all
def test_public_api_returns_json_serialisable_structures(tmp_path):
    try:
        assert api.load_magnus_model()["move_space"] == 4162
        assert api.predict_next_move(NXE5)["legal"] is True and len(api.predict_moves(NXE5, 3)) == 3
        assert len(api.find_similar_positions(NXE5, 4)) == 4 and len(api.get_historical_magnus_examples(NXE5, 3)) == 3
        for f in (lambda: api.analyze_position(NXE5), lambda: api.compare_moves(NXE5, "d4", depth=8),
                  lambda: api.generate_coach_evidence(NXE5, "Nxe5", depth=8), lambda: api.challenge_plan(NXE5, "play d4")):
            json.dumps(f())
    finally:
        api.shutdown()


@needs_all
def test_historical_examples_from_api_have_resolvable_provenance():
    try:
        ex = api.get_historical_magnus_examples(NXE5, 8)
        db = MagnusDB()
        for e in ex:
            row = db.con.execute("SELECT position_id, game_id FROM positions WHERE id=?", (e["provenance"]["row_id"],)).fetchone()
            assert row is not None and row["game_id"] == e["historical_game"]["game_id"]
            assert db.get_game(e["historical_game"]["game_id"])["opponent"] == e["historical_game"]["opponent"]
            assert e["provenance"]["kind"] == "historical_fact"
    finally:
        api.shutdown()


@needs_all
def test_generate_training_position_needs_real_mistakes_and_has_provenance(coach, tmp_path):
    store = JsonPlayerStore(tmp_path)
    assert api.generate_training_position("nobody", player_dir=tmp_path) is None            # nothing invented for a new player
    c = ChessMateCoach(coach.services, store)
    c.review_move(NXE5, "Nxe5", player_id="zed", game_id="GG", ply=5)
    pos = api.generate_training_position("zed", player_dir=tmp_path)
    assert pos and pos["provenance"]["source_game"] == "GG" and pos["provenance"]["source_ply"] == 5
    assert chess.Board(pos["fen"]).is_valid() and "better_move" not in json.dumps(pos)


@needs_all
def test_all_annotations_from_analysis_are_valid(coach):
    for fen in (NXE5, chess.STARTING_FEN, "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1"):
        r = coach.analyze_position(fen)
        assert A.validate_annotations(r["annotations"])["valid"]
    r = coach.review_move(NXE5, "Nxe5", record=False)
    assert A.validate_annotations(r["annotations"])["valid"]
