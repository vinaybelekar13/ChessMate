"""Training data access for the Magnus model.

`PositionDataset` indexes a JSONL split file by byte offset, so memory stays
small (about 8 bytes per position) even for the 577k-position train split,
and parses/encodes one record on demand. Encoding goes through the SAME
`encode_position` used at inference time.

Windows note: DataLoader workers use "spawn", so the dataset must be
picklable. It is: the open file handle is created lazily per process.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import chess
import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from .encoding import SPEEDS, collate as _stack, encode_position
from .move_space import move_to_index

COLORS = ("white", "black")
SPEED_ORDER = ("classical", "rapid", "blitz", "bullet", "ultrabullet", "unknown")  # reporting order
_GAME_ID_RE = re.compile(rb'"game_id":"([^"]+)"')


def encode_record(rec: dict) -> Dict[str, torch.Tensor]:
    """Model inputs + target for one position record.

    Adds: `target` (move-space index of the HISTORICAL Magnus move) and
    `color` (0 = Magnus played White, 1 = Black) for metric breakdowns.
    """
    fen = rec["fen_before"]
    turn = chess.WHITE if fen.split()[1] == "w" else chess.BLACK
    item = encode_position(fen, rec["last_5_moves_uci"], rec.get("time_control") or None, rec.get("speed"))
    item["target"] = torch.tensor(move_to_index(chess.Move.from_uci(rec["target_move_uci"]), turn), dtype=torch.long)
    item["color"] = torch.tensor(0 if rec["magnus_color"] == "white" else 1, dtype=torch.long)
    if not bool(item["legal_mask"][item["target"]]):  # dataset integrity: label must be legal
        raise ValueError(f"target {rec['target_move_uci']} is not legal in {fen} ({rec.get('position_id')})")
    return item


def collate(items: Sequence[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
    return _stack(items)


class PositionDataset(Dataset):
    """Random-access view of a position JSONL file."""

    def __init__(self, path, indices: Optional[Sequence[int]] = None):
        self.path = str(path)
        offsets, pos = [], 0
        with open(self.path, "rb") as fh:
            for line in fh:
                if line.strip():
                    offsets.append(pos)
                pos += len(line)
        self._all_offsets = np.asarray(offsets, dtype=np.int64)
        self.offsets = self._all_offsets if indices is None else self._all_offsets[np.asarray(indices, dtype=np.int64)]
        self._fh = None

    def __len__(self) -> int:
        return len(self.offsets)

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_fh"] = None
        return state

    def record(self, i: int) -> dict:
        if self._fh is None:
            self._fh = open(self.path, "rb")
        self._fh.seek(int(self.offsets[i]))
        return json.loads(self._fh.readline())

    def __getitem__(self, i: int) -> Dict[str, torch.Tensor]:
        return encode_record(self.record(i))

    def subset(self, n: Optional[int], seed: int = 0) -> "PositionDataset":
        """Deterministic random subset of n positions (all if n is None or >= len)."""
        if n is None or n >= len(self):
            return self
        idx = np.sort(np.random.default_rng(seed).choice(len(self), size=n, replace=False))
        sub = PositionDataset.__new__(PositionDataset)
        sub.path, sub._all_offsets, sub._fh = self.path, self._all_offsets, None
        sub.offsets = self.offsets[idx]
        return sub


def epoch_batches(n: int, batch_size: int, seed: int, epoch: int, shuffle: bool = True) -> List[List[int]]:
    """Deterministic list of index batches for one epoch (same on every run)."""
    if shuffle:
        g = torch.Generator().manual_seed(seed * 1_000_003 + epoch)
        order = torch.randperm(n, generator=g).tolist()
    else:
        order = list(range(n))
    return [order[i:i + batch_size] for i in range(0, n, batch_size)]


def make_loader(ds: Dataset, batches: List[List[int]], num_workers: int = 0) -> DataLoader:
    """Loader over an explicit list of batches (enables exact mid-epoch resume)."""
    return DataLoader(ds, batch_sampler=batches, collate_fn=collate, num_workers=num_workers,
                      persistent_workers=False)


# ------------------------------------------------------------------ split integrity
def collect_game_ids(path) -> set:
    """All game_ids in a split file (fast regex scan, no full JSON parse)."""
    ids = set()
    with open(path, "rb") as fh:
        for n, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            m = _GAME_ID_RE.search(line)
            if m is None:  # a guard that silently sees nothing is worse than no guard
                raise ValueError(f"{path}:{n}: record has no game_id; cannot verify split integrity")
            ids.add(m.group(1).decode())
    return ids


def assert_no_game_overlap(paths: Dict[str, str]) -> Dict[str, int]:
    """Raise if any game_id appears in more than one split file. Returns game counts."""
    seen: Dict[str, str] = {}
    counts = {}
    for name, path in paths.items():
        ids = collect_game_ids(path)
        counts[name] = len(ids)
        for gid in ids:
            if gid in seen:
                raise AssertionError(f"LEAKAGE: game {gid} is in both '{seen[gid]}' and '{name}'")
            seen[gid] = name
    return counts
