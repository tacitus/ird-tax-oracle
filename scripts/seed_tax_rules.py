"""Seed tax_years and tax_brackets tables from hardcoded constants."""

import logging
import sys
from datetime import date
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from src.calculators.tax_data import TAX_YEARS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

YEAR_DATES: dict[str, tuple[date, date]] = {
    "2023-24": (date(2023, 4, 1), date(2024, 3, 31)),
    "2024-25": (date(2024, 4, 1), date(2025, 3, 31)),
    "2025-26": (date(2025, 4, 1), date(2026, 3, 31)),
}


def main() -> None:
    """Insert tax year and bracket seed data."""
    db_url = settings.database_url_sync
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    inserted = 0
    for year_label, data in TAX_YEARS.items():
        start_date, end_date = YEAR_DATES[year_label]

        # Upsert tax year
        cur.execute(
            """
            INSERT INTO tax_years (
                year_label, start_date, end_date,
                acc_rate, acc_max_earnings, sl_threshold, sl_rate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (year_label) DO UPDATE SET
                acc_rate = EXCLUDED.acc_rate,
                acc_max_earnings = EXCLUDED.acc_max_earnings,
                sl_threshold = EXCLUDED.sl_threshold,
                sl_rate = EXCLUDED.sl_rate
            RETURNING id
            """,
            (
                year_label,
                start_date,
                end_date,
                float(data.acc.rate),
                float(data.acc.max_liable_earnings),
                float(data.student_loan.annual_threshold),
                float(data.student_loan.repayment_rate),
            ),
        )
        tax_year_id = cur.fetchone()[0]

        # Delete existing brackets for this year (idempotent re-seed)
        cur.execute("DELETE FROM tax_brackets WHERE tax_year_id = %s", (tax_year_id,))

        for sort_order, bracket in enumerate(data.brackets):
            cur.execute(
                """
                INSERT INTO tax_brackets (tax_year_id, lower_bound, upper_bound, rate, sort_order)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    tax_year_id,
                    float(bracket.lower),
                    float(bracket.upper) if bracket.upper is not None else None,
                    float(bracket.rate),
                    sort_order,
                ),
            )

        inserted += 1
        logger.info("Seeded %s (%d brackets)", year_label, len(data.brackets))

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Seeded %d tax years.", inserted)


if __name__ == "__main__":
    main()
