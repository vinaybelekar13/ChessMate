"""Move comparison (Phase 16): FACTS ONLY, no prose.

compare_moves(fen, user_move) sets side by side
  USER MOVE | STOCKFISH | MAGNUS MODEL | HISTORICAL MAGNUS MOVES
and never merges them into one score.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

import chess

from src.chess_core.tactics import VAL, see_capture, _lva
from src.inference.api import predict_moves
from .services import Services


@dataclass
class ClassificationConfig:
    """Move classes by WIN-PROBABILITY loss (percentage points, Lichess transform of engine cp).
    Using win% instead of raw centipawns keeps lopsided positions from over-penalising."""
    best: float = 0.5
    excellent: float = 2.0
    good: float = 5.0
    playable: float = 10.0
    inaccuracy: float = 20.0
    mistake: float = 30.0          # above this = blunder
    brilliant_min_win_pct: float = 40.0   # sacrifice must leave the mover at least this well off
    # Win% saturates in decisive positions, so forced mates get explicit handling:
    missed_mate_loss: float = 25.0        # had a forced mate, move no longer keeps one  -> at least 'mistake'
    allowed_mate_loss: float = 50.0       # move walks into a forced mate against the mover -> 'blunder'


DEFAULT_CLASSIFICATION = ClassificationConfig()


def parse_move(board: chess.Board, text: str) -> chess.Move:
    """SAN or UCI -> legal Move, else ValueError."""
    for fn in (board.parse_san, chess.Move.from_uci):
        try:
            mv = fn(text.strip())
            if mv in board.legal_moves:
                return mv
        except ValueError:
            continue
    raise ValueError(f"{text!r} is not a legal move in {board.fen()}")


def classify(loss_win_pct: float, is_engine_best: bool, sacrifice: bool, win_after: float,
             cfg: ClassificationConfig = DEFAULT_CLASSIFICATION) -> str:
    if (is_engine_best or loss_win_pct <= cfg.best):
        return "brilliant" if sacrifice and win_after >= cfg.brilliant_min_win_pct else "best"
    for name in ("excellent", "good", "playable", "inaccuracy", "mistake"):
        if loss_win_pct <= getattr(cfg, name):
            return name
    return "blunder"


def is_sacrifice(board: chess.Board, mv: chess.Move) -> bool:
    """Moved piece (>= a minor piece) can be won by exchange on its destination."""
    piece = board.piece_at(mv.from_square)
    if piece is None or VAL[piece.piece_type] < 3 or piece.piece_type == chess.KING:
        return False
    b2 = board.copy(stack=False)
    b2.push(mv)
    a = _lva(b2, mv.to_square, b2.turn)
    return a is not None and see_capture(b2, a, mv.to_square) >= 2


def compare_moves(fen: str, user_move: str, services: Services, depth: Optional[int] = None,
                  history_k: int = 10, model_k: int = 5,
                  cfg: ClassificationConfig = DEFAULT_CLASSIFICATION, previous_moves=None,
                  time_control: Optional[str] = None) -> Dict[str, Any]:
    board = chess.Board(fen)
    mv = parse_move(board, user_move)
    uci, san = mv.uci(), board.san(mv)
    eng = services.engine
    before = eng.analyze(fen, depth)
    if before["game_over"]:
        raise ValueError("game is already over")
    best = before["best_move"]
    line = next((l for l in before["lines"] if l["move_uci"] == uci), None)
    after = eng.evaluate_move(fen, uci, depth)
    eval_after = line["score"] if line else after["score_for_mover"]
    eval_before = before["evaluation"]
    same_as_best = uci == best["uci"]
    loss = 0.0 if same_as_best else max(0.0, eval_before["win_pct"] - eval_after["win_pct"])
    adjusted, reasons = loss, []
    if not same_as_best:
        if (eval_before["mate"] or 0) > 0 and not ((eval_after["mate"] or 0) > 0):
            adjusted = max(adjusted, cfg.missed_mate_loss)
            reasons.append(f"engine found a forced mate in {eval_before['mate']}; the move no longer keeps a forced mate")
        if (eval_after["mate"] or 0) < 0 and not ((eval_before["mate"] or 0) < 0):
            adjusted = max(adjusted, cfg.allowed_mate_loss)
            reasons.append(f"the move allows a forced mate against the mover (mate in {abs(eval_after['mate'])})")
    sacrifice = is_sacrifice(board, mv)
    cls = classify(adjusted, same_as_best, sacrifice, eval_after["win_pct"], cfg)

    allm = predict_moves(fen, top_k=board.legal_moves.count(), previous_moves=previous_moves,
                         time_control=time_control, model_path=services.model_path)
    by_uci = {m["uci"]: m for m in allm}

    hist = None
    if services.db is not None:
        from src.history.evidence import historical_examples
        ex = historical_examples(fen, services.db, history_k)
        moves = [e["historical_move"]["in_query_frame"] for e in ex if e["historical_move"]["legal_in_query_position"]]
        hist = {"kind": "historical_fact", "examples": ex,
                "moves_in_query_frame": [{"uci": u, "san": board.san(chess.Move.from_uci(u)), "count": moves.count(u)}
                                         for u in dict.fromkeys(moves)],
                "user_move_played_by_magnus_in_similar_positions": uci in moves,
                "engine_best_played_by_magnus_in_similar_positions": best["uci"] in moves,
                "n_examples": len(ex), "n_legal_translations": len(moves)}

    return {
        "input": {"fen": board.fen(), "side_to_move": chess.COLOR_NAMES[board.turn], "user_move": {"uci": uci, "san": san}},
        "engine": {"kind": "engine_analysis", "depth": before["depth"], "engine": before["engine"],
                   "best_move": best, "top_lines": before["lines"],
                   "evaluation_before": eval_before, "evaluation_after_user_move": eval_after,
                   "evaluation_after_source": "multipv_line" if line else "child_position_search",
                   "evaluation_delta_cp": eval_after["value_cp"] - eval_before["value_cp"],
                   "win_pct_loss": round(loss, 3), "classification_loss": round(adjusted, 3),
                   "classification_adjustments": reasons, "user_move_is_engine_best": same_as_best,
                   "opponent_best_reply": after["best_reply"], "principal_variation_after_user_move_san": after["principal_variation_san"],
                   "principal_variation_after_user_move_uci": after["principal_variation_uci"],
                   "fen_after_user_move": after["fen_after"]},
        "classification": {"label": cls, "thresholds": asdict(cfg), "sacrifice_heuristic": sacrifice,
                           "basis": "engine win-probability loss, raised for missed/allowed forced mates (see thresholds and engine.classification_adjustments)"},
        "magnus_model": {"kind": "model_prediction", "candidates": allm[:model_k],
                         "user_move": by_uci[uci], "engine_best_move": by_uci[best["uci"]]},
        "historical": hist,
        "agreement": {"user_equals_engine_best": same_as_best,
                      "user_equals_model_top1": uci == allm[0]["uci"],
                      "user_in_model_top5": by_uci[uci]["rank"] <= 5,
                      "engine_best_equals_model_top1": best["uci"] == allm[0]["uci"],
                      "engine_best_model_rank": by_uci[best["uci"]]["rank"],
                      "user_move_in_similar_history": None if hist is None else hist["user_move_played_by_magnus_in_similar_positions"],
                      "engine_best_in_similar_history": None if hist is None else hist["engine_best_played_by_magnus_in_similar_positions"]},
        "separation_notice": "engine, model and history are reported independently and never merged into one score",
    }
