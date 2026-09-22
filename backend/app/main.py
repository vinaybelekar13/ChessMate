"""FastAPI entrypoint for the Book Coach backend.

This process is separate from ChessMate's static frontend. It exists solely
because the ingestion (MinerU/Docling) and retrieval (LightRAG + LLM) pieces
of the spec cannot run in a browser. See ../ARCHITECTURE.md.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.session import init_db
from app.api.routes import books, ingestion, lessons, puzzles, search, progress, engine, magnus

app = FastAPI(title="ChessMate", version="1.0.0-integrated")


@app.on_event("startup")
def _on_startup():
    # Creates SQLite tables on first run — see db/session.py. For Postgres
    # production, use Alembic migrations instead and remove this call.
    init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books.router, prefix="/books", tags=["books"])
app.include_router(ingestion.router, prefix="/books", tags=["ingestion"])
app.include_router(lessons.router, prefix="/books", tags=["lessons"])
app.include_router(puzzles.router, prefix="/puzzles", tags=["puzzles"])
app.include_router(search.router, prefix="/books", tags=["search"])
app.include_router(progress.router, prefix="/progress", tags=["progress"])
app.include_router(engine.router, prefix="/engine", tags=["engine"])
app.include_router(magnus.router, prefix="/magnus", tags=["magnus"])


@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "shared_stockfish",
        "components": ["books", "ingestion", "lessons", "puzzles", "search", "progress", "engine", "magnus"],
    }
