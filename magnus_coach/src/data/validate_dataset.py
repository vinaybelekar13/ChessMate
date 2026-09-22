"""Independent validation + explicit leakage test of the position dataset.

Run:  python src/data/validate_dataset.py

Does not trust build_positions.py: every record is re-validated from its FEN,
per-game position counts are checked against the CORPUS, and split assignment
is re-derived from each game's hash. Exits non-zero on any failure.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.positions import validate_position_record  # noqa: E402
from src.data.splits import SPLITS, assign_split, load_manifest, magnus_decisions  # noqa: E402

CORPUS = ROOT / "data" / "cleaned" / "magnus_games.jsonl"
MANIFEST = ROOT / "data" / "splits" / "split_manifest.json"
SPLIT_DIR = ROOT / "data" / "splits"
OUT = ROOT / "outputs" / "dataset_validation.json"


def main():
    manifest = load_manifest(MANIFEST)
    corpus = {}
    with open(CORPUS, encoding="utf-8") as fh:
        for line in fh:
            g = json.loads(line)
            corpus[g["game_id"]] = (g["game_hash"], magnus_decisions(g["num_plies"], g["magnus_color"]))

    failures, per_split_ids, per_split_pos = [], {}, Counter()
    per_game_count = Counter()
    seen_pos_ids = set()
    board_keys = {}
    for split in SPLITS:
        ids, keys = set(), set()
        with open(SPLIT_DIR / f"{split}.jsonl", encoding="utf-8") as fh:
            for n, line in enumerate(fh):
                r = json.loads(line)
                errs = validate_position_record(r)
                if errs:
                    failures.append((r.get("position_id"), errs))
                if r["split"] != split:
                    failures.append((r["position_id"], [f"split_field_{r['split']}_in_{split}_file"]))
                if r["position_id"] in seen_pos_ids:
                    failures.append((r["position_id"], ["duplicate_position_id"]))
                seen_pos_ids.add(r["position_id"])
                gid = r["game_id"]
                ids.add(gid)
                per_game_count[gid] += 1
                per_split_pos[split] += 1
                if gid not in manifest or manifest[gid] != split:
                    failures.append((r["position_id"], [f"manifest_says_{manifest.get(gid)}"]))
                if gid not in corpus or assign_split(corpus[gid][0]) != split:
                    failures.append((r["position_id"], ["hash_rule_disagrees"]))
                keys.add(hash(" ".join(r["fen_before"].split()[:4])))
        per_split_ids[split] = ids
        board_keys[split] = keys
        print(f"  {split}: {per_split_pos[split]} positions, {len(ids)} games", flush=True)

    # ---- leakage: pairwise game overlap must be empty
    overlaps = {}
    for i, a in enumerate(SPLITS):
        for b in SPLITS[i + 1:]:
            overlaps[f"{a}&{b}"] = len(per_split_ids[a] & per_split_ids[b])
    leakage_ok = all(v == 0 for v in overlaps.values())

    # ---- completeness: every corpus game present once, with exactly its Magnus decisions
    # A game with zero Magnus decisions (e.g. a 1-ply game where Magnus was Black) has no
    # positions and is legitimately absent from the split files; it is still in the manifest.
    no_decision_games = [g for g, (_, n) in corpus.items() if n == 0]
    expected_games = {g for g, (_, n) in corpus.items() if n > 0}
    missing_games = [g for g in expected_games if g not in per_game_count]
    wrong_counts = [g for g, (_, n) in corpus.items() if per_game_count.get(g, 0) != n]
    union = set().union(*per_split_ids.values())

    # ---- informational: opening/transposition overlap (NOT game leakage)
    overlap_info = {}
    # per-position (not per-unique-board) fraction
    train_keys = board_keys["train"]
    for s in ("validation", "test"):
        tot = hit = 0
        with open(SPLIT_DIR / f"{s}.jsonl", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                tot += 1
                hit += hash(" ".join(r["fen_before"].split()[:4])) in train_keys
        overlap_info[f"{s}_positions_whose_board_also_in_train"] = round(hit / tot, 4)

    report = {
        "records_revalidated": sum(per_split_pos.values()),
        "record_failures": len(failures),
        "first_failures": [{"id": i, "errors": e} for i, e in failures[:20]],
        "games_per_split": {s: len(v) for s, v in per_split_ids.items()},
        "positions_per_split": dict(per_split_pos),
        "pairwise_game_overlap": overlaps,
        "LEAKAGE_TEST_PASSED": leakage_ok,
        "corpus_games_missing_from_dataset": len(missing_games),
        "games_with_wrong_position_count": len(wrong_counts),
        "corpus_games_with_zero_magnus_decisions": len(no_decision_games),
        "union_games_equals_corpus_games_with_decisions": union == expected_games,
        "informational_transposition_overlap": overlap_info,
        "overlap_note": ("Fraction of val/test positions whose exact board+turn+castling+ep also occurs "
                         "somewhere in train. This is normal (opening positions repeat across games) and is "
                         "NOT game leakage; it means part of the test set is 'seen' opening theory."),
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    ok = (not failures and leakage_ok and not missing_games and not wrong_counts and union == expected_games)
    print("\nDATASET VALIDATION", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
