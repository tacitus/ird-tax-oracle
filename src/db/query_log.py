"""Async query logging to the query_log table."""

import json
import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


async def log_query(
    pool: asyncpg.Pool,
    question: str,
    answer: str,
    model: str,
    latency_ms: int,
    tool_calls: list[dict] | None = None,
    chunk_ids: list[UUID] | None = None,
    cost_usd: float | None = None,
    error_message: str | None = None,
) -> UUID | None:
    """Insert a row into query_log and return its ID.

    Fire-and-forget friendly — errors are logged, not raised.
    Returns the query_log row UUID on success, None on failure.
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO query_log
                    (question, answer, model_used, latency_ms, tool_calls,
                     chunks_used, cost_usd, error_message)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
                RETURNING id
                """,
                question,
                answer,
                model,
                latency_ms,
                json.dumps(tool_calls) if tool_calls else None,
                chunk_ids or [],
                cost_usd,
                error_message,
            )
            return UUID(str(row["id"])) if row else None
    except Exception:
        logger.exception("Failed to log query")
        return None


async def update_feedback(
    pool: asyncpg.Pool,
    query_id: UUID,
    feedback: str,
    note: str | None = None,
) -> bool:
    """Update feedback on a query_log row. Returns True if row was found."""
    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE query_log
                SET feedback = $2, feedback_note = $3
                WHERE id = $1
                """,
                query_id,
                feedback,
                note,
            )
            return result == "UPDATE 1"
    except Exception:
        logger.exception("Failed to update feedback for query %s", query_id)
        return False


async def get_query_stats(pool: asyncpg.Pool) -> dict:
    """Get aggregate query stats for the health endpoint."""
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_queries,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour')
                        AS queries_last_hour,
                    ROUND(AVG(latency_ms)) AS avg_latency_ms,
                    ROUND(AVG(latency_ms) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour'))
                        AS avg_latency_last_hour,
                    COUNT(*) FILTER (WHERE feedback = 'positive') AS positive_feedback,
                    COUNT(*) FILTER (WHERE feedback = 'negative') AS negative_feedback,
                    COUNT(*) FILTER (WHERE error_message IS NOT NULL) AS error_count
                FROM query_log
                """
            )
            if not row:
                return {}
            return {k: v for k, v in dict(row).items() if v is not None}
    except Exception:
        logger.exception("Failed to get query stats")
        return {}
