"""Typed World — the object ``ledgerfab.generate(profile, seed)`` returns.

Dates are kept as real ``date`` objects here. The ``date_format_chaos`` knob is a
*presentation* concern and is applied at CSV export time only, so the internal
world stays clean and comparable while the exported files look like the mess a
real bookkeeper receives.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


class RootCauseType(StrEnum):
    """The exception taxonomy, inherited from the engine's first consumer.

    LedgerLab surfaces these through ``flag_exception(suspected_cause=...)``, so
    the enum is part of a tool's public contract now: extending it is a breaking
    change to that tool and needs a versioned tool name (spec 02 F1)."""

    PARTIAL_PAYMENT = "partial_payment"
    MISSING_REFERENCE = "missing_reference"
    DUPLICATE = "duplicate"
    TIMING = "timing"
    FX_ROUNDING = "fx_rounding"
    DISPUTE = "dispute"
    UNKNOWN = "unknown"


class InvoiceStatus(StrEnum):
    OPEN = "open"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    DISPUTED = "disputed"


# ----------------------------------------------------------------- entities --


@dataclass(frozen=True, slots=True)
class Company:
    id: str
    name: str
    base_currency: str
    period_start: date
    period_end: date


@dataclass(frozen=True, slots=True)
class Account:
    """A chart-of-accounts line."""

    code: str
    name: str
    type: str  # asset | liability | equity | income | expense


@dataclass(frozen=True, slots=True)
class Counterparty:
    id: str
    canonical_name: str
    aliases: list[str]
    payment_terms_days: int
    country: str


@dataclass(frozen=True, slots=True)
class Invoice:
    """``id`` is the stable internal key; ``number`` is what the vendor printed on
    the document and what a human quotes on a remittance. They are deliberately
    different so ``get_invoice(number_fuzzy=...)`` is a real search rather than a
    second spelling of an exact-id lookup (PLAN.md D7)."""

    id: str
    number: str
    counterparty_id: str
    po_number: str | None
    issue_date: date
    due_date: date
    amount: float
    currency: str
    status: InvoiceStatus


@dataclass(frozen=True, slots=True)
class BankTransaction:
    """A bank statement line. ``counterparty_raw`` may be an alias rather than the
    canonical name, and ``reference`` may be missing — that is the whole point.

    ``date`` is the parsed truth; ``date_raw`` is the string as the feed rendered
    it, which under a high ``date_format_chaos`` may be ambiguous ("03/04/2025").
    Both are required by spec 02 §6. ``messiness_flags`` lists only *observable*
    oddities, for the viewer to highlight — never anything from the answer key.
    """

    id: str
    date: date
    amount: float
    currency: str
    counterparty_raw: str
    reference: str | None
    description: str
    direction: str  # debit | credit
    bank_account_code: str = "1000"
    date_raw: str = ""
    messiness_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GLEntry:
    """An accrual-side ledger line, anchored to the invoice that caused it.

    There is deliberately no ``txn_id`` here. GL entries are booked when invoices
    arrive; the bank side is *unposted*, which is precisely what a reconciliation
    resolves. A txn id on this row would make ``propose_match`` solvable by string
    equality and the acceptance test meaningless (PLAN.md D3).
    """

    id: str
    date: date
    account_code: str
    debit: float
    credit: float
    memo: str
    invoice_id: str | None

    @property
    def amount(self) -> float:
        """Signed amount, debit-positive — the shape spec 02 §6 stores."""
        return round(self.debit - self.credit, 2)


@dataclass(frozen=True, slots=True)
class CounterpartyNote:
    """Free-text context a bookkeeper would have in email or a CRM. Often the only
    thing that distinguishes a dispute from a partial payment."""

    id: str
    counterparty_id: str
    date: date
    author: str
    text: str


@dataclass(frozen=True, slots=True)
class AccrualSchedule:
    id: str
    counterparty_id: str
    account_code: str
    amount: float
    cadence: str  # monthly | quarterly
    next_date: date


# ------------------------------------------------------------ ground truth --


@dataclass(frozen=True, slots=True)
class Match:
    """A transaction the upstream matcher would have settled cleanly."""

    txn_id: str
    invoice_id: str


@dataclass(frozen=True, slots=True)
class ExceptionTruth:
    """The correct answer for one exception — the label evals grade against.

    ``difficulty_tier`` 1-4, derived from the case's own features (alias used,
    reference missing, competing look-alike amounts). Tier 4 includes
    context-starved cases whose only honest answer is ``unknown``.
    """

    txn_id: str
    root_cause_type: RootCauseType
    explanation: str
    related_invoice_ids: list[str]
    related_txn_ids: list[str]  # duplicates cite the earlier transaction, not an invoice
    related_note_ids: list[str]
    difficulty_tier: int

    @property
    def evidence_ids(self) -> list[str]:
        """Every external ID that legitimately supports this label — the set an
        agent's citations are checked against by the eval evidence-validity grader."""
        return [*self.related_invoice_ids, *self.related_txn_ids, *self.related_note_ids]


@dataclass(frozen=True, slots=True)
class GroundTruth:
    matches: list[Match]
    exceptions: list[ExceptionTruth]

    def for_txn(self, txn_id: str) -> ExceptionTruth | None:
        return next((e for e in self.exceptions if e.txn_id == txn_id), None)

    @property
    def exception_txn_ids(self) -> set[str]:
        return {e.txn_id for e in self.exceptions}

    # -- the reconciliation answer key (LedgerLab / spec 02) ------------------
    @property
    def expected_invoice_by_txn(self) -> dict[str, str]:
        """txn_id → the one invoice that payment belongs to.

        Covers cleanly-matched transactions and every exception that has an
        invoice behind it, including duplicates: a second payment of INV-0007 is
        still a payment *against* INV-0007. Orphans are absent by construction —
        they have no right answer, which is the point of them.
        """
        expected = {m.txn_id: m.invoice_id for m in self.matches}
        for exc in self.exceptions:
            if exc.related_invoice_ids:
                expected[exc.txn_id] = exc.related_invoice_ids[0]
        return expected

    @property
    def resolvable_txn_ids(self) -> set[str]:
        """The denominator the acceptance gate scores against (PLAN.md D10).

        Every transaction an honest agent could match. Excludes the deliberate
        ``unknown`` orphans, so refusing to invent an answer for them costs the
        agent nothing — the metric measures reconciliation, not compliance.
        """
        return set(self.expected_invoice_by_txn)


# ------------------------------------------------------------------- world --


@dataclass(frozen=True, slots=True)
class World:
    """Everything one generated company-period contains, plus its answer key."""

    seed: int
    profile_name: str
    company: Company
    accounts: list[Account]
    counterparties: list[Counterparty]
    invoices: list[Invoice]
    transactions: list[BankTransaction]
    gl_entries: list[GLEntry]
    notes: list[CounterpartyNote]
    accruals: list[AccrualSchedule]
    ground_truth: GroundTruth = field(repr=False)

    # -- lookups -------------------------------------------------------------
    def counterparty(self, cp_id: str) -> Counterparty | None:
        return next((c for c in self.counterparties if c.id == cp_id), None)

    def invoice(self, invoice_id: str) -> Invoice | None:
        return next((i for i in self.invoices if i.id == invoice_id), None)

    def transaction(self, txn_id: str) -> BankTransaction | None:
        return next((t for t in self.transactions if t.id == txn_id), None)

    @property
    def exception_transactions(self) -> list[BankTransaction]:
        """The transactions an upstream matcher could not clear."""
        ids = self.ground_truth.exception_txn_ids
        return [t for t in self.transactions if t.id in ids]

    def to_dict(self) -> dict[str, Any]:
        """Canonical plain-data form, used for hashing and export."""
        return asdict(self)
