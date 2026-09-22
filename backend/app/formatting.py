"""How a figure is rendered, given a pack's style rules.

One module, used by the tables, the KPI grid, the narrative prompt and the tone linter.
That is the point: if the table renders £81,006 and the prompt tells the model the figure
is 81005.57, the model writes the second, the linter "fixes" it to the first, and the
cross-check then has to decide whether those are the same number. They are — but only if
exactly one piece of code decides how a Decimal becomes text.

So formatting is defined here and nowhere else, and the narrative is given its figures
**pre-formatted**, so the model is copying a string rather than rounding one.
"""

from __future__ import annotations

from decimal import Decimal

from app.money import quantize
from app.template.schema import PackStyle


def format_money(value: Decimal | None, style: PackStyle) -> str:
    """Currency, per the pack's style rules. `None` is "n/a", never 0."""
    if value is None:
        return "n/a"
    places = style.rounding.money
    rounded = quantize(value, places)
    negative = rounded < 0
    digits = f"{abs(rounded):,.{places}f}"
    if style.currency.thousands != ",":
        digits = digits.replace(",", style.currency.thousands)

    body = (
        f"{style.currency.symbol}{digits}"
        if style.currency.position == "prefix"
        else f"{digits}{style.currency.symbol}"
    )
    if not negative:
        return body
    # Parentheses are the accounting convention and the default. A minus sign in front of
    # a currency symbol ("-£1,234") is what a spreadsheet does, not what a pack does.
    return f"({body})" if style.currency.negative == "parens" else f"-{body}"


def format_percent(value: Decimal | None, style: PackStyle) -> str:
    if value is None:
        return "n/a"
    return f"{quantize(value, style.rounding.percent)}%"


def format_ratio(value: Decimal | None, style: PackStyle) -> str:
    if value is None:
        return "n/a"
    return str(quantize(value, style.rounding.ratio))


def format_integer(value: Decimal | int | None, _style: PackStyle) -> str:
    if value is None:
        return "n/a"
    return f"{int(value):,}"


def format_days(value: Decimal | None, style: PackStyle) -> str:
    if value is None:
        return "n/a"
    return f"{quantize(value, style.rounding.percent)} days"


def format_value(value: object, fmt: str, style: PackStyle) -> str:
    """Dispatch on the template's declared format for a column or KPI."""
    if fmt == "money":
        return format_money(value if isinstance(value, Decimal) else None, style)
    if fmt == "percent":
        return format_percent(value if isinstance(value, Decimal) else None, style)
    if fmt == "ratio":
        return format_ratio(value if isinstance(value, Decimal) else None, style)
    if fmt == "days":
        return format_days(value if isinstance(value, Decimal) else None, style)
    if fmt == "integer":
        if isinstance(value, Decimal | int) and not isinstance(value, bool):
            return format_integer(value, style)
        return "n/a"
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def format_delta(value: Decimal | None, style: PackStyle) -> str:
    """A movement, signed explicitly.

    The leading `+` is deliberate. In a column of changes, an unsigned `2.9%` reads as a
    level rather than a movement, and the reader has to look at the header to tell.
    """
    if value is None:
        return "n/a"
    rounded = quantize(value, style.rounding.percent)
    sign = "+" if rounded > 0 else ""
    return f"{sign}{rounded}%"
