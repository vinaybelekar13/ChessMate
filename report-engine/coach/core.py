from __future__ import annotations

from pathlib import Path

from typing import Any, Iterable, Optional

from coach.classifier import classify
from coach.context import build_context
from coach.consequences import analyze_consequences
from coach.explanation import explain_move
from coach.models import (
    CoachAnalysis,
    CoachContext,
    Consequence,
    MoveClassification,
)
from coach.reasoning import reason_about_move


def _motif_dict(motif: Any) -> dict:
    if isinstance(motif, dict):
        return motif

    return {
        "motif": getattr(motif, "motif", None),
        "side": getattr(motif, "side", None),
        "severity": getattr(motif, "severity", None),
        "description": getattr(motif, "description", None),
        "move_id": getattr(motif, "move_id", None),
        "game_id": getattr(motif, "game_id", None),
    }


def _classification_from_game_move(
    game_move: Any,
) -> MoveClassification:
    label = getattr(game_move, "classification", None)

    cp_loss = getattr(game_move, "centipawn_loss", None)

    evaluation_before = getattr(
        game_move,
        "evaluation_before",
        None,
    )

    evaluation_after = getattr(
        game_move,
        "evaluation_after",
        None,
    )

    best_move = getattr(
        game_move,
        "best_move",
        None,
    )

    played_move = getattr(
        game_move,
        "uci",
        None,
    )

    if label:
        return MoveClassification(
            label=label,
            cp_loss=cp_loss,
            eval_before=evaluation_before,
            eval_after=evaluation_after,
            confidence=1.0,
        )

    return classify(
        color=getattr(game_move, "color", None),
        best_move=best_move,
        played_move=played_move,
        cp_loss=cp_loss or 0.0,
        loss=cp_loss or 0.0,
        eval_before=evaluation_before,
        eval_after=evaluation_after,
        second_best_loss_gap=getattr(
            game_move,
            "second_best_loss_gap",
            None,
        ),
        sacrifice_given=getattr(
            game_move,
            "sacrifice_given",
            None,
        ),
    )


def _build_coach_context(
    game_move: Any,
    motifs: list[dict],
) -> CoachContext:
    return build_context(
        game_id=getattr(game_move, "game_id", None),
        ply=getattr(game_move, "ply", None),
        fen_before=getattr(game_move, "fen_before", None),
        fen_after=getattr(game_move, "fen_after", None),
        san=getattr(game_move, "san", None),
        uci=getattr(game_move, "uci", None),
        color=getattr(game_move, "color", None),
        move_number=getattr(game_move, "move_number", None),
        phase=getattr(game_move, "phase", None),
        evaluation_before=getattr(
            game_move,
            "evaluation_before",
            None,
        ),
        evaluation_after=getattr(
            game_move,
            "evaluation_after",
            None,
        ),
        best_move=getattr(
            game_move,
            "best_move",
            None,
        ),
        motifs=motifs,
    )


def analyze_game_move(
    game_move: Any,
    motifs: Optional[Iterable[Any]] = None,
) -> CoachAnalysis:
    """
    Run the complete deterministic Coach Core pipeline
    for one already-analyzed GameMove.

    This function does not run Stockfish itself.
    It consumes the existing ChessMate analysis data.
    """

    motif_list = [
        _motif_dict(motif)
        for motif in (motifs or [])
    ]

    context = _build_coach_context(
        game_move,
        motif_list,
    )

    classification = _classification_from_game_move(
        game_move,
    )

    consequence_list = analyze_consequences(
        fen_before=getattr(
            game_move,
            "fen_before",
            None,
        ),
        played_move=getattr(
            game_move,
            "uci",
            None,
        ),
        fen_after=getattr(
            game_move,
            "fen_after",
            None,
        ),
        mover=getattr(
            game_move,
            "color",
            None,
        ),
    )

    consequence = _select_primary_consequence(
        consequence_list
    )

    reasoning = reason_about_move(
        context=context,
        classification=classification,
        consequence=consequence,
        motifs=motif_list,
    )

    explanation = explain_move(
        context=context,
        classification=classification,
        reasoning=reasoning,
        consequence=consequence,
        motifs=motif_list,
    )

    return CoachAnalysis(
        context=context,
        classification=classification,
        consequence=consequence,
        reasoning=reasoning,
        explanation=explanation,
        motifs=motif_list,
    )


def _select_primary_consequence(
    consequences: list[Consequence],
) -> Optional[Consequence]:
    if not consequences:
        return None

    priority = {
        "critical": 0,
        "high": 1,
        "positive": 2,
        "normal": 3,
        "low": 4,
    }

    return sorted(
        consequences,
        key=lambda item: priority.get(
            item.severity,
            99,
        ),
    )[0]


def analyze_move_data(
    *,
    game_id: Optional[int],
    ply: Optional[int],
    move_number: Optional[int],
    color: Optional[str],
    san: Optional[str],
    uci: Optional[str],
    fen_before: str,
    fen_after: str,
    phase: Optional[str],
    evaluation_before: Optional[float],
    evaluation_after: Optional[float],
    best_move: Optional[str],
    centipawn_loss: Optional[float],
    classification: Optional[str] = None,
    second_best_loss_gap: Optional[float] = None,
    sacrifice_given: Optional[float] = None,
    motifs: Optional[Iterable[Any]] = None,
) -> CoachAnalysis:
    """
    Convenience API for callers that do not have
    a SQLAlchemy GameMove object.
    """

    class MoveData:
        pass

    move = MoveData()

    move.game_id = game_id
    move.ply = ply
    move.move_number = move_number
    move.color = color
    move.san = san
    move.uci = uci
    move.fen_before = fen_before
    move.fen_after = fen_after
    move.phase = phase
    move.evaluation_before = evaluation_before
    move.evaluation_after = evaluation_after
    move.best_move = best_move
    move.centipawn_loss = centipawn_loss
    move.classification = classification
    move.second_best_loss_gap = second_best_loss_gap
    move.sacrifice_given = sacrifice_given

    return analyze_game_move(
        move,
        motifs=motifs,
    )


_eclipseth_module = None


def _get_eclipseth_module():
    global _eclipseth_module
    if _eclipseth_module is not None:
        return _eclipseth_module

    import importlib.util

    repo_root = Path(__file__).resolve().parents[2]
    feature_path = (
        repo_root / "_github_refs" / "ChessCoach-Positional"
        / "backend" / "features.py"
    )

    if not feature_path.is_file():
        return None

    try:
        spec = importlib.util.spec_from_file_location(
            "chessmate_eclipseth_features", feature_path
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _eclipseth_module = module
        return _eclipseth_module
    except Exception:
        return None


def extract_positional_analysis(
    fen: str,
    uci: Optional[str] = None,
) -> dict:
    """Extract positional features directly for any valid FEN position."""
    if not fen:
        return {"available": False, "error": "Position FEN unavailable"}

    module = _get_eclipseth_module()
    if module is None:
        return {"available": False, "error": "Eclipseth features module could not be loaded"}

    try:
        import chess

        board = chess.Board(fen)
        result = {
            "available": True,
            "source": "Eclipseth3sun/ChessCoach backend/features.py",
            "features": module.extract(board),
            "description": module.describe(board),
            "piece_placement": module.piece_placement(board),
            "material_summary": module.material_summary(board),
        }

        if uci:
            try:
                move = chess.Move.from_uci(uci)
                if move in board.legal_moves:
                    result["played_move_consequences"] = (
                        module.move_consequences(board, move)
                    )
                else:
                    result["played_move_consequences"] = None
                    result["move_note"] = "UCI move is not legal in fen"
            except (ValueError, TypeError):
                result["played_move_consequences"] = None
                result["move_note"] = "Invalid UCI move; consequences omitted"

        return result
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def _positional_dict(analysis: CoachAnalysis) -> dict:
    """Expose facts from the original Eclipseth positional feature module."""
    context = analysis.context
    fen = getattr(context, "fen_before", None)
    uci = getattr(context, "uci", None)
    return extract_positional_analysis(fen, uci)


def coach_analysis_to_dict(
    analysis: CoachAnalysis,
) -> dict:
    consequence = analysis.consequence

    reasoning = analysis.reasoning

    explanation = analysis.explanation

    return {
        "context": analysis.context.__dict__,
        "classification": analysis.classification.__dict__,
        "consequence": (
            consequence.__dict__
            if consequence
            else None
        ),
        "reasoning": (
            reasoning.__dict__
            if reasoning
            else None
        ),
        "explanation": (
            explanation.__dict__
            if explanation
            else None
        ),
        "motifs": analysis.motifs,
        "positional": _positional_dict(analysis),
        "similar_mistakes": analysis.similar_mistakes,
    }
