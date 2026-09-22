"""Shared engine service (integration spec §3, §26).

There is exactly one Stockfish adapter in this codebase — app/chess/engine.py,
originally written for Book Coach's ingestion-time position checks. Per the
integration spec, that same adapter is now the ONE shared engine for the
whole application: ChessMate's move analysis, Magnus coach comparisons, and
Book Coach puzzle checking all call these two endpoints instead of each
spinning up their own Stockfish process.

Nothing here talks to the Magnus model — see routes/magnus.py. This module
only ever returns an objective Stockfish evaluation, or a clearly-labeled
"available: false" when the binary isn't present, never a fabricated score.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.chess import engine as stockfish

router = APIRouter()


class EvaluateRequest(BaseModel):
    fen: str
    depth: int = 15


@router.get("/status")
def engine_status():
    return {"available": stockfish.is_available(), "source": "shared_stockfish"}


@router.post("/evaluate")
def evaluate(body: EvaluateRequest):
    result = stockfish.evaluate_fen(body.fen, depth=body.depth)
    result["source"] = "shared_stockfish"
    return result
