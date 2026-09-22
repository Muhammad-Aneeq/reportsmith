"""Ground-truth emitter (spec 00 A3): for every generated world, the correct answers.

This is the answer key the eval suite grades against, so it is validated hard at
build time. A silently-wrong label is worse than a crash: it would make the eval
numbers meaningless while every test stayed green, so every invariant below
raises rather than warns.
"""

from __future__ import annotations

from ledgerfab.generators.transactions import PendingException, SettlementResult
from ledgerfab.models import (
    BankTransaction,
    CounterpartyNote,
    ExceptionTruth,
    GLEntry,
    GroundTruth,
    Invoice,
)


class GroundTruthError(RuntimeError):
    """The generated world contradicts its own answer key."""


def _attach_dispute_notes(pending: list[PendingException], note_by_invoice: dict[str, str]) -> None:
    """Dispute labels are only defensible if they cite the note that proves them."""
    for exc in pending:
        for invoice_id in exc.related_invoice_ids:
            note_id = note_by_invoice.get(invoice_id)
            if note_id and note_id not in exc.related_note_ids:
                exc.related_note_ids.append(note_id)


def build_ground_truth(
    settlement: SettlementResult,
    invoices: list[Invoice],
    notes: list[CounterpartyNote],
    transactions: list[BankTransaction],
    note_by_invoice: dict[str, str],
    gl_entries: list[GLEntry],
) -> GroundTruth:
    _attach_dispute_notes(settlement.exceptions, note_by_invoice)

    exceptions = [
        ExceptionTruth(
            txn_id=e.txn_id,
            root_cause_type=e.root_cause_type,
            explanation=e.explanation,
            related_invoice_ids=list(e.related_invoice_ids),
            related_txn_ids=list(e.related_txn_ids),
            related_note_ids=list(e.related_note_ids),
            difficulty_tier=e.difficulty_tier,
        )
        for e in settlement.exceptions
    ]

    gt = GroundTruth(matches=list(settlement.matches), exceptions=exceptions)
    _validate(gt, invoices, notes, transactions)
    _validate_no_gl_leak(gt, invoices, transactions, gl_entries)
    return gt


def _validate_no_gl_leak(
    gt: GroundTruth,
    invoices: list[Invoice],
    transactions: list[BankTransaction],
    gl_entries: list[GLEntry],
) -> None:
    """The GL must not contain the answer (PLAN.md D3).

    ``propose_match`` accepts a GL entry as a target, so if any GL row named the
    transaction that settled it, reconciliation would collapse into a string
    comparison and the acceptance gate would measure nothing. This is checked at
    build time, in the engine, rather than left to a test of the tool layer — the
    property belongs to the data.
    """
    invoice_ids = {i.id for i in invoices}
    txn_ids = {t.id for t in transactions}

    for entry in gl_entries:
        # Transaction-shaped anchor first: it is also an "unknown invoice", but
        # this is the diagnosis that tells the reader what actually went wrong.
        if entry.invoice_id in txn_ids:
            raise GroundTruthError(f"{entry.id} is anchored to a transaction, not an invoice")
        if entry.invoice_id is not None and entry.invoice_id not in invoice_ids:
            raise GroundTruthError(f"{entry.id} cites unknown invoice {entry.invoice_id}")
        if any(tid in entry.memo for tid in txn_ids):
            raise GroundTruthError(f"{entry.id} names a transaction in its memo: {entry.memo!r}")

    # Every resolvable transaction must be reachable through the GL, or matching
    # against a gl_entry_id would be impossible for cases where it should work.
    invoices_with_gl = {e.invoice_id for e in gl_entries if e.invoice_id}
    for txn_id, invoice_id in gt.expected_invoice_by_txn.items():
        if invoice_id not in invoices_with_gl:
            raise GroundTruthError(
                f"{txn_id} resolves to {invoice_id}, which has no GL entry to match against"
            )


def _validate(
    gt: GroundTruth,
    invoices: list[Invoice],
    notes: list[CounterpartyNote],
    transactions: list[BankTransaction],
) -> None:
    invoice_ids = {i.id for i in invoices}
    note_ids = {n.id for n in notes}
    txn_ids = {t.id for t in transactions}

    # 1. Exactly one root cause per exception transaction.
    seen: set[str] = set()
    for exc in gt.exceptions:
        if exc.txn_id in seen:
            raise GroundTruthError(f"{exc.txn_id} carries more than one root cause")
        seen.add(exc.txn_id)

    # 2. An exception cannot also be a clean match.
    matched = {m.txn_id for m in gt.matches}
    if overlap := matched & seen:
        raise GroundTruthError(
            f"transactions labelled both matched and exception: {sorted(overlap)}"
        )

    # 3. Every referenced ID must exist — the answer key may not cite phantoms.
    for exc in gt.exceptions:
        for iid in exc.related_invoice_ids:
            if iid not in invoice_ids:
                raise GroundTruthError(f"{exc.txn_id} cites unknown invoice {iid}")
        for nid in exc.related_note_ids:
            if nid not in note_ids:
                raise GroundTruthError(f"{exc.txn_id} cites unknown note {nid}")
        for tid in exc.related_txn_ids:
            if tid not in txn_ids:
                raise GroundTruthError(f"{exc.txn_id} cites unknown transaction {tid}")
        if exc.txn_id not in txn_ids:
            raise GroundTruthError(f"exception refers to unknown transaction {exc.txn_id}")
        if not 1 <= exc.difficulty_tier <= 4:
            raise GroundTruthError(f"{exc.txn_id} has out-of-range tier {exc.difficulty_tier}")

    # 4. Every non-unknown exception must cite something. An explainable exception
    #    with no supporting record would be unlabellable by any honest agent, and
    #    would silently cap achievable eval accuracy below 100%.
    for exc in gt.exceptions:
        if exc.root_cause_type != "unknown" and not exc.evidence_ids:
            raise GroundTruthError(
                f"{exc.txn_id} is labelled {exc.root_cause_type} but cites no evidence"
            )

    # 5. Conversely, unknown cases must cite nothing — otherwise they are answerable.
    for exc in gt.exceptions:
        if exc.root_cause_type == "unknown" and exc.evidence_ids:
            raise GroundTruthError(f"{exc.txn_id} is labelled unknown but cites evidence")
