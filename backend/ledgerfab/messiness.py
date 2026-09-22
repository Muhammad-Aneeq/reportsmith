"""Presentation messiness — the chaos an observer can actually see on a statement.

The generators build a *clean* world with real ``date`` objects. This module then
applies the ``date_format_chaos`` knob and records what it did, so two things can
both be true: the internal world stays comparable and hashable, and the session DB
still carries the ``date_raw`` / ``date_iso`` pair spec 02 §6 requires.

Why a separate pass rather than inline in the transaction generator: chaos is a
rendering decision, not a fact about the payment. Keeping it here means the
transaction generator's random stream is untouched by formatting choices, so
adding a new date format cannot shift anybody's amounts.

Only *observable* properties become flags. "This payment used an alias" and "this
reference is blank" are visible to anyone reading the row. "This amount carries FX
noise" is not — it is an answer, and answers live in ``ground_truth``, never here.
See PLAN.md D6 and D17.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from ledgerfab.models import BankTransaction, World
from ledgerfab.profiles import Profile
from ledgerfab.rng import Rng

# ISO is the unambiguous default, used whenever chaos does not fire.
ISO = "%Y-%m-%d"

# Each entry: (strftime pattern, the label the viewer shows).
# "DD.MM.YY" is spec 02 §9's own worked example of an annotation, so it is here
# verbatim rather than paraphrased.
CHAOTIC_FORMATS: list[tuple[str, str]] = [
    ("%d/%m/%Y", "DD/MM/YYYY"),
    ("%m-%d-%y", "MM-DD-YY"),
    ("%d %b %Y", "DD Mon YYYY"),
    ("%d.%m.%Y", "DD.MM.YYYY"),
    ("%d.%m.%y", "DD.MM.YY"),
]

# Flag vocabulary. Kept as constants because the viewer renders them and the
# tests assert on them; a typo in a string literal should break the build.
FLAG_DATE_FORMAT = "date_format"
FLAG_ALIAS_USED = "alias_used"
FLAG_REFERENCE_MISSING = "reference_missing"
FLAG_PAYEE_UNRECOGNISED = "payee_unrecognised"


def format_date(day: date, rng: Rng, chaos: float) -> tuple[str, str | None]:
    """Render a date as a bank feed would. Returns (raw_string, format_label).

    ``format_label`` is None when the date came out as plain ISO, which is what
    lets the viewer highlight only the genuinely awkward rows.
    """
    if chaos > 0 and rng.chance(chaos):
        pattern, label = rng.choice(CHAOTIC_FORMATS)
        return day.strftime(pattern), label
    return day.strftime(ISO), None


def _flags_for(
    txn: BankTransaction,
    date_label: str | None,
    canonical_names: set[str],
    alias_names: set[str],
) -> list[str]:
    """The annotations spec 02 §9 asks the World Browser to highlight.

    ``alias_used`` and ``payee_unrecognised`` are deliberately distinct. A payee
    that appears in no counterparty record at all is not a naming variant — it is
    a name your books have never seen, which is a different problem and a
    different colour on screen.
    """
    flags: list[str] = []
    if date_label:
        flags.append(f"{FLAG_DATE_FORMAT}:{date_label}")
    if txn.counterparty_raw in alias_names:
        flags.append(FLAG_ALIAS_USED)
    elif txn.counterparty_raw not in canonical_names:
        flags.append(FLAG_PAYEE_UNRECOGNISED)
    if not txn.reference:
        flags.append(FLAG_REFERENCE_MISSING)
    return flags


def apply_presentation_messiness(world: World, profile: Profile) -> World:
    """Return a copy of ``world`` whose transactions carry date_raw + flags.

    Deterministic: draws from its own ``messiness`` sub-stream derived from the
    world's seed, so the formatting is reproducible and independent of every
    other generator.
    """
    rng = Rng(world.seed, "ledgerfab/messiness")
    canonical_names = {c.canonical_name for c in world.counterparties}
    alias_names = {alias for c in world.counterparties for alias in c.aliases}

    transactions = []
    for txn in world.transactions:
        raw, label = format_date(txn.date, rng, profile.date_format_chaos)
        transactions.append(
            replace(
                txn,
                date_raw=raw,
                messiness_flags=_flags_for(txn, label, canonical_names, alias_names),
            )
        )

    return replace(world, transactions=transactions)
