"""Async query logging to the query_log table."""

import logging

import asyncpg

logger = logging.getLogger(__name__)


async def log_query(
    pool: asyncpg.Pool,
    question: str,
    answer: str,
    model: str,
    latency_ms: int,
) -> None:
    """Insert a row into query_log. Fire-and-forget — errors are logged, not raised."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO query_log (question, answer, model_used, latency_ms)
                VALUES ($1, $2, $3, $4)
                """,
                question,
                answer,
                model,
                latency_ms,
            )
    except Exception:
        logger.exception("Failed to log query")
