"""Production training pipeline for the Magnus behavioural model.

    python -m src.model.train --train data/splits/train.jsonl \\
        --val data/splits/validation.jsonl --run-name smoke2k \\
        --max-train-positions 2000 --max-val-positions 1000 --epochs 1

Loss: cross-entropy over the fixed 4162-move space with illegal moves masked
out (they cannot receive probability). Labels are always the historical
Magnus move.

Outputs in <out_dir>/<run_name>/:
    best.pt            lowest validation loss so far
    last.pt            latest state incl. optimizer/scheduler/RNG (for --resume)
    epoch_NNN.pt       one per finished epoch (optional)
    final.pt           weights at the end of training
    training_history.json   machine-readable per-epoch metrics (overall, by speed, by colour)
    train_log.jsonl    per-N-step loss / lr / grad-norm
    train_config.json  exact configuration used
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.model.checkpoint import load_payload, save_checkpoint  # noqa: E402
from src.model.config import MagnusModelConfig  # noqa: E402
from src.model.dataset import PositionDataset, assert_no_game_overlap, collate, epoch_batches, make_loader  # noqa: E402
from src.model.encoding import ENCODING_VERSION, model_inputs  # noqa: E402
from src.model.magnus_model import MagnusModel, mask_logits  # noqa: E402
from src.model.metrics import MetricAccumulator  # noqa: E402


@dataclass
class TrainConfig:
    train_path: str = "data/splits/train.jsonl"
    val_path: str = "data/splits/validation.jsonl"
    test_path: Optional[str] = None          # only used for the leakage check
    out_dir: str = "outputs/runs"
    run_name: str = "run"
    epochs: int = 1
    batch_size: int = 256
    lr: float = 1e-3
    weight_decay: float = 0.01
    warmup_steps: int = 100
    min_lr_ratio: float = 0.05               # cosine decays to lr * min_lr_ratio
    grad_clip: float = 1.0
    seed: int = 0
    num_workers: int = 0
    threads: Optional[int] = None            # torch intra-op threads (None = torch default)
    max_train_positions: Optional[int] = None
    max_val_positions: Optional[int] = None
    eval_batch_size: int = 512
    eval_every_steps: int = 0                # 0 = validate only at the end of each epoch
    checkpoint_every_steps: int = 0          # 0 = only at epoch ends
    log_every: int = 50
    max_steps: Optional[int] = None          # stop after this many optimizer steps (stage runs, tests)
    resume: bool = False                     # continue from <run_dir>/last.pt
    early_stopping_patience: int = 0         # epochs without val-loss improvement; 0 = off
    keep_epoch_checkpoints: bool = True
    model: Dict[str, Any] = field(default_factory=dict)  # MagnusModelConfig overrides


# ------------------------------------------------------------------ helpers
def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def lr_factor(step: int, warmup: int, total: int, min_ratio: float) -> float:
    """Linear warm-up then cosine decay to min_ratio."""
    if warmup > 0 and step < warmup:
        return (step + 1) / warmup
    progress = (step - warmup) / max(1, total - warmup)
    progress = min(max(progress, 0.0), 1.0)
    return min_ratio + (1 - min_ratio) * 0.5 * (1 + math.cos(math.pi * progress))


@torch.no_grad()
def evaluate(model: MagnusModel, ds, batch_size: int = 512, max_positions: Optional[int] = None,
             seed: int = 0, num_workers: int = 0) -> Dict[str, Dict[str, float]]:
    """Metrics on `ds` (overall, per speed, per colour). Deterministic subset if max_positions."""
    was_training = model.training
    model.eval()
    ds = ds.subset(max_positions, seed) if max_positions else ds
    batches = epoch_batches(len(ds), batch_size, seed=0, epoch=0, shuffle=False)
    acc = MetricAccumulator()
    for batch in make_loader(ds, batches, num_workers):
        raw = model.forward_batch(batch)
        acc.update(raw, batch["legal_mask"], batch["target"], batch["speed"], batch["color"])
    model.train(was_training)
    return acc.summary()


def _headline(summary: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    o = summary["overall"]
    return {k: o[k] for k in ("n", "loss", "perplexity", "top1", "top3", "top5", "top10", "mrr")}


def _write_json(path: Path, obj):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    tmp.replace(path)


# ------------------------------------------------------------------ main loop
def train(cfg: TrainConfig) -> Dict[str, Any]:
    run_dir = Path(cfg.out_dir) / cfg.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    set_seed(cfg.seed)
    if cfg.threads:
        torch.set_num_threads(cfg.threads)

    # ---- split integrity: no game may appear in two splits
    paths = {"train": cfg.train_path, "validation": cfg.val_path}
    if cfg.test_path:
        paths["test"] = cfg.test_path
    game_counts = assert_no_game_overlap(paths)

    # ---- data
    train_full = PositionDataset(cfg.train_path)
    val_full = PositionDataset(cfg.val_path)
    train_ds = train_full.subset(cfg.max_train_positions, cfg.seed)
    n_train = len(train_ds)
    steps_per_epoch = math.ceil(n_train / cfg.batch_size)
    total_steps = steps_per_epoch * cfg.epochs

    # ---- model / optimiser / scheduler
    model = MagnusModel(MagnusModelConfig(**cfg.model)).train()
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: lr_factor(s, cfg.warmup_steps, total_steps, cfg.min_lr_ratio))

    # ---- progress state (all of it is checkpointed so resume is exact)
    state = {"epoch": 0, "batch_in_epoch": 0, "global_step": 0, "epoch_loss_sum": 0.0,
             "epoch_correct": 0, "epoch_count": 0, "best_val_loss": float("inf"),
             "epochs_since_best": 0, "elapsed_before": 0.0}
    history = {"epochs": [], "best": None}

    last_path = run_dir / "last.pt"
    if cfg.resume and last_path.exists():
        payload = load_payload(last_path)
        model.load_state_dict(payload["model_state"])
        opt.load_state_dict(payload["optimizer_state"])
        sched.load_state_dict(payload["scheduler_state"])
        state.update(payload["train_state"])
        history = json.loads((run_dir / "training_history.json").read_text()) if (
            run_dir / "training_history.json").exists() else history
        torch.set_rng_state(payload["rng_state"])
        history.pop("stopped_mid_epoch", None)
        print(f"[resume] epoch {state['epoch']} batch {state['batch_in_epoch']} step {state['global_step']}")
    elif not cfg.resume and last_path.exists():
        print(f"[warn] {last_path} exists and --resume not set: it will be overwritten")

    _write_json(run_dir / "train_config.json", {
        "train": asdict(cfg), "model": model.config.to_dict(), "parameter_count": model.parameter_count(),
        "encoding_version": ENCODING_VERSION, "train_positions": n_train,
        "validation_positions_available": len(val_full), "games_per_split": game_counts,
        "steps_per_epoch": steps_per_epoch, "total_steps": total_steps,
        "environment": {"python": platform.python_version(), "torch": torch.__version__,
                        "platform": platform.platform(), "threads": torch.get_num_threads()},
    })

    def save_state(path: Path, extra_meta: Optional[dict] = None):
        meta = {"trained_steps": state["global_step"], "epoch": state["epoch"], "seed": cfg.seed,
                "encoding_version": ENCODING_VERSION, "run_name": cfg.run_name,
                "best_val_loss": None if state["best_val_loss"] == float("inf") else state["best_val_loss"]}
        meta.update(extra_meta or {})
        save_checkpoint(model, path, meta=meta, optimizer=opt, extra={
            "scheduler_state": sched.state_dict(), "train_state": dict(state), "rng_state": torch.get_rng_state()})

    def validate_and_track(tag: str) -> Dict[str, Any]:
        summary = evaluate(model, val_full, cfg.eval_batch_size, cfg.max_val_positions, seed=cfg.seed,
                           num_workers=cfg.num_workers)
        head = _headline(summary)
        improved = head["loss"] < state["best_val_loss"]
        if improved:
            state["best_val_loss"], state["epochs_since_best"] = head["loss"], 0
            history["best"] = {"tag": tag, "global_step": state["global_step"], **head}
            save_state(run_dir / "best.pt", {"val": head})
        return {"summary": summary, "headline": head, "improved": improved}

    # ---- baseline validation before any update (so "loss changed" is measurable)
    if state["global_step"] == 0 and "initial_validation" not in history:
        history["initial_validation"] = _headline(evaluate(
            model, val_full, cfg.eval_batch_size, cfg.max_val_positions, seed=cfg.seed, num_workers=cfg.num_workers))
        print(f"[init] val loss {history['initial_validation']['loss']:.4f} "
              f"top1 {history['initial_validation']['top1']:.4f}")

    log_file = open(run_dir / "train_log.jsonl", "a" if cfg.resume else "w", encoding="utf-8")
    t_start = time.time() - state["elapsed_before"]
    stopped_early = False
    interrupted_by_max_steps = False

    while state["epoch"] < cfg.epochs and not stopped_early:
        epoch = state["epoch"]
        batches = epoch_batches(n_train, cfg.batch_size, cfg.seed, epoch)
        skip = state["batch_in_epoch"]
        gen = torch.Generator().manual_seed(cfg.seed * 7919 + epoch)  # keeps global RNG for dropout only
        loader = torch.utils.data.DataLoader(
            train_ds, batch_sampler=batches[skip:], collate_fn=collate,
            num_workers=cfg.num_workers, generator=gen)
        model.train()
        t_epoch = time.time()

        for batch in loader:
            raw = model.forward_batch(batch)
            masked = mask_logits(raw, batch["legal_mask"])
            target = batch["target"]
            loss = F.cross_entropy(masked, target)
            if not torch.isfinite(loss):
                raise RuntimeError(f"non-finite loss at step {state['global_step']}: {loss.item()}")
            opt.zero_grad(set_to_none=True)
            loss.backward()
            grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip).item()
            opt.step()
            sched.step()

            bs = target.shape[0]
            state["global_step"] += 1
            state["batch_in_epoch"] += 1
            state["epoch_loss_sum"] += loss.item() * bs
            state["epoch_correct"] += int((masked.argmax(1) == target).sum())
            state["epoch_count"] += bs

            if cfg.log_every and state["global_step"] % cfg.log_every == 0:
                rec = {"step": state["global_step"], "epoch": epoch, "loss": round(loss.item(), 5),
                       "lr": sched.get_last_lr()[0], "grad_norm": round(grad_norm, 4),
                       "positions_per_sec": round(state["epoch_count"] / max(time.time() - t_epoch, 1e-9), 1)
                       if skip == 0 else None}
                log_file.write(json.dumps(rec) + "\n")
                log_file.flush()
                print(f"  step {state['global_step']:>6}/{total_steps} loss {loss.item():.4f} "
                      f"lr {rec['lr']:.2e} gn {grad_norm:.2f}", flush=True)

            if cfg.eval_every_steps and state["global_step"] % cfg.eval_every_steps == 0:
                v = validate_and_track(f"step{state['global_step']}")
                print(f"  [val@{state['global_step']}] loss {v['headline']['loss']:.4f} top1 {v['headline']['top1']:.4f}")
            if cfg.checkpoint_every_steps and state["global_step"] % cfg.checkpoint_every_steps == 0:
                state["elapsed_before"] = time.time() - t_start
                save_state(last_path)
            if cfg.max_steps and state["global_step"] >= cfg.max_steps:
                interrupted_by_max_steps = True
                break

        if interrupted_by_max_steps and state["batch_in_epoch"] < steps_per_epoch:
            # stopped mid-epoch: persist exact progress so --resume continues here
            state["elapsed_before"] = time.time() - t_start
            save_state(last_path)
            history["stopped_mid_epoch"] = True
            break

        # ---- end of epoch
        train_loss = state["epoch_loss_sum"] / max(state["epoch_count"], 1)
        train_top1 = state["epoch_correct"] / max(state["epoch_count"], 1)
        v = validate_and_track(f"epoch{epoch + 1}")
        entry = {"epoch": epoch + 1, "global_step": state["global_step"], "train_loss": train_loss,
                 "train_top1": train_top1, "lr_end": sched.get_last_lr()[0],
                 "val": v["summary"], "val_headline": v["headline"], "improved": v["improved"],
                 "epoch_seconds": round(time.time() - t_epoch, 1)}
        history["epochs"].append(entry)
        h = v["headline"]
        print(f"[epoch {epoch + 1}/{cfg.epochs}] train loss {train_loss:.4f} top1 {train_top1:.4f} | "
              f"val loss {h['loss']:.4f} ppl {h['perplexity']:.1f} top1 {h['top1']:.4f} top3 {h['top3']:.4f} "
              f"top5 {h['top5']:.4f} {'(best)' if v['improved'] else ''}", flush=True)

        if not v["improved"]:
            state["epochs_since_best"] += 1
        state.update(epoch=epoch + 1, batch_in_epoch=0, epoch_loss_sum=0.0, epoch_correct=0, epoch_count=0,
                     elapsed_before=time.time() - t_start)
        if cfg.keep_epoch_checkpoints:
            save_state(run_dir / f"epoch_{epoch + 1:03d}.pt", {"val": h})
        save_state(last_path)
        _write_json(run_dir / "training_history.json", history)
        if cfg.early_stopping_patience and state["epochs_since_best"] >= cfg.early_stopping_patience:
            print("[early stopping]")
            stopped_early = True
        if interrupted_by_max_steps:
            break

    log_file.close()
    completed = state["epoch"] >= cfg.epochs or stopped_early
    history["completed"] = bool(completed)
    history["total_steps_done"] = state["global_step"]
    save_checkpoint(model, run_dir / "final.pt", meta={
        "trained_steps": state["global_step"], "epoch": state["epoch"], "seed": cfg.seed,
        "encoding_version": ENCODING_VERSION, "run_name": cfg.run_name, "completed": bool(completed),
        "smoke": bool(cfg.max_train_positions and cfg.max_train_positions < 100_000)})
    _write_json(run_dir / "training_history.json", history)
    summary = {"run_dir": str(run_dir), "completed": bool(completed), "global_step": state["global_step"],
               "train_positions": n_train, "initial_validation": history.get("initial_validation"),
               "final_validation": history["epochs"][-1]["val_headline"] if history["epochs"] else None,
               "best": history["best"], "seconds": round(time.time() - t_start, 1)}
    _write_json(run_dir / "run_summary.json", summary)
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    d = TrainConfig()
    ap.add_argument("--train", dest="train_path", default=d.train_path)
    ap.add_argument("--val", dest="val_path", default=d.val_path)
    ap.add_argument("--test", dest="test_path", default=None, help="only used for the leakage check")
    ap.add_argument("--out-dir", default=d.out_dir)
    ap.add_argument("--run-name", default=d.run_name)
    for name in ("epochs", "batch_size", "warmup_steps", "seed", "num_workers", "log_every", "eval_batch_size",
                 "eval_every_steps", "checkpoint_every_steps", "early_stopping_patience"):
        ap.add_argument("--" + name.replace("_", "-"), type=int, default=getattr(d, name))
    for name in ("lr", "weight_decay", "min_lr_ratio", "grad_clip"):
        ap.add_argument("--" + name.replace("_", "-"), type=float, default=getattr(d, name))
    for name in ("threads", "max_train_positions", "max_val_positions", "max_steps"):
        ap.add_argument("--" + name.replace("_", "-"), type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--no-epoch-checkpoints", dest="keep_epoch_checkpoints", action="store_false")
    ap.add_argument("--model", type=json.loads, default={}, help='JSON overrides, e.g. \'{"d_model":64}\'')
    args = ap.parse_args(argv)
    cfg = TrainConfig(**{k: v for k, v in vars(args).items()})
    result = train(cfg)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
