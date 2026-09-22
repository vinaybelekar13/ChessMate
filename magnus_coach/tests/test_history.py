import json
import random
from pathlib import Path

import chess
import pytest

from src.history import similarity as S
from src.history.database import DEFAULT_DB, MagnusDB, build, mirror_uci
from tests.helpers import fake_game, write_fake_split

REAL = DEFAULT_DB.exists()


def rand_board(seed, plies=30):
    rng, b = random.Random(seed), chess.Board()
    for _ in range(plies):
        ms = list(b.legal_moves)
        if not ms:
            break
        b.push(rng.choice(ms))
    return b


# ------------------------------------------------------------------ similarity properties
@pytest.mark.parametrize("seed", range(8))
def test_identity_symmetry_range(seed):
    a, b = rand_board(seed), rand_board(seed + 100)
    fa, fb = S.features(a), S.features(b)
    s_aa, _ = S.similarity(fa, fa)
    s_ab, _ = S.similarity(fa, fb)
    s_ba, _ = S.similarity(fb, fa)
    assert s_aa == pytest.approx(1.0)
    assert abs(s_ab - s_ba) < 1e-12 and 0.0 <= s_ab <= 1.0


@pytest.mark.parametrize("seed", range(8))
def test_colour_mirror_is_identical_in_side_to_move_frame(seed):
    b = rand_board(seed)
    assert S.features(b) == S.features(b.mirror())
    assert S.keys(S.features(b)) == S.keys(S.features(b.mirror()))


def test_closer_positions_score_higher():
    b = chess.Board()
    one = chess.Board(); one.push_uci("e2e4"); one.push_uci("e7e5")          # 2 plies later
    far = rand_board(5, 60)
    s_near = S.similarity(S.features(b), S.features(one))[0]
    s_far = S.similarity(S.features(b), S.features(far))[0]
    assert 0.5 < s_near < 1.0 and s_far < s_near


def test_weights_sum_to_one_and_components_named():
    assert abs(sum(S.WEIGHTS.values()) - 1) < 1e-12
    _, comps = S.similarity(S.features(chess.Board()), S.features(rand_board(3)))
    assert set(comps) == set(S.WEIGHTS) and all(0 <= v <= 1 for v in comps.values())


def test_pack_roundtrip_and_keys_deterministic():
    f = S.features(rand_board(9))
    assert S.unpack(S.pack(f)) == f and S.keys(f) == S.keys(S.unpack(S.pack(f)))


def test_mirror_uci():
    assert mirror_uci("e2e4") == "e7e5" and mirror_uci("e7e8q") == "e2e1q"


# ------------------------------------------------------------------ synthetic database (provenance)
@pytest.fixture(scope="module")
def mini(tmp_path_factory):
    d = tmp_path_factory.mktemp("mini")
    recs, games = write_fake_split(d / "train.jsonl", range(0, 8), "train", plies=50)
    for s in ("validation", "test"):
        write_fake_split(d / f"{s}.jsonl", [], s)
    (d / "corpus.jsonl").write_text("\n".join(json.dumps(g) for g in games))
    (d / "manifest.json").write_text(json.dumps({"games": [{"game_id": g["game_id"], "split": "train"} for g in games]}))
    stats = build(d / "corpus.jsonl", d, d / "manifest.json", d / "h.sqlite", verbose=False)
    return d, recs, games, stats


def test_build_counts_and_indexes(mini):
    _, recs, games, stats = mini
    assert stats["games"] == len(games) and stats["positions"] == len(recs)
    assert {"ix_pos_exact", "ix_pos_pawns", "ix_pos_material", "ix_pos_game", "ix_pos_fen"} <= set(stats["indexes"])


def test_every_result_is_a_real_stored_record_with_matching_fields(mini):
    d, recs, games, _ = mini
    by_id = {r["position_id"]: r for r in recs}
    db = MagnusDB(d / "h.sqlite")
    for seed in (1, 2, 3):
        for res in db.find_similar_positions(rand_board(seed, 40).fen(), top_k=10):
            src = by_id[res["position_id"]]                                   # must exist in the source data
            assert res["fen"] == src["fen_before"] and res["magnus_move"]["uci"] == src["target_move_uci"]
            assert res["magnus_move"]["san"] == src["target_move_san"] and res["ply"] == src["ply"]
            assert res["game"]["opponent"] == src["opponent"] and res["game"]["event"] == src["event"]
            assert res["previous_moves"] == src["last_5_moves_uci"] and res["next_moves"] == src["next_moves_uci"]
            assert res["provenance"]["kind"] == "historical_fact" and res["provenance"]["row_id"] > 0
            row = db.con.execute("SELECT position_id FROM positions WHERE id=?", (res["provenance"]["row_id"],)).fetchone()
            assert row["position_id"] == res["position_id"]


def test_stored_position_is_retrieved_exactly_and_results_are_deterministic(mini):
    d, recs, _, _ = mini
    db = MagnusDB(d / "h.sqlite")
    r = recs[20]
    a = db.find_similar_positions(r["fen_before"], 200)
    assert any(x["position_id"] == r["position_id"] and x["exact_board_match"] and x["similarity"] == 1.0 for x in a)
    assert a == db.find_similar_positions(r["fen_before"], 200)


def test_mirrored_query_matches_and_translates_move(mini):
    d, recs, _, _ = mini
    db = MagnusDB(d / "h.sqlite")
    r = recs[30]
    q = chess.Board(r["fen_before"]).mirror()
    hit = next(x for x in db.find_similar_positions(q.fen(), 200) if x["position_id"] == r["position_id"])
    assert hit["mirrored"] and hit["exact_board_match"]
    assert hit["magnus_move_in_query_frame"] == mirror_uci(r["target_move_uci"])
    assert hit["legal_in_query_position"] is True


def test_filters_and_exclusions(mini):
    d, recs, games, _ = mini
    db = MagnusDB(d / "h.sqlite")
    q = recs[10]["fen_before"]
    assert db.find_similar_positions(q, 5, splits=["test"]) == []
    ex = games[0]["game_id"]
    assert all(x["game_id"] != ex for x in db.find_similar_positions(q, 50, exclude_game_ids=[ex]))


def test_surrounding_moves_are_the_actual_game_moves(mini):
    d, recs, games, _ = mini
    db = MagnusDB(d / "h.sqlite")
    g, ply = games[2], 21
    sm = db.surrounding_moves(g["game_id"], ply, 3, 3)
    assert [m["ply"] for m in sm] == list(range(18, 25))
    assert [m["uci"] for m in sm] == g["moves"][17:24] and sum(m["is_target"] for m in sm) == 1
    b = chess.Board()
    for u in g["moves"][:17]:
        b.push_uci(u)
    assert sm[0]["san"] == b.san(chess.Move.from_uci(g["moves"][17]))


def test_unknown_ids_return_none_or_raise(mini):
    db = MagnusDB(mini[0] / "h.sqlite")
    assert db.get_position("nope:1") is None and db.get_game("nope") is None
    with pytest.raises(KeyError):
        db.surrounding_moves("nope", 3)


def test_missing_database_fails_loudly(tmp_path):
    with pytest.raises(FileNotFoundError):
        MagnusDB(tmp_path / "absent.sqlite")


# ------------------------------------------------------------------ REAL database
@pytest.mark.skipif(not REAL, reason="database not built")
def test_real_db_counts_and_self_retrieval_and_provenance():
    db = MagnusDB()
    assert db.count() == 721024
    assert db.con.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 16269
    r = db.con.execute("SELECT * FROM positions WHERE id=123456").fetchone()
    res = db.find_similar_positions(r["fen"], 10)
    assert res[0]["exact_board_match"] and res[0]["similarity"] == 1.0
    for x in res:
        row = db.con.execute("SELECT * FROM positions WHERE position_id=?", (x["position_id"],)).fetchone()
        assert row is not None and row["fen"] == x["fen"] and row["target_uci"] == x["magnus_move"]["uci"]
        chess.Board(x["fen"])
        assert db.get_game(x["game_id"]) is not None


@pytest.mark.skipif(not REAL, reason="database not built")
def test_real_db_position_counts_per_split_match_dataset():
    db = MagnusDB()
    got = {r[0]: r[1] for r in db.con.execute("SELECT split, COUNT(*) FROM positions GROUP BY split")}
    assert got == {"train": 577526, "validation": 73485, "test": 70013}
