"""Checkpoint save/load. A checkpoint carries its own config, so it can be
rebuilt without external files, and refuses to load into an incompatible
encoder / move space."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import torch

from .config import MagnusModelConfig
from .magnus_model import MagnusModel

CHECKPOINT_FORMAT = 1


def save_checkpoint(model: MagnusModel, path, meta: Optional[Dict[str, Any]] = None,
                    optimizer: Optional[torch.optim.Optimizer] = None,
                    extra: Optional[Dict[str, Any]] = None) -> Path:
    """Save weights + config (+ optional optimizer state for resuming).

    `meta` is free-form but should include `trained_steps` (0 = untrained).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(meta or {})
    meta.setdefault("trained_steps", 0)
    payload = {
        "checkpoint_format": CHECKPOINT_FORMAT,
        "config": model.config.to_dict(),
        "model_state": model.state_dict(),
        "parameter_count": model.parameter_count(),
        "meta": meta,
    }
    if optimizer is not None:
        payload["optimizer_state"] = optimizer.state_dict()
    if extra:  # e.g. scheduler state, training progress, RNG state (for exact resume)
        payload.update(extra)
    tmp = path.with_name(path.name + ".tmp")
    torch.save(payload, tmp)
    tmp.replace(path)  # atomic: an interrupted save never leaves a corrupt checkpoint
    return path


def load_checkpoint(path, map_location="cpu") -> Tuple[MagnusModel, Dict[str, Any]]:
    """Rebuild the model from a checkpoint. Returns (model in eval mode, meta)."""
    payload = torch.load(Path(path), map_location=map_location, weights_only=True)
    if payload.get("checkpoint_format") != CHECKPOINT_FORMAT:
        raise ValueError(f"unsupported checkpoint format {payload.get('checkpoint_format')!r}")
    config = MagnusModelConfig.from_dict(payload["config"])  # validates against current code
    model = MagnusModel(config)
    model.load_state_dict(payload["model_state"], strict=True)
    model.eval()
    return model, payload.get("meta", {})


def load_payload(path, map_location="cpu") -> Dict[str, Any]:
    """Raw checkpoint payload (includes optimizer/scheduler/progress if present)."""
    return torch.load(Path(path), map_location=map_location, weights_only=True)
