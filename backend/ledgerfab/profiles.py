"""Messiness knobs and the clean / realistic / nightmare presets (spec 00 A3).

The seven knobs spec 00 A3 names are all here and authoritative. Three more —
``timing_rate``, ``dispute_rate`` and ``unknown_rate`` — are inherited from the
engine's first consumer, because none of the seven original knobs can produce the
``timing``, ``dispute`` or ``unknown`` root causes, and without them a third of
the exception taxonomy would be ungeneratable. See PLAN.md D8.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date


@dataclass(frozen=True, slots=True)
class Profile:
    """A named messiness configuration. Frozen: a profile cannot drift mid-run."""

    name: str

    # -- sizing --------------------------------------------------------------
    n_counterparties: int = 12
    n_invoices: int = 60
    period_start: date = date(2025, 1, 1)
    period_end: date = date(2025, 3, 31)

    # -- the seven spec 00 A3 knobs -----------------------------------------
    partial_payment_rate: float = 0.10
    missing_reference_rate: float = 0.10
    duplicate_rate: float = 0.04
    date_format_chaos: float = 0.15
    amount_noise: float = 0.03
    alias_rate: float = 0.20
    fx_rate: bool = False  # flag-only in v1 (spec 00 A3)

    # -- knobs added to cover the rest of the root-cause enum ---------------
    timing_rate: float = 0.08
    dispute_rate: float = 0.05
    unknown_rate: float = 0.05

    @property
    def total_exception_rate(self) -> float:
        """Share of transactions that become exceptions. Sanity-checked at build."""
        return (
            self.partial_payment_rate
            + self.missing_reference_rate
            + self.duplicate_rate
            + self.timing_rate
            + self.dispute_rate
            + self.unknown_rate
        )

    def with_overrides(self, **kwargs: object) -> Profile:
        """A copy with individual knobs overridden — used by evals to build tiers."""
        return replace(self, **kwargs)  # type: ignore[arg-type]


CLEAN = Profile(
    name="clean",
    partial_payment_rate=0.03,
    missing_reference_rate=0.02,
    duplicate_rate=0.01,
    date_format_chaos=0.0,
    amount_noise=0.0,
    alias_rate=0.0,
    fx_rate=False,
    timing_rate=0.02,
    dispute_rate=0.01,
    unknown_rate=0.01,
)

REALISTIC = Profile(
    name="realistic",
    partial_payment_rate=0.10,
    missing_reference_rate=0.10,
    duplicate_rate=0.04,
    date_format_chaos=0.15,
    amount_noise=0.03,
    alias_rate=0.20,
    fx_rate=False,
    timing_rate=0.08,
    dispute_rate=0.05,
    unknown_rate=0.05,
)

NIGHTMARE = Profile(
    name="nightmare",
    n_counterparties=18,
    n_invoices=90,
    partial_payment_rate=0.18,
    missing_reference_rate=0.20,
    duplicate_rate=0.09,
    date_format_chaos=0.55,
    amount_noise=0.10,
    alias_rate=0.60,
    fx_rate=True,
    timing_rate=0.15,
    dispute_rate=0.10,
    unknown_rate=0.10,
)

PROFILES: dict[str, Profile] = {p.name: p for p in (CLEAN, REALISTIC, NIGHTMARE)}


def get_profile(profile: str | Profile) -> Profile:
    """Resolve a profile by name, or pass a custom Profile straight through."""
    if isinstance(profile, Profile):
        return profile
    try:
        return PROFILES[profile]
    except KeyError:
        known = ", ".join(sorted(PROFILES))
        raise ValueError(f"unknown profile {profile!r}; expected one of: {known}") from None
