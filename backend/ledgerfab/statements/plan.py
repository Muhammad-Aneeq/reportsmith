"""The operating plan — the economic story, before it becomes accounting.

This is the layer anomaly injectors act on, and that is the whole reason it exists as
a separate step (PLAN.md **D-003**). An injector that reached into the postings to
raise receivables would leave the books unbalanced; an injector that raises
``receivable_days`` in the plan lets `postings.py` re-derive collections, cash, and the
revolver around it, and the balance sheet still balances. The invariant tests then
assert exactly that — *with every injector on*.

A ``BusinessProfile`` describes an entity: how it opens, how it trades, how quickly it
collects and pays. ``build_plans`` turns it into one ``PeriodPlan`` per period, which
is a fully-resolved set of numbers with no randomness left in it. Everything after this
point is deterministic arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from ledgerfab.rng import Rng
from ledgerfab.statements.models import Period
from ledgerfab.statements.money import ZERO, money, pct, prorate, share


@dataclass(frozen=True, slots=True)
class BusinessProfile:
    """A synthetic entity. Every field is a lever an anomaly injector can pull."""

    name: str
    entity_name: str
    currency: str = "GBP"

    # -- opening balance sheet ------------------------------------------------
    opening_cash: Decimal = Decimal("1200000.00")
    opening_deposit: Decimal = Decimal("500000.00")
    opening_receivables: Decimal = Decimal("1450000.00")
    opening_inventory: Decimal = Decimal("820000.00")
    opening_prepayments: Decimal = Decimal("110000.00")
    opening_payables: Decimal = Decimal("980000.00")
    opening_accruals: Decimal = Decimal("140000.00")
    opening_tax_payable: Decimal = Decimal("95000.00")
    opening_debt_short: Decimal = ZERO
    opening_debt_long: Decimal = Decimal("2000000.00")
    opening_ppe_gross: Decimal = Decimal("4200000.00")
    opening_accum_depreciation: Decimal = Decimal("1350000.00")
    opening_share_capital: Decimal = Decimal("1000000.00")
    #: Retained earnings is the plug that makes the opening balance sheet balance.
    #: Computed in `postings.py`, never supplied — a hand-set opening RE is the
    #: easiest possible way to ship an opening balance sheet that does not balance.

    # -- trading --------------------------------------------------------------
    opening_revenue: Decimal = Decimal("3200000.00")
    revenue_growth: Decimal = Decimal("0.030")
    gross_margin: Decimal = Decimal("0.380")
    payroll_pct_revenue: Decimal = Decimal("0.150")
    selling_pct_revenue: Decimal = Decimal("0.060")
    admin_per_period: Decimal = Decimal("240000.00")

    # -- working capital, in days of the relevant flow ------------------------
    receivable_days: Decimal = Decimal("42")
    inventory_days: Decimal = Decimal("58")
    payable_days: Decimal = Decimal("38")
    prepayment_days: Decimal = Decimal("14")

    # -- capital --------------------------------------------------------------
    capex_per_period: Decimal = Decimal("180000.00")
    depreciation_annual_rate: Decimal = Decimal("0.100")
    interest_annual_rate: Decimal = Decimal("0.068")
    tax_rate: Decimal = Decimal("0.250")
    dividend_payout: Decimal = Decimal("0.200")
    debt_repayment_per_period: Decimal = Decimal("100000.00")
    equity_issued_per_period: Decimal = ZERO

    #: The revolver. Cash below `min_cash` draws short-term debt; surplus above
    #: `min_cash` repays it. Without this a stressed profile drives the bank balance
    #: negative, and a negative "Cash" line would break the magnitude sign convention
    #: declared in chart.py — an overdraft is a borrowing, and belongs in liabilities.
    min_cash: Decimal = Decimal("250000.00")

    #: Seeded texture: ±this share on revenue and admin, per period. Small on purpose.
    #: Noise is not a story, and a trend engine that has to see through 10% of jitter
    #: is measuring the jitter.
    noise: Decimal = Decimal("0.020")


@dataclass(frozen=True, slots=True)
class PeriodPlan:
    """One period, fully resolved. No randomness survives past this point."""

    period: Period
    revenue: Decimal
    gross_margin: Decimal
    payroll: Decimal
    selling: Decimal
    admin: Decimal
    receivable_days: Decimal
    inventory_days: Decimal
    payable_days: Decimal
    prepayment_days: Decimal
    capex: Decimal
    depreciation_annual_rate: Decimal
    interest_annual_rate: Decimal
    tax_rate: Decimal
    dividend_payout: Decimal
    debt_repaid: Decimal
    debt_drawn: Decimal
    equity_issued: Decimal
    min_cash: Decimal

    @property
    def cogs(self) -> Decimal:
        return money(self.revenue * (Decimal(1) - self.gross_margin))

    @property
    def gross_profit(self) -> Decimal:
        return money(self.revenue - self.cogs)

    def target_receivables(self) -> Decimal:
        return self._days_of(self.revenue, self.receivable_days)

    def target_inventory(self) -> Decimal:
        return self._days_of(self.cogs, self.inventory_days)

    def target_payables(self, credit_purchases: Decimal) -> Decimal:
        return self._days_of(credit_purchases, self.payable_days)

    def target_prepayments(self) -> Decimal:
        return self._days_of(self.admin, self.prepayment_days)

    def _days_of(self, flow: Decimal, days: Decimal) -> Decimal:
        """``flow`` is a *period* figure, so the day count is the period's own.

        This is the quarterly-vs-365 trap in its source form: 42 receivable days
        against a quarter's revenue is 42/91 of that quarter, not 42/365 of it.
        """
        if flow <= ZERO or days <= ZERO:
            return ZERO
        return money(flow * days / Decimal(self.period.days))

    def with_(self, **changes: object) -> PeriodPlan:
        """A copy with fields overridden. The only way an injector mutates a plan."""
        return replace(self, **changes)  # type: ignore[arg-type]


def build_plans(
    profile: BusinessProfile, periods: tuple[Period, ...], rng: Rng
) -> tuple[PeriodPlan, ...]:
    """A ``BusinessProfile`` plus a period grid becomes one plan per period.

    Growth compounds per period, and the seeded noise is applied to revenue and admin
    only — the ratios (margin, payroll share) stay clean so that a *changed* margin in
    the output is always something an injector did, never something the noise did.
    That separation is what makes the anomaly ground truth trustworthy.
    """
    plans: list[PeriodPlan] = []
    revenue = profile.opening_revenue
    noise_rng = rng.child("noise")

    for period in periods:
        jitter = _jitter(noise_rng, profile.noise)
        period_revenue = money(revenue * (Decimal(1) + jitter))
        admin = money(profile.admin_per_period * (Decimal(1) + _jitter(noise_rng, profile.noise)))

        plans.append(
            PeriodPlan(
                period=period,
                revenue=period_revenue,
                gross_margin=pct(profile.gross_margin),
                payroll=share(period_revenue, profile.payroll_pct_revenue),
                selling=share(period_revenue, profile.selling_pct_revenue),
                admin=admin,
                receivable_days=profile.receivable_days,
                inventory_days=profile.inventory_days,
                payable_days=profile.payable_days,
                prepayment_days=profile.prepayment_days,
                capex=profile.capex_per_period,
                depreciation_annual_rate=profile.depreciation_annual_rate,
                interest_annual_rate=profile.interest_annual_rate,
                tax_rate=profile.tax_rate,
                dividend_payout=profile.dividend_payout,
                debt_repaid=profile.debt_repayment_per_period,
                debt_drawn=ZERO,
                equity_issued=profile.equity_issued_per_period,
                min_cash=profile.min_cash,
            )
        )
        revenue = money(revenue * (Decimal(1) + profile.revenue_growth))

    return tuple(plans)


def _jitter(rng: Rng, amplitude: Decimal) -> Decimal:
    """A deterministic ±``amplitude`` factor.

    Routed through the vendored ``Rng`` — the package's single sanctioned source of
    randomness — and immediately converted to ``Decimal`` via ``str`` so no float ever
    reaches the money path.
    """
    if amplitude <= ZERO:
        return ZERO
    a = float(amplitude)
    return Decimal(str(round(rng.uniform(-a, a), 6)))


def period_depreciation(plan: PeriodPlan, gross_ppe: Decimal) -> Decimal:
    """Straight-line on gross cost, pro-rated to the period's own length."""
    return money(gross_ppe * prorate(plan.depreciation_annual_rate, plan.period.days))


def period_interest(plan: PeriodPlan, debt: Decimal) -> Decimal:
    return money(debt * prorate(plan.interest_annual_rate, plan.period.days))
