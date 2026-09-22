"""Central settings, loaded from environment (.env in dev).

LOCAL DEVELOPMENT DEFAULT = SQLite (no Postgres/Docker required — see
README.md). Set DATABASE_URL to a postgresql:// URL for production.

Falls back to a plain stdlib reader if `pydantic-settings` isn't installed,
so the rest of the app (and this sandbox's tests) can still run before
`pip install -r requirements.txt` has been done.
"""

import os


try:
    from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        database_url: str = "sqlite:///./bookcoach.db"
        storage_root: str = "./storage"

        anthropic_api_key: str = ""
        llm_model: str = "claude-sonnet-4-6"

        mineru_mode: str = "cli"
        mineru_bin: str = "magic-pdf"
        docling_enabled: bool = True

        stockfish_path: str = "stockfish"

        # Frontend development servers allowed to call the FastAPI backend.
        allowed_origins: str = (
            "http://localhost:8000,"
            "http://127.0.0.1:8000,"
            "http://localhost:8080,"
            "http://127.0.0.1:8080"
        )

        class Config:
            env_file = ".env"

    settings = Settings()

except ImportError:

    def _env(name: str, default: str) -> str:
        return os.environ.get(name.upper(), default)

    class _PlainSettings:
        """Minimal stand-in with the same attributes as the pydantic
        version, reading straight from os.environ.
        """

        def __init__(self):
            self.database_url = _env(
                "database_url",
                "sqlite:///./bookcoach.db"
            )

            self.storage_root = _env(
                "storage_root",
                "./storage"
            )

            self.anthropic_api_key = _env(
                "anthropic_api_key",
                ""
            )

            self.llm_model = _env(
                "llm_model",
                "claude-sonnet-4-6"
            )

            self.mineru_mode = _env(
                "mineru_mode",
                "cli"
            )

            self.mineru_bin = _env(
                "mineru_bin",
                "magic-pdf"
            )

            self.docling_enabled = _env(
                "docling_enabled",
                "true"
            ).lower() == "true"

            self.stockfish_path = _env(
                "stockfish_path",
                "stockfish"
            )

            self.allowed_origins = _env(
                "allowed_origins",
                (
                    "http://localhost:8000,"
                    "http://127.0.0.1:8000,"
                    "http://localhost:8080,"
                    "http://127.0.0.1:8080"
                )
            )

    settings = _PlainSettings()