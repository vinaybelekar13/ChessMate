"""Book library + dashboard endpoints (spec §51)."""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db.session import get_session
from app.db import models as db

router = APIRouter()


@router.get("")
def list_books(session: Session = Depends(get_session)):
    return session.exec(select(db.Book)).all()


@router.get("/{book_id}")
def get_book(book_id: str, session: Session = Depends(get_session)):
    return session.get(db.Book, book_id)


def _structure(book_id: str, session: Session):
    """Chapter/section tree for the left-nav (spec §26 LEFT panel). Shared by
    both /structure and /curriculum — same tree, two names, one implementation
    (the follow-up brief's endpoint list calls it "curriculum")."""
    chapters = session.exec(
        select(db.Chapter).where(db.Chapter.book_id == book_id).order_by(db.Chapter.order_index)
    ).all()
    result = []
    for ch in chapters:
        sections = session.exec(
            select(db.Section).where(db.Section.chapter_id == ch.id).order_by(db.Section.order_index)
        ).all()
        result.append({"chapter": ch, "sections": sections})
    return result


@router.get("/{book_id}/structure")
def get_structure(book_id: str, session: Session = Depends(get_session)):
    return _structure(book_id, session)


@router.get("/{book_id}/curriculum")
def get_curriculum(book_id: str, session: Session = Depends(get_session)):
    return _structure(book_id, session)


@router.get("/{book_id}/sections/{section_id}")
def get_section(book_id: str, section_id: str, session: Session = Depends(get_session)):
    return session.get(db.Section, section_id)


@router.get("/{book_id}/puzzles")
def list_puzzles(book_id: str, session: Session = Depends(get_session)):
    return session.exec(select(db.Puzzle).where(db.Puzzle.book_id == book_id)).all()


@router.get("/{book_id}/coverage")
def get_coverage(book_id: str, session: Session = Depends(get_session)):
    """Book coverage counters (spec §44) — prevents the "illusion of full
    teaching" by reporting real processed/taught counts."""
    total_chapters = len(session.exec(select(db.Chapter).where(db.Chapter.book_id == book_id)).all())
    total_sections = len(session.exec(select(db.Section).where(db.Section.book_id == book_id)).all())
    total_puzzles = len(session.exec(select(db.Puzzle).where(db.Puzzle.book_id == book_id)).all())
    total_positions = len(session.exec(select(db.Position).where(db.Position.book_id == book_id)).all())
    book = session.get(db.Book, book_id)
    return {
        "pages": {"total": book.total_pages if book else None},
        "chapters": {"total": total_chapters},
        "sections": {"total": total_sections},
        "puzzles": {"total": total_puzzles},
        "positions": {"total": total_positions},
    }
