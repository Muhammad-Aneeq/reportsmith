"""Periods, and the one call that produces a period's data.

A ReportSmith period **is** a vendored-emitter period. The id is upstream's verbatim
(``2024-01``), which is what lets a figure here and a figure in StatementLens refer to
the same month without a translation table (PLAN.md **D-009**).

The whole world for a period is produced by one seeded call, so `make month2` is
"run the same function with a later index" rather than a second code path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from ledgerfab import generate as generate_world
from ledgerfab.models import World
from ledgerfab.profiles import get_profile
from ledgerfab.statements import StatementSet, emit_statements

# The demo company's history starts here, because the emitter's period 0 does.
DEFAULT_PROFILE = "squeeze"
DEFAULT_SEED = 42

# Eight, because eight is upstream's hard ceiling: `build_periods` raises above
# MAX_PERIODS, which spec 12 F1 fixes at *"multi-period (up to 8)"*. That ceiling reads
# naturally for statement analysis — eight periods is a lot to compare side by side —
# and tightly for a monthly reporting cadence, where eight periods is two-thirds of a
# year and a pack cannot show a prior-year comparative at all. Recorded in
# SIBLING_NOTES; here it simply bounds the demo history to 2024-01 … 2024-08.
DEFAULT_PERIOD_COUNT = 8

PERIOD_ID = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class UnknownPeriodError(ValueError):
    """Raised for a period id the emitter did not produce.

    A distinct type because the adapter layer turns this into a *gap* with a named
    reason, and catching bare ValueError there would also swallow real bugs.
    """


@dataclass(frozen=True, slots=True)
class PeriodRef:
    """A period and where it sits in the generated history."""

    id: str
    label: str
    index: int

    @property
    def prior_id(self) -> str | None:
        """The period before this one, or ``None`` at the start of history.

        ``None`` matters: every prior-period comparison in the pack has to render
        "n/a" for the first period rather than a comparison against nothing.
        """
        if self.index == 0:
            return None
        year, month = int(self.id[:4]), int(self.id[5:])
        return f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"


def validate_period_id(period_id: str) -> str:
    if not PERIOD_ID.match(period_id):
        raise UnknownPeriodError(f"period id must look like '2024-01', got {period_id!r}")
    return period_id


@lru_cache(maxsize=8)
def statements_for(
    profile: str = DEFAULT_PROFILE,
    seed: int = DEFAULT_SEED,
    periods: int = DEFAULT_PERIOD_COUNT,
) -> StatementSet:
    """The generated statement history. Cached because it is pure and not cheap.

    Safe to cache precisely because the emitter is seeded: same arguments always give
    the same object, so a cache hit and a fresh call are indistinguishable. That is an
    upstream guarantee (``statement_hash``), not an assumption made here.
    """
    return emit_statements(profile, seed=seed, periods=periods, grain="month")


@lru_cache(maxsize=8)
def world_for(period_id: str, profile: str = "realistic", seed: int = DEFAULT_SEED) -> World:
    """The purchase-cycle world for one month: invoices, exceptions, counterparties.

    Separate from the statement set on purpose. The statements are the *reported*
    position; this is the *operational* detail behind the payables line — the
    exceptions a controller actually chases. The emitter does not model them and the
    base engine does, so the pack draws on both.

    The period window is applied to the profile so every generated date lands inside
    the month, and the seed is offset by the period so two months are different data
    rather than the same month twice.
    """
    period = period_ref(period_id)
    stmt_period = next(p for p in statements_for().periods if p.id == period_id)
    base = get_profile(profile)
    monthly = base.with_overrides(
        period_start=stmt_period.start,
        period_end=stmt_period.end,
        n_invoices=40,
    )
    return generate_world(monthly, seed=seed + period.index)


def all_periods() -> list[PeriodRef]:
    return [PeriodRef(id=p.id, label=p.label, index=p.index) for p in statements_for().periods]


def period_ref(period_id: str) -> PeriodRef:
    validate_period_id(period_id)
    for period in all_periods():
        if period.id == period_id:
            return period
    known = ", ".join(p.id for p in all_periods())
    raise UnknownPeriodError(f"no such period {period_id!r}; generated history is {known}")


def default_period() -> PeriodRef:
    """The period `make month1` runs.

    The last generated month, not the first: a controller closes the month just ended,
    and a pack whose comparatives are all empty demos nothing. Picking from the end
    also means `make month2` has somewhere to go only if history allows it, which is
    asserted rather than hoped.
    """
    periods = all_periods()
    return periods[-2]


def next_period(period_id: str) -> PeriodRef:
    """The period `make month2` runs — the whole point of the repeatability demo."""
    periods = all_periods()
    current = period_ref(period_id)
    if current.index + 1 >= len(periods):
        raise UnknownPeriodError(
            f"{period_id} is the last generated period; "
            f"raise DEFAULT_PERIOD_COUNT to run a later month"
        )
    return periods[current.index + 1]
