import csv

import chess
import pytest

from src.data.build_corpus import (
    deduplicate_games,
    extract_lichess_games,
    extract_pgn_games,
    make_candidate,
)
from src.data.common import (
    classify_speed,
    clean_san,
    game_hash,
    identify_magnus,
    is_magnus_name,
    is_missing,
    replay_uci,
)

# Scholar's mate: 1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6 4.Qxf7#  (7 plies, black never moves again)
SCHOLARS = ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"]


# ------------------------------------------------------------------ SAN cleaning
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.e4", "e4"),
        ("1.c5", "c5"),
        ("2.Nc3", "Nc3"),
        ("10...Qe7", "Qe7"),
        ("59.Qxd5", "Qxd5"),
        ("12.O-O-O", "O-O-O"),
        ("Nf3", "Nf3"),
        ("7.exd8=Q+", "exd8=Q+"),
    ],
)
def test_clean_san_strips_move_numbers(raw, expected):
    assert clean_san(raw) == expected


@pytest.mark.parametrize("raw", ["NA", "na", "nan", "NaN", "N/A", "", "  ", None, float("nan")])
def test_clean_san_treats_missing_spellings_as_none(raw):
    assert clean_san(raw) is None
    assert is_missing(raw)


def test_clean_san_does_not_swallow_real_moves():
    # 'Na3' must not be confused with the 'NA' missing token.
    assert clean_san("Na3") == "Na3"
    assert not is_missing("Na3")


# ------------------------------------------------------------------ Lichess CSV
def _write_csv(path, rows, cols=("Event", "Site", "Date", "White", "Black", "Result",
                                 "Variant", "TimeControl", "ECO", "Opening", "Termination")):
    move_cols = [f"{c}{i}" for i in range(1, 6) for c in "wb"]
    fields = list(cols) + move_cols
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            base = {c: "" for c in fields}
            base.update({"Variant": "Standard", "TimeControl": "60+0", "Result": "1-0"})
            base.update(r)
            w.writerow(base)


def test_lichess_terminal_NA_game_is_accepted(tmp_path):
    """REGRESSION: the old parser rejected every game ending in a 'NA' cell."""
    p = tmp_path / "l.csv"
    _write_csv(p, [{
        "White": "DrNykterstein", "Black": "opp", "Site": "https://lichess.org/x1",
        "w1": "1.e4", "b1": "1.e5", "w2": "2.Bc4", "b2": "2.Nc6",
        "w3": "3.Qh5", "b3": "3.Nf6", "w4": "4.Qxf7#", "b4": "NA",
    }])
    games, rejects, attempted = extract_lichess_games(p)
    assert attempted == 1 and not rejects
    assert games[0]["moves"] == SCHOLARS
    assert games[0]["magnus_color"] == "white"
    assert games[0]["opponent"] == "opp"


def test_lichess_empty_string_terminal_cell_also_accepted(tmp_path):
    p = tmp_path / "l.csv"
    _write_csv(p, [{"White": "opp", "Black": "DrNykterstein", "w1": "1.e4", "b1": ""}])
    games, rejects, _ = extract_lichess_games(p)
    assert len(games) == 1 and games[0]["moves"] == ["e2e4"]
    assert games[0]["magnus_color"] == "black"


def test_lichess_atomic_variant_is_rejected_not_parsed(tmp_path):
    p = tmp_path / "l.csv"
    _write_csv(p, [{"White": "DrNykterstein", "Black": "o", "Variant": "Atomic", "w1": "1.e4"}])
    games, rejects, _ = extract_lichess_games(p)
    assert not games
    assert rejects[0]["reason"] == "variant_not_standard"


def test_lichess_illegal_san_rejected_never_repaired(tmp_path):
    p = tmp_path / "l.csv"
    _write_csv(p, [{"White": "DrNykterstein", "Black": "o", "w1": "1.e4", "b1": "1.e4"}])
    games, rejects, _ = extract_lichess_games(p)
    assert not games
    assert rejects[0]["reason"] == "san_parse_error"


def test_lichess_gap_in_moves_rejected(tmp_path):
    p = tmp_path / "l.csv"
    _write_csv(p, [{"White": "DrNykterstein", "Black": "o",
                    "w1": "1.e4", "b1": "NA", "w2": "2.Nf3"}])
    games, rejects, _ = extract_lichess_games(p)
    # The stream reader detects the hole via the move-number check.
    assert not games and rejects[0]["reason"] == "move_number_mismatch"


def test_lichess_zero_move_game_rejected(tmp_path):
    p = tmp_path / "l.csv"
    _write_csv(p, [{"White": "DrNykterstein", "Black": "o", "w1": "NA"}])
    games, rejects, _ = extract_lichess_games(p)
    assert not games and rejects[0]["reason"] == "empty_game"


def test_lichess_column_cap_is_flagged(tmp_path):
    # 5 full moves fill every column of the test CSV -> possibly truncated.
    p = tmp_path / "l.csv"
    seq = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7"]
    row = {"White": "DrNykterstein", "Black": "o"}
    for i in range(5):
        row[f"w{i+1}"], row[f"b{i+1}"] = f"{i+1}.{seq[2 * i]}", f"{i+1}.{seq[2 * i + 1]}"
    _write_csv(p, [row])
    games, _, _ = extract_lichess_games(p)
    assert "column_cap_reached" in games[0]["flags"]


# ------------------------------------------------------------------ PGN
PGN_OK = """[Event "Test"]
[Site "X"]
[Date "2010.01.01"]
[Round "1"]
[White "Carlsen,M"]
[Black "Someone"]
[Result "1-0"]
[ECO "C20"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0

"""

PGN_ILLEGAL = """[Event "Bad"]
[Site "X"]
[Date "2010.01.02"]
[Round "1"]
[White "Carlsen,M"]
[Black "Someone"]
[Result "1-0"]

1. e4 e5 2. Ke4 1-0

"""

PGN_NOT_MAGNUS = """[Event "Other"]
[Site "X"]
[Date "2010.01.03"]
[Round "1"]
[White "Smith,J"]
[Black "Jones,K"]
[Result "1-0"]

1. e4 e5 1-0

"""

PGN_FATHER = """[Event "Family"]
[Site "X"]
[Date "2010.01.04"]
[Round "1"]
[White "Carlsen,H"]
[Black "Carlsen,M"]
[Result "0-1"]

1. e4 e5 0-1

"""


def test_pgn_parsing_valid_game(tmp_path):
    p = tmp_path / "a.pgn"
    p.write_text(PGN_OK, encoding="utf-8")
    games, rejects, attempted = extract_pgn_games(p)
    assert attempted == 1 and not rejects
    g = games[0]
    assert g["moves"] == SCHOLARS
    assert g["magnus_color"] == "white" and g["eco"] == "C20"


def test_pgn_illegal_move_is_rejected_not_truncated(tmp_path):
    """python-chess silently truncates on illegal SAN; we must reject instead."""
    p = tmp_path / "a.pgn"
    p.write_text(PGN_ILLEGAL, encoding="utf-8")
    games, rejects, _ = extract_pgn_games(p)
    assert not games
    assert rejects[0]["reason"] == "pgn_parse_errors"


def test_pgn_game_without_magnus_rejected(tmp_path):
    p = tmp_path / "a.pgn"
    p.write_text(PGN_NOT_MAGNUS, encoding="utf-8")
    games, rejects, _ = extract_pgn_games(p)
    assert not games and rejects[0]["reason"] == "magnus_not_identified"


def test_pgn_magnus_vs_his_father_resolves_correct_side(tmp_path):
    p = tmp_path / "a.pgn"
    p.write_text(PGN_FATHER, encoding="utf-8")
    games, _, _ = extract_pgn_games(p)
    assert games[0]["magnus_color"] == "black"
    assert games[0]["opponent"] == "Carlsen,H"


# ------------------------------------------------------------------ identification
@pytest.mark.parametrize(
    "name", ["Carlsen,M", "Carlsen,Magnus", "Carlsen, Magnus", "Magnus Carlsen",
             "DrNykterstein", "Dr Nykterstein", "Nykterstein", "  carlsen,  magnus "]
)
def test_magnus_aliases_match(name):
    assert is_magnus_name(name)


@pytest.mark.parametrize("name", ["Carlsen,H", "Carlsen,Ingrid", "Carlsen", "Magnus", "Nakamura,H", "", None])
def test_non_magnus_names_do_not_match(name):
    assert not is_magnus_name(name)


def test_identify_magnus_ambiguous_returns_none():
    assert identify_magnus("Carlsen,M", "DrNykterstein") == (None, None)
    assert identify_magnus("a", "b") == (None, None)
    assert identify_magnus("Carlsen,M", "x") == ("white", "x")
    assert identify_magnus("x", "DrNykterstein") == ("black", "x")


# ------------------------------------------------------------------ hashing / dedup
def _cand(source, moves=SCHOLARS, fen=chess.STARTING_FEN, **meta):
    m = {"white": "Carlsen,M", "black": "opp", "date": "2010.01.01", **meta}
    g, r = make_candidate(source, m, moves, fen, f"{source}#1")
    assert g, r
    return g


def test_game_hash_depends_on_full_sequence_and_start_fen():
    h = game_hash(chess.STARTING_FEN, SCHOLARS)
    assert h == game_hash(chess.STARTING_FEN, list(SCHOLARS))
    assert h != game_hash(chess.STARTING_FEN, SCHOLARS[:-1])
    assert h != game_hash("8/8/8/8/8/8/8/K1k5 w - - 0 1", SCHOLARS)


def test_dedup_merges_same_game_across_sources_and_keeps_provenance():
    a = _cand("pgnmentor", event="Some Open")
    b = _cand("lichess", event="", time_control="180+0")
    unique = deduplicate_games([a, b])
    assert len(unique) == 1
    g = unique[0]
    assert g["sources"] == ["lichess", "pgnmentor"]
    assert len(g["source_records"]) == 2
    assert g["event"] == "Some Open"
    assert g["game_id"].startswith("mc_")


def test_dedup_does_not_merge_prefix_or_different_games():
    a = _cand("pgnmentor", moves=SCHOLARS)
    b = _cand("lichess", moves=["e2e4", "e7e5"])
    assert len(deduplicate_games([a, b])) == 2


def test_dedup_ignores_metadata_when_moves_identical():
    a = _cand("pgnmentor", date="2010.01.01")
    b = _cand("lichess", date="1999.12.31")
    assert len(deduplicate_games([a, b])) == 1


# ------------------------------------------------------------------ replay / speed
def test_replay_detects_illegal_sequence():
    ok, err, ply = replay_uci(["e2e4", "e2e4"])
    assert not ok and ply == 2 and "illegal" in err


def test_replay_detects_malformed_uci():
    ok, err, _ = replay_uci(["e2e4", "zz"])
    assert not ok


def test_replay_accepts_valid():
    assert replay_uci(SCHOLARS)[0]


def test_speed_classification_honest_about_unknowns():
    assert classify_speed("60+0", "", "lichess") == ("bullet", "time_control_header")
    assert classify_speed("180+2", "", "lichess")[0] == "blitz"
    assert classify_speed("", "World Blitz Championship", "pgnmentor") == ("blitz", "event_name")
    assert classify_speed("", "Wijk aan Zee", "pgnmentor") == ("unspecified", "none")


# ------------------------------------------------------------------ shifted CSV layout
def test_lichess_no_eval_layout_is_recovered_and_flagged(tmp_path):
    """REGRESSION: rows without evals pack 'move, clk, move, clk' into the
    3-cell-per-ply columns, so b1 held '0:01:00'. Real rows: 35 of 8,686."""
    p = tmp_path / "l.csv"
    fields = ["Event", "Site", "Date", "White", "Black", "Result", "Variant", "TimeControl",
              "ECO", "Opening", "Termination", "w1", "w1eval", "w1clk", "b1", "b1eval", "b1clk",
              "w2", "w2eval", "w2clk", "b2", "b2eval", "b2clk"]
    cells = ["1.e4", "0:01:00", "1.e5", "0:01:00", "2.Nf3", "0:00:59", "2.Nc6", "0:00:59"]
    row = {f: "" for f in fields}
    row.update({"Variant": "Standard", "White": "DrNykterstein", "Black": "o", "Site": "s1"})
    for col, val in zip(fields[fields.index("w1"):], cells):
        row[col] = val
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerow(row)
    games, rejects, _ = extract_lichess_games(p)
    assert not rejects
    assert games[0]["moves"] == ["e2e4", "e7e5", "g1f3", "b8c6"]
    assert "layout_shifted" in games[0]["flags"]


def test_lichess_eval_and_clock_cells_are_never_mistaken_for_moves(tmp_path):
    p = tmp_path / "l.csv"
    fields = ["Site", "White", "Black", "Variant", "w1", "w1eval", "w1clk", "b1", "b1eval", "b1clk"]
    row = {"Site": "s", "White": "DrNykterstein", "Black": "o", "Variant": "Standard",
           "w1": "1.e4", "w1eval": "0.32", "w1clk": "0:01:00",
           "b1": "1.e5", "b1eval": "#3", "b1clk": "0:00:59"}
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerow(row)
    games, rejects, _ = extract_lichess_games(p)
    assert games[0]["moves"] == ["e2e4", "e7e5"] and not rejects
    assert "layout_shifted" not in games[0]["flags"]
