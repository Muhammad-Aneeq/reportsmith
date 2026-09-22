"""Find every number in prose, with its span, its unit and its declared precision.

The hard part is not finding numbers. It is *not* finding things that look like numbers
and are not claims about the data: a year, a section number, an ordinal, a quarter label.
Each false positive is a sentence the composer loses for no reason; each false negative is
an unverified figure surviving into a signed document. The second is worse, so the rule is
to tokenise anything that could be a figure and let the **exemption list** — closed, and
two entries long — remove the handful that provably are not.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from numcheck.models import NumericToken, Unit

CURRENCY_SYMBOLS = "£$€¥"

_SCALES: dict[str, int] = {"k": 1_000, "m": 1_000_000, "bn": 1_000_000_000, "b": 1_000_000_000}

# One pattern, because overlapping patterns produce overlapping spans and surgery needs
# spans to be unambiguous. Groups:
#   open_paren  currency  digits  scale  percent  times  days  close_paren
_NUMBER = re.compile(
    r"""
    (?P<open>\()?                                # accounting negative
    (?P<sign>-|−)?                               # ASCII hyphen or real minus
    # The optional space belongs to the currency symbol ("£ 1,234"), not to the number.
    # Left floating outside the group it is absorbed into every token's span, shifting
    # `start` one character left - which silently breaks every span-based check
    # downstream, including the period exemption and sentence surgery.
    (?:(?P<currency>["""
    + CURRENCY_SYMBOLS
    + r"""])\s?)?
    (?P<digits>\d{1,3}(?:[, ]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    (?P<scale>bn|[kmb])?\b
    (?P<percent>\s?%)?
    (?P<times>\s?[x×])?
    (?P<days>\s?days?)?
    (?P<close>\))?
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _unit_of(match: re.Match[str]) -> Unit:
    if match.group("percent"):
        return "percent"
    if match.group("currency"):
        return "money"
    if match.group("times"):
        return "times"
    if match.group("days"):
        return "days"
    return "bare"


def _precision_of(digits: str) -> int:
    """Decimal places the author wrote. `3.8` → 1; `3,815,070.61` → 2; `4` → 0."""
    return len(digits.split(".")[1]) if "." in digits else 0


def tokenize(text: str) -> list[NumericToken]:
    """Every numeric token in the text, in order of appearance.

    Scale suffixes multiply the value but leave `precision` as written: "£3.8m" is the
    claim "3.8 million to one decimal place", i.e. anything from £3.75m to £3.85m. That
    is how a human reads it and how the matcher must treat it, or every rounded figure in
    readable prose would be scored as a fabrication.
    """
    tokens: list[NumericToken] = []
    for match in _NUMBER.finditer(text):
        digits = match.group("digits").replace(",", "").replace(" ", "")
        try:
            magnitude = Decimal(digits)
        except InvalidOperation:  # pragma: no cover — the pattern cannot produce this
            continue

        scale_key = (match.group("scale") or "").lower()
        scale = _SCALES.get(scale_key, 1)
        value = magnitude * scale

        negative = bool(match.group("sign")) or (
            bool(match.group("open")) and bool(match.group("close"))
        )
        if negative:
            value = -value

        tokens.append(
            NumericToken(
                text=match.group(0),
                start=match.start(),
                end=match.end(),
                value=value,
                unit=_unit_of(match),
                precision=_precision_of(match.group("digits")),
                scale=scale,
            )
        )
    return tokens
