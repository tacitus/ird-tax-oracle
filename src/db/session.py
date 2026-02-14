"""asyncpg connection pool with pgvector registration."""

import logging

import asyncpg
from pgvector.asyncpg import register_vector

from config.settings import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register pgvector type on each new connection."""
    await register_vector(conn)


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        db_url = settings.database_url_sync  # asyncpg uses plain postgresql:// URLs
        logger.info("Creating connection pool...")
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=2,
            max_size=10,
            init=_init_connection,
        )
    return _pool


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
