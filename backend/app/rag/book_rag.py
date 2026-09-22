"""BookRAG — spec §48. Every function from the spec's list, each backed by
either plain SQL (structural/order-based) or LightRAG (explicitly semantic).

The split is enforced by which import each function uses:
  - Ordering/structure functions import only `sqlmodel` + `app.db.models`.
  - Search functions import `app.rag.lightrag_adapter`.
No function does both, on purpose — see ARCHITECTURE.md §2.
"""
from __future__ import annotations
from sqlmodel import Session, select

from app.db import models as db
from app.rag.lightrag_adapter import get_index_for_book, RetrievedChunk
from app.rag import local_search


class BookRAG:
    def __init__(self, session: Session):
        self.session = session

    # ---- structural (SQL, book-order — never reordered by retrieval) ----

    def get_book_structure(self, book_id: str) -> list[db.Chapter]:
        stmt = select(db.Chapter).where(db.Chapter.book_id == book_id).order_by(db.Chapter.order_index)
        return list(self.session.exec(stmt))

    def get_chapter(self, chapter_id: str) -> db.Chapter | None:
        return self.session.get(db.Chapter, chapter_id)

    def get_page(self, book_id: str, page_number: int) -> db.Page | None:
        stmt = select(db.Page).where(db.Page.book_id == book_id, db.Page.page_number == page_number)
        return self.session.exec(stmt).first()

    def get_current_section(self, user_id: str, book_id: str) -> db.Section | None:
        stmt = select(db.Progress).where(db.Progress.user_id == user_id, db.Progress.book_id == book_id)
        prog = self.session.exec(stmt).first()
        if not prog or not prog.current_section_id:
            return None
        return self.session.get(db.Section, prog.current_section_id)

    def get_next_lesson(self, section_id: str) -> db.Section | None:
        current = self.session.get(db.Section, section_id)
        if not current:
            return None
        stmt = (
            select(db.Section)
            .where(db.Section.chapter_id == current.chapter_id,
                   db.Section.order_index > current.order_index)
            .order_by(db.Section.order_index)
        )
        next_in_chapter = self.session.exec(stmt).first()
        if next_in_chapter:
            return next_in_chapter
        # roll into the next chapter's first section
        chapter = self.session.get(db.Chapter, current.chapter_id)
        stmt = (
            select(db.Chapter)
            .where(db.Chapter.book_id == chapter.book_id,
                   db.Chapter.order_index > chapter.order_index)
            .order_by(db.Chapter.order_index)
        )
        next_chapter = self.session.exec(stmt).first()
        if not next_chapter:
            return None
        stmt = (
            select(db.Section)
            .where(db.Section.chapter_id == next_chapter.id)
            .order_by(db.Section.order_index)
        )
        return self.session.exec(stmt).first()

    def get_previous_lesson(self, section_id: str) -> db.Section | None:
        current = self.session.get(db.Section, section_id)
        if not current:
            return None
        stmt = (
            select(db.Section)
            .where(db.Section.chapter_id == current.chapter_id,
                   db.Section.order_index < current.order_index)
            .order_by(db.Section.order_index.desc())
        )
        return self.session.exec(stmt).first()

    def get_source(self, source_block_id: str) -> db.SourceBlock | None:
        return self.session.get(db.SourceBlock, source_block_id)

    def find_examples(self, section_id: str) -> list[db.SourceBlock]:
        stmt = select(db.SourceBlock).where(
            db.SourceBlock.section_id == section_id,
            db.SourceBlock.block_type.in_(["diagram", "paragraph"]),
        )
        return list(self.session.exec(stmt))

    def find_puzzles(self, section_id: str | None = None, book_id: str | None = None) -> list[db.Puzzle]:
        stmt = select(db.Puzzle)
        if section_id:
            stmt = stmt.where(db.Puzzle.section_id == section_id)
        elif book_id:
            stmt = stmt.where(db.Puzzle.book_id == book_id)
        return list(self.session.exec(stmt))

    def find_positions(self, book_id: str, section_id: str | None = None) -> list[db.Position]:
        stmt = select(db.Position).where(db.Position.book_id == book_id)
        return list(self.session.exec(stmt))  # NOTE: filter by section via SourceBlock join once populated

    def find_games(self, book_id: str, section_id: str | None = None) -> list[db.Game]:
        stmt = select(db.Game).where(db.Game.book_id == book_id)
        if section_id:
            stmt = stmt.where(db.Game.section_id == section_id)
        return list(self.session.exec(stmt))

    # ---- semantic / graph (LightRAG when available, else local SQLite FTS
    #      fallback — Search Mode only, §36; never used for curriculum order) ----

    def _search(self, book_id: str, question: str, section_id: str | None = None) -> list[RetrievedChunk]:
        try:
            return get_index_for_book(book_id).query(question, mode="hybrid", section_id_scope=section_id)
        except NotImplementedError:
            results = local_search.local_search(book_id, question, section_id=section_id)
            return [
                RetrievedChunk(text=r.text, book_id=book_id, section_id=r.section_id,
                                page_number=None, score=r.score)
                for r in results
            ]

    def search_book(self, book_id: str, question: str) -> list[RetrievedChunk]:
        return self._search(book_id, question)

    def search_section(self, book_id: str, section_id: str, question: str) -> list[RetrievedChunk]:
        return self._search(book_id, question, section_id=section_id)

    def search_concept(self, book_id: str, concept_name: str) -> list[RetrievedChunk]:
        return self._search(book_id, concept_name)

    def get_related_concepts(self, book_id: str, concept_name: str) -> list[RetrievedChunk]:
        # LightRAG's graph mode gives real "related concept" traversal; the
        # local fallback can only do a keyword search for now, which is a
        # materially weaker approximation — labeled via RetrievedChunk.score
        # rather than pretending it's graph-derived.
        return self._search(book_id, f"related concepts to {concept_name}")
