"""Independently validate the cleaned corpus and write dataset statistics.

Run:  .\\.venv\\Scripts\\python.exe src\\data\\validate_corpus.py

This does NOT trust build_corpus.py. Every game is re-replayed with
python-chess, its canonical hash and id are recomputed, and Magnus
identification is re-derived from the stored player names. Any failure makes
the script exit non-zero; illegal games must never reach training.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.common import game_hash, game_id_from_hash, identify_magnus, replay_uci  # noqa: E402

CORPUS_PATH = ROOT / "data" / "cleaned" / "magnus_games.jsonl"
BUILD_REPORT = ROOT / "outputs" / "corpus_build_report.json"
STATS_PATH = ROOT / "outputs" / "dataset_stats.json"

REQUIRED_FIELDS = ("game_id", "game_hash", "source", "sources", "start_fen", "moves",
                   "magnus_color", "opponent", "white", "black", "result", "date")


def top(counter, n=25):
    return dict(counter.most_common(n))


def validate(corpus_path=CORPUS_PATH, build_report=BUILD_REPORT, stats_path=STATS_PATH):
    errors = []
    seen_hash, seen_id = set(), set()
    n = 0
    plies = []
    by_source, by_year, by_result = Counter(), Counter(), Counter()
    by_color, by_speed, by_speed_basis = Counter(), Counter(), Counter()
    by_event, by_eco, by_opening, by_flag = Counter(), Counter(), Counter(), Counter()
    by_time_control, by_source_combo = Counter(), Counter()

    with open(corpus_path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            g = json.loads(line)
            n += 1
            gid = g.get("game_id", f"line{line_no}")

            missing = [f for f in REQUIRED_FIELDS if f not in g]
            if missing:
                errors.append((gid, f"missing fields {missing}"))
                continue

            ok, err, _ = replay_uci(g["moves"], g["start_fen"])
            if not ok:
                errors.append((gid, f"ILLEGAL: {err}"))
                continue

            digest = game_hash(g["start_fen"], g["moves"])
            if digest != g["game_hash"]:
                errors.append((gid, "stored game_hash does not match recomputed hash"))
            if game_id_from_hash(digest) != g["game_id"]:
                errors.append((gid, "game_id does not match hash"))
            if digest in seen_hash:
                errors.append((gid, "DUPLICATE canonical hash in corpus"))
            if g["game_id"] in seen_id:
                errors.append((gid, "duplicate game_id"))
            seen_hash.add(digest)
            seen_id.add(g["game_id"])

            color, opp = identify_magnus(g["white"], g["black"])
            if color != g["magnus_color"] or opp != g["opponent"]:
                errors.append((gid, f"magnus identification mismatch: stored "
                                    f"{g['magnus_color']}/{g['opponent']} vs derived {color}/{opp}"))
            if g["num_plies"] != len(g["moves"]):
                errors.append((gid, "num_plies != len(moves)"))

            plies.append(len(g["moves"]))
            by_source.update(g["sources"])
            by_source_combo["+".join(g["sources"])] += 1
            by_year[(g.get("date") or "????")[:4]] += 1
            by_result[g.get("result") or "?"] += 1
            by_color[g["magnus_color"]] += 1
            by_speed[g.get("speed", "?")] += 1
            by_speed_basis[g.get("speed_basis", "?")] += 1
            by_time_control[g.get("time_control") or "(none)"] += 1
            by_event[g.get("event") or "(none)"] += 1
            eco = g.get("eco") or "(none)"
            by_eco[eco[:1] if eco != "(none)" else eco] += 1
            by_opening[g.get("opening") or (f"ECO {eco}" if eco != "(none)" else "(none)")] += 1
            by_flag.update(g.get("flags", []))

    build = {}
    if Path(build_report).exists():
        build = json.loads(Path(build_report).read_text(encoding="utf-8"))

    stats = {
        "total_games": n,
        "unique_games": len(seen_hash),
        "illegal_or_invalid_games": len({e[0] for e in errors}),
        "validation_errors": [{"game": g, "error": e} for g, e in errors[:100]],
        "games_by_source_membership": dict(by_source),
        "games_by_source_combination": dict(by_source_combo),
        "total_plies": sum(plies),
        "avg_game_length_plies": round(statistics.mean(plies), 2) if plies else None,
        "median_game_length_plies": statistics.median(plies) if plies else None,
        "min_game_length_plies": min(plies) if plies else None,
        "max_game_length_plies": max(plies) if plies else None,
        "games_by_year": dict(sorted(by_year.items())),
        "games_by_result": dict(by_result),
        "games_by_magnus_color": dict(by_color),
        "games_by_speed": dict(by_speed),
        "speed_basis": dict(by_speed_basis),
        "time_controls": top(by_time_control, 15),
        "events_top25": top(by_event, 25),
        "distinct_events": len(by_event),
        "eco_volume_counts": dict(sorted(by_eco.items())),
        "openings_top25": top(by_opening, 25),
        "flags": dict(by_flag),
        "parse_success_rate_by_source": {
            k: v.get("parse_success_rate") for k, v in build.get("sources", {}).items()
        },
        "build_reject_reasons": build.get("reject_reasons_total", {}),
        "duplicates_merged_at_build": build.get("duplicates_merged"),
    }
    Path(stats_path).parent.mkdir(parents=True, exist_ok=True)
    Path(stats_path).write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    return stats, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(CORPUS_PATH))
    args = ap.parse_args()
    stats, errors = validate(Path(args.corpus))

    print("=" * 60)
    print("CORPUS VALIDATION")
    print("=" * 60)
    for key in ("total_games", "unique_games", "illegal_or_invalid_games", "total_plies",
                "avg_game_length_plies", "median_game_length_plies",
                "min_game_length_plies", "max_game_length_plies"):
        print(f"{key:32s}: {stats[key]}")
    for key in ("games_by_source_membership", "games_by_source_combination", "games_by_result",
                "games_by_magnus_color", "games_by_speed", "flags",
                "parse_success_rate_by_source", "build_reject_reasons"):
        print(f"{key}: {stats[key]}")
    print(f"games_by_year: {stats['games_by_year']}")
    print(f"\nWrote {STATS_PATH}")
    if errors:
        print(f"\nFAILED: {len(errors)} validation errors, first 10:")
        for gid, err in errors[:10]:
            print(f"  {gid}: {err}")
        sys.exit(1)
    print("\nOK: every game replays legally; hashes, ids and Magnus identity verified.")


if __name__ == "__main__":
    main()
