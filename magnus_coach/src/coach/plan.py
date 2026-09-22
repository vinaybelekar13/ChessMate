"""Challenge My Idea (Phase 18) and Socratic coaching (Phase 19).

challenge_plan simulates the user's plan against the engine's best replies and
reports ONLY facts from board calculation, Stockfish and the historical
database. The verdict is a rule over measured win-probability loss.
Socratic hints are built from the same evidence and are leak-checked: in
hint-only mode nothing that reveals the engine's best move may appear.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import chess

from src.chess_core import tactics as T
from src.engine.stockfish import win_pct
from .compare import parse_move
from .evidence import FORCING_MOTIFS, non_pawn_material
from .services import Services

SAN_RE = re.compile(r"\b(O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)")
INTENT_KEYWORDS = {"kingside_attack": ("kingside attack", "attack the kingside", "attack on the kingside", "attack the king", "pawn storm"),
                   "queenside_expansion": ("queenside",), "central_break": ("center", "centre", "break"),
                   "simplify": ("simplify", "trade", "exchange", "swap"), "castle": ("castle",),
                   "develop": ("develop",), "win_material": ("win a pawn", "win the pawn", "win material", "capture")}


def parse_plan(board: chess.Board, text: str) -> Dict[str, Any]:
    """Extract intent tags and the ordered candidate moves named in the text.

    Moves are matched as SAN tokens; only tokens that are legal for the side to move at
    that point of the simulation are used later. Free-text intent is only tagged by keywords.
    """
    low = text.lower()
    intents = [k for k, kws in INTENT_KEYWORDS.items() if any(w in low for w in kws)]
    tokens = [m.group(1) for m in SAN_RE.finditer(text) if len(m.group(1)) >= 2 or m.group(1) in ("O-O",)]
    return {"text": text, "intents": intents, "candidate_moves": tokens}


def king_shield(board: chess.Board, color: bool) -> int:
    k = board.king(color)
    if k is None:
        return 0
    step = 1 if color == chess.WHITE else -1
    n = 0
    for f in (chess.square_file(k) - 1, chess.square_file(k), chess.square_file(k) + 1):
        for dr in (1, 2):
            r = chess.square_rank(k) + step * dr
            if 0 <= f < 8 and 0 <= r < 8:
                p = board.piece_at(chess.square(f, r))
                if p and p.color == color and p.piece_type == chess.PAWN:
                    n += 1
    return n


def pawn_structure(board: chess.Board, color: bool) -> Dict[str, int]:
    files = [chess.square_file(s) for s in board.pieces(chess.PAWN, color)]
    doubled = sum(files.count(f) - 1 for f in set(files) if files.count(f) > 1)
    isolated = sum(1 for f in files if (f - 1) not in files and (f + 1) not in files)
    return {"doubled": doubled, "isolated": isolated, "pawns": len(files)}


def undeveloped_minor_pieces(board: chess.Board, color: bool) -> int:
    home = (chess.B1, chess.G1, chess.C1, chess.F1) if color == chess.WHITE else (chess.B8, chess.G8, chess.C8, chess.F8)
    return sum(1 for s in home if board.piece_type_at(s) in (chess.KNIGHT, chess.BISHOP) and board.color_at(s) == color)


def challenge_plan(fen: str, plan: str, services: Services, depth: Optional[int] = None, max_steps: int = 4) -> Dict[str, Any]:
    board = chess.Board(fen)
    mover = board.turn
    eng = services.engine
    parsed = parse_plan(board, plan)
    root = eng.analyze(fen, depth)
    if root["game_over"]:
        raise ValueError("game is already over")
    root_eval = root["evaluation"]

    steps, cur, unplayable = [], board.copy(stack=False), []
    for token in parsed["candidate_moves"]:
        if len(steps) >= max_steps:
            break
        # the plan move must be playable now; if not, try after the engine's best reply (opponent moves in between)
        try:
            mv = parse_move(cur, token)
        except ValueError:
            unplayable.append({"token": token, "fen": cur.fen(), "reason": "not a legal move for the side to move at that point"})
            continue
        if cur.turn != mover:
            continue
        before_shield, before_ps, before_hang = king_shield(cur, mover), pawn_structure(cur, mover), len(T.hanging_pieces(cur, mover))
        after = T.tactics_after_move(cur, mv)
        ev = eng.evaluate_move(cur.fen(), mv.uci(), depth)
        nb = chess.Board(after["fen_after"])
        step = {"move": {"uci": mv.uci(), "san": cur.san(mv)}, "fen_before": cur.fen(), "fen_after": nb.fen(),
                "eval_for_mover": ev["score_for_mover"], "engine_best_reply": ev["best_reply"],
                "engine_line_san": ev["principal_variation_san"][:6],
                "king_shield_before": before_shield, "king_shield_after": king_shield(nb, mover),
                "own_pawn_structure_before": before_ps, "own_pawn_structure_after": pawn_structure(nb, mover),
                "own_hanging_before": before_hang, "own_hanging_after": after["own_pieces_hanging_after"],
                "opponent_opportunities": after["opponent_opportunities"]}
        steps.append(step)
        cur = nb
        if ev["best_reply"] and not ev["game_over"]:      # engine plays the opponent's best reply, then plan continues
            cur.push(chess.Move.from_uci(ev["best_reply"]["uci"]))

    best = root["lines"][0]
    best_after = root_eval["win_pct"]
    if steps:
        worst = min(s["eval_for_mover"]["win_pct"] for s in steps)
        final = steps[-1]["eval_for_mover"]["win_pct"]
        loss = max(0.0, best_after - min(final, worst))
    else:
        loss = None

    supporting, weaknesses, opp_res, refutations, positional = [], [], [], [], []
    rank_of_first = None
    if steps:
        first = steps[0]["move"]["uci"]
        rank_of_first = next((l["rank"] for l in root["lines"] if l["move_uci"] == first), None)
        if rank_of_first:
            supporting.append({"fact": f"{steps[0]['move']['san']} is engine choice #{rank_of_first} of {len(root['lines'])} at depth {root['depth']}", "source": "engine"})
        if all(s["eval_for_mover"]["win_pct"] >= root_eval["win_pct"] - 5 for s in steps):
            supporting.append({"fact": "engine evaluation stays within 5 win-probability points of the best line throughout the simulated plan", "source": "engine"})
        for s in steps:
            if s["own_hanging_after"]:
                for h in s["own_hanging_after"]:
                    weaknesses.append({"fact": f"after {s['move']['san']}, {h['attacked_piece']} on {h['target_squares'][0]} can be won by exchange", "source": "board", "step": s["move"]["san"]})
            if s["king_shield_after"] < s["king_shield_before"]:
                positional.append({"fact": f"{s['move']['san']} reduces your king's pawn shield from {s['king_shield_before']} to {s['king_shield_after']} pawns", "source": "board", "step": s["move"]["san"]})
            ps0, ps1 = s["own_pawn_structure_before"], s["own_pawn_structure_after"]
            if ps1["doubled"] > ps0["doubled"] or ps1["isolated"] > ps0["isolated"]:
                positional.append({"fact": f"{s['move']['san']} creates pawn-structure weaknesses (doubled {ps0['doubled']}->{ps1['doubled']}, isolated {ps0['isolated']}->{ps1['isolated']})", "source": "board", "step": s["move"]["san"]})
            if s["engine_best_reply"]:
                opp_res.append({"after": s["move"]["san"], "best_reply": s["engine_best_reply"]["san"], "line": s["engine_line_san"], "source": "engine"})
            for o in s["opponent_opportunities"]:
                if o["motif"] in FORCING_MOTIFS:
                    refutations.append({"after": s["move"]["san"], "motif": o["motif"], "reply": o["trigger_move"], "detail": o["consequence"], "source": "board"})
        if "kingside_attack" in parsed["intents"]:
            ek = board.king(not mover)
            if ek is not None and chess.square_file(ek) < 3:
                weaknesses.append({"fact": f"the plan is a kingside attack but the opponent king is on {chess.square_name(ek)}, on the queenside", "source": "board"})
            elif ek is not None and any(chess.square_file(ek) >= 5 for _ in [0]):
                supporting.append({"fact": f"opponent king is on {chess.square_name(ek)}, on the side the plan attacks", "source": "board"})
            if board.fullmove_number <= 12 and undeveloped_minor_pieces(board, mover) >= 2:
                positional.append({"fact": f"{undeveloped_minor_pieces(board, mover)} of your minor pieces are undeveloped while the plan starts a pawn attack", "source": "board"})
        if non_pawn_material(board) <= 24 and "kingside_attack" in parsed["intents"]:
            positional.append({"fact": "material is reduced (endgame by the project's definition); a pawn storm carries less attacking material", "source": "board"})
        if services.db is not None:
            from src.history.evidence import historical_examples
            ex = historical_examples(fen, services.db, 10)
            hits = sum(1 for e in ex if e["historical_move"]["in_query_frame"] == steps[0]["move"]["uci"])
            supporting.append({"fact": f"{hits} of {len(ex)} similar stored Magnus positions feature {steps[0]['move']['san']} (approximate similarity)", "source": "history"}) if hits else None
    else:
        weaknesses.append({"fact": "no move in the plan text is playable in the position, so the plan cannot be evaluated as written", "source": "board"})

    if not steps:
        verdict = "not_playable"
    elif loss <= 5 and not refutations:
        verdict = "supported"
    elif loss <= 15:
        verdict = "questionable"
    else:
        verdict = "contradicted"
    n_against = len(weaknesses) + len(refutations) + len(positional)
    depth_used = root["depth"]
    confidence = {"level": ("low" if depth_used < 10 or not steps else "high" if (loss is not None and (loss > 25 or (loss <= 2 and n_against == 0))) else "medium"),
                  "basis": f"engine depth {depth_used}; measured win-probability loss {None if loss is None else round(loss, 2)}; {n_against} contradicting facts"}
    return {
        "kind": "plan_challenge", "fen": board.fen(), "proposed_plan": parsed["text"], "parsed": parsed,
        "verdict": verdict, "challenged": verdict != "supported",
        "supporting_factors": supporting, "weaknesses": weaknesses, "opponent_resources": opp_res,
        "tactical_refutations": refutations, "positional_concerns": positional,
        "unplayable_plan_tokens": unplayable,
        "alternative_plan": {"engine_best_move": best["move_san"], "line_san": best["pv_san"][:6], "eval": best["score"], "source": "engine"},
        "evaluation_trajectory": [{"after": s["move"]["san"], "eval_for_mover": s["eval_for_mover"]} for s in steps],
        "engine_root_evaluation": root_eval, "win_pct_loss": None if loss is None else round(loss, 3),
        "confidence": confidence, "steps": steps,
        "evidence_sources": {"engine": "evaluation_trajectory/alternative_plan/opponent_resources", "board": "weaknesses/positional_concerns/tactical_refutations",
                             "history": "supporting_factors[source=history]"},
    }


# ---------------------------------------------------------------------------------- Socratic
HINT_LEVELS = ("hint_1", "hint_2", "stronger_hint", "reveal")


def _leaks(text: str, evidence: dict) -> bool:
    """True if `text` reveals the engine's best move (SAN, UCI, or its destination square)."""
    best = evidence["comparison"]["engine"]["best_move"]
    fen = evidence["position"]["fen"]
    mv = chess.Move.from_uci(best["uci"])
    san = best["san"].rstrip("+#")
    tl = text.replace("+", "").replace("#", "")
    to_sq, frm_sq = chess.square_name(mv.to_square), chess.square_name(mv.from_square)
    return san in tl or best["uci"] in text or (to_sq in text and frm_sq in text) or (
        bool(re.search(rf"\b{re.escape(to_sq)}\b", text)) and evidence["user_move"]["uci"][2:4] != to_sq)


def build_hints(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Progressive, evidence-based hints. hint_1/2/stronger never contain the best move."""
    board = chess.Board(evidence["position"]["fen"])
    best = chess.Move.from_uci(evidence["comparison"]["engine"]["best_move"]["uci"])
    bp = board.piece_at(best.from_square)
    piece_name = chess.piece_name(bp.piece_type)
    reply = evidence.get("opponent_reply")
    new_h = evidence["changes"]["new_own_pieces_hanging"]
    missed = evidence["missed_opportunities"]
    label = evidence["classification"]["label"]
    h: Dict[str, Dict[str, str]] = {}
    if missed:
        m = missed[0]
        h["hint_1"] = {"text": "Look at your opponent's king. How many safe squares does it really have?", "basis": "missed_opportunities"}
        h["hint_2"] = {"text": "Which of your pieces could give a check right now, and can the king step out of it?", "basis": f"missed_opportunities[{m['motif']}]"}
        h["stronger_hint"] = {"text": f"A forcing move with your {chess.piece_name(board.piece_type_at(chess.parse_square(m['source_square']))) if board.piece_type_at(chess.parse_square(m['source_square'])) else 'piece'} wins on the spot.", "basis": "missed_opportunities.source_square"}
    elif new_h:
        x = new_h[0]
        h["hint_1"] = {"text": "What changed for your own pieces after this move? Is everything still protected?", "basis": "changes.new_own_pieces_hanging"}
        h["hint_2"] = {"text": "One of your pieces can now be captured by an opponent piece. Which of them is not adequately defended?", "basis": "changes.new_own_pieces_hanging"}
        h["stronger_hint"] = {"text": f"Check the {x['attacked_piece'].upper() if x['attacked_piece'].isupper() else x['attacked_piece']} on {x['target_squares'][0]}: count its attackers and defenders.", "basis": "changes.new_own_pieces_hanging[0]"}
    else:
        h["hint_1"] = {"text": "What is your opponent threatening after your move? What is their most forcing reply?", "basis": "opponent_reply"}
        kind = "capture" if reply and reply["is_capture"] else "check" if reply and reply["gives_check"] else "quiet move"
        h["hint_2"] = {"text": f"The engine's most testing reply is a {kind}. Which of your pieces or squares does it target?" if reply else "Which of your pieces is doing a defensive job that your move abandons?", "basis": "opponent_reply"}
        h["stronger_hint"] = {"text": f"A better move exists with your {piece_name}. Which {piece_name} move keeps your position safest?", "basis": "comparison.engine.best_move.piece_type"}
    generic = {"hint_1": "Before moving, ask what your opponent can do in reply.",
               "hint_2": "Check whether each of your pieces is still protected after your move.",
               "stronger_hint": "Compare your move with a safer alternative with the same piece type."}
    for k in ("hint_1", "hint_2", "stronger_hint"):
        if _leaks(h[k]["text"], evidence):     # never reveal the answer: fall back to a generic, non-specific hint
            h[k] = {"text": generic[k], "basis": "generic (specific hint withheld: it would have revealed the best move)"}
    best_line = evidence["comparison"]["engine"]["top_lines"][0]
    h["reveal"] = {"text": f"Best move: {best_line['move_san']}. Line: {' '.join(best_line['pv_san'][:6])}. Then read the consequence chain.",
                   "basis": "comparison.engine.top_lines[0]"}
    return h


class SocraticSession:
    def __init__(self, evidence: Dict[str, Any], hint_only: bool = False):
        self.evidence, self.hint_only = evidence, hint_only
        self._hints = build_hints(evidence)
        self.level = 0
        self.revealed = False

    def next_hint(self) -> Dict[str, Any]:
        """Advance one level. In hint_only mode the reveal level is refused."""
        if self.level >= len(HINT_LEVELS):
            return {"level": None, "text": None, "exhausted": True, "revealed": self.revealed}
        name = HINT_LEVELS[self.level]
        if name == "reveal" and self.hint_only:
            return {"level": name, "text": None, "revealed": False, "refused": True,
                    "reason": "hint-only mode: the answer is not revealed"}
        self.level += 1
        h = self._hints[name]
        if name == "reveal":
            self.revealed = True
        return {"level": name, **h, "revealed": self.revealed}

    def reveal(self) -> Dict[str, Any]:
        if self.hint_only:
            return {"level": "reveal", "text": None, "revealed": False, "refused": True, "reason": "hint-only mode: the answer is not revealed"}
        self.level, self.revealed = len(HINT_LEVELS), True
        return {"level": "reveal", **self._hints["reveal"], "revealed": True}
