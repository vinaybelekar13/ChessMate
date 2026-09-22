import copy
import json
from pathlib import Path

import chess
import pytest

from src.data import positions as P
from src.data.splits import magnus_decisions
from tests.helpers import fake_game

ROOT = Path(__file__).resolve().parents[1]
SPLIT_DIR = ROOT / "data" / "splits"


# ------------------------------------------------------------------ record creation
@pytest.mark.parametrize("seed", range(6))
def test_one_record_per_magnus_decision_with_historical_label(seed):
    g = fake_game(seed)
    recs = list(P.make_records(g, "train"))
    assert len(recs) == magnus_decisions(len(g["moves"]), g["magnus_color"])
    board = chess.Board()
    by_ply = {r["ply"]: r for r in recs}
    for i, uci in enumerate(g["moves"], start=1):
        if i in by_ply:
            r = by_ply[i]
            assert r["target_move_uci"] == uci                      # label = the actual historical move
            assert r["fen_before"] == board.fen()                   # position BEFORE the move
            assert (board.turn == chess.WHITE) == (g["magnus_color"] == "white")
            assert r["last_5_moves_uci"] == g["moves"][max(0, i - 6):i - 1]
            assert r["next_moves_uci"] == g["moves"][i:i + 5]
        board.push(chess.Move.from_uci(uci))


def test_required_fields_present_and_types():
    r = next(P.make_records(fake_game(2), "validation"))
    assert all(f in r for f in P.REQUIRED_FIELDS)
    assert r["split"] == "validation" and r["speed"] in P.SPEEDS
    assert isinstance(r["legal_moves_uci"], list) and r["legal_moves_uci"] == sorted(r["legal_moves_uci"])
    assert json.loads(json.dumps(r)) == r                           # JSON round-trips exactly


def test_unspecified_time_control_becomes_unknown_not_classical():
    g = fake_game(5)                                                # seed 5 -> "unspecified"
    assert g["speed"] == "unspecified"
    assert next(P.make_records(g, "train"))["speed"] == "unknown"


def test_illegal_move_excludes_whole_game():
    g = fake_game(1, plies=30)
    g["moves"][10] = "a1a8"                                         # corrupt one move
    with pytest.raises(P.GameReplayError):
        list(P.make_records(g, "train"))


def test_non_standard_start_is_rejected():
    g = fake_game(1)
    g["start_fen"] = "8/8/8/8/8/8/8/K1k5 w - - 0 1"
    with pytest.raises(P.GameReplayError):
        list(P.make_records(g, "train"))


# ------------------------------------------------------------------ validation catches each defect
def good():
    return next(r for r in P.make_records(fake_game(7, plies=40), "train") if r["ply"] > 6)


def test_valid_record_passes():
    assert P.validate_position_record(good()) == []


def tamper(**changes):
    r = copy.deepcopy(good())
    r.update(changes)
    return r


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"fen_before": "not a fen"}, "invalid_fen"),
        ({"fen_before": "8/8/8/8/8/8/8/8 w - - 0 1"}, "invalid_fen"),                       # no kings
        ({"target_move_uci": "a1a8"}, "target_illegal"),
        ({"target_move_uci": "zz"}, "target_not_uci"),
        ({"target_move_san": "Qh5#"}, "san_mismatch"),
        ({"legal_moves_uci": []}, "target_not_in_legal_moves_uci"),
        ({"move_number": 999}, "move_number_mismatch"),
        ({"ply": 999}, "ply_mismatch"),
        ({"speed": "lightning"}, "bad_speed"),
        ({"last_5_moves_uci": ["e2e4"] * 6}, "bad_history"),
        ({"last_5_moves_uci": ["nonsense"]}, "bad_history"),
    ],
)
def test_validator_detects_defect(changes, expected):
    assert expected in P.validate_position_record(tamper(**changes))


def test_validator_detects_wrong_side_to_move():
    r = good()
    other = "black" if r["magnus_color"] == "white" else "white"
    assert "side_to_move_is_not_magnus" in P.validate_position_record(tamper(magnus_color=other))


def test_validator_detects_legal_list_with_extra_or_missing_moves():
    r = good()
    assert "legal_moves_uci_mismatch" in P.validate_position_record(
        tamper(legal_moves_uci=sorted(r["legal_moves_uci"] + ["a1a8"])))
    assert "legal_moves_uci_mismatch" in P.validate_position_record(
        tamper(legal_moves_uci=[m for m in r["legal_moves_uci"] if m != "zz"][:-1] + [r["target_move_uci"]]))


def test_validator_reports_missing_fields():
    r = good()
    del r["fen_before"]
    assert P.validate_position_record(r)[0].startswith("missing_fields")


# ------------------------------------------------------------------ real dataset (skipped if not built)
REAL = all((SPLIT_DIR / f"{s}.jsonl").exists() for s in ("train", "validation", "test"))


@pytest.mark.skipif(not REAL, reason="real dataset not built")
@pytest.mark.parametrize("split", ["train", "validation", "test"])
def test_real_sample_records_valid_and_in_correct_split(split):
    n = 0
    with open(SPLIT_DIR / f"{split}.jsonl", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i % 400:
                continue
            r = json.loads(line)
            assert P.validate_position_record(r) == [], r["position_id"]
            assert r["split"] == split and r["speed"] in P.SPEEDS
            n += 1
    assert n > 100
