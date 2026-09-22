"""SQLite historical Magnus database (V1) and similar-position retrieval.

Every returned record is a real stored row (`provenance.row_id`); nothing is
generated. Historical FACTS (game, move, metadata) come only from the
database; the similarity score is a deterministic comparison (see
similarity.py), not a claim about chess understanding.
"""

from __future__ import annotations

import json
import sqlite3
import zlib
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import chess

from . import similarity as sim

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "magnus_history.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
  game_id TEXT PRIMARY KEY, source TEXT, sources TEXT, date TEXT, year INTEGER, event TEXT, site TEXT,
  white TEXT, black TEXT, magnus_color TEXT, opponent TEXT, result TEXT, eco TEXT, opening TEXT,
  time_control TEXT, speed TEXT, white_elo TEXT, black_elo TEXT, split TEXT, num_plies INTEGER, moves_uci TEXT);
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY, position_id TEXT UNIQUE, game_id TEXT, ply INTEGER, move_number INTEGER, fen TEXT,
  target_uci TEXT, target_san TEXT, last5 TEXT, next_moves TEXT, magnus_color TEXT, speed TEXT, split TEXT,
  bb BLOB, key_exact INTEGER, key_pawns INTEGER, key_material INTEGER, rnd INTEGER);
"""
INDEXES = """
CREATE INDEX IF NOT EXISTS ix_pos_exact ON positions(key_exact);
CREATE INDEX IF NOT EXISTS ix_pos_pawns ON positions(key_pawns, rnd);
CREATE INDEX IF NOT EXISTS ix_pos_material ON positions(key_material, rnd);
CREATE INDEX IF NOT EXISTS ix_pos_game ON positions(game_id, ply);
CREATE INDEX IF NOT EXISTS ix_pos_fen ON positions(fen);
CREATE INDEX IF NOT EXISTS ix_pos_split ON positions(split);
"""


def mirror_uci(uci: str) -> str:
    m = chess.Move.from_uci(uci)
    return chess.Move(chess.square_mirror(m.from_square), chess.square_mirror(m.to_square), m.promotion).uci()


def build(corpus_path, split_dir, manifest_path, db_path=DEFAULT_DB, verbose=True) -> dict:
    """Create the database from the validated corpus + position dataset (deterministic)."""
    from src.data.splits import load_manifest
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    manifest = load_manifest(manifest_path)
    rows = []
    with open(corpus_path, encoding="utf-8") as fh:
        for line in fh:
            g = json.loads(line)
            rows.append((g["game_id"], g["source"], ",".join(g.get("sources", [g["source"]])), g.get("date", ""),
                         int(g["date"][:4]) if g.get("date", "")[:4].isdigit() else None, g.get("event", ""), g.get("site", ""),
                         g["white"], g["black"], g["magnus_color"], g["opponent"], g.get("result", ""), g.get("eco", ""),
                         g.get("opening", ""), g.get("time_control", ""),
                         {"unspecified": "unknown"}.get(g.get("speed", ""), g.get("speed", "")), g.get("white_elo", ""),
                         g.get("black_elo", ""), manifest[g["game_id"]], g["num_plies"], " ".join(g["moves"])))
    con.executemany("INSERT INTO games VALUES (%s)" % ",".join("?" * 21), rows)
    n = 0
    for split in ("train", "validation", "test"):
        batch = []
        with open(Path(split_dir) / f"{split}.jsonl", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                f = sim.features(chess.Board(r["fen_before"]))
                k = sim.keys(f)
                batch.append((r["position_id"], r["game_id"], r["ply"], r["move_number"], r["fen_before"],
                              r["target_move_uci"], r["target_move_san"], " ".join(r["last_5_moves_uci"]),
                              " ".join(r["next_moves_uci"]), r["magnus_color"], r["speed"], split, sim.pack(f),
                              k["exact"], k["pawns"], k["material"], zlib.crc32(r["position_id"].encode())))
                if len(batch) >= 20000:
                    con.executemany("INSERT INTO positions(position_id,game_id,ply,move_number,fen,target_uci,target_san,last5,next_moves,"
                                    "magnus_color,speed,split,bb,key_exact,key_pawns,key_material,rnd) VALUES (%s)" % ",".join("?" * 17), batch)
                    n += len(batch)
                    batch = []
                    if verbose:
                        print(f"  {n} positions", flush=True)
        con.executemany("INSERT INTO positions(position_id,game_id,ply,move_number,fen,target_uci,target_san,last5,next_moves,"
                        "magnus_color,speed,split,bb,key_exact,key_pawns,key_material,rnd) VALUES (%s)" % ",".join("?" * 17), batch)
        n += len(batch)
    con.executescript(INDEXES)
    con.commit()
    con.execute("ANALYZE")
    con.commit()
    stats = {"games": con.execute("SELECT COUNT(*) FROM games").fetchone()[0],
             "positions": con.execute("SELECT COUNT(*) FROM positions").fetchone()[0],
             "indexes": [r[1] for r in con.execute("SELECT * FROM sqlite_master WHERE type='index' AND name LIKE 'ix_%'")],
             "bytes": db_path.stat().st_size}
    con.close()
    return stats


class MagnusDB:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"historical database not found: {self.path} (run src/history/build_database.py)")
        self.con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self.con.row_factory = sqlite3.Row

    def close(self):
        self.con.close()

    def count(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM positions").fetchone()[0]

    # ------------------------------------------------------------ fetchers
    def get_game(self, game_id: str) -> Optional[dict]:
        r = self.con.execute("SELECT * FROM games WHERE game_id=?", (game_id,)).fetchone()
        if r is None:
            return None
        d = dict(r)
        d["moves_uci"] = d["moves_uci"].split()
        return d

    def get_position(self, position_id: str) -> Optional[dict]:
        r = self.con.execute("SELECT * FROM positions WHERE position_id=?", (position_id,)).fetchone()
        return self._row_to_result(r) if r else None

    def surrounding_moves(self, game_id: str, ply: int, before: int = 5, after: int = 5) -> List[dict]:
        """Actual moves around `ply` (1-based) with SAN, replayed from the stored game."""
        g = self.get_game(game_id)
        if g is None:
            raise KeyError(game_id)
        board, out = chess.Board(), []
        for i, u in enumerate(g["moves_uci"], start=1):
            mv = chess.Move.from_uci(u)
            if ply - before <= i <= ply + after:
                out.append({"ply": i, "uci": u, "san": board.san(mv),
                            "played_by": "magnus" if (i % 2 == 1) == (g["magnus_color"] == "white") else "opponent",
                            "is_target": i == ply})
            board.push(mv)
            if i > ply + after:
                break
        return out

    def _row_to_result(self, r, similarity=None, comps=None, exact=None, query_turn=None, query_board=None) -> dict:
        g = self.get_game(r["game_id"])
        stored_turn = chess.WHITE if r["fen"].split()[1] == "w" else chess.BLACK
        mirrored = query_turn is not None and stored_turn != query_turn
        move_q, legal_q = None, None
        if query_board is not None:
            move_q = mirror_uci(r["target_uci"]) if mirrored else r["target_uci"]
            legal_q = chess.Move.from_uci(move_q) in query_board.legal_moves
        return {
            "position_id": r["position_id"], "game_id": r["game_id"], "ply": r["ply"], "move_number": r["move_number"],
            "fen": r["fen"], "similarity": similarity, "similarity_components": comps, "exact_board_match": exact,
            "mirrored": mirrored,
            "magnus_move": {"uci": r["target_uci"], "san": r["target_san"]},
            "magnus_move_in_query_frame": move_q, "legal_in_query_position": legal_q,
            "magnus_color": r["magnus_color"],
            "previous_moves": r["last5"].split(), "next_moves": r["next_moves"].split(),
            "game": {k: g[k] for k in ("source", "date", "event", "site", "white", "black", "opponent", "result",
                                        "eco", "opening", "time_control", "speed", "split")},
            "provenance": {"database": self.path.name, "table": "positions", "row_id": r["id"],
                           "kind": "historical_fact"},
        }

    # ------------------------------------------------------------ retrieval
    def find_similar_positions(self, fen: str, top_k: int = 10, splits: Optional[Iterable[str]] = None,
                               exclude_game_ids: Iterable[str] = (), speed: Optional[str] = None,
                               same_color_to_move: bool = False, pool: int = 800) -> List[dict]:
        """Adaptive candidate pool: try the narrow (exact / pawns+material) queries first; only
        fall back to the broad pawns-only / material-only queries if they did not find enough
        candidates. This is a measured optimisation (Phase 29): on the real database the broad
        queries pulled 15k+ candidates per call for ~200ms; narrow-first typically needs far fewer."""
        board = chess.Board(fen)
        f = sim.features(board)
        k = sim.keys(f)
        where, params = [], []
        if splits:
            splits = list(splits)
            where.append("split IN (%s)" % ",".join("?" * len(splits)))
            params += splits
        if speed:
            where.append("speed=?")
            params.append(speed)
        if same_color_to_move:
            where.append("fen LIKE ?")
            params.append("% " + ("w" if board.turn == chess.WHITE else "b") + " %")
        excl = list(exclude_game_ids)
        if excl:
            where.append("game_id NOT IN (%s)" % ",".join("?" * len(excl)))
            params += excl
        extra = (" AND " + " AND ".join(where)) if where else ""
        cols = "id, position_id, game_id, ply, move_number, fen, target_uci, target_san, last5, next_moves, magnus_color, bb"
        cand: Dict[int, sqlite3.Row] = {}

        def grab(cond, cond_params, limit):
            q = f"SELECT {cols} FROM positions WHERE {cond}{extra} ORDER BY rnd LIMIT ?"
            for r in self.con.execute(q, cond_params + params + [limit]):
                cand[r["id"]] = r

        grab("key_exact=?", [k["exact"]], pool)
        grab("key_pawns=? AND key_material=?", [k["pawns"], k["material"]], pool)
        if len(cand) < max(top_k * 20, 200):          # only widen the search if narrow queries came up short
            grab("key_pawns=?", [k["pawns"]], pool)
            grab("key_material=?", [k["material"]], pool)
        scored = []
        for r in cand.values():
            fb = sim.unpack(r["bb"])
            s, comps = sim.similarity(f, fb)
            scored.append((-s, r["position_id"], r, comps, sim.is_exact(f, fb)))
        scored.sort(key=lambda x: (x[0], x[1]))
        return [self._row_to_result(r, round(-negs, 6), {kk: round(v, 6) for kk, v in comps.items()}, exact,
                                    board.turn, board) for negs, _pid, r, comps, exact in scored[:top_k]]


_default: Optional[MagnusDB] = None


def find_similar_positions(fen: str, top_k: int = 10, **kwargs) -> List[dict]:
    """Module-level API: find_similar_positions(fen, top_k=10)."""
    global _default
    if _default is None:
        _default = MagnusDB()
    return _default.find_similar_positions(fen, top_k, **kwargs)
