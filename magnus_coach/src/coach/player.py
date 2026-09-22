"""Player model (22), personalised training (23) and retest loop (24).

Everything is evidence-backed and measurable: weaknesses are COUNTS of analysed
mistakes with links to the exact positions (record_id -> game_id, ply, FEN).
No mastery scores or ratings are invented. Ordering uses a per-player sequence
counter (not wall-clock time), so behaviour is reproducible.

Persistence goes through `PlayerStoreBase`; `JsonPlayerStore` is the V1 backend
(one atomic JSON file per player) and can be replaced by a database.
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import chess

from .evidence import FORCING_MOTIFS, generate_coach_evidence, non_pawn_material
from .plan import HINT_LEVELS, build_hints

MISTAKE_LABELS = ("inaccuracy", "mistake", "blunder")
GOOD_LABELS = ("best", "brilliant", "excellent")
SCHEMA_VERSION = 1
CATEGORY_TO_TRAINING = {"tactical": "tactics", "positional": "positional", "opening": "openings",
                        "endgame": "endgames", "calculation": "calculation"}
TIME_PRESSURE_SECONDS = 30


# ------------------------------------------------------------------ persistence
class PlayerStoreBase(ABC):
    @abstractmethod
    def load(self, player_id: str) -> Dict[str, Any]: ...

    @abstractmethod
    def save(self, player_id: str, data: Dict[str, Any]) -> None: ...


def _empty(player_id: str) -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "player_id": player_id, "seq": 0, "records": [], "training_items": [],
            "attempts": []}


class JsonPlayerStore(PlayerStoreBase):
    def __init__(self, root):
        self.root = Path(root)

    def _path(self, player_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", player_id):
            raise ValueError("invalid player_id")
        return self.root / f"{player_id}.json"

    def load(self, player_id: str) -> Dict[str, Any]:
        p = self._path(player_id)
        if not p.exists():
            return _empty(player_id)
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported player file version {data.get('schema_version')}")
        return data

    def save(self, player_id: str, data: Dict[str, Any]) -> None:
        p = self._path(player_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(tmp, p)


class MemoryPlayerStore(PlayerStoreBase):
    def __init__(self):
        self.data: Dict[str, Dict[str, Any]] = {}

    def load(self, player_id):
        return json.loads(json.dumps(self.data.get(player_id) or _empty(player_id)))

    def save(self, player_id, data):
        self.data[player_id] = json.loads(json.dumps(data))


# ------------------------------------------------------------------ player model
def record_from_evidence(ev: Dict[str, Any], game_id: str, ply: int, clock_seconds: Optional[float] = None) -> Dict[str, Any]:
    board = chess.Board(ev["position"]["fen"])
    mv = chess.Move.from_uci(ev["user_move"]["uci"])
    piece = board.piece_at(mv.from_square)
    eng = ev["comparison"]["engine"]
    found = any(o["trigger_move"] == mv.uci() and o["motif"] in FORCING_MOTIFS
                for o in ev["tactics"]["before"]["opportunities_for_side_to_move"])
    phase = "endgame" if non_pawn_material(board) <= 24 else ("opening" if board.fullmove_number <= 10 else "middlegame")
    return {
        "record_id": f"{game_id}:{ply}", "game_id": game_id, "ply": ply, "fen": ev["position"]["fen"],
        "move_number": board.fullmove_number, "user_move": ev["user_move"], "best_move": eng["best_move"],
        "label": ev["classification"]["label"], "win_pct_loss": eng["classification_loss"],
        "category": ev["mistake_category"], "motifs": ev["motifs"], "concept_key": ev["concept_key"],
        "phase": phase, "piece_type": chess.piece_name(piece.piece_type), "is_capture": board.is_capture(mv),
        "missed_opportunities": sorted({o["motif"] for o in ev["missed_opportunities"]}),
        "found_tactic": found, "clock_seconds": clock_seconds,
        "reason_claims": [c["claim"] for c in ev["consequence_chain"] if c["source"] in ("engine", "board")],
        "hints": {k: v["text"] for k, v in build_hints(ev).items() if k != "reveal"},
        "reveal_line": eng["top_lines"][0]["pv_san"][:6],
    }


class PlayerModel:
    def __init__(self, store: PlayerStoreBase, player_id: str):
        self.store, self.player_id = store, player_id

    def _data(self):
        return self.store.load(self.player_id)

    def ingest(self, ev: Dict[str, Any], game_id: str, ply: int, clock_seconds: Optional[float] = None) -> Dict[str, Any]:
        d = self._data()
        rid = f"{game_id}:{ply}"
        existing = next((r for r in d["records"] if r["record_id"] == rid), None)
        if existing:
            return existing                           # idempotent: the same analysed move is never double counted
        d["seq"] += 1
        rec = record_from_evidence(ev, game_id, ply, clock_seconds)
        rec["seq"] = d["seq"]
        d["records"].append(rec)
        self.store.save(self.player_id, d)
        return rec

    def records(self) -> List[Dict[str, Any]]:
        return self._data()["records"]

    def summary(self, min_recurrence: int = 2) -> Dict[str, Any]:
        recs = self.records()
        mistakes = [r for r in recs if r["label"] in MISTAKE_LABELS]

        def refs(rs):
            return [{"record_id": r["record_id"], "game_id": r["game_id"], "ply": r["ply"], "fen": r["fen"]} for r in rs]

        by_label: Dict[str, int] = {}
        for r in recs:
            by_label[r["label"]] = by_label.get(r["label"], 0) + 1
        cats: Dict[str, List[dict]] = {}
        concepts: Dict[str, List[dict]] = {}
        motifs: Dict[str, List[dict]] = {}
        for r in mistakes:
            cats.setdefault(r["category"] or "unclassified", []).append(r)
            concepts.setdefault(r["concept_key"] or "unclassified", []).append(r)
            for m in r["motifs"]:
                motifs.setdefault(m, []).append(r)
        positional = [r for r in mistakes if r["category"] == "positional"]
        clocked = [r for r in mistakes if r.get("clock_seconds") is not None]
        pressure = [r for r in clocked if r["clock_seconds"] < TIME_PRESSURE_SECONDS]
        return {
            "player_id": self.player_id, "analysed_moves": len(recs), "mistakes": len(mistakes), "by_label": by_label,
            "mistake_categories": {k: {"count": len(v), "share_of_mistakes": round(len(v) / len(mistakes), 4), "evidence": refs(v)}
                                   for k, v in sorted(cats.items())},
            "recurring_motifs": {k: {"count": len(v), "evidence": refs(v)} for k, v in sorted(motifs.items()) if len(v) >= min_recurrence},
            "recurring_concepts": [{"concept": k, "count": len(v), "share_of_mistakes": round(len(v) / len(mistakes), 4), "evidence": refs(v)}
                                   for k, v in sorted(concepts.items(), key=lambda kv: (-len(kv[1]), kv[0])) if len(v) >= min_recurrence],
            "piece_placement_problems": refs([r for r in positional if r["piece_type"] != "pawn"]),
            "pawn_structure_problems": refs([r for r in positional if r["piece_type"] == "pawn"]),
            "missed_opportunities": refs([r for r in recs if r["missed_opportunities"]]),
            "time_management": ({"mistakes_under_time_pressure": len(pressure), "of_mistakes_with_clock_data": len(clocked),
                                 "threshold_seconds": TIME_PRESSURE_SECONDS, "evidence": refs(pressure)} if clocked
                                else {"status": "not evidenced: no clock data was supplied"}),
            "strengths": {"best_or_excellent_moves": sum(1 for r in recs if r["label"] in GOOD_LABELS),
                          "tactics_found": refs([r for r in recs if r["found_tactic"]]),
                          "by_phase": {p: sum(1 for r in recs if r["phase"] == p and r["label"] in GOOD_LABELS) for p in ("opening", "middlegame", "endgame")}},
            "note": "All figures are counts of analysed moves; no ratings or mastery scores are computed.",
        }

    def weaknesses(self, min_count: int = 2) -> List[Dict[str, Any]]:
        return self.summary(min_count)["recurring_concepts"]


# ------------------------------------------------------------------ training
class TrainingSystem:
    def __init__(self, store: PlayerStoreBase, player_id: str):
        self.store, self.player_id = store, player_id

    def _data(self):
        return self.store.load(self.player_id)

    def generate(self, categories: Optional[List[str]] = None, max_items: int = 5, concept: Optional[str] = None) -> List[Dict[str, Any]]:
        d = self._data()
        used = {i["source_record_id"] for i in d["training_items"]}
        wanted = set(categories or CATEGORY_TO_TRAINING.values())
        new = []
        for r in sorted(d["records"], key=lambda r: -r["seq"]):
            if len(new) >= max_items:
                break
            if r["label"] not in MISTAKE_LABELS or r["record_id"] in used:
                continue
            if CATEGORY_TO_TRAINING.get(r["category"], "positional") not in wanted or (concept and r["concept_key"] != concept):
                continue
            item = {"item_id": f"T{len(d['training_items']) + len(new) + 1:04d}", "source_record_id": r["record_id"],
                    "source_game": r["game_id"], "source_ply": r["ply"], "original_fen": r["fen"], "user_move": r["user_move"],
                    "better_move": r["best_move"], "reason": r["reason_claims"], "motif": (r["motifs"] or [None])[0],
                    "concept_key": r["concept_key"], "category": CATEGORY_TO_TRAINING.get(r["category"], "positional"),
                    "hints": r["hints"], "reveal_line": r["reveal_line"], "created_seq": d["seq"],
                    "stats": {"attempts": 0, "hints_used": 0, "revealed": False, "solved": False, "solved_unassisted": False}}
            new.append(item)
        d["training_items"].extend(new)
        self.store.save(self.player_id, d)
        return new

    def items(self) -> List[Dict[str, Any]]:
        return self._data()["training_items"]

    def _get(self, d, item_id):
        for i in d["training_items"]:
            if i["item_id"] == item_id:
                return i
        raise KeyError(item_id)

    def present(self, item_id: str) -> Dict[str, Any]:
        it = self._get(self._data(), item_id)
        b = chess.Board(it["original_fen"])
        return {"item_id": item_id, "fen": it["original_fen"], "side_to_move": chess.COLOR_NAMES[b.turn], "category": it["category"],
                "prompt": "Find the best move for the side to move.", "legal_moves": sorted(m.uci() for m in b.legal_moves),
                "provenance": {"source_game": it["source_game"], "source_ply": it["source_ply"], "original_user_move": it["user_move"]["san"]}}

    def hint(self, item_id: str) -> Dict[str, Any]:
        d = self._data()
        it = self._get(d, item_id)
        n = it["stats"]["hints_used"]
        if n >= 3:
            return {"item_id": item_id, "hint": None, "exhausted": True}
        it["stats"]["hints_used"] = n + 1
        self.store.save(self.player_id, d)
        return {"item_id": item_id, "level": HINT_LEVELS[n], "hint": it["hints"][HINT_LEVELS[n]]}

    def reveal(self, item_id: str) -> Dict[str, Any]:
        d = self._data()
        it = self._get(d, item_id)
        it["stats"]["revealed"] = True
        self.store.save(self.player_id, d)
        return {"item_id": item_id, "better_move": it["better_move"], "line": it["reveal_line"], "reason": it["reason"]}

    def attempt(self, item_id: str, move: str, services=None, tolerance_win_pct: float = 2.0) -> Dict[str, Any]:
        """Solve/retry. Solved if the move equals the stored better move, or (with an engine) loses <= tolerance win% vs the best."""
        from .compare import parse_move
        d = self._data()
        it = self._get(d, item_id)
        board = chess.Board(it["original_fen"])
        try:
            mv = parse_move(board, move)
        except ValueError:
            return {"item_id": item_id, "legal": False, "solved": False, "message": "not a legal move here; try again"}
        exact = mv.uci() == it["better_move"]["uci"]
        loss = 0.0 if exact else None
        if not exact and services is not None:
            before = services.engine.analyze(it["original_fen"])["evaluation"]["win_pct"]
            after = services.engine.evaluate_move(it["original_fen"], mv.uci())["score_for_mover"]["win_pct"]
            loss = max(0.0, before - after)
        solved = exact or (loss is not None and loss <= tolerance_win_pct)
        st = it["stats"]
        st["attempts"] += 1
        unassisted = solved and st["hints_used"] == 0 and not st["revealed"]
        st["solved"] = st["solved"] or solved
        st["solved_unassisted"] = st["solved_unassisted"] or unassisted
        d["seq"] += 1
        d["attempts"].append({"item_id": item_id, "move": mv.uci(), "solved": solved, "unassisted": unassisted, "seq": d["seq"],
                              "concept_key": it["concept_key"], "win_pct_loss": None if loss is None else round(loss, 3)})
        self.store.save(self.player_id, d)
        return {"item_id": item_id, "legal": True, "solved": solved, "unassisted": unassisted, "win_pct_loss": loss,
                "matches_stored_better_move": exact, "attempts": st["attempts"], "retry_allowed": not solved}

    def stats(self) -> Dict[str, Any]:
        d = self._data()
        its = d["training_items"]
        return {"items": len(its), "attempted": sum(1 for i in its if i["stats"]["attempts"]),
                "solved": sum(1 for i in its if i["stats"]["solved"]),
                "solved_unassisted": sum(1 for i in its if i["stats"]["solved_unassisted"]),
                "revealed": sum(1 for i in its if i["stats"]["revealed"]),
                "total_attempts": sum(i["stats"]["attempts"] for i in its)}


# ------------------------------------------------------------------ retest loop
class RetestLoop:
    """PLAY -> ANALYZE -> MISTAKE -> CONCEPT -> TRAIN -> RETEST, with measurable statistics only."""

    def __init__(self, store: PlayerStoreBase, player_id: str, services):
        self.store, self.player_id, self.services = store, player_id, services
        self.model = PlayerModel(store, player_id)
        self.training = TrainingSystem(store, player_id)

    def process_move(self, fen: str, move: str, game_id: str, ply: int, clock_seconds: Optional[float] = None) -> Dict[str, Any]:
        ev = generate_coach_evidence(fen, move, self.services)                         # ANALYZE
        existing = {r["record_id"] for r in self.model.records()}
        rec = self.model.ingest(ev, game_id, ply, clock_seconds)
        new_items: List[dict] = []
        concept = None
        if rec["label"] in MISTAKE_LABELS and rec["record_id"] not in existing:        # MISTAKE -> CONCEPT
            concept = self.concept_stats(rec["concept_key"])
            new_items = self.training.generate(max_items=1, concept=rec["concept_key"])  # TRAIN
        return {"evidence": ev, "record": rec, "concept": concept, "new_training_items": new_items,
                "is_repeat_of_known_concept": bool(concept and concept["occurrences"] >= 2)}

    def concept_stats(self, concept: str) -> Dict[str, Any]:
        d = self.store.load(self.player_id)
        occ = [r for r in d["records"] if r["label"] in MISTAKE_LABELS and r["concept_key"] == concept]
        items = [i for i in d["training_items"] if i["concept_key"] == concept]
        atts = [a for a in d["attempts"] if a["concept_key"] == concept]
        first_solved = min((a["seq"] for a in atts if a["solved"]), default=None)
        return {"concept": concept, "occurrences": len(occ), "record_ids": [r["record_id"] for r in occ],
                "training_items": [i["item_id"] for i in items], "training_attempts": len(atts),
                "training_solved": sum(1 for a in atts if a["solved"]),
                "occurrences_after_first_training_success": (sum(1 for r in occ if r["seq"] > first_solved) if first_solved else 0)}

    def next_retest(self, concept: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """An unsolved item first; otherwise a solved item whose concept RECURRED after it was solved."""
        d = self.store.load(self.player_id)
        pool = [i for i in d["training_items"] if concept in (None, i["concept_key"])]
        for i in pool:
            if not i["stats"]["solved"]:
                return self.training.present(i["item_id"])
        for i in pool:
            solved_seq = min((a["seq"] for a in d["attempts"] if a["item_id"] == i["item_id"] and a["solved"]), default=None)
            if solved_seq and any(r["seq"] > solved_seq and r["label"] in MISTAKE_LABELS and r["concept_key"] == i["concept_key"]
                                  for r in d["records"]):
                return self.training.present(i["item_id"])
        return None
