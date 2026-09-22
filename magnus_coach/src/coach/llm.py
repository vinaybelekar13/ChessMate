"""LLM coach interface (Phase 25).

The LLM never calculates chess. It receives ONLY verified evidence
(`build_llm_payload`) and may explain, teach, question, connect concepts and
personalise. Its output is checked by `verify_grounding`; if it mentions a move,
number or Magnus claim the evidence does not support, the response is replaced
by the deterministic `TemplateProvider` text and the failure is reported.

`TemplateProvider` is NOT a language model: it is a deterministic renderer of
the evidence, used as the default and as the safe fallback.
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

import chess

SYSTEM_PROMPT = """You are the explanation layer of a chess coach. You do NOT calculate chess.
Use ONLY the JSON evidence you are given. Rules:
1. Never state a move, evaluation, variation, tactic or historical game that is not in the evidence.
2. Keep sources apart: Stockfish (engine_truth), the Magnus behavioural model (magnus_model),
   stored Magnus games (historical_evidence) and your own interpretation. Never present an engine
   evaluation as something Magnus thought. The model imitates historical choices; it does not
   represent Magnus Carlsen's private thoughts.
3. If the evidence is insufficient, say "insufficient evidence".
4. Teach: explain why, connect to the chess concept, and say what to check next time.
5. In socratic mode ask the question; do not reveal the answer unless mode is reveal."""

_SAN_TOKEN = re.compile(r"(?<![A-Za-z0-9])(O-O-O|O-O|[KQRBN][a-h]?[1-8]?x?[a-h][1-8][+#]?|[a-h]x[a-h][1-8](?:=[QRBN])?[+#]?|[a-h][18]=[QRBN][+#]?)")
_PUSH_TOKEN = re.compile(r"\b(?:play|played|plays|move|try|consider|prefers?|choose[s]?|chose)\s+([a-h][1-8])\b", re.I)
_CP = re.compile(r"(-?\d+)\s*(?:centipawns?|cp)\b")
_MAGNUS_CLAIM = re.compile(r"\bMagnus\b[^.\n]{0,40}\b(?:played|plays|chose|used|preferred|went for)\b", re.I)


def _norm(san: str) -> str:
    return san.replace("+", "").replace("#", "")


def allowed_facts(evidence: Dict[str, Any]) -> Dict[str, Set]:
    """Everything a text is allowed to mention, extracted from the evidence itself."""
    sans: Set[str] = set()
    cps: Set[int] = set()
    mates: Set[int] = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("san", "move_san", "move", "best_reply") and isinstance(v, str):
                    sans.add(_norm(v))
                if k in ("pv_san", "principal_variation_san", "principal_variation_after_user_move_san", "line_san", "line") and isinstance(v, list):
                    sans.update(_norm(s) for s in v if isinstance(s, str))
                if k == "value_cp" and isinstance(v, (int, float)):
                    cps.add(int(v))
                if k == "mate" and isinstance(v, int):
                    mates.add(abs(v))
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(evidence)
    fen = evidence.get("position", {}).get("fen") or evidence.get("fen")
    if fen:
        b = chess.Board(fen)
        sans.update(_norm(b.san(m)) for m in b.legal_moves)
    for h in evidence.get("comparison", {}).get("historical", {}).get("examples", []) if isinstance(evidence.get("comparison"), dict) and evidence["comparison"].get("historical") else []:
        sans.update(_norm(m["san"]) for m in h["surrounding_moves"])
    if evidence.get("comparison"):
        e = evidence["comparison"]["engine"]
        cps.add(e["evaluation_delta_cp"])
        for v in (e["evaluation_before"]["value_cp"], e["evaluation_after_user_move"]["value_cp"]):
            cps.add(v)
    n_hist = 0
    if isinstance(evidence.get("comparison"), dict) and evidence["comparison"].get("historical"):
        n_hist = len(evidence["comparison"]["historical"]["examples"])
    return {"sans": sans, "cps": cps, "mates": mates, "n_historical": n_hist}


def verify_grounding(text: str, evidence: Dict[str, Any], extra_sans: Optional[List[str]] = None) -> Dict[str, Any]:
    facts = allowed_facts(evidence)
    sans = set(facts["sans"]) | {_norm(s) for s in (extra_sans or [])}
    found = [_norm(m) for m in _SAN_TOKEN.findall(text)] + [m.lower() for m in _PUSH_TOKEN.findall(text)]
    # bare pawn pushes named after a move verb are checked as SAN pawn moves
    bad_moves = sorted({m for m in found if m not in sans})
    bad_numbers = sorted({int(n) for n in _CP.findall(text) if not any(abs(int(n) - c) <= 1 for c in facts["cps"])})
    bad_mates = sorted({int(n) for n in re.findall(r"mate in (\d+)", text, re.I) if int(n) not in facts["mates"]})
    magnus_bad = bool(_MAGNUS_CLAIM.search(text)) and facts["n_historical"] == 0
    return {"grounded": not (bad_moves or bad_numbers or bad_mates or magnus_bad), "unsupported_moves": bad_moves,
            "unsupported_numbers": bad_numbers, "unsupported_mates": bad_mates, "magnus_claim_without_evidence": magnus_bad,
            "moves_checked": len(found)}


# ------------------------------------------------------------------ payload
def build_llm_payload(evidence: Dict[str, Any], weaknesses: Optional[list] = None, mode: str = "analysis",
                      knowledge: Optional[list] = None) -> Dict[str, Any]:
    """The ONLY thing a language model gets to see."""
    comp = evidence["comparison"]
    return {
        "mode": mode,
        "position": {"fen": evidence["position"]["fen"], "legal_moves_uci": evidence["position"]["legal_moves_uci"]},
        "user_move": evidence["user_move"], "classification": evidence["classification"]["label"],
        "engine_truth": {"best_move": comp["engine"]["best_move"], "top_lines": comp["engine"]["top_lines"],
                         "evaluation_before": comp["engine"]["evaluation_before"],
                         "evaluation_after_user_move": comp["engine"]["evaluation_after_user_move"],
                         "principal_variation_after_user_move_san": comp["engine"]["principal_variation_after_user_move_san"],
                         "opponent_best_reply": comp["engine"]["opponent_best_reply"]},
        "magnus_model": comp["magnus_model"],
        "historical_evidence": {"examples": comp["historical"]["examples"] if comp["historical"] else []},
        "tactical_findings": {"motifs": evidence["motifs"], "opponent_reply": evidence["opponent_reply"],
                              "new_own_pieces_hanging": evidence["changes"]["new_own_pieces_hanging"],
                              "missed_opportunities": evidence["missed_opportunities"], "mistake_category": evidence["mistake_category"]},
        "consequence_chain": evidence["consequence_chain"],
        "player_weaknesses": weaknesses or [], "knowledge": [k.to_dict() if hasattr(k, "to_dict") else k for k in (knowledge or [])],
    }


# ------------------------------------------------------------------ providers
class LLMProvider(ABC):
    name = "provider"
    is_llm = True

    @abstractmethod
    def generate(self, system: str, payload: Dict[str, Any]) -> str: ...


class TemplateProvider(LLMProvider):
    """Deterministic renderer of the evidence. Not a language model."""
    name, is_llm = "template", False

    _LESSON_Q = {"tactical": "Before each move, list the opponent's checks, captures and threats.",
                 "opening": "Ask whether the move helps development, the centre or king safety.",
                 "endgame": "Ask which move activates your king and rooks.",
                 "calculation": "Verify the forcing line to its end before committing.",
                 "positional": "Ask which of your pieces is least active and how your move changes the pawn structure."}

    def generate(self, system: str, payload: Dict[str, Any]) -> str:
        p, mode = payload, payload["mode"]
        u, cls = p["user_move"]["san"], p["classification"]
        lines: List[str] = []
        e0, e1 = p["engine_truth"]["evaluation_before"], p["engine_truth"]["evaluation_after_user_move"]
        if mode == "socratic":
            for c in p["consequence_chain"][:0]:
                pass
            return "Before I show the answer: what changed for your own pieces after your move, and what is your opponent's most forcing reply?"
        lines.append(f"YOUR MOVE: {u} ({cls}). Engine evaluation for you: {e0['value_cp']} centipawns before, {e1['value_cp']} after.")
        lines.append("")
        lines.append("WHAT THE EVIDENCE SHOWS:")
        for c in p["consequence_chain"]:
            if c["source"] in ("engine", "board"):
                lines.append(f"- [{c['source']}] {c['claim']}")
        best = p["engine_truth"]["best_move"]
        if best["san"] != u and mode != "why_good":
            line = " ".join(p["engine_truth"]["top_lines"][0]["pv_san"][:6])
            lines += ["", f"STRONGER ALTERNATIVE (engine): {best['san']}. Line: {line}."]
        mm = p["magnus_model"]
        lines += ["", "MAGNUS MODEL (imitation of historical choices, not move quality): "
                  f"your move is ranked #{mm['user_move']['rank']}; its top choice is {mm['candidates'][0]['san']} "
                  f"({mm['candidates'][0]['probability']:.1%})."]
        ex = p["historical_evidence"]["examples"]
        if ex:
            top = ex[0]
            g = top["historical_game"]
            lines += ["", f"HISTORICAL MAGNUS EVIDENCE: in a similar stored position (similarity {top['similarity']['score']:.2f}, approximate) "
                          f"Magnus played {top['historical_move']['san']} against {g['opponent']} ({g['event']}, {g['date']}). "
                          "This shows what he did there, not that it was best."]
        else:
            lines += ["", "HISTORICAL MAGNUS EVIDENCE: none retrieved for this position."]
        cat = p["tactical_findings"]["mistake_category"]
        for k in p["knowledge"][:1]:
            lines += ["", f"CONCEPT ({k['title']}): {k['text']}  [source: {k['provenance']['type']}, {k['provenance']['author']}]"]
        if cat:
            lines += ["", f"NEXT TIME: {self._LESSON_Q.get(cat, self._LESSON_Q['positional'])}"]
        if p["player_weaknesses"]:
            w = p["player_weaknesses"][0]
            lines += [f"PATTERN IN YOUR GAMES: '{w['concept']}' appears in {w['count']} of your analysed mistakes."]
        return "\n".join(lines)


class AnthropicProvider(LLMProvider):
    """Optional real LLM. Requires `pip install anthropic` and ANTHROPIC_API_KEY. Not used by default."""
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 700):
        self.model, self.max_tokens = model, max_tokens

    def generate(self, system: str, payload: Dict[str, Any]) -> str:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        import anthropic  # imported lazily so the package works without it
        client = anthropic.Anthropic()
        msg = client.messages.create(model=self.model, max_tokens=self.max_tokens, system=system,
                                     messages=[{"role": "user", "content": json.dumps(payload)}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


class CoachLLM:
    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or TemplateProvider()
        self.fallback = TemplateProvider()

    def explain(self, evidence: Dict[str, Any], mode: str = "analysis", weaknesses=None, knowledge=None,
                extra_sans: Optional[List[str]] = None) -> Dict[str, Any]:
        payload = build_llm_payload(evidence, weaknesses, mode, knowledge)
        used, fallback, err = self.provider, False, None
        try:
            text = used.generate(SYSTEM_PROMPT, payload)
        except Exception as e:  # provider failure must never break the coach
            text, err = None, f"{type(e).__name__}: {e}"
        g = verify_grounding(text, evidence, extra_sans) if text else None
        if text is None or not g["grounded"]:
            failed = g
            text = self.fallback.generate(SYSTEM_PROMPT, payload)
            g, fallback, used = verify_grounding(text, evidence, extra_sans), True, self.fallback
            return {"text": text, "provider": used.name, "is_llm": used.is_llm, "mode": mode, "grounding": g, "fallback_used": True,
                    "rejected_output_grounding": failed, "provider_error": err}
        return {"text": text, "provider": used.name, "is_llm": used.is_llm, "mode": mode, "grounding": g, "fallback_used": False,
                "rejected_output_grounding": None, "provider_error": None}
