from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from database.database import SessionLocal
from database.models import Game
from analysis.full_game_analyzer import analyze_game


def main():
    session = SessionLocal()

    try:
        games = session.scalars(
            select(Game)
            .where(Game.analyzed == False)
            .order_by(
                Game.played_at.asc(),
                Game.id.asc(),
            )
        ).all()
    finally:
        session.close()

    total = len(games)

    if total == 0:
        print("NO_UNANALYZED_GAMES")
        return

    print("REPORT_BATCH_START")
    print("Games remaining:", total)
    print()

    completed = 0
    failed = 0
    started = time.time()

    for index, game in enumerate(games, start=1):
        game_id = game.id

        print(
            f"[{index}/{total}] "
            f"Game {game_id}: "
            f"{game.white} vs {game.black}"
        )

        try:
            result = analyze_game(game_id)

            completed += 1

            elapsed = time.time() - started
            average = elapsed / completed
            remaining = total - completed - failed
            eta_minutes = (average * remaining) / 60

            print(
                f"  OK | moves={result['moves']} "
                f"critical={result['critical']} "
                f"motifs={result['motifs']}"
            )
            print(
                f"  Progress={completed}/{total} "
                f"ETA={eta_minutes:.1f} min"
            )

        except Exception as exc:
            failed += 1

            print(
                f"  FAILED | {type(exc).__name__}: {exc}"
            )

            traceback.print_exc()

        print()

    elapsed_minutes = (time.time() - started) / 60

    print("REPORT_BATCH_COMPLETE")
    print("Completed:", completed)
    print("Failed:", failed)
    print("Total:", total)
    print(f"Elapsed minutes: {elapsed_minutes:.1f}")


if __name__ == "__main__":
    main()
