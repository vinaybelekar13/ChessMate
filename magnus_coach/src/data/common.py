"""Shared data-pipeline utilities.

Everything that decides "is this token missing?", "is this player Magnus?",
"what is this game's canonical identity?" and "is this move sequence legal?"
lives here so the corpus builder, validator and tests all use one definition.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Iterable, Optional

import chess

# ---------------------------------------------------------------------------
# Missing values
# ---------------------------------------------------------------------------
# The Lichess CSV export writes the absent final move of a game as "NA"
# (or as an empty cell). Both are VALID terminal cells, not corrupt data.
MISSING_TOKENS = frozenset({"", "na", "nan", "n/a", "none", "null"})


def is_missing(value) -> bool:
    """True for None, NaN floats and the string spellings of 'no value'."""
    if value is None:
        return True
    if isinstance(value, float) and value != value:  # NaN
        return True
    return str(value).strip().lower() in MISSING_TOKENS


_MOVE_NUMBER_PREFIX = re.compile(r"^\d+\s*\.(?:\s*\.\.)?\s*")


def clean_san(token) -> Optional[str]:
    """Normalise a CSV move cell to bare SAN, or None if the cell is missing.

    '1.e4' -> 'e4', '10...Qe7' -> 'Qe7', '59.Qxd5' -> 'Qxd5',
    'NA' / 'nan' / 'N/A' / '' / None -> None.
    """
    if is_missing(token):
        return None
    token = _MOVE_NUMBER_PREFIX.sub("", str(token).strip()).strip()
    return None if is_missing(token) else token


# ---------------------------------------------------------------------------
# Magnus identification
# ---------------------------------------------------------------------------
# Matching is on the NORMALISED FULL NAME, never on a substring: the PGN
# collection contains "Carlsen,H" (a different person) and one game with
# Carlsen-named players on both sides.
MAGNUS_ALIASES = frozenset(
    {
        "carlsen magnus",
        "magnus carlsen",
        "carlsen m",  # PGN Mentor: "Carlsen,M"
        "drnykterstein",  # Lichess account
        "dr nykterstein",
        "nykterstein",
    }
)


def normalize_name(name) -> str:
    if name is None:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[,._\-]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def is_magnus_name(name) -> bool:
    return normalize_name(name) in MAGNUS_ALIASES


def identify_magnus(white, black):
    """Return (magnus_color, opponent) with color in {'white','black'}.

    Returns (None, None) when neither side is Magnus, and also when BOTH
    sides match (ambiguous - never guess).
    """
    w, b = is_magnus_name(white), is_magnus_name(black)
    if w and not b:
        return "white", black
    if b and not w:
        return "black", white
    return None, None


# ---------------------------------------------------------------------------
# Time control
# ---------------------------------------------------------------------------
def speed_from_time_control(time_control) -> Optional[str]:
    """Lichess speed class from '<base>+<inc>' using base + 40*inc seconds."""
    if is_missing(time_control):
        return None
    m = re.fullmatch(r"\s*(\d+)\s*\+\s*(\d+)\s*", str(time_control))
    if not m:
        return None
    total = int(m.group(1)) + 40 * int(m.group(2))
    if total < 30:
        return "ultrabullet"
    if total < 180:
        return "bullet"
    if total < 480:
        return "blitz"
    if total < 1500:
        return "rapid"
    return "classical"


def classify_speed(time_control, event, source):
    """Return (speed, basis). Never claims more than the metadata supports."""
    speed = speed_from_time_control(time_control)
    if speed:
        return speed, "time_control_header"
    ev = (event or "").lower()
    if "blitz" in ev:
        return "blitz", "event_name"
    if "rapid" in ev or "rpd" in ev:
        return "rapid", "event_name"
    return "unspecified", "none"


# ---------------------------------------------------------------------------
# Canonical identity and replay
# ---------------------------------------------------------------------------
def game_hash(start_fen: str, moves: Iterable[str]) -> str:
    """SHA-256 of  '<start_fen>|<space-joined UCI moves>'.

    Identity is the full move sequence from a known start, NOT date/players.
    """
    payload = f"{start_fen}|{' '.join(moves)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def game_id_from_hash(digest: str) -> str:
    """Stable id: does not change when other games are added or removed."""
    return f"mc_{digest[:16]}"


def replay_uci(moves, start_fen: str = chess.STARTING_FEN):
    """Replay a UCI sequence with python-chess.

    Returns (ok, error_message, ply_of_failure). Never repairs anything.
    """
    board = chess.Board(start_fen)
    for ply, uci in enumerate(moves, start=1):
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as exc:
            return False, f"bad UCI '{uci}': {exc}", ply
        if move not in board.legal_moves:
            return False, f"illegal move {uci} at ply {ply} in {board.fen()}", ply
        board.push(move)
    return True, None, None
