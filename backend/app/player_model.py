"""Tracks per-concept accuracy from Attempt rows and decides when a review
detour is warranted (spec §41, §42, §43). Pure SQL + arithmetic — no
external service dependency, genuinely testable.
"""
from __future__ import annotations
from sqlmodel import Session, select

from app.db import models as db

REVIEW_THRESHOLD = 0.6  # below this accuracy on a concept, trigger a detour
MIN_ATTEMPTS_BEFORE_JUDGING = 2


class PlayerModel:
    def __init__(self, session: Session, user_id: str):
        self.session = session
        self.user_id = user_id

    def concept_accuracy(self, concept_id: str) -> float | None:
        stmt = select(db.Attempt).where(
            db.Attempt.user_id == self.user_id, db.Attempt.concept_id == concept_id
        )
        attempts = list(self.session.exec(stmt))
        if len(attempts) < MIN_ATTEMPTS_BEFORE_JUDGING:
            return None
        correct = sum(1 for a in attempts if a.result == "correct")
        return correct / len(attempts)

    def weakest_concept_in_section(self, section_id: str) -> str | None:
        """Returns a concept name below threshold among concepts tied to
        lessons in this section, or None. Real implementation needs a
        Lesson->Concept link table populated during ingestion (§6 step 21-24)
        — left as a query stub since that link table isn't in this minimal
        db/models.py yet.
        """
        return None

    def repeated_mistakes(self) -> list[str]:
        """Concept ids where the user has multiple 'incorrect' attempts —
        used to drive retest scheduling (§43)."""
        stmt = select(db.Attempt).where(
            db.Attempt.user_id == self.user_id, db.Attempt.result == "incorrect"
        )
        attempts = list(self.session.exec(stmt))
        counts: dict[str, int] = {}
        for a in attempts:
            if a.concept_id:
                counts[a.concept_id] = counts.get(a.concept_id, 0) + 1
        return [cid for cid, n in counts.items() if n >= 2]
