"""Recurring accrual schedules (spec 00 A3).

Not consumed by the v1 investigation graph, but emitted because ledgerfab is a
shared foundation: Project 10's accruals-checklist agent verifies recurring
accruals against exactly these schedules. Kept minimal and deterministic.
"""

from __future__ import annotations

from datetime import timedelta

from ledgerfab.generators.companies import EXPENSE_CODES
from ledgerfab.models import AccrualSchedule, Counterparty
from ledgerfab.profiles import Profile
from ledgerfab.rng import Rng


def generate_accruals(
    rng: Rng, profile: Profile, counterparties: list[Counterparty]
) -> list[AccrualSchedule]:
    # Roughly a third of counterparties carry a standing arrangement.
    chosen = rng.sample(counterparties, max(1, len(counterparties) // 3))
    out: list[AccrualSchedule] = []

    for i, cp in enumerate(chosen, start=1):
        cadence = rng.choice(["monthly", "monthly", "quarterly"])
        step = 30 if cadence == "monthly" else 90
        out.append(
            AccrualSchedule(
                id=f"ACC-{i:03d}",
                counterparty_id=cp.id,
                account_code=rng.choice(EXPENSE_CODES),
                amount=rng.money(200.0, 4_000.0),
                cadence=cadence,
                next_date=profile.period_end + timedelta(days=step),
            )
        )

    return out
