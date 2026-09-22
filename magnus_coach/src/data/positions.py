"""Magnus decision-position records: creation and validation.

One record per position where MAGNUS is to move. The label is always the
historical Magnus move; no engine is involved anywhere.

Field conventions
-----------------
ply            1-based ply index of the target move (1 = White's first move)
move_number    fullmove number of the position (== board.fullmove_number)
last_5_moves_uci  up to 5 moves played BEFORE this position, oldest -> newest
next_moves_uci    up to 5 moves played AFTER the target move, in order
legal_moves_uci   every legal move in fen_before, sorted alphabetically
speed          classical | rapid | blitz | bullet | ultrabullet | unknown
               ('unknown' = the source gave no time control; it is NOT
               assumed to be classical)
"""

from __future__ import annotations

import re
from typing import Dict, Iterator, List

import chess

SPEED_LABEL = {"unspecified": "unknown"}  # corpus label -> dataset label
SPEEDS = ("classical", "rapid", "blitz", "bullet", "ultrabullet", "unknown")

REQUIRED_FIELDS = (
    "game_id", "source", "date", "event", "site", "white", "black", "magnus_color",
    "opponent", "result", "ply", "move_number", "fen_before", "last_5_moves_uci",
    "target_move_uci", "target_move_san", "legal_moves_uci", "time_control", "ECO", "opening",
)


class GameReplayError(Exception):
    """A stored game could not be replayed legally."""


def year_of(date: str):
    m = re.match(r"^(\d{4})", date or "")
    return int(m.group(1)) if m else None


def game_speed(game: dict) -> str:
    s = game.get("speed", "unspecified")
    return SPEED_LABEL.get(s, s)


def make_records(game: dict, split: str) -> Iterator[Dict]:
    """Yield one record per Magnus decision by replaying the game.

    Raises GameReplayError (before yielding anything wrong) if a stored move is
    not legal; the caller must then exclude the whole game.
    """
    if game["start_fen"] != chess.STARTING_FEN:
        raise GameReplayError("non-standard start position (ply numbering assumes the standard start)")
    board = chess.Board(game["start_fen"])
    moves: List[str] = game["moves"]
    magnus_white = game["magnus_color"] == "white"
    speed = game_speed(game)
    year = year_of(game.get("date", ""))
    for i, uci in enumerate(moves):
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as exc:
            raise GameReplayError(f"ply {i + 1}: bad UCI {uci!r}: {exc}") from exc
        if move not in board.legal_moves:
            raise GameReplayError(f"ply {i + 1}: illegal move {uci} in {board.fen()}")
        if (board.turn == chess.WHITE) == magnus_white:
            yield {
                "position_id": f"{game['game_id']}:{i + 1}",
                "game_id": game["game_id"],
                "source": game["source"],
                "sources": game.get("sources", [game["source"]]),
                "date": game.get("date", ""),
                "year": year,
                "event": game.get("event", ""),
                "site": game.get("site", ""),
                "white": game["white"],
                "black": game["black"],
                "white_elo": game.get("white_elo", ""),
                "black_elo": game.get("black_elo", ""),
                "magnus_color": game["magnus_color"],
                "opponent": game["opponent"],
                "result": game.get("result", ""),
                "ply": i + 1,
                "move_number": board.fullmove_number,
                "fen_before": board.fen(),
                "last_5_moves_uci": moves[max(0, i - 5):i],
                "target_move_uci": uci,
                "target_move_san": board.san(move),
                "next_moves_uci": moves[i + 1:i + 6],
                "legal_moves_uci": sorted(m.uci() for m in board.legal_moves),
                "time_control": game.get("time_control", ""),
                "speed": speed,
                "speed_basis": game.get("speed_basis", ""),
                "ECO": game.get("eco", ""),
                "opening": game.get("opening", ""),
                "split": split,
            }
        board.push(move)


def validate_position_record(rec: dict) -> List[str]:
    """Independent re-check of one record. Returns a list of failure codes ([] = valid).

    Derives everything again from `fen_before`; trusts nothing the builder computed.
    """
    errors: List[str] = []
    missing = [f for f in REQUIRED_FIELDS if f not in rec]
    if missing:
        return [f"missing_fields:{','.join(missing)}"]

    try:
        board = chess.Board(rec["fen_before"])
    except ValueError:
        return ["invalid_fen"]
    if board.fen() != rec["fen_before"] or not board.is_valid():
        errors.append("invalid_fen")

    if rec["magnus_color"] not in ("white", "black"):
        errors.append("bad_magnus_color")
    elif (board.turn == chess.WHITE) != (rec["magnus_color"] == "white"):
        errors.append("side_to_move_is_not_magnus")

    try:
        move = chess.Move.from_uci(rec["target_move_uci"])
    except ValueError:
        return errors + ["target_not_uci"]
    if move not in board.legal_moves:
        return errors + ["target_illegal"]
    if board.san(move) != rec["target_move_san"]:
        errors.append("san_mismatch")

    legal = sorted(m.uci() for m in board.legal_moves)
    if rec["target_move_uci"] not in rec["legal_moves_uci"]:
        errors.append("target_not_in_legal_moves_uci")
    if rec["legal_moves_uci"] != legal:
        errors.append("legal_moves_uci_mismatch")

    if rec["move_number"] != board.fullmove_number:
        errors.append("move_number_mismatch")
    expected_ply = 2 * (board.fullmove_number - 1) + (1 if board.turn == chess.WHITE else 2)
    if rec["ply"] != expected_ply:  # valid because every game starts from the standard position
        errors.append("ply_mismatch")

    hist = rec["last_5_moves_uci"]
    if len(hist) > 5 or any(not re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", h) for h in hist):
        errors.append("bad_history")
    if rec["speed"] not in SPEEDS:
        errors.append("bad_speed")
    return errors
