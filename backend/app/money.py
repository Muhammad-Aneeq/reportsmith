"""The one rounding rule.

Every figure that reaches a pack passes through here. The vendored statement emitter
already hands out ``Decimal``; raw ledgerfab hands out ``float`` and SpendSort's CSV
hands out formatted strings, so those two are the only places a conversion happens
(PLAN.md **D-010**).

Why one module for six lines of arithmetic: a pack's headline claim is that every
number in its prose matches a number in its data. That claim dies quietly if two call
sites round differently — the narrative says £1,234 and the table says £1,235, both
"correct", and the cross-check fails for a reason that has nothing to do with the model.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTS = Decimal("0.01")


def to_money(value: object) -> Decimal:
    """Coerce anything a source hands us into a cent-quantised ``Decimal``.

    Floats go via ``str`` deliberately: ``Decimal(0.1)`` is
    ``0.1000000000000000055511151231257827``, while ``Decimal(str(0.1))`` is ``0.1``.
    The first is what the float really holds; the second is what the source meant, and
    sources here are money.
    """
    if isinstance(value, Decimal):
        return value.quantize(CENTS, rounding=ROUND_HALF_UP)
    if isinstance(value, int):
        return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)
    if isinstance(value, float):
        return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace(" ", "")
        if not cleaned:
            raise ValueError("empty string is not an amount")
        try:
            return Decimal(cleaned).quantize(CENTS, rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise ValueError(f"not an amount: {value!r}") from exc
    raise TypeError(f"cannot read {type(value).__name__} as money")


def quantize(value: Decimal, places: int) -> Decimal:
    """Round to ``places`` decimals, half-up.

    Half-up, not banker's rounding, because this is presentation for a human reader:
    a controller who checks 2.5 → 3 by hand and finds 2 will not trust the rest of the
    document, and being statistically unbiased is not what the document is for.
    """
    if places < 0:
        raise ValueError("places must be >= 0")
    exp = Decimal(1).scaleb(-places)
    return value.quantize(exp, rounding=ROUND_HALF_UP)


def pct_change(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    """Period-over-period change, or ``None`` when it does not exist.

    ``None`` rather than zero in three distinct cases — no prior period, a missing
    figure, and a zero base. A 0% move and "there is nothing to compare against" are
    different facts, and a pack that renders them identically is lying about one of
    them. The assembler turns each ``None`` into a visible "n/a", never a dash that
    reads like zero.
    """
    if current is None or prior is None or prior == 0:
        return None
    return quantize((current - prior) / abs(prior) * Decimal(100), 4)
