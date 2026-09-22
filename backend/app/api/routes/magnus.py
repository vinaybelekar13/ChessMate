"""Magnus model + historical Magnus evidence (integration spec §4, §8, §9).

This module is an ADAPTER, not a reimplementation: every call below goes
straight through to the existing, tested ChessMate-MagnusCoach project
(vendored as the sibling package `magnus_coach/`, unmodified). No retraining,
no new model, no fabricated predictions.

Two things this integration environment could not verify end-to-end and that
whoever deploys this should be aware of (see FINAL_REPORT.md):

1. PyTorch is a hard dependency of magnus_coach/src/inference/api.py. If it
   isn't installed, every endpoint here returns a clearly-labeled
   {"available": false} response instead of crashing the process or the
   request — the same "never fabricate, degrade visibly" pattern already
   used by app/chess/engine.py for a missing Stockfish binary.
2. The historical Magnus SQLite database (magnus_coach/data/magnus_history.sqlite,
   ~400MB / 721k positions per the original project's own build report) is
   NOT bundled in this package — see magnus_coach/README.md "Rebuild the data
   pipeline". Historical-lookup endpoints will report unavailable until that
   database is built or supplied separately.

The MAGNUS MODEL and HISTORICAL MAGNUS are kept in clearly separate response
keys everywhere in this file — never merge them into one "magnus said X"
field. See integration spec §4/§9.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_MAGNUS_ROOT = Path(__file__).resolve().parents[4] / "magnus_coach"
if str(_MAGNUS_ROOT) not in sys.path:
    sys.path.insert(0, str(_MAGNUS_ROOT))


def _import_magnus_api():
    """Lazy import so a missing torch (or a missing magnus_coach checkout)
    never prevents the rest of ChessMate's backend from starting up."""
    import src.api as magnus_api  # magnus_coach/src/api.py
    return magnus_api


def _unavailable(reason: str, source: str) -> Dict[str, Any]:
    return {"available": False, "reason": reason, "source": source}


class PredictRequest(BaseModel):
    fen: str
    top_k: int = 5
    previous_moves: Optional[List[str]] = None


class CompareRequest(BaseModel):
    fen: str
    user_move: str


class CoachEvidenceRequest(BaseModel):
    fen: str
    user_move: str


@router.get("/status")
def magnus_status():
    try:
        api = _import_magnus_api()
    except Exception as e:  # torch missing, checkpoint missing, etc.
        return _unavailable(str(e), "magnus_model")
    try:
        info = api.load_magnus_model()
        return {"available": True, "source": "magnus_model", **info}
    except Exception as e:
        return _unavailable(str(e), "magnus_model")


@router.post("/predict")
def predict_moves(body: PredictRequest):
    try:
        api = _import_magnus_api()
        predictions = api.predict_moves(body.fen, body.top_k, body.previous_moves)
        return {"available": True, "source": "magnus_model", "predictions": predictions}
    except Exception as e:
        return _unavailable(str(e), "magnus_model")


@router.get("/historical")
def historical_examples(fen: str, top_k: int = 5):
    """HISTORICAL MAGNUS — actual games from the database, never a model
    prediction. Returns available: false (not an error) if the ~400MB
    historical database hasn't been built/supplied for this deployment."""
    try:
        api = _import_magnus_api()
        games = api.get_historical_magnus_examples(fen, top_k)
        return {"available": True, "source": "historical_magnus", "games": games}
    except Exception as e:
        return _unavailable(str(e), "historical_magnus")


@router.post("/compare")
def compare_moves(body: CompareRequest):
    try:
        api = _import_magnus_api()
        return {"available": True, "source": "magnus_coach", **api.compare_moves(body.fen, body.user_move)}
    except Exception as e:
        return _unavailable(str(e), "magnus_coach")


@router.post("/coach-evidence")
def coach_evidence(body: CoachEvidenceRequest):
    """The unified evidence object for a single user move (spec §7): engine +
    Magnus model + historical Magnus, whichever of those are actually
    available in this deployment — never fabricated for the ones that aren't."""
    try:
        api = _import_magnus_api()
        return {"available": True, "source": "magnus_coach", **api.generate_coach_evidence(body.fen, body.user_move)}
    except Exception as e:
        return _unavailable(str(e), "magnus_coach")
