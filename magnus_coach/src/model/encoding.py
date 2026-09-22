"""Position -> tensor encoding for the Magnus model.

STATUS: FINAL (encoding version "v1"). This module is the single place that
defines model inputs; training (src/model/dataset.py) and inference
(src/inference/predict.py) both go through `encode_position`, so there is no
train/serve skew. Encoding is fully deterministic (no randomness).

Inputs per position (all in the SIDE-TO-MOVE frame, see move_space.py):

    squares       long  [64]   0 empty | 1..6 own P,N,B,R,Q,K | 7..12 opp P..K
    history_from  long  [5]    from-square of last 5 moves, newest first, 64=pad
    history_to    long  [5]    to-square of the same moves,            64=pad
    speed         long  []     0 unknown 1 ultrabullet 2 bullet 3 blitz
                               4 rapid 5 classical
    ep            long  []     file 0..7 of a LEGAL en-passant capture, 8=none
    numeric       float [10]   own K/Q castling, opp K/Q castling,
                               halfmove clock/100, fullmove number/100 (game
                               phase), played_as_black, time_control_present,
                               log base time, log increment
    legal_mask    bool  [4162] (not a model input; used to mask the output)
"""

from __future__ import annotations

import math
import re
from typing import Dict, Iterable, List, Optional, Sequence, Union

import chess
import torch

from .move_space import NUM_MOVES, legal_move_mask, orient_square

ENCODING_VERSION = "v1"

HISTORY_LEN = 5
HISTORY_PAD = 64
NUM_PIECE_TOKENS = 13
SPEEDS = ("unknown", "ultrabullet", "bullet", "blitz", "rapid", "classical")
# The corpus builder (Phase 1-3, unchanged) labels missing time control "unspecified".
SPEED_ALIASES = {"unspecified": "unknown"}
SPEED_TO_ID = {s: i for i, s in enumerate(SPEEDS)}
NUM_EP_STATES = 9
NUM_NUMERIC = 10
MODEL_INPUT_KEYS = ("squares", "history_from", "history_to", "speed", "ep", "numeric")

_MAX_BASE_SECONDS = 7200.0
_MAX_INCREMENT_SECONDS = 180.0


# ----------------------------------------------------------------- time control
def parse_time_control(time_control) -> Optional[tuple]:
    """'60+0' -> (60.0, 0.0); '300' -> (300.0, 0.0); anything else -> None."""
    if time_control is None:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*(?:\+\s*(\d+))?\s*", str(time_control))
    if not m:
        return None
    return float(m.group(1)), float(m.group(2) or 0)


def speed_from_seconds(base: float, increment: float) -> str:
    """Lichess convention: estimated duration = base + 40 * increment."""
    total = base + 40 * increment
    if total < 30:
        return "ultrabullet"
    if total < 180:
        return "bullet"
    if total < 480:
        return "blitz"
    if total < 1500:
        return "rapid"
    return "classical"


def resolve_time_control(time_control=None, speed: Optional[str] = None):
    """Return (speed_id, [present, log_base, log_inc]).

    An explicit `speed` wins (the corpus sometimes infers speed from the event
    name when there is no TimeControl header). Unknown -> 'unknown', all 0.
    """
    parsed = parse_time_control(time_control)
    speed = SPEED_ALIASES.get(speed, speed)
    if speed is not None and speed not in SPEED_TO_ID:
        raise ValueError(f"unknown speed {speed!r}; expected one of {SPEEDS}")
    if speed is None:
        speed = speed_from_seconds(*parsed) if parsed else "unknown"
    if parsed:
        base, inc = parsed
        feats = [
            1.0,
            min(math.log1p(base) / math.log1p(_MAX_BASE_SECONDS), 1.0),
            min(math.log1p(inc) / math.log1p(_MAX_INCREMENT_SECONDS), 1.0),
        ]
    else:
        feats = [0.0, 0.0, 0.0]
    return SPEED_TO_ID[speed], feats


# ----------------------------------------------------------------- position
def _as_board(position: Union[str, chess.Board]) -> chess.Board:
    board = chess.Board(position) if isinstance(position, str) else position
    if board.chess960:
        raise ValueError("Chess960 is not supported")
    return board


def encode_position(
    position: Union[str, chess.Board],
    history_uci: Sequence[str] = (),
    time_control: Optional[str] = None,
    speed: Optional[str] = None,
) -> Dict[str, torch.Tensor]:
    """Encode one position (side to move = the player being modelled).

    `history_uci`: moves played BEFORE this position, oldest -> newest; only
    the last HISTORY_LEN are used.
    """
    board = _as_board(position)
    turn = board.turn

    squares = torch.zeros(64, dtype=torch.long)
    for sq, piece in board.piece_map().items():
        offset = 0 if piece.color == turn else 6
        squares[orient_square(sq, turn)] = offset + piece.piece_type

    hist_from = torch.full((HISTORY_LEN,), HISTORY_PAD, dtype=torch.long)
    hist_to = torch.full((HISTORY_LEN,), HISTORY_PAD, dtype=torch.long)
    recent = list(history_uci)[-HISTORY_LEN:]
    for slot, uci in enumerate(reversed(recent)):  # slot 0 = newest
        move = chess.Move.from_uci(uci)
        hist_from[slot] = orient_square(move.from_square, turn)
        hist_to[slot] = orient_square(move.to_square, turn)

    ep = chess.square_file(board.ep_square) if (board.ep_square is not None and board.has_legal_en_passant()) else 8

    speed_id, tc_feats = resolve_time_control(time_control, speed)
    numeric = torch.tensor(
        [
            float(board.has_kingside_castling_rights(turn)),
            float(board.has_queenside_castling_rights(turn)),
            float(board.has_kingside_castling_rights(not turn)),
            float(board.has_queenside_castling_rights(not turn)),
            min(board.halfmove_clock, 100) / 100.0,
            min(board.fullmove_number, 100) / 100.0,
            float(turn == chess.BLACK),
            *tc_feats,
        ],
        dtype=torch.float32,
    )

    return {
        "squares": squares,
        "history_from": hist_from,
        "history_to": hist_to,
        "speed": torch.tensor(speed_id, dtype=torch.long),
        "ep": torch.tensor(ep, dtype=torch.long),
        "numeric": numeric,
        "legal_mask": legal_move_mask(board),
    }


def collate(items: Iterable[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
    """Stack per-position dicts into a batch."""
    items = list(items)
    if not items:
        raise ValueError("cannot collate an empty batch")
    return {k: torch.stack([it[k] for it in items]) for k in items[0]}


def model_inputs(batch: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
    """The subset of a batch that is fed to the network (excludes legal_mask)."""
    return {k: batch[k] for k in MODEL_INPUT_KEYS}
