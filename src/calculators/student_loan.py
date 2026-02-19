"""Student loan repayment calculator."""

from decimal import Decimal
from typing import Any

from src.calculators.tax_data import DEFAULT_TAX_YEAR, TAX_YEARS


def calculate_student_loan_repayment(
    annual_income: Decimal,
    tax_year: str = DEFAULT_TAX_YEAR,
) -> dict[str, Any]:
    """Calculate annual student loan repayment.

    Repayment is charged at 12% on income above the annual threshold.

    Args:
        annual_income: Gross annual income (must be >= 0).
        tax_year: Tax year key, e.g. "2025-26".

    Returns:
        Dict with annual_repayment, repayment_rate, threshold, tax_year.
    """
    if tax_year not in TAX_YEARS:
        return {"error": f"Unknown tax year: {tax_year}. Available: {', '.join(sorted(TAX_YEARS))}"}

    if annual_income < 0:
        return {"error": "Annual income must be non-negative."}

    sl = TAX_YEARS[tax_year].student_loan
    income_above_threshold = max(Decimal("0"), annual_income - sl.annual_threshold)
    repayment = income_above_threshold * sl.repayment_rate

    return {
        "annual_income": float(annual_income),
        "annual_repayment": float(repayment),
        "repayment_rate": float(sl.repayment_rate),
        "annual_threshold": float(sl.annual_threshold),
        "income_above_threshold": float(income_above_threshold),
        "tax_year": tax_year,
    }
