"""Progress endpoints exposed independently of the lessons router."""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db.session import get_session
from app.db import models as db

router = APIRouter()


@router.get("/{user_id}/{book_id}")
def get_progress(user_id: str, book_id: str, session: Session = Depends(get_session)):
    stmt = select(db.Progress).where(db.Progress.user_id == user_id, db.Progress.book_id == book_id)
    return session.exec(stmt).first()
