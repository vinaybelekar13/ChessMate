from __future__ import annotations
from dataclasses import dataclass, field

from typing import Any, Optional

import json
import chess

from coach.models import ChessReasoning, CoachContext, Consequence, MoveClassification


def _side_name(color: Optional[str]) -> str:
    if color == "w":
        return "White"
    if color == "b":
        return "Black"
    return "The player"


def _opponent_name(color: Optional[str]) -> str:
    if color == "w":
        return "Black"
    if color == "b":
        return "White"
    return "the opponent"


def _piece_name(piece: Optional[chess.Piece]) -> str:
    if piece is None:
        return "piece"

    names = {
        chess.PAWN: "pawn",
        chess.KNIGHT: "knight",
        chess.BISHOP: "bishop",
        chess.ROOK: "rook",
        chess.QUEEN: "queen",
        chess.KING: "king",
    }

    return names.get(piece.piece_type, "piece")


def _square_name(square: Optional[int]) -> str:
    if square is None:
        return "unknown square"
    return chess.square_name(square)


def _move_description(board: chess.Board, move_uci: Optional[str]) -> Optional[str]:
    if not move_uci:
        return None

    try:
        move = chess.Move.from_uci(move_uci)

        if move not in board.legal_moves:
            return move_uci

        return board.san(move)
    except Exception:
        return move_uci


def _find_move(board: chess.Board, move_uci: Optional[str]) -> Optional[chess.Move]:
    if not move_uci:
        return None

    try:
        move = chess.Move.from_uci(move_uci)
        if move in board.legal_moves:
            return move
    except Exception:
        pass

    return None


def _forcing_move_exists(board: chess.Board) -> bool:
    for move in board.legal_moves:
        if board.gives_check(move):
            return True

    for move in board.legal_moves:
        if board.is_capture(move):
            return True

    return False


def _king_safety_reason(
    context: CoachContext,
    board: chess.Board,
) -> Optional[str]:
    if context.color not in ("w", "b"):
        return None

    mover = chess.WHITE if context.color == "w" else chess.BLACK
    opponent = not mover

    king = board.king(mover)

    if king is None:
        return None

    attackers = board.attackers(opponent, king)

    if attackers:
        return (
            f"Your king is under pressure on {_square_name(king)}. "
            f"King safety should take priority over a slow improvement."
        )

    return None


def _piece_activity_reason(
    context: CoachContext,
    board: chess.Board,
) -> Optional[str]:
    if context.color not in ("w", "b"):
        return None

    mover = chess.WHITE if context.color == "w" else chess.BLACK

    pieces = []

    for square, piece in board.piece_map().items():
        if piece.color != mover:
            continue

        if piece.piece_type in (
            chess.KNIGHT,
            chess.BISHOP,
            chess.ROOK,
            chess.QUEEN,
        ):
            pieces.append((piece, square))

    if not pieces:
        return None

    least_active = None
    least_score = None

    for piece, square in pieces:
        mobility = len(board.attacks(square))

        if least_score is None or mobility < least_score:
            least_score = mobility
            least_active = (piece, square)

    if least_active is None:
        return None

    piece, square = least_active

    if least_score is not None and least_score <= 2:
        return (
            f"Your {_piece_name(piece)} on {_square_name(square)} is restricted. "
            f"Improving your worst piece may be more useful than making another "
            f"unconnected move."
        )

    return None


def _pawn_structure_reason(
    context: CoachContext,
    board: chess.Board,
) -> Optional[str]:
    if context.color not in ("w", "b"):
        return None

    mover = chess.WHITE if context.color == "w" else chess.BLACK

    weak = 0

    for file_index in range(8):
        pawns = []

        for rank in range(8):
            square = chess.square(file_index, rank)
            piece = board.piece_at(square)

            if (
                piece is not None
                and piece.piece_type == chess.PAWN
                and piece.color == mover
            ):
                pawns.append(square)

        if len(pawns) > 1:
            weak += 1

    isolated = 0

    for square, piece in board.piece_map().items():
        if piece.piece_type != chess.PAWN or piece.color != mover:
            continue

        file_index = chess.square_file(square)

        neighbouring_files = []

        if file_index > 0:
            neighbouring_files.append(file_index - 1)

        if file_index < 7:
            neighbouring_files.append(file_index + 1)

        has_neighbour = False

        for neighbour_file in neighbouring_files:
            for rank in range(8):
                neighbour_square = chess.square(neighbour_file, rank)
                neighbour_piece = board.piece_at(neighbour_square)

                if (
                    neighbour_piece is not None
                    and neighbour_piece.piece_type == chess.PAWN
                    and neighbour_piece.color == mover
                ):
                    has_neighbour = True
                    break

            if has_neighbour:
                break

        if not has_neighbour:
            isolated += 1

    if weak or isolated:
        parts = []

        if weak:
            parts.append(f"{weak} doubled-pawn file(s)")

        if isolated:
            parts.append(f"{isolated} isolated pawn(s)")

        return (
            "Your pawn structure contains "
            + " and ".join(parts)
            + ". Avoid creating further structural weaknesses unless there "
            "is a concrete benefit."
        )

    return None


def _classification_reason(
    classification: MoveClassification,
) -> Optional[str]:
    label = (classification.label or "").lower()

    if label == "blunder":
        return (
            "The move creates a serious deterioration in the position and "
            "requires a concrete explanation of what changed."
        )

    if label == "mistake":
        return (
            "The move gives the opponent a meaningful improvement and should "
            "be compared with stronger candidate moves."
        )

    if label == "inaccuracy":
        return (
            "The move is playable but gives up part of the position's potential."
        )

    if label in {"best", "excellent", "great", "brilliant"}:
        return (
            "The move performs well according to the engine evaluation. "
            "The useful lesson is to understand the idea behind it."
        )

    if label == "good":
        return (
            "The move is sound, although there may be a more precise continuation."
        )

    return None


def _consequence_reason(
    consequence: Optional[Consequence],
) -> Optional[str]:
    if consequence is None:
        return None

    category = consequence.category.lower()

    if category == "material_gain":
        return consequence.description

    if category == "material_loss":
        return consequence.description

    if category == "piece_hanging":
        return consequence.description

    if category == "opponent_forcing_move":
        return consequence.description

    if category == "king_safety":
        return consequence.description

    if category == "pawn_structure":
        return consequence.description

    return consequence.description



def _move_purpose(board: chess.Board, move_uci: Optional[str]) -> Optional[str]:
    """Infer the basic chess purpose of a candidate move."""
    if not move_uci:
        return None

    try:
        move = chess.Move.from_uci(move_uci)
    except ValueError:
        return None

    if move not in board.legal_moves:
        return None

    piece = board.piece_at(move.from_square)
    if piece is None:
        return None

    # Castling.
    if (
        piece.piece_type == chess.KING
        and abs(
            chess.square_file(move.to_square)
            - chess.square_file(move.from_square)
        ) == 2
    ):
        return "improves king safety and activates the rook"

    # Checks.
    board_after = board.copy()
    board_after.push(move)
    if board_after.is_check():
        return "creates a check and forces a response"

    # Captures.
    if board.is_capture(move):
        return "wins or challenges material"

    # Pawn moves.
    if piece.piece_type == chess.PAWN:
        target_file = chess.square_file(move.to_square)
        target_rank = chess.square_rank(move.to_square)

        if target_file in {3, 4} and target_rank in {3, 4}:
            return "claims central space"

        return "changes the pawn structure"

    # Minor-piece development/activity.
    if piece.piece_type in {chess.KNIGHT, chess.BISHOP}:
        start_rank = 0 if piece.color == chess.WHITE else 7

        if chess.square_rank(move.from_square) == start_rank:
            return "develops a piece"

        return "improves piece activity"

    # Rook/queen activity.
    if piece.piece_type in {chess.ROOK, chess.QUEEN}:
        return "improves piece activity"

    return "improves the position"




@dataclass
class TacticalSummary:
    """
    Internal structured representation of tactical evidence.

    This is deliberately kept inside the reasoning layer. It is not part
    of the public CoachAnalysis API.
    """

    primary: str
    effect: str
    resource_uci: Optional[str] = None
    supporting: list[str] = field(default_factory=list)


def _tactical_motif_reason(
    context: CoachContext,
    motifs: list[dict[str, Any]],
) -> Optional[TacticalSummary]:
    """
    Build one structured tactical explanation from the existing motif records.

    The motif engine may report several related motifs for the same move.
    We aggregate them into one tactical story while preserving the stronger
    tactical resource separately.
    """
    if not motifs:
        return None

    parsed: list[tuple[str, dict[str, Any]]] = []

    for motif in motifs:
        if not isinstance(motif, dict):
            continue

        name = str(
            motif.get("motif")
            or motif.get("type")
            or motif.get("name")
            or motif.get("key")
            or ""
        ).lower().strip()

        description = motif.get("description")

        if isinstance(description, str):
            try:
                description = json.loads(description)
            except (TypeError, ValueError):
                description = {}
        elif not isinstance(description, dict):
            description = {}

        if name:
            parsed.append((name, description))

    if not parsed:
        return None

    names = {name for name, _ in parsed}

    def first_description(name: str) -> dict[str, Any]:
        for motif_name, description in parsed:
            if motif_name == name:
                return description
        return {}

    board_before = None

    if context.fen_before:
        try:
            board_before = chess.Board(context.fen_before)
        except Exception:
            board_before = None

    def san_for(uci: Optional[str]) -> Optional[str]:
        if not uci:
            return None

        if board_before is None:
            return uci

        try:
            move = chess.Move.from_uci(uci)
            if move in board_before.legal_moves:
                return board_before.san(move)
        except (ValueError, chess.IllegalMoveError):
            pass

        return uci

    fork = first_description("fork_missed")
    skewer = first_description("skewer_missed")
    pin = first_description("pin_missed")
    discovered = first_description("discovered_attack")
    hanging = first_description("hanging_piece")
    overloaded = first_description("overloaded_piece")

    fork_move = fork.get("by_move")
    skewer_move = skewer.get("by_move")
    pin_move = pin.get("by_move")

    resource_uci = None

    if fork_move:
        resource_uci = fork_move
    elif skewer_move:
        resource_uci = skewer_move
    elif pin_move:
        resource_uci = pin_move
    elif overloaded.get("by_move"):
        resource_uci = overloaded.get("by_move")
    elif discovered.get("moved_from") and discovered.get("moved_to"):
        resource_uci = (
            f"{discovered.get('moved_from')}"
            f"{discovered.get('moved_to')}"
        )

    resource_san = san_for(resource_uci)

    # ------------------------------------------------------------
    # Fork + skewer
    # ------------------------------------------------------------

    if "fork_missed" in names and "skewer_missed" in names:
        targets = fork.get("targets") or []
        target_text = ", ".join(str(x) for x in targets)

        effect = (
            f"{resource_san or resource_uci} creates a fork"
        )

        if target_text:
            effect += f" against {target_text}"

        effect += (
            " while also creating a skewer, so one forcing move "
            "creates multiple tactical threats at once."
        )

        return TacticalSummary(
            primary=(
                "You missed a forcing tactical sequence that created "
                "multiple threats at once."
            ),
            effect=effect,
            resource_uci=resource_uci,
            supporting=["fork", "skewer"],
        )

    # ------------------------------------------------------------
    # Fork + pin
    # ------------------------------------------------------------

    if "fork_missed" in names and "pin_missed" in names:
        targets = fork.get("targets") or []
        target_text = ", ".join(str(x) for x in targets)

        effect = f"{resource_san or resource_uci} creates a fork"

        if target_text:
            effect += f" against {target_text}"

        effect += (
            " while also creating a pin."
        )

        if "discovered_attack" in names:
            effect += (
                " It also activates the previously hidden a-file attack."
            )

        effect += (
            " One forcing move creates several problems at once."
        )

        supporting = ["fork", "pin"]

        if "discovered_attack" in names:
            supporting.append("discovered attack")

        if "hanging_piece" in names:
            supporting.append("vulnerable piece")

        return TacticalSummary(
            primary=(
                "You missed a tactical sequence that created multiple "
                "threats with one move."
            ),
            effect=effect,
            resource_uci=resource_uci,
            supporting=supporting,
        )

    # ------------------------------------------------------------
    # Discovered attack + another motif
    # ------------------------------------------------------------

    supporting = []

    if "fork_missed" in names:
        supporting.append("fork")

    if "skewer_missed" in names:
        supporting.append("skewer")

    if "pin_missed" in names:
        supporting.append("pin")

    if "hanging_piece" in names:
        supporting.append("vulnerable piece")

    if "overloaded_piece" in names:
        supporting.append("overloaded defender")

    if "discovered_attack" in names and supporting:
        support_text = ", ".join(supporting)

        effect = (
            f"{resource_san or resource_uci} activates a discovered attack "
            f"while also creating {support_text}. The important point is "
            "that one move changes several tactical relationships at once."
        )

        return TacticalSummary(
            primary=(
                "You missed a tactical sequence in which one move created "
                "multiple threats."
            ),
            effect=effect,
            resource_uci=resource_uci,
            supporting=["discovered attack", *supporting],
        )

    # ------------------------------------------------------------
    # Individual motifs
    # ------------------------------------------------------------

    if "hanging_piece" in names:
        squares = hanging.get("squares") or []
        square = squares[0] if squares else None
        piece = hanging.get("piece", "piece")
        reason = hanging.get("reason")

        if square:
            if reason == "moved_piece_left_hanging":
                return TacticalSummary(
                    primary=(
                        "The move left material vulnerable to an immediate "
                        "tactical punishment."
                    ),
                    effect=(
                        f"Your {piece} on {square} was left hanging by the "
                        "move, allowing the opponent to exploit the newly "
                        "undefended piece."
                    ),
                    resource_uci=resource_uci,
                    supporting=["hanging piece"],
                )

            return TacticalSummary(
                primary="The move left a piece vulnerable to a tactical response.",
                effect=(
                    f"Your {piece} on {square} became vulnerable after the "
                    "move. The key question was whether it remained adequately "
                    "defended."
                ),
                resource_uci=resource_uci,
                supporting=["hanging piece"],
            )

    if "fork_missed" in names:
        square = fork.get("fork_square")
        targets = fork.get("targets") or []
        target_text = ", ".join(str(x) for x in targets)
        move = fork.get("by_move")
        san = san_for(move)

        return TacticalSummary(
            primary=(
                "You missed a tactical fork that created multiple threats "
                "with one move."
            ),
            effect=(
                f"{san or move} creates a fork from {square} against "
                f"{target_text}, creating multiple threats at once."
            ),
            resource_uci=move,
            supporting=["fork"],
        )

    if "skewer_missed" in names:
        squares = skewer.get("squares") or []
        move = skewer.get("by_move")
        san = san_for(move)

        if len(squares) >= 2:
            return TacticalSummary(
                primary="You missed a tactical skewer.",
                effect=(
                    f"{san or move} creates a skewer along {squares[0]} to "
                    f"{squares[1]}, forcing the front target to move and "
                    "exposing the more valuable piece behind it."
                ),
                resource_uci=move,
                supporting=["skewer"],
            )

    if "pin_missed" in names:
        pinned = pin.get("pinned_squares") or []
        move = pin.get("by_move")
        san = san_for(move)

        if pinned:
            return TacticalSummary(
                primary="You missed a tactical pin that restricted a defender.",
                effect=(
                    f"{san or move} creates a pin against "
                    f"{', '.join(str(x) for x in pinned)}. The pinned piece "
                    "cannot move freely without exposing something more valuable."
                ),
                resource_uci=move,
                supporting=["pin"],
            )

    if "overloaded_piece" in names:
        target = overloaded.get("target")
        defender = overloaded.get("overloaded_defender")
        also_defends = overloaded.get("also_defends")
        move = overloaded.get("by_move")

        if defender and target and also_defends:
            return TacticalSummary(
                primary="You missed an overloaded-defender tactic.",
                effect=(
                    f"The piece on {defender} has to defend both {target} "
                    f"and {also_defends}, creating a tactical opportunity."
                ),
                resource_uci=move,
                supporting=["overloaded defender"],
            )

    if "intermezzo_missed" in names:
        description = first_description("intermezzo_missed")
        move = description.get("by_move")
        san = san_for(move)

        if move:
            return TacticalSummary(
                primary="You missed an intermediate forcing move.",
                effect=(
                    f"{san or move} should be played before the obvious "
                    "continuation. The zwischenzug changes the position "
                    "before the expected recapture."
                ),
                resource_uci=move,
                supporting=["intermezzo"],
            )

    if "discovered_attack" in names:
        moved_from = discovered.get("moved_from")
        moved_to = discovered.get("moved_to")
        attacks = discovered.get("discovered_attacks") or []

        if attacks:
            attack = attacks[0]
            target = attack.get("target")
            attacker = attack.get("uncovered_attacker")

            if moved_from and moved_to and target and attacker:
                return TacticalSummary(
                    primary=(
                        "You missed a tactical discovered attack that "
                        "activated a previously hidden line."
                    ),
                    effect=(
                        f"Moving from {moved_from} to {moved_to} uncovers "
                        f"the attack of the piece on {attacker} against "
                        f"{target}, activating another line."
                    ),
                    resource_uci=(
                        f"{moved_from}{moved_to}"
                    ),
                    supporting=["discovered attack"],
                )

    if "back_rank" in names:
        description = first_description("back_rank")
        king_square = description.get("king_square")

        if king_square:
            return TacticalSummary(
                primary="You allowed a back-rank weakness.",
                effect=(
                    f"Your king on {king_square} is vulnerable on the back "
                    "rank. The defensive priority is to create an escape "
                    "square or stop the attack."
                ),
                resource_uci=resource_uci,
                supporting=["back rank"],
            )

    if "king_safety" in names:
        description = first_description("king_safety")
        king_square = description.get("king_square")

        if king_square:
            return TacticalSummary(
                primary="The move created a concrete king-safety weakness.",
                effect=(
                    f"The move changes the safety of your king on "
                    f"{king_square}. King safety needed to be checked before "
                    "opening lines around your own king."
                ),
                resource_uci=resource_uci,
                supporting=["king safety"],
            )

    return None


def _move_priority_reason(
    context: CoachContext,
) -> Optional[str]:
    """
    Detect when the played move prepares an idea that the stronger
    candidate can execute immediately.

    This is a general positional concept, not a c3/d4-only rule.
    """
    if not context.fen_before or not context.uci or not context.best_move:
        return None

    try:
        board = chess.Board(context.fen_before)

        played = chess.Move.from_uci(context.uci)
        best = chess.Move.from_uci(context.best_move)

        if played not in board.legal_moves:
            return None

        played_piece = board.piece_at(played.from_square)
        best_piece = board.piece_at(best.from_square)

        if played_piece is None or best_piece is None:
            return None

        played_san = board.san(played)
        best_san = board.san(best)

        # ----------------------------------------------------
        # Pawn preparation vs immediate central break.
        #
        # Example:
        #   c3 -> prepares d4
        #   d4 -> executes the central idea immediately
        # ----------------------------------------------------
        if (
            played_piece.piece_type == chess.PAWN
            and best_piece.piece_type == chess.PAWN
        ):
            played_file = chess.square_file(played.to_square)
            played_rank = chess.square_rank(played.to_square)

            best_file = chess.square_file(best.to_square)
            best_rank = chess.square_rank(best.to_square)

            # A non-central pawn move followed by an immediate
            # central pawn move is a strong signal that the played
            # move may simply be preparation.
            if (
                best_file in {3, 4}
                and best_rank in {3, 4}
                and not (
                    played_file in {3, 4}
                    and played_rank in {3, 4}
                )
            ):
                return (
                    f"{best_san} executes the central idea immediately. "
                    f"{played_san} is mainly preparation for a future pawn "
                    "advance, so you spend a tempo before carrying out the "
                    "plan. When the position allows you to execute the plan "
                    "at once, the direct move is usually more precise."
                )

        return None

    except (ValueError, chess.IllegalMoveError):
        return None


def _candidate_comparison_reason(
    context: CoachContext,
    classification: MoveClassification,
) -> Optional[str]:
    """Explain the purpose difference between the played move and best candidate."""
    if not context.fen_before or not context.best_move or not context.uci:
        return None

    try:
        board = chess.Board(context.fen_before)

        played_move = chess.Move.from_uci(context.uci)
        best_move = chess.Move.from_uci(context.best_move)

        if played_move not in board.legal_moves:
            return None

        played_san = board.san(played_move)
        best_san = board.san(best_move)

        played_purpose = _move_purpose(board, context.uci)
        best_purpose = _move_purpose(board, context.best_move)

        # Important central-tempo case:
        # c3 prepares d4, while d4 claims the centre immediately.
        if (
            played_purpose == "changes the pawn structure"
            and best_purpose == "claims central space"
        ):
            return (
                f"{best_san} claims the center immediately. "
                f"{played_san} prepares a future central pawn move instead of "
                "making that move now, so you spend a tempo on preparation."
            )

        if played_purpose and best_purpose and played_purpose != best_purpose:
            return (
                f"{best_san} is stronger because it {best_purpose}, "
                f"while {played_san} mainly {played_purpose}."
            )

        return (
            f"The engine prefers {best_san} because it achieves a more useful "
            "positional goal immediately."
        )

    except (ValueError, chess.IllegalMoveError):
        return None


def reason_about_move(
    *,
    context: CoachContext,
    classification: MoveClassification,
    consequence: Optional[Consequence] = None,
    motifs: Optional[list[dict[str, Any]]] = None,
) -> ChessReasoning:
    """
    Build layered chess reasoning from the canonical analysis data.

    Each reasoning field has a distinct responsibility:

    primary_reason
        The root cause of the move's quality.

    tactical_effect
        The concrete tactical pattern or tactical consequence.

    strategic_effect
        The positional or long-term consequence.

    practical_effect
        The calculation habit or practical decision-making lesson.

    missed_resource
        The stronger resource/candidate that should have been considered.
    """
    motifs = motifs or []

    tactical_effect: Optional[str] = None
    strategic_effect: Optional[str] = None
    practical_effect: Optional[str] = None
    missed_resource: Optional[str] = None

    board_before: Optional[chess.Board] = None
    board_after: Optional[chess.Board] = None

    if context.fen_before:
        try:
            board_before = chess.Board(context.fen_before)
        except Exception:
            board_before = None

    if context.fen_after:
        try:
            board_after = chess.Board(context.fen_after)
        except Exception:
            board_after = None

    tactical_summary = _tactical_motif_reason(context, motifs)
    tactical_motif_reason = (
        tactical_summary.effect if tactical_summary else None
    )
    priority_reason = _move_priority_reason(context)
    consequence_text = _consequence_reason(consequence)

    classification_label = classification.label.lower()

    # ------------------------------------------------------------
    # 1. Tactical reasoning has the highest explanatory priority.
    # ------------------------------------------------------------

    if tactical_motif_reason:
        tactical_effect = tactical_motif_reason

        if "multiple tactical threats" in tactical_motif_reason:
            primary_reason = (
                "You missed a forcing tactical sequence that created "
                "multiple threats at once."
            )
        elif "left hanging" in tactical_motif_reason:
            primary_reason = (
                "The move left material vulnerable to an immediate tactical "
                "punishment."
            )
        elif "fork" in tactical_motif_reason:
            primary_reason = (
                "You missed a tactical fork that created multiple threats "
                "with one move."
            )
        elif "skewer" in tactical_motif_reason:
            primary_reason = (
                "You missed a tactical skewer that changed the value of the "
                "position."
            )
        elif "pin" in tactical_motif_reason:
            primary_reason = (
                "You missed a tactical pin that restricted a defender."
            )
        elif "discovered attack" in tactical_motif_reason:
            primary_reason = (
                "You missed a tactical line that became active after the "
                "piece moved."
            )
        else:
            primary_reason = (
                "The move missed a concrete tactical resource in the position."
            )

        # The tactical habit is deliberately separate from the tactical
        # description itself.
        if (
            "multiple tactical threats" in tactical_motif_reason
            or "fork" in tactical_motif_reason
            or "skewer" in tactical_motif_reason
            or "pin" in tactical_motif_reason
        ):
            practical_effect = (
                "Before choosing a quiet move, scan checks, captures, "
                "and forcing moves for tactical ideas that create more "
                "than one threat."
            )
        elif "hanging" in tactical_motif_reason:
            practical_effect = (
                "After every move, check which pieces or pawns became "
                "undefended and whether the opponent can exploit them."
            )
        elif "discovered attack" in tactical_motif_reason:
            practical_effect = (
                "After moving a piece, check which files, ranks, and "
                "diagonals become newly opened."
            )
        else:
            practical_effect = (
                "The position required a concrete tactical check before "
                "committing to the move."
            )

    # ------------------------------------------------------------
    # 2. Positional priority reasoning.
    # ------------------------------------------------------------

    elif priority_reason:
        strategic_effect = priority_reason

        primary_reason = priority_reason

        practical_effect = (
            "When a useful plan can be executed immediately, prefer the "
            "direct move unless preparation creates a concrete benefit."
        )

    # ------------------------------------------------------------
    # 3. Generic consequence reasoning.
    # ------------------------------------------------------------

    else:
        # No concrete reason was established by the available analysis.
        primary_reason = None

    if consequence_text:
        # A concrete tactical motif is more informative than the generic
        # consequence. Never overwrite an existing tactical explanation.
        if tactical_motif_reason:
            if practical_effect is None:
                practical_effect = consequence_text
        else:
            tactical_effect = consequence_text

            if classification_label in {
                "blunder",
                "mistake",
                "inaccuracy",
            }:
                practical_effect = (
                    "Compare the move with the opponent's strongest forcing "
                    "responses before deciding on the next move."
                )
            else:
                practical_effect = (
                    "Evaluate the concrete position before applying a general "
                    "chess rule."
                )

    # ------------------------------------------------------------
    # 4. Board-derived strategic information
    # ------------------------------------------------------------
    # Do not infer that a move caused a weakness merely because
    # the resulting position contains a restricted piece or an
    # existing pawn-structure weakness. Strategic claims must be
    # supported by move-specific evidence.
    #
    # Tactical motifs, verified consequences, and the existing
    # priority-reasoning pipeline remain active.
    # ------------------------------------------------------------
    # 5. Secondary consequence information.
    #
    # Tactical motif reasoning remains primary, but a concrete consequence
    # can still be surfaced as a practical effect when useful.
    # ------------------------------------------------------------

    if consequence_text:
        if tactical_motif_reason:
            if practical_effect is None:
                practical_effect = consequence_text
        elif tactical_effect is None:
            tactical_effect = consequence_text

    # ------------------------------------------------------------
    # 6. Stronger candidate / missed resource.
    # ------------------------------------------------------------

    better_move = context.best_move

    better_move_text: Optional[str] = None

    if better_move and board_before is not None:
        better_move_text = _move_description(board_before, better_move)

    missed_resource = None

    if better_move_text:
        if tactical_motif_reason:
            missed_resource = (
                f"{better_move_text} was the stronger tactical resource."
            )

        elif priority_reason:
            missed_resource = (
                f"{better_move_text} was the stronger candidate because "
                "it executes the useful idea more directly."
            )

        elif classification_label in {
            "blunder",
            "mistake",
            "inaccuracy",
        }:
            missed_resource = (
                f"{better_move_text} was the stronger engine candidate "
                "and should have been compared before committing to the move."
            )

    # ------------------------------------------------------------
    # 7. Candidate comparison remains factual and compact.
    # ------------------------------------------------------------

    candidate_comparison: list[str] = []

    if better_move_text:
        candidate_comparison.append(
            f"Best engine candidate: {better_move_text}"
        )
    elif context.best_move:
        candidate_comparison.append(
            f"Best engine candidate: {context.best_move}"
        )

    if context.san:
        candidate_comparison.append(
            f"Played move: {context.san}"
        )

    return ChessReasoning(
        primary_reason=primary_reason,
        tactical_effect=tactical_effect,
        strategic_effect=strategic_effect,
        practical_effect=practical_effect,
        missed_resource=missed_resource,
        better_move=better_move_text or better_move,
        # A candidate move alone does not explain why it is better.
        better_move_reason=None,
        candidate_comparison=candidate_comparison,
    )



def inspect_reasoning_position(fen: str) -> dict[str, Any]:
    board = chess.Board(fen)

    forcing_moves = []

    for move in board.legal_moves:
        if board.gives_check(move) or board.is_capture(move):
            forcing_moves.append(board.san(move))

    return {
        "fen": fen,
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
        "king_white": chess.square_name(board.king(chess.WHITE)),
        "king_black": chess.square_name(board.king(chess.BLACK)),
        "in_check": board.is_check(),
        "forcing_moves": forcing_moves[:20],
        "legal_moves": board.legal_moves.count(),
    }

