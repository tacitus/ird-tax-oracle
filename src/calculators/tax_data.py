"""NZ tax constants — brackets, ACC levies, student loan thresholds.

Hardcoded Python constants (not DB-driven). Tax brackets change rarely
(last NZ change: July 2024). Trivially testable, no external dependencies.
"""

from decimal import Decimal
from typing import NamedTuple


class TaxBracket(NamedTuple):
    """A single income tax bracket."""

    lower: Decimal  # inclusive
    upper: Decimal | None  # None = no cap
    rate: Decimal


class AccLevy(NamedTuple):
    """ACC earner's levy parameters for a tax year."""

    rate: Decimal
    max_liable_earnings: Decimal


class StudentLoanThreshold(NamedTuple):
    """Student loan repayment parameters for a tax year."""

    annual_threshold: Decimal
    repayment_rate: Decimal


class TaxYearData(NamedTuple):
    """All tax parameters for a single NZ tax year."""

    brackets: tuple[TaxBracket, ...]
    acc: AccLevy
    student_loan: StudentLoanThreshold


# Pre-July 2024 brackets (2023-24 and earlier)
_BRACKETS_PRE_2024 = (
    TaxBracket(Decimal("0"), Decimal("14000"), Decimal("0.105")),
    TaxBracket(Decimal("14000"), Decimal("48000"), Decimal("0.175")),
    TaxBracket(Decimal("48000"), Decimal("70000"), Decimal("0.30")),
    TaxBracket(Decimal("70000"), Decimal("180000"), Decimal("0.33")),
    TaxBracket(Decimal("180000"), None, Decimal("0.39")),
)

# Post-July 2024 brackets (2024-25 onwards)
_BRACKETS_2024 = (
    TaxBracket(Decimal("0"), Decimal("15600"), Decimal("0.105")),
    TaxBracket(Decimal("15600"), Decimal("53500"), Decimal("0.175")),
    TaxBracket(Decimal("53500"), Decimal("78100"), Decimal("0.30")),
    TaxBracket(Decimal("78100"), Decimal("180000"), Decimal("0.33")),
    TaxBracket(Decimal("180000"), None, Decimal("0.39")),
)

TAX_YEARS: dict[str, TaxYearData] = {
    "2023-24": TaxYearData(
        brackets=_BRACKETS_PRE_2024,
        acc=AccLevy(
            rate=Decimal("0.0153"),  # $1.53 per $100 incl. GST
            max_liable_earnings=Decimal("139384"),
        ),
        student_loan=StudentLoanThreshold(
            annual_threshold=Decimal("22828"),
            repayment_rate=Decimal("0.12"),
        ),
    ),
    "2024-25": TaxYearData(
        brackets=_BRACKETS_2024,
        acc=AccLevy(
            rate=Decimal("0.0160"),  # $1.60 per $100 incl. GST (from 1 Apr 2024)
            max_liable_earnings=Decimal("142283"),
        ),
        student_loan=StudentLoanThreshold(
            annual_threshold=Decimal("24128"),  # increased from 1 Apr 2024
            repayment_rate=Decimal("0.12"),
        ),
    ),
    # Source: IRD ACC earners' levy rates page, ird.govt.nz
    "2025-26": TaxYearData(
        brackets=_BRACKETS_2024,
        acc=AccLevy(
            rate=Decimal("0.0167"),  # $1.67 per $100 incl. GST (from 1 Apr 2025)
            max_liable_earnings=Decimal("152790"),
        ),
        student_loan=StudentLoanThreshold(
            annual_threshold=Decimal("24128"),  # frozen at 2024-25 level
            repayment_rate=Decimal("0.12"),
        ),
    ),
}

DEFAULT_TAX_YEAR = "2025-26"
