from __future__ import annotations

from typing import Optional

from analysis.classifier import (
    MoveClassification as CanonicalMoveClassification,
    classify_move as canonical_classify_move,
)

from coach.models import MoveClassification


def classify(
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
    ChessMate Coach adapter around the canonical Game Review classifier.

    IMPORTANT:
    The Coach Core does not maintain its own classification thresholds.
    analysis.classifier remains the single source of truth.
    """

    result: CanonicalMoveClassification = canonical_classify_move(
        color=color,
        best_move=best_move,
        played_move=played_move,
        cp_loss=cp_loss,
        loss=loss,
        second_best_loss_gap=second_best_loss_gap,
        sacrifice=sacrifice,
        material_before=material_before,
        eval_before=eval_before,
        eval_after=eval_after,
        is_book=is_book,
    )

    return MoveClassification(
        label=result.classification,
        cp_loss=result.cp_loss,
        eval_before=eval_before,
        eval_after=eval_after,
        confidence=1.0,
    )


def classify_from_result(result: CanonicalMoveClassification) -> MoveClassification:
    """
    Convert an already-computed canonical ChessMate classification
    into the Coach Core representation.
    """

    return MoveClassification(
        label=result.classification,
        cp_loss=result.cp_loss,
        confidence=1.0,
    )
