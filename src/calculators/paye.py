"""PAYE calculator — composites income tax, ACC, and optional student loan."""

from decimal import Decimal
from typing import Any

from src.calculators.acc import calculate_acc_levy
from src.calculators.income_tax import calculate_income_tax
from src.calculators.student_loan import calculate_student_loan_repayment
from src.calculators.tax_data import DEFAULT_TAX_YEAR

PAY_PERIODS: dict[str, int] = {
    "weekly": 52,
    "fortnightly": 26,
    "four-weekly": 13,
    "monthly": 12,
}


def calculate_paye(
    annual_income: Decimal,
    pay_period: str = "monthly",
    has_student_loan: bool = False,
    tax_year: str = DEFAULT_TAX_YEAR,
) -> dict[str, Any]:
    """Calculate PAYE deductions per pay period.

    Simplified v1: annual income tax + ACC + optional student loan,
    divided by pay periods. Covers M/ME tax codes.

    Args:
        annual_income: Gross annual income (must be >= 0).
        pay_period: One of weekly, fortnightly, four-weekly, monthly.
        has_student_loan: Whether to include student loan repayment.
        tax_year: Tax year key, e.g. "2025-26".

    Returns:
        Dict with per-period and annual breakdowns.
    """
    if pay_period not in PAY_PERIODS:
        valid = ", ".join(sorted(PAY_PERIODS))
        return {"error": f"Invalid pay period: {pay_period}. Must be one of: {valid}"}

    tax_result = calculate_income_tax(annual_income, tax_year)
    if "error" in tax_result:
        return tax_result

    acc_result = calculate_acc_levy(annual_income, tax_year)
    if "error" in acc_result:
        return acc_result

    periods = PAY_PERIODS[pay_period]
    annual_tax = Decimal(str(tax_result["total_tax"]))
    annual_acc = Decimal(str(acc_result["annual_levy"]))
    annual_sl = Decimal("0")

    sl_result: dict[str, Any] | None = None
    if has_student_loan:
        sl_result = calculate_student_loan_repayment(annual_income, tax_year)
        if "error" in sl_result:
            return sl_result
        annual_sl = Decimal(str(sl_result["annual_repayment"]))

    annual_total_deductions = annual_tax + annual_acc + annual_sl
    annual_take_home = annual_income - annual_total_deductions

    per_period_gross = annual_income / periods
    per_period_tax = annual_tax / periods
    per_period_acc = annual_acc / periods
    per_period_sl = annual_sl / periods
    per_period_total_deductions = annual_total_deductions / periods
    per_period_take_home = annual_take_home / periods

    result: dict[str, Any] = {
        "annual_income": float(annual_income),
        "pay_period": pay_period,
        "periods_per_year": periods,
        "tax_year": tax_year,
        "annual": {
            "income_tax": float(annual_tax),
            "acc_levy": float(annual_acc),
            "student_loan": float(annual_sl),
            "total_deductions": float(annual_total_deductions),
            "take_home": float(annual_take_home),
        },
        "per_period": {
            "gross": float(per_period_gross),
            "income_tax": float(per_period_tax),
            "acc_levy": float(per_period_acc),
            "student_loan": float(per_period_sl),
            "total_deductions": float(per_period_total_deductions),
            "take_home": float(per_period_take_home),
        },
        "income_tax_detail": tax_result,
        "notes": (
            "Simplified PAYE for M/ME tax codes. "
            "Secondary income (tax code S/SH/ST) uses different rates. "
            "Does not include KiwiSaver employer/employee contributions."
        ),
    }

    return result
