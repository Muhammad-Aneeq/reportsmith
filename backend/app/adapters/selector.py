"""The closed selector grammar: where · group_by · aggregate · order_by · limit.

No expressions. No `eval`. No user-supplied callables. A template is user input, and an
expression language in user input is a remote-code-execution hole wearing a YAML hat
(PLAN.md **D-008**).

The other reason is determinism. Everything here is a pure function of (frame, selector),
and every ordering is *total* — the sort key always ends with a tiebreak, so two rows
holding the same value cannot swap places between runs. Without that, a golden file
fails on a day nothing changed, somebody adds `--force-regenerate` to the Makefile, and
the determinism guarantee quietly stops being one.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.adapters.frame import Frame, Value
from app.template.schema import AggFn, Condition, Selector


class SelectorError(ValueError):
    """The selector asked for something this frame cannot do. Becomes a gap."""


def _compare(left: Value, op: str, right: Any) -> bool:
    # Every comparison here is genuinely dynamic — `Value` is a union whose members are not
    # mutually comparable — so the results are coerced with bool() rather than annotated
    # away. A TypeError below is a real data problem and becomes a named gap.
    if op == "eq":
        return bool(left == right)
    if op == "ne":
        return bool(left != right)
    if op == "in":
        return bool(left in right)
    if op == "not_in":
        return bool(left not in right)

    # Ordered comparisons on None are a category error, not False: a row with no value
    # is not "less than 10", it is unknown. Excluding it is the honest reading.
    if left is None:
        return False
    try:
        if op == "gt":
            return bool(left > right)
        if op == "gte":
            return bool(left >= right)
        if op == "lt":
            return bool(left < right)
        if op == "lte":
            return bool(left <= right)
    except TypeError as exc:
        raise SelectorError(
            f"cannot compare {type(left).__name__} with {type(right).__name__} using {op!r}"
        ) from exc
    raise SelectorError(f"unknown operator {op!r}")


def _apply_where(frame: Frame, conditions: list[Condition]) -> Frame:
    if not conditions:
        return frame
    for cond in conditions:
        if cond.field not in frame.columns:
            raise SelectorError(
                f"where references unknown field {cond.field!r}; available: {list(frame.columns)}"
            )
    rows = tuple(
        row
        for row in frame.rows
        if all(_compare(row.get(c.field), c.op, c.value) for c in conditions)
    )
    return Frame(
        columns=frame.columns,
        rows=rows,
        source=frame.source,
        dataset=frame.dataset,
        schema_version=frame.schema_version,
        meta=frame.meta,
    )


def _aggregate(values: list[Value], fn: AggFn) -> Value:
    """Aggregate, skipping Nones.

    Skipping rather than treating them as zero: the sum of three known amounts and one
    unknown is the sum of three amounts, not a figure that pretends the fourth was nil.
    ``count`` deliberately counts *present* values for the same reason; use a column
    that is never null if you want a row count.
    """
    present = [v for v in values if v is not None]
    if fn == "count":
        return len(present)
    if fn == "count_distinct":
        return len({str(v) for v in present})
    if not present:
        return None
    if fn in ("min", "max"):
        # Comparable only within one type. Mixed types in a column are a data problem,
        # and raising here surfaces it as a named gap rather than an arbitrary winner.
        try:
            return min(present) if fn == "min" else max(present)
        except TypeError as exc:
            raise SelectorError(f"cannot {fn} a column of mixed types") from exc

    numbers: list[Decimal] = []
    for v in present:
        if isinstance(v, Decimal):
            numbers.append(v)
        elif isinstance(v, bool):
            numbers.append(Decimal(int(v)))
        elif isinstance(v, int):
            numbers.append(Decimal(v))
        else:
            raise SelectorError(f"cannot {fn} a non-numeric value {v!r}")
    total = sum(numbers, Decimal(0))
    if fn == "sum":
        return total
    if fn == "mean":
        return total / Decimal(len(numbers))
    raise SelectorError(f"unknown aggregate {fn!r}")


def _apply_group(frame: Frame, selector: Selector) -> Frame:
    keys = selector.group_by
    for key in keys:
        if key not in frame.columns:
            raise SelectorError(
                f"group_by references unknown field {key!r}; available: {list(frame.columns)}"
            )
    for field_name in selector.aggregate:
        if field_name not in frame.columns:
            raise SelectorError(
                f"aggregate references unknown field {field_name!r}; "
                f"available: {list(frame.columns)}"
            )

    # dict preserves insertion order, so groups come out in first-seen order — a stable,
    # explainable default before order_by is applied.
    groups: dict[tuple[Value, ...], list[dict[str, Value]]] = {}
    for row in frame.rows:
        groups.setdefault(tuple(row.get(k) for k in keys), []).append(row)

    out: list[dict[str, Value]] = []
    for key_values, members in groups.items():
        grouped: dict[str, Value] = dict(zip(keys, key_values, strict=True))
        for field_name, fn in selector.aggregate.items():
            grouped[field_name] = _aggregate([m.get(field_name) for m in members], fn)
        out.append(grouped)

    columns = tuple(keys) + tuple(selector.aggregate)
    return Frame(
        columns=columns,
        rows=tuple(out),
        source=frame.source,
        dataset=frame.dataset,
        schema_version=frame.schema_version,
        meta=frame.meta,
    )


def _sort_key(
    row: dict[str, Value], fields: list[str], tiebreak: tuple[str, ...]
) -> tuple[Any, ...]:
    """A total, type-stable sort key.

    Python refuses to order ``None`` against a number, and refuses to order a string
    against a Decimal. Both happen in real data, so every value is mapped to a
    ``(type_rank, comparable)`` pair: Nones sort last regardless of direction, and mixed
    types group rather than raise.
    """
    key: list[Any] = []
    for spec in fields:
        descending = spec.startswith("-")
        name = spec[1:] if descending else spec
        value = row.get(name)
        if value is None:
            # 1 sorts after 0 ascending; negating below would flip that, so Nones are
            # pinned last in both directions by never negating their rank.
            key.append((1, 0))
            continue
        comparable: Any
        if isinstance(value, bool):
            comparable = Decimal(int(value))
        elif isinstance(value, Decimal | int):
            comparable = Decimal(value)
        else:
            comparable = str(value)
        if descending:
            comparable = -comparable if isinstance(comparable, Decimal) else _invert_str(comparable)
        key.append((0, comparable))
    key.extend(str(row.get(t, "")) for t in tiebreak)
    return tuple(key)


class _InvertedStr:
    """Descending order for strings, without reversing the whole list.

    Reversing the list after an ascending sort would also reverse the tiebreak, which
    is exactly what the tiebreak exists to prevent.
    """

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __lt__(self, other: _InvertedStr) -> bool:
        return self.value > other.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _InvertedStr) and self.value == other.value


def _invert_str(value: Any) -> Any:
    return _InvertedStr(value) if isinstance(value, str) else value


def _apply_order(frame: Frame, selector: Selector) -> Frame:
    if not selector.order_by:
        return frame
    for spec in selector.order_by:
        name = spec[1:] if spec.startswith("-") else spec
        if name not in frame.columns:
            raise SelectorError(
                f"order_by references unknown field {name!r}; available: {list(frame.columns)}"
            )
    # The tiebreak is what makes the order total. Group keys first if we grouped,
    # otherwise every column — either way, two rows can only tie if they are identical.
    tiebreak = tuple(selector.group_by) if selector.group_by else frame.columns
    rows = tuple(sorted(frame.rows, key=lambda r: _sort_key(r, selector.order_by, tiebreak)))
    return Frame(
        columns=frame.columns,
        rows=rows,
        source=frame.source,
        dataset=frame.dataset,
        schema_version=frame.schema_version,
        meta=frame.meta,
    )


def apply_selector(frame: Frame, selector: Selector) -> Frame:
    """where → group_by/aggregate → order_by → limit. In that order, always.

    The order is fixed and not configurable: filtering after aggregating would mean
    "top 10 by spend" silently became "top 10 of whatever survived", and a template
    author would have no way to see which they got.
    """
    out = _apply_where(frame, selector.where)
    if selector.group_by:
        out = _apply_group(out, selector)
    out = _apply_order(out, selector)
    if selector.limit is not None and len(out.rows) > selector.limit:
        out = Frame(
            columns=out.columns,
            rows=out.rows[: selector.limit],
            source=out.source,
            dataset=out.dataset,
            schema_version=out.schema_version,
            # The pack must be able to say "top 10 of 47" rather than implying 10 is all
            # there was. A silently truncated table is a lie of omission.
            meta={**out.meta, "truncated_from": len(out.rows)},
        )
    return out
