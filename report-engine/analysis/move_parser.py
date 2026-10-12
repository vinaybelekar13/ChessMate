from pathlib import Path
import sys
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chess
import chess.pgn

from database.database import SessionLocal
from database.models import Game, GameMove
from sqlalchemy import select


CLOCK_RE = re.compile(r"\[%clk\s+([0-9:.]+)\]")


def clock_to_seconds(value):
    parts = value.split(":")

    if len(parts) == 3:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds

    if len(parts) == 2:
        minutes = float(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds

    return float(parts[0])


def extract_clock(comment):
    match = CLOCK_RE.search(comment or "")
    if not match:
        return None
    return clock_to_seconds(match.group(1))


def detect_phase(board):
    pieces = len(board.piece_map())

    if pieces <= 6:
        return "endgame"

    if board.fullmove_number <= 12:
        return "opening"

    return "middlegame"


def parse_time_control(value):
    if not value:
        return 0.0

    value = str(value).strip()

    if "+" not in value:
        return 0.0

    try:
        parts = value.split("+", 1)
        return float(parts[1])
    except (ValueError, IndexError):
        return 0.0


def parse_game(game):
    pgn = game.pgn

    import io
    parsed = chess.pgn.read_game(io.StringIO(pgn))

    if parsed is None:
        return [] 

    board = parsed.board()
    moves = []

    previous_clock = None
    ply = 0

    for move in parsed.mainline_moves():
        ply += 1

        fen_before = board.fen()
        san = board.san(move)
        uci = move.uci()

        node = None

        for candidate in board.legal_moves:
            if candidate == move:
                break

        board.push(move)

        node = parsed

        phase = detect_phase(board)

        clock = None

        moves.append({
            "ply": ply,
            "move_number": (ply + 1) // 2,
            "color": "w" if ply % 2 == 1 else "b",
            "san": san,
            "uci": uci,
            "fen_before": fen_before,
            "fen_after": board.fen(),
            "phase": phase,
            "clock_seconds": clock,
            "thinking_time": None,
        })

    return moves


def parse_game_with_clock(game):
    import io

    parsed = chess.pgn.read_game(io.StringIO(game.pgn))

    if parsed is None:
        return []

    board = parsed.board()
    moves = []

    ply = 0
    previous_clock = {
        "w": None,
        "b": None,
    }

    increment = parse_time_control(game.time_control)

    for node in parsed.mainline():
        move = node.move
        ply += 1

        color = "w" if board.turn == chess.WHITE else "b"

        fen_before = board.fen()
        san = board.san(move)

        clock = extract_clock(node.comment or "")

        thinking_time = None

        if clock is not None and previous_clock[color] is not None:
            thinking_time = (
                previous_clock[color]
                - clock
                + increment
            )

            if thinking_time < 0:
                thinking_time = 0.0

        if clock is not None:
            previous_clock[color] = clock

        board.push(move)

        moves.append({
            "ply": ply,
            "move_number": (ply + 1) // 2,
            "color": color,
            "san": san,
            "uci": move.uci(),
            "fen_before": fen_before,
            "fen_after": board.fen(),
            "phase": detect_phase(board),
            "clock_seconds": clock,
            "thinking_time": thinking_time,
        })

    return moves


def main():
    session = SessionLocal()

    games = session.scalars(
        select(Game).order_by(Game.played_at.desc())
    ).all()

    total_games = 0
    total_moves = 0

    try:
        for game in games:
            session.query(GameMove).filter(
                GameMove.game_id == game.id
            ).delete()

            moves = parse_game_with_clock(game)

            for data in moves:
                session.add(
                    GameMove(
                        game_id=game.id,
                        ply=data["ply"],
                        move_number=data["move_number"],
                        color=data["color"],
                        san=data["san"],
                        uci=data["uci"],
                        fen_before=data["fen_before"],
                        fen_after=data["fen_after"],
                        phase=data["phase"],
                        clock_seconds=data["clock_seconds"],
                        thinking_time=data["thinking_time"],
                    )
                )

            total_games += 1
            total_moves += len(moves)

        session.commit()

    finally:
        session.close()

    print("MOVE_PARSER_OK")
    print("Games parsed:", total_games)
    print("Moves stored:", total_moves)


if __name__ == "__main__":
    main()
