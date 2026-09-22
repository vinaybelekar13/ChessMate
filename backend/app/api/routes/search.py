"""Search-mode / "find in book" endpoints (spec §35, §36)."""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.rag.book_rag import BookRAG

router = APIRouter()


@router.get("/{book_id}/search")
def search_book(book_id: str, q: str, session: Session = Depends(get_session)):
    rag = BookRAG(session)
    return rag.search_book(book_id, q)
