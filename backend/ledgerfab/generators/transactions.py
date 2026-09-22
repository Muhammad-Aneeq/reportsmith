"""Settlement — where clean books become exceptions.

Each invoice is settled by exactly one path: a clean match, or one of the six
failure modes in ``RootCauseType``. Orphan transactions (no invoice at all) are
added separately to produce the ``unknown`` cases, which exist so evals can
measure whether the agent refuses to confabulate rather than reaching for the
nearest plausible label.

Two exception types are deliberately near-identical on the numbers alone —
``partial_payment`` and ``dispute`` are both short payments — and separable only
by the counterparty note. That is what stops LedgerLab being an arithmetic
exercise: context, not subtraction, resolves the exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ledgerfab.generators.companies import bank_account_for
from ledgerfab.models import (
    BankTransaction,
    Counterparty,
    Invoice,
    InvoiceStatus,
    Match,
    RootCauseType,
)
from ledgerfab.profiles import Profile
from ledgerfab.rng import Rng


@dataclass
class PendingException:
    """A ground-truth label under construction. Note IDs are attached later by the
    notes generator, which is why this is mutable and ``ExceptionTruth`` is not."""

    txn_id: str
    root_cause_type: RootCauseType
    explanation: str
    related_invoice_ids: list[str] = field(default_factory=list)
    related_txn_ids: list[str] = field(default_factory=list)
    related_note_ids: list[str] = field(default_factory=list)
    difficulty_tier: int = 1


@dataclass
class SettlementResult:
    transactions: list[BankTransaction]
    matches: list[Match]
    exceptions: list[PendingException]
    invoice_status: dict[str, InvoiceStatus]
    dispute_invoice_ids: list[str]


_PAYMENT_RAILS = ["BACS PAYMENT", "FASTER PAYMENT", "CHAPS", "DIRECT DEBIT", "BANK TRANSFER"]

# Payees that never invoiced this company. Deliberately disjoint from the
# counterparty stems in `counterparties.py`, so an orphan payment cannot be
# explained by *any* invoice, note or prior payment in the world.
#
# This is what makes the `unknown` label defensible. Earlier these payments went
# to real counterparties who had open invoices, which made "partial payment
# against one of their invoices" a reasonable inference rather than a
# confabulation — so the unknown-honesty metric was punishing sound reasoning
# instead of measuring refusal to invent.
_UNKNOWN_PAYEES = [
    "Vantage Facilities Ltd",
    "Millbrook Freight Ltd",
    "Thornbury Associates LLP",
    "Aldgate Media Ltd",
    "Rosewood Catering Ltd",
    "Calder Utilities PLC",
]


def _counterparty_label(cp: Counterparty, rng: Rng, profile: Profile) -> str:
    """The name as it lands on the statement — canonical, or an alias."""
    if cp.aliases and rng.chance(profile.alias_rate):
        return rng.choice(cp.aliases)
    return cp.canonical_name


def _reference_for(inv: Invoice, rng: Rng) -> str:
    """What the payer typed in the reference field.

    Three plausible things, because all three happen: the PO number, the invoice
    number as the vendor printed it, or the internal invoice id. The mix is what
    forces an agent to use both ``get_invoice(invoice_id=...)`` and
    ``get_invoice(number_fuzzy=...)`` rather than only ever the exact-id path.
    """
    candidates = [inv.number, inv.id]
    if inv.po_number:
        # POs dominate real remittances, so weight it accordingly.
        candidates = [inv.po_number, inv.po_number, inv.number, inv.id]
    return rng.choice(candidates)


def _describe(rail: str, label: str, reference: str | None) -> str:
    return f"{rail} {label}" + (f" {reference}" if reference else "")


def _similar_amount_count(inv: Invoice, invoices: list[Invoice]) -> int:
    """How many other invoices sit within 2% of this one — the competing-candidate
    signal that makes a case genuinely harder rather than arbitrarily labelled."""
    tol = inv.amount * 0.02
    return sum(1 for o in invoices if o.id != inv.id and abs(o.amount - inv.amount) <= tol)


def _tier(*, aliased: bool, no_reference: bool, competitors: int) -> int:
    """Difficulty derived from the case's actual features, not assigned by fiat."""
    tier = 1
    if aliased:
        tier += 1
    if no_reference:
        tier += 1
    if competitors >= 2:
        tier += 1
    return min(tier, 4)


def generate_transactions(  # noqa: C901 - one branch per exception type; splitting hides the taxonomy
    rng: Rng,
    profile: Profile,
    invoices: list[Invoice],
    counterparties: list[Counterparty],
    currency: str,
) -> SettlementResult:
    by_id = {c.id: c for c in counterparties}
    txns: list[BankTransaction] = []
    matches: list[Match] = []
    exceptions: list[PendingException] = []
    statuses: dict[str, InvoiceStatus] = {}
    disputed_invoices: list[str] = []
    counter = 0

    def new_txn(
        *,
        day: date,
        amount: float,
        label: str,
        reference: str | None,
        rail: str,
    ) -> BankTransaction:
        nonlocal counter
        counter += 1
        return BankTransaction(
            id=f"TXN-{counter:04d}",
            date=day,
            amount=amount,
            currency=currency,
            counterparty_raw=label,
            reference=reference,
            description=_describe(rail, label, reference),
            direction="debit",
            bank_account_code=bank_account_for(amount),
            # date_raw and messiness_flags are filled by the presentation pass,
            # which owns every formatting decision (ledgerfab.messiness).
        )

    for inv in invoices:
        cp = by_id[inv.counterparty_id]
        rail = rng.choice(_PAYMENT_RAILS)
        label = _counterparty_label(cp, rng, profile)
        aliased = label != cp.canonical_name
        competitors = _similar_amount_count(inv, invoices)
        pay_date = rng.jitter_days(inv.due_date, -3, 7)

        # One roll decides this invoice's fate; bands are ordered so the knobs
        # compose additively and never double-apply to the same invoice.
        roll = rng.uniform(0.0, 1.0)
        p = profile
        cut_partial = p.partial_payment_rate
        cut_missing = cut_partial + p.missing_reference_rate
        cut_dup = cut_missing + p.duplicate_rate
        cut_timing = cut_dup + p.timing_rate
        cut_dispute = cut_timing + p.dispute_rate
        cut_fx = cut_dispute + (p.amount_noise if p.amount_noise > 0 else 0.0)

        # ---------------------------------------------------------- partial --
        if roll < cut_partial:
            paid = rng.pct_of(inv.amount, 0.35, 0.80)
            t = new_txn(
                day=pay_date,
                amount=paid,
                label=label,
                reference=_reference_for(inv, rng),
                rail=rail,
            )
            txns.append(t)
            statuses[inv.id] = InvoiceStatus.PARTIALLY_PAID
            exceptions.append(
                PendingException(
                    txn_id=t.id,
                    root_cause_type=RootCauseType.PARTIAL_PAYMENT,
                    explanation=(
                        f"Payment of {paid:.2f} settles only part of invoice {inv.id} "
                        f"({inv.amount:.2f}); balance {inv.amount - paid:.2f} remains outstanding."
                    ),
                    related_invoice_ids=[inv.id],
                    difficulty_tier=_tier(
                        aliased=aliased, no_reference=False, competitors=competitors
                    ),
                )
            )

        # -------------------------------------------------- missing reference --
        elif roll < cut_missing:
            t = new_txn(day=pay_date, amount=inv.amount, label=label, reference=None, rail=rail)
            txns.append(t)
            statuses[inv.id] = InvoiceStatus.PAID
            exceptions.append(
                PendingException(
                    txn_id=t.id,
                    root_cause_type=RootCauseType.MISSING_REFERENCE,
                    explanation=(
                        f"Amount matches invoice {inv.id} exactly but the payment carries no "
                        f"PO or invoice reference, so the matcher could not link it."
                    ),
                    related_invoice_ids=[inv.id],
                    difficulty_tier=_tier(
                        aliased=aliased, no_reference=True, competitors=competitors
                    ),
                )
            )

        # -------------------------------------------------------- duplicate --
        elif roll < cut_dup:
            ref = _reference_for(inv, rng)
            original = new_txn(
                day=pay_date, amount=inv.amount, label=label, reference=ref, rail=rail
            )
            txns.append(original)
            matches.append(Match(txn_id=original.id, invoice_id=inv.id))

            dup = new_txn(
                day=rng.jitter_days(pay_date, 0, 3),
                amount=inv.amount,
                label=label,
                reference=ref,
                rail=rail,
            )
            txns.append(dup)
            statuses[inv.id] = InvoiceStatus.PAID
            exceptions.append(
                PendingException(
                    txn_id=dup.id,
                    root_cause_type=RootCauseType.DUPLICATE,
                    explanation=(
                        f"Second payment of {inv.amount:.2f} for invoice {inv.id}; "
                        f"transaction {original.id} already settled it on "
                        f"{original.date.isoformat()}."
                    ),
                    related_invoice_ids=[inv.id],
                    related_txn_ids=[original.id],
                    difficulty_tier=_tier(
                        aliased=aliased, no_reference=False, competitors=competitors
                    ),
                )
            )

        # ----------------------------------------------------------- timing --
        elif roll < cut_timing:
            late = inv.due_date + timedelta(days=rng.randint(25, 70))
            t = new_txn(
                day=late,
                amount=inv.amount,
                label=label,
                reference=_reference_for(inv, rng),
                rail=rail,
            )
            txns.append(t)
            statuses[inv.id] = InvoiceStatus.PAID
            exceptions.append(
                PendingException(
                    txn_id=t.id,
                    root_cause_type=RootCauseType.TIMING,
                    explanation=(
                        f"Invoice {inv.id} was due {inv.due_date.isoformat()} but paid "
                        f"{late.isoformat()}, landing outside the matching window."
                    ),
                    related_invoice_ids=[inv.id],
                    difficulty_tier=_tier(
                        aliased=aliased, no_reference=False, competitors=competitors
                    ),
                )
            )

        # ---------------------------------------------------------- dispute --
        elif roll < cut_dispute:
            paid = rng.pct_of(inv.amount, 0.55, 0.90)
            t = new_txn(
                day=rng.jitter_days(inv.due_date, 5, 30),
                amount=paid,
                label=label,
                reference=_reference_for(inv, rng),
                rail=rail,
            )
            txns.append(t)
            statuses[inv.id] = InvoiceStatus.DISPUTED
            disputed_invoices.append(inv.id)
            exceptions.append(
                PendingException(
                    txn_id=t.id,
                    root_cause_type=RootCauseType.DISPUTE,
                    explanation=(
                        f"Short payment against invoice {inv.id}: {inv.amount - paid:.2f} withheld "
                        f"pending the dispute recorded in the counterparty notes."
                    ),
                    related_invoice_ids=[inv.id],
                    difficulty_tier=max(
                        2, _tier(aliased=aliased, no_reference=False, competitors=competitors)
                    ),
                )
            )

        # ------------------------------------------------------ fx/rounding --
        elif roll < cut_fx:
            delta = round(inv.amount * rng.uniform(0.001, 0.008), 2)
            paid = round(inv.amount - delta, 2)
            t = new_txn(
                day=pay_date,
                amount=paid,
                label=label,
                reference=_reference_for(inv, rng),
                rail=rail,
            )
            txns.append(t)
            statuses[inv.id] = InvoiceStatus.PAID
            exceptions.append(
                PendingException(
                    txn_id=t.id,
                    root_cause_type=RootCauseType.FX_ROUNDING,
                    explanation=(
                        f"Payment differs from invoice {inv.id} by {delta:.2f} "
                        f"({delta / inv.amount:.2%}) — consistent with rounding or an FX spread, "
                        f"not a partial settlement."
                    ),
                    related_invoice_ids=[inv.id],
                    difficulty_tier=max(
                        2, _tier(aliased=aliased, no_reference=False, competitors=competitors)
                    ),
                )
            )

        # ------------------------------------------------------ clean match --
        else:
            t = new_txn(
                day=pay_date,
                amount=inv.amount,
                label=cp.canonical_name,
                reference=_reference_for(inv, rng),
                rail=rail,
            )
            txns.append(t)
            matches.append(Match(txn_id=t.id, invoice_id=inv.id))
            statuses[inv.id] = InvoiceStatus.PAID

    # ----------------------------------------------------------- unknowns --
    # Orphans: real money moved, no invoice explains it, no note mentions it. The
    # only honest answer is "unknown" — these cases exist to catch confabulation.
    n_unknown = max(1, round(profile.n_invoices * profile.unknown_rate))
    for _ in range(n_unknown):
        t = new_txn(
            day=rng.date_between(profile.period_start, profile.period_end),
            amount=rng.money(150.0, 6_000.0),
            label=rng.choice(_UNKNOWN_PAYEES),
            reference=None,
            rail=rng.choice(_PAYMENT_RAILS),
        )
        txns.append(t)
        exceptions.append(
            PendingException(
                txn_id=t.id,
                root_cause_type=RootCauseType.UNKNOWN,
                explanation=(
                    "No invoice, prior transaction or note in the available context explains "
                    "this payment. Insufficient evidence to assign a root cause."
                ),
                difficulty_tier=4,
            )
        )

    return SettlementResult(
        transactions=txns,
        matches=matches,
        exceptions=exceptions,
        invoice_status=statuses,
        dispute_invoice_ids=disputed_invoices,
    )
