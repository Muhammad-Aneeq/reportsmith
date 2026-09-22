"""Figures → computations → flags, for one period and its comparative."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from app.analysis.flags import Flag, evaluate_rules
from app.analysis.formula import Computation, compute_all
from app.money import pct_change, to_money
from app.periods import period_ref, statements_for

# Line deltas the rules can reference as `delta.<name>`. Kept to an explicit list rather
# than "every line", so a rule referencing `delta.revenue_line` fails loudly at load if
# the name is wrong, instead of silently resolving to None and never firing.
_LINE_DELTAS = {
    "revenue_line": "revenue",
    "cogs_line": "cogs",
    "net_income_line": "net_income",
}


def figures_for(period: str, profile: str, seed: int) -> dict[str, Decimal | None]:
    """Every statement line for a period, as line_code → amount."""
    st = statements_for(profile, seed)
    return {line.line_code: to_money(line.amount) for line in st.lines if line.period_id == period}


@lru_cache(maxsize=32)
def analyse(
    period: str, profile: str, seed: int
) -> tuple[tuple[Computation, ...], tuple[Flag, ...]]:
    """The ratio pack and the flags for one period.

    Cached on the same reasoning as the statement set: pure function of seeded inputs.
    """
    figures = figures_for(period, profile, seed)
    prior_id = period_ref(period).prior_id
    prior_figures = figures_for(prior_id, profile, seed) if prior_id else {}

    computations = compute_all(figures, period)
    prior_computations = compute_all(prior_figures, prior_id) if prior_id else []
    prior_by_id = {c.formula_id: c for c in prior_computations}

    # Ratio deltas, as percentage change. A rule saying "receivable days up >20%" is
    # asking about the change in the ratio, not the ratio itself.
    deltas: dict[str, Decimal | None] = {}
    for comp in computations:
        prior = prior_by_id.get(comp.formula_id)
        deltas[comp.formula_id] = pct_change(comp.value, prior.value) if prior is not None else None
    for alias, line_code in _LINE_DELTAS.items():
        deltas[alias] = pct_change(figures.get(line_code), prior_figures.get(line_code))

    flags = evaluate_rules(computations, figures, deltas, period)
    return tuple(computations), tuple(flags)


def prior_computations_for(period: str, profile: str, seed: int) -> dict[str, Computation]:
    prior_id = period_ref(period).prior_id
    if prior_id is None:
        return {}
    comps, _ = analyse(prior_id, profile, seed)
    return {c.formula_id: c for c in comps}
