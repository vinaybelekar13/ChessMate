from __future__ import annotations

from typing import Optional

import chess

from coach.models import CoachContext


PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}


def material_score(board: chess.Board, color: chess.Color) -> int:
    """Return material value for one side, excluding the king."""

    return sum(
        len(board.pieces(piece_type, color)) * value
        for piece_type, value in PIECE_VALUES.items()
    )


def material_balance(board: chess.Board, color: chess.Color) -> int:
    """Return material advantage from the requested side's perspective."""

    own = material_score(board, color)
    opponent = material_score(board, not color)
    return own - opponent


def piece_counts(board: chess.Board, color: chess.Color) -> dict[str, int]:
    """Return piece counts for one side."""

    names = {
        chess.PAWN: "pawn",
        chess.KNIGHT: "knight",
        chess.BISHOP: "bishop",
        chess.ROOK: "rook",
        chess.QUEEN: "queen",
    }

    return {
        name: len(board.pieces(piece_type, color))
        for piece_type, name in names.items()
    }


def pawn_weakness_count(
    board: chess.Board,
    color: chess.Color,
) -> int:
    """
    Count simple structural pawn weaknesses.

    Currently:
    - doubled pawns
    - isolated pawns

    This intentionally stays conservative. More sophisticated
    structural reasoning belongs in the reasoning layer.
    """

    pawn_squares = board.pieces(chess.PAWN, color)

    file_counts = [0] * 8

    for square in pawn_squares:
        file_counts[chess.square_file(square)] += 1

    doubled = sum(
        count - 1
        for count in file_counts
        if count > 1
    )

    isolated = 0

    for square in pawn_squares:
        file_index = chess.square_file(square)

        has_neighbor = any(
            0 <= neighbor_file < 8
            and file_counts[neighbor_file] > 0
            for neighbor_file in (file_index - 1, file_index + 1)
        )

        if not has_neighbor:
            isolated += 1

    return doubled + isolated


def non_pawn_material(board: chess.Board) -> int:
    """Return total non-pawn material on the board."""

    return sum(
        len(board.pieces(piece_type, color)) * value
        for piece_type, value in PIECE_VALUES.items()
        if piece_type != chess.PAWN
        for color in (chess.WHITE, chess.BLACK)
    )


def compute_phase(board: chess.Board) -> str:
    """
    Classify the position as opening, middlegame, or endgame.

    This follows the same conservative phase idea already used
    by ChessMate's motif engine.
    """

    if non_pawn_material(board) <= 13:
        return "endgame"

    if board.fullmove_number <= 12:
        return "opening"

    return "middlegame"


def king_square(
    board: chess.Board,
    color: chess.Color,
) -> Optional[str]:
    """Return the king square in algebraic notation."""

    square = board.king(color)

    if square is None:
        return None

    return chess.square_name(square)


def king_is_in_check(
    board: chess.Board,
    color: chess.Color,
) -> bool:
    """Return whether the requested side's king is currently in check."""

    king = board.king(color)

    if king is None:
        return False

    return board.is_attacked_by(not color, king)


def legal_move_count(
    board: chess.Board,
    color: Optional[chess.Color] = None,
) -> int:
    """
    Count legal moves.

    If color is supplied, evaluate a copy with that side to move.
    """

    if color is None or color == board.turn:
        return board.legal_moves.count()

    copy = board.copy(stack=False)
    copy.turn = color
    return copy.legal_moves.count()


def attacked_piece_count(
    board: chess.Board,
    attacker: chess.Color,
) -> int:
    """
    Count enemy non-king pieces currently attacked by the requested side.
    """

    opponent = not attacker
    count = 0

    for square in chess.SQUARES:
        piece = board.piece_at(square)

        if piece is None:
            continue

        if piece.color != opponent:
            continue

        if piece.piece_type == chess.KING:
            continue

        if board.is_attacked_by(attacker, square):
            count += 1

    return count


def build_context(
    *,
    fen_before: str,
    game_id: Optional[int] = None,
    ply: Optional[int] = None,
    san: Optional[str] = None,
    uci: Optional[str] = None,
    color: Optional[str] = None,
    move_number: Optional[int] = None,
    phase: Optional[str] = None,
    fen_after: Optional[str] = None,
    evaluation_before: Optional[float] = None,
    evaluation_after: Optional[float] = None,
    best_move: Optional[str] = None,
    motifs: Optional[list[dict]] = None,
) -> CoachContext:
    """
    Build the Coach Core's normalized position context.

    The returned CoachContext currently stores the core fields.
    Additional derived facts are intentionally kept as local
    validation/context data until the model is expanded.
    """

    board = chess.Board(fen_before)

    mover = board.turn

    resolved_color = color or ("w" if mover == chess.WHITE else "b")

    resolved_move_number = (
        move_number
        if move_number is not None
        else board.fullmove_number
    )

    resolved_phase = phase or compute_phase(board)

    context = CoachContext(
        game_id=game_id,
        ply=ply,
        fen_before=fen_before,
        fen_after=fen_after,
        san=san,
        uci=uci,
        color=resolved_color,
        move_number=resolved_move_number,
        phase=resolved_phase,
        evaluation_before=evaluation_before,
        evaluation_after=evaluation_after,
        best_move=best_move,
        side_to_move=resolved_color,
        motifs=motifs or [],
    )

    return context


def inspect_position(fen: str) -> dict:
    """
    Return a compact diagnostic snapshot of a FEN.

    This is primarily useful for Coach Core tests and debugging.
    """

    board = chess.Board(fen)

    return {
        "fen": fen,
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
        "fullmove_number": board.fullmove_number,
        "phase": compute_phase(board),
        "white_material": material_score(board, chess.WHITE),
        "black_material": material_score(board, chess.BLACK),
        "material_balance_white": material_balance(
            board,
            chess.WHITE,
        ),
        "white_piece_counts": piece_counts(
            board,
            chess.WHITE,
        ),
        "black_piece_counts": piece_counts(
            board,
            chess.BLACK,
        ),
        "white_king": king_square(
            board,
            chess.WHITE,
        ),
        "black_king": king_square(
            board,
            chess.BLACK,
        ),
        "white_in_check": king_is_in_check(
            board,
            chess.WHITE,
        ),
        "black_in_check": king_is_in_check(
            board,
            chess.BLACK,
        ),
        "white_pawn_weaknesses": pawn_weakness_count(
            board,
            chess.WHITE,
        ),
        "black_pawn_weaknesses": pawn_weakness_count(
            board,
            chess.BLACK,
        ),
        "legal_moves": board.legal_moves.count(),
        "attacked_by_white": attacked_piece_count(
            board,
            chess.WHITE,
        ),
        "attacked_by_black": attacked_piece_count(
            board,
            chess.BLACK,
        ),
    }
