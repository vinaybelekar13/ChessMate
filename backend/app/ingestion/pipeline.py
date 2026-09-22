"""Orchestrates the full PDF -> curriculum pipeline (spec §6, §50).

Reports step-by-step status so `GET /books/{id}/ingestion-status` reflects
real progress rather than a fake timer, per §50's "show real stages"
requirement.
"""
from __future__ import annotations
import json
from enum import Enum

from sqlmodel import Session, select

from app.ingestion import mineru_adapter, docling_adapter, local_pdf_adapter, structure_detector, chess_extractor
from app.chess import validation as chess_validation
from app.db import models as db


class IngestionStep(str, Enum):
    reading_pages = "Reading pages"
    understanding_structure = "Understanding structure"
    finding_chapters = "Finding chapters"
    finding_sections = "Finding sections"
    finding_diagrams = "Finding diagrams"
    finding_positions = "Finding chess positions"
    finding_games = "Finding games"
    finding_puzzles = "Finding puzzles"
    building_lessons = "Building lessons"
    building_course = "Building your course"
    done = "Book ready"
    failed = "Failed"


class IngestionProgressReporter:
    """Swap for a real pub/sub (Redis, DB row update) — kept in-memory here."""

    def __init__(self):
        self._state: dict[str, dict] = {}

    def set(self, book_id: str, step: IngestionStep, counts: dict | None = None):
        self._state[book_id] = {"step": step.value, "counts": counts or {}}

    def get(self, book_id: str) -> dict:
        return self._state.get(book_id, {"step": "unknown", "counts": {}})


progress_reporter = IngestionProgressReporter()


def _extract_blocks(pdf_path: str, output_dir: str) -> tuple[list, str]:
    """Real fallback chain: MinerU -> Docling -> local pdfplumber extraction.

    Returns (blocks, extraction_method) where extraction_method is one of
    "mineru" | "docling" | "local_pdf" — recorded on the Book row so the app
    never silently claims a higher-fidelity extractor was used than actually
    ran (per the "never fabricate" requirement).
    """
    try:
        return mineru_adapter.parse(pdf_path, output_dir), "mineru"
    except mineru_adapter.MinerUError:
        pass
    try:
        return docling_adapter.parse(pdf_path), "docling"
    except docling_adapter.DoclingError:
        pass
    return local_pdf_adapter.parse(pdf_path), "local_pdf"


def _clear_existing_ingestion(session: Session, book_id: str) -> None:
    """Delete any rows a previous ingestion run for this book_id already
    created, so calling /books/{id}/ingest again (the documented "retry a
    failed run" path) is idempotent instead of appending duplicate chapters/
    sections. Progress/Attempt rows are left untouched — a retry is expected
    to happen before real learner progress exists against this book."""
    from sqlmodel import delete

    section_ids = session.exec(
        select(db.Section.id).where(db.Section.book_id == book_id)
    ).all()
    if section_ids:
        session.exec(delete(db.Subsection).where(db.Subsection.section_id.in_(section_ids)))

    for model in (db.Puzzle, db.Position, db.Game, db.SourceBlock, db.Page,
                  db.Section, db.Chapter):
        session.exec(delete(model).where(model.book_id == book_id))
    session.commit()


def ingest_book(session: Session, book: db.Book, pdf_path: str, output_dir: str) -> None:
    book_id = book.id
    try:
        _clear_existing_ingestion(session, book_id)
        progress_reporter.set(book_id, IngestionStep.reading_pages)
        blocks, extraction_method = _extract_blocks(pdf_path, output_dir)
        book.extraction_method = extraction_method
        session.add(book)
        session.commit()

        progress_reporter.set(book_id, IngestionStep.understanding_structure)
        hierarchy = structure_detector.build_hierarchy(blocks)

        progress_reporter.set(book_id, IngestionStep.finding_chapters,
                               {"chapters": len(hierarchy)})
        chapters = _persist_chapters(session, book_id, hierarchy)

        progress_reporter.set(book_id, IngestionStep.finding_sections,
                               {"sections": sum(len(c.children) for c in hierarchy)})
        sections = _persist_sections(session, chapters, hierarchy)

        # Pages + SourceBlocks: the provenance backbone everything else (positions,
        # puzzles, games, the source panel) points back to. Previously stubbed
        # with empty ids — genuinely persisted now.
        pages_by_number = _persist_pages(session, book_id, blocks)
        source_blocks_by_raw_id = _persist_source_blocks(session, book_id, blocks, pages_by_number, sections)

        progress_reporter.set(book_id, IngestionStep.finding_diagrams)
        diagram_candidates = chess_extractor.find_diagram_candidates(blocks)

        progress_reporter.set(book_id, IngestionStep.finding_positions,
                               {"diagrams": len(diagram_candidates)})
        positions_by_raw_id = _persist_positions(
            session, book_id, diagram_candidates, pages_by_number, source_blocks_by_raw_id
        )

        progress_reporter.set(book_id, IngestionStep.finding_games)
        move_blocks = chess_extractor.find_move_text_blocks(blocks)
        _persist_games(session, book_id, move_blocks, sections, source_blocks_by_raw_id)

        progress_reporter.set(book_id, IngestionStep.finding_puzzles)
        puzzle_candidates = chess_extractor.find_puzzle_candidates(blocks)
        _persist_puzzles(
            session, book_id, puzzle_candidates, diagram_candidates,
            positions_by_raw_id, sections, chapters, pages_by_number, source_blocks_by_raw_id,
        )

        progress_reporter.set(book_id, IngestionStep.building_lessons)
        # Concept/lesson extraction from prose is an LLM-assisted step in a
        # real build (classify each section's dominant concepts) — stubbed
        # here since it needs the LLM adapter wired to a real key.

        progress_reporter.set(book_id, IngestionStep.building_course)
        # Search-mode indexing happens here — LightRAG if installed, else the
        # local SQLite FTS index (see app/rag/local_search.py); either way it
        # only affects Search Mode, never curriculum order (ARCHITECTURE.md §2).
        try:
            from app.rag.lightrag_adapter import get_index_for_book
            index = get_index_for_book(book_id)
            for raw_id, sb in source_blocks_by_raw_id.items():
                if sb.text:
                    index.index_block(sb.text, section_id=sb.section_id, page_number=None)
        except (ImportError, NotImplementedError):
            from app.rag.local_search import index_book_for_local_search
            index_book_for_local_search(session, book_id)

        book.status = "ready"
        book.total_pages = max((b.page_number for b in blocks), default=0)
        session.add(book)
        session.commit()
        progress_reporter.set(book_id, IngestionStep.done)

    except Exception:
        book.status = "failed"
        session.add(book)
        session.commit()
        progress_reporter.set(book_id, IngestionStep.failed)
        raise


def _persist_chapters(session: Session, book_id: str, hierarchy) -> list[db.Chapter]:
    out = []
    for node in hierarchy:
        ch = db.Chapter(book_id=book_id, order_index=node.order_index, title=node.title,
                         start_page=node.start_page, end_page=node.end_page)
        session.add(ch)
        out.append(ch)
    session.commit()
    return out


def _persist_sections(session: Session, chapters: list[db.Chapter], hierarchy) -> list[db.Section]:
    out = []
    for chapter_db, node in zip(chapters, hierarchy):
        for s in node.children:
            sec = db.Section(chapter_id=chapter_db.id, book_id=chapter_db.book_id,
                              order_index=s.order_index, title=s.title,
                              start_page=s.start_page, end_page=s.end_page)
            session.add(sec)
            out.append(sec)
    session.commit()
    return out


def _persist_pages(session: Session, book_id: str, blocks: list) -> dict[int, db.Page]:
    pages_by_number: dict[int, db.Page] = {}
    for page_number in sorted({b.page_number for b in blocks}):
        page = db.Page(book_id=book_id, page_number=page_number)
        session.add(page)
        pages_by_number[page_number] = page
    session.commit()
    return pages_by_number


def _section_for_page(sections: list[db.Section], page_number: int) -> db.Section | None:
    for s in sections:
        if s.start_page <= page_number <= s.end_page:
            return s
    return None


def _persist_source_blocks(
    session: Session, book_id: str, blocks: list,
    pages_by_number: dict[int, db.Page], sections: list[db.Section],
) -> dict[int, db.SourceBlock]:
    """Keyed by `id(raw_block)` (the in-memory RawBlock, not a DB id) so
    later steps that hold references to the same RawBlock objects (puzzle
    candidates, diagram candidates, move blocks) can look up the persisted
    row without re-matching on text.
    """
    out: dict[int, db.SourceBlock] = {}
    for b in blocks:
        section = _section_for_page(sections, b.page_number)
        sb = db.SourceBlock(
            book_id=book_id,
            page_id=pages_by_number[b.page_number].id,
            section_id=section.id if section else None,
            block_type=b.block_type,
            order_index=b.order_index,
            text=b.text,
            image_ref=b.image_ref,
        )
        session.add(sb)
        out[id(b)] = sb
    session.commit()
    return out


def _persist_positions(
    session: Session, book_id: str, diagram_candidates,
    pages_by_number: dict[int, db.Page], source_blocks_by_raw_id: dict[int, db.SourceBlock],
) -> dict[int, db.Position]:
    """Returns a map keyed by id(diagram_candidate) -> persisted Position,
    so puzzle linking can find "the Position for this diagram" directly."""
    out: dict[int, db.Position] = {}
    for cand in diagram_candidates:
        fen, confidence = None, 0.0
        try:
            fen, confidence = chess_extractor.reconstruct_position_from_diagram(
                cand.block.image_ref or ""
            )
        except NotImplementedError:
            pass  # expected until a board-vision model is wired in — see chess_extractor.py
        source_block = source_blocks_by_raw_id.get(id(cand.block))
        pos = db.Position(
            book_id=book_id,
            source_block_id=source_block.id if source_block else "",
            page_id=pages_by_number[cand.block.page_number].id,
            fen=fen if confidence >= 0.9 else None,
            verified=confidence >= 0.9,
            raw_image_ref=cand.block.image_ref or "",
        )
        session.add(pos)
        out[id(cand)] = pos
    session.commit()
    return out


def _persist_games(
    session: Session, book_id: str, move_blocks,
    sections: list[db.Section], source_blocks_by_raw_id: dict[int, db.SourceBlock],
) -> list[db.Game]:
    """Stores each detected move-text block as a Game row. Validates with
    python-chess when it's installed; when it isn't, still stores the raw
    extracted move text (it came from the book, so storing it isn't
    fabrication) but leaves `pgn_validated=False` rather than pretending it
    was checked.
    """
    out = []
    for b in move_blocks:
        section = _section_for_page(sections, b.page_number)
        source_block = source_blocks_by_raw_id.get(id(b))
        validated = False
        try:
            validated = chess_validation.is_valid_movetext(b.text or "")
        except RuntimeError:
            pass  # python-chess not installed — see app/chess/validation.py
        game = db.Game(
            book_id=book_id,
            section_id=section.id if section else None,
            pgn=b.text or "",
            pgn_validated=validated,
            source_block_id=source_block.id if source_block else "",
        )
        session.add(game)
        out.append(game)
    session.commit()
    return out


def _nearest_diagram_on_same_page(diagram_candidates, page_number: int):
    same_page = [d for d in diagram_candidates if d.block.page_number == page_number]
    return same_page[0] if same_page else None


def _persist_puzzles(
    session: Session, book_id: str, puzzle_candidates, diagram_candidates,
    positions_by_raw_id: dict[int, db.Position], sections: list[db.Section],
    chapters: list[db.Chapter], pages_by_number: dict[int, db.Page],
    source_blocks_by_raw_id: dict[int, db.SourceBlock],
) -> list[db.Puzzle]:
    """Links each puzzle-prompt candidate to the nearest diagram on the same
    page (per spec: a caption alone isn't an interactive puzzle without a
    position). When no diagram is found nearby, a placeholder unverified
    Position is created (fen=None) rather than skipping the puzzle entirely —
    the frontend is expected to show "position requires verification" for it.
    No solution is ever invented: `solution_line_san` stays an empty list
    unless real solution-move extraction is implemented, and the puzzle's
    `original_text` preserves the book's own prompt for provenance.
    """
    out = []
    chapters_by_id = {c.id: c for c in chapters}
    for cand in puzzle_candidates:
        page_number = cand.block.page_number
        section = _section_for_page(sections, page_number)
        if not section:
            continue  # can't place a puzzle we can't locate in the curriculum

        diagram = _nearest_diagram_on_same_page(diagram_candidates, page_number)
        if diagram is not None and id(diagram) in positions_by_raw_id:
            position = positions_by_raw_id[id(diagram)]
        else:
            position = db.Position(
                book_id=book_id, source_block_id="", page_id=pages_by_number[page_number].id,
                fen=None, verified=False, raw_image_ref="",
            )
            session.add(position)
            session.commit()

        puzzle = db.Puzzle(
            book_id=book_id,
            chapter_id=section.chapter_id,
            section_id=section.id,
            page_id=pages_by_number[page_number].id,
            position_id=position.id,
            source="book",
            original_text=cand.block.text,
            solution_line_san=json.dumps([]),  # never invented — see docstring
            author_explanation=None,
        )
        session.add(puzzle)
        out.append(puzzle)
    session.commit()
    return out
