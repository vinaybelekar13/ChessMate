import json

import chess
import pytest

from src.coach import player as PL
from src.coach.evidence import generate_coach_evidence
from src.coach.services import Services
from src.engine.stockfish import engine_available
from src.history.database import DEFAULT_DB

pytestmark = pytest.mark.skipif(not (engine_available() and DEFAULT_DB.exists()), reason="needs Stockfish + database")
NXE5 = ("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", "Nxe5")
QXE5 = ("r1bqkbnr/pppp1ppp/2n5/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 2 3", "Qxe5+")
QH4 = ("rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2", "Qh4")
MATE = ("6k1/5ppp/8/8/8/8/5PPP/R3K3 w - - 0 1", "Kd2")
GOOD = ("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4", "d3")


@pytest.fixture(scope="module")
def sv():
    s = Services(engine_depth=8)
    yield s
    s.close()


@pytest.fixture(scope="module")
def evs(sv):
    return {k: generate_coach_evidence(*v, sv) for k, v in dict(nxe5=NXE5, qxe5=QXE5, qh4=QH4, mate=MATE, good=GOOD).items()}


def loaded(evs, keys=("nxe5", "qxe5", "mate", "good")):
    store = PL.MemoryPlayerStore()
    pm = PL.PlayerModel(store, "p1")
    for i, k in enumerate(keys, start=1):
        pm.ingest(evs[k], "g1", i, clock_seconds=None)
    return store, pm


# ---------------------------------------------------------------- evidence concept fix (regression)
def test_missed_mate_is_tactical_with_its_own_concept(evs):
    e = evs["mate"]
    assert e["mistake_category"] == "tactical" and "missed_back_rank_mate" in e["motifs"]   # REGRESSION: was 'opening'


# ---------------------------------------------------------------- player model
def test_ingest_is_idempotent_and_counts(evs):
    store, pm = loaded(evs)
    n = len(pm.records())
    pm.ingest(evs["nxe5"], "g1", 1)
    assert len(pm.records()) == n == 4
    s = pm.summary()
    assert s["analysed_moves"] == 4 and s["mistakes"] >= 3 and sum(s["by_label"].values()) == 4


def test_every_weakness_links_to_real_analysed_positions(evs):
    _, pm = loaded(evs)
    s = pm.summary()
    ids = {r["record_id"]: r for r in pm.records()}
    assert s["recurring_concepts"], "two hanging-piece blunders should recur"
    for w in s["recurring_concepts"]:
        assert w["count"] == len(w["evidence"]) >= 2
        for ref in w["evidence"]:
            r = ids[ref["record_id"]]
            assert r["fen"] == ref["fen"] and r["game_id"] == ref["game_id"] and r["ply"] == ref["ply"]
            chess.Board(ref["fen"])
    top = s["recurring_concepts"][0]
    assert top["concept"] == "hanging_piece" and top["count"] == 2


def test_no_invented_scores(evs):
    _, pm = loaded(evs)
    txt = json.dumps(pm.summary()).lower()
    assert "mastery" not in txt.replace("no ratings or mastery scores are computed", "") and "rating" not in txt.replace("no ratings or mastery scores are computed", "")
    for c in pm.summary()["mistake_categories"].values():
        assert c["count"] == len(c["evidence"])


def test_time_management_only_when_clock_data_exists(evs):
    store = PL.MemoryPlayerStore()
    pm = PL.PlayerModel(store, "a")
    pm.ingest(evs["nxe5"], "g", 1)
    assert pm.summary()["time_management"]["status"].startswith("not evidenced")
    pm.ingest(evs["qxe5"], "g", 2, clock_seconds=12.0)
    tm = pm.summary()["time_management"]
    assert tm["mistakes_under_time_pressure"] == 1 and tm["of_mistakes_with_clock_data"] == 1


def test_strengths_count_good_moves_and_found_tactics(evs):
    _, pm = loaded(evs, ("good", "mate"))
    assert pm.summary()["strengths"]["best_or_excellent_moves"] >= 0
    assert pm.summary()["missed_opportunities"]                      # Kd2 missed the mate


def test_json_store_persists_across_instances_and_validates(tmp_path, evs):
    a = PL.JsonPlayerStore(tmp_path)
    PL.PlayerModel(a, "alice").ingest(evs["nxe5"], "g", 1)
    b = PL.JsonPlayerStore(tmp_path)
    assert len(PL.PlayerModel(b, "alice").records()) == 1
    assert PL.PlayerModel(b, "bob").records() == []
    with pytest.raises(ValueError):
        b.load("../evil")
    data = json.loads((tmp_path / "alice.json").read_text())
    data["schema_version"] = 99
    (tmp_path / "alice.json").write_text(json.dumps(data))
    with pytest.raises(ValueError):
        b.load("alice")


# ---------------------------------------------------------------- training
def test_training_items_have_full_provenance_and_only_come_from_mistakes(evs):
    store, pm = loaded(evs)
    ts = PL.TrainingSystem(store, "p1")
    items = ts.generate(max_items=10)
    recs = {r["record_id"]: r for r in pm.records()}
    assert items and all(recs[i["source_record_id"]]["label"] in PL.MISTAKE_LABELS for i in items)
    for i in items:
        for k in ("source_game", "source_ply", "original_fen", "user_move", "better_move", "reason", "motif", "category", "concept_key"):
            assert k in i
        r = recs[i["source_record_id"]]
        assert i["original_fen"] == r["fen"] and i["better_move"] == r["best_move"] and i["source_ply"] == r["ply"]
    assert ts.generate(max_items=10) == []                            # no duplicates on a second call
    assert all(i["category"] in PL.CATEGORY_TO_TRAINING.values() for i in items)


def test_solve_retry_hint_reveal_flow(evs, sv):
    store, pm = loaded(evs, ("nxe5",))
    ts = PL.TrainingSystem(store, "p1")
    it = ts.generate()[0]
    p = ts.present(it["item_id"])
    assert "better_move" not in json.dumps(p) and p["fen"] == it["original_fen"]
    bad = ts.attempt(it["item_id"], "Nxe5", sv)
    assert bad["legal"] and not bad["solved"] and bad["retry_allowed"]
    assert ts.attempt(it["item_id"], "Qh8", sv)["legal"] is False
    h1 = ts.hint(it["item_id"])
    assert h1["level"] == "hint_1" and h1["hint"]
    good = ts.attempt(it["item_id"], it["better_move"]["san"], sv)
    assert good["solved"] and not good["unassisted"]                  # a hint was used
    assert ts.stats()["solved"] == 1 and ts.stats()["solved_unassisted"] == 0 and ts.stats()["total_attempts"] == 2      # illegal attempts are not counted


def test_unassisted_solve_and_reveal_bookkeeping(evs):
    store, _ = loaded(evs, ("nxe5", "qxe5"))
    ts = PL.TrainingSystem(store, "p1")
    a, b = ts.generate(max_items=2)
    assert ts.attempt(a["item_id"], a["better_move"]["uci"])["unassisted"]
    ts.reveal(b["item_id"])
    r = ts.attempt(b["item_id"], b["better_move"]["uci"])
    assert r["solved"] and not r["unassisted"]
    s = ts.stats()
    assert s["solved_unassisted"] == 1 and s["revealed"] == 1


def test_hints_exhaust_after_three(evs):
    store, _ = loaded(evs, ("nxe5",))
    ts = PL.TrainingSystem(store, "p1")
    it = ts.generate()[0]
    got = [ts.hint(it["item_id"]) for _ in range(4)]
    assert [g.get("level") for g in got[:3]] == ["hint_1", "hint_2", "stronger_hint"] and got[3]["exhausted"]


# ---------------------------------------------------------------- retest loop
def test_retest_loop_links_recurring_concept_and_measures_recurrence(sv, tmp_path):
    store = PL.JsonPlayerStore(tmp_path)
    loop = PL.RetestLoop(store, "sam", sv)
    r1 = loop.process_move(*NXE5, "g1", 5)
    assert r1["record"]["label"] in PL.MISTAKE_LABELS and len(r1["new_training_items"]) == 1 and not r1["is_repeat_of_known_concept"]
    concept = r1["record"]["concept_key"]
    item1 = r1["new_training_items"][0]
    assert loop.next_retest()["item_id"] == item1["item_id"]              # unsolved item is due
    assert loop.training.attempt(item1["item_id"], item1["better_move"]["uci"])["solved"]
    assert loop.next_retest() is None                                     # solved and not recurred: nothing due
    r2 = loop.process_move(*QH4, "g2", 4)                                  # same concept again, other colour
    assert r2["record"]["concept_key"] == concept and r2["is_repeat_of_known_concept"]
    assert r2["concept"]["occurrences"] == 2 and len(r2["new_training_items"]) == 1
    assert r2["concept"]["occurrences_after_first_training_success"] == 1   # measured: it recurred AFTER training
    assert loop.next_retest(concept)["item_id"] == r2["new_training_items"][0]["item_id"]   # the new unsolved item is due
    again = loop.process_move(*QH4, "g2", 4)                                # replaying the same analysed move changes nothing
    assert again["new_training_items"] == [] and loop.concept_stats(concept)["occurrences"] == 2


def test_good_move_creates_no_training_item(sv):
    loop = PL.RetestLoop(PL.MemoryPlayerStore(), "x", sv)
    r = loop.process_move(*GOOD, "g", 7)
    assert r["record"]["label"] in ("best", "brilliant", "excellent", "good", "playable")
    assert r["new_training_items"] == [] and r["concept"] is None
