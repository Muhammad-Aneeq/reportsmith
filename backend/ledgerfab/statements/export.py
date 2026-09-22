"""A statement set, in the shape the intake template accepts.

One format for both doors. A set generated here exports to exactly the layout P3's
CSV/XLSX template defines, so `generate → export → upload → parse` round-trips to an
identical set. That is not a convenience: it means the upload path is exercised by
every generated fixture, rather than only by whatever hand-made file someone remembered
to write.

Layout — one row per line, one column per period, which is how a human reads a set of
comparatives and therefore how a human will hand you one:

    statement,line_code,label,2024-Q1,2024-Q2,…
    pnl,revenue,Revenue,3532774.00,3623760.00,…

Amounts are plain fixed 2-dp strings: no thousands separators, no currency symbol, no
parenthesised negatives. The messy variants are a *parsing* problem and P3's parser
owns them; emitting them here would mean the round-trip test silently depended on the
parser's leniency instead of on the two formats agreeing.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from ledgerfab.statements.chart import LINE_ORDER
from ledgerfab.statements.models import StatementSet

HEADER_PREFIX: tuple[str, ...] = ("statement", "line_code", "label")


def to_rows(statement_set: StatementSet) -> list[list[str]]:
    """Header row plus one row per line, in statement declaration order."""
    period_ids = list(statement_set.period_ids)
    rows: list[list[str]] = [[*HEADER_PREFIX, *period_ids]]

    seen: dict[tuple[str, str], str] = {}
    for line in statement_set.lines:
        seen[(line.statement, line.line_code)] = line.label

    for (statement, line_code), label in sorted(
        seen.items(), key=lambda item: LINE_ORDER[item[0][1]]
    ):
        amounts = [f"{statement_set.amount(pid, line_code) or 0:.2f}" for pid in period_ids]
        rows.append([statement, line_code, label, *amounts])
    return rows


def to_csv(statement_set: StatementSet) -> str:
    """CSV text. ``newline=""`` and an explicit ``\\n`` so the bytes are the same on
    every platform — otherwise a Windows checkout and a Linux CI runner would produce
    different file hashes for identical data."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(to_rows(statement_set))
    return buffer.getvalue()


def to_xlsx(statement_set: StatementSet) -> bytes:
    """The same grid as an .xlsx workbook.

    `openpyxl` is imported lazily: the emitter's core has no third-party dependency
    beyond the standard library, and a project reusing it for CSV alone should not be
    forced to install a spreadsheet library (BLOCKERS.md — openpyxl degradation).
    """
    from openpyxl import Workbook

    workbook = Workbook()
    sheet: Any = workbook.active
    sheet.title = "statements"
    rows = to_rows(statement_set)
    sheet.append(rows[0])
    for row in rows[1:]:
        # Amounts as floats so the cells are numeric in the workbook. This is a
        # *presentation* boundary, not the money path: the CSV form stays the
        # authoritative one and the round-trip test runs through it.
        sheet.append([*row[:3], *(float(value) for value in row[3:])])

    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()
