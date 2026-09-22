import json
import random

import chess
import pytest

from src.chess_core import tactics as T


def motifs(findings):
    return {f["motif"] for f in findings}


# ---------------------------------------------------------------- SEE
@pytest.mark.parametrize("fen,frm,to,expected", [
    ("4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1", "e4", "d5", 1),          # pawn takes undefended pawn
    ("4k3/8/2p5/3p4/4P3/8/8/4K3 w - - 0 1", "e4", "d5", 0),         # pawn trade (cxd5 exd5)
    ("4k3/8/2p5/3p4/8/8/8/3QK3 w - - 0 1", "d1", "d5", -8),         # queen takes defended pawn
    ("4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1", "d1", "d5", 3),            # rook wins hanging knight
])
def test_see(fen, frm, to, expected):
    assert T.see_capture(chess.Board(fen), chess.parse_square(frm), chess.parse_square(to)) == expected


def test_see_xray_battery():
    # Rd2xd5 (+3) cxd5 (-5) Rd1xd5 (+1): the second rook joins through the x-ray, net -1
    b = chess.Board("4k3/8/2p5/3n4/8/8/3R4/3RK3 w - - 0 1")
    assert T.see_capture(b, chess.D2, chess.D5) == -1
    # with the pawn defender gone the same battery simply wins the knight
    b2 = chess.Board("4k3/8/8/3n4/8/8/3R4/3RK3 w - - 0 1")
    assert T.see_capture(b2, chess.D2, chess.D5) == 3


def test_see_en_passant():
    b = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    assert T.see_capture(b, chess.E5, chess.D6) == 1


# ---------------------------------------------------------------- individual motifs
def test_knight_fork_king_and_rook():
    b = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1")
    f = [x for x in T.opportunities(b) if x["motif"] == "fork"]
    assert f and f[0]["trigger_move"] == "d5c7" and set(f[0]["target_squares"]) == {"a8", "e8"}
    assert f[0]["supporting_legal_moves"] == ["d5c7"] and chess.Board(f[0]["resulting_fen"]).is_check()


def test_no_fork_when_forking_piece_is_lost():
    b = chess.Board("r2qk3/8/8/3N4/8/8/8/4K3 w - - 0 1")     # Nc7+ forks but Qxc7 wins the knight
    assert not [x for x in T.opportunities(b) if x["motif"] == "fork" and x["trigger_move"] == "d5c7"]


def test_absolute_pin_and_relative_pin():
    b = chess.Board("4k3/8/2n5/1B6/8/8/8/4K3 w - - 0 1")
    p = [x for x in T.pins_and_skewers(b) if x["motif"] == "pin"]
    assert len(p) == 1 and p[0]["absolute"] and p[0]["front_square"] == "c6" and p[0]["rear_square"] == "e8"
    b2 = chess.Board("3rk3/8/8/8/8/3N4/8/3QK3 b - - 0 1")     # rook d8 pins knight d3 to queen d1 (relative)
    p2 = [x for x in T.pins_and_skewers(b2) if x["motif"] == "pin" and x["source_square"] == "d8"]
    assert p2 and not p2[0]["absolute"]


def test_skewer_king_in_front_of_queen():
    b = chess.Board("q7/8/8/8/k7/8/8/R3K3 b - - 0 1")
    s = [x for x in T.pins_and_skewers(b) if x["motif"] == "skewer"]
    assert s and s[0]["source_square"] == "a1" and s[0]["target_squares"] == ["a4", "a8"]


def test_hanging_piece():
    b = chess.Board("4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1")
    h = T.hanging_pieces(b, chess.BLACK)
    assert len(h) == 1 and h[0]["target_squares"] == ["d5"] and h[0]["material_at_risk"] == 3
    assert T.hanging_pieces(chess.Board(), chess.WHITE) == []


def test_discovered_check():
    b = chess.Board("4k3/8/8/8/4N3/8/8/4RK2 w - - 0 1")
    d = [x for x in T.opportunities(b) if x["motif"] == "discovered_check"]
    assert d and all(chess.Board(x["resulting_fen"]).is_check() for x in d)
    assert {x["source_square"] for x in d} == {"e1"}


def test_back_rank_mate_and_weakness():
    b = chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
    m = [x for x in T.opportunities(b) if x["motif"] == "back_rank_mate"]
    assert m and m[0]["trigger_move"] == "a1a8" and chess.Board(m[0]["resulting_fen"]).is_checkmate()
    w = T.back_rank_weakness(b, chess.BLACK)
    assert w and "no flight square" in w["consequence"]
    assert T.back_rank_weakness(chess.Board("6k1/5p1p/8/8/8/8/8/R3K3 w - - 0 1"), chess.BLACK) is None  # luft on g7


def test_mate_threat_against_side_to_move():
    b = chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 b - - 0 1")     # Black to move; White threatens Ra8#
    a = T.analyze_tactics(b)
    assert any(t["motif"] == "back_rank_mate" and t["trigger_move"] == "a1a8" for t in a["threats_against_side_to_move"])


def test_trapped_piece():
    b = chess.Board("r3k3/B1p5/1p6/8/8/8/8/4K3 w - - 0 1")
    tr = T.trapped_pieces(b, chess.WHITE)
    assert tr and tr[0]["target_squares"] == ["a7"]
    assert T.trapped_pieces(chess.Board(), chess.WHITE) == []


def test_overloaded_piece_verified_by_simulation():
    # Black Qd8 is the only defender of Bb6 and Nd5? (Rd1 attacks d5, Be3 attacks b6)
    b = chess.Board("3q2k1/8/1b6/3n4/8/4B3/8/3RK3 w - - 0 1")
    found = [x for x in T.opportunities(b) if x["motif"] == "overloaded_piece"]
    for f in found:                                            # whatever is reported must be a real, legal line
        pos = chess.Board(b.fen())
        for u in f["supporting_legal_moves"]:
            assert chess.Move.from_uci(u) in pos.legal_moves
            pos.push_uci(u)


def test_zwischenzug_is_declared_unsupported():
    assert "zwischenzug" in T.analyze_tactics(chess.Board())["unsupported_motifs"]
    assert "zwischenzug" not in T.SUPPORTED_MOTIFS


# ---------------------------------------------------------------- no false positives on quiet starts
def test_start_position_has_no_tactics():
    a = T.analyze_tactics(chess.Board())
    assert a["opportunities_for_side_to_move"] == [] and a["threats_against_side_to_move"] == []
    assert not T.is_tactical_position(chess.Board())


# ---------------------------------------------------------------- consequences of a move
def test_tactics_after_blunder_shows_opponent_resource():
    b = chess.Board("4k3/8/8/3n4/8/8/8/3RK3 b - - 0 1")     # Black to move; leaving Nd5 en prise
    c = T.tactics_after_move(b, chess.Move.from_uci("e8e7"))
    assert any(o["motif"] == "hanging_piece" and o["target_squares"] == ["d5"] for o in c["opponent_opportunities"])
    assert c["fen_after"] == _push(b, "e8e7")


def _push(b, u):
    b2 = b.copy(); b2.push_uci(u); return b2.fen()


def test_tactics_after_illegal_move_raises():
    with pytest.raises(ValueError):
        T.tactics_after_move(chess.Board(), chess.Move.from_uci("e2e5"))


# ---------------------------------------------------------------- global invariants on random positions
def test_all_findings_are_internally_consistent():
    rng = random.Random(3)
    checked = 0
    for _ in range(40):
        b = chess.Board()
        for _ in range(rng.randint(10, 80)):
            ms = list(b.legal_moves)
            if not ms:
                break
            b.push(rng.choice(ms))
        if b.is_game_over():
            continue
        a = T.analyze_tactics(b)
        for f in a["opportunities_for_side_to_move"]:
            assert f["motif"] in T.SUPPORTED_MOTIFS
            for u in f["supporting_legal_moves"][:1]:
                assert chess.Move.from_uci(u) in b.legal_moves           # first supporting move is legal now
            if f["resulting_fen"]:
                chess.Board(f["resulting_fen"])                          # parseable
            for s in f["target_squares"] + [f["source_square"]]:
                chess.parse_square(s)
            checked += 1
        json.dumps(a)                                                    # JSON-serialisable
    assert checked > 0


def test_piece_symbols_are_rendered_as_readable_names_in_consequences():
    """REGRESSION: claims said 'n on c6' / 'captures a N' - case encodes colour and was unreadable."""
    assert T.piece_name("N") == "white knight" and T.piece_name("q") == "black queen"
    assert T.words("n on c6 wins material; R @ d1") == "black knight on c6 wins material; white rook @ d1"
    b = chess.Board("4k3/8/8/3n4/8/8/8/3RK3 w - - 0 1")
    h = T.hanging_pieces(b, chess.BLACK)[0]
    assert h["consequence"].startswith("white rook on d1 wins material")
