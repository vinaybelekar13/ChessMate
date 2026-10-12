from __future__ import annotations

from typing import Optional

import chess

from coach.models import Consequence


PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}


PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


def _piece_name(board: chess.Board, square: chess.Square) -> str:
    piece = board.piece_at(square)

    if piece is None:
        return "piece"

    return PIECE_NAMES.get(piece.piece_type, "piece")


def _square(square: chess.Square) -> str:
    return chess.square_name(square)


def _material(board: chess.Board, color: chess.Color) -> int:
    return sum(
        len(board.pieces(piece_type, color)) * value
        for piece_type, value in PIECE_VALUES.items()
    )


def _legal_capture_targets(
    board: chess.Board,
) -> set[chess.Square]:
    """
    Return squares that the side to move can legally capture.

    Using legal moves avoids false positives from pinned pieces.
    """

    return {
        move.to_square
        for move in board.legal_moves
        if board.is_capture(move)
    }


def _forcing_moves(
    board: chess.Board,
) -> list[chess.Move]:
    """
    Return forcing moves in priority order:

    checks first, then captures.

    This is deliberately conservative. Deeper tactical
    classification remains the responsibility of the motif engine.
    """

    checks = []
    captures = []

    for move in board.legal_moves:
        if board.gives_check(move):
            checks.append(move)
        elif board.is_capture(move):
            captures.append(move)

    return checks + captures


def detect_moved_piece_hanging(
    board_before: chess.Board,
    board_after: chess.Board,
    played_move: chess.Move,
) -> Optional[Consequence]:
    """
    Detect whether the piece moved by the player can now be
    legally captured without adequate defense.
    """

    destination = played_move.to_square
    piece = board_after.piece_at(destination)

    if piece is None:
        return None

    opponent = board_after.turn

    if destination not in _legal_capture_targets(board_after):
        return None

    defenders = board_after.attackers(
        not opponent,
        destination,
    )

    if defenders:
        return None

    return Consequence(
        category="hanging_piece",
        description=(
            f"The {PIECE_NAMES.get(piece.piece_type, 'piece')} "
            f"on {_square(destination)} is left hanging."
        ),
        severity="high",
        immediate=(
            f"The opponent can capture the {PIECE_NAMES.get(piece.piece_type, 'piece')} "
            f"on {_square(destination)}."
        ),
    )


def detect_opponent_forcing_moves(
    board_after: chess.Board,
) -> list[Consequence]:
    """
    Detect immediate checks and captures available to the opponent.
    """

    consequences: list[Consequence] = []

    opponent = board_after.turn

    for move in _forcing_moves(board_after)[:8]:
        san = board_after.san(move)

        if board_after.gives_check(move):
            consequences.append(
                Consequence(
                    category="forcing_check",
                    description=(
                        f"The opponent has the forcing check {san}."
                    ),
                    severity="high",
                    immediate=(
                        f"{san} forces you to respond to check."
                    ),
                    opponent_threat=san,
                )
            )
        else:
            captured = board_after.piece_at(move.to_square)

            if captured is not None:
                captured_name = PIECE_NAMES.get(
                    captured.piece_type,
                    "piece",
                )

                consequences.append(
                    Consequence(
                        category="forcing_capture",
                        description=(
                            f"The opponent can capture your "
                            f"{captured_name} with {san}."
                        ),
                        severity="medium",
                        immediate=(
                            f"{san} wins or removes material."
                        ),
                        opponent_threat=san,
                    )
                )

    return consequences


def detect_material_change(
    board_before: chess.Board,
    board_after: chess.Board,
    mover: chess.Color,
) -> Optional[Consequence]:
    """
    Report a material change caused by the move.
    """

    before_own = _material(board_before, mover)
    before_opp = _material(board_before, not mover)

    after_own = _material(board_after, mover)
    after_opp = _material(board_after, not mover)

    before_balance = before_own - before_opp
    after_balance = after_own - after_opp

    delta = after_balance - before_balance

    if delta == 0:
        return None

    if delta < 0:
        return Consequence(
            category="material_loss",
            description=(
                f"The move changes the material balance by "
                f"{abs(delta)} point(s) against you."
            ),
            severity="high" if delta <= -3 else "medium",
            immediate=(
                f"You lose approximately {abs(delta)} point(s) of material."
            ),
        )

    return Consequence(
        category="material_gain",
        description=(
            f"The move changes the material balance by "
            f"{delta} point(s) in your favor."
        ),
        severity="positive",
        immediate=(
            f"You gain approximately {delta} point(s) of material."
        ),
    )


def detect_king_safety_change(
    board_before: chess.Board,
    board_after: chess.Board,
    mover: chess.Color,
) -> Optional[Consequence]:
    """
    Detect a basic king-safety deterioration.

    This is intentionally conservative. The detailed king-safety
    motif detector remains the authoritative tactical detector.
    """

    king_before = board_before.king(mover)
    king_after = board_after.king(mover)

    if king_before is None or king_after is None:
        return None

    opponent = not mover

    before_attackers = len(
        board_before.attackers(opponent, king_before)
    )

    after_attackers = len(
        board_after.attackers(opponent, king_after)
    )

    if after_attackers <= before_attackers:
        return None

    return Consequence(
        category="king_safety",
        description=(
            "Your king becomes more exposed after the move."
        ),
        severity="high" if after_attackers > 1 else "medium",
        immediate=(
            "The opponent gains additional attacking access to your king."
        ),
    )


def detect_pawn_structure_change(
    board_before: chess.Board,
    board_after: chess.Board,
    mover: chess.Color,
) -> Optional[Consequence]:
    """
    Detect simple increases in doubled/isolated pawn weaknesses.
    """

    def weakness_count(board: chess.Board) -> int:
        pawns = board.pieces(chess.PAWN, mover)

        files = [0] * 8

        for square in pawns:
            files[chess.square_file(square)] += 1

        doubled = sum(
            count - 1
            for count in files
            if count > 1
        )

        isolated = 0

        for square in pawns:
            file_index = chess.square_file(square)

            if not any(
                0 <= neighbor < 8
                and files[neighbor] > 0
                for neighbor in (
                    file_index - 1,
                    file_index + 1,
                )
            ):
                isolated += 1

        return doubled + isolated

    before = weakness_count(board_before)
    after = weakness_count(board_after)

    if after <= before:
        return None

    return Consequence(
        category="pawn_structure",
        description=(
            "The move creates additional pawn-structure weaknesses."
        ),
        severity="medium",
        immediate=(
            f"Your simple pawn-weakness count increases from "
            f"{before} to {after}."
        ),
    )


def analyze_consequences(
    *,
    fen_before: str,
    played_move: str,
    fen_after: Optional[str] = None,
    mover: Optional[str] = None,
) -> list[Consequence]:
    """
    Analyze the immediate consequences of a played move.

    This function intentionally reports evidence rather than
    pretending to understand the entire strategic position.
    """

    board_before = chess.Board(fen_before)

    try:
        move = chess.Move.from_uci(played_move)
    except ValueError as exc:
        raise ValueError(
            f"Invalid UCI move: {played_move}"
        ) from exc

    if move not in board_before.legal_moves:
        raise ValueError(
            f"Illegal move {played_move} for FEN: {fen_before}"
        )

    moving_color = (
        chess.WHITE
        if mover == "w"
        else chess.BLACK
        if mover == "b"
        else board_before.turn
    )

    board_after = board_before.copy(stack=False)
    board_after.push(move)

    # A terminal checkmate overrides ordinary material consequences.
    if board_after.is_checkmate():
        return [
            Consequence(
                category="checkmate",
                description="Checkmate. The opponent has no legal reply, so the game is won.",
                severity="critical",
                immediate="The opposing king is checkmated; the game ends immediately.",
                follow_up=None,
                opponent_threat=None,
            )
        ]

    consequences: list[Consequence] = []

    hanging = detect_moved_piece_hanging(
        board_before,
        board_after,
        move,
    )

    if hanging:
        consequences.append(hanging)

    material = detect_material_change(
        board_before,
        board_after,
        moving_color,
    )

    if material:
        consequences.append(material)

    king_safety = detect_king_safety_change(
        board_before,
        board_after,
        moving_color,
    )

    if king_safety:
        consequences.append(king_safety)

    pawn_structure = detect_pawn_structure_change(
        board_before,
        board_after,
        moving_color,
    )

    if pawn_structure:
        consequences.append(pawn_structure)

    consequences.extend(
        detect_opponent_forcing_moves(board_after)
    )

    return consequences
