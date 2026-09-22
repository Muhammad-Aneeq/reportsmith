"""The shared numeric-fidelity metric (spec 12 §10 / spec 13 §10).

The metric has **two** numbers, and publishing only the first would be dishonest:

``fidelity``       — verified tokens ÷ total tokens. The gate is 100%.
``figures_checked``— how many numeric claims there were at all.

A narrative with no numbers scores 100% fidelity, correctly and uselessly. So the gate
also requires a minimum number of checked figures: a composer that learned to satisfy the
checker by not stating anything would pass the first test and fail the second, which is
the behaviour you want.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from numcheck.models import FigureRef
from numcheck.verify import verify


@dataclass(frozen=True, slots=True)
class FidelityReport:
    sections: int
    figures_checked: int
    figures_verified: int
    failures: list[dict[str, str]] = field(default_factory=list)

    @property
    def fidelity(self) -> Decimal:
        if self.figures_checked == 0:
            return Decimal(100)
        return (
            Decimal(self.figures_verified) / Decimal(self.figures_checked) * Decimal(100)
        ).quantize(Decimal("0.01"))

    def passed(self, *, min_figures: int = 1) -> bool:
        """100% fidelity **and** something actually checked."""
        return self.figures_verified == self.figures_checked and self.figures_checked >= min_figures

    def summary(self) -> str:
        verdict = "PASS" if self.passed() else "FAIL"
        return (
            f"{verdict} numeric-fidelity {self.fidelity}% "
            f"({self.figures_verified}/{self.figures_checked} figures across "
            f"{self.sections} section(s))"
        )


def score(
    narratives: Iterable[tuple[str, str, list[FigureRef], list[str]]],
) -> FidelityReport:
    """Score an iterable of (section_key, text, refs, periods)."""
    checked = verified = sections = 0
    failures: list[dict[str, str]] = []

    for section_key, text, refs, periods in narratives:
        sections += 1
        result = verify(text, refs, periods)
        checked += result.checked
        verified += result.checked - len(result.failures)
        failures.extend(
            {"section": section_key, "token": v.token.text, "reason": v.reason}
            for v in result.failures
        )

    return FidelityReport(
        sections=sections,
        figures_checked=checked,
        figures_verified=verified,
        failures=failures,
    )
