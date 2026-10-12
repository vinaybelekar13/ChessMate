
from pathlib import Path
import sys
import json
import chess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from database.database import SessionLocal
from database.models import Game, GameMove, Motif
from analysis.engine_cache import EngineCache
from analysis.preston_motif import tag_motifs_with_details
from analysis.classifier import (
    classify_move as canonical_classify_move,
    win_probability_loss,
    accuracy_from_losses,
    mover_score,
    BEST_TOL_CP,
)


FAST_DEPTH = 12
DEEP_DEPTH = 18
MULTIPV = 2

INACCURACY_CPL = 50
MISTAKE_CPL = 100
BLUNDER_CPL = 200
CRITICAL_CPL = 50


MATE_SCORE = 100000


def score_for_mover(line, color):
    if line["mate"] is not None:
        mate = line["mate"]
        score = MATE_SCORE if mate > 0 else -MATE_SCORE
    elif line["eval_cp"] is not None:
        score = line["eval_cp"]
    else:
        return None

    return score if color == "w" else -score


def best_line_for_mover(lines, color):
    if not lines:
        return None

    best = lines[0]

    return {
        "score": score_for_mover(best, color),
        "move_uci": best["move_uci"],
        "pv": best["pv"],
        "mate": best["mate"],
    }


def cpl_from_scores(before, after):
    if before is None or after is None:
        return None

    return max(0.0, float(before - after))


def cpl_from_engine_lines(before_line, after_line, color):
    if before_line is None or after_line is None:
        return None

    before_mate = before_line.get("mate")
    after_mate = after_line.get("mate")

    # Convert mate distances from White POV to mover POV.
    if before_mate is not None:
        before_mate = before_mate if color == "w" else -before_mate

    if after_mate is not None:
        after_mate = after_mate if color == "w" else -after_mate

    # A mate=0 result is a checkmated position. If the mover's
    # best line delivers mate, the move has zero centipawn loss.
    if (
        before_mate is not None
        and before_mate > 0
        and after_mate is not None
        and after_mate >= 0
    ):
        return 0.0

    # If the mover already has a forced mate and the played move
    # keeps a forced mate, treat it as zero loss.
    if (
        before_mate is not None
        and before_mate > 0
        and after_mate is not None
        and after_mate > 0
    ):
        return 0.0

    # Losing a forced mate is a catastrophic loss.
    if before_mate is not None and before_mate > 0:
        return float(MATE_SCORE)

    # Moving into a forced mate for the opponent is catastrophic.
    if after_mate is not None and after_mate < 0:
        return float(MATE_SCORE)

    before_score = score_for_mover(before_line, color)
    after_score = score_for_mover(after_line, color)

    return cpl_from_scores(before_score, after_score)



# Static Exchange Evaluation values used for sacrifice detection.
SEE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}


def see_gain(board: chess.Board, square: chess.Square) -> float:
    """
    Estimate the net material that the side to move can gain by capturing
    on `square`, assuming the cheapest legal recapture sequence.

    This mirrors the existing browser Game Review's SEE-based sacrifice
    detection rather than relying on Stockfish's chosen reply.
    """
    captures = [
        move
        for move in board.legal_moves
        if move.to_square == square
        and board.is_capture(move)
    ]

    if not captures:
        return 0.0

    captures.sort(
        key=lambda move: SEE_VALUES.get(
            board.piece_at(move.from_square).piece_type,
            0,
        )
    )

    move = captures[0]
    captured_piece = board.piece_at(move.to_square)

    if captured_piece is None:
        return 0.0

    captured_value = SEE_VALUES.get(
        captured_piece.piece_type,
        0,
    )

    next_board = board.copy(stack=False)
    next_board.push(move)

    # Taking is optional. A losing exchange is therefore simply declined.
    return max(
        0.0,
        float(captured_value) - see_gain(next_board, square),
    )


def sacrifice_evidence(
    fen_before: str,
    fen_after: str,
    move: chess.Move,
) -> dict:
    """
    Determine whether the played move actually offers material.

    Returns structured evidence so the decision can later be surfaced
    by Game Review / Report / Magnus Coach.
    """
    before = chess.Board(fen_before)
    after = chess.Board(fen_after)

    mover = before.turn

    moving_piece = before.piece_at(move.from_square)
    captured_piece = before.piece_at(move.to_square)
    offered_piece = after.piece_at(move.to_square)

    if moving_piece is None or offered_piece is None:
        return {
            "is_sacrifice": False,
            "given": 0.0,
            "piece_value": 0.0,
            "captured_value": 0.0,
        }

    win_back = see_gain(after, move.to_square)

    captured_value = (
        float(SEE_VALUES.get(captured_piece.piece_type, 0))
        if captured_piece
        else 0.0
    )

    offered_value = float(
        SEE_VALUES.get(offered_piece.piece_type, 0)
    )

    # Net material handed over, matching the browser implementation.
    given = max(
        0.0,
        win_back - captured_value,
    )

    is_sacrifice = (
        offered_value >= 3.0
        and given >= 1.0
    )

    return {
        "is_sacrifice": is_sacrifice,
        "given": given,
        "piece_value": offered_value,
        "captured_value": captured_value,
        "win_back": win_back,
        "mover": "w" if mover == chess.WHITE else "b",
        "square": chess.square_name(move.to_square),
    }


def analyze_game(game_id, fast_depth=FAST_DEPTH, deep_depth=DEEP_DEPTH):
    session = SessionLocal()

    try:
        game = session.scalar(
            select(Game).where(Game.id == game_id)
        )

        if game is None:
            raise ValueError(f"GAME_NOT_FOUND:{game_id}")

        moves = session.scalars(
            select(GameMove)
            .where(GameMove.game_id == game.id)
            .order_by(GameMove.ply)
        ).all()

        if not moves:
            raise ValueError(f"NO_MOVES_FOR_GAME:{game_id}")

        # Clear previous analysis for this game.
        session.query(Motif).filter(
            Motif.game_id == game.id
        ).delete()

        for move in moves:
            move.evaluation_before = None
            move.evaluation_after = None
            move.best_move = None
            move.best_pv = None
            move.centipawn_loss = None
            move.win_probability_loss = None
            move.accuracy = None
            move.classification = None
            move.second_best_loss_gap = None
            move.sacrifice_given = None
            move.classification_version = None
            move.is_critical = False

        session.commit()

        fast_cache = EngineCache(depth=fast_depth)

        try:
            before_lines = fast_cache.evaluate_position(
                moves[0].fen_before,
                multipv=MULTIPV,
            )

            analyzed_count = 0
            motif_count = 0
            critical_count = 0

            for index, move in enumerate(moves):
                color = move.color

                if index == 0:
                    before_lines = fast_cache.evaluate_position(
                        move.fen_before,
                        multipv=MULTIPV,
                    )

                after_lines = fast_cache.evaluate_position(
                    move.fen_after,
                    multipv=MULTIPV,
                )

                best = best_line_for_mover(before_lines, color)

                before_score = best["score"] if best else None

                # The played position is evaluated from the mover's POV.
                after_engine = after_lines[0] if after_lines else None
                after_score = (
                    score_for_mover(after_engine, color)
                    if after_engine
                    else None
                )

                before_engine = before_lines[0] if before_lines else None

                before_cp = (
                    before_engine.get("eval_cp")
                    if before_engine
                    else None
                )
                before_mate = (
                    before_engine.get("mate")
                    if before_engine
                    else None
                )
                after_cp = (
                    after_engine.get("eval_cp")
                    if after_engine
                    else None
                )
                after_mate = (
                    after_engine.get("mate")
                    if after_engine
                    else None
                )

                cpl = cpl_from_engine_lines(
                    before_engine,
                    after_engine,
                    color,
                )

                if cpl is None:
                    cpl = 0.0

                # Canonical Game Review metric: win-percentage loss
                # from the moving player's perspective.
                loss = win_probability_loss(
                    before_cp,
                    after_cp,
                    before_mate,
                    after_mate,
                    color,
                )

                if loss is None:
                    loss = 0.0

                # MultiPV=2: how much stronger the best move is than
                # the second-best move, measured in mover POV win%.
                second_score = None
                if len(before_lines) >= 2:
                    second_line = before_lines[1]
                    second_cp = second_line.get("eval_cp")
                    second_mate = second_line.get("mate")

                    best_mover_score = mover_score(
                        before_cp,
                        color,
                        before_mate,
                    )
                    second_mover_score = mover_score(
                        second_cp,
                        color,
                        second_mate,
                    )

                    if (
                        best_mover_score is not None
                        and second_mover_score is not None
                    ):
                        from analysis.classifier import win_pct

                        second_score = max(
                            0.0,
                            win_pct(best_mover_score)
                            - win_pct(second_mover_score),
                        )

                cp_loss = float(cpl)

                # SEE-based sacrifice detection.
                # This is deliberately static and deterministic; it does not
                # ask Stockfish whether the move "looks like" a sacrifice.
                sac = sacrifice_evidence(
                    move.fen_before,
                    move.fen_after,
                    chess.Move.from_uci(move.uci),
                )

                is_best = (
                    bool(best)
                    and (
                        best["move_uci"] == move.uci
                        or cp_loss <= BEST_TOL_CP
                    )
                )

                canonical = canonical_classify_move(
                    color=color,
                    best_move=best["move_uci"] if best else None,
                    played_move=move.uci,
                    cp_loss=cp_loss,
                    loss=loss,
                    second_best_loss_gap=second_score,
                    sacrifice=sac["is_sacrifice"],
                    material_before=sac["piece_value"],
                    eval_before=before_score,
                    eval_after=after_score,
                    is_book=False,
                )

                classification = canonical.classification
                accuracy = accuracy_from_losses([loss])

                move.evaluation_before = before_score
                move.evaluation_after = after_score
                move.best_move = best["move_uci"] if best else None
                move.best_pv = (
                    " ".join(best["pv"])
                    if best and best["pv"]
                    else None
                )
                move.centipawn_loss = cpl
                move.win_probability_loss = loss
                move.accuracy = accuracy
                move.classification = classification
                move.second_best_loss_gap = second_score
                move.sacrifice_given = (
                    sac["given"]
                    if sac["is_sacrifice"]
                    else None
                )
                move.classification_version = "report-v2-canonical"
                move.is_critical = cpl >= CRITICAL_CPL

                if move.is_critical:
                    critical_count += 1

                board_before = chess.Board(move.fen_before)
                played_move = chess.Move.from_uci(move.uci)
                best_move = (
                    chess.Move.from_uci(best["move_uci"])
                    if best and best["move_uci"]
                    else None
                )

                tags, details = tag_motifs_with_details(
                    board_before,
                    played_move,
                    best_move,
                    classification,
                    phase=move.phase or "middlegame",
                    score_before=(
                        mover_score(
                            before_cp,
                            color,
                            before_mate,
                        )
                    ),
                    score_after=(
                        mover_score(
                            after_cp,
                            color,
                            after_mate,
                        )
                    ),
                    second_pv_score=(
                        mover_score(
                            before_lines[1].get("eval_cp"),
                            color,
                            before_lines[1].get("mate"),
                        )
                        if len(before_lines) >= 2
                        else None
                    ),
                )

                for tag in tags:
                    evidence = details.get(tag, {})
                    session.add(
                        Motif(
                            game_id=game.id,
                            move_id=move.id,
                            motif=tag,
                            side=color,
                            severity=classification,
                            description=json.dumps(
                                evidence,
                                separators=(",", ":"),
                            ),
                        )
                    )
                    motif_count += 1

                analyzed_count += 1

                # The next move's before position is this move's after position.
                if index + 1 < len(moves):
                    before_lines = after_lines

            session.commit()

            # Deep pass only for critical moves.
            deep_cache = EngineCache(depth=deep_depth)

            try:
                for move in moves:
                    if not move.is_critical:
                        continue

                    deep_lines_before = deep_cache.evaluate_position(
                        move.fen_before,
                        multipv=MULTIPV,
                    )

                    deep_lines_after = deep_cache.evaluate_position(
                        move.fen_after,
                        multipv=MULTIPV,
                    )

                    best = best_line_for_mover(
                        deep_lines_before,
                        move.color,
                    )

                    if best:
                        deep_before = best["score"]

                        deep_after = score_for_mover(
                            deep_lines_after[0],
                            move.color,
                        ) if deep_lines_after else None

                        deep_cpl = cpl_from_engine_lines(
                            deep_lines_before[0] if deep_lines_before else None,
                            deep_lines_after[0] if deep_lines_after else None,
                            move.color,
                        )

                        if deep_cpl is not None:
                            move.evaluation_before = deep_before
                            move.evaluation_after = deep_after
                            move.centipawn_loss = deep_cpl

                            deep_before_engine = (
                                deep_lines_before[0]
                                if deep_lines_before
                                else None
                            )
                            deep_after_engine = (
                                deep_lines_after[0]
                                if deep_lines_after
                                else None
                            )

                            deep_loss = win_probability_loss(
                                (
                                    deep_before_engine.get("eval_cp")
                                    if deep_before_engine
                                    else None
                                ),
                                (
                                    deep_after_engine.get("eval_cp")
                                    if deep_after_engine
                                    else None
                                ),
                                (
                                    deep_before_engine.get("mate")
                                    if deep_before_engine
                                    else None
                                ),
                                (
                                    deep_after_engine.get("mate")
                                    if deep_after_engine
                                    else None
                                ),
                                move.color,
                            )

                            if deep_loss is None:
                                deep_loss = 0.0

                            deep_second_gap = None

                            if len(deep_lines_before) >= 2:
                                db = deep_lines_before[0]
                                ds = deep_lines_before[1]

                                db_score = mover_score(
                                    db.get("eval_cp"),
                                    move.color,
                                    db.get("mate"),
                                )
                                ds_score = mover_score(
                                    ds.get("eval_cp"),
                                    move.color,
                                    ds.get("mate"),
                                )

                                if (
                                    db_score is not None
                                    and ds_score is not None
                                ):
                                    from analysis.classifier import win_pct

                                    deep_second_gap = max(
                                        0.0,
                                        win_pct(db_score)
                                        - win_pct(ds_score),
                                    )

                            deep_canonical = canonical_classify_move(
                                color=move.color,
                                best_move=best["move_uci"],
                                played_move=move.uci,
                                cp_loss=float(deep_cpl),
                                loss=deep_loss,
                                second_best_loss_gap=deep_second_gap,
                                sacrifice=sac["is_sacrifice"],
                                material_before=sac["piece_value"],
                                eval_before=deep_before,
                                eval_after=deep_after,
                                is_book=False,
                            )

                            move.win_probability_loss = deep_loss
                            move.accuracy = accuracy_from_losses(
                                [deep_loss]
                            )
                            move.classification = (
                                deep_canonical.classification
                            )
                            move.second_best_loss_gap = deep_second_gap
                            move.sacrifice_given = (
                                sac["given"]
                                if sac["is_sacrifice"]
                                else None
                            )
                            move.classification_version = (
                                "report-v2-canonical"
                            )
                            move.best_move = best["move_uci"]
                            move.best_pv = (
                                " ".join(best["pv"])
                                if best["pv"]
                                else None
                            )

                session.commit()

            finally:
                deep_cache.close()

        finally:
            fast_cache.close()

        game.analyzed = True
        game.analysis_version = "report-v2-canonical"
        session.commit()

        return {
            "game_id": game.id,
            "moves": analyzed_count,
            "critical": critical_count,
            "motifs": motif_count,
            "analysis_version": game.analysis_version,
        }

    finally:
        session.close()


def latest_unanalyzed_game():
    session = SessionLocal()

    try:
        return session.scalar(
            select(Game)
            .where(Game.analyzed == False)
            .order_by(
                Game.played_at.desc(),
                Game.id.desc(),
            )
        )
    finally:
        session.close()


def main():
    game = latest_unanalyzed_game()

    if game is None:
        raise SystemExit("NO_UNANALYZED_GAMES")

    print("FULL_GAME_ANALYSIS_START")
    print("Game ID:", game.id)
    print("White:", game.white)
    print("Black:", game.black)
    print("Played:", game.played_at)

    result = analyze_game(game.id)

    print("FULL_GAME_ANALYSIS_OK")
    print("Game ID:", result["game_id"])
    print("Moves:", result["moves"])
    print("Critical:", result["critical"])
    print("Motifs:", result["motifs"])
    print("Version:", result["analysis_version"])


if __name__ == "__main__":
    main()
