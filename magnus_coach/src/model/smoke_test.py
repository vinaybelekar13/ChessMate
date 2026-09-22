"""Model smoke test (NOT training).

Run:  .\\.venv\\Scripts\\python.exe -m src.model.smoke_test

1. builds the default model, writes models/final/model_config.json
2. forward pass + legal masking on 512 REAL Magnus decision positions
3. checks that every historical Magnus move in the corpus is a legal move
   with a slot in the move space (read-only replay; no dataset is written)
4. measures memory and the time of a forward / forward+backward step
5. saves an UNTRAINED checkpoint (trained_steps=0) and runs FEN inference

Nothing here updates weights, so no accuracy number is meaningful: an
untrained model only proves the plumbing.
"""

from __future__ import annotations

import json
import math
import resource
import sys
import time
from collections import Counter
from pathlib import Path

import chess
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.inference.predict import MagnusPredictor  # noqa: E402
from src.model import MagnusModel, MagnusModelConfig, load_checkpoint, save_checkpoint, save_config_json  # noqa: E402
from src.model.encoding import HISTORY_LEN, collate, encode_position  # noqa: E402
from src.model.move_space import NUM_MOVES, UNDERPROMO_OFFSET, move_to_index  # noqa: E402

CORPUS = ROOT / "data" / "cleaned" / "magnus_games.jsonl"
CONFIG_PATH = ROOT / "models" / "final" / "model_config.json"
SMOKE_CKPT = ROOT / "outputs" / "smoke" / "untrained_smoke.pt"
REPORT = ROOT / "outputs" / "model_smoke_test.json"


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # Linux: KB -> MB


def iter_magnus_positions(every_nth_game=1):
    """Yield (board_before, played_move, game) for each Magnus decision."""
    with open(CORPUS, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i % every_nth_game:
                continue
            g = json.loads(line)
            board = chess.Board(g["start_fen"])
            magnus_white = g["magnus_color"] == "white"
            for ply, uci in enumerate(g["moves"]):
                move = chess.Move.from_uci(uci)
                if (board.turn == chess.WHITE) == magnus_white:
                    yield board, move, g, ply
                board.push(move)


def sample_real_positions(n=512):
    """Spread n real decision positions over the whole corpus (every k-th one)."""
    total = sum(1 for _ in iter_magnus_positions(every_nth_game=25))
    stride = max(total // n, 1)
    items = []
    for j, (board, move, g, ply) in enumerate(iter_magnus_positions(every_nth_game=25)):
        if j % stride or len(items) >= n:
            continue
        history = g["moves"][max(0, ply - HISTORY_LEN):ply]
        items.append((encode_position(board, history, g.get("time_control") or None, g.get("speed")),
                      move_to_index(move, board.turn), g["speed"]))
    return items


def geometrically_possible_slots():
    """Slots some legal move could ever occupy: from->to pairs reachable by queen
    or knight geometry on an empty board (covers every piece incl. pawns and
    castling) plus all underpromotion slots. An UPPER bound on reachable slots."""
    slots = set()
    for sq in range(64):
        for piece_type in (chess.QUEEN, chess.KNIGHT):
            board = chess.Board(None)
            board.set_piece_at(sq, chess.Piece(piece_type, chess.WHITE))
            slots.update(sq * 64 + t for t in board.attacks(sq))
    slots.update(range(UNDERPROMO_OFFSET, NUM_MOVES))
    return slots


def target_coverage():
    """Replay ALL games: is every Magnus move legal and inside the move space?"""
    total = illegal = out_of_range = 0
    slots = Counter()
    for board, move, _g, _ply in iter_magnus_positions():
        total += 1
        idx = move_to_index(move, board.turn)
        if not 0 <= idx < NUM_MOVES:
            out_of_range += 1
        if move not in board.legal_moves:
            illegal += 1
        slots[idx] += 1
    return total, illegal, out_of_range, slots


def main():
    torch.manual_seed(0)
    report = {"note": "UNTRAINED weights: plumbing checks only, no accuracy claims."}
    report["torch_threads"] = torch.get_num_threads()
    rss0 = rss_mb()

    # ---- 1. build + config
    cfg = MagnusModelConfig()
    model = MagnusModel(cfg).eval()
    n_params = model.parameter_count()
    save_config_json(cfg, CONFIG_PATH, n_params)
    report["parameter_count"] = n_params
    report["parameter_megabytes_fp32"] = round(n_params * 4 / 1e6, 3)
    report["config_written_to"] = str(CONFIG_PATH.relative_to(ROOT))
    rss1 = rss_mb()
    print(f"[1] model built: {n_params:,} params ({n_params * 4 / 1e6:.2f} MB fp32); config -> {CONFIG_PATH}")

    # ---- 2. forward + masking on real positions
    items = sample_real_positions(512)
    batch = collate([it[0] for it in items])
    targets = torch.tensor([it[1] for it in items])
    speed_mix = dict(Counter(it[2] for it in items))
    with torch.no_grad():
        t0 = time.perf_counter()
        logits = model.forward_batch(batch)
        fwd_s = time.perf_counter() - t0
        probs = model.probs(batch)
        loss = F.cross_entropy(model.masked_logits(batch), targets).item()
    mask = batch["legal_mask"]
    n_legal = mask.sum(1).float()
    fwd = {
        "batch_size": len(items),
        "speed_mix_of_sample": speed_mix,
        "logits_shape": list(logits.shape),
        "all_logits_finite": bool(torch.isfinite(logits).all()),
        "max_abs_prob_sum_error": float((probs.sum(1) - 1).abs().max()),
        "max_prob_on_illegal_moves": float(probs[~mask].max()),
        "argmax_is_legal_fraction": float(mask.gather(1, probs.argmax(1, keepdim=True)).float().mean()),
        "targets_are_legal_fraction": float(mask.gather(1, targets[:, None]).float().mean()),
        "mean_legal_moves": float(n_legal.mean()),
        "untrained_cross_entropy": round(loss, 4),
        "uniform_over_legal_cross_entropy": round(float(torch.log(n_legal).mean()), 4),
        "forward_seconds_batch512": round(fwd_s, 3),
    }
    report["forward_and_masking"] = fwd
    print("[2] real-position forward + masking:")
    for k, v in fwd.items():
        print(f"      {k}: {v}")
    assert fwd["all_logits_finite"] and fwd["max_prob_on_illegal_moves"] == 0.0
    assert fwd["argmax_is_legal_fraction"] == 1.0 and fwd["targets_are_legal_fraction"] == 1.0

    # ---- 3. coverage of every historical Magnus move
    t0 = time.perf_counter()
    total, illegal, oor, slots = target_coverage()
    possible = geometrically_possible_slots()
    unseen_possible = sorted(possible - set(slots))
    impossible_seen = sorted(set(slots) - possible)
    cov = {
        "magnus_decision_positions": total,
        "targets_illegal": illegal,
        "targets_outside_move_space": oor,
        "move_space_size": NUM_MOVES,
        "geometrically_possible_slots_upper_bound": len(possible),
        "distinct_slots_seen_as_targets": len(slots),
        "seen_slots_that_are_geometrically_impossible": len(impossible_seen),  # must be 0
        "possible_slots_never_seen_as_target": len(unseen_possible),
        "of_which_underpromotions": sum(1 for i in unseen_possible if i >= UNDERPROMO_OFFSET),
        "of_which_normal_moves": sum(1 for i in unseen_possible if i < UNDERPROMO_OFFSET),
        "note": ("Every legal move has a slot. Possible slots never seen as a target get only negative "
                 "training signal, so the trained model will give them very low probability; that is a "
                 "data limit, not an architectural one."),
        "seconds": round(time.perf_counter() - t0, 1),
    }
    report["corpus_target_coverage"] = cov
    print("[3] full-corpus target coverage:")
    for k, v in cov.items():
        print(f"      {k}: {v}")
    assert illegal == 0 and oor == 0 and not impossible_seen

    # ---- 4. memory + step time
    train_model = MagnusModel(cfg).train()
    opt = torch.optim.AdamW(train_model.parameters(), lr=1e-3)
    bs = 256
    tb = collate([items[i % len(items)][0] for i in range(bs)])
    tt = torch.tensor([items[i % len(items)][1] for i in range(bs)])
    rss2 = rss_mb()
    times = []
    for _ in range(3):
        t0 = time.perf_counter()
        opt.zero_grad()
        F.cross_entropy(train_model.masked_logits(tb), tt).backward()
        # NOTE: no optimizer.step(): this is a timing probe, not training.
        times.append(time.perf_counter() - t0)
    rss3 = rss_mb()
    step_s = sum(times) / len(times)
    positions = total
    mem = {
        "peak_rss_mb_after_imports": round(rss0, 1),
        "peak_rss_mb_after_model_build": round(rss1, 1),
        "peak_rss_mb_after_train_batch256_fwd_bwd": round(rss3, 1),
        "approx_train_batch256_working_set_mb": round(rss3 - rss2, 1),
        "adamw_state_mb_fp32": round(n_params * 4 * 2 / 1e6, 2),
        "train_step_seconds_batch256_fwd_bwd": round(step_s, 3),
        "torch_threads": torch.get_num_threads(),
        "projected_seconds_per_epoch_all_positions": round(step_s * positions / bs),
        "projected_hours_per_epoch_all_positions": round(step_s * positions / bs / 3600, 2),
        "projection_caveat": ("measured on THIS sandbox with the thread count above; ignores data loading "
                              "and optimizer step; your machine will differ. Uses all 721k positions - a "
                              "train split is ~80% of that."),
    }
    report["memory_and_speed"] = mem
    print("[4] memory / speed:")
    for k, v in mem.items():
        print(f"      {k}: {v}")

    # ---- 5. untrained checkpoint + FEN inference
    save_checkpoint(model, SMOKE_CKPT, meta={"trained_steps": 0, "purpose": "smoke test, random weights"})
    reloaded, meta = load_checkpoint(SMOKE_CKPT)
    with torch.no_grad():
        same = bool(torch.equal(model.forward_batch(batch), reloaded.forward_batch(batch)))
    predictor = MagnusPredictor(reloaded, meta)
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
    top = predictor.predict(fen, top_k=5, time_control="180+0", history_uci=["g1f3", "b8c6", "f1c4", "g8f6"][-4:])
    board = chess.Board(fen)
    ck = {
        "checkpoint_bytes": SMOKE_CKPT.stat().st_size,
        "reload_outputs_bit_identical": same,
        "predictor_is_trained": predictor.is_trained,
        "fen_inference_top5_UNTRAINED_random_weights": top,
        "all_top5_legal": all(chess.Move.from_uci(t["uci"]) in board.legal_moves for t in top),
    }
    report["checkpoint_and_inference"] = ck
    print("[5] checkpoint + inference (random weights - the ranking below is meaningless):")
    for k, v in ck.items():
        print(f"      {k}: {v}")
    assert same and ck["all_top5_legal"] and not predictor.is_trained

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSMOKE TEST PASSED. Report: {REPORT}")


if __name__ == "__main__":
    main()
