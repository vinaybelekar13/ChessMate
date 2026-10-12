from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datetime import datetime
import json

import chess
import chess.engine
from sqlalchemy import select

from database.database import SessionLocal
from database.models import EngineLine
from analysis.stockfish_engine import STOCKFISH_PATH


class EngineCache:
    def __init__(self, depth=14):
        self.depth = depth
        self.engine = chess.engine.SimpleEngine.popen_uci(
            str(STOCKFISH_PATH)
        )

    def _read_cache(self, session, fen, multipv):
        rows = session.scalars(
            select(EngineLine)
            .where(EngineLine.fen == fen)
            .order_by(EngineLine.multipv_rank)
        ).all()

        if len(rows) < multipv:
            return None

        rows = rows[:multipv]

        for row in rows:
            if row.depth < self.depth:
                return None

        return rows

    def _write_cache(self, session, fen, infos, depth):
        now = datetime.utcnow()

        for info in infos:
            rank = info.get("multipv", 1)
            pv = info.get("pv", [])

            move_uci = pv[0].uci() if pv else ""
            pv_json = json.dumps([move.uci() for move in pv])

            score = info["score"].white()

            if score.is_mate():
                eval_cp = None
                mate = score.mate()
            else:
                eval_cp = score.score()
                mate = None

            existing = session.scalar(
                select(EngineLine).where(
                    EngineLine.fen == fen,
                    EngineLine.multipv_rank == rank,
                )
            )

            if existing is None:
                session.add(
                    EngineLine(
                        fen=fen,
                        multipv_rank=rank,
                        move_uci=move_uci,
                        eval_cp=eval_cp,
                        mate=mate,
                        pv=pv_json,
                        depth=depth,
                        computed_at=now,
                    )
                )
            elif depth >= existing.depth:
                existing.move_uci = move_uci
                existing.eval_cp = eval_cp
                existing.mate = mate
                existing.pv = pv_json
                existing.depth = depth
                existing.computed_at = now

    def evaluate_position(self, fen, multipv=2):
        board = chess.Board(fen)
        session = SessionLocal()

        try:
            cached = self._read_cache(
                session,
                fen,
                multipv,
            )

            if cached is not None:
                return [
                    {
                        "rank": row.multipv_rank,
                        "move_uci": row.move_uci,
                        "eval_cp": row.eval_cp,
                        "mate": row.mate,
                        "pv": json.loads(row.pv),
                        "depth": row.depth,
                    }
                    for row in cached
                ]

            infos = self.engine.analyse(
                board,
                chess.engine.Limit(depth=self.depth),
                multipv=multipv,
            )

            self._write_cache(
                session,
                fen,
                infos,
                self.depth,
            )

            session.commit()

            return [
                {
                    "rank": info.get("multipv", index + 1),
                    "move_uci": (
                        info["pv"][0].uci()
                        if info.get("pv")
                        else None
                    ),
                    "eval_cp": (
                        info["score"].white()
                        .score()
                        if not info["score"].white().is_mate()
                        else None
                    ),
                    "mate": (
                        info["score"].white()
                        .mate()
                        if info["score"].white().is_mate()
                        else None
                    ),
                    "pv": [
                        move.uci()
                        for move in info.get("pv", [])
                    ],
                    "depth": self.depth,
                }
                for index, info in enumerate(infos)
            ]

        finally:
            session.close()

    def close(self):
        self.engine.quit()


def main():
    cache = EngineCache(depth=12)

    try:
        result = cache.evaluate_position(
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            multipv=2,
        )

        print("ENGINE_CACHE_OK")

        for line in result:
            print(
                "Rank:", line["rank"],
                "Move:", line["move_uci"],
                "Eval:", line["eval_cp"],
                "Mate:", line["mate"],
                "Depth:", line["depth"],
            )

    finally:
        cache.close()


if __name__ == "__main__":
    main()
