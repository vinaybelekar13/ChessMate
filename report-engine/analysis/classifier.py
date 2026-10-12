from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


MATE_CP = 100000

# Matches the existing browser review's engine-equivalent tolerance.
BEST_TOL_CP = 10

# Win-percentage loss thresholds used by the existing Game Review.
EXCELLENT_MAX_LOSS = 2.0
GOOD_MAX_LOSS = 5.0
INACCURACY_MAX_LOSS = 10.0
MISTAKE_MAX_LOSS = 20.0

# Brilliant-move rules from the existing Game Review.
SAC_MIN_GIVEN = 1.0
SAC_MIN_EVAL_AFTER = 0.0
SAC_MAX_EVAL_BEFORE = 300.0

# Great-move / only-move rule.
GREAT_MIN_GAP = 12.0
GREAT_MAX_LOSS = 2.0


@dataclass(frozen=True)
class MoveClassification:
    classification: str
    loss: float
    cp_loss: float
    is_best: bool
    is_brilliant: bool
    is_great: bool
    only_move_gap: Optional[float] = None
    sacrifice_given: Optional[float] = None


def win_pct(cp: float) -> float:
    """
    Exact win-percentage curve used by the existing browser review.
    """
    cp = float(cp)
    return 50.0 + 50.0 * (
        2.0 / (1.0 + math.exp(-0.00368208 * cp)) - 1.0
    )


def mover_score(
    eval_cp: Optional[float],
    color: str,
    mate: Optional[int] = None,
) -> Optional[float]:
    """
    Convert an engine evaluation from White POV to the moving player's POV.

    Mate scores are represented using the same saturated scale already used
    by ChessMate's Python analyzer.
    """
    if mate is not None:
        score = MATE_CP if mate > 0 else -MATE_CP
    elif eval_cp is not None:
        score = float(eval_cp)
    else:
        return None

    return score if color == "w" else -score


def mate_aware_cp_loss(
    before_cp: Optional[float],
    after_cp: Optional[float],
    before_mate: Optional[int],
    after_mate: Optional[int],
    color: str,
) -> Optional[float]:
    """
    Calculate raw centipawn loss from the mover's perspective while preserving
    ChessMate's existing mate semantics.
    """
    if before_cp is None and before_mate is None:
        return None

    if after_cp is None and after_mate is None:
        return None

    if before_mate is not None:
        before_mover_mate = (
            before_mate if color == "w" else -before_mate
        )
    else:
        before_mover_mate = None

    if after_mate is not None:
        after_mover_mate = (
            after_mate if color == "w" else -after_mate
        )
    else:
        after_mover_mate = None

    # Already having a forced mate and retaining it is not a loss.
    if (
        before_mover_mate is not None
        and before_mover_mate > 0
        and after_mover_mate is not None
        and after_mover_mate >= 0
    ):
        return 0.0

    # Already having a forced mate and retaining a forced mate.
    if (
        before_mover_mate is not None
        and before_mover_mate > 0
        and after_mover_mate is not None
        and after_mover_mate > 0
    ):
        return 0.0

    # A forced mate that disappears is catastrophic.
    if before_mover_mate is not None and before_mover_mate > 0:
        return float(MATE_CP)

    # Moving into an opponent-forced mate is catastrophic.
    if after_mover_mate is not None and after_mover_mate < 0:
        return float(MATE_CP)

    before = mover_score(before_cp, color)
    after = mover_score(after_cp, color)

    if before is None or after is None:
        return None

    return max(0.0, before - after)


def win_probability_loss(
    before_cp: Optional[float],
    after_cp: Optional[float],
    before_mate: Optional[int],
    after_mate: Optional[int],
    color: str,
) -> Optional[float]:
    """
    Convert the mover's evaluation change into win-percentage loss.

    This is the canonical metric used for move classification and accuracy.
    """
    before = mover_score(before_cp, color, before_mate)
    after = mover_score(after_cp, color, after_mate)

    if before is None or after is None:
        return None

    if before_mate is not None and before > 0:
        if after_mate is not None and after >= 0:
            return 0.0
        return 100.0

    if after_mate is not None and after < 0:
        return 100.0

    return max(
        0.0,
        win_pct(before) - win_pct(after),
    )


def classify_move(
    *,
    color: str,
    best_move: Optional[str],
    played_move: str,
    cp_loss: float,
    loss: float,
    second_best_loss_gap: Optional[float] = None,
    sacrifice: bool = False,
    material_before: float = 0.0,
    eval_before: Optional[float] = None,
    eval_after: Optional[float] = None,
    is_book: bool = False,
) -> MoveClassification:
    """
    Canonical ChessMate move classification.

    Ordering intentionally matches the existing Game Review:
        Book → Brilliant → Great → Best → Excellent → Good
        → Inaccuracy → Mistake → Blunder
    """
    if is_book:
        return MoveClassification(
            classification="book",
            loss=loss,
            cp_loss=cp_loss,
            is_best=False,
            is_brilliant=False,
            is_great=False,
        )

    is_best = cp_loss <= BEST_TOL_CP

    is_brilliant = (
        sacrifice
        and loss < 3.0
        and material_before > 3.0
        and eval_after is not None
        and eval_after >= SAC_MIN_EVAL_AFTER
        and eval_after < 9000
        and eval_before is not None
        and eval_before <= SAC_MAX_EVAL_BEFORE
    )

    is_great = (
        is_best
        and second_best_loss_gap is not None
        and second_best_loss_gap >= GREAT_MIN_GAP
        and loss < GREAT_MAX_LOSS
    )

    if is_brilliant:
        cls = "brilliant"
    elif is_great:
        cls = "great"
    elif is_best:
        cls = "best"
    elif loss < EXCELLENT_MAX_LOSS:
        cls = "excellent"
    elif loss < GOOD_MAX_LOSS:
        cls = "good"
    elif loss < INACCURACY_MAX_LOSS:
        cls = "inaccuracy"
    elif loss < MISTAKE_MAX_LOSS:
        cls = "mistake"
    else:
        cls = "blunder"

    return MoveClassification(
        classification=cls,
        loss=loss,
        cp_loss=cp_loss,
        is_best=is_best,
        is_brilliant=is_brilliant,
        is_great=is_great,
        only_move_gap=second_best_loss_gap if is_great else None,
    )


def accuracy_from_losses(losses: list[float]) -> float:
    """
    Exact accuracy curve used by the existing browser Game Review.
    """
    if not losses:
        return 100.0

    avg = sum(losses) / len(losses)

    accuracy = (
        103.1668 * math.exp(-0.04354 * avg) - 3.1669
    )

    return round(
        max(0.0, min(100.0, accuracy)),
        1,
    )
