import chess.pgn
from pathlib import Path
from collections import Counter

PGN_PATH = Path("data/raw/carlsen/Carlsen.pgn")

total_games = 0
valid_games = 0
invalid_games = 0

years = Counter()
events = Counter()
results = Counter()
colors = Counter()

total_positions = 0
moves_per_game = []

with PGN_PATH.open("r", encoding="utf-8", errors="replace") as f:
    while True:
        try:
            game = chess.pgn.read_game(f)
        except Exception as e:
            invalid_games += 1
            continue

        if game is None:
            break

        total_games += 1

        headers = game.headers

        try:
            board = game.board()
            move_count = 0

            for move in game.mainline_moves():
                if move not in board.legal_moves:
                    raise ValueError("Illegal move")
                board.push(move)
                move_count += 1

            valid_games += 1
            total_positions += move_count

            moves_per_game.append(move_count)

            date = headers.get("Date", "")
            if date:
                years[date[:4]] += 1

            events[headers.get("Event", "Unknown")] += 1
            results[headers.get("Result", "*")] += 1

            white = headers.get("White", "")
            black = headers.get("Black", "")

            if "Carlsen" in white:
                colors["White"] += 1
            elif "Carlsen" in black:
                colors["Black"] += 1

        except Exception:
            invalid_games += 1


print("=" * 60)
print("MAGNUS CARLSEN PGN DATASET INSPECTION")
print("=" * 60)

print(f"\nPGN file       : {PGN_PATH}")
print(f"Total games    : {total_games}")
print(f"Valid games    : {valid_games}")
print(f"Invalid games  : {invalid_games}")
print(f"Total positions: {total_positions}")

if moves_per_game:
    print(f"Avg plies/game : {sum(moves_per_game) / len(moves_per_game):.2f}")
    print(f"Min plies/game : {min(moves_per_game)}")
    print(f"Max plies/game : {max(moves_per_game)}")

print("\n--- COLORS ---")
for key, value in colors.items():
    print(f"{key:10}: {value}")

print("\n--- RESULTS ---")
for key, value in results.most_common():
    print(f"{key:10}: {value}")

print("\n--- YEARS ---")
for key, value in sorted(years.items()):
    print(f"{key}: {value}")

print("\n--- TOP EVENTS ---")
for key, value in events.most_common(20):
    print(f"{value:5}  {key}")

print("\n" + "=" * 60)