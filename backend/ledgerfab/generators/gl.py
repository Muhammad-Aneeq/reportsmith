"""General ledger — the accrual side of the purchase cycle.

Every invoice is booked when it arrives: debit the expense, credit accounts
payable. That is all the GL contains. The **bank side is deliberately unposted**,
because an unposted bank side is exactly what a reconciliation resolves: you hold
a statement in one hand and a ledger of payables in the other, and your job is to
work out which payment settles which accrual.

### Why this is a rewrite rather than the inherited version

The engine this was copied from generated GL entries one-per-transaction, each
carrying the ``txn_id`` that produced it. That is fine for its owner (its agent
never reads the GL) but fatal here: spec 02 F1 exposes
``propose_match(txn_id, gl_entry_id | invoice_id, reason)``, so a ``txn_id`` on
the GL row reduces the entire reconciliation task to a string comparison and the
CI acceptance test would prove nothing about the agent. Spec 02 §6's own schema
agrees — ``gl_entries(id, date, account_id, amount, description, invoice_id NULL)``
has no transaction column. See PLAN.md D3.

The link from a payment to a GL entry therefore runs *through the invoice*, which
is both how real books work and what makes the task worth setting.
"""

from __future__ import annotations

from ledgerfab.generators.companies import ACCOUNTS_PAYABLE, EXPENSE_CODES
from ledgerfab.models import Counterparty, GLEntry, Invoice
from ledgerfab.rng import Rng


def generate_gl_entries(
    rng: Rng,
    invoices: list[Invoice],
    counterparties: list[Counterparty],
) -> list[GLEntry]:
    """Two entries per invoice: the expense debit and the payables credit.

    Dated at issue, not at payment — the accrual predates the money. Memos quote
    the vendor's own invoice number, which is realistic and is corroboration for
    an agent, not a shortcut: it is the *bank* side whose references are missing.
    """
    by_id = {c.id: c for c in counterparties}
    entries: list[GLEntry] = []
    counter = 0

    def add(inv: Invoice, code: str, debit: float, credit: float, memo: str) -> None:
        nonlocal counter
        counter += 1
        entries.append(
            GLEntry(
                id=f"GL-{counter:05d}",
                date=inv.issue_date,
                account_code=code,
                debit=debit,
                credit=credit,
                memo=memo,
                invoice_id=inv.id,
            )
        )

    for inv in invoices:
        cp = by_id[inv.counterparty_id]
        expense_code = rng.choice(EXPENSE_CODES)
        memo = f"{cp.canonical_name} — invoice {inv.number}"

        add(inv, expense_code, inv.amount, 0.0, memo)
        add(inv, ACCOUNTS_PAYABLE, 0.0, inv.amount, memo)

    return entries
