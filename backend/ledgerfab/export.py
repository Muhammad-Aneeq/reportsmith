"""World → CSV, in the shape a bookkeeper would actually receive.

``date_format_chaos`` is applied here rather than during generation: the internal
world keeps real ``date`` objects, and only the exported files carry the mixed
DD/MM/YYYY, MM-DD-YY and "15 Jan 2025" formats that make CSV intake hard. That
split keeps the world comparable while still exercising the parser.

Ambiguity is the point. "03/04/2025" is 3 April to a British system and 4 March to
an American one; the intake validator is expected to flag that rather than guess.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from ledgerfab.messiness import format_date
from ledgerfab.models import World
from ledgerfab.rng import Rng


def _fmt_date(day: date, rng: Rng, chaos: float) -> str:
    """Document dates are re-rendered here; transaction dates are not.

    A transaction already carries ``date_raw`` from the presentation pass, and the
    CSV must show that same string — otherwise the shipped files and the session
    DB would disagree about what the bank sent.
    """
    raw, _label = format_date(day, rng, chaos)
    return raw


def _write(path: Path, header: list[str], rows: list[list[object]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" per csv module contract; utf-8 so counterparty names survive.
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return len(rows)


def export_world(world: World, out_dir: str | Path, chaos: float | None = None) -> dict[str, int]:
    """Write transactions/invoices/notes CSVs. Returns {filename: row_count}.

    The CSVs are a convenience for humans and for sibling projects that ingest
    files; LedgerLab itself serves the same world over MCP from a session DB.

    ``transactions.csv`` holds only the *exceptions* — the residue an upstream
    matcher could not clear. ``prior_transactions.csv`` holds the settled ones as
    **context only**: a duplicate-payment finding is groundable solely by citing
    the earlier payment, so without that file ``duplicate`` is structurally
    unprovable from the CSVs alone.
    """
    out = Path(out_dir)
    rng = Rng(world.seed, "export")
    if chaos is None:
        from ledgerfab.profiles import get_profile

        chaos = get_profile(world.profile_name).date_format_chaos

    cp_by_id = {c.id: c for c in world.counterparties}

    def _txn_row(t) -> list[object]:  # type: ignore[no-untyped-def]
        return [
            t.id,
            t.date_raw or t.date.isoformat(),
            f"{t.amount:.2f}",
            t.currency,
            t.counterparty_raw,
            t.reference or "",
            t.description,
            t.direction,
            t.bank_account_code,
        ]

    exception_ids = world.ground_truth.exception_txn_ids
    txn_rows = [_txn_row(t) for t in world.exception_transactions]
    prior_rows = [_txn_row(t) for t in world.transactions if t.id not in exception_ids]

    inv_rows: list[list[object]] = [
        [
            i.id,
            i.number,
            cp_by_id[i.counterparty_id].canonical_name,
            i.po_number or "",
            _fmt_date(i.issue_date, rng, chaos),
            _fmt_date(i.due_date, rng, chaos),
            f"{i.amount:.2f}",
            i.currency,
            str(i.status),
        ]
        for i in world.invoices
    ]

    note_rows: list[list[object]] = [
        [
            n.id,
            cp_by_id[n.counterparty_id].canonical_name,
            _fmt_date(n.date, rng, chaos),
            n.author,
            n.text,
        ]
        for n in world.notes
    ]

    txn_header = [
        "txn_id",
        "date",
        "amount",
        "currency",
        "counterparty",
        "reference",
        "description",
        "direction",
        "bank_account",
    ]

    return {
        "transactions.csv": _write(out / "transactions.csv", txn_header, txn_rows),
        "prior_transactions.csv": _write(out / "prior_transactions.csv", txn_header, prior_rows),
        "invoices.csv": _write(
            out / "invoices.csv",
            [
                "invoice_id",
                "invoice_number",
                "counterparty",
                "po_number",
                "issue_date",
                "due_date",
                "amount",
                "currency",
                "status",
            ],
            inv_rows,
        ),
        "notes.csv": _write(
            out / "notes.csv",
            ["note_id", "counterparty", "date", "author", "text"],
            note_rows,
        ),
    }
