"""ledgerfab — the synthetic finance data engine (spec 00 A3).

    from ledgerfab import generate
    world = generate("realistic", seed=42)
    world.ground_truth.exceptions   # the answer key, free with every dataset

Determinism contract: same seed + same profile => byte-identical world, provable
via ``dataset_hash(world)``. All randomness routes through ``ledgerfab.rng``; the
package holds no clock, no UUIDs and no global state.

Deliberately self-contained: nothing here imports from ``app``. That one-way
dependency is what makes extracting this package into its own repo a move rather
than a refactor.
"""

from __future__ import annotations

from dataclasses import replace

from ledgerfab.generators.accruals import generate_accruals
from ledgerfab.generators.companies import generate_accounts, generate_company
from ledgerfab.generators.counterparties import generate_counterparties
from ledgerfab.generators.gl import generate_gl_entries
from ledgerfab.generators.invoices import generate_invoices
from ledgerfab.generators.notes import generate_notes
from ledgerfab.generators.transactions import generate_transactions
from ledgerfab.ground_truth import build_ground_truth
from ledgerfab.hashing import dataset_hash
from ledgerfab.messiness import apply_presentation_messiness
from ledgerfab.models import (
    Account,
    AccrualSchedule,
    BankTransaction,
    Company,
    Counterparty,
    CounterpartyNote,
    ExceptionTruth,
    GLEntry,
    GroundTruth,
    Invoice,
    InvoiceStatus,
    Match,
    RootCauseType,
    World,
)
from ledgerfab.profiles import CLEAN, NIGHTMARE, PROFILES, REALISTIC, Profile, get_profile
from ledgerfab.rng import Rng

__all__ = [
    "generate",
    "dataset_hash",
    "apply_presentation_messiness",
    "get_profile",
    "Profile",
    "PROFILES",
    "CLEAN",
    "REALISTIC",
    "NIGHTMARE",
    "World",
    "GroundTruth",
    "ExceptionTruth",
    "Match",
    "RootCauseType",
    "InvoiceStatus",
    "Company",
    "Account",
    "Counterparty",
    "Invoice",
    "BankTransaction",
    "GLEntry",
    "CounterpartyNote",
    "AccrualSchedule",
    "Rng",
]

__version__ = "0.1.0"


def generate(profile: str | Profile = "realistic", seed: int = 42) -> World:
    """Generate one company-period of synthetic books, plus its ground truth.

    Args:
        profile: ``"clean"``, ``"realistic"``, ``"nightmare"``, or a custom Profile.
        seed: any int. Same seed + profile always yields the same world.
    """
    prof = get_profile(profile)
    root = Rng(seed, "ledgerfab")

    company = generate_company(root.child("company"), prof)
    accounts = generate_accounts()
    counterparties = generate_counterparties(root.child("counterparties"), prof)
    invoices = generate_invoices(
        root.child("invoices"), prof, counterparties, company.base_currency
    )

    settlement = generate_transactions(
        root.child("transactions"), prof, invoices, counterparties, company.base_currency
    )

    notes, note_by_invoice = generate_notes(
        root.child("notes"), prof, counterparties, invoices, settlement.dispute_invoice_ids
    )

    # Settlement decided each invoice's fate; fold those statuses back in.
    invoices = [
        replace(inv, status=settlement.invoice_status.get(inv.id, inv.status)) for inv in invoices
    ]

    # GL is booked from invoices, never from transactions — see generators/gl.py.
    gl_entries = generate_gl_entries(root.child("gl"), invoices, counterparties)
    accruals = generate_accruals(root.child("accruals"), prof, counterparties)

    ground_truth = build_ground_truth(
        settlement, invoices, notes, settlement.transactions, note_by_invoice, gl_entries
    )

    world = World(
        seed=seed,
        profile_name=prof.name,
        company=company,
        accounts=accounts,
        counterparties=counterparties,
        invoices=invoices,
        transactions=settlement.transactions,
        gl_entries=gl_entries,
        notes=notes,
        accruals=accruals,
        ground_truth=ground_truth,
    )

    # Last: render the dates as a bank feed would. A separate pass so that a
    # formatting change can never perturb an amount (ledgerfab.messiness).
    return apply_presentation_messiness(world, prof)
