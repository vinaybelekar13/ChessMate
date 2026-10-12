from pathlib import Path
import chess
import chess.engine


PROJECT_ROOT = Path(__file__).resolve().parents[3]

STOCKFISH_PATH = (
    PROJECT_ROOT
    / "engines"
    / "stockfish"
    / "stockfish-windows-x86-64-universal.exe"
)


class StockfishEngine:
    def __init__(self, depth=16):
        self.depth = depth
        self.engine = chess.engine.SimpleEngine.popen_uci(
            str(STOCKFISH_PATH)
        )

    def analyze(self, fen):
        board = chess.Board(fen)

        result = self.engine.analyse(
            board,
            chess.engine.Limit(depth=self.depth),
        )

        score = result["score"].pov(board.turn)

        return {
            "score_cp": score.score(mate_score=100000),
            "mate": score.mate(),
            "best_move": result["pv"][0].uci() if result.get("pv") else None,
            "pv": [move.uci() for move in result.get("pv", [])],
            "depth": self.depth,
        }

    def close(self):
        self.engine.quit()


def main():
    engine = StockfishEngine(depth=12)

    try:
        result = engine.analyze(
            "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
        )

        print("STOCKFISH_ENGINE_OK")
        print("Score:", result["score_cp"])
        print("Mate:", result["mate"])
        print("Best move:", result["best_move"])
        print("PV:", " ".join(result["pv"][:8]))
        print("Depth:", result["depth"])

    finally:
        engine.close()


if __name__ == "__main__":
    main()
