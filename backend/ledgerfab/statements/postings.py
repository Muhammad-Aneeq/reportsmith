"""Operating plan → balanced double-entry journals.

Everything the statements say comes from here. There is no second path: `derive.py`
reads these entries and nothing else, so a figure that appears on the balance sheet
appeared because something posted it.

**Order matters and is not arbitrary.** Trading first, then the flows that settle it,
then capital, then the revolver, then the close. The revolver has to run after every
other cash movement because it exists to react to the balance they leave behind.

**Cash is a single account.** All movement runs through `1000` (current); `1010`
(deposit) holds a fixed treasury balance from the opening balance sheet. Splitting
operating cash across two bank accounts would add realism nothing here reads and one
more way for a balance to go negative.

**Opening retained earnings is the plug.** `BusinessProfile` deliberately has no
`opening_retained_earnings` field: it is computed as whatever makes the opening balance
sheet balance. Hand-setting it is the easiest way to ship an opening position that
does not balance, and every downstream invariant would then fail for a reason that has
nothing to do with the code being tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from ledgerfab.statements.chart import (
    ACCRUALS,
    ACCUM_DEPRECIATION,
    ADMIN_CODES,
    CASH_CURRENT,
    CASH_DEPOSIT,
    COST_OF_SALES,
    DEBT_LONG,
    DEBT_SHORT,
    DEPRECIATION,
    DIVIDENDS,
    INTEREST,
    INVENTORY,
    PAYABLES,
    PAYROLL,
    PPE_COST,
    PREPAYMENTS,
    RECEIVABLES,
    RETAINED_EARNINGS,
    REVENUE,
    SELLING,
    SHARE_CAPITAL,
    TAX_EXPENSE,
    TAX_PAYABLE,
    is_debit_positive,
    is_pnl_account,
)
from ledgerfab.statements.models import JournalEntry, PostingLine
from ledgerfab.statements.money import ZERO, money
from ledgerfab.statements.plan import (
    BusinessProfile,
    PeriodPlan,
    period_depreciation,
    period_interest,
)


@dataclass
class _Books:
    """Running natural balances, plus the entries that produced them."""

    balances: dict[str, Decimal] = field(default_factory=dict)
    entries: list[JournalEntry] = field(default_factory=list)
    _seq: int = 0

    def balance(self, code: str) -> Decimal:
        return self.balances.get(code, ZERO)

    def post(
        self,
        period_id: str,
        when: object,
        memo: str,
        moves: list[tuple[str, Decimal, Decimal]],
        *,
        is_closing: bool = False,
        is_opening: bool = False,
    ) -> None:
        """Record one journal. Zero-value legs are dropped; empty journals are skipped.

        Dropping zero legs matters for readability of the ledger and costs nothing:
        a period with no capex should not carry a £0.00 capex journal that a reader
        has to dismiss.
        """
        lines = tuple(
            PostingLine(code, money(dr), money(cr))
            for code, dr, cr in moves
            if money(dr) != ZERO or money(cr) != ZERO
        )
        if not lines:
            return

        self._seq += 1
        entry = JournalEntry(
            id=f"JE-{self._seq:05d}",
            period_id=period_id,
            date=when,  # type: ignore[arg-type]
            memo=memo,
            lines=lines,
            is_closing=is_closing,
            is_opening=is_opening,
        )
        if not entry.is_balanced:
            raise AssertionError(
                f"{entry.id} ({memo}) does not balance: "
                f"debits {entry.total_debit} vs credits {entry.total_credit}"
            )
        self.entries.append(entry)
        for line in entry.lines:
            self.balances[line.account_code] = money(self.balance(line.account_code) + line.natural)


def build_entries(
    profile: BusinessProfile, plans: tuple[PeriodPlan, ...]
) -> tuple[JournalEntry, ...]:
    """The whole ledger: an opening position, then each period's trading and close."""
    books = _Books()
    _post_opening(books, profile, plans[0])
    for plan in plans:
        _post_period(books, plan)
    return tuple(books.entries)


# ------------------------------------------------------------------- opening --


def _post_opening(books: _Books, profile: BusinessProfile, first: PeriodPlan) -> None:
    """The opening balance sheet, as one journal dated the day before period 1.

    Flagged `is_opening` so `derive.py` can use it to establish period 1's opening
    cash without counting it as a period-1 cash movement.
    """
    debits: list[tuple[str, Decimal]] = [
        (CASH_CURRENT, profile.opening_cash),
        (CASH_DEPOSIT, profile.opening_deposit),
        (RECEIVABLES, profile.opening_receivables),
        (INVENTORY, profile.opening_inventory),
        (PREPAYMENTS, profile.opening_prepayments),
        (PPE_COST, profile.opening_ppe_gross),
    ]
    credits: list[tuple[str, Decimal]] = [
        (ACCUM_DEPRECIATION, profile.opening_accum_depreciation),
        (PAYABLES, profile.opening_payables),
        (ACCRUALS, profile.opening_accruals),
        (TAX_PAYABLE, profile.opening_tax_payable),
        (DEBT_SHORT, profile.opening_debt_short),
        (DEBT_LONG, profile.opening_debt_long),
        (SHARE_CAPITAL, profile.opening_share_capital),
    ]

    # Retained earnings is the plug — see the module docstring.
    total_debits = money(sum((amount for _, amount in debits), ZERO))
    total_credits = money(sum((amount for _, amount in credits), ZERO))
    opening_re = money(total_debits - total_credits)

    moves: list[tuple[str, Decimal, Decimal]] = [(c, a, ZERO) for c, a in debits]
    moves += [(c, ZERO, a) for c, a in credits]
    if opening_re >= ZERO:
        moves.append((RETAINED_EARNINGS, ZERO, opening_re))
    else:
        moves.append((RETAINED_EARNINGS, -opening_re, ZERO))

    books.post(
        first.period.id,
        first.period.start - timedelta(days=1),
        "Opening balance sheet",
        moves,
        is_opening=True,
    )


# -------------------------------------------------------------------- period --


def _post_period(books: _Books, plan: PeriodPlan) -> None:
    pid = plan.period.id
    end = plan.period.end

    opening_receivables = books.balance(RECEIVABLES)
    opening_inventory = books.balance(INVENTORY)
    opening_prepayments = books.balance(PREPAYMENTS)
    opening_payables = books.balance(PAYABLES)
    opening_tax_payable = books.balance(TAX_PAYABLE)

    # -- 1 · trading, on credit ----------------------------------------------
    books.post(
        pid,
        end,
        "Revenue on credit",
        [
            (RECEIVABLES, plan.revenue, ZERO),
            (REVENUE, ZERO, plan.revenue),
        ],
    )

    # -- 2 · purchases and cost of sales -------------------------------------
    # Buy enough to cover what is sold and to move inventory toward its target.
    # Clamped at zero: a target so far below the opening balance that it implies
    # negative purchases is a drawdown, not a refund.
    wanted_inventory = plan.target_inventory()
    purchases = money(max(ZERO, plan.cogs + wanted_inventory - opening_inventory))
    books.post(
        pid,
        end,
        "Purchases on credit",
        [
            (INVENTORY, purchases, ZERO),
            (PAYABLES, ZERO, purchases),
        ],
    )
    # Cost of sales cannot exceed what is on the shelf.
    cogs = money(min(plan.cogs, money(opening_inventory + purchases)))
    books.post(
        pid,
        end,
        "Cost of sales",
        [
            (COST_OF_SALES, cogs, ZERO),
            (INVENTORY, ZERO, cogs),
        ],
    )

    # -- 3 · operating expenses ----------------------------------------------
    # Payroll settles in cash within the period; the rest lands in payables, which
    # is what gives payable days something to act on.
    books.post(
        pid,
        end,
        "Payroll",
        [
            (PAYROLL, plan.payroll, ZERO),
            (CASH_CURRENT, ZERO, plan.payroll),
        ],
    )
    books.post(
        pid,
        end,
        "Selling & marketing on credit",
        [
            (SELLING, plan.selling, ZERO),
            (PAYABLES, ZERO, plan.selling),
        ],
    )
    admin_split = _split(plan.admin, len(ADMIN_CODES))
    books.post(
        pid,
        end,
        "Administrative expenses on credit",
        [(code, amount, ZERO) for code, amount in zip(ADMIN_CODES, admin_split, strict=True)]
        + [(PAYABLES, ZERO, plan.admin)],
    )

    # -- 4 · prepayments -----------------------------------------------------
    prepay_move = money(plan.target_prepayments() - opening_prepayments)
    books.post(
        pid,
        end,
        "Movement in prepayments",
        [
            (PREPAYMENTS, max(ZERO, prepay_move), max(ZERO, -prepay_move)),
            (CASH_CURRENT, max(ZERO, -prepay_move), max(ZERO, prepay_move)),
        ],
    )

    # -- 5 · depreciation and capex ------------------------------------------
    depreciation = period_depreciation(plan, books.balance(PPE_COST))
    books.post(
        pid,
        end,
        "Depreciation",
        [
            (DEPRECIATION, depreciation, ZERO),
            (ACCUM_DEPRECIATION, ZERO, depreciation),
        ],
    )
    books.post(
        pid,
        end,
        "Capital expenditure",
        [
            (PPE_COST, plan.capex, ZERO),
            (CASH_CURRENT, ZERO, plan.capex),
        ],
    )

    # -- 6 · interest --------------------------------------------------------
    debt = money(books.balance(DEBT_SHORT) + books.balance(DEBT_LONG))
    interest = period_interest(plan, debt)
    books.post(
        pid,
        end,
        "Interest on borrowings",
        [
            (INTEREST, interest, ZERO),
            (CASH_CURRENT, ZERO, interest),
        ],
    )

    # -- 7 · settle payables -------------------------------------------------
    credit_purchases = money(purchases + plan.selling + plan.admin)
    wanted_payables = plan.target_payables(credit_purchases)
    payable_pool = money(opening_payables + credit_purchases)
    payments = money(max(ZERO, payable_pool - wanted_payables))
    books.post(
        pid,
        end,
        "Payments to suppliers",
        [
            (PAYABLES, payments, ZERO),
            (CASH_CURRENT, ZERO, payments),
        ],
    )

    # -- 8 · collect receivables ---------------------------------------------
    wanted_receivables = plan.target_receivables()
    receivable_pool = money(opening_receivables + plan.revenue)
    collections = money(max(ZERO, receivable_pool - wanted_receivables))
    books.post(
        pid,
        end,
        "Customer receipts",
        [
            (CASH_CURRENT, collections, ZERO),
            (RECEIVABLES, ZERO, collections),
        ],
    )

    # -- 9 · tax -------------------------------------------------------------
    # Charged on this period's profit, and last period's charge is what gets paid —
    # which is why `tax_payable` is a working-capital line with something in it.
    pretax = money(
        plan.revenue - cogs - plan.payroll - plan.selling - plan.admin - depreciation - interest
    )
    tax = money(max(ZERO, pretax * plan.tax_rate))
    books.post(
        pid,
        end,
        "Tax charge",
        [
            (TAX_EXPENSE, tax, ZERO),
            (TAX_PAYABLE, ZERO, tax),
        ],
    )
    books.post(
        pid,
        end,
        "Tax paid",
        [
            (TAX_PAYABLE, opening_tax_payable, ZERO),
            (CASH_CURRENT, ZERO, opening_tax_payable),
        ],
    )

    # -- 10 · financing ------------------------------------------------------
    repayment = money(min(plan.debt_repaid, books.balance(DEBT_LONG)))
    books.post(
        pid,
        end,
        "Debt repayment",
        [
            (DEBT_LONG, repayment, ZERO),
            (CASH_CURRENT, ZERO, repayment),
        ],
    )
    books.post(
        pid,
        end,
        "Debt drawn",
        [
            (CASH_CURRENT, plan.debt_drawn, ZERO),
            (DEBT_LONG, ZERO, plan.debt_drawn),
        ],
    )
    books.post(
        pid,
        end,
        "Equity issued",
        [
            (CASH_CURRENT, plan.equity_issued, ZERO),
            (SHARE_CAPITAL, ZERO, plan.equity_issued),
        ],
    )

    # -- 11 · dividends ------------------------------------------------------
    # Declared out of this period's profit, and only if there is a profit. A company
    # paying a dividend out of a loss is a different story and not one on offer here.
    net_income = money(pretax - tax)
    dividends = money(max(ZERO, net_income * plan.dividend_payout))
    dividends = money(min(dividends, max(ZERO, books.balance(CASH_CURRENT))))
    books.post(
        pid,
        end,
        "Dividends paid",
        [
            (DIVIDENDS, dividends, ZERO),
            (CASH_CURRENT, ZERO, dividends),
        ],
    )

    # -- 12 · the revolver ---------------------------------------------------
    _revolve(books, plan)

    # -- 13 · close the P&L to retained earnings -----------------------------
    _close_period(books, plan)


def _revolve(books: _Books, plan: PeriodPlan) -> None:
    """Top the current account up to ``min_cash``, or sweep surplus against the facility.

    Runs after every other cash movement, because it reacts to the balance they leave.
    This is also what keeps the `cash` line a non-negative magnitude, as chart.py
    declares: a company that runs out of money borrows, and a borrowing belongs in
    liabilities rather than as a negative asset.
    """
    cash = books.balance(CASH_CURRENT)
    outstanding = books.balance(DEBT_SHORT)

    if cash < plan.min_cash:
        draw = money(plan.min_cash - cash)
        books.post(
            plan.period.id,
            plan.period.end,
            "Revolving facility drawn",
            [
                (CASH_CURRENT, draw, ZERO),
                (DEBT_SHORT, ZERO, draw),
            ],
        )
    elif outstanding > ZERO:
        repay = money(min(outstanding, cash - plan.min_cash))
        books.post(
            plan.period.id,
            plan.period.end,
            "Revolving facility repaid",
            [
                (DEBT_SHORT, repay, ZERO),
                (CASH_CURRENT, ZERO, repay),
            ],
        )


def _close_period(books: _Books, plan: PeriodPlan) -> None:
    """Sweep every P&L account into retained earnings.

    Without this, income and expense balances accumulate forever and
    ``assets = liabilities + equity`` never holds. With it, each period's balance sheet
    closes exactly and retained earnings rolls forward by that period's net income —
    which is one of the four invariants the tests assert.
    """
    moves: list[tuple[str, Decimal, Decimal]] = []
    net_income = ZERO

    for code, balance in sorted(books.balances.items()):
        if not is_pnl_account(code) or balance == ZERO:
            continue
        # `natural` is credit-positive for income and debit-positive for expenses, so
        # income adds to profit and expense subtracts, whatever the sign of either.
        net_income = money(net_income + (balance if not is_debit_positive(code) else -balance))
        if is_debit_positive(code):  # an expense: credit it away
            moves.append((code, ZERO, balance))
        else:  # income: debit it away
            moves.append((code, balance, ZERO))

    if not moves:
        return

    if net_income >= ZERO:
        moves.append((RETAINED_EARNINGS, ZERO, net_income))
    else:
        moves.append((RETAINED_EARNINGS, -net_income, ZERO))

    books.post(
        plan.period.id,
        plan.period.end,
        f"Close {plan.period.label} to retained earnings",
        moves,
        is_closing=True,
    )


def _split(amount: Decimal, parts: int) -> list[Decimal]:
    """Split to cents with the remainder on the first part, so the sum is exact.

    Naive division leaves a stray penny that would unbalance the journal — and a
    one-penny imbalance is the hardest kind of bug to see in a balance sheet.
    """
    each = money(amount / Decimal(parts))
    out = [each] * parts
    out[0] = money(amount - each * Decimal(parts - 1))
    return out
