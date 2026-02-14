"""Create required PostgreSQL extensions."""

from yoyo import step

__depends__ = {}  # type: ignore[var-annotated]

steps = [
    step(
        "CREATE EXTENSION IF NOT EXISTS vector",
        "DROP EXTENSION IF EXISTS vector",
    ),
    step(
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "DROP EXTENSION IF EXISTS pg_trgm",
    ),
]
