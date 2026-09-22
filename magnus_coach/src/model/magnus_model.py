"""Compact Transformer that models historical Magnus move choices.

    squares(64) + global(1) + history(5)  ->  Transformer  ->  move logits (4162)

The model is a BEHAVIOURAL model: it scores how likely a move is under
Magnus's historical choices. It is not a chess evaluator.
"""

from __future__ import annotations

import math
from typing import Dict, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import MagnusModelConfig
from .move_space import NUM_PAIR_MOVES, NUM_UNDERPROMO_TYPES, UNDERPROMO_PAIR_INDEX
from .encoding import MODEL_INPUT_KEYS

ILLEGAL_LOGIT = -1e9


def mask_logits(logits: torch.Tensor, legal_mask: torch.Tensor) -> torch.Tensor:
    """Set illegal-move logits to ILLEGAL_LOGIT. Refuses rows with no legal move.

    A fully masked row would softmax to a uniform distribution over ILLEGAL
    moves, so it is an error, never a silent fallback.
    """
    if logits.shape != legal_mask.shape:
        raise ValueError(f"logits {tuple(logits.shape)} and mask {tuple(legal_mask.shape)} differ")
    if not bool(legal_mask.any(dim=-1).all()):
        raise ValueError("at least one position has no legal moves (checkmate/stalemate)")
    return logits.masked_fill(~legal_mask, ILLEGAL_LOGIT)


class MagnusModel(nn.Module):
    def __init__(self, config: Optional[MagnusModelConfig] = None):
        super().__init__()
        self.config = (config or MagnusModelConfig()).validate()
        c = self.config
        d = c.d_model

        # ---- input embeddings
        self.piece_emb = nn.Embedding(c.num_piece_tokens, d)
        self.square_emb = nn.Embedding(64, d)
        self.hist_from_emb = nn.Embedding(65, d)  # 64 squares + pad
        self.hist_to_emb = nn.Embedding(65, d)
        self.hist_slot_emb = nn.Embedding(c.history_len, d)
        self.speed_emb = nn.Embedding(c.num_speeds, d)
        self.ep_emb = nn.Embedding(c.num_ep_states, d)
        self.numeric_proj = nn.Linear(c.num_numeric, d)

        # ---- backbone
        layer = nn.TransformerEncoderLayer(
            d_model=d, nhead=c.n_heads, dim_feedforward=c.d_ff, dropout=c.dropout,
            activation="gelu", batch_first=True, norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, c.n_layers, enable_nested_tensor=False)
        self.final_norm = nn.LayerNorm(d)

        # ---- move head: score(from, to) from the 64 square tokens
        self.from_proj = nn.Linear(d, c.policy_dim)
        self.to_proj = nn.Linear(d, c.policy_dim)
        self.pair_bias = nn.Parameter(torch.zeros(64, 64))
        self.underpromo_bias = nn.Parameter(torch.full((NUM_UNDERPROMO_TYPES,), c.underpromo_bias_init))
        self.register_buffer(
            "underpromo_pair_index", torch.tensor(UNDERPROMO_PAIR_INDEX, dtype=torch.long), persistent=False
        )
        self.register_buffer("square_ids", torch.arange(64), persistent=False)
        self.register_buffer("hist_slot_ids", torch.arange(c.history_len), persistent=False)

        self._init_weights()

    def _init_weights(self):
        for emb in (self.piece_emb, self.square_emb, self.hist_from_emb, self.hist_to_emb,
                    self.hist_slot_emb, self.speed_emb, self.ep_emb):
            nn.init.normal_(emb.weight, std=0.02)

    # ------------------------------------------------------------------ forward
    def forward(
        self,
        squares: torch.Tensor,       # long  [B, 64]
        history_from: torch.Tensor,  # long  [B, H]
        history_to: torch.Tensor,    # long  [B, H]
        speed: torch.Tensor,         # long  [B]
        ep: torch.Tensor,            # long  [B]
        numeric: torch.Tensor,       # float [B, num_numeric]
    ) -> torch.Tensor:
        """Raw (UNMASKED) move logits, float [B, num_moves]."""
        board_tok = self.piece_emb(squares) + self.square_emb(self.square_ids)          # [B,64,d]
        global_tok = (self.numeric_proj(numeric) + self.speed_emb(speed) + self.ep_emb(ep)).unsqueeze(1)
        hist_tok = (self.hist_from_emb(history_from) + self.hist_to_emb(history_to)
                    + self.hist_slot_emb(self.hist_slot_ids))                            # [B,H,d]

        x = torch.cat([board_tok, global_tok, hist_tok], dim=1)                          # [B,70,d]
        x = self.final_norm(self.encoder(x))

        sq = x[:, :64]                                                                    # square tokens
        q, k = self.from_proj(sq), self.to_proj(sq)
        pair = torch.matmul(q, k.transpose(1, 2)) / math.sqrt(self.config.policy_dim)     # [B,64,64]
        pair = (pair + self.pair_bias).reshape(-1, NUM_PAIR_MOVES)                        # [B,4096]

        under = pair[:, self.underpromo_pair_index].unsqueeze(-1) + self.underpromo_bias  # [B,22,3]
        return torch.cat([pair, under.reshape(under.shape[0], -1)], dim=1)                # [B,4162]

    def forward_batch(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        return self(*(batch[k] for k in MODEL_INPUT_KEYS))

    # ------------------------------------------------------------------ masked outputs
    def masked_logits(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        return mask_logits(self.forward_batch(batch), batch["legal_mask"])

    def log_probs(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        """log-probabilities over LEGAL moves (illegal ~ -1e9)."""
        return F.log_softmax(self.masked_logits(batch), dim=-1)

    def probs(self, batch: Dict[str, torch.Tensor]) -> torch.Tensor:
        """Probabilities over legal moves; exactly 0 at illegal indices."""
        return F.softmax(self.masked_logits(batch), dim=-1)

    # ------------------------------------------------------------------ introspection
    def parameter_count(self, trainable_only: bool = False) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad or not trainable_only)
