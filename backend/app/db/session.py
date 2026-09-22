"""LOCAL DEVELOPMENT DEFAULT = SQLite (settings.database_url defaults to
sqlite:///./bookcoach.db — no Postgres/Docker required, see README.md).
PRODUCTION OPTION = set DATABASE_URL to a postgresql:// URL; SQLModel/
SQLAlchemy abstracts the rest, no code change needed.
"""
from sqlmodel import create_engine, Session, SQLModel
from app.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=_connect_args)


def init_db() -> None:
    """Creates all tables if they don't exist yet. Fine for SQLite local dev;
    use Alembic migrations instead once you're on Postgres in production."""
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
