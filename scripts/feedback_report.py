"""Feedback and quality report from query_log data.

Analyzes query_log for negative feedback patterns, zero-retrieval queries,
slow queries, and tool usage patterns. Designed to identify areas for
improvement in the RAG pipeline.

Usage:
    docker compose run --rm dev python scripts/feedback_report.py
    docker compose run --rm dev python scripts/feedback_report.py --days 7
"""

import argparse
import asyncio
import logging
from typing import Any

from src.db.session import close_pool, get_pool

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def fetch_report_data(
    pool: Any,
    days: int,
) -> dict[str, Any]:
    """Run all report queries against query_log."""
    async with pool.acquire() as conn:
        # Summary stats
        summary = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total_queries,
                COUNT(*) FILTER (WHERE feedback = 'positive') AS positive,
                COUNT(*) FILTER (WHERE feedback = 'negative') AS negative,
                COUNT(*) FILTER (WHERE feedback IS NULL) AS no_feedback,
                COUNT(*) FILTER (WHERE chunks_used = '{}') AS zero_retrieval,
                COUNT(*) FILTER (WHERE error_message IS NOT NULL) AS errors,
                ROUND(AVG(latency_ms)) AS avg_latency_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms)
                    AS p95_latency_ms,
                ROUND(SUM(COALESCE(cost_usd, 0))::numeric, 4) AS total_cost_usd
            FROM query_log
            WHERE created_at > NOW() - make_interval(days => $1)
            """,
            days,
        )

        # Negative feedback queries
        negative_queries = await conn.fetch(
            """
            SELECT question, answer, feedback_note, latency_ms, created_at
            FROM query_log
            WHERE feedback = 'negative'
              AND created_at > NOW() - make_interval(days => $1)
            ORDER BY created_at DESC
            LIMIT 20
            """,
            days,
        )

        # Zero-retrieval queries (empty chunks_used)
        zero_retrieval = await conn.fetch(
            """
            SELECT question, latency_ms, created_at
            FROM query_log
            WHERE chunks_used = '{}'
              AND created_at > NOW() - make_interval(days => $1)
            ORDER BY created_at DESC
            LIMIT 20
            """,
            days,
        )

        # Slowest queries (P95+)
        slow_queries = await conn.fetch(
            """
            SELECT question, latency_ms, model_used, created_at
            FROM query_log
            WHERE created_at > NOW() - make_interval(days => $1)
            ORDER BY latency_ms DESC
            LIMIT 10
            """,
            days,
        )

        # Tool usage patterns
        tool_usage = await conn.fetch(
            """
            SELECT
                tool_call->>'name' AS tool_name,
                COUNT(*) AS call_count
            FROM query_log,
                 jsonb_array_elements(tool_calls) AS tool_call
            WHERE created_at > NOW() - make_interval(days => $1)
              AND tool_calls IS NOT NULL
              AND tool_calls != '[]'::jsonb
            GROUP BY tool_call->>'name'
            ORDER BY call_count DESC
            """,
            days,
        )

        # Error patterns
        errors = await conn.fetch(
            """
            SELECT question, error_message, created_at
            FROM query_log
            WHERE error_message IS NOT NULL
              AND created_at > NOW() - make_interval(days => $1)
            ORDER BY created_at DESC
            LIMIT 10
            """,
            days,
        )

    return {
        "summary": dict(summary) if summary else {},
        "negative_queries": [dict(r) for r in negative_queries],
        "zero_retrieval": [dict(r) for r in zero_retrieval],
        "slow_queries": [dict(r) for r in slow_queries],
        "tool_usage": [dict(r) for r in tool_usage],
        "errors": [dict(r) for r in errors],
    }


def print_report(data: dict[str, Any], days: int) -> None:
    """Log the formatted report."""
    s = data["summary"]

    logger.info("=" * 70)
    logger.info("NZ TAX RAG — FEEDBACK & QUALITY REPORT (last %d days)", days)
    logger.info("=" * 70)

    # Summary
    logger.info("")
    logger.info("SUMMARY")
    logger.info("-" * 40)
    logger.info("  Total queries:       %s", s.get("total_queries", 0))
    logger.info("  Positive feedback:   %s", s.get("positive", 0))
    logger.info("  Negative feedback:   %s", s.get("negative", 0))
    logger.info("  No feedback:         %s", s.get("no_feedback", 0))
    logger.info("  Zero-retrieval:      %s", s.get("zero_retrieval", 0))
    logger.info("  Errors:              %s", s.get("errors", 0))
    logger.info("  Avg latency:         %sms", s.get("avg_latency_ms", "N/A"))
    logger.info("  P95 latency:         %sms", s.get("p95_latency_ms", "N/A"))
    logger.info("  Total cost:          $%s", s.get("total_cost_usd", "0.00"))

    # Negative feedback
    neg = data["negative_queries"]
    if neg:
        logger.info("")
        logger.info("NEGATIVE FEEDBACK (%d queries)", len(neg))
        logger.info("-" * 40)
        for q in neg:
            logger.info("  Q: %s", q["question"][:100])
            if q.get("feedback_note"):
                logger.info("     Note: %s", q["feedback_note"][:200])
            logger.info("     Latency: %dms | %s", q["latency_ms"], q["created_at"])
    else:
        logger.info("")
        logger.info("NEGATIVE FEEDBACK: None")

    # Zero-retrieval queries
    zr = data["zero_retrieval"]
    if zr:
        logger.info("")
        logger.info("ZERO-RETRIEVAL QUERIES (%d queries)", len(zr))
        logger.info("-" * 40)
        for q in zr:
            logger.info("  Q: %s", q["question"][:100])
    else:
        logger.info("")
        logger.info("ZERO-RETRIEVAL QUERIES: None")

    # Slow queries
    slow = data["slow_queries"]
    if slow:
        logger.info("")
        logger.info("SLOWEST QUERIES (top 10)")
        logger.info("-" * 40)
        for q in slow:
            logger.info(
                "  %5dms | %-12s | %s",
                q["latency_ms"],
                q["model_used"][:12],
                q["question"][:80],
            )

    # Tool usage
    tools = data["tool_usage"]
    if tools:
        logger.info("")
        logger.info("TOOL USAGE")
        logger.info("-" * 40)
        for t in tools:
            logger.info("  %-35s %d calls", t["tool_name"], t["call_count"])

    # Errors
    errs = data["errors"]
    if errs:
        logger.info("")
        logger.info("RECENT ERRORS (%d)", len(errs))
        logger.info("-" * 40)
        for e in errs:
            logger.info("  Q: %s", e["question"][:80])
            logger.info("     Error: %s", e["error_message"][:200])

    logger.info("")
    logger.info("=" * 70)


async def main() -> None:
    """Run the feedback report."""
    parser = argparse.ArgumentParser(description="NZ Tax RAG Feedback Report")
    parser.add_argument(
        "--days", type=int, default=30,
        help="Number of days to include in the report (default: 30)",
    )
    args = parser.parse_args()

    pool = await get_pool()
    data = await fetch_report_data(pool, args.days)
    print_report(data, args.days)
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
