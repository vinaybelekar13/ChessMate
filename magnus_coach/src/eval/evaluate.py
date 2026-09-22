"""Held-out TEST evaluation (Phase 10) and baselines (Phase 11).

    python -m src.eval.evaluate --checkpoint outputs/runs/stage3_full_epoch/best.pt

The test set is used ONLY to report. Every tunable quantity (baseline
smoothing strengths) is chosen on the VALIDATION set; the checkpoint was
chosen on validation during training.

All systems (Transformer + baselines) score the SAME positions with the SAME
metric code. Every system defines a probability over the position's LEGAL
moves; ties are broken alphabetically by UCI so results are deterministic.
The random baseline uses exact expectations rather than sampling.

Position categories (all deterministic; definitions live in `features()`):
  phase     endgame: total non-pawn material of both sides <= 24 (Q9 R5 B3 N3);
            opening: not endgame and move_number <= 10; else middlegame
  tactical  in check, or the side to move has a capture that wins material by
            static exchange (see chess_core.tactics); otherwise quiet
  material  number of pieces on the board excluding kings: <=10 / 11-20 / 21-30
  board     "seen" if the exact board+turn+castling+ep occurs in the train split
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

import chess
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chess_core.tactics import VAL, is_tactical_position  # noqa: E402
from src.model.checkpoint import load_checkpoint  # noqa: E402
from src.model.dataset import collate, encode_record  # noqa: E402
from src.model.metrics import batch_stats  # noqa: E402
from src.model.move_space import move_to_index  # noqa: E402

SPLITS = ROOT / "data" / "splits"
TOPK = (1, 3, 5, 10)


def read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            yield json.loads(line)


def turn_of(fen: str) -> bool:
    return chess.WHITE if fen.split()[1] == "w" else chess.BLACK


def board_key(fen: str) -> int:
    return hash(" ".join(fen.split()[:4]))


# ---------------------------------------------------------------- train tables
class Tables:
    """Frequency tables built from the TRAIN split only."""

    def __init__(self):
        self.slot = Counter()                    # oriented move slot -> count (position independent)
        self.uci = Counter()                     # raw UCI -> count (position independent, colour specific)
        self.eco_ply = defaultdict(Counter)      # (ECO, ply) -> slot counts
        self.board = defaultdict(Counter)        # exact board -> slot counts
        self.n = 0

    @classmethod
    def build(cls, path):
        t = cls()
        for r in read_jsonl(path):
            idx = move_to_index(chess.Move.from_uci(r["target_move_uci"]), turn_of(r["fen_before"]))
            t.slot[idx] += 1
            t.uci[r["target_move_uci"]] += 1
            t.eco_ply[(r["ECO"] or "", r["ply"])][idx] += 1
            t.board[board_key(r["fen_before"])][idx] += 1
            t.n += 1
        return t


def prepare(rec: dict) -> dict:
    turn = turn_of(rec["fen_before"])
    legal = rec["legal_moves_uci"]
    return {"legal": legal, "t": legal.index(rec["target_move_uci"]),
            "idxs": np.array([move_to_index(chess.Move.from_uci(u), turn) for u in legal]),
            "eco": rec["ECO"] or "", "ply": rec["ply"], "bkey": board_key(rec["fen_before"])}


def _norm(x):
    return x / x.sum()


def baseline_probs(name: str, p: dict, T: Tables, hp: dict) -> np.ndarray:
    """Probability of each LEGAL move (aligned with p['legal']) under a baseline."""
    n = len(p["legal"])
    if name == "random":
        return np.full(n, 1.0 / n)
    if name == "global_uci_freq":
        return _norm(np.array([T.uci.get(u, 0) for u in p["legal"]], float) + hp["a0"])
    slot = _norm(np.array([T.slot.get(i, 0) for i in p["idxs"]], float) + hp["a0"])
    if name == "global_slot_freq":
        return slot
    table = T.eco_ply.get((p["eco"], p["ply"])) if name == "eco_ply_freq" else T.board.get(p["bkey"])
    if not table:
        return slot
    c = np.array([table.get(i, 0) for i in p["idxs"]], float)
    return (c + hp["ab"] * slot) / (c.sum() + hp["ab"])


def rank_of(prob: np.ndarray, legal: List[str], t: int) -> int:
    pt = prob[t]
    higher = int((prob > pt).sum())
    ties = sum(1 for i in range(len(prob)) if prob[i] == pt and legal[i] < legal[t])
    return 1 + higher + ties


def score(name, p, T, hp):
    """(nll, [top1,top3,top5,top10], rr). Random uses exact expectations."""
    n = len(p["legal"])
    if name == "random":
        h = sum(1.0 / r for r in range(1, n + 1)) / n
        return math.log(n), [min(k, n) / n for k in TOPK], h
    prob = baseline_probs(name, p, T, hp)
    r = rank_of(prob, p["legal"], p["t"])
    return -math.log(prob[p["t"]]), [float(r <= k) for k in TOPK], 1.0 / r


BASELINES = ("random", "global_uci_freq", "global_slot_freq", "eco_ply_freq", "board_lookup")
BASELINE_DESC = {
    "random": "uniform over legal moves (exact expectation)",
    "global_uci_freq": "position-independent frequency of raw UCI moves in train",
    "global_slot_freq": "position-independent frequency of side-to-move-oriented move slots in train",
    "eco_ply_freq": "frequency of the move slot given (game ECO code, ply); backs off to global_slot_freq. "
                    "NOTE: uses the game's ECO label, which a live position would not have",
    "board_lookup": "frequency of the move slot given the exact board seen in train; backs off to global_slot_freq",
}


def tune(T: Tables, val_records, n=20000):
    """Choose smoothing strengths on VALIDATION only."""
    prepared = [prepare(r) for r in val_records[:n]]
    best = {}
    for name in BASELINES[1:]:
        grid = [{"a0": a0, "ab": ab} for a0 in (0.5, 5.0, 50.0, 500.0) for ab in ((1.0, 4.0, 16.0) if name in ("eco_ply_freq", "board_lookup") else (1.0,))]
        scored = []
        for hp in grid:
            loss = float(np.mean([score(name, p, T, hp)[0] for p in prepared]))
            scored.append((loss, hp))
        best[name] = min(scored, key=lambda x: x[0])
    return best


# ---------------------------------------------------------------- features
def features(rec: dict, seen_boards) -> Dict[str, str]:
    b = chess.Board(rec["fen_before"])
    mv = chess.Move.from_uci(rec["target_move_uci"])
    non_pawn = sum(VAL[p.piece_type] for p in b.piece_map().values() if p.piece_type not in (chess.PAWN, chess.KING))
    pieces = len(b.piece_map()) - 2
    if non_pawn <= 24:
        phase = "endgame"
    elif rec["move_number"] <= 10:
        phase = "opening"
    else:
        phase = "middlegame"
    eco = rec["ECO"] or "(none)"
    return {
        "speed": rec["speed"], "color": rec["magnus_color"], "eco_letter": eco[0], "eco": eco, "phase": phase,
        "capture": "capture" if b.is_capture(mv) else "non_capture",
        "castling": "castling" if b.is_castling(mv) else "not_castling",
        "promotion": "promotion" if mv.promotion else "no_promotion",
        "material": "<=10" if pieces <= 10 else ("11-20" if pieces <= 20 else "21-30"),
        "tactical": "tactical" if is_tactical_position(b) else "quiet",
        "in_check": "in_check" if b.is_check() else "not_in_check",
        "board": "seen_in_train" if board_key(rec["fen_before"]) in seen_boards else "unseen_in_train",
    }


def aggregate(nll, tops, rr, extra=None):
    n = len(nll)
    if n == 0:
        return {"n": 0}
    loss = float(np.mean(nll))
    out = {"n": n, "loss": loss, "perplexity": math.exp(min(loss, 50)), "mrr": float(np.mean(rr))}
    for j, k in enumerate(TOPK):
        out[f"top{k}"] = float(np.mean(tops[:, j]))
    if extra:
        out.update({k: float(np.mean(v)) for k, v in extra.items()})
    return out


# ---------------------------------------------------------------- main
def run(checkpoint, out_dir, max_test=None, batch=512):
    t0 = time.time()
    out_dir = Path(out_dir)
    print("building train tables ...", flush=True)
    T = Tables.build(SPLITS / "train.jsonl")
    seen = set(T.board.keys())
    print(f"  {T.n} train positions, {len(seen)} distinct boards ({time.time() - t0:.0f}s)", flush=True)

    val = list(read_jsonl(SPLITS / "validation.jsonl"))
    tuned = tune(T, val)
    hps = {k: v[1] for k, v in tuned.items()}
    print("tuned on VALIDATION:", {k: (round(v[0], 4), v[1]) for k, v in tuned.items()}, flush=True)
    del val

    test = list(read_jsonl(SPLITS / "test.jsonl"))
    if max_test:
        test = test[:max_test]
    model, meta = load_checkpoint(checkpoint)
    N = len(test)
    print(f"evaluating {N} TEST positions ...", flush=True)

    sysnames = ("transformer",) + BASELINES
    nll = {s: np.zeros(N) for s in sysnames}
    tops = {s: np.zeros((N, 4)) for s in sysnames}
    rr = {s: np.zeros(N) for s in sysnames}
    raw_legal, masked_legal = np.zeros(N), np.zeros(N)
    feats: List[Dict[str, str]] = []

    import torch
    with torch.no_grad():
        for s in range(0, N, batch):
            recs = test[s:s + batch]
            b = collate([encode_record(r) for r in recs])
            raw = model.forward_batch(b)
            st = batch_stats(raw, b["legal_mask"], b["target"])
            e = s + len(recs)
            nll["transformer"][s:e] = st["nll"].numpy()
            rk = st["rank"].numpy()
            for j, k in enumerate(TOPK):
                tops["transformer"][s:e, j] = rk <= k
            rr["transformer"][s:e] = 1.0 / rk
            raw_legal[s:e] = st["raw_legal"].numpy()
            masked_legal[s:e] = st["masked_legal"].numpy()
            if (s // batch) % 20 == 0:
                print(f"  transformer {e}/{N} ({time.time() - t0:.0f}s)", flush=True)
    for i, r in enumerate(test):
        p = prepare(r)
        for name in BASELINES:
            a, b_, c = score(name, p, T, hps.get(name, {}))
            nll[name][i], tops[name][i], rr[name][i] = a, b_, c
        feats.append(features(r, seen))
        if i % 20000 == 0:
            print(f"  baselines/features {i}/{N} ({time.time() - t0:.0f}s)", flush=True)

    # ---- groups
    groups = defaultdict(list)
    for i, f in enumerate(feats):
        groups["overall"].append(i)
        for k, v in f.items():
            groups[f"{k}/{v}"].append(i)
    groups = {k: np.array(v) for k, v in groups.items()}

    def summ(system, idx, extra=False):
        ex = {"raw_top1_legal_rate": raw_legal[idx], "masked_top1_legal_rate": masked_legal[idx]} if extra else None
        return aggregate(nll[system][idx], tops[system][idx], rr[system][idx], ex)

    transformer = {g: summ("transformer", idx, True) for g, idx in sorted(groups.items())
                   if not g.startswith("eco/") or len(idx) >= 200}
    baselines_overall = {s: aggregate(nll[s], tops[s], rr[s]) for s in sysnames}
    major = [g for g in groups if g.split("/")[0] in ("speed", "color", "phase", "tactical", "board", "material", "capture")]
    baselines_by_group = {g: {s: aggregate(nll[s][groups[g]], tops[s][groups[g]], rr[s][groups[g]]) for s in sysnames}
                          for g in sorted(major)}
    uniform_ppl = math.exp(float(np.mean(nll["random"])))

    report = {
        "checkpoint": str(checkpoint), "checkpoint_meta": {k: v for k, v in meta.items() if k in ("trained_steps", "epoch", "run_name", "encoding_version")},
        "test_positions": N, "used_for_selection": False,
        "uniform_random_perplexity": uniform_ppl,
        "transformer": transformer,
        "seconds": round(time.time() - t0, 1),
        "limitations": [
            "Accuracy measures imitation of the historical Magnus move among legal moves, not move quality.",
            "~15% of test boards also occur in train (repeated opening positions); see board/seen_in_train vs unseen_in_train.",
            "The split is by game, so games from the same online match can share openings and opponents.",
            "'classical' has 0 positions; 'unknown' means the source gave no time control and is NOT assumed classical.",
            "About half of all positions are bullet/ultrabullet online play, so overall numbers reflect that mix.",
        ],
    }
    base = {"descriptions": BASELINE_DESC, "tuning": {k: {"validation_loss": v[0], **v[1]} for k, v in tuned.items()},
            "tuning_data": "first 20000 VALIDATION positions", "test_positions": N,
            "overall": baselines_overall, "by_group": baselines_by_group}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "test_evaluation.json").write_text(json.dumps(report, indent=2))
    (out_dir / "baselines.json").write_text(json.dumps(base, indent=2))
    np.savez_compressed(out_dir / "eval_test_positions.npz", **{f"{s}_nll": nll[s] for s in sysnames},
                        **{f"{s}_rr": rr[s] for s in sysnames}, **{f"{s}_tops": tops[s] for s in sysnames})
    print(json.dumps({"overall_transformer": transformer["overall"], "baselines": baselines_overall}, indent=1))
    return report, base


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", default=str(ROOT / "outputs/runs/stage3_full_epoch/best.pt"))
    ap.add_argument("--out", default=str(ROOT / "outputs"))
    ap.add_argument("--max-test", type=int, default=None)
    a = ap.parse_args()
    run(a.checkpoint, a.out, a.max_test)
