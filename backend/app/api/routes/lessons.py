"""Curriculum-mode lesson endpoints (spec §10, §11, §30-§33, §49)."""
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import get_session
from app.coach.book_coach import BookCoach
from app.rag.book_rag import BookRAG

router = APIRouter()


class SearchQuery(BaseModel):
    query: str
    section_id: str | None = None


class AskQuery(BaseModel):
    question: str


@router.post("/{book_id}/start")
def start_book(book_id: str, user_id: str, session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    section = coach.start_book()
    return {"section": section}


@router.get("/{book_id}/resume")
def resume(book_id: str, user_id: str, session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    return coach.resume_progress()


@router.post("/{book_id}/continue")
def continue_lesson(book_id: str, user_id: str, session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    return coach.continue_lesson()


@router.post("/{book_id}/sections/{section_id}/skip")
def skip_section(book_id: str, section_id: str, user_id: str, session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    coach.skip_section(section_id)
    return {"skipped": section_id}


@router.get("/{book_id}/sections/{section_id}/teach")
def teach_section(book_id: str, section_id: str, user_id: str, depth: str = "normal",
                   session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    return coach.teach_section(section_id, depth=depth)  # {"mode": ..., "text": ...}


@router.get("/{book_id}/curriculum/current")
def curriculum_current(book_id: str, user_id: str, session: Session = Depends(get_session)):
    rag = BookRAG(session)
    return rag.get_current_section(user_id, book_id)


@router.post("/{book_id}/curriculum/next")
def curriculum_next(book_id: str, user_id: str, session: Session = Depends(get_session)):
    # Deliberately the same implementation as /continue (not a second one) —
    # advancing the curriculum always goes through the review-detour check
    # in continue_lesson(), per §42: "adaptive teaching without breaking
    # book order" applies to every forward step, not just the "Continue"
    # button.
    coach = BookCoach(session, user_id, book_id)
    return coach.continue_lesson()


@router.post("/{book_id}/curriculum/previous")
def curriculum_previous(book_id: str, user_id: str, session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    return {"section": coach.go_back()}


@router.post("/{book_id}/ingest")
def trigger_ingest(book_id: str, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    """Explicit (re)ingestion trigger for a book that's already uploaded —
    upload itself already kicks off ingestion automatically (see
    routes/ingestion.py upload_book), this is for retrying a failed run."""
    from app.db import models as db
    from app.ingestion.pipeline import ingest_book
    import os

    book = session.get(db.Book, book_id)
    if not book:
        return {"error": "book not found"}
    book.status = "processing"
    session.add(book)
    session.commit()
    output_dir = os.path.dirname(book.pdf_storage_ref)
    background_tasks.add_task(ingest_book, session, book, book.pdf_storage_ref, output_dir)
    return {"book_id": book_id, "status": "processing"}


@router.post("/{book_id}/search")
def search_book_post(book_id: str, body: SearchQuery, session: Session = Depends(get_session)):
    """POST form of search (see routes/search.py for the GET ?q= form kept
    for backward compatibility — both call the same BookRAG, not two
    separate search implementations)."""
    rag = BookRAG(session)
    if body.section_id:
        return rag.search_section(book_id, body.section_id, body.query)
    return rag.search_book(book_id, body.query)


@router.post("/{book_id}/ask")
def ask_book(book_id: str, body: AskQuery, user_id: str, session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    return coach.ask_book(book_id, body.question)


@router.get("/{book_id}/progress")
def get_progress(book_id: str, user_id: str, session: Session = Depends(get_session)):
    from sqlmodel import select
    from app.db import models as db
    stmt = select(db.Progress).where(db.Progress.user_id == user_id, db.Progress.book_id == book_id)
    return session.exec(stmt).first()


@router.post("/{book_id}/puzzles/{puzzle_id}/attempt")
def submit_puzzle_move_nested(book_id: str, puzzle_id: str, body: dict, user_id: str,
                               session: Session = Depends(get_session)):
    """Same underlying logic as POST /puzzles/{puzzle_id}/attempt (see
    routes/puzzles.py) — this nested path matches the endpoint list from the
    follow-up brief; both call BookCoach.submit_puzzle_move, not two
    separate puzzle implementations."""
    coach = BookCoach(session, user_id, book_id)
    return coach.submit_puzzle_move(puzzle_id, body.get("move_san", ""))
