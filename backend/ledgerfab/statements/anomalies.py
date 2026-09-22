"""The seeded anomalies knob (spec 12 F1), and the ground truth it produces.

**Injectors perturb the plan, never the postings.** Raising receivables directly would
leave the books unbalanced; raising ``receivable_days`` lets `postings.py` re-derive
collections, cash and the revolver around it, and the balance sheet still balances.
That is why `test_emitter_anomalies` can assert the four articulation invariants
*with every injector switched on* — an anomaly that breaks the books is a bug, not an
anomaly (PLAN.md P2 risk (b)).

**Injectors are defined by economic behaviour, not by the rule list.** If each one were
written backwards from a shipped red-flag rule, flag recall would measure wiring rather
than detection. So each describes a thing a business does, and ``expected_rule_ids``
records — separately — which rules *ought* to notice. `capex_pause` deliberately maps
to none: underinvestment is real, this project ships no rule for it, and without at
least one such case recall would be 100% by construction (PLAN.md **D-015**).

**``expected_rule_ids`` is a claim, and P5 verifies it.** The rule engine does not
exist yet, so at the time of writing these mappings are reasoned rather than observed.
`tests/test_rules_matrix.py` will assert that every id named here *actually fires* on
the profile that injects it; a mapping that turns out to be wishful is a test failure
that gets fixed here, not a footnote. Two of them have already been corrected by
measurement — see `_debt_spike` — which is the argument for checking rather than
trusting the reasoning.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from ledgerfab.rng import Rng
from ledgerfab.statements.models import AnomalyTruth
from ledgerfab.statements.money import ZERO, money, pct
from ledgerfab.statements.plan import PeriodPlan

Plans = tuple[PeriodPlan, ...]
Injector = Callable[[Plans, Rng], Plans]


@dataclass(frozen=True, slots=True)
class Anomaly:
    """One economic pattern, and what a competent rule set ought to make of it."""

    id: str
    kind: str
    description: str
    #: How many periods at the end of the series the pattern occupies. The tail,
    #: because a deterioration a reader is meant to notice is a recent one.
    tail: int
    expected_rule_ids: tuple[str, ...]
    apply: Injector

    def truth(self, plans: Plans) -> AnomalyTruth:
        affected = tuple(p.period.id for p in plans[-self.tail :]) if self.tail else ()
        return AnomalyTruth(
            anomaly_id=self.id,
            kind=self.kind,
            description=self.description,
            period_ids=affected,
            expected_rule_ids=self.expected_rule_ids,
        )


def _tail_indices(plans: Plans, tail: int) -> range:
    return range(max(0, len(plans) - tail), len(plans))


def _ramp(step: int, per_step: Decimal) -> Decimal:
    """A deterioration that gets worse each period rather than arriving all at once.

    Streak rules exist to catch direction sustained over time, so a single-period step
    change would be an unfair test of them — it would look like a one-off, because it
    would be one.
    """
    return pct(per_step) * Decimal(step + 1)


def _grow(value: Decimal, step: int, per_step: str) -> Decimal:
    """``value`` compounded by a ramping deterioration. The shape of most injectors."""
    return money(value * (Decimal(1) + _ramp(step, Decimal(per_step))))


# ---------------------------------------------------------------- injectors --


def _ar_days_balloon(plans: Plans, rng: Rng) -> Plans:
    """Collections slip badly while trading holds up.

    Revenue growth is flattened at the same time, because the interesting version of
    this is receivables rising *without* sales rising — a collections problem, not a
    growth-funded build.
    """
    out = list(plans)
    for step, i in enumerate(_tail_indices(plans, 4)):
        base = plans[i]
        out[i] = base.with_(
            receivable_days=_grow(base.receivable_days, step, "0.14"),
            revenue=money(plans[max(0, i - 1)].revenue * Decimal("1.002")),
        )
    return tuple(out)


def _margin_compression(plans: Plans, rng: Rng) -> Plans:
    """Gross margin gives way a little further every period — input costs the entity
    cannot pass on. Four periods, so a three-period streak rule has something to see
    and one period of margin recovery would not hide it."""
    out = list(plans)
    for step, i in enumerate(_tail_indices(plans, 4)):
        base = plans[i]
        out[i] = base.with_(gross_margin=pct(base.gross_margin) - pct("0.022") * Decimal(step + 1))
    return tuple(out)


def _ocf_ni_divergence(plans: Plans, rng: Rng) -> Plans:
    """Profitable on paper, haemorrhaging cash: receivables and inventory both build
    hard while the P&L still reports income. The single most useful thing a first-pass
    analysis can surface, and the reason `cf_operating` is computed rather than
    narrated."""
    out = list(plans)
    for step, i in enumerate(_tail_indices(plans, 3)):
        base = plans[i]
        out[i] = base.with_(
            receivable_days=_grow(base.receivable_days, step, "0.22"),
            inventory_days=_grow(base.inventory_days, step, "0.20"),
            payable_days=money(base.payable_days * Decimal("0.92")),
        )
    return tuple(out)


def _liquidity_squeeze(plans: Plans, rng: Rng) -> Plans:
    """Over-investment into a downturn: heavy capex funded by the revolving facility,
    which drives the current ratio through 1.

    **The first version of this injector did the opposite of what it claimed**, and it
    is worth recording why, because the mistake is an easy one to make in a spreadsheet
    too. It stretched *payable* days — and paying suppliers more slowly generates cash.
    Worse, payables and cash both sit in the current section, so the current ratio
    barely moved: current liabilities rose and current assets rose with them.

    What actually pushes a current ratio below 1 is moving value *out* of the current
    section while funding it from *within* — which is precisely capex on an overdraft.
    Cash (a current asset) becomes plant (a non-current asset), and the facility that
    paid for it (a current liability) stays behind. Slower collections are kept as a
    secondary driver; they are what makes it feel like a squeeze rather than a choice.
    """
    out = list(plans)
    for step, i in enumerate(_tail_indices(plans, 3)):
        base = plans[i]
        out[i] = base.with_(
            # Sized so the breach is not arguable. At 3× the current ratio finished at
            # 1.04 — a threshold rule sitting four hundredths from its boundary, where
            # the "correct" answer depends on rounding rather than on the business.
            # finsight hit the same class of problem (its D-018) and the fix is the
            # same: move the *driver* until there is a clear dead zone around the
            # threshold, never move the threshold.
            capex=money(base.capex * (Decimal(6) + _ramp(step, Decimal("2.0")))),
            receivable_days=_grow(base.receivable_days, step, "0.12"),
            min_cash=money(base.min_cash * Decimal("0.30")),
        )
    return tuple(out)


def _inventory_build(plans: Plans, rng: Rng) -> Plans:
    """Stock accumulates faster than it sells — obsolescence, or a demand call that
    did not land."""
    out = list(plans)
    for step, i in enumerate(_tail_indices(plans, 4)):
        base = plans[i]
        out[i] = base.with_(inventory_days=_grow(base.inventory_days, step, "0.15"))
    return tuple(out)


def _payable_stretch(plans: Plans, rng: Rng) -> Plans:
    """Suppliers get paid later and later. Flattering to cash, and a leading indicator
    of the opposite."""
    out = list(plans)
    for step, i in enumerate(_tail_indices(plans, 4)):
        base = plans[i]
        out[i] = base.with_(payable_days=_grow(base.payable_days, step, "0.18"))
    return tuple(out)


def _debt_spike(plans: Plans, rng: Rng) -> Plans:
    """A drawdown lifts gearing and interest cost, and interest cover falls with it.

    **Sized deliberately, and the first draft was wrong.** A £3.4m term draw was large
    enough to repay the whole revolving facility, which moved borrowing out of current
    liabilities and made the current ratio *improve* — in the profile whose entire
    point is a liquidity squeeze. Measurement caught it: the ratio went 0.92 → 2.94 in
    the period the spike landed. A term facility that rescues working capital is a
    real thing, but stacking it with `liquidity_squeeze` produced a set whose ground
    truth contradicted itself. £1.2m raises gearing without paying off the revolver.
    """
    out = list(plans)
    indices = list(_tail_indices(plans, 3))
    first = indices[0]
    out[first] = plans[first].with_(debt_drawn=money("1200000.00"), debt_repaid=ZERO)
    for i in indices[1:]:
        out[i] = plans[i].with_(debt_repaid=ZERO)
    return tuple(out)


def _revenue_decline(plans: Plans, rng: Rng) -> Plans:
    """Sales fall for three periods running — a streak, not a wobble."""
    out = list(plans)
    for step, i in enumerate(_tail_indices(plans, 3)):
        base = plans[i]
        factor = Decimal(1) - pct("0.07") * Decimal(step + 1)
        out[i] = base.with_(
            revenue=money(base.revenue * factor),
            payroll=money(base.payroll * factor),
            selling=money(base.selling * factor),
        )
    return tuple(out)


def _capex_pause(plans: Plans, rng: Rng) -> Plans:
    """Investment stops dead while the asset base keeps depreciating.

    **This is the deliberately unruled one** (PLAN.md **D-015**). It is a real pattern
    a human analyst would flag — the entity is consuming its asset base — and this
    project ships no rule that fires on it. It exists so flag-mention recall is
    measuring detection rather than confirming that every planted anomaly had a rule
    written for it.
    """
    out = list(plans)
    for i in _tail_indices(plans, 4):
        out[i] = plans[i].with_(capex=money(plans[i].capex * Decimal("0.05")))
    return tuple(out)


# ------------------------------------------------------------------ registry --

ANOMALIES: tuple[Anomaly, ...] = (
    Anomaly(
        "ar_days_balloon",
        "efficiency",
        "Receivable days climb sharply over the final periods while revenue is flat — "
        "a collections problem rather than a growth-funded receivable build.",
        4,
        ("efficiency.receivable_days_up_while_revenue_flat",),
        _ar_days_balloon,
    ),
    Anomaly(
        "margin_compression",
        "profitability",
        "Gross margin gives way a little further every period: input costs the entity "
        "is not passing on.",
        4,
        ("profitability.margin_compression_streak",),
        _margin_compression,
    ),
    Anomaly(
        "ocf_ni_divergence",
        "cashflow",
        "Net income stays positive while operating cash flow turns negative — "
        "receivables and inventory absorbing more cash than trading generates.",
        3,
        ("cashflow.negative_ocf_with_positive_ni",),
        _ocf_ni_divergence,
    ),
    Anomaly(
        "liquidity_squeeze",
        "liquidity",
        "Cash drains and the revolving facility takes the strain, pushing short-term "
        "debt into current liabilities until the current ratio breaks 1.",
        3,
        ("liquidity.current_ratio_below_1",),
        _liquidity_squeeze,
    ),
    Anomaly(
        "inventory_build",
        "efficiency",
        "Inventory days rise steadily: stock accumulating faster than it sells.",
        4,
        ("efficiency.inventory_days_spike",),
        _inventory_build,
    ),
    Anomaly(
        "payable_stretch",
        "efficiency",
        "Payable days stretch period after period — suppliers financing the entity.",
        4,
        ("efficiency.payable_days_stretch",),
        _payable_stretch,
    ),
    Anomaly(
        "debt_spike",
        "leverage",
        "A drawdown lifts gearing and interest cost, and interest cover falls with it.",
        3,
        ("leverage.interest_cover_below_2",),
        _debt_spike,
    ),
    Anomaly(
        "revenue_decline",
        "profitability",
        "Revenue falls for three consecutive periods.",
        3,
        ("profitability.revenue_decline_streak",),
        _revenue_decline,
    ),
    Anomaly(
        "capex_pause",
        "structure",
        "Capital expenditure stops while the asset base keeps depreciating — the "
        "entity is consuming its productive capacity. DELIBERATELY UNRULED: no shipped "
        "rule fires on this, so flag recall stays a real measurement.",
        4,
        (),
        _capex_pause,
    ),
)

ANOMALIES_BY_ID: dict[str, Anomaly] = {a.id: a for a in ANOMALIES}


def resolve(names: tuple[str, ...]) -> tuple[Anomaly, ...]:
    unknown = [n for n in names if n not in ANOMALIES_BY_ID]
    if unknown:
        known = ", ".join(sorted(ANOMALIES_BY_ID))
        raise ValueError(f"unknown anomaly {unknown}; expected one of: {known}")
    return tuple(ANOMALIES_BY_ID[n] for n in names)


def apply_anomalies(
    plans: Plans, names: tuple[str, ...], rng: Rng
) -> tuple[Plans, tuple[AnomalyTruth, ...]]:
    """Apply each named injector in order, and record what was done.

    Each injector draws from its own named sub-stream, so adding one to a profile
    cannot shift the numbers another one draws — the same property the vendored
    ``Rng`` provides for generators, and the reason eval cases stay stable as the
    anomaly set grows.
    """
    truths: list[AnomalyTruth] = []
    for anomaly in resolve(names):
        plans = anomaly.apply(plans, rng.child(anomaly.id))
        truths.append(anomaly.truth(plans))
    return plans, tuple(truths)
