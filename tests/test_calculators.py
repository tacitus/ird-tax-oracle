"""Tests for NZ tax calculator tools."""

from decimal import Decimal

import pytest

from src.calculators.acc import calculate_acc_levy
from src.calculators.income_tax import calculate_income_tax
from src.calculators.paye import calculate_paye
from src.calculators.student_loan import (
    calculate_student_loan_repayment,
)

# --- Income tax tests ---


class TestIncomeTax:
    def test_zero_income(self) -> None:
        result = calculate_income_tax(Decimal("0"), "2025-26")
        assert result["total_tax"] == 0.0
        assert result["effective_rate"] == 0.0
        assert result["breakdown"] == []

    def test_within_first_bracket(self) -> None:
        """$10,000 at 10.5% = $1,050."""
        result = calculate_income_tax(Decimal("10000"), "2025-26")
        assert result["total_tax"] == 1050.0
        assert result["effective_rate"] == 10.5

    def test_exact_first_boundary(self) -> None:
        """$15,600 — top of first bracket in 2025-26."""
        result = calculate_income_tax(Decimal("15600"), "2025-26")
        assert result["total_tax"] == 1638.0
        assert len(result["breakdown"]) == 1

    def test_spans_two_brackets(self) -> None:
        """$30,000 spans first two brackets."""
        result = calculate_income_tax(Decimal("30000"), "2025-26")
        # $15,600 * 10.5% + $14,400 * 17.5% = $1,638 + $2,520 = $4,158
        assert result["total_tax"] == 4158.0
        assert len(result["breakdown"]) == 2

    def test_reference_65k(self) -> None:
        """Hand-verified: $65,000 on 2025-26 = $11,720.50."""
        result = calculate_income_tax(Decimal("65000"), "2025-26")
        assert result["total_tax"] == 11720.5
        assert result["effective_rate"] == 18.03
        assert len(result["breakdown"]) == 3

    def test_high_income_200k(self) -> None:
        """$200,000 spans all 5 brackets including 39%."""
        result = calculate_income_tax(Decimal("200000"), "2025-26")
        assert len(result["breakdown"]) == 5
        # Top bracket: ($200,000 - $180,000) * 39% = $7,800
        top = result["breakdown"][4]
        assert top["tax"] == 7800.0

    def test_old_brackets_2023_24(self) -> None:
        """$65,000 on 2023-24 (old brackets) should differ from 2025-26."""
        old = calculate_income_tax(Decimal("65000"), "2023-24")
        new = calculate_income_tax(Decimal("65000"), "2025-26")
        assert old["total_tax"] != new["total_tax"]
        # Old: $14,000*10.5% + $34,000*17.5% + $17,000*30% = $1,470+$5,950+$5,100 = $12,520
        assert old["total_tax"] == 12520.0

    def test_negative_income(self) -> None:
        result = calculate_income_tax(Decimal("-1000"), "2025-26")
        assert "error" in result

    def test_unknown_year(self) -> None:
        result = calculate_income_tax(Decimal("50000"), "2099-00")
        assert "error" in result


class TestAccLevy:
    def test_below_cap(self) -> None:
        """$80,000 — below max liable earnings."""
        result = calculate_acc_levy(Decimal("80000"), "2025-26")
        # $80,000 * 1.67% = $1,336
        assert result["annual_levy"] == pytest.approx(1336.0, abs=0.01)
        assert result["liable_earnings"] == 80000.0

    def test_above_cap(self) -> None:
        """$200,000 — capped at max liable earnings."""
        result = calculate_acc_levy(Decimal("200000"), "2025-26")
        assert result["liable_earnings"] == 152790.0
        # $152,790 * 1.67% = $2,551.593
        assert result["annual_levy"] == pytest.approx(2551.593, abs=0.01)

    def test_zero_income(self) -> None:
        result = calculate_acc_levy(Decimal("0"), "2025-26")
        assert result["annual_levy"] == 0.0

    def test_different_year_rate(self) -> None:
        """2023-24 has 1.53% rate vs 2025-26 at 1.67%."""
        old = calculate_acc_levy(Decimal("80000"), "2023-24")
        new = calculate_acc_levy(Decimal("80000"), "2025-26")
        assert old["acc_rate"] == 0.0153
        assert new["acc_rate"] == 0.0167
        assert new["annual_levy"] > old["annual_levy"]

    def test_2024_25_rate(self) -> None:
        """2024-25 has 1.60% rate."""
        result = calculate_acc_levy(Decimal("80000"), "2024-25")
        assert result["acc_rate"] == 0.016
        # $80,000 * 1.60% = $1,280
        assert result["annual_levy"] == pytest.approx(1280.0, abs=0.01)


class TestStudentLoan:
    def test_below_threshold(self) -> None:
        """$20,000 — below $24,128 threshold, no repayment."""
        result = calculate_student_loan_repayment(Decimal("20000"), "2025-26")
        assert result["annual_repayment"] == 0.0

    def test_above_threshold(self) -> None:
        """$65,000 — repayment on income above threshold."""
        result = calculate_student_loan_repayment(Decimal("65000"), "2025-26")
        # ($65,000 - $24,128) * 12% = $40,872 * 0.12 = $4,904.64
        assert result["annual_repayment"] == pytest.approx(4904.64, abs=0.01)

    def test_zero_income(self) -> None:
        result = calculate_student_loan_repayment(Decimal("0"), "2025-26")
        assert result["annual_repayment"] == 0.0

    def test_exact_threshold(self) -> None:
        result = calculate_student_loan_repayment(Decimal("24128"), "2025-26")
        assert result["annual_repayment"] == 0.0

    def test_2023_24_threshold(self) -> None:
        """2023-24 threshold is $22,828."""
        result = calculate_student_loan_repayment(Decimal("65000"), "2023-24")
        # ($65,000 - $22,828) * 12% = $42,172 * 0.12 = $5,060.64
        assert result["annual_repayment"] == pytest.approx(5060.64, abs=0.01)


class TestPaye:
    def test_monthly_no_student_loan(self) -> None:
        """$65,000 monthly, no student loan."""
        result = calculate_paye(Decimal("65000"), "monthly", False, "2025-26")
        assert result["periods_per_year"] == 12
        annual = result["annual"]
        assert annual["income_tax"] == 11720.5
        assert annual["student_loan"] == 0.0
        # Take-home = $65,000 - tax - ACC
        assert annual["take_home"] == pytest.approx(
            65000.0 - 11720.5 - annual["acc_levy"], abs=0.01
        )
        # Per-period checks
        per = result["per_period"]
        assert per["gross"] == pytest.approx(65000.0 / 12, abs=0.01)

    def test_weekly_with_student_loan(self) -> None:
        """$65,000 weekly, with student loan."""
        result = calculate_paye(Decimal("65000"), "weekly", True, "2025-26")
        assert result["periods_per_year"] == 52
        assert result["annual"]["student_loan"] > 0
        assert result["per_period"]["student_loan"] > 0

    def test_invalid_pay_period(self) -> None:
        result = calculate_paye(Decimal("65000"), "biweekly", False, "2025-26")
        assert "error" in result

    def test_component_sums(self) -> None:
        """Annual deductions should equal sum of components."""
        result = calculate_paye(Decimal("65000"), "monthly", True, "2025-26")
        annual = result["annual"]
        expected_deductions = (
            annual["income_tax"] + annual["acc_levy"] + annual["student_loan"]
        )
        assert annual["total_deductions"] == pytest.approx(expected_deductions, abs=0.01)
        assert annual["take_home"] == pytest.approx(
            65000.0 - expected_deductions, abs=0.01
        )

    def test_fortnightly_period(self) -> None:
        result = calculate_paye(Decimal("65000"), "fortnightly", False, "2025-26")
        assert result["periods_per_year"] == 26

    def test_four_weekly_period(self) -> None:
        result = calculate_paye(Decimal("65000"), "four-weekly", False, "2025-26")
        assert result["periods_per_year"] == 13


class TestCrossYear:
    def test_same_income_different_tax(self) -> None:
        """Same income yields different tax under old vs new brackets."""
        old = calculate_income_tax(Decimal("65000"), "2023-24")
        new = calculate_income_tax(Decimal("65000"), "2025-26")
        # New brackets are more favourable (wider low-rate bands)
        assert new["total_tax"] < old["total_tax"]

    def test_acc_rate_changed(self) -> None:
        """ACC rate changed between 2023-24 (1.53%) and 2025-26 (1.67%)."""
        old = calculate_acc_levy(Decimal("100000"), "2023-24")
        new = calculate_acc_levy(Decimal("100000"), "2025-26")
        assert new["annual_levy"] > old["annual_levy"]
