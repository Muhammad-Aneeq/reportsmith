"""The assembler: template + period → a pack, in template order, with a section for
every template section — always.

The invariant this module exists to hold:

    len(pack.sections) == len(template.sections)

for every possible behaviour of every adapter. Not "usually", not "unless a source is
down". A section whose binding failed is still a section; it just carries a gap instead of
content. `test_no_silent_omission.py` drives twelve adversarial adapter behaviours against
this and asserts the invariant holds for all of them.

Narrative sections are assembled here as *empty* — the composer fills them in a second
pass (`app/narrate/`), because drafting needs the bound frame and the tone rules, and
because a pack should be inspectable before a model has touched it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.adapters.base import Bound, Gap, SourceAdapter, resolve_binding
from app.adapters.frame import Frame
from app.assemble.hashes import snapshot_hash, structure_hash, value_digest
from app.assemble.renderers import (
    build_figure_refs,
    render_flags,
    render_kpi_grid,
    render_table,
)
from app.template.schema import (
    FlagsSection,
    KpiGridSection,
    NarrativeSection,
    TableSection,
    Template,
)


@dataclass
class AssembledSection:
    section_key: str
    title: str
    type: str
    order_index: int
    required: bool
    binding_status: str  # "bound" | "gap"
    content_json: dict[str, Any]
    gaps_json: list[dict[str, Any]]
    frame: Frame | None = None

    @property
    def has_gap(self) -> bool:
        return bool(self.gaps_json)

    def as_row(self) -> dict[str, Any]:
        return {
            "section_key": self.section_key,
            "title": self.title,
            "type": self.type,
            "order_index": self.order_index,
            "required": self.required,
            "binding_status": self.binding_status,
            "content_json": self.content_json,
            "gaps_json": self.gaps_json,
        }


@dataclass
class AssembledPack:
    template_ref: str
    template_id: str
    template_version: int
    period: str
    sections: list[AssembledSection]
    cover: dict[str, Any]
    structure_hash: str
    value_digest: str
    snapshot_hash: str
    snapshot: dict[str, Any] = field(default_factory=dict)

    @property
    def gaps(self) -> list[dict[str, Any]]:
        """Every gap in the pack, flattened for the gaps panel."""
        return [
            {**gap, "section_key": s.section_key, "title": s.title, "required": s.required}
            for s in self.sections
            for gap in s.gaps_json
        ]

    @property
    def blocking_gaps(self) -> list[dict[str, Any]]:
        """Gaps that stand between this pack and issuance (spec 13 F5).

        Only on `required` sections. An optional section that could not bind is
        information; a required one is a hole somebody has to account for.
        """
        return [g for g in self.gaps if g["required"]]


def assemble(
    template: Template,
    period: str,
    adapters: dict[str, SourceAdapter],
) -> AssembledPack:
    """Build the pack. Never raises on adapter trouble — that becomes a gap."""
    sections: list[AssembledSection] = []
    snapshot: dict[str, Any] = {}

    for index, spec in enumerate(template.sections):
        result = resolve_binding(adapters, spec.binding, period)

        if isinstance(result, Gap):
            sections.append(
                AssembledSection(
                    section_key=spec.id,
                    title=spec.title,
                    type=spec.type,
                    order_index=index,
                    required=spec.required,
                    binding_status="gap",
                    # An empty dict, not a fabricated shell. A gapped table must not
                    # render as a table with no rows — those are different facts, and the
                    # UI shows them differently.
                    content_json={},
                    gaps_json=[result.to_json()],
                )
            )
            continue

        assert isinstance(result, Bound)
        frame = result.frame
        snapshot[spec.id] = frame.to_json()

        try:
            content = _render(spec, frame, template)
            gaps: list[dict[str, Any]] = []
        except KeyError as exc:
            # The frame bound but the template asked for a field it does not publish.
            # A rendering failure is still a gap, not a traceback.
            content, gaps = (
                {},
                [
                    {
                        "reason": "selector_invalid",
                        "detail": str(exc).strip("'"),
                        "source": frame.source,
                        "dataset": frame.dataset,
                    }
                ],
            )

        sections.append(
            AssembledSection(
                section_key=spec.id,
                title=spec.title,
                type=spec.type,
                order_index=index,
                required=spec.required,
                binding_status="gap" if gaps else "bound",
                content_json=content,
                gaps_json=gaps,
                frame=frame,
            )
        )

    rows = [s.as_row() for s in sections]
    return AssembledPack(
        template_ref=template.ref,
        template_id=template.id,
        template_version=template.version,
        period=period,
        sections=sections,
        cover=_cover(template, period, sections),
        structure_hash=structure_hash(template.ref, rows),
        value_digest=value_digest(rows),
        snapshot_hash=snapshot_hash(snapshot),
        snapshot=snapshot,
    )


def _render(spec: Any, frame: Frame, template: Template) -> dict[str, Any]:
    style = template.style
    if isinstance(spec, TableSection):
        return render_table(spec, frame, style)
    if isinstance(spec, KpiGridSection):
        return render_kpi_grid(spec, frame, style)
    if isinstance(spec, FlagsSection):
        return render_flags(spec, frame, style)
    if isinstance(spec, NarrativeSection):
        # Left for the composer. The figure refs are computed now, because they are a
        # deterministic function of the bound data and belong to assembly, not drafting —
        # the model must not get to choose which figures it is allowed to cite.
        return {
            "text": "",
            "figure_refs": build_figure_refs(spec, frame, style),
            "tone_rules": list(spec.tone_rules),
            "max_words": spec.max_words,
            "drafted": False,
            "source": frame.source,
            "dataset": frame.dataset,
            "schema_version": frame.schema_version,
        }
    raise TypeError(f"no renderer for {type(spec).__name__}")


def _cover(template: Template, period: str, sections: list[AssembledSection]) -> dict[str, Any]:
    """The generated cover and contents (spec 13 F3)."""
    return {
        "title": template.name,
        "period": period,
        "template_ref": template.ref,
        "contents": [
            {
                "key": s.section_key,
                "title": s.title,
                "type": s.type,
                "status": s.binding_status,
                "required": s.required,
            }
            for s in sections
        ],
        "section_count": len(sections),
        "gap_count": sum(1 for s in sections if s.has_gap),
    }


def default_adapters() -> dict[str, SourceAdapter]:
    """The three sources spec 13 F2 names."""
    from app.adapters.ledgerfab_adapter import LedgerfabAdapter
    from app.adapters.spendsort_adapter import SpendSortAdapter
    from app.adapters.statementlens_adapter import StatementLensAdapter

    return {
        "ledgerfab": LedgerfabAdapter(),
        "spendsort": SpendSortAdapter(),
        "statementlens": StatementLensAdapter(),
    }
