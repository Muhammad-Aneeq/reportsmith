"""The template model — spec 13 F1, and nothing beyond it.

    sections[{id, title, type[table|kpi_grid|narrative|flags], binding, tone_rules,
    required}] + pack-level style rules (voice, rounding, currency display, taboo phrases)

Two properties are enforced structurally rather than by review, because spec 13 §14 names
*"template YAML complexity creep"* as the project's first risk:

**Four section types, closed.** ``Literal[...]`` on a discriminated union. A fifth type is
a validation error, not a silently-ignored section.

**``extra="forbid"`` at every level.** A typo'd key (``tone_rule:`` for ``tone_rules:``)
fails loudly at load. The alternative — pydantic's default of quietly dropping unknown keys
— means a controller edits the tone rules, sees no error, and gets a pack drafted under the
old ones. That is the exact failure this product exists to prevent.

The binding selector is a **closed declarative grammar**, never an expression language
(PLAN.md **D-008**). Three things follow at once: assembly is deterministic and therefore
golden-file testable; a template is user input and `eval` in user input is a remote-code
execution hole; and the editor can point at the offending line because the grammar has a
schema.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SectionType = Literal["table", "kpi_grid", "narrative", "flags"]
SourceName = Literal["ledgerfab", "spendsort", "statementlens"]

AggFn = Literal["sum", "count", "count_distinct", "mean", "min", "max"]
CompareOp = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in"]


class Strict(BaseModel):
    """Base for every node: unknown keys are errors, values are immutable once loaded."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ----------------------------------------------------------------- selector --


class Condition(Strict):
    """One ``where`` clause. Field, operator, value — no expressions, ever."""

    field: str
    op: CompareOp = "eq"
    value: Any = None

    @model_validator(mode="after")
    def _list_ops_take_lists(self) -> Condition:
        if self.op in ("in", "not_in") and not isinstance(self.value, list):
            raise ValueError(f"op {self.op!r} needs a list value, got {type(self.value).__name__}")
        if self.op not in ("in", "not_in") and isinstance(self.value, list):
            raise ValueError(f"op {self.op!r} takes a scalar, not a list")
        return self


class Selector(Strict):
    """A declarative frame query. These keys and no others.

    ``order_by`` entries take a leading ``-`` for descending. The engine always appends
    the group key as a final tiebreak, so the ordering is *total*: two rows with equal
    values cannot swap places between runs and silently break a golden file.
    """

    source: SourceName
    select: str
    where: list[Condition] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregate: dict[str, AggFn] = Field(default_factory=dict)
    order_by: list[str] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=1000)

    @model_validator(mode="after")
    def _aggregate_needs_group_by(self) -> Selector:
        # Without this, `aggregate` with no `group_by` is ambiguous: is it one total row
        # or a no-op? Rather than pick a meaning, refuse — the template author knows which
        # they meant and the error says so.
        if self.aggregate and not self.group_by:
            raise ValueError(
                "aggregate requires group_by; use group_by: [] with an explicit "
                "total_row: true selector if you want a single total"
            )
        return self


# ----------------------------------------------------------------- sections --


class ColumnSpec(Strict):
    """Presentation only. A column spec can never change a number, only how it reads."""

    field: str
    label: str
    align: Literal["left", "right", "center"] = "left"
    format: Literal["text", "money", "percent", "integer", "date"] = "text"


class KpiSpec(Strict):
    id: str
    label: str
    metric: str
    format: Literal["money", "percent", "integer", "ratio", "days"] = "money"
    compare: Literal["prior_period", "none"] = "none"
    direction: Literal["higher_is_better", "lower_is_better", "neutral"] = "neutral"


class SectionBase(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title: str
    required: bool = True
    binding: Selector


class TableSection(SectionBase):
    type: Literal["table"]
    columns: list[ColumnSpec] = Field(min_length=1)
    total_row: bool = False


class KpiGridSection(SectionBase):
    type: Literal["kpi_grid"]
    kpis: list[KpiSpec] = Field(min_length=1)


class NarrativeSection(SectionBase):
    type: Literal["narrative"]
    tone_rules: list[str] = Field(default_factory=list)
    max_words: int = Field(default=220, ge=40, le=1000)


class FlagsSection(SectionBase):
    type: Literal["flags"]
    severity_order: list[str] = Field(default_factory=lambda: ["high", "medium", "low"])


Section = Annotated[
    TableSection | KpiGridSection | NarrativeSection | FlagsSection,
    Field(discriminator="type"),
]


# -------------------------------------------------------------------- style --


class CurrencyStyle(Strict):
    code: str = "GBP"
    symbol: str = "£"
    position: Literal["prefix", "suffix"] = "prefix"
    thousands: str = ","
    negative: Literal["parens", "minus"] = "parens"


class RoundingStyle(Strict):
    money: int = Field(default=0, ge=0, le=6)
    percent: int = Field(default=1, ge=0, le=6)
    ratio: int = Field(default=2, ge=0, le=6)


class PackStyle(Strict):
    """Pack-level style rules — spec 13 F1's second half.

    These are the linter's whole rulebook, which is why they live on the template and
    are versioned with it: changing them is a tracked, evaluable event (spec 13 §8),
    not a prompt tweak somebody made on a Tuesday.
    """

    voice: str = "Third person, past tense, factual. No recommendations."
    rounding: RoundingStyle = Field(default_factory=RoundingStyle)
    currency: CurrencyStyle = Field(default_factory=CurrencyStyle)
    taboo_phrases: list[str] = Field(default_factory=list)
    max_sentence_words: int = Field(default=30, ge=8, le=120)

    @field_validator("taboo_phrases")
    @classmethod
    def _lowercase(cls, phrases: list[str]) -> list[str]:
        # Matching is case-insensitive; normalising here means the linter does not have
        # to re-lower a list on every sentence of every section of every run.
        return [p.strip().lower() for p in phrases if p.strip()]


# ----------------------------------------------------------------- template --


class Template(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    version: int = Field(ge=1)
    description: str = ""
    style: PackStyle = Field(default_factory=PackStyle)
    sections: list[Section] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_section_ids(self) -> Template:
        seen: set[str] = set()
        for section in self.sections:
            if section.id in seen:
                raise ValueError(f"duplicate section id {section.id!r}")
            seen.add(section.id)
        return self

    @model_validator(mode="after")
    def _unique_kpi_ids(self) -> Template:
        for section in self.sections:
            if isinstance(section, KpiGridSection):
                ids = [k.id for k in section.kpis]
                if len(ids) != len(set(ids)):
                    raise ValueError(f"duplicate kpi id in section {section.id!r}")
        return self

    @property
    def ref(self) -> str:
        """The string that identifies this exact template content everywhere."""
        return f"{self.id}@v{self.version}"

    def section(self, section_id: str) -> Section | None:
        return next((s for s in self.sections if s.id == section_id), None)

    @property
    def narrative_sections(self) -> list[NarrativeSection]:
        return [s for s in self.sections if isinstance(s, NarrativeSection)]
