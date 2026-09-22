"""Puzzle interaction endpoints (spec §14-§18)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.db.session import get_session
from app.coach.book_coach import BookCoach

router = APIRouter()


class MoveSubmission(BaseModel):
    move_san: str


@router.get("/{puzzle_id}")
def get_puzzle(puzzle_id: str, user_id: str, book_id: str, session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    return coach.start_puzzle(puzzle_id)


@router.post("/{puzzle_id}/attempt")
def submit_move(puzzle_id: str, body: MoveSubmission, user_id: str, book_id: str,
                 session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    return coach.submit_puzzle_move(puzzle_id, body.move_san)


@router.get("/{puzzle_id}/hint")
def get_hint(puzzle_id: str, user_id: str, book_id: str, session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    return {"hint": coach.give_hint(puzzle_id)}


@router.post("/{puzzle_id}/solution")
def show_solution(puzzle_id: str, user_id: str, book_id: str, session: Session = Depends(get_session)):
    coach = BookCoach(session, user_id, book_id)
    return coach.show_solution(puzzle_id)
