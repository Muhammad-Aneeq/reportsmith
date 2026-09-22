"""Purchase invoices with PO numbers.

Invoices are generated *before* transactions because settlement drives the mess:
the transaction generator decides how (or whether) each invoice gets paid, and
writes the invoice's final status back. Statuses here are provisional.
"""

from __future__ import annotations

from ledgerfab.models import Counterparty, Invoice, InvoiceStatus
from ledgerfab.profiles import Profile
from ledgerfab.rng import Rng

# Invoice sizes cluster: many small, a few large. Keeps amount collisions realistic
# without making every exception a coin-flip between identical candidates.
_AMOUNT_BANDS: list[tuple[float, float, int]] = [
    (120.0, 900.0, 5),  # small, common
    (900.0, 4_500.0, 3),  # mid
    (4_500.0, 22_000.0, 1),  # large, rare
]


def _pick_amount(rng: Rng) -> float:
    weighted = [band for band in _AMOUNT_BANDS for _ in range(band[2])]
    low, high, _ = rng.choice(weighted)
    return rng.money(low, high)


def _vendor_prefix(canonical_name: str) -> str:
    """ "Acme Supplies Ltd" -> "ACM". The stem a vendor puts on its own documents."""
    stem = "".join(ch for ch in canonical_name.split()[0] if ch.isalpha())
    return stem[:3].upper()


class _NumberSeries:
    """Per-vendor invoice numbering, because that is how vendors actually number.

    Each counterparty gets its own sequence starting at a random base, so numbers
    are realistic, globally unique, and not merely a restatement of the invoice's
    index — which is what makes ``number_fuzzy`` a genuine search (PLAN.md D7).
    """

    def __init__(self, rng: Rng) -> None:
        self._rng = rng
        self._next: dict[str, int] = {}

    def issue(self, cp: Counterparty, year: int) -> str:
        if cp.id not in self._next:
            self._next[cp.id] = self._rng.randint(1_000, 8_000)
        seq = self._next[cp.id]
        self._next[cp.id] = seq + 1
        return f"{_vendor_prefix(cp.canonical_name)}-{year}-{seq:04d}"


def generate_invoices(
    rng: Rng,
    profile: Profile,
    counterparties: list[Counterparty],
    currency: str,
) -> list[Invoice]:
    out: list[Invoice] = []
    numbers = _NumberSeries(rng)

    for i in range(1, profile.n_invoices + 1):
        cp = rng.choice(counterparties)
        issue_date = rng.date_between(profile.period_start, profile.period_end)
        due_date = rng.jitter_days(issue_date, cp.payment_terms_days, cp.payment_terms_days)

        # Most invoices carry a PO; some genuinely never had one, which is a
        # legitimate reason a reference can be absent downstream.
        po_number = f"PO-{rng.randint(10_000, 99_999)}" if rng.chance(0.8) else None

        out.append(
            Invoice(
                id=f"INV-{i:04d}",
                number=numbers.issue(cp, issue_date.year),
                counterparty_id=cp.id,
                po_number=po_number,
                issue_date=issue_date,
                due_date=due_date,
                amount=_pick_amount(rng),
                currency=currency,
                status=InvoiceStatus.OPEN,
            )
        )

    return out
