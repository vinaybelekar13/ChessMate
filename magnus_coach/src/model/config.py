"""Model configuration. Serialises to models/final/model_config.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Dict

from . import encoding as enc
from . import move_space as ms

MODEL_FORMAT = "magnus-transformer-v1"


@dataclass
class MagnusModelConfig:
    # ---- tunable architecture (CPU-friendly defaults)
    d_model: int = 128        # token width
    n_layers: int = 3         # transformer blocks
    n_heads: int = 4          # attention heads (d_model % n_heads == 0)
    d_ff: int = 256           # feed-forward width inside each block
    dropout: float = 0.1
    policy_dim: int = 64      # width of the from/to projections in the move head
    underpromo_bias_init: float = -2.0  # prior: underpromotions are rare

    # ---- structural constants: must match encoding.py / move_space.py.
    # Stored so a checkpoint made for a different input/output contract is
    # rejected on load instead of silently mis-scoring moves.
    num_moves: int = ms.NUM_MOVES
    num_piece_tokens: int = enc.NUM_PIECE_TOKENS
    history_len: int = enc.HISTORY_LEN
    num_speeds: int = len(enc.SPEEDS)
    num_ep_states: int = enc.NUM_EP_STATES
    num_numeric: int = enc.NUM_NUMERIC
    encoding_version: str = enc.ENCODING_VERSION
    model_format: str = MODEL_FORMAT

    def validate(self) -> "MagnusModelConfig":
        if self.d_model % self.n_heads:
            raise ValueError(f"d_model ({self.d_model}) must be divisible by n_heads ({self.n_heads})")
        for name in ("d_model", "n_layers", "n_heads", "d_ff", "policy_dim"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        expected = {
            "num_moves": ms.NUM_MOVES, "num_piece_tokens": enc.NUM_PIECE_TOKENS,
            "history_len": enc.HISTORY_LEN, "num_speeds": len(enc.SPEEDS),
            "num_ep_states": enc.NUM_EP_STATES, "num_numeric": enc.NUM_NUMERIC,
            "encoding_version": enc.ENCODING_VERSION, "model_format": MODEL_FORMAT,
        }
        for key, want in expected.items():
            if getattr(self, key) != want:
                raise ValueError(
                    f"config.{key}={getattr(self, key)!r} does not match this code's {want!r}; "
                    "the encoder/move space changed since this config was written"
                )
        return self

    @property
    def sequence_length(self) -> int:
        return 64 + 1 + self.history_len  # board squares + global token + history

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MagnusModelConfig":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known}).validate()

    @classmethod
    def load(cls, path) -> "MagnusModelConfig":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw.get("config", raw))


def describe(config: MagnusModelConfig, parameter_count: int = None) -> Dict[str, Any]:
    """Human-readable architecture description (the content of model_config.json)."""
    c = config
    return {
        "model_format": c.model_format,
        "purpose": ("Behavioural model of historical Magnus Carlsen move choices. "
                    "Outputs a distribution over LEGAL moves; not an evaluator of move quality."),
        "config": c.to_dict(),
        "parameter_count": parameter_count,
        "input": {
            "encoding_version": c.encoding_version,
            "tensors": {
                "squares": f"long [B, 64]  piece id per square (0..{c.num_piece_tokens - 1}), side-to-move frame",
                "history_from": f"long [B, {c.history_len}]  last moves' from-squares, newest first, 64 = pad",
                "history_to": f"long [B, {c.history_len}]  last moves' to-squares, newest first, 64 = pad",
                "speed": f"long [B]  time-control class (0..{c.num_speeds - 1}): {', '.join(enc.SPEEDS)}",
                "ep": f"long [B]  legal en-passant file 0..7 or 8 = none",
                "numeric": f"float [B, {c.num_numeric}]  castling x4, halfmove/100, fullmove/100, played_as_black, "
                           "time_control_present, log base time, log increment",
            },
            "token_sequence": f"{c.sequence_length} tokens = 64 squares + 1 global + {c.history_len} history moves",
        },
        "backbone": {
            "type": "pre-norm Transformer encoder",
            "d_model": c.d_model, "layers": c.n_layers, "heads": c.n_heads,
            "d_ff": c.d_ff, "activation": "gelu", "dropout": c.dropout,
        },
        "output": {
            "logits": f"float [B, {c.num_moves}] raw move scores",
            "layout": {
                "[0, 4096)": "from_square*64 + to_square (normal moves, castling, en passant, queen promotion)",
                "[4096, 4162)": "underpromotions: 22 rank7->rank8 pawn (from,to) pairs x {rook, bishop, knight}",
            },
            "frame": "side-to-move (board mirrored vertically when Black is to move)",
            "head": (f"attention-style: score(from,to) = <W_q h_from, W_k h_to>/sqrt({c.policy_dim}) "
                     "+ learned 64x64 bias; underpromotion score = pair score + learned per-piece bias"),
        },
        "legal_move_masking": (
            "logits at illegal indices are replaced by -1e9 before softmax; a row with zero legal moves "
            "(mate/stalemate) raises ValueError. Any legal move has a slot, so coverage does not depend "
            "on which moves occur in the training data."
        ),
    }


def save_config_json(config: MagnusModelConfig, path, parameter_count: int = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(describe(config, parameter_count), indent=2), encoding="utf-8")
    return path
