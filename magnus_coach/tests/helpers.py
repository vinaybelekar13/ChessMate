"""Shared test helpers: synthetic games/splits built from seeded random legal play."""
import json
import random
from pathlib import Path

import chess

from src.data.positions import make_records

SPEEDS_CYCLE = ["classical", "rapid", "blitz", "bullet", "ultrabullet", "unspecified"]
TC_CYCLE = ["5400+30", "900+10", "180+2", "60+0", "15+0", ""]


def fake_game(seed, prefix="mc_t", plies=None, color=None):
    rng = random.Random(seed)
    plies = plies or rng.randint(20, 70)
    board, moves = chess.Board(), []
    for _ in range(plies):
        legal = list(board.legal_moves)
        if not legal:
            break
        m = rng.choice(legal)
        moves.append(m.uci())
        board.push(m)
    color = color or ("white" if seed % 2 == 0 else "black")
    k = seed % len(SPEEDS_CYCLE)
    return {
        "game_id": f"{prefix}{seed:012x}", "source": "test", "sources": ["test"], "start_fen": chess.STARTING_FEN,
        "moves": moves, "num_plies": len(moves), "magnus_color": color,
        "white": "Carlsen,M" if color == "white" else "Opp", "black": "Opp" if color == "white" else "Carlsen,M",
        "opponent": "Opp", "result": "1/2-1/2", "date": f"20{10 + seed % 15}.01.01", "event": "Test Event",
        "site": "nowhere", "eco": "A00", "opening": "", "time_control": TC_CYCLE[k], "speed": SPEEDS_CYCLE[k],
        "speed_basis": "test", "white_elo": "2800", "black_elo": "2600",
    }


def write_fake_split(path, seeds, split="train", prefix="mc_t", plies=None):
    """Write position records for fake games; returns (records, games)."""
    games = [fake_game(s, prefix, plies) for s in seeds]
    recs = [r for g in games for r in make_records(g, split)]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in recs:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    return recs, games
