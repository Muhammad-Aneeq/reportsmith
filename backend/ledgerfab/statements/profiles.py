"""Named statement profiles — the presets a caller actually reaches for.

The vendored engine's presets (`clean` / `realistic` / `nightmare`) describe how *messy
the data* is. These describe how the *business is doing*, which is the axis statement
analysis cares about. Both exist; they are not the same knob and merging them would
make one of the two meanings unreachable.

`steady` is the control. It ships no injected anomalies, which makes it the case that
proves the red-flag engine does not simply fire on everything.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ledgerfab.statements.plan import BusinessProfile


@dataclass(frozen=True, slots=True)
class StatementProfile:
    """A business, plus the anomalies to inject into its plan."""

    name: str
    business: BusinessProfile
    anomalies: tuple[str, ...] = ()
    description: str = ""


STEADY = StatementProfile(
    name="steady",
    description=(
        "A profitable, unremarkable trading company. No injected anomalies — the "
        "control case, and the one that proves the rule engine does not fire on "
        "everything."
    ),
    business=BusinessProfile(
        name="steady",
        entity_name="Harbourline Logistics Ltd",
    ),
)

GROWTH = StatementProfile(
    name="growth",
    description=(
        "Growing fast and funding the working capital that comes with it. No injected "
        "anomalies, but the receivable and inventory build is real — a good test of "
        "whether the narrative can tell growth-funded absorption apart from distress."
    ),
    business=BusinessProfile(
        name="growth",
        entity_name="Meridian Foods Ltd",
        opening_revenue=Decimal("2100000.00"),
        revenue_growth=Decimal("0.115"),
        gross_margin=Decimal("0.420"),
        # Trimmed from 18.5%/9.5%/210k after the first run: the profile was
        # loss-making in its opening periods, and a "growth" case that is quietly a
        # loss-making case cannot test the thing it exists to test — whether the
        # narrative distinguishes growth-funded absorption from distress.
        payroll_pct_revenue=Decimal("0.160"),
        selling_pct_revenue=Decimal("0.080"),
        admin_per_period=Decimal("185000.00"),
        receivable_days=Decimal("48"),
        inventory_days=Decimal("64"),
        payable_days=Decimal("40"),
        capex_per_period=Decimal("320000.00"),
        opening_cash=Decimal("900000.00"),
        opening_debt_long=Decimal("1500000.00"),
        dividend_payout=Decimal("0.000"),
        debt_repayment_per_period=Decimal("60000.00"),
    ),
)

PAPER_PROFIT = StatementProfile(
    name="paper_profit",
    description=(
        "Solidly profitable on the P&L and burning cash underneath it: receivables "
        "and inventory absorbing more than trading generates. The single most "
        "valuable thing a first-pass analysis can surface, and it gets its own "
        "profile because `ocf_ni_divergence` needs net income to STAY POSITIVE to be "
        "the pattern it claims to be — stacked onto `distress` it had nothing to "
        "diverge from."
    ),
    business=BusinessProfile(
        name="paper_profit",
        entity_name="Beacon & Vale Ltd",
        opening_revenue=Decimal("3400000.00"),
        revenue_growth=Decimal("0.025"),
        gross_margin=Decimal("0.405"),
        payroll_pct_revenue=Decimal("0.140"),
        selling_pct_revenue=Decimal("0.055"),
        admin_per_period=Decimal("225000.00"),
        opening_cash=Decimal("1500000.00"),
        opening_debt_long=Decimal("1600000.00"),
        dividend_payout=Decimal("0.150"),
    ),
    anomalies=("ocf_ni_divergence",),
)

SQUEEZE = StatementProfile(
    name="squeeze",
    description=(
        "Margins giving way and collections slipping at the same time. The demo "
        "default: two independent deteriorations that a reader should be able to see "
        "separately in the ratio pack."
    ),
    business=BusinessProfile(
        name="squeeze",
        entity_name="Coldharbour Manufacturing Ltd",
        opening_revenue=Decimal("3600000.00"),
        revenue_growth=Decimal("0.012"),
        gross_margin=Decimal("0.345"),
        admin_per_period=Decimal("265000.00"),
        receivable_days=Decimal("46"),
        inventory_days=Decimal("62"),
        opening_debt_long=Decimal("2600000.00"),
    ),
    anomalies=("margin_compression", "ar_days_balloon", "inventory_build"),
)

DISTRESS = StatementProfile(
    name="distress",
    description=(
        "Sales falling, margins going with them, and equity eroding period after "
        "period while investment stops. Opens marginally profitable so the "
        "deterioration is visible rather than merely bad, and the narrative's honest "
        "limits section has to resist diagnosing a cause it cannot see."
    ),
    business=BusinessProfile(
        name="distress",
        entity_name="Stonebridge Services Ltd",
        opening_revenue=Decimal("2900000.00"),
        revenue_growth=Decimal("-0.010"),
        # Opens marginally profitable rather than already loss-making. The first draft
        # was under water in period 1, which made the deterioration invisible: every
        # trend arrow pointed down from a position that was already bad, so nothing in
        # the ratio pack could show the entity *becoming* distressed.
        gross_margin=Decimal("0.355"),
        payroll_pct_revenue=Decimal("0.155"),
        selling_pct_revenue=Decimal("0.050"),
        admin_per_period=Decimal("220000.00"),
        receivable_days=Decimal("52"),
        inventory_days=Decimal("70"),
        payable_days=Decimal("44"),
        opening_cash=Decimal("620000.00"),
        opening_debt_long=Decimal("2400000.00"),
        opening_debt_short=Decimal("300000.00"),
        interest_annual_rate=Decimal("0.089"),
        capex_per_period=Decimal("120000.00"),
        dividend_payout=Decimal("0.000"),
        min_cash=Decimal("150000.00"),
    ),
    # Three injectors, not five. The first draft stacked `ocf_ni_divergence`,
    # `liquidity_squeeze` and `debt_spike` on top of these and the set contradicted
    # itself: the divergence needs positive net income and this profile has none;
    # the squeeze raises capex while `capex_pause` zeroes it; and the term drawdown
    # repaid the revolver, so the "distressed" entity ended with a current ratio of
    # 3.5 and rising cash. Losses are enough of a story on their own — they burn cash,
    # the facility covers it, and the current ratio falls without help.
    anomalies=("revenue_decline", "margin_compression", "capex_pause"),
)

LEVERAGED = StatementProfile(
    name="leveraged",
    description=(
        "Over-investment into a downturn, funded on the facility: gearing climbs, "
        "interest cover falls, and the current ratio breaks 1 as cash turns into "
        "plant while the borrowing that paid for it stays in current liabilities."
    ),
    business=BusinessProfile(
        name="leveraged",
        entity_name="Northwind Trading Ltd",
        opening_revenue=Decimal("3100000.00"),
        revenue_growth=Decimal("0.008"),
        # Opens modestly profitable. Same correction as `distress`: an entity that is
        # already loss-making in period 1 has no deterioration for the trend engine to
        # show, and the story here is what the over-investment *does*, not where it
        # started.
        gross_margin=Decimal("0.350"),
        payroll_pct_revenue=Decimal("0.150"),
        selling_pct_revenue=Decimal("0.055"),
        admin_per_period=Decimal("225000.00"),
        opening_cash=Decimal("700000.00"),
        opening_deposit=Decimal("200000.00"),
        opening_debt_long=Decimal("2800000.00"),
        interest_annual_rate=Decimal("0.082"),
        capex_per_period=Decimal("200000.00"),
        dividend_payout=Decimal("0.100"),
        min_cash=Decimal("200000.00"),
    ),
    anomalies=("liquidity_squeeze", "debt_spike"),
)

PROFILES: dict[str, StatementProfile] = {
    p.name: p for p in (STEADY, GROWTH, PAPER_PROFIT, SQUEEZE, LEVERAGED, DISTRESS)
}

DEFAULT_PROFILE = "squeeze"


def get_profile(profile: str | StatementProfile) -> StatementProfile:
    """Resolve by name, or pass a custom profile straight through."""
    if isinstance(profile, StatementProfile):
        return profile
    try:
        return PROFILES[profile]
    except KeyError:
        known = ", ".join(sorted(PROFILES))
        raise ValueError(
            f"unknown statement profile {profile!r}; expected one of: {known}"
        ) from None
