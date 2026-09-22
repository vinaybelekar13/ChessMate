"""Stockfish adapter — supplementary only (spec §39). Never used to
generate or override the author's lesson; only for legality/evaluation
confirmation, surfaced to the user as clearly-labeled "ENGINE" output
(see coach/prompts.py §38 claim-separation rule).

ChessMate's existing frontend already bundles Stockfish 18 as WASM
(vendor/stockfish/) for its game-review feature — for Book Coach positions
the frontend can likely reuse that same in-browser engine instead of a
server-side one at all. This server-side adapter is here for cases where
you want engine confirmation as part of ingestion (e.g. auto-checking that a
reconstructed diagram position isn't checkmate-already-over, or flagging
puzzles whose "book solution" isn't actually best per engine, for manual
review) rather than for live per-user requests.
"""
from __future__ import annotations
import shutil


_COMMON_INSTALL_PATHS = ("/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish")


def _resolve_binary() -> str | None:
    """Resolve the configured/PATH stockfish binary, falling back to the
    common apt/Debian install location (/usr/games) which is frequently NOT
    on a non-interactive shell's PATH even when the package is installed —
    this is exactly the gap that made the shared engine silently report
    "unavailable" on a freshly-provisioned box in this integration."""
    from app.config import settings
    found = shutil.which(settings.stockfish_path) or shutil.which("stockfish")
    if found:
        return found
    for candidate in _COMMON_INSTALL_PATHS:
        if shutil.which(candidate):
            return candidate
    return None


def is_available() -> bool:
    """Checks for the configured Stockfish binary (PATH or a common install
    location) without invoking it.
    """
    return _resolve_binary() is not None


def evaluate_fen(fen: str, depth: int = 15) -> dict:
    """Runs Stockfish via UCI over python-chess's engine wrapper when both
    Stockfish and python-chess are available. Never fabricates an
    evaluation: if either is missing, returns a clearly-labeled
    "unavailable" result instead of raising or guessing a score, per the
    "engine is supplementary, never fabricated" rule (spec §39 / follow-up
    §8).
    """
    if not is_available():
        return {"available": False, "reason": "Stockfish binary not found", "fen": fen}
    try:
        import chess
        import chess.engine
    except ImportError:
        return {"available": False, "reason": "python-chess not installed", "fen": fen}

    from app.config import settings
    binary = _resolve_binary()
    try:
        with chess.engine.SimpleEngine.popen_uci(binary) as engine:
            board = chess.Board(fen)
            info = engine.analyse(board, chess.engine.Limit(depth=depth))
            return {
                "available": True,
                "fen": fen,
                "score_cp": info["score"].white().score(mate_score=100000),
                "best_move": str(info.get("pv", [None])[0]) if info.get("pv") else None,
                "depth": depth,
            }
    except Exception as e:
        return {"available": False, "reason": f"Stockfish call failed: {e}", "fen": fen}
