"""Domain models matching spec §47 (RAG data model) and §8 (book structure).

These are the Pydantic shapes used across API request/response bodies.
`app/db/models.py` mirrors these as SQLModel ORM tables — kept as two files
on purpose so the API contract doesn't silently change when the DB schema
does.
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class BookStatus(str, Enum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Book(BaseModel):
    id: str
    title: str
    author: Optional[str] = None
    total_pages: Optional[int] = None
    status: BookStatus = BookStatus.uploaded
    extraction_method: Optional[str] = None  # "mineru" | "docling" | "local_pdf"
    created_at: datetime


class Chapter(BaseModel):
    id: str
    book_id: str
    order_index: int
    title: str
    start_page: int
    end_page: int


class Section(BaseModel):
    id: str
    chapter_id: str
    book_id: str
    order_index: int
    title: str
    start_page: int
    end_page: int


class Subsection(BaseModel):
    id: str
    section_id: str
    order_index: int
    title: str
    start_page: int
    end_page: int


class Page(BaseModel):
    id: str
    book_id: str
    page_number: int
    image_ref: Optional[str] = None  # rasterized page, for the source viewer


class SourceBlockType(str, Enum):
    paragraph = "paragraph"
    heading = "heading"
    caption = "caption"
    diagram = "diagram"
    table = "table"
    move_text = "move_text"


class SourceBlock(BaseModel):
    id: str
    book_id: str
    page_id: str
    section_id: Optional[str] = None
    subsection_id: Optional[str] = None
    block_type: SourceBlockType
    order_index: int
    text: Optional[str] = None
    image_ref: Optional[str] = None


class Concept(BaseModel):
    id: str
    book_id: str
    name: str  # e.g. "weak square", "fork", "isolated pawn"
    category: str  # strategic | tactical | endgame | opening


class Lesson(BaseModel):
    id: str
    section_id: str
    order_index: int
    concept_ids: list[str] = Field(default_factory=list)
    source_block_ids: list[str] = Field(default_factory=list)


class Example(BaseModel):
    id: str
    lesson_id: str
    source_block_id: str
    position_id: Optional[str] = None


class Game(BaseModel):
    id: str
    book_id: str
    section_id: Optional[str] = None
    white: Optional[str] = None
    black: Optional[str] = None
    pgn: str  # raw extracted move text; validated via python-chess when available
    pgn_validated: bool = False
    source_block_id: str


class Variation(BaseModel):
    id: str
    parent_position_id: str
    label: str  # "Main line", "Variation A", ...
    moves_san: list[str]


class Position(BaseModel):
    id: str
    book_id: str
    source_block_id: str
    page_id: str
    fen: Optional[str] = None  # null if not confidently reconstructed
    verified: bool = False
    raw_image_ref: str  # always kept, even when fen is null (§46)
    to_move: Optional[str] = None  # "white" | "black", if known


class PuzzleSourceType(str, Enum):
    book = "book"
    generated = "generated"  # must be labeled "ChessMate application exercise" (§17)


class Puzzle(BaseModel):
    id: str
    book_id: str
    chapter_id: str
    section_id: str
    page_id: str
    position_id: str
    source: PuzzleSourceType
    original_text: Optional[str] = None  # verbatim prompt, book puzzles only
    solution_line_san: list[str]
    author_explanation: Optional[str] = None


class Exercise(BaseModel):
    """Generated-only practice items, distinct from book Puzzles (§17, §43)."""
    id: str
    book_id: str
    concept_id: str
    position_id: str
    solution_line_san: list[str]
    source: PuzzleSourceType = PuzzleSourceType.generated


class Progress(BaseModel):
    id: str
    user_id: str
    book_id: str
    current_section_id: Optional[str] = None
    pages_processed: int = 0
    sections_completed: list[str] = Field(default_factory=list)
    sections_skipped: list[str] = Field(default_factory=list)
    updated_at: datetime


class AttemptResult(str, Enum):
    correct = "correct"
    incorrect = "incorrect"
    hint_used = "hint_used"
    solution_shown = "solution_shown"


class Attempt(BaseModel):
    id: str
    user_id: str
    puzzle_id: Optional[str] = None
    exercise_id: Optional[str] = None
    concept_id: Optional[str] = None
    move_san: Optional[str] = None
    result: AttemptResult
    created_at: datetime
