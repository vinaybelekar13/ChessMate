"""Deterministic tactical detection (Phase 20). No engine, no LLM.

Every finding is computed from board state and legal-move generation and
carries: motif, source/target squares, attacking and defending pieces,
consequence (a factual string built from those numbers), trigger move,
resulting FEN and supporting legal moves. If a motif cannot be established
reliably it is simply not reported (zwischenzug is NOT supported).

Piece values (pawns): P1 N3 B3 R5 Q9 K100. `see_capture` is a standard static
exchange evaluation: material won (+) or lost (-) by starting a capture
sequence on a square, always recapturing with the least valuable piece.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import re

import chess
from chess import BLACK, WHITE

VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}
_ORDER = (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING)
SUPPORTED_MOTIFS = ("fork", "double_attack", "pin", "skewer", "discovered_attack", "discovered_check",
                    "overloaded_piece", "hanging_piece", "back_rank_mate", "back_rank_weakness",
                    "mate_threat", "mate_in_one", "trapped_piece")
UNSUPPORTED_MOTIFS = ("zwischenzug",)


_NAMES = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen", "k": "king"}


def piece_name(symbol: str) -> str:
    """'N' -> 'white knight', 'n' -> 'black knight'."""
    return f"{'white' if symbol.isupper() else 'black'} {_NAMES[symbol.lower()]}"


def words(text: str) -> str:
    """Replace 'N on e5' / 'n @ c6' piece-symbol phrases by readable names (case encodes colour)."""
    return re.sub(r"(?<![A-Za-z])([KQRBNPkqrbnp]) (on|@) ", lambda m: f"{piece_name(m.group(1))} {m.group(2)} ", text)


def sq(s: int) -> str:
    return chess.square_name(s)


def pc(board: chess.Board, s: int) -> str:
    p = board.piece_at(s)
    return p.symbol() if p else "."


def _lsb(mask: int) -> int:
    return (mask & -mask).bit_length() - 1


def see_capture(board: chess.Board, frm: int, to: int) -> int:
    """Static exchange value (pawns) of `piece at frm` capturing on `to`."""
    p = board.piece_at(frm)
    if p is None:
        return 0
    occ = board.occupied & ~chess.BB_SQUARES[frm]
    victim = board.piece_at(to)
    if victim is not None:
        vval = VAL[victim.piece_type]
    elif p.piece_type == chess.PAWN and to == board.ep_square:
        vval = 1
        occ &= ~chess.BB_SQUARES[chess.square(chess.square_file(to), chess.square_rank(frm))]
    else:
        vval = 0
    gain, cur, color = [vval], VAL[p.piece_type], not p.color
    while len(gain) < 32:
        att = (board.attackers_mask(WHITE, to, occ) | board.attackers_mask(BLACK, to, occ)) & occ & board.occupied_co[color]
        if not att:
            break
        for pt in _ORDER:
            m = att & board.pieces_mask(pt, color)
            if m:
                break
        else:
            break
        s = _lsb(m)
        gain.append(cur - gain[-1])
        cur = VAL[pt]
        occ &= ~chess.BB_SQUARES[s]
        color = not color
    while len(gain) > 1:
        gain[-2] = -max(-gain[-2], gain[-1])
        gain.pop()
    return gain[0]


def _lva(board: chess.Board, target: int, by: bool) -> Optional[int]:
    best = None
    for a in board.attackers(by, target):
        if best is None or VAL[board.piece_type_at(a)] < VAL[board.piece_type_at(best)]:
            best = a
    return best


def winning_targets(board: chess.Board, by: bool) -> List[dict]:
    """Enemy non-king pieces that `by` could win material on (SEE > 0)."""
    out = []
    for t, p in board.piece_map().items():
        if p.color == by or p.piece_type == chess.KING:
            continue
        a = _lva(board, t, by)
        if a is not None:
            g = see_capture(board, a, t)
            if g > 0:
                out.append({"target": t, "attacker": a, "gain": g})
    return sorted(out, key=lambda d: d["target"])


def hanging_pieces(board: chess.Board, color: bool) -> List[dict]:
    """Pieces of `color` that the opponent wins material on (SEE > 0)."""
    res = []
    for w in winning_targets(board, not color):
        t, a = w["target"], w["attacker"]
        if board.color_at(t) != color:
            continue
        defenders = [sq(d) for d in board.attackers(color, t)]
        res.append({"motif": "hanging_piece", "color": chess.COLOR_NAMES[color], "source_square": sq(a),
                    "target_squares": [sq(t)], "attacking_piece": pc(board, a), "attacked_piece": pc(board, t),
                    "defending_pieces": [f"{pc(board, chess.parse_square(d))}@{d}" for d in defenders],
                    "material_at_risk": w["gain"],
                    "consequence": words(f"{pc(board, a)} on {sq(a)} wins material ({w['gain']} pawns by exchange) on {sq(t)}"),
                    "trigger_move": chess.Move(a, t).uci() if chess.Move(a, t) in board.pseudo_legal_moves else None,
                    "resulting_fen": None, "supporting_legal_moves": []})
    return res


def _copy_after(board: chess.Board, move: chess.Move) -> chess.Board:
    b = board.copy(stack=False)
    b.push(move)
    return b


def _finding(motif, board, color, source, targets, attacker, defenders, consequence, trigger=None, fen=None, moves=(), **extra):
    d = {"motif": motif, "color": chess.COLOR_NAMES[color], "source_square": source, "target_squares": list(targets),
         "attacking_piece": attacker, "defending_pieces": list(defenders), "consequence": words(consequence),
         "trigger_move": trigger, "resulting_fen": fen, "supporting_legal_moves": list(moves)}
    d.update(extra)
    return d


def mate_in_one(board: chess.Board) -> List[chess.Move]:
    out = []
    for m in board.legal_moves:
        board.push(m)
        if board.is_checkmate():
            out.append(m)
        board.pop()
    return out


def _rays(piece_type):
    if piece_type == chess.BISHOP:
        return ((1, 1), (1, -1), (-1, 1), (-1, -1))
    if piece_type == chess.ROOK:
        return ((1, 0), (-1, 0), (0, 1), (0, -1))
    return ((1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1))


def pins_and_skewers(board: chess.Board) -> List[dict]:
    """Static pins/skewers by sliders of either colour.

    front piece worth less than the piece behind -> pin (absolute if the rear piece is the king);
    front piece worth more than the rear piece   -> skewer.
    """
    res = []
    for s, p in board.piece_map().items():
        if p.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            continue
        for df, dr in _rays(p.piece_type):
            f, r, seen = chess.square_file(s) + df, chess.square_rank(s) + dr, []
            while 0 <= f < 8 and 0 <= r < 8 and len(seen) < 2:
                t = chess.square(f, r)
                if board.piece_at(t):
                    seen.append(t)
                f, r = f + df, r + dr
            if len(seen) < 2:
                continue
            a, b = seen
            if board.color_at(a) == p.color or board.color_at(b) == p.color:
                continue
            va, vb = VAL[board.piece_type_at(a)], VAL[board.piece_type_at(b)]
            if va == vb:
                continue
            kind = "pin" if va < vb else "skewer"
            absolute = board.piece_type_at(b) == chess.KING and kind == "pin"
            defenders = [f"{pc(board, d)}@{sq(d)}" for d in board.attackers(board.color_at(a), a)]
            res.append(_finding(
                kind, board, p.color, sq(s), [sq(a), sq(b)], pc(board, s), defenders,
                (f"{pc(board, s)} on {sq(s)} {'pins' if kind == 'pin' else 'skewers'} {pc(board, a)} on {sq(a)} "
                 f"against {pc(board, b)} on {sq(b)}" + (" (absolute pin: it cannot legally move off the line)" if absolute else "")),
                absolute=absolute, front_square=sq(a), rear_square=sq(b)))
    return res


def trapped_pieces(board: chess.Board, color: bool) -> List[dict]:
    res = []
    enemy = not color
    for s, p in board.piece_map().items():
        if p.color != color or p.piece_type in (chess.PAWN, chess.KING):
            continue
        a = _lva(board, s, enemy)
        if a is None or see_capture(board, a, s) <= 0 and VAL[board.piece_type_at(a)] >= VAL[p.piece_type]:
            continue
        b = board.copy(stack=False)
        b.turn = color
        b.ep_square = None
        escapes, tried = [], 0
        for mv in b.generate_pseudo_legal_moves(chess.BB_SQUARES[s]):
            tried += 1
            victim = board.piece_type_at(mv.to_square)
            b3 = b.copy(stack=False)
            b3.push(mv)
            a2 = _lva(b3, mv.to_square, enemy)
            lost = see_capture(b3, a2, mv.to_square) if a2 is not None else 0
            if lost <= 0 or (victim and VAL[victim] >= VAL[p.piece_type]):
                escapes.append(mv.uci())
        if not escapes:
            res.append(_finding("trapped_piece", board, color, sq(a), [sq(s)], pc(board, a), [],
                                f"{pc(board, s)} on {sq(s)} is attacked by {pc(board, a)} on {sq(a)} and none of its "
                                f"{tried} moves reaches a safe square", None, None, [], piece=pc(board, s), moves_examined=tried))
    return res


def back_rank_weakness(board: chess.Board, color: bool) -> Optional[dict]:
    k = board.king(color)
    home = 0 if color == WHITE else 7
    if k is None or chess.square_rank(k) != home:
        return None
    step = 1 if color == WHITE else -1
    kf = chess.square_file(k)
    front = [chess.square(f, home + step) for f in (kf - 1, kf, kf + 1) if 0 <= f < 8]
    if not all(board.color_at(s) == color for s in front):
        return None
    enemy_heavy = [s for s, p in board.piece_map().items() if p.color != color and p.piece_type in (chess.ROOK, chess.QUEEN)]
    return _finding("back_rank_weakness", board, not color, sq(k), [sq(k)], "", [],
                    f"{chess.COLOR_NAMES[color]} king on {sq(k)} has no flight square: {', '.join(sq(s) for s in front)} "
                    f"are blocked by its own pieces", None, None, [],
                    enemy_heavy_pieces=[f"{pc(board, s)}@{sq(s)}" for s in enemy_heavy])


def opportunities(board: chess.Board) -> List[dict]:
    """Tactical resources available to the SIDE TO MOVE, each tied to a legal move."""
    us, them = board.turn, not board.turn
    res: List[dict] = []
    before = {w["target"] for w in winning_targets(board, us)}
    for mv in board.legal_moves:
        b2 = _copy_after(board, mv)
        fen2 = b2.fen()
        piece = board.piece_at(mv.from_square)
        mated = b2.is_checkmate()
        if mated:
            lastrank = chess.square_rank(b2.king(them)) == (0 if them == WHITE else 7)
            heavy_on_rank = piece.piece_type in (chess.ROOK, chess.QUEEN) and chess.square_rank(mv.to_square) == chess.square_rank(b2.king(them))
            res.append(_finding("back_rank_mate" if lastrank and heavy_on_rank else "mate_in_one", board, us, sq(mv.from_square),
                                [sq(b2.king(them))], piece.symbol(), [], f"{board.san(mv)} is checkmate", mv.uci(), fen2, [mv.uci()]))
            continue
        moved_safe = True
        a = _lva(b2, mv.to_square, them)
        if a is not None and see_capture(b2, a, mv.to_square) > 0:
            moved_safe = False
        # --- fork / double attack
        wt = [w for w in winning_targets(b2, us) if w["target"] not in before or True]
        by_moved = [w for w in wt if mv.to_square in b2.attackers(us, w["target"])
                    and see_capture(b2, mv.to_square, w["target"]) > 0]
        gives_check_by_moved = b2.is_check() and mv.to_square in b2.checkers()
        n_targets = len(by_moved) + (1 if gives_check_by_moved else 0)
        if moved_safe and n_targets >= 2:
            tg = [sq(w["target"]) for w in by_moved] + ([sq(b2.king(them))] if gives_check_by_moved else [])
            res.append(_finding("fork", board, us, sq(mv.to_square), tg, piece.symbol(),
                                [f"{pc(board, d)}@{sq(d)}" for w in by_moved for d in b2.attackers(them, w["target"])],
                                f"{board.san(mv)} attacks {', '.join(f'{pc(b2, chess.parse_square(t))} on {t}' for t in tg)} at once; "
                                f"the {piece.symbol()} on {sq(mv.to_square)} cannot be won by exchange", mv.uci(), fen2, [mv.uci()]))
        else:
            new = [w for w in wt if w["target"] not in before]
            if moved_safe and len(new) >= 2:
                res.append(_finding("double_attack", board, us, sq(mv.to_square), [sq(w["target"]) for w in new], piece.symbol(), [],
                                    f"{board.san(mv)} creates {len(new)} new threats to win material", mv.uci(), fen2, [mv.uci()]))
        # --- discovered attack / check
        for s2, p2 in board.piece_map().items():
            if p2.color != us or s2 == mv.from_square or p2.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
                continue
            for t in b2.attacks(s2) & ~board.attacks(s2) & b2.occupied_co[them]:
                if not chess.between(s2, t) & chess.BB_SQUARES[mv.from_square]:
                    continue
                if b2.piece_type_at(t) == chess.KING:
                    res.append(_finding("discovered_check", board, us, sq(s2), [sq(t)], p2.symbol(), [],
                                        f"moving {piece.symbol()} {sq(mv.from_square)}->{sq(mv.to_square)} uncovers check from {p2.symbol()} on {sq(s2)}",
                                        mv.uci(), fen2, [mv.uci()]))
                elif see_capture(b2, s2, t) > 0:
                    res.append(_finding("discovered_attack", board, us, sq(s2), [sq(t)], p2.symbol(),
                                        [f"{pc(b2, d)}@{sq(d)}" for d in b2.attackers(them, t)],
                                        f"moving {piece.symbol()} {sq(mv.from_square)}->{sq(mv.to_square)} uncovers {p2.symbol()} on {sq(s2)} attacking {pc(b2, t)} on {sq(t)}",
                                        mv.uci(), fen2, [mv.uci()]))
    # --- hanging pieces we can simply capture
    for h in hanging_pieces(board, them):
        if h["trigger_move"]:
            h["resulting_fen"] = _copy_after(board, chess.Move.from_uci(h["trigger_move"])).fen()
            h["supporting_legal_moves"] = [h["trigger_move"]] if chess.Move.from_uci(h["trigger_move"]) in board.legal_moves else []
            if h["supporting_legal_moves"]:
                res.append(h)
    res.extend(_overloads(board))
    return res


def _overloads(board: chess.Board) -> List[dict]:
    """Verified by simulation: capture, forced recapture by the overloaded defender, then a second win."""
    us, them = board.turn, not board.turn
    res = []
    attacked = [t for t, p in board.piece_map().items() if p.color == them and p.piece_type != chess.KING and board.attackers(us, t)]
    defenders: Dict[int, List[int]] = {}
    for t in attacked:
        ds = list(board.attackers(them, t))
        if len(ds) == 1:
            defenders.setdefault(ds[0], []).append(t)
    for d, targets in defenders.items():
        if len(targets) < 2 or board.piece_type_at(d) == chess.KING:
            continue
        for t1 in targets:
            for mv in board.legal_moves:
                if mv.to_square != t1:
                    continue
                b2 = _copy_after(board, mv)
                recap = [m for m in b2.legal_moves if m.from_square == d and m.to_square == t1]
                if not recap:
                    continue
                b3 = _copy_after(b2, recap[0])
                others = [t for t in targets if t != t1]
                won = [w for w in winning_targets(b3, us) if w["target"] in others]
                if won:
                    res.append(_finding("overloaded_piece", board, us, sq(d), [sq(t) for t in targets], pc(board, d), [],
                                        f"{pc(board, d)} on {sq(d)} is the only defender of {', '.join(sq(t) for t in targets)}; "
                                        f"after {board.san(mv)} it must recapture and {sq(won[0]['target'])} falls",
                                        mv.uci(), _copy_after(board, mv).fen(), [mv.uci(), recap[0].uci()], overloaded_square=sq(d)))
                    break
            else:
                continue
            break
    return res


def analyze_tactics(board: chess.Board) -> dict:
    """Full tactical picture of a position."""
    stm = board.turn
    threats = []
    if not board.is_check():
        nb = board.copy(stack=False)
        nb.push(chess.Move.null())
        threats = [t for t in opportunities(nb) if t["motif"] in ("mate_in_one", "back_rank_mate", "fork", "double_attack",
                                                                    "discovered_attack", "discovered_check", "overloaded_piece", "hanging_piece")]
        for t in threats:
            t["motif_role"] = "threat_if_it_were_opponent_to_move"
    return {
        "fen": board.fen(), "side_to_move": chess.COLOR_NAMES[stm],
        "opportunities_for_side_to_move": opportunities(board),
        "threats_against_side_to_move": threats,
        "hanging": {chess.COLOR_NAMES[c]: hanging_pieces(board, c) for c in (WHITE, BLACK)},
        "pins_and_skewers": pins_and_skewers(board),
        "trapped": trapped_pieces(board, WHITE) + trapped_pieces(board, BLACK),
        "back_rank_weakness": [w for w in (back_rank_weakness(board, WHITE), back_rank_weakness(board, BLACK)) if w],
        "unsupported_motifs": list(UNSUPPORTED_MOTIFS),
    }


def tactics_after_move(board: chess.Board, move: chess.Move) -> dict:
    """Consequences of playing `move`: what the OPPONENT can now do."""
    if move not in board.legal_moves:
        raise ValueError(f"{move.uci()} is not legal in {board.fen()}")
    mover = board.turn
    san = board.san(move)
    captured = board.piece_at(move.to_square)
    b2 = _copy_after(board, move)
    opp = opportunities(b2) if not b2.is_game_over() else []
    return {"move_san": san, "move_uci": move.uci(), "fen_after": b2.fen(), "gives_check": b2.is_check(),
            "is_checkmate": b2.is_checkmate(), "is_stalemate": b2.is_stalemate(),
            "captures": captured.symbol() if captured else None,
            "opponent_opportunities": opp,
            "own_pieces_hanging_after": hanging_pieces(b2, mover),
            "pins_and_skewers_after": pins_and_skewers(b2)}


def is_tactical_position(board: chess.Board) -> bool:
    """Deterministic tactical/quiet split used by evaluation: in check, or the side to move
    has a capture that wins material by static exchange."""
    return board.is_check() or bool(winning_targets(board, board.turn))
