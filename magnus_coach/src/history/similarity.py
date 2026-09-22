"""Deterministic V1 position similarity. NOT semantic chess understanding.

Positions are compared in the SIDE-TO-MOVE frame (board mirrored vertically
when Black is to move, "own" = side to move), so a position with Black to
move can match the mirrored position with White to move. `mirrored` in a
result says whether the stored position had the other side to move.

Score = weighted sum of components, each in [0,1] (1 = identical):

  placement 0.30  Jaccard of the (piece type, owner, square) sets
  material  0.15  1 - L1(piece counts) / sum of per-type maxima (P,N,B,R,Q, own & opp)
  pawns     0.20  Jaccard of own-pawn squares + opp-pawn squares
  kings     0.10  mean over both kings of 1 - chebyshev_distance/7
  castling  0.05  fraction of the 4 castling-right bits (own K/Q, opp K/Q) that agree
  pieces    0.10  minor/major piece placement, compared on 16 coarse zones (2x2 blocks)
                  for own and opponent separately: 1 - L1/sum of maxima
  center    0.10  Jaccard of occupied (owner, square) in the 16-square extended centre (c3-f6)

Identical oriented placement + castling rights = score 1.0 (`exact_board_match`).
Retrieval uses indexed hash keys (exact board, pawn structure, material) to build
a candidate pool, then scores candidates with this function.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Dict, Tuple

import chess

WEIGHTS = {"placement": 0.30, "material": 0.15, "pawns": 0.20, "kings": 0.10,
           "castling": 0.05, "pieces": 0.10, "center": 0.10}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
_TYPES = (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING)
_CENTER = 0
for _f in range(2, 6):
    for _r in range(2, 6):
        _CENTER |= chess.BB_SQUARES[chess.square(_f, _r)]
_ZONE_MASKS = [sum(chess.BB_SQUARES[chess.square(f, r)] for f in range(zf * 2, zf * 2 + 2) for r in range(zr * 2, zr * 2 + 2))
               for zr in range(4) for zf in range(4)]
Features = Tuple[Tuple[int, ...], int]   # (12 bitboards own P..K then opp P..K, castling nibble)


def pop(x: int) -> int:
    return x.bit_count()


def features(board: chess.Board) -> Features:
    turn = board.turn
    flip = chess.flip_vertical if turn == chess.BLACK else (lambda b: b)
    bbs = [flip(board.pieces_mask(t, turn)) for t in _TYPES] + [flip(board.pieces_mask(t, not turn)) for t in _TYPES]
    cast = (board.has_kingside_castling_rights(turn) | board.has_queenside_castling_rights(turn) << 1
            | board.has_kingside_castling_rights(not turn) << 2 | board.has_queenside_castling_rights(not turn) << 3)
    return tuple(bbs), int(cast)


def pack(f: Features) -> bytes:
    return struct.pack("<12QB", *f[0], f[1])


def unpack(blob: bytes) -> Features:
    v = struct.unpack("<12QB", blob)
    return tuple(v[:12]), v[12]


def _i64(b: bytes) -> int:
    return int.from_bytes(hashlib.sha256(b).digest()[:8], "big", signed=True)


def keys(f: Features) -> Dict[str, int]:
    bbs, cast = f
    counts = tuple(pop(bbs[i]) for i in (0, 1, 2, 3, 4, 6, 7, 8, 9, 10))
    return {"exact": _i64(pack(f)), "pawns": _i64(struct.pack("<2Q", bbs[0], bbs[6])),
            "material": _i64(bytes(counts))}


def _jac(a: int, b: int) -> float:
    u = pop(a | b)
    return 1.0 if u == 0 else pop(a & b) / u


def _l1sim(a, b) -> float:
    m = sum(max(x, y) for x, y in zip(a, b))
    return 1.0 if m == 0 else 1.0 - sum(abs(x - y) for x, y in zip(a, b)) / m


def similarity(fa: Features, fb: Features) -> Tuple[float, Dict[str, float]]:
    A, B = fa[0], fb[0]
    pl_i = sum(pop(a & b) for a, b in zip(A, B))
    pl_u = sum(pop(a | b) for a, b in zip(A, B))
    comp = {"placement": 1.0 if pl_u == 0 else pl_i / pl_u}
    idx = (0, 1, 2, 3, 4, 6, 7, 8, 9, 10)
    comp["material"] = _l1sim([pop(A[i]) for i in idx], [pop(B[i]) for i in idx])
    comp["pawns"] = (_jac(A[0], B[0]) + _jac(A[6], B[6])) / 2
    kd = [1 - chess.square_distance(chess.msb(A[k]), chess.msb(B[k])) / 7 for k in (5, 11) if A[k] and B[k]]
    comp["kings"] = sum(kd) / len(kd) if kd else 0.0
    comp["castling"] = sum(1 for i in range(4) if (fa[1] >> i & 1) == (fb[1] >> i & 1)) / 4
    zs = 0.0
    for lo in (1, 7):   # own N,B,R,Q = idx 1..4 ; opp = 7..10
        pa = A[lo] | A[lo + 1] | A[lo + 2] | A[lo + 3]
        pb = B[lo] | B[lo + 1] | B[lo + 2] | B[lo + 3]
        zs += _l1sim([pop(pa & z) for z in _ZONE_MASKS], [pop(pb & z) for z in _ZONE_MASKS])
    comp["pieces"] = zs / 2
    oa = [A[i] & _CENTER for i in range(12)]
    ob = [B[i] & _CENTER for i in range(12)]
    own_a, opp_a = 0, 0
    for i in range(6):
        own_a |= oa[i]
        opp_a |= oa[6 + i]
    own_b, opp_b = 0, 0
    for i in range(6):
        own_b |= ob[i]
        opp_b |= ob[6 + i]
    ju = pop(own_a | own_b) + pop(opp_a | opp_b)
    comp["center"] = 1.0 if ju == 0 else (pop(own_a & own_b) + pop(opp_a & opp_b)) / ju
    score = sum(WEIGHTS[k] * v for k, v in comp.items())
    return score, comp


def is_exact(fa: Features, fb: Features) -> bool:
    return fa == fb
