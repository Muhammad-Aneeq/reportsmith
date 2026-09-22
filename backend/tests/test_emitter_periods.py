"""The period grid.

Small, but it carries the trap that PLAN.md P4 risk (c) names: ``Period.days`` is the
period's *own* day count, and a formula that reaches for 365 instead is wrong by a
factor of four on a quarterly set while still returning a plausible number. The grid is
where that fact is established, so it is where it gets asserted.
"""

from __future__ import annotations

from datetime import date
from itertools import pairwise

import pytest

from ledgerfab.statements import MAX_PERIODS, build_periods


def test_quarters_are_contiguous_and_labelled() -> None:
    periods = build_periods(8, "quarter", date(2024, 1, 1))
    assert [p.id for p in periods] == [
        "2024-Q1",
        "2024-Q2",
        "2024-Q3",
        "2024-Q4",
        "2025-Q1",
        "2025-Q2",
        "2025-Q3",
        "2025-Q4",
    ]
    assert periods[0].label == "Q1 2024"
    assert periods[0].start == date(2024, 1, 1)
    assert periods[0].end == date(2024, 3, 31)
    assert periods[-1].end == date(2025, 12, 31)


def test_months_are_contiguous() -> None:
    periods = build_periods(8, "month", date(2024, 11, 1))
    assert [p.id for p in periods] == [
        "2024-11",
        "2024-12",
        "2025-01",
        "2025-02",
        "2025-03",
        "2025-04",
        "2025-05",
        "2025-06",
    ]
    assert periods[1].end == date(2024, 12, 31)


def test_years_are_contiguous() -> None:
    periods = build_periods(3, "year", date(2023, 1, 1))
    assert [p.id for p in periods] == ["2023", "2024", "2025"]
    assert periods[0].label == "FY2023"
    assert periods[-1].end == date(2025, 12, 31)


@pytest.mark.parametrize("grain", ["month", "quarter", "year"])
def test_periods_never_overlap_or_leave_a_gap(grain: str) -> None:
    periods = build_periods(6 if grain != "year" else 3, grain, date(2024, 1, 1))
    for earlier, later in pairwise(periods):
        assert (later.start - earlier.end).days == 1, (
            f"{earlier.id} ends {earlier.end} but {later.id} starts {later.start}"
        )


def test_day_counts_are_the_periods_own() -> None:
    """The quarterly-vs-365 trap at its source."""
    quarters = build_periods(4, "quarter", date(2024, 1, 1))
    assert [p.days for p in quarters] == [91, 91, 92, 92]  # 2024 is a leap year
    assert sum(p.days for p in quarters) == 366

    assert build_periods(1, "year", date(2025, 1, 1))[0].days == 365
    assert build_periods(1, "month", date(2025, 2, 1))[0].days == 28


def test_indices_are_sequential_from_zero() -> None:
    periods = build_periods(5, "quarter", date(2024, 4, 1))
    assert [p.index for p in periods] == [0, 1, 2, 3, 4]


def test_more_than_eight_periods_is_rejected() -> None:
    """Spec 12 F1 caps multi-period intake at 8."""
    assert MAX_PERIODS == 8
    with pytest.raises(ValueError, match=r"1\.\.8"):
        build_periods(9, "quarter", date(2024, 1, 1))


def test_zero_periods_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"1\.\.8"):
        build_periods(0, "quarter", date(2024, 1, 1))


def test_an_unknown_grain_is_rejected_loudly() -> None:
    with pytest.raises(ValueError, match="unknown grain"):
        build_periods(4, "fortnight", date(2024, 1, 1))
