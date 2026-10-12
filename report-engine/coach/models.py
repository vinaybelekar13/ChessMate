from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MoveClassification:
    label: str
    cp_loss: Optional[float] = None
    eval_before: Optional[float] = None
    eval_after: Optional[float] = None
    confidence: float = 1.0


@dataclass
class CoachContext:
    game_id: Optional[int] = None
    ply: Optional[int] = None

    fen_before: Optional[str] = None
    fen_after: Optional[str] = None

    san: Optional[str] = None
    uci: Optional[str] = None

    color: Optional[str] = None
    move_number: Optional[int] = None
    phase: Optional[str] = None

    evaluation_before: Optional[float] = None
    evaluation_after: Optional[float] = None
    best_move: Optional[str] = None

    side_to_move: Optional[str] = None

    motifs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Consequence:
    category: str
    description: str
    severity: str = "normal"

    immediate: Optional[str] = None
    follow_up: Optional[str] = None
    opponent_threat: Optional[str] = None


@dataclass
class ChessReasoning:
    primary_reason: str

    tactical_effect: Optional[str] = None
    strategic_effect: Optional[str] = None
    practical_effect: Optional[str] = None

    missed_resource: Optional[str] = None
    better_move: Optional[str] = None
    better_move_reason: Optional[str] = None

    candidate_comparison: list[str] = field(default_factory=list)


@dataclass
class CoachExplanation:
    headline: str
    summary: str

    what_you_played: Optional[str] = None
    why_it_is_wrong: Optional[str] = None
    what_you_missed: Optional[str] = None
    immediate_effect: Optional[str] = None
    better_move: Optional[str] = None
    why_better: Optional[str] = None
    longer_term_effect: Optional[str] = None
    lesson: Optional[str] = None

    details: list[str] = field(default_factory=list)


@dataclass
class CoachAnalysis:
    context: CoachContext
    classification: MoveClassification
    consequence: Optional[Consequence] = None
    reasoning: Optional[ChessReasoning] = None
    explanation: Optional[CoachExplanation] = None

    motifs: list[dict[str, Any]] = field(default_factory=list)
    similar_mistakes: list[dict[str, Any]] = field(default_factory=list)
