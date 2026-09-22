import json
import pickle
from pathlib import Path

import chess
import pytest
import torch

from src.model import dataset as D
from src.model.encoding import MODEL_INPUT_KEYS, NUM_NUMERIC, SPEEDS
from src.model.move_space import NUM_MOVES, move_to_index
from tests.helpers import write_fake_split

ROOT = Path(__file__).resolve().parents[1]
SPLIT_DIR = ROOT / "data" / "splits"
REAL = all((SPLIT_DIR / f"{s}.jsonl").exists() for s in ("train", "validation", "test"))


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    path = tmp_path_factory.mktemp("d") / "train.jsonl"
    recs, _ = write_fake_split(path, range(0, 12), "train")
    return path, recs


def test_length_and_item_contract(tiny):
    path, recs = tiny
    ds = D.PositionDataset(path)
    assert len(ds) == len(recs)
    item = ds[0]
    for k in MODEL_INPUT_KEYS + ("legal_mask", "target", "color"):
        assert k in item
    assert item["squares"].shape == (64,) and item["numeric"].shape == (NUM_NUMERIC,)
    assert item["legal_mask"].shape == (NUM_MOVES,) and item["target"].dtype == torch.long


def test_target_is_the_historical_move_and_is_legal(tiny):
    path, recs = tiny
    ds = D.PositionDataset(path)
    for i in range(0, len(ds), 7):
        item, rec = ds[i], recs[i]
        turn = chess.WHITE if rec["fen_before"].split()[1] == "w" else chess.BLACK
        assert item["target"].item() == move_to_index(chess.Move.from_uci(rec["target_move_uci"]), turn)
        assert item["legal_mask"][item["target"]]
        assert int(item["legal_mask"].sum()) == len(rec["legal_moves_uci"])   # mask == stored legal list


def test_mask_equals_stored_legal_moves_exactly(tiny):
    path, recs = tiny
    ds = D.PositionDataset(path)
    for i in range(0, len(ds), 5):
        turn = chess.WHITE if recs[i]["fen_before"].split()[1] == "w" else chess.BLACK
        expected = {move_to_index(chess.Move.from_uci(u), turn) for u in recs[i]["legal_moves_uci"]}
        assert set(ds[i]["legal_mask"].nonzero().flatten().tolist()) == expected


def test_encoding_is_deterministic(tiny):
    ds = D.PositionDataset(tiny[0])
    a, b = ds[3], ds[3]
    assert all(torch.equal(a[k], b[k]) for k in a)
    ds2 = D.PositionDataset(tiny[0])
    assert all(torch.equal(a[k], ds2[3][k]) for k in a)


def test_speed_and_color_metadata_reach_tensors(tiny):
    path, recs = tiny
    ds = D.PositionDataset(path)
    for i in range(0, len(ds), 9):
        assert SPEEDS[ds[i]["speed"].item()] == recs[i]["speed"].replace("unspecified", "unknown")
        assert ds[i]["color"].item() == (0 if recs[i]["magnus_color"] == "white" else 1)


def test_subset_is_deterministic_and_smaller(tiny):
    ds = D.PositionDataset(tiny[0])
    a, b = ds.subset(50, seed=3), ds.subset(50, seed=3)
    assert len(a) == 50 and (a.offsets == b.offsets).all()
    assert not (ds.subset(50, seed=4).offsets == a.offsets).all()
    assert ds.subset(None) is ds and ds.subset(10 ** 9) is ds


def test_dataset_is_picklable_for_windows_workers(tiny):
    ds = D.PositionDataset(tiny[0])
    _ = ds[0]                                                   # opens the file handle
    ds2 = pickle.loads(pickle.dumps(ds))
    assert len(ds2) == len(ds) and torch.equal(ds2[1]["squares"], ds[1]["squares"])


def test_epoch_batches_cover_every_index_once_and_are_reproducible():
    b = D.epoch_batches(103, 16, seed=1, epoch=0)
    flat = [i for batch in b for i in batch]
    assert sorted(flat) == list(range(103)) and len(b) == 7 and len(b[-1]) == 103 % 16
    assert b == D.epoch_batches(103, 16, seed=1, epoch=0)
    assert b != D.epoch_batches(103, 16, seed=1, epoch=1)
    assert D.epoch_batches(10, 4, 0, 0, shuffle=False) == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]]


def test_loader_yields_stacked_batches(tiny):
    ds = D.PositionDataset(tiny[0])
    batches = D.epoch_batches(len(ds), 16, 0, 0)
    first = next(iter(D.make_loader(ds, batches)))
    assert first["squares"].shape[0] == len(batches[0]) and first["legal_mask"].shape[1] == NUM_MOVES


def test_illegal_label_is_rejected_at_encode_time(tiny):
    rec = json.loads(open(tiny[0]).readline())
    rec["target_move_uci"] = "a1a8"
    with pytest.raises(ValueError):
        D.encode_record(rec)


# ------------------------------------------------------------------ split integrity
def test_leakage_guard_passes_for_disjoint_and_fails_for_shared_game(tmp_path):
    write_fake_split(tmp_path / "a.jsonl", range(0, 5), "train", prefix="mc_a")
    write_fake_split(tmp_path / "b.jsonl", range(0, 5), "validation", prefix="mc_b")
    counts = D.assert_no_game_overlap({"train": tmp_path / "a.jsonl", "validation": tmp_path / "b.jsonl"})
    assert counts == {"train": 5, "validation": 5}
    write_fake_split(tmp_path / "c.jsonl", range(3, 8), "test", prefix="mc_a")      # games 3,4 repeat train's
    with pytest.raises(AssertionError, match="LEAKAGE"):
        D.assert_no_game_overlap({"train": tmp_path / "a.jsonl", "test": tmp_path / "c.jsonl"})


# ------------------------------------------------------------------ REAL dataset
@pytest.mark.skipif(not REAL, reason="real dataset not built")
def test_real_positions_encode_correctly_and_deterministically():
    ds = D.PositionDataset(SPLIT_DIR / "validation.jsonl").subset(400, seed=0)
    speeds = set()
    for i in range(len(ds)):
        rec, item = ds.record(i), ds[i]
        turn = chess.WHITE if rec["fen_before"].split()[1] == "w" else chess.BLACK
        expected = {move_to_index(chess.Move.from_uci(u), turn) for u in rec["legal_moves_uci"]}
        assert set(item["legal_mask"].nonzero().flatten().tolist()) == expected
        assert item["legal_mask"][item["target"]]
        assert all(torch.equal(item[k], ds[i][k]) for k in item)          # deterministic
        assert item["numeric"][6].item() == (1.0 if turn == chess.BLACK else 0.0)   # played_as_black
        speeds.add(SPEEDS[item["speed"].item()])
    assert len(speeds) >= 3                                                # bullet/blitz/unknown/... all reach the encoder


@pytest.mark.skipif(not REAL, reason="real dataset not built")
def test_real_splits_share_no_game():
    counts = D.assert_no_game_overlap({s: SPLIT_DIR / f"{s}.jsonl" for s in ("train", "validation", "test")})
    assert counts["train"] > counts["validation"] > 0 and counts["test"] > 0


def test_leakage_guard_detects_non_hex_ids_and_refuses_records_without_game_id(tmp_path):
    """REGRESSION: the guard used a hex-only regex and silently matched nothing for other ids."""
    write_fake_split(tmp_path / "a.jsonl", range(0, 3), "train", prefix="mc_tr")
    write_fake_split(tmp_path / "b.jsonl", range(2, 5), "validation", prefix="mc_tr")   # game 2 shared
    with pytest.raises(AssertionError, match="LEAKAGE"):
        D.assert_no_game_overlap({"train": tmp_path / "a.jsonl", "validation": tmp_path / "b.jsonl"})
    (tmp_path / "bad.jsonl").write_text('{"position_id":"x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="no game_id"):
        D.collect_game_ids(tmp_path / "bad.jsonl")
