"""Visual annotation schema (Phase 21). UI-framework independent, JSON only.

    {"type":"arrow","from":"e2","to":"e4","category":"best-move","fen":"<position it refers to>","source":"engine","reason":"..."}
    {"type":"highlight","square":"e5","category":"threat","fen":"...","source":"board","reason":"..."}

Every annotation names the FEN it refers to and is validated against that
board: arrows for best-move/user-move must be legal moves there, capture arrows
must land on an enemy piece, threat/defended-square arrows must follow real
attack geometry. Annotations are built from evidence, never from free text.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

import chess

CATEGORIES = ("best-move", "user-move", "mistake", "threat", "capture", "defended-square", "target", "escape")
ARROW_CATEGORIES = ("best-move", "user-move", "mistake", "threat", "capture", "defended-square", "escape")
HIGHLIGHT_CATEGORIES = ("mistake", "threat", "capture", "defended-square", "target", "escape", "best-move", "user-move")
SOURCES = ("engine", "board", "user", "history", "model")


def arrow(frm: str, to: str, category: str, fen: str, source: str, reason: str = "") -> Dict[str, Any]:
    a = {"type": "arrow", "from": frm, "to": to, "category": category, "fen": fen, "source": source, "reason": reason}
    _basic(a)
    return a


def highlight(square: str, category: str, fen: str, source: str, reason: str = "") -> Dict[str, Any]:
    a = {"type": "highlight", "square": square, "category": category, "fen": fen, "source": source, "reason": reason}
    _basic(a)
    return a


def _basic(a: Dict[str, Any]):
    if a.get("type") not in ("arrow", "highlight"):
        raise ValueError(f"unknown annotation type {a.get('type')!r}")
    if a["category"] not in CATEGORIES:
        raise ValueError(f"unknown category {a['category']!r}")
    if a["source"] not in SOURCES:
        raise ValueError(f"unknown source {a['source']!r}")
    for k in (("from", "to") if a["type"] == "arrow" else ("square",)):
        chess.parse_square(a[k])           # raises ValueError on a bad square
    chess.Board(a["fen"])


def problems(a: Dict[str, Any]) -> List[str]:
    """Reasons an annotation is NOT supported by its board ([] = valid)."""
    try:
        _basic(a)
    except ValueError as e:
        return [str(e)]
    b = chess.Board(a["fen"])
    out = []
    if a["type"] == "arrow":
        f, t = chess.parse_square(a["from"]), chess.parse_square(a["to"])
        p, c = a["category"], b.piece_at(f)
        if f == t:
            out.append("arrow from == to")
        if p in ("best-move", "user-move"):
            promo = [m for m in b.legal_moves if m.from_square == f and m.to_square == t]
            if not promo:
                out.append(f"{a['from']}{a['to']} is not a legal move in the referenced position")
        elif p == "capture":
            if c is None or (b.piece_at(t) is None or b.piece_at(t).color == c.color):
                if not (c and c.piece_type == chess.PAWN and t == b.ep_square):
                    out.append("capture arrow does not end on an enemy piece")
        elif p in ("threat", "mistake"):
            if c is None:
                out.append("arrow starts on an empty square")
            elif t not in b.attacks(f) and not any(m.from_square == f and m.to_square == t for m in
                                                    _pseudo(b, c.color)):
                out.append("threat/mistake arrow does not follow an attack or move of that piece")
        elif p in ("defended-square", "escape"):
            if c is None:
                out.append("arrow starts on an empty square")
            elif t not in b.attacks(f) and not any(m.from_square == f and m.to_square == t for m in _pseudo(b, c.color)):
                out.append("defence/escape arrow is not reachable by that piece")
    else:
        if a["category"] in ("capture", "target") and b.piece_at(chess.parse_square(a["square"])) is None:
            out.append(f"{a['category']} highlight is on an empty square")
    return out


def _pseudo(b: chess.Board, color: bool):
    c = b.copy(stack=False)
    c.turn = color
    return list(c.generate_pseudo_legal_moves())


def validate_annotations(annots: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    bad = [{"annotation": a, "problems": p} for a in annots if (p := problems(a))]
    return {"valid": not bad, "invalid": bad}


def dedupe(annots: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for a in annots:
        key = (a["type"], a.get("from"), a.get("to"), a.get("square"), a["category"], a["fen"])
        if key not in seen:
            seen.add(key)
            out.append(a)
    return out


def from_tactic(t: Dict[str, Any], fen: str, source: str = "board") -> List[Dict[str, Any]]:
    """Annotations for one tactics.py finding, on the position `fen` the finding was computed on."""
    out = []
    if t.get("trigger_move"):
        m = chess.Move.from_uci(t["trigger_move"])
        cat = "capture" if chess.Board(fen).is_capture(m) else "threat"
        out.append(arrow(chess.square_name(m.from_square), chess.square_name(m.to_square), cat, fen, source, t["consequence"]))
    for sqn in t.get("target_squares", []):
        out.append(highlight(sqn, "target", fen, source, t["motif"]))
    return out
