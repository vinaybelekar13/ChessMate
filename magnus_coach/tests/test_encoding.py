import random

import chess
import pytest
import torch

from src.data.common import speed_from_time_control
from src.model import encoding as enc
from src.model.move_space import NUM_MOVES


def playout(seed, plies):
    rng = random.Random(seed)
    board = chess.Board()
    for _ in range(plies):
        moves = list(board.legal_moves)
        if not moves:
            break
        board.push(rng.choice(moves))
    return board


def test_shapes_and_dtypes():
    t = enc.encode_position(chess.STARTING_FEN, ["e2e4"], "180+2")
    assert t["squares"].shape == (64,) and t["squares"].dtype == torch.long
    assert t["history_from"].shape == (enc.HISTORY_LEN,) == t["history_to"].shape
    assert t["speed"].shape == () and t["ep"].shape == ()
    assert t["numeric"].shape == (enc.NUM_NUMERIC,) and t["numeric"].dtype == torch.float32
    assert t["legal_mask"].shape == (NUM_MOVES,) and t["legal_mask"].dtype == torch.bool
    assert int(t["squares"].max()) < enc.NUM_PIECE_TOKENS


def test_start_position_is_in_side_to_move_frame():
    t = enc.encode_position(chess.STARTING_FEN)
    assert t["squares"][0].item() == 4      # own rook a1
    assert t["squares"][4].item() == 6      # own king e1
    assert t["squares"][60].item() == 12    # opp king e8
    assert t["squares"][8].item() == 1      # own pawn a2
    assert t["squares"][48].item() == 7     # opp pawn a7


def test_black_to_move_start_looks_identical_apart_from_played_as_black():
    """After 1.e4 e5 2.Nf3 Nc6 the mirrored view of Black's move must equal
    White's view of the mirrored position: verified on many random positions."""
    for seed in range(40):
        board = playout(seed, random.Random(seed).randint(1, 90))
        if not any(board.legal_moves):
            continue
        a = enc.encode_position(board)
        b = enc.encode_position(board.mirror())
        for key in ("squares", "speed", "ep", "legal_mask"):
            assert torch.equal(a[key], b[key]), (key, board.fen())
        na, nb = a["numeric"].clone(), b["numeric"].clone()
        assert na[6] != nb[6]  # played_as_black differs (mirror flips who is to move)
        na[6] = nb[6] = 0
        assert torch.equal(na, nb)


def test_history_is_mirrored_consistently():
    for seed in range(30):
        board = playout(seed, 40)
        if not any(board.legal_moves):
            continue
        ucis = [m.uci() for m in board.move_stack]
        mirrored_hist = [
            chess.Move(chess.square_mirror(m.from_square), chess.square_mirror(m.to_square), m.promotion).uci()
            for m in board.move_stack
        ]
        a = enc.encode_position(board, ucis)
        b = enc.encode_position(board.mirror(), mirrored_hist)
        assert torch.equal(a["history_from"], b["history_from"])
        assert torch.equal(a["history_to"], b["history_to"])


def test_history_newest_first_padded_and_truncated():
    t = enc.encode_position(chess.STARTING_FEN, ["e2e4", "e7e5"])
    # side to move is White: e7e5 (newest) is oriented-mirrored? No: White => identity.
    assert t["history_from"][0].item() == chess.E7 and t["history_to"][0].item() == chess.E5
    assert t["history_from"][1].item() == chess.E2
    assert (t["history_from"][2:] == enc.HISTORY_PAD).all()
    long = enc.encode_position(chess.STARTING_FEN, ["a2a3"] * 9)
    assert (long["history_from"] != enc.HISTORY_PAD).all()


def test_en_passant_only_when_capture_is_legal():
    with_ep = enc.encode_position("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
    assert with_ep["ep"].item() == chess.square_file(chess.F6)
    board = chess.Board()
    board.push_uci("e2e4")  # FEN ep square e3, but no black pawn can capture it
    assert enc.encode_position(board)["ep"].item() == 8


def test_castling_bits_are_own_then_opponent():
    t = enc.encode_position("r3k2r/8/8/8/8/8/8/R3K2R w Kkq - 0 1")
    assert t["numeric"][:4].tolist() == [1.0, 0.0, 1.0, 1.0]
    t = enc.encode_position("r3k2r/8/8/8/8/8/8/R3K2R b Kkq - 0 1")  # Black to move: own = black
    assert t["numeric"][:4].tolist() == [1.0, 1.0, 1.0, 0.0]


# ------------------------------------------------------------ time control
@pytest.mark.parametrize(
    "tc,parsed", [("60+0", (60.0, 0.0)), ("180+2", (180.0, 2.0)), ("300", (300.0, 0.0)),
                  ("", None), (None, None), ("-", None), ("40/7200:3600", None)],
)
def test_parse_time_control(tc, parsed):
    assert enc.parse_time_control(tc) == parsed


@pytest.mark.parametrize("tc", ["15+0", "30+0", "60+0", "180+0", "180+2", "300+0", "600+0", "900+10", "1800+0", "5400+30"])
def test_speed_classes_agree_with_corpus_builder(tc):
    """The model's speed classes must match the ones stored in the corpus."""
    sid, _ = enc.resolve_time_control(tc)
    assert enc.SPEEDS[sid] == speed_from_time_control(tc)


def test_time_control_features_and_unspecified():
    sid, feats = enc.resolve_time_control(None)
    assert enc.SPEEDS[sid] == "unknown" and feats == [0.0, 0.0, 0.0]
    sid, feats = enc.resolve_time_control("60+0")
    assert enc.SPEEDS[sid] == "bullet" and feats[0] == 1.0 and 0 < feats[1] < 1 and feats[2] == 0.0
    assert all(0.0 <= f <= 1.0 for f in enc.resolve_time_control("99999+9999")[1])


def test_explicit_speed_overrides_and_is_validated():
    """Corpus can know 'blitz' from the event name while TimeControl is empty."""
    sid, feats = enc.resolve_time_control(None, "blitz")
    assert enc.SPEEDS[sid] == "blitz" and feats[0] == 0.0
    with pytest.raises(ValueError):
        enc.resolve_time_control(None, "lightning")


def test_time_control_reaches_the_tensors():
    a = enc.encode_position(chess.STARTING_FEN, time_control="60+0")
    b = enc.encode_position(chess.STARTING_FEN, time_control="1800+0")
    c = enc.encode_position(chess.STARTING_FEN)
    assert a["speed"] != b["speed"] and a["speed"] != c["speed"]
    assert not torch.equal(a["numeric"], b["numeric"])


def test_collate_and_model_inputs():
    items = [enc.encode_position(chess.STARTING_FEN), enc.encode_position(chess.STARTING_FEN, time_control="60+0")]
    batch = enc.collate(items)
    assert batch["squares"].shape == (2, 64) and batch["speed"].shape == (2,)
    assert set(enc.model_inputs(batch)) == set(enc.MODEL_INPUT_KEYS)
    assert "legal_mask" not in enc.model_inputs(batch)
    with pytest.raises(ValueError):
        enc.collate([])


def test_chess960_rejected():
    with pytest.raises(ValueError):
        enc.encode_position(chess.Board(chess960=True))
