import csv
import json
import re
from pathlib import Path

import chess
import chess.pgn


ROOT = Path(__file__).resolve().parents[2]

PGN_PATH = ROOT / "data" / "raw" / "carlsen" / "Carlsen.pgn"
CSV_PATH = ROOT / "data" / "raw" / "DrNykterstein.csv"

OUTPUT_DIR = ROOT / "data" / "cleaned"
OUTPUT_PATH = OUTPUT_DIR / "magnus_games.jsonl"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------
# SAN CLEANING
# ---------------------------------------------------------

def clean_san(token):
    """
    Convert values such as:
        1.e4   -> e4
        1.c5   -> c5
        2.Nc3  -> Nc3
        10...Qe7 -> Qe7
    """

    if token is None:
        return None

    token = str(token).strip()

    if not token or token.lower() == "nan":
        return None

    # Remove move number at beginning.
    token = re.sub(r"^\d+\.(?:\.\.)?", "", token).strip()

    return token if token else None


# ---------------------------------------------------------
# PGN MENTOR
# ---------------------------------------------------------

def extract_pgn_games():
    games = []

    print("Reading PGN Mentor...")

    with open(PGN_PATH, "r", encoding="utf-8", errors="ignore") as f:

        game_count = 0

        while True:

            game = chess.pgn.read_game(f)

            if game is None:
                break

            game_count += 1

            board = game.board()
            moves = []

            try:

                for move in game.mainline_moves():
                    moves.append(move.uci())
                    board.push(move)

            except Exception as e:

                print(f"Skipping PGN game {game_count}: {e}")
                continue

            headers = game.headers

            games.append(
                {
                    "source": "pgnmentor",
                    "white": headers.get("White", ""),
                    "black": headers.get("Black", ""),
                    "result": headers.get("Result", ""),
                    "date": headers.get("Date", ""),
                    "event": headers.get("Event", ""),
                    "site": headers.get("Site", ""),
                    "eco": headers.get("ECO", ""),
                    "opening": headers.get("Opening", ""),
                    "time_control": headers.get("TimeControl", ""),
                    "moves": moves,
                }
            )

    print(f"PGN Mentor games: {len(games)}")

    return games


# ---------------------------------------------------------
# LICHESS CSV
# ---------------------------------------------------------

def extract_lichess_games():

    games = []

    print()
    print("Reading DrNykterstein CSV...")

    parse_failures = 0
    first_failures = []

    with open(
        CSV_PATH,
        "r",
        encoding="utf-8",
        errors="ignore",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row_index, row in enumerate(reader, start=2):

            board = chess.Board()

            moves = []

            failed = False

            # Dataset contains w1/b1 ... w103/b103
            for move_number in range(1, 104):

                white_token = clean_san(
                    row.get(f"w{move_number}")
                )

                black_token = clean_san(
                    row.get(f"b{move_number}")
                )

                # White move
                if white_token:

                    try:

                        move = board.parse_san(white_token)

                        moves.append(move.uci())

                        board.push(move)

                    except Exception as e:

                        parse_failures += 1
                        failed = True

                        if len(first_failures) < 5:

                            first_failures.append(
                                (
                                    row_index,
                                    f"w{move_number}",
                                    white_token,
                                    str(e),
                                )
                            )

                        break

                # Black move
                if black_token:

                    try:

                        move = board.parse_san(black_token)

                        moves.append(move.uci())

                        board.push(move)

                    except Exception as e:

                        parse_failures += 1
                        failed = True

                        if len(first_failures) < 5:

                            first_failures.append(
                                (
                                    row_index,
                                    f"b{move_number}",
                                    black_token,
                                    str(e),
                                )
                            )

                        break

            if failed:
                continue

            if not moves:
                continue

            games.append(
                {
                    "source": "lichess",
                    "white": row.get("White", ""),
                    "black": row.get("Black", ""),
                    "result": row.get("Result", ""),
                    "date": row.get("Date", ""),
                    "event": row.get("Event", ""),
                    "site": row.get("Site", ""),
                    "eco": row.get("ECO", ""),
                    "opening": row.get("Opening", ""),
                    "time_control": row.get("TimeControl", ""),
                    "variant": row.get("Variant", ""),
                    "moves": moves,
                }
            )

    print(f"Lichess games: {len(games)}")

    if parse_failures:

        print(f"Lichess parse failures: {parse_failures}")

        print("First parse failures:")

        for failure in first_failures:

            print(
                f"  row={failure[0]} "
                f"column={failure[1]} "
                f"move={failure[2]} "
                f"error={failure[3]}"
            )

    return games


# ---------------------------------------------------------
# DEDUPLICATION
# ---------------------------------------------------------

def deduplicate_games(games):

    unique = {}

    for game in games:

        # Full UCI sequence is used as the identity.
        # This catches duplicate games even if metadata differs.
        move_key = " ".join(game["moves"])

        if not move_key:
            continue

        if move_key not in unique:

            unique[move_key] = game

        else:

            # Preserve information that the game exists in
            # multiple public sources.
            existing = unique[move_key]

            sources = set()

            sources.add(existing.get("source", ""))

            sources.add(game.get("source", ""))

            existing["sources"] = sorted(
                source for source in sources if source
            )

    return list(unique.values())


# ---------------------------------------------------------
# SAVE
# ---------------------------------------------------------

def save_games(games):

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        for index, game in enumerate(games, start=1):

            game["game_id"] = f"magnus_{index:06d}"

            if "sources" not in game:

                game["sources"] = [
                    game.get("source", "")
                ]

            f.write(
                json.dumps(
                    game,
                    ensure_ascii=False
                )
                + "\n"
            )


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    pgn_games = extract_pgn_games()

    lichess_games = extract_lichess_games()

    all_games = pgn_games + lichess_games

    print()
    print(f"Raw combined games: {len(all_games)}")

    unique_games = deduplicate_games(all_games)

    duplicates_removed = (
        len(all_games) - len(unique_games)
    )

    total_plies = sum(
        len(game["moves"])
        for game in unique_games
    )

    print(f"Duplicates removed: {duplicates_removed}")

    print(f"Unique games: {len(unique_games)}")

    print(f"Total plies: {total_plies}")

    save_games(unique_games)

    print()
    print("Saved corpus:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()