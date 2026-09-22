"""ChessMateCoach orchestrator (Phase 27).

Receives a position / move / plan / question, decides which components are
needed, calls them, assembles STRUCTURED evidence and asks the (replaceable)
LLM layer for an explanation. Sections of every response are kept apart:

  engine_truth          Stockfish only
  magnus_model          learned imitation of historical Magnus moves
  historical_evidence   stored Magnus games (real records)
  player_history        the user's analysed mistakes
  knowledge             concept definitions with provenance
  coach_interpretation  text from the LLM layer, with its grounding check
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

import chess

from src.chess_core import tactics as T
from src.history.evidence import historical_examples
from src.inference.api import predict_moves
from . import annotations as A
from .evidence import generate_coach_evidence
from .knowledge import KnowledgeSource, LocalKnowledgeBase
from .llm import CoachLLM
from .plan import SocraticSession, challenge_plan
from .player import JsonPlayerStore, PlayerModel, PlayerStoreBase, RetestLoop, TrainingSystem
from .services import Services

MODES = ("analysis", "why_wrong", "why_good", "socratic", "reveal")


class ChessMateCoach:
    def __init__(self, services: Optional[Services] = None, player_store: Optional[PlayerStoreBase] = None,
                 knowledge: Optional[KnowledgeSource] = None, llm: Optional[CoachLLM] = None):
        self.services = services or Services()
        self.store = player_store
        self.kb = knowledge or LocalKnowledgeBase()
        self.llm = llm or CoachLLM()
        self._sessions: Dict[str, SocraticSession] = {}

    def close(self):
        self.services.close()

    # ------------------------------------------------------------------ position
    def analyze_position(self, fen: str, previous_moves=None, time_control=None, top_k: int = 5) -> Dict[str, Any]:
        board = chess.Board(fen)
        out: Dict[str, Any] = {"kind": "position_analysis", "fen": board.fen(), "side_to_move": chess.COLOR_NAMES[board.turn]}
        if board.is_game_over():
            out["engine_truth"] = None
            out["magnus_model"] = None
            out["historical_evidence"] = ({"kind": "historical_fact", "examples": historical_examples(fen, self.services.db, top_k)}
                                          if self.services.db is not None else {"kind": "historical_fact", "examples": [],
                                                                                "note": "historical database not available"})
            out["note"] = f"game over: {board.result()}"
            return out
        out["magnus_model"] = {"kind": "model_prediction", "moves": predict_moves(fen, top_k, previous_moves, time_control,
                                                                                 model_path=self.services.model_path)}
        out["historical_evidence"] = ({"kind": "historical_fact", "examples": historical_examples(fen, self.services.db, top_k)}
                                      if self.services.db is not None else {"kind": "historical_fact", "examples": [],
                                                                            "note": "historical database not available"})
        out["engine_truth"] = self.services.engine.analyze(fen) if self.services.engine_ok else {
            "kind": "engine_analysis", "error": "engine_unavailable"}
        tac = T.analyze_tactics(board)
        out["tactics"] = {"opportunities_for_side_to_move": tac["opportunities_for_side_to_move"],
                          "threats_against_side_to_move": tac["threats_against_side_to_move"],
                          "pins_and_skewers": tac["pins_and_skewers"], "trapped": tac["trapped"],
                          "hanging": tac["hanging"], "back_rank_weakness": tac["back_rank_weakness"],
                          "unsupported_motifs": tac["unsupported_motifs"]}
        ann = []
        if out["engine_truth"] and out["engine_truth"].get("best_move"):
            bm = chess.Move.from_uci(out["engine_truth"]["best_move"]["uci"])
            ann.append(A.arrow(chess.square_name(bm.from_square), chess.square_name(bm.to_square), "best-move", board.fen(), "engine", "engine best move"))
        for c in ("white", "black"):
            for h in tac["hanging"][c]:
                ann.append(A.highlight(h["target_squares"][0], "threat", board.fen(), "board", "hanging piece"))
        out["annotations"] = A.dedupe(ann)
        return out

    # ------------------------------------------------------------------ move review
    def review_move(self, fen: str, move: str, mode: str = "analysis", player_id: Optional[str] = None, game_id: Optional[str] = None,
                    ply: Optional[int] = None, clock_seconds: Optional[float] = None, previous_moves=None, time_control=None,
                    record: bool = True) -> Dict[str, Any]:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
        ev = generate_coach_evidence(fen, move, self.services, previous_moves=previous_moves, time_control=time_control)
        weaknesses, training = [], []
        if player_id and self.store is not None:
            if record and game_id is not None and ply is not None:
                loop = RetestLoop(self.store, player_id, self.services)
                rec = loop.model.ingest(ev, game_id, ply, clock_seconds)
                if rec["label"] in ("inaccuracy", "mistake", "blunder"):
                    training = loop.training.generate(max_items=1, concept=rec["concept_key"])
            weaknesses = PlayerModel(self.store, player_id).weaknesses()
        knowledge = self.kb.for_concept(ev["concept_key"]) if ev["concept_key"] else self.kb.search(tags=["blunder_check"], k=1) if ev["classification"]["label"] in ("mistake", "blunder") else []
        text = self.llm.explain(ev, "analysis" if mode == "reveal" else mode, weaknesses, knowledge)
        c = ev["comparison"]
        return {
            "kind": "move_review", "mode": mode, "fen": ev["position"]["fen"], "user_move": ev["user_move"],
            "classification": ev["classification"], "mistake_category": ev["mistake_category"], "concept": ev["concept_key"],
            "engine_truth": c["engine"], "magnus_model": c["magnus_model"], "historical_evidence": c["historical"],
            "player_history": {"weaknesses": weaknesses, "new_training_items": training} if player_id else None,
            "knowledge": [k.to_dict() for k in knowledge], "coach_interpretation": text,
            "annotations": ev["annotations"], "consequence_chain": ev["consequence_chain"], "evidence": ev,
            "separation": ["engine_truth", "magnus_model", "historical_evidence", "player_history", "knowledge", "coach_interpretation"],
        }

    # ------------------------------------------------------------------ plan / socratic / training
    def challenge(self, fen: str, plan: str) -> Dict[str, Any]:
        r = challenge_plan(fen, plan, self.services)
        r["knowledge"] = [k.to_dict() for k in self.kb.search(tags=["king_safety"] if any("shield" in w["fact"] for w in r["positional_concerns"]) else [], query=plan, k=1)]
        return r

    def socratic_start(self, fen: str, move: str, hint_only: bool = False) -> Dict[str, Any]:
        ev = generate_coach_evidence(fen, move, self.services)
        sid = uuid.uuid4().hex[:12]
        s = SocraticSession(ev, hint_only)
        self._sessions[sid] = s
        return {"session_id": sid, "hint_only": hint_only, "classification": ev["classification"]["label"], **s.next_hint()}

    def socratic_next(self, session_id: str) -> Dict[str, Any]:
        return {"session_id": session_id, **self._sessions[session_id].next_hint()}

    def socratic_reveal(self, session_id: str) -> Dict[str, Any]:
        return {"session_id": session_id, **self._sessions[session_id].reveal()}

    def training(self, player_id: str) -> TrainingSystem:
        if self.store is None:
            raise RuntimeError("no player store configured")
        return TrainingSystem(self.store, player_id)

    # ------------------------------------------------------------------ router
    def route(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Determine the required analysis from a request dict and dispatch."""
        task = request.get("task")
        try:
            if task == "analyze_position":
                return self.analyze_position(request["fen"], request.get("previous_moves"), request.get("time_control"))
            if task == "review_move":
                return self.review_move(request["fen"], request["move"], request.get("mode", "analysis"), request.get("player_id"),
                                        request.get("game_id"), request.get("ply"), request.get("clock_seconds"))
            if task == "challenge_plan":
                return self.challenge(request["fen"], request["plan"])
            if task == "socratic_start":
                return self.socratic_start(request["fen"], request["move"], request.get("hint_only", False))
            if task == "socratic_next":
                return self.socratic_next(request["session_id"])
            if task == "player_summary":
                return PlayerModel(self.store, request["player_id"]).summary()
            raise ValueError(f"unknown task {task!r}")
        except (ValueError, KeyError) as e:
            return {"kind": "error", "task": task, "error": str(e)}
