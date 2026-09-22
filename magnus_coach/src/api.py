"""ChessMate integration API (Phase 32). Every function returns JSON-serialisable data.

    from src.api import (load_magnus_model, predict_next_move, predict_moves, find_similar_positions,
                         analyze_position, compare_moves, get_historical_magnus_examples,
                         generate_coach_evidence, challenge_plan, generate_training_position)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.coach import compare as _compare
from src.coach import evidence as _evidence
from src.coach import plan as _plan
from src.coach.orchestrator import ChessMateCoach
from src.coach.player import JsonPlayerStore, TrainingSystem
from src.coach.services import Services
from src.history import database as _db
from src.history.evidence import historical_examples
from src.inference import api as _inf

ROOT = Path(__file__).resolve().parents[1]
PLAYER_DIR = ROOT / "data" / "players"
_services: Optional[Services] = None
_coach: Optional[ChessMateCoach] = None


def _svc() -> Services:
    global _services
    if _services is None:
        _services = Services()
    return _services


def _get_coach() -> ChessMateCoach:
    global _coach
    if _coach is None:
        _coach = ChessMateCoach(_svc(), JsonPlayerStore(PLAYER_DIR))
    return _coach


def shutdown() -> None:
    global _services, _coach
    if _services is not None:
        _services.close()
    _services = _coach = None


def _json(x):
    return json.loads(json.dumps(x))       # guarantees JSON-serialisable output (raises otherwise)


def load_magnus_model(path: Optional[str] = None) -> Dict[str, Any]:
    model, meta = _inf.load_magnus_model(str(path or _inf.DEFAULT_MODEL))
    return _json({"loaded": True, "path": str(path or _inf.DEFAULT_MODEL), "parameters": model.parameter_count(),
                  "encoding_version": model.config.encoding_version, "move_space": model.config.num_moves, "meta": meta})


def predict_moves(fen: str, top_k: int = 5, previous_moves=None, time_control=None) -> List[Dict[str, Any]]:
    return _json(_inf.predict_moves(fen, top_k, previous_moves, time_control))


def predict_next_move(fen: str, previous_moves=None, time_control=None) -> Dict[str, Any]:
    return _json(_inf.predict_next_move(fen, previous_moves=previous_moves, time_control=time_control))


def find_similar_positions(fen: str, top_k: int = 10, **filters) -> List[Dict[str, Any]]:
    return _json(_svc().db.find_similar_positions(fen, top_k, **filters))


def get_historical_magnus_examples(fen: str, top_k: int = 5) -> List[Dict[str, Any]]:
    return _json(historical_examples(fen, _svc().db, top_k))


def analyze_position(fen: str, **kw) -> Dict[str, Any]:
    return _json(_get_coach().analyze_position(fen, **kw))


def compare_moves(fen: str, user_move: str, **kw) -> Dict[str, Any]:
    return _json(_compare.compare_moves(fen, user_move, _svc(), **kw))


def generate_coach_evidence(fen: str, user_move: str, **kw) -> Dict[str, Any]:
    return _json(_evidence.generate_coach_evidence(fen, user_move, _svc(), **kw))


def challenge_plan(fen: str, plan: str) -> Dict[str, Any]:
    return _json(_plan.challenge_plan(fen, plan, _svc()))


def generate_training_position(player_id: str, categories: Optional[List[str]] = None, concept: Optional[str] = None,
                               player_dir=None) -> Optional[Dict[str, Any]]:
    """Next training position built from the player's REAL analysed mistakes (None if there are none)."""
    ts = TrainingSystem(JsonPlayerStore(player_dir or PLAYER_DIR), player_id)
    ts.generate(categories, max_items=1, concept=concept)
    pool = [i for i in ts.items() if not i["stats"]["solved"] and (not categories or i["category"] in categories)
            and (concept is None or i["concept_key"] == concept)]
    return _json({**ts.present(pool[0]["item_id"]), "hints_available": 3}) if pool else None
