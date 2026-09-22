"""The statement emitter's correctness claims, asserted to the cent.

Spec 12 F1 asks for *"multi-period P&L/BS/CF **consistent** with its GL worlds"*. This
file is what "consistent" means here, and every assertion is exact equality rather than
a tolerance — Decimal money (PLAN.md **D-005**) is what makes that affordable.

The four headline invariants:

1. every journal balances,
2. ``assets = liabilities + equity`` at every period end,
3. ``retained_earnings_t = retained_earnings_{t-1} + net_income_t − dividends_t``,
4. ``cf_net_change_in_cash = cash_t − cash_{t-1}``.

Plus the one that is not obvious and is the strongest of the five:
``test_indirect_operating_equals_direct_operating`` rebuilds the operating section from
the *cash postings themselves* and requires it to equal the indirect build-up from the
P&L and balance-sheet deltas. Those are two genuinely independent routes to the same
number — one from the journals, one from the statements — so agreement is evidence
rather than tautology.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ledgerfab.statements import PROFILES, StatementSet, emit_statements
from ledgerfab.statements.chart import (
    ACCOUNTS_BY_CODE,
    CASH_CODES,
    LINES_BY_CODE,
    STATEMENT_LINES,
    cash_flow_section,
    is_pnl_account,
)
from ledgerfab.statements.money import ZERO, money

PROFILE_NAMES = sorted(PROFILES)
SEEDS = (42, 7)


@pytest.fixture(scope="module", params=PROFILE_NAMES)
def statements(request: pytest.FixtureRequest) -> StatementSet:
    return emit_statements(request.param, seed=42, periods=8, grain="quarter")


# ------------------------------------------------------------- 1 · journals --


def test_every_journal_balances(statements: StatementSet) -> None:
    unbalanced = [
        (e.id, e.memo, e.total_debit, e.total_credit)
        for e in statements.entries
        if not e.is_balanced
    ]
    assert not unbalanced, f"unbalanced journals: {unbalanced[:5]}"


def test_the_whole_ledger_nets_to_zero(statements: StatementSet) -> None:
    """Σ(debits − credits) over every posting ever made."""
    total = money(sum((line.signed for e in statements.entries for line in e.lines), ZERO))
    assert total == ZERO


def test_no_journal_is_empty(statements: StatementSet) -> None:
    assert all(e.lines for e in statements.entries)


# -------------------------------------------------------- 2 · balance sheet --


def test_balance_sheet_balances(statements: StatementSet) -> None:
    for period in statements.periods:
        assets = statements.amount(period.id, "total_assets")
        liabs_equity = statements.amount(period.id, "total_liabilities_and_equity")
        assert assets == liabs_equity, (
            f"{statements.profile_name}/{period.id}: assets {assets} != "
            f"liabilities+equity {liabs_equity} (out by {assets - liabs_equity})"  # type: ignore[operator]
        )


def test_pnl_accounts_are_closed_at_every_period_end(statements: StatementSet) -> None:
    """After the close, no income or expense account carries a balance.

    This is *why* the balance sheet balances. Without the closing journal, income and
    expense accumulate forever and `assets = liabilities + equity` never holds — so
    asserting it separately says which mechanism is responsible when it breaks.
    """
    balances: dict[str, Decimal] = {}
    for entry in statements.entries:
        for line in entry.lines:
            balances[line.account_code] = money(
                balances.get(line.account_code, ZERO) + line.natural
            )
        if entry.is_closing:
            leftover = {
                code: bal for code, bal in balances.items() if is_pnl_account(code) and bal != ZERO
            }
            assert not leftover, f"P&L accounts still open after {entry.id}: {leftover}"


# --------------------------------------------------- 3 · retained earnings --


def test_retained_earnings_rolls_forward(statements: StatementSet) -> None:
    """``RE_t = RE_{t-1} + NI_t − dividends_t``.

    ``cf_dividends_paid`` is already negative (inflow-positive convention), so it is
    added rather than subtracted.
    """
    previous: Decimal | None = None
    for period in statements.periods:
        current = statements.amount(period.id, "retained_earnings")
        net_income = statements.amount(period.id, "net_income")
        dividends = statements.amount(period.id, "cf_dividends_paid")
        assert current is not None and net_income is not None and dividends is not None

        if previous is not None:
            expected = money(previous + net_income + dividends)
            assert current == expected, (
                f"{statements.profile_name}/{period.id}: retained earnings {current} "
                f"!= {previous} + {net_income} + {dividends} = {expected}"
            )
        previous = current


# ------------------------------------------------------------ 4 · cash flow --


def test_cash_flow_articulates_with_the_balance_sheet(statements: StatementSet) -> None:
    for index, period in enumerate(statements.periods):
        closing_cash = statements.amount(period.id, "cash")
        cf_close = statements.amount(period.id, "cf_cash_close")
        assert cf_close == closing_cash, (
            f"{statements.profile_name}/{period.id}: cash flow closes at {cf_close} "
            f"but the balance sheet says {closing_cash}"
        )

        if index > 0:
            prior_cash = statements.amount(statements.periods[index - 1].id, "cash")
            movement = statements.amount(period.id, "cf_net_change_in_cash")
            assert movement == money(closing_cash - prior_cash)  # type: ignore[operator]
            assert statements.amount(period.id, "cf_cash_open") == prior_cash


def test_indirect_operating_equals_direct_operating(statements: StatementSet) -> None:
    """The strong one: two independent routes to operating cash flow must agree.

    The statements build it indirectly (net income, add back depreciation, adjust for
    working-capital deltas). This test builds it directly, by walking the journals and
    classifying each cash movement by the account sitting opposite it. If the emitter's
    sections were mis-assigned, or a posting escaped the chart, these two would differ
    — and nothing else in this file would notice.
    """
    for period in statements.periods:
        direct: dict[str, Decimal] = {"operating": ZERO, "investing": ZERO, "financing": ZERO}

        for entry in statements.entries:
            if entry.period_id != period.id or entry.is_opening or entry.is_closing:
                continue
            cash_legs = [ln for ln in entry.lines if ln.account_code in CASH_CODES]
            if not cash_legs:
                continue
            others = [ln for ln in entry.lines if ln.account_code not in CASH_CODES]
            assert len(others) == 1, (
                f"{entry.id} ({entry.memo}) has {len(others)} non-cash legs; this test "
                "assumes every cash journal is two-legged so the section is unambiguous"
            )
            section = cash_flow_section(others[0].account_code)
            movement = money(sum((ln.signed for ln in cash_legs), ZERO))
            direct[section] = money(direct[section] + movement)

        for section, line_code in (
            ("operating", "cf_operating"),
            ("investing", "cf_investing"),
            ("financing", "cf_financing"),
        ):
            reported = statements.amount(period.id, line_code)
            assert reported == direct[section], (
                f"{statements.profile_name}/{period.id}: {line_code} reports "
                f"{reported} but the cash postings say {direct[section]}"
            )


# ------------------------------------------------------ presentation rules --


def test_every_subtotal_equals_its_declared_components(statements: StatementSet) -> None:
    """Subtotals are computed from chart.py's declaration, so this checks the
    declaration itself is arithmetically what it claims — a wrong coefficient would
    otherwise produce a self-consistent statement that is quietly wrong."""
    for period in statements.periods:
        for defn in STATEMENT_LINES:
            if not defn.is_subtotal:
                continue
            assert defn.subtotal_of is not None
            expected = money(
                sum(
                    (
                        (statements.amount(period.id, code) or ZERO) * Decimal(coefficient)
                        for code, coefficient in defn.subtotal_of
                    ),
                    ZERO,
                )
            )
            assert statements.amount(period.id, defn.code) == expected, (
                f"{period.id}/{defn.code} does not equal its components"
            )


def test_magnitude_lines_are_never_negative(statements: StatementSet) -> None:
    """chart.py declares each line's sign convention; this is that declaration held to.

    It is also why `postings.py` has a revolver: without one, a stressed profile drives
    the bank balance negative and `cash` — declared a magnitude — goes with it. An
    overdraft is a borrowing and belongs in liabilities.
    """
    offenders = [
        (ln.period_id, ln.line_code, ln.amount)
        for ln in statements.lines
        if LINES_BY_CODE[ln.line_code].sign == "magnitude" and ln.amount < ZERO
    ]
    assert not offenders, f"magnitude lines went negative: {offenders[:5]}"


def test_all_three_statements_are_present_for_every_period(statements: StatementSet) -> None:
    assert statements.statements_present == ("bs", "cf", "pnl")
    for period in statements.periods:
        for statement in ("pnl", "bs", "cf"):
            emitted = {ln.line_code for ln in statements.statement_lines(statement, period.id)}
            declared = {ln.code for ln in STATEMENT_LINES if ln.statement == statement}
            assert emitted == declared


def test_every_posted_account_maps_to_a_statement_line(statements: StatementSet) -> None:
    """No posting may escape the presentation.

    Not housekeeping: the cash-flow identity in `derive.py` holds only because every
    account sits in exactly one section. An account posted to but presented nowhere
    would break the articulation with no other symptom.
    """
    mapped = {code for defn in STATEMENT_LINES for code in defn.accounts}
    posted = {ln.account_code for e in statements.entries for ln in e.lines}
    unmapped = posted - mapped
    assert not unmapped, (
        f"posted but on no statement line: {sorted(unmapped)} "
        f"({[ACCOUNTS_BY_CODE[c].name for c in sorted(unmapped)]})"
    )


# ------------------------------------------------------------ across shapes --


@pytest.mark.parametrize("grain", ["month", "quarter", "year"])
def test_invariants_hold_at_every_grain(grain: str) -> None:
    """The quarterly-vs-365 trap has its own test at the source.

    Working-capital targets are days *of the period's own flow*, so a grain change must
    not disturb the accounting — only the size of each period.
    """
    periods = 4 if grain == "year" else 8
    st = emit_statements("squeeze", seed=42, periods=periods, grain=grain)
    assert len(st.periods) == periods
    for period in st.periods:
        assert st.amount(period.id, "total_assets") == st.amount(
            period.id, "total_liabilities_and_equity"
        )
        assert st.amount(period.id, "cf_cash_close") == st.amount(period.id, "cash")


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("profile", PROFILE_NAMES)
def test_invariants_hold_across_seeds(profile: str, seed: int) -> None:
    st = emit_statements(profile, seed=seed, periods=8, grain="quarter")
    for period in st.periods:
        assert st.amount(period.id, "total_assets") == st.amount(
            period.id, "total_liabilities_and_equity"
        )
        assert st.amount(period.id, "cf_cash_close") == st.amount(period.id, "cash")


def test_a_single_period_set_is_valid() -> None:
    """One period is a legal set. It has no trends and no prior-period comparison,
    which is a case the computation engine has to survive rather than assume away."""
    st = emit_statements("steady", seed=42, periods=1, grain="year")
    assert len(st.periods) == 1
    only = st.periods[0]
    assert st.amount(only.id, "total_assets") == st.amount(only.id, "total_liabilities_and_equity")
    assert st.amount(only.id, "cf_cash_close") == st.amount(only.id, "cash")
