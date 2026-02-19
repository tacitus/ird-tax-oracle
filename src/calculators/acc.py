"""ACC earner's levy calculator."""

from decimal import Decimal
from typing import Any

from src.calculators.tax_data import DEFAULT_TAX_YEAR, TAX_YEARS


def calculate_acc_levy(
    annual_income: Decimal,
    tax_year: str = DEFAULT_TAX_YEAR,
) -> dict[str, Any]:
    """Calculate ACC earner's levy.

    The levy is charged on income up to a maximum liable earnings cap.

    Args:
        annual_income: Gross annual income (must be >= 0).
        tax_year: Tax year key, e.g. "2025-26".

    Returns:
        Dict with annual_levy, acc_rate, max_liable_earnings, tax_year.
    """
    if tax_year not in TAX_YEARS:
        return {"error": f"Unknown tax year: {tax_year}. Available: {', '.join(sorted(TAX_YEARS))}"}

    if annual_income < 0:
        return {"error": "Annual income must be non-negative."}

    acc = TAX_YEARS[tax_year].acc
    liable_earnings = min(annual_income, acc.max_liable_earnings)
    levy = liable_earnings * acc.rate

    return {
        "annual_income": float(annual_income),
        "annual_levy": float(levy),
        "acc_rate": float(acc.rate),
        "liable_earnings": float(liable_earnings),
        "max_liable_earnings": float(acc.max_liable_earnings),
        "tax_year": tax_year,
    }
