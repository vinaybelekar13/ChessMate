import json
import math

import pytest
import torch

from src.model import train as T
from src.model.checkpoint import load_checkpoint, load_payload
from src.model.dataset import PositionDataset
from src.model.move_space import legal_moves_with_indices
from tests.helpers import write_fake_split

TINY_MODEL = {"d_model": 32, "n_layers": 1, "n_heads": 2, "d_ff": 64, "policy_dim": 16}


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    d = tmp_path_factory.mktemp("train_data")
    write_fake_split(d / "train.jsonl", range(0, 4), "train", prefix="mc_tr", plies=40)
    write_fake_split(d / "val.jsonl", range(100, 102), "validation", prefix="mc_va", plies=40)
    return d


def cfg(data, tmp_path, **kw):
    base = dict(train_path=str(data / "train.jsonl"), val_path=str(data / "val.jsonl"), out_dir=str(tmp_path),
                run_name="r", epochs=2, batch_size=32, lr=3e-3, warmup_steps=2, seed=0, log_every=1000,
                model=TINY_MODEL, threads=1)
    base.update(kw)
    return T.TrainConfig(**base)


# ------------------------------------------------------------------ schedule
def test_lr_schedule_warms_up_peaks_then_decays_to_floor():
    f = [T.lr_factor(s, warmup=10, total=100, min_ratio=0.1) for s in range(100)]
    assert f[0] < f[5] < f[9] and abs(f[10] - 1.0) < 1e-9
    assert all(f[i] >= f[i + 1] - 1e-12 for i in range(10, 99))
    assert abs(T.lr_factor(100, 10, 100, 0.1) - 0.1) < 1e-9
    assert T.lr_factor(10 ** 6, 10, 100, 0.1) == pytest.approx(0.1)          # clamped past the end


# ------------------------------------------------------------------ end-to-end on tiny data
def test_training_run_produces_all_artifacts_and_valid_history(data, tmp_path):
    res = T.train(cfg(data, tmp_path))
    run = tmp_path / "r"
    for name in ("best.pt", "last.pt", "final.pt", "epoch_001.pt", "epoch_002.pt", "training_history.json",
                 "train_log.jsonl", "train_config.json", "run_summary.json"):
        assert (run / name).exists(), name
    hist = json.loads((run / "training_history.json").read_text())
    assert hist["completed"] and len(hist["epochs"]) == 2 and hist["initial_validation"]["n"] > 0
    e = hist["epochs"][-1]
    for grp in ["overall", "color/white", "color/black"]:
        assert grp in e["val"]
    assert any(k.startswith("speed/") for k in e["val"])
    for k in ("loss", "perplexity", "top1", "top3", "top5", "top10", "mrr", "raw_top1_legal_rate"):
        assert k in e["val"]["overall"]
    assert res["completed"] and res["global_step"] == hist["total_steps_done"]


def test_loss_decreases_when_the_model_can_fit_the_data(tmp_path):
    """Gradient check: a tiny training set must be memorisable."""
    write_fake_split(tmp_path / "t.jsonl", range(0, 2), "train", prefix="mc_x", plies=34)
    write_fake_split(tmp_path / "v.jsonl", range(50, 51), "validation", prefix="mc_y", plies=34)
    c = T.TrainConfig(train_path=str(tmp_path / "t.jsonl"), val_path=str(tmp_path / "v.jsonl"),
                      out_dir=str(tmp_path), run_name="fit", epochs=40, batch_size=64, lr=5e-3, warmup_steps=2,
                      model={**TINY_MODEL, "dropout": 0.0}, log_every=1000, keep_epoch_checkpoints=False, threads=1)
    T.train(c)
    hist = json.loads((tmp_path / "fit" / "training_history.json").read_text())
    first, last = hist["epochs"][0]["train_loss"], hist["epochs"][-1]["train_loss"]
    assert last < 0.75 * first, (first, last)
    assert first > 1.5                                                         # started near ln(#legal moves)


def test_best_checkpoint_is_the_lowest_validation_loss(data, tmp_path):
    T.train(cfg(data, tmp_path, epochs=3))
    hist = json.loads((tmp_path / "r" / "training_history.json").read_text())
    best = min(e["val_headline"]["loss"] for e in hist["epochs"])
    assert hist["best"]["loss"] == pytest.approx(best)
    meta = load_payload(tmp_path / "r" / "best.pt")["meta"]
    assert meta["val"]["loss"] == pytest.approx(best)


def test_saved_models_reload_and_predict_only_legal_moves(data, tmp_path):
    T.train(cfg(data, tmp_path, epochs=1))
    for name in ("best.pt", "final.pt", "last.pt"):
        model, meta = load_checkpoint(tmp_path / "r" / name)
        assert meta["trained_steps"] > 0
        ds = PositionDataset(data / "val.jsonl")
        from src.model.dataset import collate
        batch = collate([ds[i] for i in range(0, 40, 4)])
        p = model.probs(batch)
        assert torch.equal(p > 0, batch["legal_mask"])                          # mass only on legal moves


# ------------------------------------------------------------------ exact resume
def test_resume_mid_epoch_reproduces_uninterrupted_run_exactly(data, tmp_path):
    a = T.train(cfg(data, tmp_path / "A", epochs=3))
    # interrupted after 5 steps (mid-epoch 2 with 5 steps/epoch), then resumed
    part = T.train(cfg(data, tmp_path / "B", epochs=3, max_steps=7))
    assert not part["completed"] and part["global_step"] == 7
    b = T.train(cfg(data, tmp_path / "B", epochs=3, resume=True))
    assert b["completed"] and b["global_step"] == a["global_step"]
    ma, _ = load_checkpoint(tmp_path / "A" / "r" / "final.pt")
    mb, _ = load_checkpoint(tmp_path / "B" / "r" / "final.pt")
    for (n1, p1), (n2, p2) in zip(ma.state_dict().items(), mb.state_dict().items()):
        assert n1 == n2 and torch.equal(p1, p2), n1
    ha = json.loads((tmp_path / "A" / "r" / "training_history.json").read_text())
    hb = json.loads((tmp_path / "B" / "r" / "training_history.json").read_text())
    assert [e["train_loss"] for e in ha["epochs"]] == [e["train_loss"] for e in hb["epochs"]]


def test_resume_restores_optimizer_and_scheduler_state(data, tmp_path):
    T.train(cfg(data, tmp_path, epochs=3, max_steps=4))
    p = load_payload(tmp_path / "r" / "last.pt")
    assert p["train_state"]["global_step"] == 4 and "optimizer_state" in p and "scheduler_state" in p
    assert p["scheduler_state"]["last_epoch"] == 4


# ------------------------------------------------------------------ guards
def test_trainer_refuses_splits_that_share_a_game(data, tmp_path):
    write_fake_split(tmp_path / "leaky_val.jsonl", range(2, 4), "validation", prefix="mc_tr", plies=40)  # games 2,3 also in train
    with pytest.raises(AssertionError, match="LEAKAGE"):
        T.train(cfg(data, tmp_path, val_path=str(tmp_path / "leaky_val.jsonl")))


def test_evaluate_is_deterministic_and_restores_train_mode(data):
    torch.manual_seed(0)
    m = T.MagnusModel(T.MagnusModelConfig(**TINY_MODEL)).train()
    ds = PositionDataset(data / "val.jsonl")
    a, b = T.evaluate(m, ds), T.evaluate(m, ds)
    assert a == b and m.training
    assert a["overall"]["n"] == len(ds)
    # untrained model ~ uniform over legal moves
    assert abs(a["overall"]["loss"] - math.log(a["overall"]["uniform_perplexity"])) < 1.0


def test_max_positions_uses_a_deterministic_subset(data):
    torch.manual_seed(0)
    m = T.MagnusModel(T.MagnusModelConfig(**TINY_MODEL))
    ds = PositionDataset(data / "val.jsonl")
    a, b = T.evaluate(m, ds, max_positions=20, seed=1), T.evaluate(m, ds, max_positions=20, seed=1)
    assert a == b and a["overall"]["n"] == 20
