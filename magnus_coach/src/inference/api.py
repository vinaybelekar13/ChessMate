"""Magnus model inference API (Phase 14).

predict_moves(fen, top_k=5, previous_moves=None, time_control=None, speed=None) -> list[dict]
predict_next_move(fen, ...) -> dict

Every result is a LEGAL move (legal=True always) with UCI, SAN, probability,
rank and the model's raw score (logit). Deterministic: eval mode, no sampling.
Probabilities are over legal moves and mean "how likely the model thinks this
move is under HISTORICAL Magnus move choices" - not move quality, not an
engine evaluation, not Magnus's thoughts.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import chess
import torch

from src.model.checkpoint import load_checkpoint
from src.model.encoding import collate, encode_position
from src.model.move_space import index_to_move, legal_moves_with_indices

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "models" / "final" / "magnus_model.pt"
KIND = "model_prediction"


@lru_cache(maxsize=4)
def load_magnus_model(path: str = str(DEFAULT_MODEL)):
    """Load (and cache) the model. Returns (model, meta)."""
    if not Path(path).exists():
        raise FileNotFoundError(f"no Magnus model at {path}")
    model, meta = load_checkpoint(path)
    return model.eval(), meta


def predict_moves(fen: str, top_k: int = 5, previous_moves: Optional[Sequence[str]] = None,
                  time_control: Optional[str] = None, speed: Optional[str] = None,
                  model_path: Optional[str] = None) -> List[Dict[str, Any]]:
    board = chess.Board(fen)
    legal = legal_moves_with_indices(board)
    if not legal:
        raise ValueError("position has no legal moves")
    model, _ = load_magnus_model(str(model_path or DEFAULT_MODEL))
    batch = collate([encode_position(board, list(previous_moves or []), time_control, speed)])
    with torch.no_grad():
        raw = model.forward_batch(batch)[0]
        probs = model.probs(batch)[0]
    ranked = sorted(legal, key=lambda im: (-float(probs[im[0]]), im[1].uci()))
    out = []
    for rank, (idx, mv) in enumerate(ranked[:max(1, top_k)], start=1):
        assert mv in board.legal_moves
        out.append({"uci": mv.uci(), "san": board.san(mv), "probability": float(probs[idx]), "rank": rank,
                    "score": float(raw[idx]), "legal": True, "kind": KIND})
    return out


def predict_next_move(fen: str, **kw) -> Dict[str, Any]:
    return predict_moves(fen, top_k=1, **kw)[0]


def move_probability(fen: str, uci: str, **kw) -> Dict[str, Any]:
    """Model probability/rank of one specific legal move (used by move comparison)."""
    board = chess.Board(fen)
    mv = chess.Move.from_uci(uci)
    if mv not in board.legal_moves:
        raise ValueError(f"{uci} is not legal in {fen}")
    allm = predict_moves(fen, top_k=len(list(board.legal_moves)), **kw)
    return next(m for m in allm if m["uci"] == uci)
