"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    database_url: str = "postgresql+asyncpg://taxapp:changeme@localhost:5432/nz_tax"
    gemini_api_key: str = ""
    llm_default_model: str = "gemini/gemini-2.5-flash"
    auth_username: str = ""
    auth_password: str = ""
    reranker_enabled: bool = True

    @property
    def database_url_sync(self) -> str:
        """Return a plain postgresql:// URL for sync drivers (yoyo, psycopg2)."""
        return self.database_url.replace("+asyncpg", "")

    @property
    def database_url_asyncpg(self) -> str:
        """Return a plain postgresql:// URL for asyncpg (no +asyncpg scheme)."""
        return self.database_url.replace("+asyncpg", "")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
