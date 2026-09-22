"""The types the statement emitter returns.

Shaped by one decision (PLAN.md **D-003**): statements are *derived* from double-entry
journal entries, never authored directly. So the primary artefact is
``StatementSet.entries`` — the books — and ``StatementSet.lines`` is what you get when
you read them. Three independently-written statements are three chances to disagree
with each other; a trial balance cannot disagree with itself.

``entries`` is kept on the returned object rather than thrown away, because it is the
evidence for the invariant tests and because a later project may want the postings
rather than the presentation.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from ledgerfab.statements.chart import ACCOUNTS_BY_CODE, LINE_ORDER, is_debit_positive
from ledgerfab.statements.money import ZERO, money

GRAINS: tuple[str, ...] = ("month", "quarter", "year")
MAX_PERIODS = 8
"""Spec 12 F1: *"multi-period (up to 8)"*."""


# ------------------------------------------------------------------- periods --


@dataclass(frozen=True, slots=True)
class Period:
    """One reporting period.

    ``days`` is carried rather than assumed. Receivable days on a quarterly set must
    divide by the quarter's own day count, not by 365 — a formula that hard-codes the
    year is wrong by a factor of four and still returns a plausible-looking number.
    """

    id: str
    label: str
    start: date
    end: date
    index: int
    grain: str

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def build_periods(count: int, grain: str, first_start: date) -> tuple[Period, ...]:
    """``count`` contiguous periods of ``grain``, starting at ``first_start``.

    Contiguity is produced here rather than validated later: the emitter cannot create
    a gap, so P3's period-alignment check is exercising the *upload* path, which is the
    only path that can actually be misaligned.
    """
    if grain not in GRAINS:
        raise ValueError(f"unknown grain {grain!r}; expected one of {', '.join(GRAINS)}")
    if not 1 <= count <= MAX_PERIODS:
        raise ValueError(f"count must be 1..{MAX_PERIODS} (spec 12 F1), got {count}")

    step = {"month": 1, "quarter": 3, "year": 12}[grain]
    periods: list[Period] = []
    year, month = first_start.year, first_start.month

    for index in range(count):
        start = date(year, month, 1)
        end_month_index = month + step - 1
        end_year = year + (end_month_index - 1) // 12
        end_month = (end_month_index - 1) % 12 + 1
        end = _month_end(end_year, end_month)

        if grain == "month":
            pid, label = f"{start:%Y-%m}", f"{start:%b %Y}"
        elif grain == "quarter":
            q = (start.month - 1) // 3 + 1
            pid, label = f"{start.year}-Q{q}", f"Q{q} {start.year}"
        else:
            pid, label = f"{start.year}", f"FY{start.year}"

        periods.append(Period(pid, label, start, end, index, grain))
        month = end_month + 1
        year = end_year + (1 if month > 12 else 0)
        month = 1 if month > 12 else month

    return tuple(periods)


_PERIOD_ID = re.compile(
    r"""^(?:
        (?P<year_only>\d{4})
      | (?P<qy>\d{4})-Q(?P<q>[1-4])
      | (?P<my>\d{4})-(?P<m>0[1-9]|1[0-2])
    )$""",
    re.VERBOSE,
)


def parse_period_id(period_id: str, index: int = 0) -> Period:
    """``"2024-Q1"`` / ``"2024-03"`` / ``"2024"`` → a ``Period``.

    The inverse of what `build_periods` emits, and the reason the period id format is a
    *contract* rather than a label: an uploaded file names its periods in the header
    row and nothing else tells us their grain, length or order. Parsing the id is how
    an upload gets the same `Period.days` that a generated set has — and day count is
    what every efficiency ratio divides by.

    Deliberately strict. A period column headed "Q1" or "Mar-24" is rejected with a
    message naming the accepted forms, rather than guessed at; guessing the year is how
    an upload silently becomes a different set of statements.
    """
    match = _PERIOD_ID.match(period_id.strip())
    if not match:
        raise ValueError(
            f"unrecognised period {period_id!r}. Expected 'YYYY-Qn' (2024-Q1), "
            f"'YYYY-MM' (2024-03) or 'YYYY' (2024)."
        )
    groups = match.groupdict()

    if groups["q"]:
        year, quarter = int(groups["qy"]), int(groups["q"])
        start = date(year, (quarter - 1) * 3 + 1, 1)
        end = _month_end(year, quarter * 3)
        return Period(period_id, f"Q{quarter} {year}", start, end, index, "quarter")

    if groups["m"]:
        year, month = int(groups["my"]), int(groups["m"])
        start = date(year, month, 1)
        return Period(period_id, f"{start:%b %Y}", start, _month_end(year, month), index, "month")

    year = int(groups["year_only"])
    return Period(period_id, f"FY{year}", date(year, 1, 1), date(year, 12, 31), index, "year")


# ------------------------------------------------------------------ postings --


@dataclass(frozen=True, slots=True)
class PostingLine:
    account_code: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO

    @property
    def signed(self) -> Decimal:
        """Debit-positive, matching the vendored engine's ``GLEntry.amount``."""
        return money(self.debit - self.credit)

    @property
    def natural(self) -> Decimal:
        """The movement in this account's own natural direction.

        Positive means "more of what this account normally holds": more cash, more
        revenue, more payables. Reading balances naturally is what lets `derive.py`
        present a magnitude line without a sign flip at every call site.
        """
        return self.signed if is_debit_positive(self.account_code) else money(-self.signed)


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """A balanced journal. ``is_closing`` marks the period-end entry that sweeps the
    P&L accounts into retained earnings.

    Closing entries are excluded when reading a period's P&L (they would zero it) and
    included when reading the balance sheet (they are what makes retained earnings
    accumulate and ``assets = liabilities + equity`` hold exactly).
    """

    id: str
    period_id: str
    date: date
    memo: str
    lines: tuple[PostingLine, ...]
    is_closing: bool = False
    #: The opening balance sheet, dated the day before period 1. Belongs to period 1's
    #: balance sheet but is not a period-1 *movement*, so the cash flow statement uses
    #: it to establish opening cash rather than counting it as a flow.
    is_opening: bool = False

    @property
    def total_debit(self) -> Decimal:
        return money(sum((ln.debit for ln in self.lines), ZERO))

    @property
    def total_credit(self) -> Decimal:
        return money(sum((ln.credit for ln in self.lines), ZERO))

    @property
    def is_balanced(self) -> bool:
        return self.total_debit == self.total_credit

    def touches(self, code: str) -> bool:
        return any(ln.account_code == code for ln in self.lines)


# --------------------------------------------------------------------- lines --


@dataclass(frozen=True, slots=True)
class Line:
    """One presented figure: this line, this period, this amount."""

    period_id: str
    statement: str
    line_code: str
    label: str
    amount: Decimal
    is_subtotal: bool = False


# -------------------------------------------------------------- ground truth --


@dataclass(frozen=True, slots=True)
class AnomalyTruth:
    """One injected anomaly, and what a rule engine ought to make of it.

    ``expected_rule_ids`` is deliberately allowed to be empty. Spec 00 A3 promises a
    ground-truth emitter *"so Projects get labels for free"*, and the label that
    matters most is the honest one: `capex_pause` is a real economic pattern that this
    project ships no rule for. Without at least one such case, flag recall would be
    100% by construction and would measure nothing but wiring (PLAN.md **D-015**).
    """

    anomaly_id: str
    kind: str
    description: str
    period_ids: tuple[str, ...]
    expected_rule_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StatementGroundTruth:
    anomalies: tuple[AnomalyTruth, ...] = ()

    @property
    def expected_rule_ids(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for a in self.anomalies:
            for rid in a.expected_rule_ids:
                seen[rid] = None
        return tuple(seen)

    @property
    def unruled(self) -> tuple[AnomalyTruth, ...]:
        """Injected patterns no shipped rule is expected to catch."""
        return tuple(a for a in self.anomalies if not a.expected_rule_ids)

    def for_rule(self, rule_id: str) -> tuple[AnomalyTruth, ...]:
        return tuple(a for a in self.anomalies if rule_id in a.expected_rule_ids)


# ----------------------------------------------------------------------- set --


@dataclass(frozen=True, slots=True)
class StatementSet:
    """Everything one generated entity-history contains, plus its answer key."""

    seed: int
    profile_name: str
    entity_name: str
    currency: str
    grain: str
    periods: tuple[Period, ...]
    lines: tuple[Line, ...]
    entries: tuple[JournalEntry, ...] = field(repr=False, default=())
    ground_truth: StatementGroundTruth = field(repr=False, default_factory=StatementGroundTruth)

    # -- lookups -------------------------------------------------------------
    def period(self, period_id: str) -> Period | None:
        return next((p for p in self.periods if p.id == period_id), None)

    def amount(self, period_id: str, line_code: str) -> Decimal | None:
        """The figure, or ``None`` if this set does not carry that line.

        ``None`` rather than zero, always. A missing cash flow statement is not a cash
        flow of nought, and the computation engine's `undefined` status (PLAN.md
        **D-007**) depends on being able to tell those apart.
        """
        return next(
            (
                ln.amount
                for ln in self.lines
                if ln.period_id == period_id and ln.line_code == line_code
            ),
            None,
        )

    def series(self, line_code: str) -> tuple[Decimal | None, ...]:
        """One line across every period, in period order."""
        return tuple(self.amount(p.id, line_code) for p in self.periods)

    def statement_lines(self, statement: str, period_id: str) -> tuple[Line, ...]:
        return tuple(
            sorted(
                (
                    ln
                    for ln in self.lines
                    if ln.statement == statement and ln.period_id == period_id
                ),
                key=lambda ln: LINE_ORDER[ln.line_code],
            )
        )

    @property
    def statements_present(self) -> tuple[str, ...]:
        return tuple(sorted({ln.statement for ln in self.lines}))

    @property
    def period_ids(self) -> tuple[str, ...]:
        return tuple(p.id for p in self.periods)

    # -- serialisation -------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Canonical plain-data form, used for hashing and export.

        Hand-written rather than ``dataclasses.asdict`` because `Decimal` must reach
        the hash as a fixed 2-dp *string*. Serialising money through a float would
        undo the point of holding it as a Decimal, silently, at the one step whose job
        is proving the data did not change (finsight hit this; its D-017).
        """
        return {
            "seed": self.seed,
            "profile_name": self.profile_name,
            "entity_name": self.entity_name,
            "currency": self.currency,
            "grain": self.grain,
            "periods": [
                {
                    "id": p.id,
                    "label": p.label,
                    "start": p.start.isoformat(),
                    "end": p.end.isoformat(),
                    "index": p.index,
                    "grain": p.grain,
                    "days": p.days,
                }
                for p in self.periods
            ],
            "lines": [
                {
                    "period_id": ln.period_id,
                    "statement": ln.statement,
                    "line_code": ln.line_code,
                    "label": ln.label,
                    "amount": f"{ln.amount:.2f}",
                    "is_subtotal": ln.is_subtotal,
                }
                for ln in self.lines
            ],
            "ground_truth": {
                "anomalies": [
                    {
                        "anomaly_id": a.anomaly_id,
                        "kind": a.kind,
                        "description": a.description,
                        "period_ids": list(a.period_ids),
                        "expected_rule_ids": list(a.expected_rule_ids),
                    }
                    for a in self.ground_truth.anomalies
                ]
            },
        }


def account_label(code: str) -> str:
    return ACCOUNTS_BY_CODE[code].name
