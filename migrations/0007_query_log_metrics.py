"""Add monitoring columns to query_log: cost_usd, error_message."""

from yoyo import step

__depends__ = {"0006_tax_years_and_brackets"}

steps = [
    step(
        """
        ALTER TABLE query_log
            ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(10, 6),
            ADD COLUMN IF NOT EXISTS error_message TEXT
        """,
        """
        ALTER TABLE query_log
            DROP COLUMN IF EXISTS cost_usd,
            DROP COLUMN IF EXISTS error_message
        """,
    ),
]
