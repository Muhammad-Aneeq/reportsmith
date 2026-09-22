"""The anomalies knob (spec 12 F1), and the ground truth it emits.

Two claims are being tested, and the second is the one that matters most:

1. **Each injector does what it says.** The targeted metric moves in the stated
   direction, measurably, against the same profile with the injector switched off.
   Comparing against the *unperturbed same-seed set* rather than against an absolute
   threshold is what makes this a test of the injector rather than of the profile.

2. **An injected anomaly never breaks the books.** Every articulation invariant holds
   with every injector on. This is the payoff for injectors perturbing the *plan*
   rather than the postings (PLAN.md **D-003**): raising receivables directly would
   unbalance the balance sheet, whereas raising `receivable_days` lets `postings.py`
   re-derive collections, cash and the revolver around it.

An anomaly that breaks the books is a bug, not an anomaly.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

import pytest

from ledgerfab.statements import ANOMALIES, ANOMALIES_BY_ID, StatementSet, emit_statements
from ledgerfab.statements.money import ZERO, money

ANOMALY_IDS = sorted(ANOMALIES_BY_ID)


def _assert_books_intact(st: StatementSet, context: str) -> None:
    for entry in st.entries:
        assert entry.is_balanced, f"{context}: {entry.id} ({entry.memo}) does not balance"
    for period in st.periods:
        assert st.amount(period.id, "total_assets") == st.amount(
            period.id, "total_liabilities_and_equity"
        ), f"{context}/{period.id}: balance sheet does not balance"
        assert st.amount(period.id, "cf_cash_close") == st.amount(period.id, "cash"), (
            f"{context}/{period.id}: cash flow does not articulate"
        )


def _tail_mean(st: StatementSet, line_code: str, n: int = 3) -> Decimal:
    values = [v for v in st.series(line_code)[-n:] if v is not None]
    return money(sum(values, ZERO) / Decimal(len(values)))


def _ratio_tail(st: StatementSet, numerator: str, denominator: str, n: int = 3) -> Decimal:
    """A crude ratio over the tail — enough to detect direction without importing the
    computation engine, which does not exist yet and must not be a dependency of the
    emitter's own tests."""
    num = _tail_mean(st, numerator, n)
    den = _tail_mean(st, denominator, n)
    return num / den if den != ZERO else ZERO


# ------------------------------------------------- the books survive it all --


@pytest.mark.parametrize("anomaly_id", ANOMALY_IDS)
def test_each_injector_leaves_the_books_intact(anomaly_id: str) -> None:
    _assert_books_intact(emit_statements("steady", seed=42, anomalies=(anomaly_id,)), anomaly_id)


def test_every_injector_at_once_leaves_the_books_intact() -> None:
    """The adversarial case: all nine stacked, including the ones that fight.

    Their *economics* contradict — `liquidity_squeeze` raises capex while `capex_pause`
    zeroes it — and the resulting entity is nonsense as a business. That is fine and
    it is the point: the accounting must still hold whatever the plan asks for.
    """
    st = emit_statements("steady", seed=42, anomalies=tuple(ANOMALY_IDS))
    _assert_books_intact(st, "all-injectors")
    assert len(st.ground_truth.anomalies) == len(ANOMALY_IDS)


@pytest.mark.parametrize("grain", ["month", "quarter", "year"])
def test_injectors_survive_every_grain(grain: str) -> None:
    periods = 4 if grain == "year" else 8
    st = emit_statements("squeeze", seed=42, periods=periods, grain=grain)
    _assert_books_intact(st, f"squeeze/{grain}")


# ------------------------------------------------- each injector does its job --


def test_ar_days_balloon_slows_collections() -> None:
    off = emit_statements("steady", seed=42, anomalies=())
    on = emit_statements("steady", seed=42, anomalies=("ar_days_balloon",))
    # Receivables per unit of revenue — the shape of a days metric, without needing one.
    assert _ratio_tail(on, "accounts_receivable", "revenue") > _ratio_tail(
        off, "accounts_receivable", "revenue"
    ) * Decimal("1.25")


def test_margin_compression_reduces_gross_margin_every_period() -> None:
    st = emit_statements("steady", seed=42, anomalies=("margin_compression",))
    margins = [
        (st.amount(p.id, "gross_profit") or ZERO) / (st.amount(p.id, "revenue") or Decimal(1))
        for p in st.periods
    ]
    tail = margins[-4:]
    assert all(later < earlier for earlier, later in pairwise(tail)), (
        f"expected a monotonic decline over the final four periods, got {tail}"
    )
    assert tail[-1] < margins[0] - Decimal("0.05")


def test_ocf_ni_divergence_produces_positive_income_and_negative_operating_cash() -> None:
    """The pattern this injector exists for, on the profile built to carry it.

    `paper_profit` is a separate profile precisely because this test failed on
    `distress`: net income there was already negative, so there was nothing for
    operating cash flow to diverge *from* and the ground-truth label was unreachable.
    """
    st = emit_statements("paper_profit", seed=42)
    tail = st.periods[-3:]
    for period in tail:
        assert (st.amount(period.id, "net_income") or ZERO) > ZERO, (
            f"{period.id}: net income must stay positive for the divergence to be one"
        )
        assert (st.amount(period.id, "cf_operating") or ZERO) < ZERO, (
            f"{period.id}: operating cash flow should be negative"
        )


def test_liquidity_squeeze_drives_the_current_ratio_below_one() -> None:
    st = emit_statements("leveraged", seed=42)
    ratios = [
        (st.amount(p.id, "total_current_assets") or ZERO)
        / (st.amount(p.id, "total_current_liabilities") or Decimal(1))
        for p in st.periods
    ]
    assert ratios[0] > Decimal("2.0"), "should start comfortably liquid"
    assert min(ratios) < Decimal("1.0"), f"never breaks 1: {[f'{r:.2f}' for r in ratios]}"


def test_no_generated_ratio_sits_on_the_current_ratio_threshold() -> None:
    """No profile may leave a current ratio within 0.10 of 1.0.

    A threshold rule evaluated against a ratio of 0.99 is a coin toss dressed as a
    measurement: a one-line change anywhere upstream flips the expected answer and the
    eval starts failing for reasons unrelated to what it tests. The fix when this trips
    is to move the *driver* — capex, collection days — never the threshold.
    (finsight hit the same class of problem; its D-018.)
    """
    from ledgerfab.statements import PROFILES

    offenders: list[str] = []
    for name in sorted(PROFILES):
        st = emit_statements(name, seed=42)
        for period in st.periods:
            ratio = (st.amount(period.id, "total_current_assets") or ZERO) / (
                st.amount(period.id, "total_current_liabilities") or Decimal(1)
            )
            if abs(ratio - Decimal(1)) < Decimal("0.10"):
                offenders.append(f"{name}/{period.id}={ratio:.3f}")
    assert not offenders, f"current ratios sitting on the 1.0 boundary: {offenders}"


def test_inventory_build_raises_stock_relative_to_cost_of_sales() -> None:
    off = emit_statements("steady", seed=42, anomalies=())
    on = emit_statements("steady", seed=42, anomalies=("inventory_build",))
    assert _ratio_tail(on, "inventory", "cogs") > _ratio_tail(off, "inventory", "cogs") * Decimal(
        "1.25"
    )


def test_payable_stretch_raises_payables_relative_to_costs() -> None:
    off = emit_statements("steady", seed=42, anomalies=())
    on = emit_statements("steady", seed=42, anomalies=("payable_stretch",))
    assert _ratio_tail(on, "accounts_payable", "cogs") > _ratio_tail(
        off, "accounts_payable", "cogs"
    ) * Decimal("1.25")


def test_debt_spike_raises_borrowings_and_interest() -> None:
    off = emit_statements("steady", seed=42, anomalies=())
    on = emit_statements("steady", seed=42, anomalies=("debt_spike",))
    assert _tail_mean(on, "long_term_debt") > _tail_mean(off, "long_term_debt")
    assert _tail_mean(on, "interest_expense") > _tail_mean(off, "interest_expense")


def test_revenue_decline_falls_for_three_consecutive_periods() -> None:
    st = emit_statements("steady", seed=42, anomalies=("revenue_decline",))
    series = [v for v in st.series("revenue") if v is not None]
    tail = series[-3:]
    assert all(later < earlier for earlier, later in pairwise(tail)), (
        f"expected a decline streak, got {tail}"
    )


def test_capex_pause_stops_investment_while_depreciation_continues() -> None:
    st = emit_statements("steady", seed=42, anomalies=("capex_pause",))
    off = emit_statements("steady", seed=42, anomalies=())
    assert _tail_mean(st, "cf_capex") > _tail_mean(off, "cf_capex")  # less negative
    assert _tail_mean(st, "depreciation") > ZERO


# ---------------------------------------------------------- the ground truth --


def test_ground_truth_records_every_injection() -> None:
    st = emit_statements("squeeze", seed=42)
    recorded = {a.anomaly_id for a in st.ground_truth.anomalies}
    assert recorded == {"margin_compression", "ar_days_balloon", "inventory_build"}
    for anomaly in st.ground_truth.anomalies:
        assert anomaly.period_ids, f"{anomaly.anomaly_id} names no periods"
        assert set(anomaly.period_ids) <= set(st.period_ids)
        assert anomaly.description.strip()


def test_capex_pause_is_deliberately_unruled() -> None:
    """PLAN.md **D-015**. If every planted anomaly mapped to a shipped rule, flag
    recall would be 100% by construction and would measure wiring, not detection."""
    assert ANOMALIES_BY_ID["capex_pause"].expected_rule_ids == ()
    st = emit_statements("distress", seed=42)
    unruled = {a.anomaly_id for a in st.ground_truth.unruled}
    assert "capex_pause" in unruled


def test_exactly_one_anomaly_is_unruled() -> None:
    """One is deliberate; two would start to look like an excuse for a thin rule set."""
    unruled = [a.id for a in ANOMALIES if not a.expected_rule_ids]
    assert unruled == ["capex_pause"]


def test_expected_rule_ids_are_well_formed() -> None:
    """`category.rule_name`, matching the YAML files P5 ships. Checked now because a
    typo here would be discovered as a silent recall miss much later."""
    for anomaly in ANOMALIES:
        for rule_id in anomaly.expected_rule_ids:
            category, _, name = rule_id.partition(".")
            assert name, f"{anomaly.id}: malformed rule id {rule_id!r}"
            assert category in {
                "liquidity",
                "profitability",
                "leverage",
                "efficiency",
                "cashflow",
                "structure",
            }, f"{anomaly.id}: unknown rule category {category!r}"


def test_profiles_with_no_anomalies_carry_an_empty_answer_key() -> None:
    """The control cases. `steady` and `growth` are what prove the rule engine does not
    simply fire on everything."""
    for name in ("steady", "growth"):
        assert emit_statements(name, seed=42).ground_truth.anomalies == ()


def test_an_unknown_anomaly_is_rejected_loudly() -> None:
    with pytest.raises(ValueError, match="unknown anomaly"):
        emit_statements("steady", seed=42, anomalies=("no_such_pattern",))
