from __future__ import annotations

from coach.models import (
    ChessReasoning,
    CoachContext,
    CoachExplanation,
    Consequence,
    MoveClassification,
)


def _label_name(label: str) -> str:
    return (label or "unknown").replace("_", " ").strip().lower()


def _capitalize(text: str | None) -> str | None:
    if not text:
        return None

    return text[0].upper() + text[1:]


def _classification_headline(label: str) -> str:
    label = _label_name(label)

    headlines = {
        "blunder": "A serious mistake changed the position",
        "mistake": "This move gives the opponent an important improvement",
        "inaccuracy": "This move misses a more precise continuation",
        "good": "A solid move with room for improvement",
        "excellent": "A strong and accurate decision",
        "best": "The strongest move",
        "great": "A very strong decision",
        "brilliant": "A highly effective tactical decision",
        "book": "A known opening move",
    }

    return headlines.get(
        label,
        "The position needs a concrete explanation",
    )


def _played_move_sentence(
    context: CoachContext,
) -> str | None:
    if not context.san:
        return None

    if context.move_number is not None and context.color in ("w", "b"):
        if context.color == "w":
            return f"You played {context.move_number}. {context.san}."
        return f"You played {context.move_number}... {context.san}."

    return f"You played {context.san}."



def _concise_reason(reasoning: ChessReasoning) -> str | None:
    """Turn reasoning into a concise coaching diagnosis.

    Concrete tactical causes take priority over generic candidate
    comparison. Strategic reasoning is used when no tactical cause
    is available.
    """
    reason = (
        reasoning.tactical_effect
        or reasoning.primary_reason
        or reasoning.strategic_effect
        or reasoning.better_move_reason
    )

    if not reason:
        return None

    lower = reason.lower()

    # Compound tactical ideas should remain explicit.
    if "two tactical ideas at once" in lower:
        return (
            "You missed a move that creates both a fork and a skewer, "
            "giving the opponent multiple tactical threats at once."
        )

    if "both a fork and a skewer" in lower:
        return (
            "You missed a move that creates both a fork and a skewer, "
            "giving the opponent multiple tactical threats at once."
        )

    if "spend a tempo" in lower and "preparation" in lower:
        return (
            "You spent a tempo preparing the central idea instead of "
            "playing it immediately."
        )

    if "claims the center immediately" in lower:
        return "The stronger move claims the center immediately."

    if "forcing" in lower:
        return "You missed a more forcing continuation."

    return reason


def _why_wrong(
    classification: MoveClassification,
    reasoning: ChessReasoning,
) -> str | None:
    label = _label_name(classification.label)

    if label not in {"blunder", "mistake", "inaccuracy"}:
        return None

    concise = _concise_reason(reasoning)

    if concise:
        return _capitalize(concise)

    if reasoning.tactical_effect:
        return _capitalize(reasoning.tactical_effect)

    return "The move gives up part of the position's value."


def _what_you_missed(
    reasoning: ChessReasoning,
) -> str | None:
    """Explain the concrete resource or tactical idea that was missed."""

    tactical = reasoning.tactical_effect

    if tactical:
        lower = tactical.lower()

        if "two tactical ideas at once" in lower:
            return (
                "You missed the same move creating both a fork and a skewer, "
                "so the opponent gets multiple threats from one move."
            )

        if "both a fork and a skewer" in lower:
            return (
                "You missed the same move creating both a fork and a skewer, "
                "so the opponent gets multiple threats from one move."
            )

        if "left hanging" in lower or "became vulnerable" in lower:
            return (
                "You missed that the moved piece became insufficiently "
                "defended and could be captured."
            )

        if "fork" in lower:
            return (
                "You missed the opponent's fork and the multiple threats "
                "created by the fork."
            )

        if "skewer" in lower:
            return (
                "You missed the alignment of the valuable pieces and the "
                "skewer that could attack them in sequence."
            )

        if "pin" in lower:
            return (
                "You missed that the pinned piece could not move freely "
                "without exposing something more valuable."
            )

        if "uncovers the attack" in lower or "discovered" in lower:
            return (
                "You missed that moving the piece also uncovered a second "
                "attack from the piece behind it."
            )

        if "overloaded" in lower:
            return (
                "You missed that one defender was responsible for protecting "
                "more than one important target."
            )

        if "intermediate check" in lower or "zwischenzug" in lower:
            return (
                "You missed the intermediate forcing move before continuing "
                "with the obvious sequence."
            )

        if "back-rank" in lower:
            return (
                "You missed the back-rank threat against your king."
            )

        if "pawn shield" in lower or "king safety" in lower:
            return (
                "You missed how the move weakened your king's defensive cover."
            )

        return _capitalize(tactical)

    if reasoning.better_move_reason:
        reason = reasoning.better_move_reason
        lower = reason.lower()

        if "claims the center immediately" in lower:
            return (
                "You could claim the center immediately with the stronger "
                "candidate instead of preparing the idea first."
            )

        if "forcing" in lower:
            return "You missed a more forcing continuation."

    if reasoning.strategic_effect:
        return _capitalize(reasoning.strategic_effect)

    return None

def _immediate_effect(
    consequence: Consequence | None,
    reasoning: ChessReasoning,
) -> str | None:

    # A concrete tactical motif is more important for coaching than
    # a generic engine consequence such as a later check.
    if reasoning.tactical_effect:
        tactical = reasoning.tactical_effect.lower()

        if "two tactical ideas at once" in tactical:
            return (
                "The missed move creates multiple immediate threats, "
                "including the fork and the skewer."
            )

        if "both a fork and a skewer" in tactical:
            return (
                "The missed move creates multiple immediate threats, "
                "including the fork and the skewer."
            )

        if "left hanging" in tactical or "became vulnerable" in tactical:
            return (
                "The opponent can immediately exploit the vulnerable piece "
                "or pawn."
            )

        if "fork" in tactical:
            return (
                "The opponent can create multiple threats with the fork."
            )

        if "skewer" in tactical:
            return (
                "The opponent can attack the front target and then exploit "
                "the piece behind it."
            )

    if consequence is not None:
        if consequence.immediate:
            return _capitalize(consequence.immediate)

        if consequence.description:
            return _capitalize(consequence.description)

    # A positional inaccuracy without a concrete consequence should
    # not pretend that a tactical event occurred.
    if reasoning.strategic_effect:
        return (
            "The position remains playable, but the move delays the "
            "more purposeful continuation."
        )

    if reasoning.tactical_effect:
        return _capitalize(reasoning.tactical_effect)

    return None


def _better_move(
    context: CoachContext,
    reasoning: ChessReasoning,
) -> str | None:
    if not context.best_move:
        return None

    move = reasoning.better_move or context.best_move

    # Report the engine candidate neutrally. Its presence alone does not
    # establish that the played move was a mistake or explain why it is worse.
    return f"Engine candidate: {move}."


def _why_better(
    reasoning: ChessReasoning,
) -> str | None:
    # A tactical effect alone does not prove why another move is better.
    # Only return an alternative-move explanation when specific reasoning
    # actually supports it.
    if reasoning.better_move_reason:
        return _capitalize(reasoning.better_move_reason)

    return None


def _long_term_effect(
    reasoning: ChessReasoning,
    consequence: Consequence | None,
) -> str | None:
    if consequence is not None and consequence.follow_up:
        return _capitalize(consequence.follow_up)

    if reasoning.strategic_effect:
        lower = reasoning.strategic_effect.lower()

        if "tempo" in lower or "preparation" in lower:
            return (
                "You give up some momentum by spending an extra tempo "
                "on preparation instead of improving the position directly."
            )

        return (
            "The move gives the opponent more time to improve while "
            "your position develops less efficiently."
        )

    return None


def _lesson(
    classification: MoveClassification,
    reasoning: ChessReasoning,
    consequence: Consequence | None,
) -> str:
    label = _label_name(classification.label)

    # Concrete tactical lessons take priority over generic
    # positional advice.
    if reasoning.tactical_effect:
        tactical = reasoning.tactical_effect.lower()

        if "two tactical ideas at once" in tactical:
            return (
                "Before choosing a quiet move, look for forcing moves that "
                "create multiple tactical threats at the same time."
            )

        if "both a fork and a skewer" in tactical:
            return (
                "Before choosing a quiet move, look for forcing moves that "
                "create multiple tactical threats at the same time."
            )

        if "left hanging" in tactical or "became vulnerable" in tactical:
            return (
                "After every move, check which pieces or pawns became "
                "undefended and whether the opponent can capture them."
            )

        if "fork" in tactical:
            return (
                "Before making a move, check the opponent's forcing moves "
                "and look for squares that attack multiple targets."
            )

        if "skewer" in tactical:
            return (
                "Look for aligned valuable pieces and ask whether one can "
                "be attacked in front of another."
            )

        if "pin" in tactical:
            return (
                "Check whether an apparently mobile defender is actually "
                "restricted by a pin."
            )

        if "discovered" in tactical or "uncovers the attack" in tactical:
            return (
                "Before moving a piece, check whether it is blocking a "
                "line piece and whether moving it creates a second threat."
            )

        if "overloaded" in tactical:
            return (
                "Count the important defensive jobs each piece is performing. "
                "An overloaded defender can often be attacked indirectly."
            )

        if "zwischenzug" in tactical or "intermediate check" in tactical:
            return (
                "Before making the obvious recapture, check for forcing "
                "checks, captures, and threats."
            )

        if "back-rank" in tactical:
            return (
                "Before winning material, check whether your king has an "
                "escape square and whether a back-rank threat exists."
            )

        if "pawn shield" in tactical or "king safety" in tactical:
            return (
                "Before weakening your pawn shield, check whether the "
                "opponent can open lines against your king immediately."
            )

    # Reuse the concrete positional concept when one exists.
    if reasoning.strategic_effect:
        if "tempo" in reasoning.strategic_effect.lower():
            return (
                "When your plan can be executed immediately, do not spend "
                "a tempo preparing it without a concrete reason."
            )

        return (
            "Prefer moves that improve the position with a clear purpose "
            "and avoid unnecessary preparation."
        )

    if reasoning.missed_resource:
        return _capitalize(reasoning.missed_resource)

    if label in {"blunder", "mistake"}:
        if consequence and consequence.opponent_threat:
            return (
                "Before making the next move, check what your opponent is "
                "threatening and whether you have a forcing response."
            )

        return (
            "Before committing to a move, compare your candidate with the "
            "opponent's forcing replies."
        )

    if label == "inaccuracy":
        return (
            "Look for the most purposeful continuation before settling "
            "for a merely playable move."
        )

    if label in {"best", "great", "brilliant", "excellent"}:
        return (
            "The available analysis does not establish a specific tactical "
            "or positional idea for this move."
        )

    return (
        "Judge the move by the concrete position and the plans it creates "
        "for both sides."
    )


def _summary(
    classification: MoveClassification,
    context: CoachContext,
    reasoning: ChessReasoning,
    consequence: Consequence | None,
) -> str:
    label = _label_name(classification.label)

    if label in {"blunder", "mistake", "inaccuracy"}:
        if context.san and reasoning.primary_reason:
            return (
                f"{context.san} is {label} because "
                f"{reasoning.primary_reason.lower()}"
            )

        return (
            f"This {label} should be understood through the concrete "
            "consequences of the move."
        )

    if label in {"best", "great", "brilliant", "excellent"}:
        if reasoning.primary_reason:
            return _capitalize(reasoning.primary_reason)

        return (
            "The engine rated this move positively, but the available "
            "analysis does not establish a more specific explanation."
        )
    if consequence and consequence.description:
        return _capitalize(consequence.description)

    return "The move is playable, but the position should be judged concretely."


def explain_move(
    *,
    context: CoachContext,
    classification: MoveClassification,
    reasoning: ChessReasoning,
    consequence: Consequence | None = None,
    motifs: list[dict] | None = None,
) -> CoachExplanation:
    label = _label_name(classification.label)

    if consequence and consequence.category == "checkmate":
        return CoachExplanation(
            headline="Checkmate ? the game is won",
            summary="This move checkmates the opposing king. The opponent has no legal moves, so the game ends in victory.",
            what_you_played=_played_move_sentence(context),
            why_it_is_wrong=None,
            what_you_missed=None,
            immediate_effect="Checkmate. The opposing king has no legal escape or blocking move.",
            better_move=None,
            why_better=None,
            longer_term_effect="The game ends immediately; no further continuation is possible.",
            lesson="Look for forcing checks and verify whether the opposing king has any legal response.",
            details=["Verified terminal result: checkmate; the resulting position has no legal replies."],
        )

    headline = _classification_headline(label)

    played = _played_move_sentence(context)

    why_wrong = _why_wrong(
        classification,
        reasoning,
    )

    what_missed = _what_you_missed(reasoning)

    immediate = _immediate_effect(
        consequence,
        reasoning,
    )

    better = _better_move(
        context,
        reasoning,
    )

    why_better = _why_better(reasoning)

    longer_term = _long_term_effect(
        reasoning,
        consequence,
    )

    lesson = _lesson(
        classification,
        reasoning,
        consequence,
    )

    summary = _summary(
        classification,
        context,
        reasoning,
        consequence,
    )

    details = []

    if reasoning.tactical_effect:
        details.append(
            f"Tactical effect: {_capitalize(reasoning.tactical_effect)}"
        )

    if reasoning.strategic_effect:
        details.append(
            f"Strategic effect: {_capitalize(reasoning.strategic_effect)}"
        )

    if reasoning.practical_effect:
        details.append(
            f"Practical effect: {_capitalize(reasoning.practical_effect)}"
        )

    if consequence and consequence.follow_up:
        details.append(
            f"Follow-up: {_capitalize(consequence.follow_up)}"
        )

    if consequence and consequence.opponent_threat:
        details.append(
            f"Opponent threat: {_capitalize(consequence.opponent_threat)}"
        )

    if motifs:
        names = []

        for motif in motifs:
            if not isinstance(motif, dict):
                continue

            name = (
                motif.get("motif")
                or motif.get("type")
                or motif.get("name")
                or motif.get("key")
            )

            if name:
                names.append(str(name).replace("_", " "))

        if names:
            details.append(
                "Detected patterns: " + ", ".join(names) + "."
            )

    return CoachExplanation(
        headline=headline,
        summary=summary,
        what_you_played=played,
        why_it_is_wrong=why_wrong,
        what_you_missed=what_missed,
        immediate_effect=immediate,
        better_move=better,
        why_better=why_better,
        longer_term_effect=longer_term,
        lesson=lesson,
        details=details,
    )


def explanation_to_dict(
    explanation: CoachExplanation,
) -> dict:
    return {
        "headline": explanation.headline,
        "summary": explanation.summary,
        "what_you_played": explanation.what_you_played,
        "why_it_is_wrong": explanation.why_it_is_wrong,
        "what_you_missed": explanation.what_you_missed,
        "immediate_effect": explanation.immediate_effect,
        "better_move": explanation.better_move,
        "why_better": explanation.why_better,
        "longer_term_effect": explanation.longer_term_effect,
        "lesson": explanation.lesson,
        "details": explanation.details,
    }


