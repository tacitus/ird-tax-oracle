"""Create query_log table for evaluation and improvement."""

from yoyo import step

__depends__ = {"0004_taxtechnical_fields"}

steps = [
    step(
        """
        CREATE TABLE query_log (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            question        TEXT NOT NULL,
            answer          TEXT NOT NULL,
            model_used      TEXT NOT NULL,
            chunks_used     UUID[] DEFAULT '{}',
            tool_calls      JSONB DEFAULT '[]',
            latency_ms      INTEGER,
            feedback        TEXT CHECK (feedback IN ('positive', 'negative')),
            feedback_note   TEXT,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "DROP TABLE IF EXISTS query_log",
    ),
]
