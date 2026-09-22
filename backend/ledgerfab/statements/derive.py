"""Journal entries → P&L, balance sheet and cash flow.

The reading rules, which are the whole trick:

* **P&L for period *p*** — the period's own entries, *excluding* the closing journal
  and the opening balance sheet. Include the close and every P&L line reads zero.
* **Balance sheet at the end of *p*** — *every* entry up to and including *p*'s close.
  The close is what makes retained earnings accumulate and
  ``assets = liabilities + equity`` hold exactly.
* **Cash flow for *p*** — built by the indirect method from the P&L and the balance
  sheet deltas.

That last one deserves the algebra, because "the cash flow articulates" is a claim
the tests assert to the penny and it should be clear *why* it holds rather than
merely that it does. From ``A = L + E``:

    ΔCash = ΔAP + ΔAccr + ΔTaxPay + ΔSTD + ΔLTD + ΔSC + ΔRE
            − ΔAR − ΔInv − ΔPrepay − ΔPPEnet

Substituting ``ΔRE = NI − dividends`` and ``ΔPPEnet = capex − depreciation``:

    ΔCash = (NI + depreciation − ΔAR − ΔInv − ΔPrepay + ΔAP + ΔAccr + ΔTaxPay)
            + (− capex)
            + (ΔSTD + ΔLTD + ΔSC − dividends)
          =  operating + investing + financing

which is exactly the three sections below. It holds only because every account sits in
precisely one section and nothing is posted outside the chart — so
`test_every_posted_account_maps_to_a_line` is not housekeeping, it is what protects
this identity.
"""

from __future__ import annotations

from decimal import Decimal

from ledgerfab.statements.chart import (
    ACCUM_DEPRECIATION,
    BS,
    CF,
    DEBT_LONG,
    DEBT_SHORT,
    DIVIDENDS,
    LINES_BY_CODE,
    PNL,
    PPE_COST,
    SHARE_CAPITAL,
    StatementLineDef,
    lines_for,
)
from ledgerfab.statements.models import JournalEntry, Line, Period
from ledgerfab.statements.money import ZERO, money

Balances = dict[str, Decimal]


# ---------------------------------------------------------------- balances --


def _accumulate(entries: object) -> Balances:
    balances: Balances = {}
    for entry in entries:  # type: ignore[attr-defined]
        for line in entry.lines:
            balances[line.account_code] = money(
                balances.get(line.account_code, ZERO) + line.natural
            )
    return balances


def period_activity(entries: tuple[JournalEntry, ...], period: Period) -> Balances:
    """This period's movement, excluding the close and the opening position."""
    return _accumulate(
        e for e in entries if e.period_id == period.id and not e.is_closing and not e.is_opening
    )


def balances_at(
    entries: tuple[JournalEntry, ...], periods: tuple[Period, ...], index: int
) -> Balances:
    """Cumulative balances at the end of ``periods[index]``.

    ``index = -1`` means "the opening position only", which is how period 1 learns its
    opening cash without treating the opening journal as a period-1 flow.
    """
    if index < 0:
        return _accumulate(e for e in entries if e.is_opening)
    allowed = {p.id for p in periods[: index + 1]}
    return _accumulate(e for e in entries if e.is_opening or e.period_id in allowed)


def _from_accounts(defn: StatementLineDef, balances: Balances) -> Decimal:
    return money(sum((balances.get(code, ZERO) for code in defn.accounts), ZERO))


def _subtotal(defn: StatementLineDef, resolved: dict[str, Decimal]) -> Decimal:
    assert defn.subtotal_of is not None
    return money(
        sum(
            (
                resolved.get(code, ZERO) * Decimal(coefficient)
                for code, coefficient in defn.subtotal_of
            ),
            ZERO,
        )
    )


def _emit(
    statement: str, period: Period, values: dict[str, Decimal]
) -> tuple[list[Line], dict[str, Decimal]]:
    """Resolve every line of one statement in declaration order.

    Subtotals are computed from their declared components, never hand-coded — the
    declaration order in chart.py guarantees a component is resolved before the
    subtotal that consumes it.
    """
    out: list[Line] = []
    for defn in lines_for(statement):
        if defn.is_subtotal:
            values[defn.code] = _subtotal(defn, values)
        values.setdefault(defn.code, ZERO)
        out.append(
            Line(
                period_id=period.id,
                statement=statement,
                line_code=defn.code,
                label=defn.label,
                amount=values[defn.code],
                is_subtotal=defn.is_subtotal,
            )
        )
    return out, values


# ------------------------------------------------------------------- P&L --


def build_pnl(period: Period, activity: Balances) -> tuple[list[Line], dict[str, Decimal]]:
    values: dict[str, Decimal] = {}
    for defn in lines_for(PNL):
        if defn.accounts:
            values[defn.code] = _from_accounts(defn, activity)
    return _emit(PNL, period, values)


# --------------------------------------------------------- balance sheet --


def build_bs(period: Period, cumulative: Balances) -> tuple[list[Line], dict[str, Decimal]]:
    values: dict[str, Decimal] = {}
    for defn in lines_for(BS):
        if defn.accounts:
            values[defn.code] = _from_accounts(defn, cumulative)
    return _emit(BS, period, values)


# ------------------------------------------------------------- cash flow --


def build_cf(
    period: Period,
    pnl: dict[str, Decimal],
    opening: Balances,
    closing: Balances,
    period_entries: tuple[JournalEntry, ...],
) -> tuple[list[Line], dict[str, Decimal]]:
    """Indirect-method cash flow. Every value signed inflow-positive."""

    def delta(code: str) -> Decimal:
        return money(closing.get(code, ZERO) - opening.get(code, ZERO))

    def bs_delta(line_code: str) -> Decimal:
        return money(sum((delta(code) for code in LINES_BY_CODE[line_code].accounts), ZERO))

    values: dict[str, Decimal] = {
        "cf_net_income": pnl["net_income"],
        "cf_depreciation": delta(ACCUM_DEPRECIATION),
        # An asset going up consumes cash; a liability going up releases it.
        "cf_change_receivables": money(-bs_delta("accounts_receivable")),
        "cf_change_inventory": money(-bs_delta("inventory")),
        "cf_change_prepayments": money(-bs_delta("prepayments")),
        "cf_change_payables": bs_delta("accounts_payable"),
        "cf_change_accruals": bs_delta("accruals"),
        "cf_change_tax_payable": bs_delta("tax_payable"),
        # PPE is carried at cost and never disposed of here, so the gross movement is
        # capex exactly. Read from the balance sheet rather than from the plan, so
        # that what the statement reports is what the books actually did.
        "cf_capex": money(-delta(PPE_COST)),
        "cf_equity_issued": delta(SHARE_CAPITAL),
        # Dividends: `3200` is contra-equity, so its natural (credit-positive) balance
        # moves negative as dividends are declared — already the outflow sign the cash
        # flow statement wants.
        "cf_dividends_paid": delta(DIVIDENDS),
    }

    # Debt is split into drawn and repaid from the postings rather than netted, because
    # "drew £2m and repaid £1.9m" and "drew £100k" are different stories and a reader
    # of a financing section is entitled to both.
    drawn, repaid = ZERO, ZERO
    for entry in period_entries:
        if entry.is_opening or entry.is_closing:
            continue
        for line in entry.lines:
            if line.account_code not in (DEBT_SHORT, DEBT_LONG):
                continue
            drawn = money(drawn + line.credit)
            repaid = money(repaid + line.debit)
    values["cf_debt_drawn"] = drawn
    values["cf_debt_repaid"] = money(-repaid)

    values["cf_cash_open"] = money(
        sum((opening.get(c, ZERO) for c in LINES_BY_CODE["cash"].accounts), ZERO)
    )
    return _emit(CF, period, values)


# ----------------------------------------------------------------- driver --


def build_lines(entries: tuple[JournalEntry, ...], periods: tuple[Period, ...]) -> tuple[Line, ...]:
    """Every line of every statement for every period."""
    lines: list[Line] = []
    for period in periods:
        opening = balances_at(entries, periods, period.index - 1)
        closing = balances_at(entries, periods, period.index)
        activity = period_activity(entries, period)

        pnl_lines, pnl_values = build_pnl(period, activity)
        bs_lines, _ = build_bs(period, closing)
        period_entries = tuple(e for e in entries if e.period_id == period.id)
        cf_lines, _ = build_cf(period, pnl_values, opening, closing, period_entries)

        lines.extend(pnl_lines)
        lines.extend(bs_lines)
        lines.extend(cf_lines)
    return tuple(lines)
