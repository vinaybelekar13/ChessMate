"""Detects chess-specific content in extracted blocks (spec §13, §19, §46).

Puzzle/PGN text detection is pure regex/string logic and is genuinely
runnable/testable without external services. Diagram -> FEN reconstruction
needs a board-vision model this scaffold does not include (see the
NotImplementedError below) — per §46, when reconstruction isn't possible or
isn't confident, the diagram is kept and marked unverified rather than
guessed.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

from app.ingestion.mineru_adapter import RawBlock

PUZZLE_TRIGGER_PATTERNS = [
    re.compile(r"\bwhite to move\b", re.IGNORECASE),
    re.compile(r"\bblack to move\b", re.IGNORECASE),
    re.compile(r"\bfind the best move\b", re.IGNORECASE),
    re.compile(r"\bfind the continuation\b", re.IGNORECASE),
    re.compile(r"\bexercise\s*\d*\b", re.IGNORECASE),
    re.compile(r"\bpuzzle\s*\d*\b", re.IGNORECASE),
    re.compile(r"\btest yourself\b", re.IGNORECASE),
]

# Very rough SAN-move-sequence detector: "1.e4 e5 2.Nf3 ..." style text.
MOVE_TEXT_RE = re.compile(
    r"\d+\.\s*[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](=[QRBN])?[+#]?"
)


@dataclass
class PuzzleCandidate:
    block: RawBlock
    trigger_text: str


@dataclass
class DiagramCandidate:
    block: RawBlock


def find_puzzle_candidates(blocks: list[RawBlock]) -> list[PuzzleCandidate]:
    """Flags blocks whose text matches a known puzzle-prompt pattern.

    A candidate becomes a real `Puzzle` row only once it's been paired with a
    nearby diagram (usually the block immediately before or after it) during
    pipeline.py's linking step — a caption alone isn't enough to build an
    interactive puzzle.
    """
    found = []
    for b in blocks:
        if b.block_type in ("paragraph", "caption") and b.text:
            for pattern in PUZZLE_TRIGGER_PATTERNS:
                if pattern.search(b.text):
                    found.append(PuzzleCandidate(block=b, trigger_text=pattern.pattern))
                    break
    return found


def find_diagram_candidates(blocks: list[RawBlock]) -> list[DiagramCandidate]:
    return [DiagramCandidate(block=b) for b in blocks if b.block_type == "diagram"]


def find_move_text_blocks(blocks: list[RawBlock]) -> list[RawBlock]:
    """Blocks that look like annotated game/PGN text rather than prose."""
    out = []
    for b in blocks:
        if b.text and len(MOVE_TEXT_RE.findall(b.text)) >= 3:
            out.append(b)
    return out


def reconstruct_position_from_diagram(image_ref: str) -> tuple[str | None, float]:
    """Returns (fen_or_none, confidence).

    NOT IMPLEMENTED: this needs a trained board-recognition model (piece
    detection on a rasterized diagram crop) — genuinely out of scope for a
    scaffold with no network/model access. Wire in something like an
    open board-recognition model here, validate the result with
    `app.chess.validation.is_valid_fen`, and only return a FEN when
    confidence clears a threshold you're comfortable with (spec §46 is
    explicit: never invent a FEN when uncertain).
    """
    raise NotImplementedError(
        "Plug in a board-recognition model here. Until then, diagrams are "
        "stored with fen=None, verified=False, and the original image kept "
        "(see Position.raw_image_ref) — the frontend must render "
        "'Position requires verification' for those."
    )
