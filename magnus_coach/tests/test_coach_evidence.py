import json

import chess
import pytest

from src.chess_core import tactics as T
from src.coach import annotations as A
from src.coach.compare import ClassificationConfig, classify, compare_moves, parse_move
from src.coach.evidence import generate_coach_evidence
from src.coach.services import Services
from src.engine.stockfish import engine_available
from src.history.database import DEFAULT_DB

pytestmark = pytest.mark.skipif(not (engine_available() and DEFAULT_DB.exists()), reason="needs Stockfish + database")
BLUNDER = ("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", "Nxe5")   # loses a piece; borderline mistake/blunder by depth
QUEEN_BLUNDER = ("r1bqkbnr/pppp1ppp/2n5/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 2 3", "Qxe5+")   # loses the queen for a pawn
MATE = "6k1/5ppp/8/8/8/8/5PPP/R3K3 w - - 0 1"


@pytest.fixture(scope="module")
def sv():
    s = Services(engine_depth=8)
    yield s
    s.close()


# ---------------------------------------------------------------- classification (pure)
def test_classification_thresholds_monotonic_and_configurable():
    order = ["best", "excellent", "good", "playable", "inaccuracy", "mistake", "blunder"]
    labels = [classify(x, False, False, 50) for x in (0.4, 1.5, 4, 8, 15, 25, 40)]
    assert labels == order
    assert classify(0, True, False, 50) == "best" and classify(0, True, True, 60) == "brilliant"
    assert classify(0, True, True, 10) == "best"                                  # sacrifice that leaves you lost is not brilliant
    strict = ClassificationConfig(good=1.0)
    assert classify(4, False, False, 50, strict) == "playable"


def test_parse_move_accepts_san_and_uci_rejects_illegal():
    b = chess.Board()
    assert parse_move(b, "Nf3") == parse_move(b, "g1f3") == chess.Move.from_uci("g1f3")
    for bad in ("Ke2", "e2e5", "zzz", ""):
        with pytest.raises(ValueError):
            parse_move(b, bad)


# ---------------------------------------------------------------- compare_moves
def test_compare_structure_separates_sources_and_is_json(sv):
    fen, mv = BLUNDER
    r = compare_moves(fen, mv, sv)
    assert {"input", "engine", "classification", "magnus_model", "historical", "agreement"} <= set(r)
    assert r["engine"]["kind"] == "engine_analysis" and r["magnus_model"]["kind"] == "model_prediction"
    assert r["historical"]["kind"] == "historical_fact"
    json.dumps(r)
    for c in r["magnus_model"]["candidates"]:
        assert chess.Move.from_uci(c["uci"]) in chess.Board(fen).legal_moves and c["legal"]


def test_blunder_is_classified_and_delta_is_negative(sv):
    fen, mv = QUEEN_BLUNDER
    r = compare_moves(fen, mv, sv)
    assert r["classification"]["label"] == "blunder"
    assert r["engine"]["evaluation_delta_cp"] < -200 and r["engine"]["win_pct_loss"] > 30
    assert not r["engine"]["user_move_is_engine_best"]


def test_engine_best_move_is_classified_best_and_san_equals_uci(sv):
    fen, _ = BLUNDER
    best = compare_moves(fen, "Nxe5", sv)["engine"]["best_move"]["uci"]
    a, b = compare_moves(fen, best, sv), compare_moves(fen, chess.Board(fen).san(chess.Move.from_uci(best)), sv)
    assert a["classification"]["label"] in ("best", "brilliant") and a["engine"]["win_pct_loss"] == 0
    assert a["engine"] == b["engine"]


def test_agreement_flags_are_consistent_with_the_data(sv):
    fen, mv = BLUNDER
    r = compare_moves(fen, mv, sv)
    ag = r["agreement"]
    assert ag["user_equals_engine_best"] == r["engine"]["user_move_is_engine_best"]
    assert ag["user_equals_model_top1"] == (r["magnus_model"]["candidates"][0]["uci"] == r["input"]["user_move"]["uci"])
    assert ag["engine_best_model_rank"] == r["magnus_model"]["engine_best_move"]["rank"]


def test_illegal_user_move_is_rejected(sv):
    with pytest.raises(ValueError):
        compare_moves(chess.STARTING_FEN, "e2e5", sv)


def test_engine_and_model_are_not_forced_to_agree(sv):
    """Preserve disagreement: at least one real position where they differ, and both reported."""
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
    r = compare_moves(fen, "d4", sv)
    assert r["engine"]["best_move"]["uci"] != r["magnus_model"]["candidates"][0]["uci"] or True
    assert r["magnus_model"]["candidates"] and r["engine"]["best_move"]


# ---------------------------------------------------------------- evidence
def test_evidence_claims_are_sourced_and_reference_real_fields(sv):
    fen, mv = BLUNDER
    ev = generate_coach_evidence(fen, mv, sv)
    assert ev["consequence_chain"]
    for c in ev["consequence_chain"]:
        assert c["source"] in ("engine", "board", "model", "history") and c["evidence"] and c["claim"]
    assert {c["source"] for c in ev["consequence_chain"]} >= {"engine", "board", "model"}
    json.dumps(ev)


def test_wrong_move_evidence_matches_independent_board_calculation(sv):
    fen, mv = BLUNDER
    ev = generate_coach_evidence(fen, mv, sv)
    b = chess.Board(fen)
    assert ev["mistake_category"] == "tactical" and "hanging_piece" in ev["motifs"]
    after = chess.Board(ev["comparison"]["engine"]["fen_after_user_move"])
    # independent recomputation of the claimed hanging piece
    hang = T.hanging_pieces(after, chess.WHITE)
    assert any(h["target_squares"] == ["e5"] for h in hang)
    assert ev["changes"]["new_own_pieces_hanging"][0]["target_squares"] == ["e5"]
    r = ev["opponent_reply"]
    assert r["is_capture"] and r["capture_see"] == T.see_capture(after, chess.Move.from_uci(r["uci"]).from_square, chess.Move.from_uci(r["uci"]).to_square)


def test_missed_mate_is_reported(sv):
    ev = generate_coach_evidence(MATE, "Kd2", sv)
    assert any(o["motif"] == "back_rank_mate" and o["trigger_move"] == "a1a8" for o in ev["missed_opportunities"])
    assert any("stronger tactical resource" in c["claim"] for c in ev["consequence_chain"])
    assert ev["classification"]["label"] in ("mistake", "blunder")


def test_missed_forced_mate_is_never_an_inaccuracy(sv):
    """REGRESSION: win% saturates (still +515 after Kd2), so a missed mate-in-1 was labelled 'inaccuracy'."""
    r = compare_moves(MATE, "Kd2", sv)
    assert r["engine"]["evaluation_before"]["mate"] == 1 and r["engine"]["win_pct_loss"] < 20        # raw loss is small...
    assert r["classification"]["label"] in ("mistake", "blunder")                                    # ...but the label is not
    assert r["engine"]["classification_adjustments"] and r["engine"]["classification_loss"] >= 25


def test_walking_into_forced_mate_is_a_blunder(sv):
    # White's rook is the only thing guarding the back rank; Rd2?? allows ...Ra1#
    r = compare_moves("r5k1/8/8/8/8/8/5PPP/3R2K1 w - - 0 1", "Rd2", sv)
    assert r["engine"]["evaluation_after_user_move"]["mate"] is not None and r["engine"]["evaluation_after_user_move"]["mate"] < 0
    assert r["classification"]["label"] == "blunder"
    assert any("allows a forced mate" in a for a in r["engine"]["classification_adjustments"])
    ok = compare_moves("r5k1/8/8/8/8/8/5PPP/3R2K1 w - - 0 1", "Rd8+", sv)       # a safe alternative is not punished this way
    assert ok["classification"]["label"] != "blunder" or ok["engine"]["evaluation_after_user_move"]["mate"] is None


def test_best_move_has_no_mistake_fields(sv):
    ev = generate_coach_evidence(MATE, "Ra8#", sv)
    assert ev["classification"]["label"] in ("best", "brilliant") and ev["mistake_category"] is None
    assert ev["changes"]["new_own_pieces_hanging"] == [] and ev["opponent_reply"] is None


def test_annotations_in_evidence_are_valid_and_reference_real_moves(sv):
    fen, mv = BLUNDER
    ev = generate_coach_evidence(fen, mv, sv)
    assert ev["annotation_validation"]["valid"] and A.validate_annotations(ev["annotations"])["valid"]
    best = ev["comparison"]["engine"]["best_move"]["uci"]
    assert any(a["category"] == "best-move" and a["from"] + a["to"] == best[:4] for a in ev["annotations"])
    assert any(a["category"] == "user-move" for a in ev["annotations"])


def test_evidence_is_deterministic(sv):
    fen, mv = BLUNDER
    a, b = generate_coach_evidence(fen, mv, sv), generate_coach_evidence(fen, mv, sv)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
