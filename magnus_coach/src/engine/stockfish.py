"""Stockfish integration (Phase 15): OBJECTIVE analysis only.

Everything returned here is labelled kind="engine_analysis". It never feeds
the Magnus model and is never described as what Magnus thought.

Scores are given from the SIDE-TO-MOVE point of view: `cp` (centipawns) or
`mate` (moves, negative = being mated). `value_cp` maps both onto one number
(mate -> +/-(10000 - 10*|mate|)) and `win_pct` is the Lichess win-probability
transform of it, used for move classification.
"""

from __future__ import annotations

import atexit
import math
import os
import shutil
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

import chess
import chess.engine

KIND = "engine_analysis"
_CANDIDATES = ("/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish", "stockfish", "stockfish.exe")


def find_stockfish() -> Optional[str]:
    env = os.environ.get("STOCKFISH_PATH")
    if env and Path(env).exists():
        return env
    for c in _CANDIDATES:
        p = shutil.which(c) or (c if Path(c).exists() else None)
        if p:
            return p
    return None


def value_cp(cp: Optional[int], mate: Optional[int]) -> int:
    if mate is not None:
        return (10000 - 10 * abs(mate)) * (1 if mate > 0 else -1)
    return int(cp or 0)


def win_pct(cp_value: float) -> float:
    """Lichess win-probability transform (0-100) of a centipawn value."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * max(-10000, min(10000, cp_value)))) - 1)


def _score(pov: chess.engine.PovScore, turn: bool) -> Dict[str, Any]:
    s = pov.pov(turn)
    cp, mate = s.score(), s.mate()
    v = value_cp(cp, mate)
    return {"cp": cp if mate is None else None, "mate": mate, "value_cp": v, "win_pct": round(win_pct(v), 3),
            "perspective": chess.COLOR_NAMES[turn]}


class StockfishAnalyzer:
    def __init__(self, path: Optional[str] = None, depth: int = 12, multipv: int = 3, threads: int = 1,
                 hash_mb: int = 64, cache_size: int = 512):
        self.path = path or find_stockfish()
        if not self.path:
            raise FileNotFoundError("Stockfish not found (install it or set STOCKFISH_PATH)")
        self.depth, self.multipv = depth, multipv
        self.engine = chess.engine.SimpleEngine.popen_uci(self.path)
        self.engine.configure({"Threads": threads, "Hash": hash_mb})
        self.name = self.engine.id.get("name", "Stockfish")
        self._cache: "OrderedDict[tuple, dict]" = OrderedDict()
        self._cache_size = cache_size
        self.calls = self.cache_hits = 0
        self._closed = False
        # python-chess's engine thread is NON-daemon and Python joins such threads BEFORE running atexit
        # handlers, so atexit is too late. threading._register_atexit runs before the join.
        try:
            threading._register_atexit(self.close)
        except (AttributeError, RuntimeError):
            atexit.register(self.close)

    # ------------------------------------------------------------------ lifecycle
    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.engine.quit()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # ------------------------------------------------------------------ analysis
    def analyze(self, fen: str, depth: Optional[int] = None, multipv: Optional[int] = None) -> Dict[str, Any]:
        depth, multipv = depth or self.depth, multipv or self.multipv
        board = chess.Board(fen)
        key = (board.fen(), depth, multipv)
        if key in self._cache:
            self._cache.move_to_end(key)
            self.cache_hits += 1
            return self._cache[key]
        if board.is_game_over():
            res = {"kind": KIND, "engine": self.name, "fen": fen, "depth": depth, "game_over": True,
                   "result": board.result(), "best_move": None, "evaluation": None, "lines": []}
        else:
            self.calls += 1
            infos = self.engine.analyse(board, chess.engine.Limit(depth=depth), multipv=min(multipv, board.legal_moves.count()))
            lines: List[Dict[str, Any]] = []
            for i, info in enumerate(infos, start=1):
                pv = info.get("pv", [])
                b, pv_san = board.copy(), []
                for m in pv:
                    pv_san.append(b.san(m))
                    b.push(m)
                lines.append({"rank": i, "move_uci": pv[0].uci(), "move_san": pv_san[0],
                              "pv_uci": [m.uci() for m in pv], "pv_san": pv_san,
                              "score": _score(info["score"], board.turn), "depth": info.get("depth")})
            res = {"kind": KIND, "engine": self.name, "fen": board.fen(), "depth": depth, "game_over": False,
                   "side_to_move": chess.COLOR_NAMES[board.turn],
                   "best_move": {"uci": lines[0]["move_uci"], "san": lines[0]["move_san"]},
                   "evaluation": lines[0]["score"], "lines": lines}
        self._cache[key] = res
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return res

    def evaluate_move(self, fen: str, move_uci: str, depth: Optional[int] = None) -> Dict[str, Any]:
        """Evaluation of the position AFTER `move_uci`, from the MOVER's point of view."""
        board = chess.Board(fen)
        mv = chess.Move.from_uci(move_uci)
        if mv not in board.legal_moves:
            raise ValueError(f"{move_uci} is not legal in {fen}")
        mover = board.turn
        board.push(mv)
        a = self.analyze(board.fen(), depth, multipv=1)
        if a["game_over"]:
            v = 10000 if board.is_checkmate() else 0
            score = {"cp": None if board.is_checkmate() else 0, "mate": 0 if board.is_checkmate() else None, "value_cp": v,
                     "win_pct": round(win_pct(v), 3), "perspective": chess.COLOR_NAMES[mover]}
            return {"kind": KIND, "fen_after": board.fen(), "score_for_mover": score, "best_reply": None,
                    "principal_variation_uci": [], "principal_variation_san": [], "game_over": True, "depth": a["depth"]}
        opp = a["lines"][0]
        flipped = {**opp["score"], "cp": None if opp["score"]["cp"] is None else -opp["score"]["cp"],
                   "mate": None if opp["score"]["mate"] is None else -opp["score"]["mate"],
                   "value_cp": -opp["score"]["value_cp"], "perspective": chess.COLOR_NAMES[mover]}
        flipped["win_pct"] = round(win_pct(flipped["value_cp"]), 3)
        return {"kind": KIND, "fen_after": board.fen(), "score_for_mover": flipped,
                "best_reply": {"uci": opp["move_uci"], "san": opp["move_san"]},
                "principal_variation_uci": opp["pv_uci"], "principal_variation_san": opp["pv_san"],
                "game_over": False, "depth": a["depth"]}


def engine_available() -> bool:
    return find_stockfish() is not None
