import random

import chess
import pytest
import torch

from src.model import move_space as ms


def random_positions(n_games=60, max_plies=110, seed=1234):
    """Positions from seeded random playouts (covers varied, legal boards)."""
    rng = random.Random(seed)
    for _ in range(n_games):
        board = chess.Board()
        for _ in range(max_plies):
            yield board.copy(stack=False)
            moves = list(board.legal_moves)
            if not moves:
                break
            board.push(rng.choice(moves))


def test_constants():
    assert ms.NUM_UNDERPROMO_PAIRS == 22
    assert ms.NUM_MOVES == 4096 + 22 * 3 == 4162
    assert len(set(ms.UNDERPROMO_PAIR_INDEX)) == 22


def test_every_legal_move_has_a_unique_slot_and_roundtrips():
    checked = 0
    for board in random_positions():
        pairs = ms.legal_moves_with_indices(board)  # asserts uniqueness internally
        for idx, move in pairs:
            assert 0 <= idx < ms.NUM_MOVES
            assert ms.index_to_move(idx, board) == move
            checked += 1
    assert checked > 100_000


def test_mask_marks_exactly_the_legal_moves():
    for board in random_positions(n_games=15):
        mask = ms.legal_move_mask(board)
        assert mask.dtype == torch.bool and mask.shape == (ms.NUM_MOVES,)
        assert int(mask.sum()) == board.legal_moves.count()
        for idx in mask.nonzero().flatten().tolist():
            assert ms.index_to_move(idx, board) in board.legal_moves


@pytest.mark.parametrize(
    "fen",
    [
        "1n5k/P7/8/8/8/8/8/K7 w - - 0 1",   # a8 (x4 pieces) and axb8 (x4 pieces), White
        "k7/8/8/8/8/8/p7/1N5K b - - 0 1",   # a1 and axb1 promotions, Black (mirrored frame)
        "1r1r3k/2P5/8/8/8/8/8/K7 w - - 0 1",  # capture promotions both sides
    ],
)
def test_all_promotions_including_underpromotions_are_distinct(fen):
    board = chess.Board(fen)
    promos = [m for m in board.legal_moves if m.promotion]
    assert len(promos) >= 8
    pairs = {m: ms.move_to_index(m, board.turn) for m in promos}
    assert len(set(pairs.values())) == len(promos)
    for move, idx in pairs.items():
        assert ms.index_to_move(idx, board) == move
    # queen promotion lives in the pair range, others in the underpromotion range
    for move, idx in pairs.items():
        assert (idx < ms.UNDERPROMO_OFFSET) == (move.promotion == chess.QUEEN)


def test_castling_and_en_passant_are_representable():
    for fen, expected_uci in [
        ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", {"e1g1", "e1c1"}),
        ("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1", {"e8g8", "e8c8"}),
        ("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3", {"e5f6"}),
    ]:
        board = chess.Board(fen)
        got = {m.uci() for _, m in ms.legal_moves_with_indices(board)}
        assert expected_uci <= got
        for idx, m in ms.legal_moves_with_indices(board):
            assert ms.index_to_move(idx, board) == m


def test_mirror_symmetry_of_indices():
    """(vertical mirror + colour swap) must give identical index sets."""
    for board in random_positions(n_games=20):
        mirrored = board.mirror()
        a = {i for i, _ in ms.legal_moves_with_indices(board)}
        b = {i for i, _ in ms.legal_moves_with_indices(mirrored)}
        assert a == b


def test_out_of_range_index_rejected():
    with pytest.raises(ValueError):
        ms.index_to_move(ms.NUM_MOVES, chess.Board())
    with pytest.raises(ValueError):
        ms.index_to_move(-1, chess.Board())


def test_no_dependence_on_observed_corpus_moves():
    """The whole point: slots exist for moves never seen as targets.
    Every one of the 4096 from/to pairs that is legal somewhere is reachable
    by construction (index = from*64+to), independent of any vocabulary file."""
    seen = set()
    for board in random_positions(n_games=80, seed=7):
        seen.update(i for i, _ in ms.legal_moves_with_indices(board))
    assert len(seen) > 1500  # broad coverage from random play alone
