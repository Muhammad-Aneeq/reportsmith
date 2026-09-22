"""The typed frame every adapter returns.

Deliberately not pandas. A pack's frames are tens of rows, and what matters about them
is that money stays ``Decimal`` and ordering stays total — two things pandas makes
harder, not easier (it will happily coerce a Decimal column to float64 the first time
you aggregate it, which is precisely the bug the numeric-fidelity gate exists to catch).

A ``Frame`` is columns, rows of plain values, and a note about where it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

Value = str | int | Decimal | bool | None


@dataclass(frozen=True, slots=True)
class Frame:
    """Rows of named values, plus the provenance a reader needs to trust them."""

    columns: tuple[str, ...]
    rows: tuple[dict[str, Value], ...]
    source: str = ""
    dataset: str = ""
    schema_version: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def is_empty(self) -> bool:
        return not self.rows

    def column(self, name: str) -> list[Value]:
        return [row.get(name) for row in self.rows]

    def require(self, *names: str) -> None:
        """Fail loudly when a template asks for a field the dataset does not publish.

        The caller turns this into a *gap* naming the missing field, so a template typo
        produces "column 'amunt' not in [amount, …]" in the gaps panel rather than a
        column of blanks that looks like real missing data.
        """
        missing = [n for n in names if n not in self.columns]
        if missing:
            raise KeyError(
                f"{self.dataset or 'dataset'} has no column(s) {missing}; "
                f"available: {list(self.columns)}"
            )

    def to_json(self) -> dict[str, Any]:
        """Canonical plain-data form. Decimals become strings, never floats.

        A Decimal serialised through float is how a verified figure quietly becomes an
        unverifiable one, at the exact step whose job is proving the data did not change.
        """
        return {
            "columns": list(self.columns),
            "rows": [
                {k: (str(v) if isinstance(v, Decimal) else v) for k, v in row.items()}
                for row in self.rows
            ],
            "source": self.source,
            "dataset": self.dataset,
            "schema_version": self.schema_version,
            "meta": self.meta,
        }


def frame_from_dicts(
    rows: list[dict[str, Value]],
    *,
    columns: tuple[str, ...] | None = None,
    source: str = "",
    dataset: str = "",
    schema_version: str = "",
    meta: dict[str, Any] | None = None,
) -> Frame:
    """Build a frame, deriving the column order from the first row if not given.

    Column order is taken from the first row rather than from a set union, because a
    set has no order and the pack's tables would reshuffle between runs — a golden-file
    failure with no underlying data change.
    """
    if columns is None:
        columns = tuple(rows[0].keys()) if rows else ()
    return Frame(
        columns=columns,
        rows=tuple(rows),
        source=source,
        dataset=dataset,
        schema_version=schema_version,
        meta=meta or {},
    )
