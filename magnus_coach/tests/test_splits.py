import json
from pathlib import Path

import pytest

from src.data import splits as sp

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "splits" / "split_manifest.json"
CORPUS = ROOT / "data" / "cleaned" / "magnus_games.jsonl"


def fake_hashes(n):
    import hashlib
    return [hashlib.sha256(str(i).encode()).hexdigest() for i in range(n)]


def test_assignment_is_deterministic_and_order_independent():
    hs = fake_hashes(500)
    a = {h: sp.assign_split(h) for h in hs}
    b = {h: sp.assign_split(h) for h in reversed(hs)}
    assert a == b


def test_ratios_are_close_to_80_10_10():
    counts = {s: 0 for s in sp.SPLITS}
    for h in fake_hashes(20000):
        counts[sp.assign_split(h)] += 1
    assert 0.78 < counts["train"] / 20000 < 0.82
    assert 0.08 < counts["validation"] / 20000 < 0.12
    assert 0.08 < counts["test"] / 20000 < 0.12


def test_adding_games_never_moves_existing_games():
    hs = fake_hashes(2000)
    before = {h: sp.assign_split(h) for h in hs[:1000]}
    after = {h: sp.assign_split(h) for h in hs}          # corpus "grew"
    assert all(after[h] == s for h, s in before.items())


def test_magnus_decision_counts():
    assert sp.magnus_decisions(7, "white") == 4 and sp.magnus_decisions(7, "black") == 3
    assert sp.magnus_decisions(8, "white") == 4 and sp.magnus_decisions(8, "black") == 4
    assert sp.magnus_decisions(1, "black") == 0 and sp.magnus_decisions(0, "white") == 0


def test_manifest_roundtrip_and_validation(tmp_path):
    corpus = tmp_path / "c.jsonl"
    rows = [{"game_id": f"mc_{i}", "game_hash": h, "num_plies": 10 + i, "magnus_color": "white"}
            for i, h in enumerate(fake_hashes(50))]
    corpus.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    m = sp.build_manifest(corpus)
    assert m["total_games"] == 50 and sum(m["games_per_split"].values()) == 50
    p = tmp_path / "m.json"
    p.write_text(json.dumps(m))
    mapping = sp.load_manifest(p)
    assert len(mapping) == 50 and set(mapping.values()) <= set(sp.SPLITS)
    m["games"].append(dict(m["games"][0]))
    p.write_text(json.dumps(m))
    with pytest.raises(ValueError):
        sp.load_manifest(p)
    m["games"] = [{"game_id": "x", "split": "dev"}]
    p.write_text(json.dumps(m))
    with pytest.raises(ValueError):
        sp.load_manifest(p)


@pytest.mark.skipif(not (MANIFEST.exists() and CORPUS.exists()), reason="real corpus/manifest not present")
def test_real_manifest_matches_corpus_and_hash_rule():
    mapping = sp.load_manifest(MANIFEST)
    n = 0
    with open(CORPUS, encoding="utf-8") as fh:
        for line in fh:
            g = json.loads(line)
            assert mapping[g["game_id"]] == sp.assign_split(g["game_hash"])
            n += 1
    assert n == len(mapping) == 16269
