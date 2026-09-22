"""Inference: FEN -> ranked LEGAL moves with model probabilities.

The probabilities describe how likely the model thinks a move is under
historical Magnus move choices. They are NOT move quality, NOT a Stockfish
evaluation and NOT Magnus's actual thinking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import chess
import torch

from src.model.checkpoint import load_checkpoint
from src.model.encoding import collate, encode_position, model_inputs  # noqa: F401
from src.model.magnus_model import MagnusModel
from src.model.move_space import index_to_move

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKPOINT = ROOT / "models" / "final" / "magnus_model.pt"


class MagnusPredictor:
    def __init__(self, model: MagnusModel, meta: Optional[Dict[str, Any]] = None):
        self.model = model.eval()
        self.meta = meta or {}

    @classmethod
    def from_checkpoint(cls, path=DEFAULT_CHECKPOINT) -> "MagnusPredictor":
        if not Path(path).exists():
            raise FileNotFoundError(f"no model checkpoint at {path} (has the model been trained?)")
        model, meta = load_checkpoint(path)
        return cls(model, meta)

    @property
    def is_trained(self) -> bool:
        return int(self.meta.get("trained_steps", 0)) > 0

    @torch.no_grad()
    def predict(self, fen: str, top_k: int = 5, history_uci: Sequence[str] = (),
                time_control: Optional[str] = None, speed: Optional[str] = None) -> List[Dict[str, Any]]:
        """Top-k legal moves by model probability: [{uci, san, probability}]."""
        board = chess.Board(fen)
        if board.is_game_over(claim_draw=False) and not any(board.legal_moves):
            raise ValueError("position has no legal moves")
        batch = collate([encode_position(board, history_uci, time_control, speed)])
        probs = self.model.probs(batch)[0]
        k = min(top_k, int(batch["legal_mask"][0].sum()))
        values, indices = torch.topk(probs, k)
        out = []
        for p, idx in zip(values.tolist(), indices.tolist()):
            move = index_to_move(idx, board)
            if move not in board.legal_moves:  # cannot happen thanks to the mask; never emit if it does
                raise AssertionError(f"model produced illegal move {move.uci()} in {fen}")
            out.append({"uci": move.uci(), "san": board.san(move), "probability": p})
        return out


_default: Optional[MagnusPredictor] = None


def predict_magnus_moves(fen: str, top_k: int = 5, **kwargs) -> List[Dict[str, Any]]:
    """Spec API: predict_magnus_moves(fen, top_k=5). Needs models/final/magnus_model.pt."""
    global _default
    if _default is None:
        _default = MagnusPredictor.from_checkpoint()
    return _default.predict(fen, top_k, **kwargs)
