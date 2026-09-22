"""The matcher. No tolerance parameter — the precision comes from the text.

A token matches a ref when **both** hold:

1. the units agree, and
2. the ref's value, rounded to the token's own declared precision, equals the token's
   value exactly.

Exact `Decimal` comparison after rounding, never `abs(a - b) < epsilon`. An epsilon is a
knob, a knob gets widened the first time a build goes red at 5pm, and a widened knob means
the gate no longer measures what it claims to.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from numcheck.models import FigureRef, NumericToken

# Units that may satisfy one another. `bare` is the only flexible one, because prose
# legitimately drops the symbol on a repeat mention ("revenue of £3.8m … the 3.8m was").
# money↔percent is deliberately absent: that conflation is the hole worth keeping shut.
_COMPATIBLE: dict[str, frozenset[str]] = {
    "bare": frozenset({"bare", "money", "percent", "count", "days", "times"}),
    "money": frozenset({"money", "bare"}),
    "percent": frozenset({"percent", "bare"}),
    "count": frozenset({"count", "bare"}),
    "days": frozenset({"days", "bare", "count"}),
    "times": frozenset({"times", "bare"}),
}


def units_agree(token_unit: str, ref_unit: str) -> bool:
    return ref_unit in _COMPATIBLE.get(token_unit, frozenset({token_unit}))


def round_to(value: Decimal, places: int) -> Decimal:
    exp = Decimal(1).scaleb(-places)
    return value.quantize(exp, rounding=ROUND_HALF_UP)


def matches(token: NumericToken, ref: FigureRef) -> bool:
    """Does this token legitimately state this ref?

    The scale-aware comparison is what lets "£3.8m" match a ref of 3,815,070.61: the
    token's precision of 1 is interpreted *at its own scale*, so the ref is rounded to
    the nearest 0.1m rather than the nearest 0.1.
    """
    if not units_agree(token.unit, ref.unit):
        return False

    if token.scale != 1:
        scaled_ref = ref.value / Decimal(token.scale)
        scaled_token = token.value / Decimal(token.scale)
        return round_to(scaled_ref, token.precision) == round_to(scaled_token, token.precision)

    return round_to(ref.value, token.precision) == round_to(token.value, token.precision)


def find_match(token: NumericToken, refs: list[FigureRef]) -> FigureRef | None:
    """The first ref this token satisfies.

    First, not best: the question is whether the number is *supportable*, not which
    figure the author had in mind. If two refs both round to what was written, the
    sentence is true either way.
    """
    return next((ref for ref in refs if matches(token, ref)), None)
