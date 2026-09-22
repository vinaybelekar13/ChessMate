"""Evaluation metrics for the Magnus behavioural model.

All probabilities are over LEGAL moves only (illegal logits are masked), so
loss / perplexity / ranks are "how well does the model rank the historical
Magnus move among the legal moves". Nothing here measures move quality.

Definitions
-----------
top-k        historical Magnus move is among the k highest-probability legal moves
rank         1 + number of legal moves scored strictly higher than the target
MRR          mean of 1 / rank
loss         mean negative log-likelihood of the historical move (nats)
perplexity   exp(loss): the "effective number of equally likely moves"
uniform_ppl  exp(mean log(#legal moves)): perplexity of picking a legal move at random
raw_top1_legal_rate
             fraction of positions whose UNMASKED top-1 logit is a legal move
             (masking makes the final prediction always legal, so this is the
             informative version of "legal-move accuracy")
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, Optional

import torch
import torch.nn.functional as F

from .dataset import COLORS, SPEED_ORDER
from .encoding import SPEEDS
from .magnus_model import ILLEGAL_LOGIT

TOPK = (1, 3, 5, 10)


class _Group:
    __slots__ = ("n", "nll", "hits", "rr", "raw_legal", "masked_legal", "log_legal")

    def __init__(self):
        self.n = 0
        self.nll = 0.0
        self.hits = {k: 0 for k in TOPK}
        self.rr = 0.0
        self.raw_legal = 0
        self.masked_legal = 0
        self.log_legal = 0.0

    def merge(self, other: "_Group"):
        self.n += other.n
        self.nll += other.nll
        for k in TOPK:
            self.hits[k] += other.hits[k]
        self.rr += other.rr
        self.raw_legal += other.raw_legal
        self.masked_legal += other.masked_legal
        self.log_legal += other.log_legal

    def summary(self) -> Dict[str, float]:
        if self.n == 0:
            return {"n": 0}
        loss = self.nll / self.n
        out = {"n": self.n, "loss": loss, "perplexity": math.exp(min(loss, 50)),
               "mrr": self.rr / self.n,
               "uniform_perplexity": math.exp(self.log_legal / self.n),
               "raw_top1_legal_rate": self.raw_legal / self.n,
               "masked_top1_legal_rate": self.masked_legal / self.n}
        for k in TOPK:
            out[f"top{k}"] = self.hits[k] / self.n
        return out


def batch_stats(raw_logits: torch.Tensor, legal_mask: torch.Tensor, target: torch.Tensor):
    """Per-position statistics for a batch. Returns dict of tensors [B]."""
    masked = raw_logits.masked_fill(~legal_mask, ILLEGAL_LOGIT)
    log_probs = F.log_softmax(masked, dim=-1)
    nll = -log_probs.gather(1, target[:, None]).squeeze(1)
    target_logit = masked.gather(1, target[:, None])
    rank = 1 + (masked > target_logit).sum(1)                       # 1 = best
    raw_top = raw_logits.argmax(1, keepdim=True)
    masked_top = masked.argmax(1, keepdim=True)
    return {
        "nll": nll,
        "rank": rank,
        "raw_legal": legal_mask.gather(1, raw_top).squeeze(1),
        "masked_legal": legal_mask.gather(1, masked_top).squeeze(1),
        "log_legal": legal_mask.sum(1).clamp(min=1).float().log(),
    }


class MetricAccumulator:
    """Accumulates overall + per-speed + per-color metrics across batches."""

    def __init__(self):
        self.groups: Dict[str, _Group] = {}

    def _g(self, name: str) -> _Group:
        return self.groups.setdefault(name, _Group())

    @torch.no_grad()
    def update(self, raw_logits, legal_mask, target, speed_ids, color_ids):
        st = batch_stats(raw_logits, legal_mask, target)
        keys = [("overall", torch.ones_like(target, dtype=torch.bool))]
        for sid, name in enumerate(SPEEDS):
            keys.append((f"speed/{name}", speed_ids == sid))
        for cid, name in enumerate(COLORS):
            keys.append((f"color/{name}", color_ids == cid))
        for name, sel in keys:
            if not bool(sel.any()):
                continue
            g = self._g(name)
            g.n += int(sel.sum())
            g.nll += float(st["nll"][sel].sum())
            rk = st["rank"][sel]
            for k in TOPK:
                g.hits[k] += int((rk <= k).sum())
            g.rr += float((1.0 / rk.float()).sum())
            g.raw_legal += int(st["raw_legal"][sel].sum())
            g.masked_legal += int(st["masked_legal"][sel].sum())
            g.log_legal += float(st["log_legal"][sel].sum())

    def summary(self) -> Dict[str, Dict[str, float]]:
        order = ["overall"] + [f"speed/{s}" for s in SPEED_ORDER] + [f"color/{c}" for c in COLORS]
        return {k: self.groups[k].summary() for k in order if k in self.groups}

    @property
    def overall(self) -> Dict[str, float]:
        return self._g("overall").summary()
