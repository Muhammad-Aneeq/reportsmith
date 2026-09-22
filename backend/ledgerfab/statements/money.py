"""The single rounding rule for the statement emitter.

The vendored engine holds money as ``float`` and rounds to cents at the edges, which
is fine for its purpose: nothing there sums a thousand rows and then asserts the total
to the penny.

This extension does exactly that. Its correctness claim is that the balance sheet
balances and the cash flow articulates **to the cent**, per period, for every profile
and every seed. Float dust would make that claim flaky for reasons that have nothing
to do with the accounting — a test failing at 1e-11 teaches nobody anything. So money
here is ``Decimal``, quantised to cents at every boundary, and the invariant tests can
assert exact equality rather than a tolerance.

``ROUND_HALF_UP`` rather than Python's banker's rounding, because that is what
accounting convention expects and what a reader checking a figure by hand will do.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, localcontext

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: Decimal | int | str) -> Decimal:
    """Quantise to cents, half-up. The only way an amount enters the emitter."""
    with localcontext() as ctx:
        ctx.prec = 28
        return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def pct(value: Decimal | int | str) -> Decimal:
    """A rate — a growth rate, a margin, a tax rate. Not money, so not quantised to
    cents: quantising 0.315 to 0.32 would be a 1.6% error in a gross margin."""
    return Decimal(value)


def share(amount: Decimal, rate: Decimal) -> Decimal:
    """``amount × rate``, back to cents. The most common arithmetic in the emitter."""
    return money(amount * rate)


def prorate(annual_rate: Decimal, days: int, year_days: int = 365) -> Decimal:
    """An annual rate applied over a period of ``days``.

    Kept explicit and shared because getting it wrong is invisible: an interest rate
    or a depreciation rate silently applied per-period rather than pro-rata makes a
    quarterly model produce four years of expense in one year, and every downstream
    ratio would still look plausible.
    """
    return pct(annual_rate) * Decimal(days) / Decimal(year_days)


def total(amounts: object) -> Decimal:
    """Sum to cents. ``sum()`` on an empty iterable returns ``int`` 0, which then
    fails a ``Decimal`` comparison in a way that reads like a data problem."""
    acc = ZERO
    for a in amounts:  # type: ignore[attr-defined]
        acc += a
    return money(acc)
