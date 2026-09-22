import json

import chess

from src.data.build_corpus import make_candidate, deduplicate_games
from src.data.validate_corpus import validate

SCHOLARS = ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"]


def _good_game():
    g, _ = make_candidate("t", {"white": "Carlsen,M", "black": "x", "date": "2010.01.01"},
                          SCHOLARS, chess.STARTING_FEN, "t#1")
    return deduplicate_games([g])[0]


def _write(path, games):
    path.write_text("\n".join(json.dumps(g) for g in games) + "\n", encoding="utf-8")


def _run(tmp_path, games):
    p = tmp_path / "c.jsonl"
    _write(p, games)
    return validate(p, build_report=tmp_path / "none.json", stats_path=tmp_path / "s.json")


def test_validator_accepts_clean_corpus(tmp_path):
    stats, errors = _run(tmp_path, [_good_game()])
    assert not errors and stats["total_games"] == 1 and stats["unique_games"] == 1


def test_validator_flags_illegal_game(tmp_path):
    g = _good_game()
    g["moves"] = ["e2e4", "e2e4"]
    g["num_plies"] = 2
    _, errors = _run(tmp_path, [g])
    assert any("ILLEGAL" in e for _, e in errors)


def test_validator_flags_tampered_hash(tmp_path):
    g = _good_game()
    g["game_hash"] = "0" * 64
    _, errors = _run(tmp_path, [g])
    assert any("hash" in e for _, e in errors)


def test_validator_flags_duplicate_games(tmp_path):
    g = _good_game()
    _, errors = _run(tmp_path, [g, dict(g)])
    assert any("DUPLICATE" in e for _, e in errors)


def test_validator_flags_wrong_magnus_side(tmp_path):
    g = _good_game()
    g["magnus_color"] = "black"
    _, errors = _run(tmp_path, [g])
    assert any("identification" in e for _, e in errors)
