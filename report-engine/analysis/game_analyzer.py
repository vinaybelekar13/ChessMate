from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from database.database import SessionLocal
from database.models import Game, GameMove
from analysis.stockfish_engine import StockfishEngine


FAST_DEPTH = 10
DEEP_DEPTH = 18

CRITICAL_CPL = 50


def analyze_move(engine, move):
    before = engine.analyze(move.fen_before)
    after = engine.analyze(move.fen_after)

    score_before = before["score_cp"]
    score_after = after["score_cp"]

    if move.color == "w":
        centipawn_loss = score_before - score_after
    else:
        centipawn_loss = score_after - score_before

    centipawn_loss = max(0.0, float(centipawn_loss))

    return {
        "evaluation_before": score_before,
        "evaluation_after": score_after,
        "best_move": before["best_move"],
        "best_pv": " ".join(before["pv"]),
        "centipawn_loss": centipawn_loss,
        "fast": before,
    }


def classify_move(cpl):
    if cpl <= 10:
        return "best"
    if cpl <= 30:
        return "excellent"
    if cpl <= 60:
        return "good"
    if cpl <= 100:
        return "inaccuracy"
    if cpl <= 200:
        return "mistake"
    return "blunder"


def main():
    session = SessionLocal()

    try:
        move = session.scalars(
            select(GameMove)
            .join(Game)
            .order_by(Game.played_at.desc(), GameMove.ply)
        ).first()

        if move is None:
            raise SystemExit("NO_GAME_MOVES_FOUND")

        print("Testing move:")
        print("Game ID:", move.game_id)
        print("Ply:", move.ply)
        print("Move:", move.san)
        print("Color:", move.color)

        engine = StockfishEngine(depth=FAST_DEPTH)

        try:
            result = analyze_move(engine, move)

            print("ANALYSIS_PIPELINE_OK")
            print("Evaluation before:", result["evaluation_before"])
            print("Evaluation after:", result["evaluation_after"])
            print("Best move:", result["best_move"])
            print("CPL:", result["centipawn_loss"])
            print("Classification:", classify_move(result["centipawn_loss"]))

        finally:
            engine.close()

    finally:
        session.close()


if __name__ == "__main__":
    main()
