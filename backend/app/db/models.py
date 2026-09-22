"""SQLModel ORM tables. Mirrors app/models/schemas.py.

Kept deliberately boring/relational: curriculum order comes from `order_index`
columns and plain `ORDER BY`, not from any embedding or graph traversal — see
ARCHITECTURE.md §2. Generate real Alembic migrations from this once you have
a database to point at.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


def new_id() -> str:
    return str(uuid.uuid4())


class Book(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    title: str
    author: Optional[str] = None
    total_pages: Optional[int] = None
    status: str = "uploaded"
    pdf_storage_ref: str
    extraction_method: Optional[str] = None  # "mineru" | "docling" | "local_pdf" — never fabricated
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Chapter(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    order_index: int = Field(index=True)
    title: str
    start_page: int
    end_page: int


class Section(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    chapter_id: str = Field(foreign_key="chapter.id", index=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    order_index: int = Field(index=True)
    title: str
    start_page: int
    end_page: int


class Subsection(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    section_id: str = Field(foreign_key="section.id", index=True)
    order_index: int = Field(index=True)
    title: str
    start_page: int
    end_page: int


class Page(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    page_number: int = Field(index=True)
    image_ref: Optional[str] = None


class SourceBlock(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    page_id: str = Field(foreign_key="page.id", index=True)
    section_id: Optional[str] = Field(default=None, foreign_key="section.id", index=True)
    subsection_id: Optional[str] = Field(default=None, foreign_key="subsection.id")
    block_type: str
    order_index: int
    text: Optional[str] = None
    image_ref: Optional[str] = None


class Concept(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    name: str = Field(index=True)
    category: str


class Position(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    source_block_id: str = Field(foreign_key="sourceblock.id")
    page_id: str = Field(foreign_key="page.id")
    fen: Optional[str] = None
    verified: bool = False
    raw_image_ref: str
    to_move: Optional[str] = None


class Puzzle(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    chapter_id: str = Field(foreign_key="chapter.id")
    section_id: str = Field(foreign_key="section.id", index=True)
    page_id: str = Field(foreign_key="page.id")
    position_id: str = Field(foreign_key="position.id")
    source: str = "book"  # "book" | "generated" — see §17
    original_text: Optional[str] = None
    solution_line_san: str = "[]"  # JSON-encoded list
    author_explanation: Optional[str] = None


class Game(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    section_id: Optional[str] = Field(default=None, foreign_key="section.id")
    white: Optional[str] = None
    black: Optional[str] = None
    pgn: str
    pgn_validated: bool = False  # True only if python-chess actually parsed it legally
    source_block_id: str = Field(foreign_key="sourceblock.id")


class Progress(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(index=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    current_section_id: Optional[str] = Field(default=None, foreign_key="section.id")
    pages_processed: int = 0
    sections_completed: str = "[]"  # JSON-encoded list of section ids
    sections_skipped: str = "[]"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Attempt(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: str = Field(index=True)
    puzzle_id: Optional[str] = Field(default=None, foreign_key="puzzle.id")
    exercise_id: Optional[str] = None
    concept_id: Optional[str] = Field(default=None, foreign_key="concept.id")
    move_san: Optional[str] = None
    result: str  # correct | incorrect | hint_used | solution_shown
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
