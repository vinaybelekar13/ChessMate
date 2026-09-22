"""Replaceable component container used by compare / evidence / orchestrator."""

from __future__ import annotations

from typing import Optional

from src.engine.stockfish import StockfishAnalyzer, engine_available
from src.history.database import DEFAULT_DB, MagnusDB
from src.inference.api import DEFAULT_MODEL


class Services:
    def __init__(self, engine=None, db=None, model_path=None, engine_depth: int = 12, engine_multipv: int = 3):
        self._engine, self._db = engine, db
        self.model_path = str(model_path or DEFAULT_MODEL)
        self.engine_depth, self.engine_multipv = engine_depth, engine_multipv

    @property
    def engine(self) -> StockfishAnalyzer:
        if self._engine is None:
            self._engine = StockfishAnalyzer(depth=self.engine_depth, multipv=self.engine_multipv)
        return self._engine

    @property
    def db(self) -> Optional[MagnusDB]:
        if self._db is None and DEFAULT_DB.exists():
            self._db = MagnusDB()
        return self._db

    @property
    def engine_ok(self) -> bool:
        return self._engine is not None or engine_available()

    def close(self):
        if self._engine is not None:
            self._engine.close()
        if self._db is not None:
            self._db.close()
