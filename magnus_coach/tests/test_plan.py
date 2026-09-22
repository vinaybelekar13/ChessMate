import json

import chess
import pytest

from src.coach import plan as P
from src.coach.evidence import generate_coach_evidence
from src.coach.services import Services
from src.engine.stockfish import engine_available
from src.history.database import DEFAULT_DB

pytestmark = pytest.mark.skipif(not (engine_available() and DEFAULT_DB.exists()), reason="needs Stockfish + database")
NXE5 = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
MATE = "6k1/5ppp/8/8/8/8/5PPP/R3K3 w - - 0 1"


@pytest.fixture(scope="module")
def sv():
    s = Services(engine_depth=8)
    yield s
    s.close()


# ---------------------------------------------------------------- plan parsing
def test_parse_plan_extracts_moves_and_intents():
    p = P.parse_plan(chess.Board(), "I want to attack the kingside with h4 and g4, then Qh5")
    assert p["candidate_moves"] == ["h4", "g4", "Qh5"] and "kingside_attack" in p["intents"]
    assert set(P.parse_plan(chess.Board(), "castle and develop")["intents"]) == {"castle", "develop"}


def test_structure_helpers():
    b = chess.Board()
    assert P.king_shield(b, chess.WHITE) == 3            # d2, e2, f2 shield the king on e1
    b.push_uci("e2e4")
    assert P.king_shield(b, chess.WHITE) == 2            # the e-pawn left the shield
    assert P.pawn_structure(chess.Board("4k3/8/8/8/8/P7/P7/4K3 w - - 0 1"), chess.WHITE)["doubled"] == 1
    assert P.pawn_structure(chess.Board("4k3/8/8/8/8/8/P1P5/4K3 w - - 0 1"), chess.WHITE)["isolated"] == 2
    assert P.undeveloped_minor_pieces(chess.Board(), chess.WHITE) == 4


# ---------------------------------------------------------------- challenge
def test_bad_plan_is_challenged_with_board_evidence(sv):
    r = P.challenge_plan(NXE5, "I will win a pawn with Nxe5", sv)
    assert r["verdict"] in ("contradicted", "questionable") and r["challenged"]
    assert r["weaknesses"] and any("e5" in w["fact"] for w in r["weaknesses"])
    assert r["opponent_resources"] and r["alternative_plan"]["engine_best_move"] != "Nxe5"
    assert r["win_pct_loss"] > 15
    json.dumps(r)


def test_sound_plan_is_supported(sv):
    r = P.challenge_plan(NXE5, "play d4 to open the centre", sv)
    assert r["verdict"] == "supported" and not r["challenged"]
    assert r["evaluation_trajectory"] and r["supporting_factors"]


def test_unplayable_plan_is_reported_not_agreed_with(sv):
    r = P.challenge_plan(NXE5, "Qh8 wins everything", sv)
    assert r["verdict"] == "not_playable" and r["challenged"] and r["unplayable_plan_tokens"]


def test_kingside_attack_on_wrong_wing_is_flagged(sv):
    fen = "2kr4/ppp5/8/8/8/8/PPP2PPP/4K2R w K - 0 1"          # Black king is on the queenside (c8)
    r = P.challenge_plan(fen, "attack the kingside with h4 and g4", sv)
    assert any("queenside" in w["fact"] for w in r["weaknesses"])


def test_every_claim_has_a_source(sv):
    r = P.challenge_plan(NXE5, "Nxe5", sv)
    for k in ("supporting_factors", "weaknesses", "positional_concerns", "tactical_refutations"):
        assert all(x["source"] in ("engine", "board", "history") for x in r[k])
    assert r["confidence"]["basis"]


# ---------------------------------------------------------------- Socratic
@pytest.fixture(scope="module")
def evidences(sv):
    return [generate_coach_evidence(NXE5, "Nxe5", sv), generate_coach_evidence(MATE, "Kd2", sv),
            generate_coach_evidence("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", "a3", sv)]


def test_hints_never_reveal_the_best_move(evidences):
    for ev in evidences:
        hints = P.build_hints(ev)
        assert set(hints) == set(P.HINT_LEVELS)
        for k in ("hint_1", "hint_2", "stronger_hint"):
            assert not P._leaks(hints[k]["text"], ev), (k, hints[k]["text"])
            assert hints[k]["basis"]
        best = ev["comparison"]["engine"]["best_move"]["san"]
        assert best in hints["reveal"]["text"]


def test_hint_only_mode_never_reveals(evidences):
    for ev in evidences:
        s = P.SocraticSession(ev, hint_only=True)
        seen = [s.next_hint() for _ in range(6)]
        texts = " ".join(h["text"] or "" for h in seen)
        assert not P._leaks(texts, ev)
        assert any(h.get("refused") for h in seen) and not s.revealed
        assert s.reveal()["refused"] is True and s.revealed is False


def test_full_mode_progresses_then_reveals(evidences):
    ev = evidences[0]
    s = P.SocraticSession(ev)
    levels = [s.next_hint()["level"] for _ in range(4)]
    assert levels == list(P.HINT_LEVELS) and s.revealed
    assert s.next_hint()["exhausted"]
    s2 = P.SocraticSession(ev)
    assert s2.reveal()["revealed"] and ev["comparison"]["engine"]["best_move"]["san"] in s2.reveal()["text"]


def test_hints_are_grounded_in_evidence_type(evidences):
    hang, mate = evidences[0], evidences[1]
    assert "captured" in P.build_hints(hang)["hint_2"]["text"] or "not adequately defended" in P.build_hints(hang)["hint_2"]["text"]
    assert "king" in P.build_hints(mate)["hint_1"]["text"].lower()


def test_leak_detector_catches_obvious_leaks(evidences):
    ev = evidences[0]
    best = ev["comparison"]["engine"]["best_move"]
    assert P._leaks(f"Play {best['san']}!", ev) and P._leaks(f"try {best['uci']}", ev)
    assert not P._leaks("Think about your opponent's reply.", ev)
