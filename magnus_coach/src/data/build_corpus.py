"""Build the cleaned Magnus corpus from public raw sources.

Run:  .\\.venv\\Scripts\\python.exe src\\data\\build_corpus.py

Pipeline per source:  parse -> replay-validate -> identify Magnus -> collect.
Then:                 merge duplicates by canonical hash -> write outputs.

Every game that is dropped is written to data/cleaned/rejected_games.jsonl
with an explicit reason. Nothing is silently repaired or silently skipped.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.common import (  # noqa: E402
    classify_speed,
    clean_san,
    game_hash,
    game_id_from_hash,
    identify_magnus,
    replay_uci,
)

PGN_PATH = ROOT / "data" / "raw" / "carlsen" / "Carlsen.pgn"
CSV_PATH = ROOT / "data" / "raw" / "DrNykterstein.csv"
OUTPUT_DIR = ROOT / "data" / "cleaned"
OUTPUT_PATH = OUTPUT_DIR / "magnus_games.jsonl"
REJECTS_PATH = OUTPUT_DIR / "rejected_games.jsonl"
REPORT_PATH = ROOT / "outputs" / "corpus_build_report.json"

STANDARD_VARIANTS = {"", "standard", "chess"}

# Metadata copied from every source record (kept per-source for provenance).
META_FIELDS = (
    "white", "black", "result", "date", "event", "site", "round",
    "eco", "opening", "time_control", "termination", "white_elo", "black_elo",
)


# ---------------------------------------------------------------------------
# Candidate construction / validation shared by every source
# ---------------------------------------------------------------------------
def make_candidate(source, meta, moves, start_fen, source_ref, flags=None):
    """Validate one parsed game. Returns (game, None) or (None, reject)."""

    def reject(reason, detail=""):
        return None, {
            "source": source,
            "source_ref": source_ref,
            "reason": reason,
            "detail": detail,
            "white": meta.get("white", ""),
            "black": meta.get("black", ""),
            "date": meta.get("date", ""),
        }

    if not moves:
        return reject("empty_game", "no moves")

    ok, err, _ply = replay_uci(moves, start_fen)
    if not ok:
        return reject("illegal_sequence", err)

    color, opponent = identify_magnus(meta.get("white"), meta.get("black"))
    if color is None:
        return reject("magnus_not_identified", f"{meta.get('white')} vs {meta.get('black')}")

    speed, speed_basis = classify_speed(meta.get("time_control"), meta.get("event"), source)
    game = {
        "source": source,
        "source_ref": source_ref,
        "start_fen": start_fen,
        "moves": list(moves),
        "num_plies": len(moves),
        "magnus_color": color,
        "opponent": opponent,
        "speed": speed,
        "speed_basis": speed_basis,
        "flags": sorted(flags or []),
    }
    game.update({k: meta.get(k, "") for k in META_FIELDS})
    return game, None


# ---------------------------------------------------------------------------
# PGN source (PGN Mentor)
# ---------------------------------------------------------------------------
def extract_pgn_games(path, source="pgnmentor"):
    games, rejects, attempted = [], [], 0
    print(f"Reading PGN: {path}")
    # Strict decoding: a bad byte must fail loudly, not be silently dropped.
    with open(path, "r", encoding="utf-8-sig", errors="strict") as fh:
        index = 0
        while True:
            game = chess.pgn.read_game(fh)
            if game is None:
                break
            index += 1
            attempted += 1
            h = game.headers
            meta = {
                "white": h.get("White", ""), "black": h.get("Black", ""),
                "result": h.get("Result", ""), "date": h.get("Date", ""),
                "event": h.get("Event", ""), "site": h.get("Site", ""),
                "round": h.get("Round", ""), "eco": h.get("ECO", ""),
                "opening": h.get("Opening", ""), "time_control": h.get("TimeControl", ""),
                "termination": h.get("Termination", ""),
                "white_elo": h.get("WhiteElo", ""), "black_elo": h.get("BlackElo", ""),
            }
            ref = f"{Path(path).name}#game{index}"

            variant = h.get("Variant", "").strip().lower()
            if variant not in STANDARD_VARIANTS:
                rejects.append(_reject(source, ref, "variant_not_standard", h.get("Variant"), meta))
                continue

            # python-chess does NOT raise on illegal/ambiguous SAN: it records
            # game.errors and truncates the mainline. Treat that as a reject.
            if game.errors:
                rejects.append(_reject(source, ref, "pgn_parse_errors", str(game.errors[0]), meta))
                continue

            start_fen = game.board().fen()
            moves = [m.uci() for m in game.mainline_moves()]
            cand, rej = make_candidate(source, meta, moves, start_fen, ref)
            (games if cand else rejects).append(cand or rej)

    print(f"  {source}: attempted={attempted} accepted={len(games)} rejected={len(rejects)}")
    return games, rejects, attempted


# ---------------------------------------------------------------------------
# Lichess CSV source (DrNykterstein)
# ---------------------------------------------------------------------------
# A real move cell looks like "12.Nf3" / "12.O-O" / "12...Qe7" and always starts
# with a move number followed by a SAN that begins with a piece, file or 'O'.
# Clock cells ("0:01:00"), eval cells ("0.32", "#3") and 'NA' never match.
MOVE_CELL = re.compile(r"^(\d+)\.(?:\.\.)?[KQRBNOa-h]")


def lichess_row_moves(row, fieldnames):
    """Extract (san_list, layout_shifted) from one wide-CSV row.

    The export has two row layouts packed into the same columns:
      * with evals:    move, eval, clk, move, eval, clk ...  (3 cells / ply)
      * without evals: move, clk, move, clk ...              (2 cells / ply)
    so reading by column name ('w1','b1',...) returns clock strings for the
    second layout. Instead we read cells IN ORDER and keep only move-shaped
    cells. Each move number must match its ply (checked by the caller), so a
    misaligned read cannot silently yield a different-but-legal game.
    """
    start = fieldnames.index("w1")
    sans, shifted = [], False
    for col in fieldnames[start:]:
        value = (row.get(col) or "").strip()
        m = MOVE_CELL.match(value)
        if not m:
            continue
        ply = len(sans)
        expected_move_no = ply // 2 + 1
        if int(m.group(1)) != expected_move_no:
            raise ValueError(
                f"move number {m.group(1)} in column {col} but ply {ply + 1} "
                f"is move {expected_move_no}"
            )
        expected_col = f"{'w' if ply % 2 == 0 else 'b'}{expected_move_no}"
        if col != expected_col:
            shifted = True
        sans.append(clean_san(value))
    return sans, shifted


def extract_lichess_games(path, source="lichess"):
    """Parse the wide CSV (w1,b1,...). Terminal 'NA'/empty cells are VALID."""
    games, rejects, attempted = [], [], 0
    print(f"Reading Lichess CSV: {path}")
    with open(path, "r", encoding="utf-8-sig", errors="strict", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        move_cols = [int(m.group(1)) for c in fieldnames if (m := re.fullmatch(r"w(\d+)", c))]
        max_move = max(move_cols) if move_cols else 0

        for row_index, row in enumerate(reader, start=2):  # header is row 1
            attempted += 1
            meta = {
                "white": row.get("White", ""), "black": row.get("Black", ""),
                "result": row.get("Result", ""), "date": row.get("Date", ""),
                "event": row.get("Event", ""), "site": row.get("Site", ""),
                "round": "", "eco": row.get("ECO", ""), "opening": row.get("Opening", ""),
                "time_control": row.get("TimeControl", ""),
                "termination": row.get("Termination", ""),
                "white_elo": row.get("WhiteElo", ""), "black_elo": row.get("BlackElo", ""),
            }
            ref = row.get("Site") or f"{Path(path).name}#row{row_index}"

            variant = (row.get("Variant") or "").strip().lower()
            if variant not in STANDARD_VARIANTS:
                rejects.append(_reject(source, ref, "variant_not_standard", row.get("Variant"), meta))
                continue

            flags = set()
            try:
                sans, shifted = lichess_row_moves(row, fieldnames)
            except ValueError as exc:
                rejects.append(_reject(source, ref, "move_number_mismatch", exc, meta))
                continue
            if shifted:
                flags.add("layout_shifted")  # recovered from the no-eval layout

            board, moves, failure = chess.Board(), [], None
            for ply, san in enumerate(sans, start=1):
                try:
                    move = board.parse_san(san)
                except ValueError as exc:
                    failure = ("san_parse_error", f"ply {ply} {san!r}: {exc}")
                    break
                moves.append(move.uci())
                board.push(move)
            if failure:
                rejects.append(_reject(source, ref, failure[0], failure[1], meta))
                continue

            # The export only has columns up to `max_move`; a game that fills
            # every column may have been cut off. Keep it, but flag it.
            if len(moves) == 2 * max_move and not shifted:
                flags.add("column_cap_reached")

            cand, rej = make_candidate(source, meta, moves, chess.STARTING_FEN, ref, flags)
            (games if cand else rejects).append(cand or rej)

    print(f"  {source}: attempted={attempted} accepted={len(games)} rejected={len(rejects)}")
    return games, rejects, attempted


def _reject(source, ref, reason, detail, meta):
    return {
        "source": source, "source_ref": ref, "reason": reason, "detail": str(detail or ""),
        "white": meta.get("white", ""), "black": meta.get("black", ""), "date": meta.get("date", ""),
    }


# ---------------------------------------------------------------------------
# Deduplication (canonical identity = SHA-256(start_fen | full UCI sequence))
# ---------------------------------------------------------------------------
def deduplicate_games(games):
    """Merge games with identical canonical hash, keeping ALL provenance.

    The first occurrence is the primary record; empty fields are back-filled
    from later duplicates, and each source's own metadata is retained in
    `source_records`.
    """
    unique = {}
    for g in games:
        digest = game_hash(g["start_fen"], g["moves"])
        record = {"source": g["source"], "source_ref": g["source_ref"],
                  **{k: g.get(k, "") for k in META_FIELDS}}
        if digest not in unique:
            g = dict(g)
            g["game_hash"] = digest
            g["game_id"] = game_id_from_hash(digest)
            g["sources"] = [g["source"]]
            g["source_records"] = [record]
            unique[digest] = g
            continue
        primary = unique[digest]
        if g["source"] not in primary["sources"]:
            primary["sources"].append(g["source"])
        primary["source_records"].append(record)
        for k in META_FIELDS:
            if not primary.get(k) and g.get(k):
                primary[k] = g[k]
        if primary.get("speed") == "unspecified" and g.get("speed") != "unspecified":
            primary["speed"], primary["speed_basis"] = g["speed"], g["speed_basis"]
        primary["flags"] = sorted(set(primary["flags"]) | set(g["flags"]))
    for g in unique.values():
        g["sources"] = sorted(g["sources"])
    return sorted(unique.values(), key=lambda g: (g.get("date", ""), g["game_hash"]))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def build(pgn_path=PGN_PATH, csv_path=CSV_PATH, out_path=OUTPUT_PATH,
          rejects_path=REJECTS_PATH, report_path=REPORT_PATH):
    all_games, all_rejects, per_source = [], [], {}

    for name, fn, path in (("pgnmentor", extract_pgn_games, pgn_path),
                           ("lichess", extract_lichess_games, csv_path)):
        if not Path(path).exists():
            print(f"  (skipping missing source: {path})")
            continue
        g, r, attempted = fn(path)
        all_games += g
        all_rejects += r
        per_source[name] = {
            "attempted": attempted, "accepted": len(g), "rejected": len(r),
            "reject_reasons": dict(Counter(x["reason"] for x in r)),
            "parse_success_rate": round(len(g) / attempted, 6) if attempted else None,
        }

    unique = deduplicate_games(all_games)
    write_jsonl(out_path, unique)
    write_jsonl(rejects_path, all_rejects)

    report = {
        "sources": per_source,
        "accepted_before_dedup": len(all_games),
        "duplicates_merged": len(all_games) - len(unique),
        "unique_games": len(unique),
        "total_plies": sum(g["num_plies"] for g in unique),
        "multi_source_games": sum(1 for g in unique if len(g["sources"]) > 1),
        "flagged_column_cap": sum(1 for g in unique if "column_cap_reached" in g["flags"]),
        "flagged_layout_shifted": sum(1 for g in unique if "layout_shifted" in g["flags"]),
        "reject_reasons_total": dict(Counter(x["reason"] for x in all_rejects)),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== CORPUS BUILD ===")
    for k, v in report.items():
        print(f"{k}: {v}")
    print(f"\nWrote {out_path}\nWrote {rejects_path}\nWrote {report_path}")
    return report


if __name__ == "__main__":
    build()
