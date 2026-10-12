from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    chesscom_uuid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    url: Mapped[str | None] = mapped_column(String(500))
    pgn: Mapped[str] = mapped_column(Text)

    played_at: Mapped[datetime | None] = mapped_column(DateTime)

    white: Mapped[str | None] = mapped_column(String(100))
    black: Mapped[str | None] = mapped_column(String(100))

    white_rating: Mapped[int | None] = mapped_column(Integer)
    black_rating: Mapped[int | None] = mapped_column(Integer)

    result: Mapped[str | None] = mapped_column(String(10))
    time_control: Mapped[str | None] = mapped_column(String(50))

    eco: Mapped[str | None] = mapped_column(String(20))
    opening: Mapped[str | None] = mapped_column(String(200))

    termination: Mapped[str | None] = mapped_column(String(100))

    analyzed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    analysis_version: Mapped[str | None] = mapped_column(String(50))

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    moves: Mapped[list["GameMove"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )


class GameMove(Base):
    __tablename__ = "game_moves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        index=True,
    )

    ply: Mapped[int] = mapped_column(Integer)
    move_number: Mapped[int] = mapped_column(Integer)

    color: Mapped[str] = mapped_column(String(1))

    san: Mapped[str] = mapped_column(String(20))
    uci: Mapped[str] = mapped_column(String(10))

    fen_before: Mapped[str] = mapped_column(Text)
    fen_after: Mapped[str] = mapped_column(Text)

    phase: Mapped[str | None] = mapped_column(String(20))

    evaluation_before: Mapped[float | None] = mapped_column(Float)
    evaluation_after: Mapped[float | None] = mapped_column(Float)

    best_move: Mapped[str | None] = mapped_column(String(10))
    best_pv: Mapped[str | None] = mapped_column(Text)

    centipawn_loss: Mapped[float | None] = mapped_column(Float)
    win_probability_loss: Mapped[float | None] = mapped_column(Float)
    accuracy: Mapped[float | None] = mapped_column(Float)

    classification: Mapped[str | None] = mapped_column(String(30))
    second_best_loss_gap: Mapped[float | None] = mapped_column(Float)
    sacrifice_given: Mapped[float | None] = mapped_column(Float)
    classification_version: Mapped[str | None] = mapped_column(String(50))

    clock_seconds: Mapped[float | None] = mapped_column(Float)
    thinking_time: Mapped[float | None] = mapped_column(Float)

    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)

    game: Mapped["Game"] = relationship(
        back_populates="moves",
    )


class Motif(Base):
    __tablename__ = "motifs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        index=True,
    )

    move_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_moves.id", ondelete="CASCADE"),
        index=True,
    )

    motif: Mapped[str] = mapped_column(String(100))
    side: Mapped[str | None] = mapped_column(String(1))

    severity: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)


class TrainingPosition(Base):
    __tablename__ = "training_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        index=True,
    )

    move_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_moves.id", ondelete="CASCADE"),
        index=True,
    )

    fen: Mapped[str] = mapped_column(Text)

    category: Mapped[str] = mapped_column(String(50))

    source: Mapped[str] = mapped_column(String(50))

    difficulty: Mapped[str | None] = mapped_column(String(30))

    solved: Mapped[bool] = mapped_column(Boolean, default=False)

    attempts: Mapped[int] = mapped_column(Integer, default=0)


class ProfileSnapshot(Base):
    __tablename__ = "profile_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    games_analyzed: Mapped[int] = mapped_column(Integer, default=0)

    wins: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)

    win_rate: Mapped[float | None] = mapped_column(Float)
    average_accuracy: Mapped[float | None] = mapped_column(Float)
    average_cpl: Mapped[float | None] = mapped_column(Float)

    blunders_per_game: Mapped[float | None] = mapped_column(Float)
    mistakes_per_game: Mapped[float | None] = mapped_column(Float)
    inaccuracies_per_game: Mapped[float | None] = mapped_column(Float)

    strongest_phase: Mapped[str | None] = mapped_column(String(30))
    weakest_phase: Mapped[str | None] = mapped_column(String(30))

    strongest_motif: Mapped[str | None] = mapped_column(String(100))
    weakest_motif: Mapped[str | None] = mapped_column(String(100))

    summary: Mapped[str | None] = mapped_column(Text)

class EngineLine(Base):
    __tablename__ = "engine_lines"

    fen: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    multipv_rank: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    move_uci: Mapped[str] = mapped_column(String(10))

    eval_cp: Mapped[int | None] = mapped_column(Integer)

    mate: Mapped[int | None] = mapped_column(Integer)

    pv: Mapped[str] = mapped_column(
        Text,
        default="[]",
    )

    depth: Mapped[int] = mapped_column(Integer)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )


# ============================================================
# CHESSMATE / PRESTON FEATURE LAYER
# ============================================================

class Puzzle(Base):
    __tablename__ = "puzzles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Position / solution
    fen: Mapped[str] = mapped_column(Text, index=True)
    side_to_move: Mapped[str | None] = mapped_column(String(1))
    solution_uci: Mapped[str | None] = mapped_column(Text)
    solution_pv: Mapped[str | None] = mapped_column(Text)

    # Classification
    themes: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(50), index=True)
    difficulty: Mapped[str | None] = mapped_column(String(30))

    # Origin
    source: Mapped[str | None] = mapped_column(String(50), index=True)
    source_game_id: Mapped[int | None] = mapped_column(
        ForeignKey("games.id", ondelete="SET NULL"),
        index=True
    )
    source_move_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_moves.id", ondelete="SET NULL"),
        index=True
    )
    source_motif: Mapped[str | None] = mapped_column(String(100), index=True)

    # Metadata
    explanation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    solved_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)


class PuzzleAttempt(Base):
    __tablename__ = "puzzle_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    puzzle_id: Mapped[int] = mapped_column(
        ForeignKey("puzzles.id", ondelete="CASCADE"),
        index=True
    )

    username: Mapped[str | None] = mapped_column(
        String(100),
        index=True
    )

    solved: Mapped[bool] = mapped_column(Boolean, default=False)

    # User's attempted line / move
    attempted_move: Mapped[str | None] = mapped_column(String(10))
    attempted_pv: Mapped[str | None] = mapped_column(Text)

    # Training metadata
    time_seconds: Mapped[float | None] = mapped_column(Float)
    streak: Mapped[int] = mapped_column(Integer, default=0)

    attempted_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True
    )


class PlayerSetting(Base):
    __tablename__ = "player_settings"

    username: Mapped[str] = mapped_column(
        String(100),
        primary_key=True
    )

    auto_analyze: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    auto_depth: Mapped[int] = mapped_column(
        Integer,
        default=18
    )

    auto_workers: Mapped[int] = mapped_column(
        Integer,
        default=4
    )

    auto_batch: Mapped[int] = mapped_column(
        Integer,
        default=50
    )

    auto_time_format: Mapped[str | None] = mapped_column(
        String(30)
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(
        String(100),
        primary_key=True
    )

    value: Mapped[str] = mapped_column(
        Text,
        default=""
    )


class CoachExplanation(Base):
    __tablename__ = "coach_explanations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    # Can belong to a game move or a puzzle.
    game_id: Mapped[int | None] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        index=True
    )

    move_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_moves.id", ondelete="CASCADE"),
        index=True
    )

    puzzle_id: Mapped[int | None] = mapped_column(
        ForeignKey("puzzles.id", ondelete="CASCADE"),
        index=True
    )

    provider: Mapped[str | None] = mapped_column(
        String(50)
    )

    # Versioned so explanations can be regenerated safely.
    version: Mapped[str | None] = mapped_column(
        String(50)
    )

    explanation: Mapped[str] = mapped_column(
        Text
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


class Narrative(Base):
    __tablename__ = "narratives"

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"),
        primary_key=True
    )

    narrative: Mapped[str] = mapped_column(
        Text
    )

    provider: Mapped[str | None] = mapped_column(
        String(50)
    )

    version: Mapped[str | None] = mapped_column(
        String(50)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
