"""Counterparty notes — the unstructured context a bookkeeper carries in their head.

Two kinds are generated:

* **Dispute notes**, written against a specific invoice. These are load-bearing:
  a dispute and a partial payment are numerically identical, so the note is the
  only thing that distinguishes them. An agent that ignores notes will
  systematically mislabel disputes as partial payments — which is exactly the
  failure the eval suite is built to catch.
* **Ambient notes**, unrelated chatter about terms and contacts. These are noise,
  and they matter: retrieval that only ever surfaces relevant notes would flatter
  the agent and hide its real discrimination ability.
"""

from __future__ import annotations

from datetime import date

from ledgerfab.models import Counterparty, CounterpartyNote, Invoice
from ledgerfab.profiles import Profile
from ledgerfab.rng import Rng

_AUTHORS = ["a.patel", "j.okafor", "m.lindqvist", "s.duarte", "r.whitfield"]

_DISPUTE_REASONS = [
    "short-shipped {n} units; withholding the balance until credit note issued",
    "quality claim raised on delivery; {n} items rejected and payment reduced pro rata",
    "duplicate line billed on this invoice; balance withheld pending correction",
    "agreed retention of {pct}% until the remedial work signs off",
    "pricing disagreement — invoiced above the agreed rate card; paying the agreed amount only",
]

_AMBIENT = [
    "Payment terms renegotiated to {days} days from next quarter.",
    "New AP contact confirmed; remittance advice now goes to their shared inbox.",
    "Confirmed bank details unchanged following their domain migration.",
    "They batch supplier payments on the last working day of the month.",
    "Annual price review scheduled; no impact on open invoices.",
    "Historically settles 2-3 weeks past due date; chased twice, no escalation needed.",
]


def generate_notes(
    rng: Rng,
    profile: Profile,
    counterparties: list[Counterparty],
    invoices: list[Invoice],
    dispute_invoice_ids: list[str],
) -> tuple[list[CounterpartyNote], dict[str, str]]:
    """Returns (notes, {invoice_id: note_id}) so dispute labels can cite their note."""
    notes: list[CounterpartyNote] = []
    by_invoice: dict[str, str] = {}
    invoice_map = {i.id: i for i in invoices}
    counter = 0

    def add(cp_id: str, day: date, text: str) -> CounterpartyNote:
        nonlocal counter
        counter += 1
        note = CounterpartyNote(
            id=f"NOTE-{counter:03d}",
            counterparty_id=cp_id,
            date=day,
            author=rng.choice(_AUTHORS),
            text=text,
        )
        notes.append(note)
        return note

    # Dispute notes first, so their IDs are stable regardless of ambient volume.
    for invoice_id in dispute_invoice_ids:
        inv = invoice_map[invoice_id]
        reason = rng.choice(_DISPUTE_REASONS).format(
            n=rng.randint(2, 40), pct=rng.randint(5, 25), days=rng.choice([30, 45, 60])
        )
        note = add(
            inv.counterparty_id,
            rng.jitter_days(inv.due_date, -10, 5),
            f"Dispute logged against invoice {inv.id}: {reason}.",
        )
        by_invoice[invoice_id] = note.id

    # Ambient chatter — roughly one note per counterparty, some with none.
    for cp in counterparties:
        for _ in range(rng.randint(0, 2)):
            add(
                cp.id,
                rng.date_between(profile.period_start, profile.period_end),
                rng.choice(_AMBIENT).format(days=rng.choice([14, 30, 45, 60])),
            )

    return notes, by_invoice
