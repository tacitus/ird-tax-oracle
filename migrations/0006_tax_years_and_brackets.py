"""Create tax_years and tax_brackets tables for future DB-driven calculators."""

from yoyo import step

__depends__ = {"0005_query_log"}

steps = [
    step(
        """
        CREATE TABLE tax_years (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            year_label      TEXT NOT NULL UNIQUE,
            start_date      DATE NOT NULL,
            end_date        DATE NOT NULL,
            acc_rate        NUMERIC(6,4) NOT NULL,
            acc_max_earnings NUMERIC(12,2) NOT NULL,
            sl_threshold    NUMERIC(12,2) NOT NULL,
            sl_rate         NUMERIC(4,2) NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "DROP TABLE IF EXISTS tax_brackets; DROP TABLE IF EXISTS tax_years",
    ),
    step(
        """
        CREATE TABLE tax_brackets (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tax_year_id     UUID NOT NULL REFERENCES tax_years(id) ON DELETE CASCADE,
            lower_bound     NUMERIC(12,2) NOT NULL,
            upper_bound     NUMERIC(12,2),
            rate            NUMERIC(6,4) NOT NULL,
            sort_order      INTEGER NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "DROP TABLE IF EXISTS tax_brackets",
    ),
    step(
        "CREATE INDEX idx_tax_brackets_year ON tax_brackets (tax_year_id, sort_order)",
        "DROP INDEX IF EXISTS idx_tax_brackets_year",
    ),
]
