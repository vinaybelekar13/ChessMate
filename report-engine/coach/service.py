from collections import defaultdict
from typing import Any, Optional
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import select

from database.database import SessionLocal
from database.models import Game, GameMove, Motif

from coach.core import (
    analyze_game_move,
    coach_analysis_to_dict,
    extract_positional_analysis,
)


def _motif_dict(motif: Motif) -> dict[str, Any]:
    """
    Convert a database Motif row into the dictionary format
    expected by Coach Core.
    """
    return {
        "motif": motif.motif,
        "side": motif.side,
        "severity": motif.severity,
        "description": motif.description,
        "move_id": motif.move_id,
        "game_id": motif.game_id,
    }


def _load_game(
    session,
    game_id: int,
) -> Optional[Game]:
    return session.scalar(
        select(Game).where(Game.id == game_id)
    )


def _load_game_moves(
    session,
    game_id: int,
) -> list[GameMove]:
    return session.scalars(
        select(GameMove)
        .where(GameMove.game_id == game_id)
        .order_by(GameMove.ply.asc())
    ).all()


def _load_game_motifs(
    session,
    game_id: int,
) -> dict[int, list[dict[str, Any]]]:
    """
    Group database motifs by GameMove.id.

    A move can have multiple motifs, so Coach Core receives
    the complete motif list for that move.
    """
    rows = session.scalars(
        select(Motif)
        .where(Motif.game_id == game_id)
        .order_by(Motif.id.asc())
    ).all()

    motifs_by_move: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for motif in rows:
        if motif.move_id is None:
            continue

        motifs_by_move[motif.move_id].append(
            _motif_dict(motif)
        )

    return motifs_by_move


def _load_jcabiles_review(
    game: Game,
    moves: list[GameMove],
) -> dict[str, Any]:
    """Attach a review only when the complete move sequence matches."""
    base_url = "http://127.0.0.1:8011"
    headers = {"Accept": "application/json"}

    try:
        request = Request(f"{base_url}/api/games", headers=headers)
        with urlopen(request, timeout=8) as response:
            candidates = json.loads(response.read().decode("utf-8"))

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            if (candidate.get("white") or "").strip().casefold() != (game.white or "").strip().casefold():
                continue
            if (candidate.get("black") or "").strip().casefold() != (game.black or "").strip().casefold():
                continue
            if (candidate.get("result") or "").strip() != (game.result or "").strip():
                continue
            if candidate.get("ply_count") != len(moves):
                continue

            candidate_id = candidate.get("id")
            if candidate_id is None:
                continue

            review_request = Request(
                f"{base_url}/api/games/{candidate_id}/review",
                headers=headers,
            )
            with urlopen(review_request, timeout=8) as response:
                review = json.loads(response.read().decode("utf-8"))

            review_plies = review.get("plies")
            if not isinstance(review_plies, list) or len(review_plies) != len(moves):
                continue

            matches = True
            for i in range(len(moves)):
                source_move = moves[i]
                reviewed_move = review_plies[i]

                source_uci = getattr(source_move, "uci", None)
                reviewed_uci = reviewed_move.get("uci")
                source_san = getattr(source_move, "san", None)
                reviewed_san = reviewed_move.get("san")

                if source_uci and reviewed_uci:
                    same_move = source_uci == reviewed_uci
                elif source_san and reviewed_san:
                    same_move = source_san == reviewed_san
                else:
                    same_move = False

                if not same_move:
                    matches = False
                    break

            if matches:
                return {
                    "available": True,
                    "source": "jcabiles/chess-coach",
                    "matched_game_id": candidate_id,
                    "match_method": "players_result_and_full_move_sequence",
                    "review": review,
                }

        return {
            "available": False,
            "source": "jcabiles/chess-coach",
            "reason": "No candidate matched the game identity and complete move sequence.",
        }

    except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError) as exc:
        return {
            "available": False,
            "source": "jcabiles/chess-coach",
            "error": str(exc),
        }


def get_move_coaching(
    move_id: int,
) -> Optional[dict[str, Any]]:
    """
    Generate deterministic coaching for one analyzed GameMove.

    This does not run Stockfish.
    It consumes the analysis already stored in the database.
    """
    session = SessionLocal()

    try:
        move = session.scalar(
            select(GameMove).where(GameMove.id == move_id)
        )

        if move is None:
            return None

        game = _load_game(session, move.game_id)

        if game is None:
            return None

        motifs_by_move = _load_game_motifs(
            session,
            move.game_id,
        )

        analysis = analyze_game_move(
            move,
            motifs=motifs_by_move.get(move.id, []),
        )

        result = coach_analysis_to_dict(analysis)

        result["game"] = {
            "id": game.id,
            "white": game.white,
            "black": game.black,
            "result": game.result,
            "played_at": (
                game.played_at.isoformat()
                if game.played_at
                else None
            ),
        }

        return result

    finally:
        session.close()


def get_game_coaching(
    game_id: int,
) -> Optional[dict[str, Any]]:
    """
    Generate deterministic coaching for every analyzed move
    in one game.

    The same Coach Core is used for every move.
    """
    session = SessionLocal()

    try:
        game = _load_game(session, game_id)

        if game is None:
            return None

        moves = _load_game_moves(
            session,
            game_id,
        )

        motifs_by_move = _load_game_motifs(
            session,
            game_id,
        )

        coaching = []

        for move in moves:
            analysis = analyze_game_move(
                move,
                motifs=motifs_by_move.get(move.id, []),
            )

            coaching.append(
                coach_analysis_to_dict(analysis)
            )

        jcabiles = _load_jcabiles_review(game, moves)

        # Build game-level summary metrics and training insights
        critical_moments = []
        blunders = []
        mistakes = []
        lessons = []
        seen_lessons = set()
        tactical_positions = 0
        terminal_checkmate = None

        for c in coaching:
            ctx = c.get("context") or {}
            ply = ctx.get("ply")
            san = ctx.get("san")
            cls_obj = c.get("classification") or {}
            cls_label = (cls_obj.get("label") or "").lower()
            cpl = cls_obj.get("cp_loss")
            conseq = c.get("consequence") or {}
            reasoning = c.get("reasoning") or {}
            explanation = c.get("explanation") or {}

            if cls_label == "blunder":
                blunders.append({
                    "ply": ply,
                    "san": san,
                    "cp_loss": cpl,
                    "explanation": explanation.get("summary"),
                })
                if ply is not None:
                    critical_moments.append(ply)
            elif cls_label == "mistake":
                mistakes.append({
                    "ply": ply,
                    "san": san,
                    "cp_loss": cpl,
                    "explanation": explanation.get("summary"),
                })
                if ply is not None:
                    critical_moments.append(ply)

            if (
                conseq.get("category") == "checkmate"
                or (san or "").endswith("#")
            ):
                terminal_checkmate = {"ply": ply, "san": san}
                if ply is not None:
                    critical_moments.append(ply)

            if reasoning.get("tactical_effect"):
                tactical_positions += 1

            lesson = explanation.get("lesson")
            if lesson and lesson not in seen_lessons:
                seen_lessons.add(lesson)
                lessons.append(lesson)

        summary_data: dict[str, Any] = {
            "white": game.white,
            "black": game.black,
            "result": game.result,
            "move_count": len(coaching),
            "critical_moments": sorted(list(set(critical_moments))),
            "blunders_count": len(blunders),
            "mistakes_count": len(mistakes),
            "biggest_mistakes": sorted(
                blunders + mistakes,
                key=lambda x: x.get("cp_loss") or 0,
                reverse=True,
            )[:5],
            "terminal_checkmate": terminal_checkmate,
            "tactical_positions_count": tactical_positions,
            "training_lessons": lessons[:5],
            "sources": {
                "native_analysis": "ChessMate Coach Engine",
                "positional_features": "Eclipseth3sun/ChessCoach backend/features.py",
                "game_review": (
                    jcabiles.get("source")
                    if jcabiles.get("available")
                    else "native_fallback"
                ),
            },
        }

        if jcabiles.get("available") and isinstance(jcabiles.get("review"), dict):
            j_sum = jcabiles["review"].get("summary", {})
            summary_data["accuracy"] = {
                "white": j_sum.get("white_accuracy"),
                "black": j_sum.get("black_accuracy"),
                "white_estimated_elo": j_sum.get("white_elo"),
                "black_estimated_elo": j_sum.get("black_elo"),
                "method": "jcabiles/chess-coach engine review",
            }

        return {
            "game": {
                "id": game.id,
                "white": game.white,
                "black": game.black,
                "result": game.result,
                "played_at": (
                    game.played_at.isoformat()
                    if game.played_at
                    else None
                ),
                "analyzed": bool(game.analyzed),
                "analysis_version": game.analysis_version,
            },
            "summary": summary_data,
            "moves": coaching,
            "move_count": len(coaching),
            "jcabiles_review": jcabiles,
        }

    finally:
        session.close()


def get_position_coaching(
    fen: str,
    move_uci: Optional[str] = None,
) -> dict[str, Any]:
    """
    Generate coaching and insights for an arbitrary board position.
    Supports Free Board, Book Reader, and custom FEN analysis.
    """
    import chess

    normalized_fen = (fen or "").strip()
    try:
        board = chess.Board(normalized_fen)
    except Exception as exc:
        return {
            "available": False,
            "is_valid": False,
            "error": f"Invalid FEN position: {exc}",
            "fen": normalized_fen,
        }

    turn_color = "white" if board.turn == chess.WHITE else "black"
    is_check = board.is_check()
    is_checkmate = board.is_checkmate()
    is_stalemate = board.is_stalemate()

    # 1. Extract Eclipseth positional analysis
    positional = extract_positional_analysis(normalized_fen, move_uci)

    # 2. Extract Stockfish evaluation if available
    stockfish_analysis = None
    try:
        from analysis.stockfish_engine import StockfishEngine

        sf = StockfishEngine(depth=12)
        try:
            sf_res = sf.analyze(normalized_fen)
            best_move_uci = sf_res.get("best_move")
            best_move_san = None
            if best_move_uci:
                try:
                    best_move_san = board.san(chess.Move.from_uci(best_move_uci))
                except Exception:
                    pass
            stockfish_analysis = {
                "available": True,
                "source": "Stockfish universal",
                "depth": sf_res.get("depth"),
                "score_cp": sf_res.get("score_cp"),
                "mate": sf_res.get("mate"),
                "best_move_uci": best_move_uci,
                "best_move_san": best_move_san,
                "pv": sf_res.get("pv", []),
            }
        finally:
            sf.close()
    except Exception as sf_err:
        stockfish_analysis = {
            "available": False,
            "source": "Stockfish universal",
            "error": str(sf_err),
        }

    # 3. Build human-readable explanations and takeaways
    observations = []
    if positional.get("available") and isinstance(positional.get("description"), list):
        observations.extend(positional["description"])

    pos_features = positional.get("features", {}) if positional.get("available") else {}
    phase = pos_features.get("phase", "middlegame")

    headline = f"{turn_color.capitalize()} to move in the {phase}."
    if is_checkmate:
        winner = "Black" if board.turn == chess.WHITE else "White"
        headline = f"Checkmate! {winner} wins."
    elif is_stalemate:
        headline = "Stalemate — game is a draw."
    elif is_check:
        headline = f"{turn_color.capitalize()} is in check!"

    recommendation = ""
    if stockfish_analysis and stockfish_analysis.get("best_move_san"):
        recommendation = f"Engine recommends {stockfish_analysis['best_move_san']}. "
    if observations:
        recommendation += f"Key positional factor: {observations[0]}."

    return {
        "available": True,
        "is_valid": True,
        "context": {
            "is_standalone": True,
            "fen": normalized_fen,
            "side_to_move": turn_color,
            "phase": phase,
            "is_check": is_check,
            "is_checkmate": is_checkmate,
            "is_stalemate": is_stalemate,
            "legal_move_count": board.legal_moves.count(),
        },
        "headline": headline,
        "recommendation": recommendation,
        "positional": positional,
        "engine": stockfish_analysis,
        "takeaways": observations[:4],
        "sources": {
            "positional": "Eclipseth3sun/ChessCoach backend/features.py",
            "engine": (
                "Stockfish"
                if (stockfish_analysis and stockfish_analysis.get("available"))
                else "unavailable"
            ),
            "coach": "ChessMate Magnus Coach",
        },
    }
