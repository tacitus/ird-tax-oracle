"""Income tax calculator — bracket-by-bracket breakdown."""

from decimal import Decimal
from typing import Any

from src.calculators.tax_data import DEFAULT_TAX_YEAR, TAX_YEARS


def calculate_income_tax(
    annual_income: Decimal,
    tax_year: str = DEFAULT_TAX_YEAR,
) -> dict[str, Any]:
    """Calculate NZ income tax with per-bracket breakdown.

    Args:
        annual_income: Gross annual income (must be >= 0).
        tax_year: Tax year key, e.g. "2025-26".

    Returns:
        Dict with total_tax, effective_rate, breakdown, tax_year, notes.
    """
    if tax_year not in TAX_YEARS:
        return {"error": f"Unknown tax year: {tax_year}. Available: {', '.join(sorted(TAX_YEARS))}"}

    if annual_income < 0:
        return {"error": "Annual income must be non-negative."}

    data = TAX_YEARS[tax_year]
    breakdown: list[dict[str, Any]] = []
    total_tax = Decimal("0")

    for bracket in data.brackets:
        if annual_income <= bracket.lower:
            break

        upper = bracket.upper if bracket.upper is not None else annual_income
        taxable = min(annual_income, upper) - bracket.lower
        tax = taxable * bracket.rate

        breakdown.append({
            "lower": float(bracket.lower),
            "upper": float(upper) if bracket.upper is not None else None,
            "rate": float(bracket.rate),
            "taxable_amount": float(taxable),
            "tax": float(tax),
        })
        total_tax += tax

    effective_rate = (total_tax / annual_income * 100) if annual_income > 0 else Decimal("0")

    return {
        "annual_income": float(annual_income),
        "total_tax": float(total_tax),
        "effective_rate": float(round(effective_rate, 2)),
        "breakdown": breakdown,
        "tax_year": tax_year,
    }
