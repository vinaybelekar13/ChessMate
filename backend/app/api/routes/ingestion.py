"""Upload + ingestion-status endpoints (spec §50)."""
import os
import uuid

from fastapi import APIRouter, Depends, UploadFile, BackgroundTasks
from sqlmodel import Session

from app.config import settings
from app.db.session import get_session
from app.db import models as db
from app.ingestion.pipeline import ingest_book, progress_reporter

router = APIRouter()


@router.post("/upload")
async def upload_book(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    book_dir = os.path.join(settings.storage_root, "books", str(uuid.uuid4()))
    os.makedirs(book_dir, exist_ok=True)
    pdf_path = os.path.join(book_dir, file.filename)
    with open(pdf_path, "wb") as f:
        f.write(await file.read())

    book = db.Book(title=file.filename, status="processing", pdf_storage_ref=pdf_path)
    session.add(book)
    session.commit()
    session.refresh(book)

    background_tasks.add_task(ingest_book, session, book, pdf_path, book_dir)
    return {"book_id": book.id, "status": "processing"}


@router.get("/{book_id}/ingestion-status")
def ingestion_status(book_id: str):
    return progress_reporter.get(book_id)
