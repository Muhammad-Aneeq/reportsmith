"""ledgerfab.statements — multi-period P&L / balance sheet / cash flow (spec 12 F1).

    from ledgerfab.statements import emit_statements

    st = emit_statements("squeeze", seed=42, periods=8, grain="quarter")
    st.amount("2025-Q4", "current_ratio")     # -> None; ratios are not the emitter's job
    st.amount("2025-Q4", "total_assets")      # -> Decimal('9_412_338.55')
    st.ground_truth.anomalies                 # the answer key, free with every set

**The design in one sentence:** an operating plan becomes balanced double-entry
journals, and the three statements are *derived* from the trial balance — never
authored (PLAN.md **D-003**). Three separately-generated statements are three chances
to disagree; a trial balance cannot disagree with itself. Everything the emitter
guarantees follows from that:

* every journal balances,
* ``assets = liabilities + equity`` at every period end,
* ``retained_earnings_t = retained_earnings_{t-1} + net_income_t − dividends_t``,
* ``cf_net_change_in_cash = cash_t − cash_{t-1}``, to the cent.

**Determinism contract** (spec 00 A3): same profile + seed + shape → byte-identical
set, provable via ``statement_hash``. All randomness routes through
``ledgerfab.rng.Rng``; this package holds no clock, no UUIDs and no global state.

**Reuse.** Nothing here imports from `statementlens`, so lifting this directory into
the shared engine is a move rather than a refactor. See `README.md` in this directory
for the contract another project should code against.
"""

from __future__ import annotations

from datetime import date

from ledgerfab.rng import Rng
from ledgerfab.statements.anomalies import ANOMALIES, ANOMALIES_BY_ID, Anomaly, apply_anomalies
from ledgerfab.statements.chart import (
    ACCOUNTS_BY_CODE,
    LINES_BY_CODE,
    STATEMENT_ACCOUNTS,
    STATEMENT_LINES,
    StatementAccount,
    StatementLineDef,
    lines_for,
)
from ledgerfab.statements.derive import build_lines
from ledgerfab.statements.hashing import statement_hash
from ledgerfab.statements.models import (
    MAX_PERIODS,
    AnomalyTruth,
    JournalEntry,
    Line,
    Period,
    PostingLine,
    StatementGroundTruth,
    StatementSet,
    build_periods,
    parse_period_id,
)
from ledgerfab.statements.plan import BusinessProfile, PeriodPlan, build_plans
from ledgerfab.statements.postings import build_entries
from ledgerfab.statements.profiles import (
    DEFAULT_PROFILE,
    PROFILES,
    StatementProfile,
    get_profile,
)

__all__ = [
    "emit_statements",
    "statement_hash",
    # profiles + knobs
    "StatementProfile",
    "PROFILES",
    "DEFAULT_PROFILE",
    "get_profile",
    "BusinessProfile",
    "PeriodPlan",
    "build_plans",
    # anomalies
    "Anomaly",
    "ANOMALIES",
    "ANOMALIES_BY_ID",
    "apply_anomalies",
    "AnomalyTruth",
    "StatementGroundTruth",
    # the vocabulary
    "STATEMENT_LINES",
    "LINES_BY_CODE",
    "StatementLineDef",
    "lines_for",
    "STATEMENT_ACCOUNTS",
    "ACCOUNTS_BY_CODE",
    "StatementAccount",
    # the data
    "StatementSet",
    "Period",
    "Line",
    "JournalEntry",
    "PostingLine",
    "build_periods",
    "parse_period_id",
    "build_entries",
    "build_lines",
    "MAX_PERIODS",
]

__version__ = "0.1.0"

#: Period 1 of the default grid. Fixed rather than derived from the clock, because a
#: generator that reads the clock is not reproducible — and "same seed, same data"
#: would quietly become "same seed, same data, same day".
DEFAULT_FIRST_START = date(2024, 1, 1)


def emit_statements(
    profile: str | StatementProfile = DEFAULT_PROFILE,
    seed: int = 42,
    periods: int = 8,
    grain: str = "quarter",
    first_start: date = DEFAULT_FIRST_START,
    anomalies: tuple[str, ...] | None = None,
) -> StatementSet:
    """Generate one entity's multi-period statements, plus its ground truth.

    Args:
        profile: ``"steady"``, ``"growth"``, ``"squeeze"``, ``"distress"``, or a
            custom ``StatementProfile``.
        seed: any int. Same seed + profile + shape always yields the same set.
        periods: 1..8 (spec 12 F1 caps multi-period intake at 8).
        grain: ``"month"``, ``"quarter"`` or ``"year"``.
        first_start: the first day of period 1.
        anomalies: override the profile's anomaly list. ``()`` switches them all off,
            which is how a test isolates the underlying business from the injections.
    """
    resolved = get_profile(profile)
    grid = build_periods(periods, grain, first_start)
    root = Rng(seed, f"statements/{resolved.name}")

    plans = build_plans(resolved.business, grid, root.child("plan"))
    selected = resolved.anomalies if anomalies is None else anomalies
    plans, truths = apply_anomalies(plans, selected, root.child("anomalies"))

    entries = build_entries(resolved.business, plans)
    lines = build_lines(entries, grid)

    return StatementSet(
        seed=seed,
        profile_name=resolved.name,
        entity_name=resolved.business.entity_name,
        currency=resolved.business.currency,
        grain=grain,
        periods=grid,
        lines=lines,
        entries=entries,
        ground_truth=StatementGroundTruth(anomalies=truths),
    )
