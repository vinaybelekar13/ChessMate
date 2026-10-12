from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import chess
import json
import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "trainer_puzzles.sqlite3")

app = Flask(__name__)
CORS(app)

def connect_db():
    con = sqlite3.connect(
        f"file:{DB_PATH}?mode=ro",
        uri=True,
        timeout=10
    )
    con.row_factory = sqlite3.Row
    return con

def puzzle_dict(row):
    item = dict(row)
    item["themes"] = (item.get("themes") or "").split()
    item["moves_uci"] = (item.get("moves_uci") or "").split()
    return item

@app.get("/api/health")
def health():
    return jsonify({
        "ok": os.path.isfile(DB_PATH),
        "database": "trainer_puzzles.sqlite3",
        "read_only": True
    })

@app.get("/api/puzzle")
def get_puzzle():
    try:
        minimum = max(0, min(3500, int(request.args.get("min_rating", 0))))
        maximum = max(minimum, min(3500, int(request.args.get("max_rating", 3500))))
        theme = request.args.get("theme", "").strip()
        source = request.args.get("source", "lichess").strip()
        limit = 1

        conditions = [
            "rating BETWEEN ? AND ?",
            "source = ?",
            "rating IS NOT NULL",
            "fen != ''",
            "moves_uci != ''"
        ]
        params = [minimum, maximum, source]

        if theme:
            # Themes are space-separated tokens in the existing database.
            conditions.append("(' ' || themes || ' ') LIKE ?")
            params.append("% " + theme + " %")

        where = " AND ".join(conditions)

        with connect_db() as con:
            # Random row selection from millions of records can be expensive.
            # Select a random puzzle ID from a bounded candidate sample instead.
            candidates = con.execute(
                f"""
                SELECT source, puzzle_id, rating, popularity
                FROM puzzles
                WHERE {where}
                ORDER BY popularity DESC
                LIMIT 500
                """,
                params
            ).fetchall()

            if not candidates:
                return jsonify({"error": "No puzzles match these filters"}), 404

            chosen = random.choice(candidates)
            row = con.execute(
                """
                SELECT source, puzzle_id, fen, moves_uci, rating,
                       rating_deviation, popularity, nb_plays, themes,
                       game_url, opening_tags, daily_date
                FROM puzzles
                WHERE source = ? AND puzzle_id = ?
                """,
                (chosen["source"], chosen["puzzle_id"])
            ).fetchone()

        return jsonify(puzzle_dict(row))
    except (ValueError, sqlite3.Error) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/legal-moves")
def legal_moves():
    data = request.get_json(silent=True) or {}
    try:
        board = chess.Board(data.get("fen", ""))
        return jsonify({
            "moves": [
                {
                    "uci": move.uci(),
                    "from": chess.square_name(move.from_square),
                    "to": chess.square_name(move.to_square),
                    "promotion": chess.piece_symbol(move.promotion) if move.promotion else None
                }
                for move in board.legal_moves
            ]
        })
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

@app.post("/api/validate")
def validate_move():
    data = request.get_json(silent=True) or {}
    fen = data.get("fen", "")
    uci = data.get("uci", "")

    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            return jsonify({"legal": False, "error": "Illegal move"}), 400
        san = board.san(move)
        board.push(move)
        return jsonify({
            "legal": True,
            "fen": board.fen(),
            "san": san
        })
    except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError) as exc:
        return jsonify({"legal": False, "error": str(exc)}), 400

@app.post("/api/solution-check")
def solution_check():
    data = request.get_json(silent=True) or {}
    puzzle_id = str(data.get("puzzle_id", ""))
    source = str(data.get("source", "lichess"))
    moves = data.get("moves", [])

    if not puzzle_id or not isinstance(moves, list):
        return jsonify({"error": "puzzle_id and moves are required"}), 400

    with connect_db() as con:
        row = con.execute(
            "SELECT fen, moves_uci FROM puzzles WHERE source = ? AND puzzle_id = ?",
            (source, puzzle_id)
        ).fetchone()

    if row is None:
        return jsonify({"error": "Puzzle not found"}), 404

    expected = row["moves_uci"].split()
    # Puzzle FEN is the position before the first solution move.
    # Accept the player's submitted move sequence as a prefix of the solution.
    submitted = [str(move) for move in moves]
    correct = submitted == expected[:len(submitted)]
    complete = correct and len(submitted) == len(expected)

    return jsonify({
        "correct": correct,
        "complete": complete,
        "next_expected_move": expected[len(submitted)] if correct and not complete else None
    })

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8788, debug=False)
