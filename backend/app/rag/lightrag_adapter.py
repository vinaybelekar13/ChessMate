"""LightRAG adapter (spec §7B). UNTESTED — could not install `lightrag-hku`
(or whatever its current package name is) in the build sandbox; written
against LightRAG's documented usage pattern
(https://github.com/HKUDS/LightRAG). Verify the import path/API against the
version you actually install.

CRITICAL CONSTRAINT (spec §3): this module is used for Search Mode only. It
must never be called by anything that decides curriculum order — see
app/rag/book_rag.py, where the ordering functions are plain SQL and this
module isn't imported by them at all.
"""
from __future__ import annotations
from dataclasses import dataclass

from app.config import settings


@dataclass
class RetrievedChunk:
    text: str
    book_id: str
    section_id: str | None
    page_number: int | None
    score: float


class LightRAGIndex:
    """One LightRAG working directory per book, per spec §52 (independent
    knowledge base per book)."""

    def __init__(self, book_id: str, working_dir: str):
        self.book_id = book_id
        self.working_dir = working_dir
        self._rag = None  # real: lightrag.LightRAG(working_dir=working_dir, llm_model_func=...)

    def index_block(self, block_text: str, *, section_id: str | None, page_number: int | None) -> None:
        """Insert one SourceBlock's text with structural metadata attached,
        so every retrieval result can be traced back to book order even
        though retrieval itself is semantic.

        Real sketch:
            self._rag.insert(block_text, metadata={
                "section_id": section_id, "page_number": page_number,
            })
        """
        raise NotImplementedError("Install lightrag and wire up self._rag before calling this.")

    def query(self, question: str, mode: str = "hybrid",
              section_id_scope: str | None = None) -> list[RetrievedChunk]:
        """Search Mode entry point. `section_id_scope`, when given, restricts
        results to one section (used by `searchSection`/`getRelatedConcepts`
        style narrow lookups); omit it for whole-book search.

        Real sketch:
            result = self._rag.query(question, param=QueryParam(mode=mode))
        """
        raise NotImplementedError("Install lightrag and wire up self._rag before calling this.")


def get_index_for_book(book_id: str) -> LightRAGIndex:
    working_dir = f"{settings.storage_root}/lightrag/{book_id}"
    return LightRAGIndex(book_id, working_dir)
