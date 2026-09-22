"""The types. Pydantic is this package's entire third-party surface."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# `money` and `percent` are distinct on purpose: `1.42` must not satisfy a ref of
# `1.42%`. They are different claims about the world and a checker that conflates them
# has a hole exactly where a model is most likely to slip.
Unit = Literal["money", "percent", "count", "days", "times", "bare"]


class FigureRef(BaseModel):
    """A figure the narrative is permitted to cite."""

    model_config = ConfigDict(frozen=True)

    ref_id: str
    value: Decimal
    unit: Unit = "bare"
    label: str = ""


class NumericToken(BaseModel):
    """A number found in prose, with where it was and how precisely it was written.

    ``precision`` is the count of decimal places **the author actually wrote**. It is the
    heart of the matcher: a model that writes "£3.8m" has claimed one decimal place, and
    is checked to one. A model that writes "£3,815,070.61" has claimed two and is checked
    to two. There is no tolerance setting to tune, because the tolerance is supplied by
    the text itself (D-009 in StatementLens's PLAN).
    """

    model_config = ConfigDict(frozen=True)

    text: str
    start: int
    end: int
    value: Decimal
    unit: Unit
    precision: int
    scale: int = 1  # 1000 for "k", 1_000_000 for "m", …


class TokenVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: NumericToken
    ok: bool
    matched_ref: str | None = None
    reason: str = ""


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdicts: list[TokenVerdict] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True only when every numeric token in the text was verified.

        Vacuously true for prose with no numbers — which is correct: a sentence that
        states no figure cannot state a wrong one. The *harness* separately reports how
        many figures were checked, so "100% fidelity" can never be achieved by writing
        nothing.
        """
        return all(v.ok for v in self.verdicts)

    @property
    def failures(self) -> list[TokenVerdict]:
        return [v for v in self.verdicts if not v.ok]

    @property
    def checked(self) -> int:
        return len(self.verdicts)
