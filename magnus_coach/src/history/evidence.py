"""Historical move evidence (Phase 13).

Keeps three categories apart:
  historical_fact   - stored Magnus games/moves from the database (real records only)
  model_prediction  - optional, from the Magnus model
  engine_analysis   - optional, from Stockfish
Engine output is never described as what Magnus thought.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

import chess

from .database import MagnusDB


def historical_examples(fen: str, db: MagnusDB, top_k: int = 10, context: int = 3, **filters) -> List[Dict[str, Any]]:
    board = chess.Board(fen)
    out = []
    for r in db.find_similar_positions(fen, top_k, **filters):
        out.append({
            "historical_move": {**r["magnus_move"], "in_query_frame": r["magnus_move_in_query_frame"],
                                "legal_in_query_position": r["legal_in_query_position"], "mirrored": r["mirrored"]},
            "historical_game": {"game_id": r["game_id"], "ply": r["ply"], "move_number": r["move_number"],
                                "magnus_color": r["magnus_color"], "fen": r["fen"], **r["game"]},
            "surrounding_moves": db.surrounding_moves(r["game_id"], r["ply"], context, context),
            "similarity": {"score": r["similarity"], "components": r["similarity_components"],
                           "exact_board_match": r["exact_board_match"]},
            "provenance": r["provenance"],
        })
    return out


def historical_evidence(fen: str, db: MagnusDB, top_k: int = 5, engine=None, model_predictions: Optional[list] = None,
                        **filters) -> Dict[str, Any]:
    board = chess.Board(fen)
    ex = historical_examples(fen, db, top_k, **filters)
    counts = Counter(e["historical_move"]["in_query_frame"] for e in ex if e["historical_move"]["legal_in_query_position"])
    summary = [{"uci": u, "san": board.san(chess.Move.from_uci(u)), "count": c, "of": len(ex)} for u, c in counts.most_common()]
    return {
        "position": {"fen": board.fen(), "side_to_move": chess.COLOR_NAMES[board.turn]},
        "historical_fact": {"kind": "historical_fact", "examples": ex,
                            "move_counts_among_similar_positions": summary,
                            "note": "Counts are over the retrieved similar positions only, not over all of Magnus's games."},
        "model_prediction": {"kind": "model_prediction", "moves": model_predictions} if model_predictions is not None else None,
        "engine_analysis": engine.analyze(fen) if engine is not None else None,
        "separation_notice": "historical_fact = what Magnus actually played; model_prediction = a learned imitation; "
                             "engine_analysis = objective evaluation. They are independent signals.",
    }
