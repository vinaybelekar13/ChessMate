"""Game-level train / validation / test split.

Every game is assigned to exactly ONE split from a stable hash of its
canonical game hash (SHA-256 of start FEN + full UCI sequence):

    bucket = int(sha256("<salt>:<game_hash>")[:12], 16) % 10000
    bucket <  8000  -> train        (~80% of games)
    bucket <  9000  -> validation   (~10%)
    otherwise       -> test         (~10%)

Properties: deterministic; independent of corpus order and of every other
game (adding games later never moves an existing game); all positions of a
game share the game's split because splitting is by game, never by position.
Counts are therefore approximately, not exactly, 80/10/10.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SPLIT_SALT = "magnus-game-split-v1"
BUCKETS = 10_000
TRAIN_UPTO = 8_000
VALIDATION_UPTO = 9_000
SPLITS = ("train", "validation", "test")


def split_bucket(game_hash: str) -> int:
    digest = hashlib.sha256(f"{SPLIT_SALT}:{game_hash}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % BUCKETS


def assign_split(game_hash: str) -> str:
    b = split_bucket(game_hash)
    if b < TRAIN_UPTO:
        return "train"
    if b < VALIDATION_UPTO:
        return "validation"
    return "test"


def magnus_decisions(num_plies: int, magnus_color: str) -> int:
    """How many of a game's plies are Magnus moves (= positions we create)."""
    return (num_plies + 1) // 2 if magnus_color == "white" else num_plies // 2


def build_manifest(corpus_path) -> dict:
    games, counts, positions = [], {s: 0 for s in SPLITS}, {s: 0 for s in SPLITS}
    with open(corpus_path, encoding="utf-8") as fh:
        for line in fh:
            g = json.loads(line)
            split = assign_split(g["game_hash"])
            games.append({"game_id": g["game_id"], "split": split})
            counts[split] += 1
            positions[split] += magnus_decisions(g["num_plies"], g["magnus_color"])
    games.sort(key=lambda x: x["game_id"])
    return {
        "version": 1,
        "method": "stable hash of canonical game hash; whole games only",
        "salt": SPLIT_SALT,
        "buckets": {"train": f"[0,{TRAIN_UPTO})", "validation": f"[{TRAIN_UPTO},{VALIDATION_UPTO})",
                    "test": f"[{VALIDATION_UPTO},{BUCKETS})"},
        "games_per_split": counts,
        "expected_positions_per_split": positions,
        "total_games": len(games),
        "games": games,
    }


def load_manifest(path) -> dict:
    """Return {game_id: split}; raises on duplicate ids or unknown split names."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    mapping = {}
    for row in raw["games"]:
        if row["split"] not in SPLITS:
            raise ValueError(f"unknown split {row['split']!r}")
        if row["game_id"] in mapping:
            raise ValueError(f"duplicate game_id in manifest: {row['game_id']}")
        mapping[row["game_id"]] = row["split"]
    return mapping
