"""Universal move space for the Magnus model.

Goal: EVERY legal standard-chess move has exactly one slot, independent of
which moves happened to occur as Magnus targets in the training corpus.

Layout (indices are in the SIDE-TO-MOVE frame, see `orient_square`):

    [0, 4096)      from_square * 64 + to_square
                   covers all normal moves, captures, castling (king moves two
                   squares, e.g. e1g1), en passant, and QUEEN promotion.
    [4096, 4162)   underpromotions: 22 (from, to) pawn pairs on the 7th->8th
                   rank (8 straight + 7 left-capture + 7 right-capture) x 3
                   pieces (rook, bishop, knight).

    NUM_MOVES = 4096 + 22 * 3 = 4162

Orientation: when Black is to move the board is mirrored vertically
(square ^ 56), so the model always sees "own pieces moving up the board".
Chess is symmetric under (vertical mirror + colour swap), so this halves what
the network has to learn. Move indices use the same mirror.

Only standard chess is supported (no Chess960).
"""

from __future__ import annotations

from typing import List, Tuple

import chess
import torch

NUM_PAIR_MOVES = 64 * 64
_UNDERPROMO_PIECES = (chess.ROOK, chess.BISHOP, chess.KNIGHT)
_UNDERPROMO_TYPE = {p: i for i, p in enumerate(_UNDERPROMO_PIECES)}


def _build_underpromo_pairs() -> List[Tuple[int, int]]:
    """Oriented (from, to) pairs a pawn can promote with: rank 7 -> rank 8."""
    pairs = []
    for from_file in range(8):
        for to_file in (from_file - 1, from_file, from_file + 1):
            if 0 <= to_file < 8:
                pairs.append((chess.square(from_file, 6), chess.square(to_file, 7)))
    return pairs


UNDERPROMO_PAIRS: Tuple[Tuple[int, int], ...] = tuple(_build_underpromo_pairs())
NUM_UNDERPROMO_PAIRS = len(UNDERPROMO_PAIRS)  # 22
NUM_UNDERPROMO_TYPES = len(_UNDERPROMO_PIECES)  # 3
_PAIR_TO_ID = {pair: i for i, pair in enumerate(UNDERPROMO_PAIRS)}
UNDERPROMO_OFFSET = NUM_PAIR_MOVES
NUM_MOVES = NUM_PAIR_MOVES + NUM_UNDERPROMO_PAIRS * NUM_UNDERPROMO_TYPES  # 4162

# Flat pair-space index of every underpromotion (from,to), used by the model head.
UNDERPROMO_PAIR_INDEX: Tuple[int, ...] = tuple(f * 64 + t for f, t in UNDERPROMO_PAIRS)


def orient_square(square: int, turn: bool) -> int:
    """Square in the side-to-move frame (vertical mirror for Black)."""
    return square if turn == chess.WHITE else square ^ 56


def move_to_index(move: chess.Move, turn: bool) -> int:
    """Index of `move` for the side `turn` that is playing it."""
    f = orient_square(move.from_square, turn)
    t = orient_square(move.to_square, turn)
    if move.promotion in _UNDERPROMO_TYPE:
        pair_id = _PAIR_TO_ID.get((f, t))
        if pair_id is None:  # cannot happen for a legal promotion
            raise ValueError(f"promotion {move} is not a rank-7 to rank-8 pawn move")
        return UNDERPROMO_OFFSET + pair_id * NUM_UNDERPROMO_TYPES + _UNDERPROMO_TYPE[move.promotion]
    return f * 64 + t


def index_to_move(index: int, board: chess.Board) -> chess.Move:
    """Inverse of `move_to_index` for the side to move on `board`.

    Note: a from/to slot that is a pawn reaching the last rank decodes as a
    QUEEN promotion (that is what the pair slots mean).
    """
    if not 0 <= index < NUM_MOVES:
        raise ValueError(f"move index {index} outside [0, {NUM_MOVES})")
    turn = board.turn
    promotion = None
    if index >= UNDERPROMO_OFFSET:
        rel = index - UNDERPROMO_OFFSET
        f, t = UNDERPROMO_PAIRS[rel // NUM_UNDERPROMO_TYPES]
        promotion = _UNDERPROMO_PIECES[rel % NUM_UNDERPROMO_TYPES]
    else:
        f, t = divmod(index, 64)
    from_sq, to_sq = orient_square(f, turn), orient_square(t, turn)  # mirror is an involution
    if promotion is None:
        piece = board.piece_at(from_sq)
        if piece is not None and piece.piece_type == chess.PAWN and chess.square_rank(to_sq) in (0, 7):
            promotion = chess.QUEEN
    return chess.Move(from_sq, to_sq, promotion)


def legal_moves_with_indices(board: chess.Board) -> List[Tuple[int, chess.Move]]:
    """[(index, move)] for every legal move. Indices are guaranteed unique."""
    out = [(move_to_index(m, board.turn), m) for m in board.legal_moves]
    if len({i for i, _ in out}) != len(out):  # would indicate a move-space bug
        raise AssertionError("move-space collision among legal moves in " + board.fen())
    return out


def legal_move_mask(board: chess.Board) -> torch.Tensor:
    """Bool tensor [NUM_MOVES]; True exactly at the legal moves' indices."""
    mask = torch.zeros(NUM_MOVES, dtype=torch.bool)
    for idx, _ in legal_moves_with_indices(board):
        mask[idx] = True
    return mask
