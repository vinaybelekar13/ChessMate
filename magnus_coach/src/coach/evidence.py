"""Coach evidence engine (Phase 17): deterministic, structured, grounded.

    position + user move
      -> Stockfish (compare_moves) -> Magnus model -> historical retrieval
      -> tactical analysis (board calculation) -> consequence chain + annotations

No natural-language explanation is generated here. The `consequence_chain` is a
list of short factual claims, EACH with a `source` (engine | board | model |
history) and an `evidence` pointer to the data that supports it. Anything that
cannot be supported is simply absent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import chess

from src.chess_core import tactics as T
from . import annotations as A
from .compare import compare_moves, parse_move
from .services import Services

MISTAKE_LABELS = ("inaccuracy", "mistake", "blunder")
FORCING_MOTIFS = ("mate_in_one", "back_rank_mate", "fork", "double_attack", "discovered_attack", "discovered_check",
                  "overloaded_piece", "hanging_piece")


def non_pawn_material(board: chess.Board) -> int:
    return sum(T.VAL[p.piece_type] for p in board.piece_map().values() if p.piece_type not in (chess.PAWN, chess.KING))


def material_balance(board: chess.Board, color: bool) -> int:
    """Piece-value balance (pawns) from `color`'s view."""
    return sum((1 if p.color == color else -1) * T.VAL[p.piece_type] for p in board.piece_map().values()
               if p.piece_type != chess.KING)


def _claim(claims: List[dict], claim: str, source: str, evidence: str):
    claims.append({"id": len(claims) + 1, "claim": claim, "source": source, "evidence": evidence})


def _reply_facts(board_after: chess.Board, reply_uci: Optional[str], tactics_after: dict) -> Optional[dict]:
    if not reply_uci:
        return None
    mv = chess.Move.from_uci(reply_uci)
    if mv not in board_after.legal_moves:
        return None
    victim = board_after.piece_at(mv.to_square)
    san = board_after.san(mv)
    b3 = board_after.copy(stack=False)
    b3.push(mv)
    match = [o for o in tactics_after["opponent_opportunities"] if o["trigger_move"] == reply_uci]
    return {"uci": reply_uci, "san": san, "is_capture": board_after.is_capture(mv),
            "captured_piece": victim.symbol() if victim else ("P" if board_after.is_en_passant(mv) else None),
            "gives_check": b3.is_check(), "is_checkmate": b3.is_checkmate(), "fen_after_reply": b3.fen(),
            "matching_tactics": match,
            "capture_see": T.see_capture(board_after, mv.from_square, mv.to_square) if board_after.is_capture(mv) else None}


def generate_coach_evidence(fen: str, user_move: str, services: Services, depth: Optional[int] = None,
                            previous_moves=None, time_control: Optional[str] = None, history_k: int = 10,
                            game_context: Optional[dict] = None) -> Dict[str, Any]:
    board = chess.Board(fen)
    mv = parse_move(board, user_move)
    cmp = compare_moves(fen, mv.uci(), services, depth, history_k=history_k, previous_moves=previous_moves,
                        time_control=time_control)
    eng, label = cmp["engine"], cmp["classification"]["label"]
    mover = board.turn
    best_uci = eng["best_move"]["uci"]
    user_is_best = eng["user_move_is_engine_best"]

    before = T.analyze_tactics(board)
    after = T.tactics_after_move(board, mv)
    board_after = chess.Board(after["fen_after"])
    reply = _reply_facts(board_after, eng["opponent_best_reply"]["uci"] if eng["opponent_best_reply"] else None, after)
    alt_after = None if user_is_best else T.tactics_after_move(board, chess.Move.from_uci(best_uci))

    hanging_before = {h["target_squares"][0] for h in before["hanging"][chess.COLOR_NAMES[mover]]}
    new_hanging = [h for h in after["own_pieces_hanging_after"] if h["target_squares"][0] not in hanging_before]
    missed = [o for o in before["opportunities_for_side_to_move"]
              if o["trigger_move"] and o["trigger_move"] != mv.uci() and o["motif"] in FORCING_MOTIFS]
    threats_ignored = [t for t in before["threats_against_side_to_move"] if t["trigger_move"] and
                       any(o["trigger_move"] == t["trigger_move"] for o in after["opponent_opportunities"])]

    motifs = sorted({m["motif"] for m in (reply["matching_tactics"] if reply else [])} | {"hanging_piece" for _ in new_hanging}
                    | {t["motif"] for t in threats_ignored})
    missed_motifs = sorted({f"missed_{o['motif']}" for o in missed})
    if label in MISTAKE_LABELS:
        motifs = sorted(set(motifs) | set(missed_motifs))      # a missed forcing tactic is its own concept
        if motifs or after["opponent_opportunities"] and any(o["motif"] in FORCING_MOTIFS for o in after["opponent_opportunities"]):
            category = "tactical"
        elif board.fullmove_number <= 10:
            category = "opening"
        elif non_pawn_material(board) <= 24:
            category = "endgame"
        elif reply and (reply["is_capture"] or reply["gives_check"]):
            category = "calculation"
        else:
            category = "positional"
    else:
        category = None

    changes = {
        "material_balance_before_for_mover": material_balance(board, mover),
        "material_balance_after_user_move_for_mover": material_balance(board_after, mover),
        "material_balance_after_opponent_best_reply_for_mover":
            material_balance(chess.Board(reply["fen_after_reply"]), mover) if reply else None,
        "new_own_pieces_hanging": new_hanging, "gives_check": after["gives_check"],
        "pins_and_skewers_after_move": after["pins_and_skewers_after"],
        "tactical_threats_against_mover_before_move": before["threats_against_side_to_move"],
    }

    claims: List[dict] = []
    e0, e1 = eng["evaluation_before"], eng["evaluation_after_user_move"]
    _claim(claims, f"{cmp['input']['user_move']['san']} is classified '{label}': engine evaluation for the mover goes from "
                   f"{e0['value_cp']} to {e1['value_cp']} centipawns (win probability loss {eng['win_pct_loss']} points, depth {eng['depth']})" + ("; " + "; ".join(eng['classification_adjustments']) if eng['classification_adjustments'] else "") + ".",
           "engine", "compare.engine.evaluation_before/evaluation_after_user_move")
    if reply:
        pv = " ".join(eng["principal_variation_after_user_move_san"][:6])
        _claim(claims, f"The engine's best reply is {reply['san']}; its line continues {pv}.", "engine",
               "compare.engine.opponent_best_reply/principal_variation_after_user_move_san")
        if reply["is_capture"]:
            _claim(claims, f"{reply['san']} captures a {T.piece_name(reply['captured_piece']) if reply['captured_piece'] else 'piece'} (static exchange {reply['capture_see']:+d} pawns for the capturer).",
                   "board", "reply.capture_see")
        for m in reply["matching_tactics"]:
            _claim(claims, f"Tactic after {reply['san']}: {m['consequence']}.", "board", f"reply.matching_tactics[{m['motif']}]")
        if reply["is_checkmate"]:
            _claim(claims, f"{reply['san']} is checkmate.", "board", "reply.is_checkmate")
    for h in new_hanging:
        _claim(claims, f"After your move, {T.piece_name(h['attacked_piece'])} on {h['target_squares'][0]} can be won by {T.piece_name(h['attacking_piece'])} on "
                       f"{h['source_square']} ({h['material_at_risk']} pawns at risk); it was not attackable this way before.",
               "board", "changes.new_own_pieces_hanging")
    for t in threats_ignored:
        _claim(claims, f"A threat already existed against you ({t['motif']} via {t['trigger_move']}) and your move does not address it.",
               "board", "changes.tactical_threats_against_mover_before_move")
    for o in missed[:3]:
        _claim(claims, f"A stronger tactical resource existed: {o['motif']} with {o['trigger_move']} — {o['consequence']}.",
               "board", f"missed_opportunities[{o['motif']}]")
    if not user_is_best:
        b = eng["best_move"]
        _claim(claims, f"Stockfish prefers {b['san']} (evaluation {e0['value_cp']}); line: {' '.join(eng['top_lines'][0]['pv_san'][:6])}.",
               "engine", "compare.engine.best_move/top_lines[0]")
    mm = cmp["magnus_model"]
    _claim(claims, f"The Magnus behavioural model ranks your move #{mm['user_move']['rank']} ({mm['user_move']['probability']:.1%}) and "
                   f"the engine's move #{mm['engine_best_move']['rank']} ({mm['engine_best_move']['probability']:.1%}); this is imitation of "
                   f"historical choices, not move quality.", "model", "compare.magnus_model")
    h = cmp["historical"]
    if h and h["n_legal_translations"]:
        _claim(claims, f"In {h['n_legal_translations']} similar stored Magnus positions, your move was played in "
                       f"{sum(1 for x in h['moves_in_query_frame'] if x['uci'] == mv.uci() for _ in range(x['count']))} and the engine's move in "
                       f"{sum(x['count'] for x in h['moves_in_query_frame'] if x['uci'] == best_uci)} (similarity is approximate).",
               "history", "compare.historical.moves_in_query_frame")

    # ---- annotations (all validated against the position they reference)
    ann: List[dict] = []
    fb, fa = board.fen(), after["fen_after"]
    ann.append(A.arrow(chess.square_name(mv.from_square), chess.square_name(mv.to_square), "user-move", fb, "user", "move played"))
    if not user_is_best:
        bm = chess.Move.from_uci(best_uci)
        ann.append(A.arrow(chess.square_name(bm.from_square), chess.square_name(bm.to_square), "best-move", fb, "engine", "engine best move"))
    if label in MISTAKE_LABELS:
        ann.append(A.highlight(chess.square_name(mv.to_square), "mistake", fa, "engine", f"{label}"))
    if reply:
        rm = chess.Move.from_uci(reply["uci"])
        ann.append(A.arrow(chess.square_name(rm.from_square), chess.square_name(rm.to_square),
                           "capture" if reply["is_capture"] else "threat", fa, "engine", "engine's best reply"))
        for m in reply["matching_tactics"]:
            ann.extend(a for a in A.from_tactic(m, fa) if a["type"] == "highlight")
    for h_ in new_hanging:
        ann.append(A.highlight(h_["target_squares"][0], "threat", fa, "board", "piece can be won"))
    ann = A.dedupe(ann)
    ann_check = A.validate_annotations(ann)

    return {
        "kind": "coach_evidence", "piece_notation": "uppercase = White piece, lowercase = Black piece",
        "position": {"fen": fb, "side_to_move": chess.COLOR_NAMES[mover], "move_number": board.fullmove_number,
                     "legal_moves_uci": sorted(m.uci() for m in board.legal_moves)},
        "user_move": cmp["input"]["user_move"],
        "classification": cmp["classification"],
        "comparison": cmp,
        "tactics": {"before": before, "after_user_move": after, "after_engine_best": alt_after},
        "opponent_reply": reply,
        "changes": changes,
        "missed_opportunities": missed,
        "motifs": motifs,
        "mistake_category": category,
        "concept_key": (motifs[0] if motifs else category),
        "consequence_chain": claims,
        "annotations": ann, "annotation_validation": ann_check,
        "game_context": game_context or {},
        "supported_motifs": list(T.SUPPORTED_MOTIFS), "unsupported_motifs": list(T.UNSUPPORTED_MOTIFS),
        "separation": {"engine": "comparison.engine", "model": "comparison.magnus_model",
                       "history": "comparison.historical", "board_calculation": "tactics/changes/opponent_reply"},
    }
