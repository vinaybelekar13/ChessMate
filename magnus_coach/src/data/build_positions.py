"""Build the Magnus decision-position dataset from the validated corpus.

Run:  python src/data/build_positions.py

Reads   data/cleaned/magnus_games.jsonl  +  data/splits/split_manifest.json
Writes  data/splits/{train,validation,test}.jsonl   (one JSON record per line)
        data/processed/rejected_positions.jsonl     (everything excluded, with reason)
        outputs/position_dataset_report.json

Each game goes to exactly one split file (the manifest's assignment, which is
also re-derived from the game hash and must agree). Every record is re-validated
before it is written; failures are recorded and excluded, never repaired.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.positions import GameReplayError, make_records, validate_position_record  # noqa: E402
from src.data.splits import SPLITS, assign_split, load_manifest  # noqa: E402

CORPUS = ROOT / "data" / "cleaned" / "magnus_games.jsonl"
MANIFEST = ROOT / "data" / "splits" / "split_manifest.json"
SPLIT_DIR = ROOT / "data" / "splits"
REJECTS = ROOT / "data" / "processed" / "rejected_positions.jsonl"
REPORT = ROOT / "outputs" / "position_dataset_report.json"


def build(corpus=CORPUS, manifest=MANIFEST, split_dir=SPLIT_DIR, rejects_path=REJECTS, report_path=REPORT,
          verbose=True):
    assignment = load_manifest(manifest)
    split_dir, rejects_path = Path(split_dir), Path(rejects_path)
    split_dir.mkdir(parents=True, exist_ok=True)
    rejects_path.parent.mkdir(parents=True, exist_ok=True)

    out = {s: open(split_dir / f"{s}.jsonl", "w", encoding="utf-8", newline="\n") for s in SPLITS}
    rej = open(rejects_path, "w", encoding="utf-8", newline="\n")

    games = magnus_games = 0
    positions = Counter()           # per split
    by_color, by_year, by_speed = Counter(), Counter(), Counter()
    by_tc, by_source, by_split_speed = Counter(), Counter(), Counter()
    games_per_split = Counter()
    rejected, reasons = 0, Counter()
    t0 = time.time()

    def reject(payload):
        nonlocal rejected
        rejected += 1
        reasons[payload["reason"]] += 1
        rej.write(json.dumps(payload, ensure_ascii=False) + "\n")

    with open(corpus, encoding="utf-8") as fh:
        for line in fh:
            game = json.loads(line)
            games += 1
            if game.get("magnus_color") not in ("white", "black"):
                reject({"game_id": game["game_id"], "reason": "game_without_magnus", "detail": ""})
                continue
            magnus_games += 1

            split = assignment.get(game["game_id"])
            if split is None or split != assign_split(game["game_hash"]):
                reject({"game_id": game["game_id"], "reason": "split_assignment_inconsistent",
                        "detail": f"manifest={split}"})
                continue

            # Materialise first: a replay failure must exclude the WHOLE game.
            try:
                recs = list(make_records(game, split))
            except GameReplayError as exc:
                reject({"game_id": game["game_id"], "reason": "game_replay_failed", "detail": str(exc)})
                continue

            games_per_split[split] += 1
            for rec in recs:
                errs = validate_position_record(rec)
                if errs:
                    for e in errs:
                        reasons[e] += 0  # keep key ordering stable; counted below
                    rejected += 1
                    reasons[errs[0]] += 1
                    rej.write(json.dumps({"position_id": rec["position_id"], "game_id": rec["game_id"],
                                          "reason": errs[0], "all_reasons": errs, "fen_before": rec["fen_before"],
                                          "target_move_uci": rec["target_move_uci"]}) + "\n")
                    continue
                out[split].write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
                positions[split] += 1
                by_color[rec["magnus_color"]] += 1
                by_year[str(rec["year"])] += 1
                by_speed[rec["speed"]] += 1
                by_tc[rec["time_control"] or "(none)"] += 1
                by_source[rec["source"]] += 1
                by_split_speed[f"{split}/{rec['speed']}"] += 1
            if verbose and games % 2000 == 0:
                print(f"  {games} games, {sum(positions.values())} positions, {time.time() - t0:.0f}s", flush=True)

    for f in out.values():
        f.close()
    rej.close()

    total = sum(positions.values())
    report = {
        "games_processed": games,
        "magnus_games": magnus_games,
        "games_per_split": dict(games_per_split),
        "positions_generated": total,
        "positions_per_split": dict(positions),
        "positions_rejected_or_games_excluded": rejected,
        "rejection_reasons": {k: v for k, v in reasons.items() if v},
        "positions_by_magnus_color": dict(by_color),
        "positions_by_year": dict(sorted(by_year.items())),
        "positions_by_speed": {s: by_speed.get(s, 0) for s in ("classical", "rapid", "blitz", "bullet", "ultrabullet", "unknown")},
        "positions_by_split_and_speed": dict(sorted(by_split_speed.items())),
        "positions_by_time_control_top15": dict(by_tc.most_common(15)),
        "positions_by_source": dict(by_source),
        "seconds": round(time.time() - t0, 1),
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if verbose:
        print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    build()
